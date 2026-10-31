"""텔레그램 봇 예약 즉시 실행 (long polling · 사용자별 계정 연결).

PC 에서 나가는 ``getUpdates`` 만 쓰므로 공개 URL·포트 개방 없이 LAN 밖의 폰에서 예약을
실행할 수 있다. 봇은 하나를 모두가 함께 쓰고, 텔레그램 계정은 웹 계정 화면에서 발급한
일회용 코드로 사용자에 연결한다. 예약 범위는 예약 관리 화면과 같다: 일반 사용자는 본인이
만든 예약만, 관리자는 전체. 인가는 매 업데이트마다 DB 의 사용자로 판단하므로 비활성화나
연결 해제가 바로 적용된다.

실행은 ``/run`` → 예약 선택 → 확인 카드의 [실행] 순서이고, 확인 카드의 일회용 nonce 가
오발사를 막는다: PC 절전 중 눌린 버튼은 깨어날 때 뒤늦게 도착할 수 있는데 ``CallbackQuery``
에는 시각 필드가 없고, 업데이트는 재전달될 수 있으며, ``trigger_now`` 의 멱등 가드는 실행이
끝난 뒤의 재탭을 막지 못한다. nonce 는 메모리에만 두어 재시작 후 재전달된 탭도 실패하게
하고, 만료는 절전 중에도 흐르는 벽시계로 잰다.

봇 채팅은 E2E 암호화가 아니다. ``trigger_token``·입력값·예외 상세·사이트의 OTP 안내 문구는
채팅으로 보내지 않는다. 봇 토큰은 URL 경로에 들어가므로 httpx 예외를 그대로 올리지 않는다.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

from app.contexts.scheduling.scheduler import _ACTIVE_RUN_STATUSES
from app.core.logging import get_logger
from app.core.status_view import mobile_status_view_map

if TYPE_CHECKING:
    from app.contexts.identity.models import User
    from app.contexts.identity.service import UserService
    from app.contexts.scheduling.scheduler import SchedulerService
    from app.core.settings import E2ESettings

logger = get_logger(__name__)

_POLL_TIMEOUT_S = 30
_RETRY_BASE_S = 1
_RETRY_MAX_S = 60
_WATCH_INTERVAL_S = 5.0
# 절전 복귀 후 폴링이 재개되는 시간보다 커야 한다.
_MAX_MESSAGE_AGE_S = 120
_CONFIRM_TTL_S = 60
# 목록 탭이 카드로 바뀌는 순간의 더블탭이 [실행]까지 통과하지 못하게 한다.
_CONFIRM_MIN_AGE_S = 1
_LINK_TTL_S = 600

_STATUS_LABELS = {code: view["label"] for code, view in mobile_status_view_map().items()}

_HELP_TEXT = "/run 으로 예약 목록을 열어 점검을 실행합니다."
_LINK_GUIDE_TEXT = (
    "e2eTester 계정 연결이 필요합니다. 웹의 텔레그램 연결 화면에서 코드를 받아 주세요."
)
_BAD_LINK_TEXT = "만료되었거나 잘못된 코드입니다. 웹에서 새 코드를 받아 주세요."
_EXPIRED_TEXT = "만료된 버튼입니다. /run 부터 다시 시작해 주세요."
_START_FAILED_TEXT = "점검을 시작하지 못했습니다. 대시보드에서 예약을 확인해 주세요."
_OTP_PROMPT_TEXT = "인증번호가 필요합니다. 이 메시지에 답장으로 보내 주세요."


class TelegramApiError(Exception):
    """Bot API 호출 실패. 메시지에 토큰이 든 URL 을 넣지 않는다."""


@dataclass(frozen=True)
class TelegramLink:
    code: str
    bot_username: str
    url: str


@dataclass(frozen=True)
class _PendingLink:
    user_id: str
    issued_at: float


@dataclass(frozen=True)
class _Confirm:
    nonce: str
    schedule_id: str
    issued_at: float
    user_id: str


@dataclass(frozen=True)
class _OtpTarget:
    schedule_id: str
    user_id: str
    execution_id: str
    otp_run_id: str
    otp_request_id: str


def _label(status: dict) -> str:
    code = status["status"]
    label = _STATUS_LABELS.get(code, code or "-")
    return f"{label} ({status['progress']})" if status["progress"] else str(label)


def _progress_text(status: dict) -> str:
    return f"{status['name']}\n상태: {_label(status)}"


def _is_private(sender: dict | None, chat: dict | None) -> bool:
    if not sender or not chat or chat.get("type") != "private":
        return False
    return sender.get("id") == chat.get("id")


class TelegramBot:
    def __init__(
        self,
        token: str,
        users: UserService,
        schedules: SchedulerService,
        *,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = time.time,
        watch_interval: float = _WATCH_INTERVAL_S,
    ) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._users = users
        self._schedules = schedules
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(10, read=_POLL_TIMEOUT_S + 10)
        )
        self._now = now
        self._watch_interval = watch_interval
        self._username: str | None = None
        self._pending_links: dict[str, _PendingLink] = {}
        self._link_lock = asyncio.Lock()
        # 사용자마다 유효한 확인 카드는 하나다. 새 카드가 이전 카드를 무효화한다.
        self._confirms: dict[int, _Confirm] = {}
        self._watchers: dict[tuple[int, str], asyncio.Task[None]] = {}
        # message_id 는 채팅마다 따로 매겨지므로 채팅과 함께 키로 쓴다.
        self._otp_prompts: dict[tuple[int, int], _OtpTarget] = {}

    async def unlink_user(self, user_id: str) -> None:
        """연결 중인 작업과 직렬화하고 미사용 코드·확인 카드를 함께 폐기한다."""
        async with self._link_lock:
            self._pending_links = {
                code: pending
                for code, pending in self._pending_links.items()
                if pending.user_id != user_id
            }
            self._confirms = {
                chat: confirm
                for chat, confirm in self._confirms.items()
                if confirm.user_id != user_id
            }
            await self._users.unlink_telegram(user_id)

    async def issue_link(self, user_id: str) -> TelegramLink:
        """웹에서 로그인한 사용자에게 일회용 연결 코드를 발급한다(새 코드가 이전 코드를 대체)."""
        username = self._username or (await self._call("getMe"))["username"]
        self._username = username
        async with self._link_lock:
            now = self._now()
            self._pending_links = {
                code: pending
                for code, pending in self._pending_links.items()
                if pending.user_id != user_id and now - pending.issued_at <= _LINK_TTL_S
            }
            code = secrets.token_hex(4).upper()
            self._pending_links[code] = _PendingLink(user_id, now)
        return TelegramLink(code, username, f"https://t.me/{username}?start={code}")

    async def run_forever(self) -> None:
        logger.info("텔레그램 봇 시작", log_event="schedule.telegram_started")
        offset: int | None = None
        delay = _RETRY_BASE_S
        try:
            while True:
                params = {"offset": offset} if offset is not None else {}
                try:
                    updates = await self._call(
                        "getUpdates",
                        timeout=_POLL_TIMEOUT_S,
                        allowed_updates=["message", "callback_query"],
                        **params,
                    )
                except TelegramApiError as exc:
                    logger.warning(
                        "텔레그램 폴링 실패",
                        log_event="schedule.telegram_poll_failed",
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _RETRY_MAX_S)
                    continue
                delay = _RETRY_BASE_S
                for update in updates:
                    offset = update["update_id"] + 1
                    try:
                        await self.handle_update(update)
                    except Exception:  # 업데이트 하나가 폴링을 멈추면 안 된다
                        logger.exception(
                            "텔레그램 업데이트 처리 오류",
                            log_event="schedule.telegram_update_error",
                        )
        finally:
            watchers = list(self._watchers.values())
            for watcher in watchers:
                watcher.cancel()
            await asyncio.gather(*watchers, return_exceptions=True)
            await self._client.aclose()

    async def handle_update(self, update: dict) -> None:
        if (message := update.get("message")) is not None:
            if _is_private(message.get("from"), message.get("chat")):
                await self._on_message(message["chat"]["id"], message)
        elif (query := update.get("callback_query")) is not None:
            chat = (query.get("message") or {}).get("chat")
            if _is_private(query.get("from"), chat):
                user = await self._active_user(chat["id"])
                if user is not None:
                    await self._on_callback(user, chat["id"], query)

    async def _active_user(self, telegram_user_id: int) -> User | None:
        user = await self._users.get_user_by_telegram_id(telegram_user_id)
        return user if user is not None and user.is_active else None

    async def _on_message(self, chat_id: int, message: dict) -> None:
        text = (message.get("text") or "").strip()
        parts = text.split()
        command = parts[0] if parts else ""
        if command in ("/start", "/link") and len(parts) == 2:
            if self._now() - message["date"] > _MAX_MESSAGE_AGE_S:
                await self._send(chat_id, "만료된 연결 메시지입니다. 새로 보내 주세요.")
            else:
                await self._link(chat_id, parts[1])
            return
        reply_id = (message.get("reply_to_message") or {}).get("message_id", 0)
        target = self._otp_prompts.get((chat_id, reply_id))
        user = await self._active_user(chat_id)
        if user is None:
            if target is not None:
                await self._delete(chat_id, message["message_id"])
            if command == "/start":
                await self._send(chat_id, _LINK_GUIDE_TEXT)
            return
        age = self._now() - message["date"]
        if age > _MAX_MESSAGE_AGE_S:
            if target is not None:
                await self._delete(chat_id, message["message_id"])
            await self._send(
                chat_id, f"{int(age // 60)}분 전 메시지라 처리하지 않았습니다. 다시 보내 주세요."
            )
            return
        if target is not None:
            await self._submit_otp(chat_id, target, text, message["message_id"])
        elif text == "/run":
            await self._send_schedule_list(chat_id, user)
        else:
            await self._send(chat_id, _HELP_TEXT)

    async def _link(self, chat_id: int, code: str) -> None:
        async with self._link_lock:
            pending = self._pending_links.pop(code.upper(), None)
            if pending is None or self._now() - pending.issued_at > _LINK_TTL_S:
                await self._send(chat_id, _BAD_LINK_TEXT)
                return
            try:
                user = await self._users.link_telegram(pending.user_id, chat_id)
            except (KeyError, ValueError):
                await self._send(chat_id, _BAD_LINK_TEXT)
                return
        await self._send(chat_id, f"{user.name} 계정에 연결했습니다. {_HELP_TEXT}")

    async def _visible_schedules(self, user: User) -> list[dict]:
        """예약 관리 화면(GET /api/schedules)과 같은 조회 범위."""
        return await self._schedules.list_schedules(
            user_id=None if user.role == "admin" else user.user_id
        )

    async def _find_schedule(self, user: User, schedule_id: str) -> dict | None:
        for schedule in await self._visible_schedules(user):
            if schedule["schedule_id"] == schedule_id:
                return schedule
        return None

    async def _send_schedule_list(self, chat_id: int, user: User) -> None:
        schedules = await self._visible_schedules(user)
        if not schedules:
            await self._send(chat_id, "실행할 수 있는 예약이 없습니다.")
            return
        rows = [
            [{"text": item["name"], "callback_data": f"pick:{item['schedule_id']}"}]
            for item in schedules
        ]
        await self._send(chat_id, "실행할 예약을 고르세요.", reply_markup={"inline_keyboard": rows})

    async def _on_callback(self, user: User, chat_id: int, query: dict) -> None:
        data = query.get("data") or ""
        message_id = query["message"]["message_id"]
        if data.startswith("run:"):
            await self._on_run_tap(user, chat_id, query, data.removeprefix("run:"))
            return
        await self._answer(query)
        if data.startswith("pick:"):
            await self._show_confirm(user, chat_id, message_id, data.removeprefix("pick:"))
        elif data == "cancel":
            self._confirms.pop(chat_id, None)
            await self._edit(chat_id, message_id, "취소했습니다.")

    async def _show_confirm(
        self, user: User, chat_id: int, message_id: int, schedule_id: str
    ) -> None:
        schedule = await self._find_schedule(user, schedule_id)
        if schedule is None:
            await self._edit(chat_id, message_id, "예약을 찾을 수 없습니다.")
            return
        confirm = _Confirm(secrets.token_urlsafe(8), schedule_id, self._now(), user.user_id)
        self._confirms[chat_id] = confirm
        await self._edit(
            chat_id,
            message_id,
            f"{schedule['name']} ({schedule['system_name']})\n실제 사이트 점검을 실행할까요?",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "취소", "callback_data": "cancel"}],
                    [{"text": "실행", "callback_data": f"run:{confirm.nonce}"}],
                ]
            },
        )

    async def _on_run_tap(self, user: User, chat_id: int, query: dict, nonce: str) -> None:
        confirm = self._confirms.get(chat_id)
        if confirm is None or confirm.nonce != nonce or confirm.user_id != user.user_id:
            await self._answer(query, _EXPIRED_TEXT)
            return
        age = self._now() - confirm.issued_at
        if age < _CONFIRM_MIN_AGE_S:
            await self._answer(query, "내용을 확인한 뒤 다시 눌러 주세요.")
            return
        # 첫 await 전에 소비해야 재전달된 탭이 이중 발사되지 않는다.
        del self._confirms[chat_id]
        if age > _CONFIRM_TTL_S:
            await self._answer(query, _EXPIRED_TEXT)
            return
        await self._answer(query)
        await self._start(user, chat_id, query["message"]["message_id"], confirm.schedule_id)

    async def _start(self, user: User, chat_id: int, message_id: int, schedule_id: str) -> None:
        # 카드를 띄운 뒤 권한이 바뀌었을 수 있어 실행 직전에 다시 확인한다.
        current = await self._authorized_user(chat_id, user.user_id, schedule_id)
        if current is None:
            await self._edit(chat_id, message_id, _START_FAILED_TEXT)
            return
        try:
            status = await self._schedules.trigger_now(
                schedule_id, user_id=current.user_id, user_name=current.name
            )
        except (KeyError, ValueError):
            await self._edit(chat_id, message_id, _START_FAILED_TEXT)
            return
        text = _progress_text(status)
        if status["already_running"]:
            text = f"이미 실행 중입니다.\n{text}"
        # 메시지 편집이 실패해도 결과 알림은 받도록 감시를 먼저 건다.
        previous = self._watchers.get((chat_id, schedule_id))
        if previous is not None:
            previous.cancel()
            await asyncio.gather(previous, return_exceptions=True)
        self._watchers[(chat_id, schedule_id)] = asyncio.create_task(
            self._watch(
                chat_id,
                schedule_id,
                message_id,
                text,
                user_id=current.user_id,
                execution_id=status["execution_id"],
            )
        )
        await self._edit(chat_id, message_id, text)

    async def _watch(
        self,
        chat_id: int,
        schedule_id: str,
        message_id: int,
        shown: str | None = None,
        *,
        user_id: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        """진행은 메시지 하나를 편집하고, 알림이 필요한 OTP 요청·결과는 새 메시지로 보낸다."""
        prompt_id: int | None = None
        try:
            if user_id is None:
                initial_user = await self._active_user(chat_id)
                if initial_user is None:
                    return
                user_id = initial_user.user_id
            while True:
                await asyncio.sleep(self._watch_interval)
                try:
                    if await self._authorized_user(chat_id, user_id, schedule_id) is None:
                        return
                    status = await self._schedules.trigger_status(schedule_id)
                    if execution_id is None:
                        execution_id = status["execution_id"]
                    if execution_id is None or status["execution_id"] != execution_id:
                        return
                    target = None
                    if (
                        status["waiting_input"]
                        and status["otp_request_id"]
                        and status["otp_run_id"]
                    ):
                        target = _OtpTarget(
                            schedule_id,
                            user_id,
                            execution_id,
                            status["otp_run_id"],
                            status["otp_request_id"],
                        )
                    if (
                        prompt_id is not None
                        and self._otp_prompts.get((chat_id, prompt_id)) != target
                    ):
                        self._otp_prompts.pop((chat_id, prompt_id), None)
                        await self._delete(chat_id, prompt_id)
                        prompt_id = None
                    if target is not None and prompt_id is None:
                        prompt = await self._send(
                            chat_id, _OTP_PROMPT_TEXT, reply_markup={"force_reply": True}
                        )
                        self._otp_prompts[(chat_id, prompt["message_id"])] = target
                        prompt_id = prompt["message_id"]
                    if status["status"] not in _ACTIVE_RUN_STATUSES:
                        await self._send(
                            chat_id, f"점검 완료: {status['name']}\n결과: {_label(status)}"
                        )
                        return
                    text = _progress_text(status)
                    if text != shown:
                        await self._edit(chat_id, message_id, text)
                        shown = text
                except KeyError:
                    return
                except TelegramApiError as exc:  # 다음 주기에 다시 시도한다
                    logger.warning(
                        "텔레그램 진행 알림 실패",
                        log_event="schedule.telegram_notify_failed",
                        schedule_id=schedule_id,
                        error=str(exc),
                    )
        finally:
            if prompt_id is not None:
                self._otp_prompts.pop((chat_id, prompt_id), None)
                await self._delete(chat_id, prompt_id)
            self._watchers.pop((chat_id, schedule_id), None)

    async def _authorized_user(self, chat_id: int, user_id: str, schedule_id: str) -> User | None:
        user = await self._active_user(chat_id)
        if user is None or user.user_id != user_id:
            return None
        return user if await self._find_schedule(user, schedule_id) is not None else None

    async def _submit_otp(
        self, chat_id: int, target: _OtpTarget, code: str, message_id: int
    ) -> None:
        try:
            if await self._authorized_user(chat_id, target.user_id, target.schedule_id) is None:
                raise ValueError("인증번호 요청 권한이 만료되었습니다.")
            await self._schedules.submit_trigger_otp(
                target.schedule_id,
                code,
                expected_execution_id=target.execution_id,
                expected_otp_run_id=target.otp_run_id,
                expected_otp_request_id=target.otp_request_id,
            )
            notice = "인증번호를 전달했습니다."
        except (KeyError, ValueError):
            notice = "인증번호를 전달하지 못했습니다. 대시보드에서 확인해 주세요."
        finally:
            await self._delete(chat_id, message_id)
        await self._send(chat_id, notice)

    async def _delete(self, chat_id: int, message_id: int) -> None:
        try:
            await self._call("deleteMessage", chat_id=chat_id, message_id=message_id)
        except TelegramApiError as exc:
            logger.warning(
                "텔레그램 메시지 삭제 실패",
                log_event="schedule.telegram_delete_failed",
                error=str(exc),
            )

    async def _send(self, chat_id: int, text: str, **params: Any) -> dict:
        return await self._call("sendMessage", chat_id=chat_id, text=text, **params)

    async def _edit(self, chat_id: int, message_id: int, text: str, **params: Any) -> None:
        await self._call(
            "editMessageText", chat_id=chat_id, message_id=message_id, text=text, **params
        )

    async def _answer(self, query: dict, text: str | None = None) -> None:
        params = {"text": text} if text else {}
        await self._call("answerCallbackQuery", callback_query_id=query["id"], **params)

    async def _call(self, method: str, **params: Any) -> Any:
        # ponytail: 429 retry_after 미처리, 감시 주기 5초면 채팅당 한도에 닿지 않는다.
        try:
            response = await self._client.post(f"{self._base_url}/{method}", json=params)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramApiError(f"{method}: {type(exc).__name__}") from None
        if not body.get("ok"):
            raise TelegramApiError(f"{method}: {response.status_code} {body.get('description')}")
        return body["result"]


def build_telegram_bot(
    settings: E2ESettings, schedules: SchedulerService, users: UserService
) -> TelegramBot | None:
    """봇 토큰이 있을 때만 봇을 만든다."""
    secret = settings.telegram_bot_token
    token = secret.get_secret_value().strip() if secret is not None else ""
    return TelegramBot(token, users, schedules) if token else None
