"""텔레그램 봇 예약 즉시 실행 (long polling · 소유자 1인 전용).

PC 에서 나가는 ``getUpdates`` 만 쓰므로 공개 URL·포트 개방 없이 LAN 밖의 폰에서 예약을
실행할 수 있다. 실행은 ``/run`` → 예약 선택 → 확인 카드의 [실행] 순서이고, 확인 카드의
일회용 nonce 가 오발사를 막는다: PC 절전 중 눌린 버튼은 깨어날 때 뒤늦게 도착할 수 있는데
``CallbackQuery`` 에는 시각 필드가 없고, 업데이트는 재전달될 수 있으며, ``trigger_now`` 의
멱등 가드는 실행이 끝난 뒤의 재탭을 막지 못한다. nonce 는 메모리에만 두어 재시작 후
재전달된 탭도 실패하게 하고, 만료는 절전 중에도 흐르는 벽시계로 잰다.

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

_STATUS_LABELS = {code: view["label"] for code, view in mobile_status_view_map().items()}

_HELP_TEXT = "/run 으로 예약 목록을 열어 점검을 실행합니다."
_EXPIRED_TEXT = "만료된 버튼입니다. /run 부터 다시 시작해 주세요."
_START_FAILED_TEXT = "점검을 시작하지 못했습니다. 대시보드에서 예약을 확인해 주세요."
_OTP_PROMPT_TEXT = "인증번호가 필요합니다. 이 메시지에 답장으로 보내 주세요."


class TelegramApiError(Exception):
    """Bot API 호출 실패. 메시지에 토큰이 든 URL 을 넣지 않는다."""


@dataclass(frozen=True)
class _Confirm:
    nonce: str
    schedule_id: str
    issued_at: float


def _label(status: dict) -> str:
    code = status["status"]
    label = _STATUS_LABELS.get(code, code or "-")
    return f"{label} ({status['progress']})" if status["progress"] else str(label)


def _progress_text(status: dict) -> str:
    return f"{status['name']}\n상태: {_label(status)}"


class TelegramBot:
    def __init__(
        self,
        token: str,
        owner_id: int,
        schedules: SchedulerService,
        *,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = time.time,
        watch_interval: float = _WATCH_INTERVAL_S,
    ) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._owner_id = owner_id
        self._schedules = schedules
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(10, read=_POLL_TIMEOUT_S + 10)
        )
        self._now = now
        self._watch_interval = watch_interval
        # 소유자가 한 명이라 유효한 확인 카드도 하나뿐이다. 새 카드가 이전 카드를 무효화한다.
        self._confirm: _Confirm | None = None
        self._watchers: dict[str, asyncio.Task[None]] = {}
        self._otp_prompts: dict[int, str] = {}

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
            for watcher in self._watchers.values():
                watcher.cancel()
            await self._client.aclose()

    async def handle_update(self, update: dict) -> None:
        if (message := update.get("message")) is not None:
            if self._is_owner(message.get("from"), message.get("chat")):
                await self._on_message(message)
        elif (query := update.get("callback_query")) is not None:
            if self._is_owner(query.get("from"), (query.get("message") or {}).get("chat")):
                await self._on_callback(query)

    def _is_owner(self, sender: dict | None, chat: dict | None) -> bool:
        if not sender or not chat or chat.get("type") != "private":
            return False
        return sender.get("id") == chat.get("id") == self._owner_id

    async def _on_message(self, message: dict) -> None:
        age = self._now() - message["date"]
        if age > _MAX_MESSAGE_AGE_S:
            await self._send(
                f"{int(age // 60)}분 전 메시지라 처리하지 않았습니다. 다시 보내 주세요."
            )
            return
        text = (message.get("text") or "").strip()
        reply_id = (message.get("reply_to_message") or {}).get("message_id", 0)
        schedule_id = self._otp_prompts.get(reply_id)
        if schedule_id is not None:
            await self._submit_otp(schedule_id, text, message["message_id"])
        elif text == "/run":
            await self._send_schedule_list()
        else:
            await self._send(_HELP_TEXT)

    async def _send_schedule_list(self) -> None:
        schedules = await self._schedules.list_schedules()
        if not schedules:
            await self._send("등록된 예약이 없습니다.")
            return
        rows = [
            [{"text": item["name"], "callback_data": f"pick:{item['schedule_id']}"}]
            for item in schedules
        ]
        await self._send("실행할 예약을 고르세요.", reply_markup={"inline_keyboard": rows})

    async def _on_callback(self, query: dict) -> None:
        data = query.get("data") or ""
        message_id = query["message"]["message_id"]
        if data.startswith("run:"):
            await self._on_run_tap(query, data.removeprefix("run:"))
            return
        await self._answer(query)
        if data.startswith("pick:"):
            await self._show_confirm(message_id, data.removeprefix("pick:"))
        elif data == "cancel":
            self._confirm = None
            await self._edit(message_id, "취소했습니다.")

    async def _show_confirm(self, message_id: int, schedule_id: str) -> None:
        try:
            status = await self._schedules.trigger_status(schedule_id)
        except KeyError:
            await self._edit(message_id, "삭제된 예약입니다.")
            return
        confirm = _Confirm(secrets.token_urlsafe(8), schedule_id, self._now())
        self._confirm = confirm
        await self._edit(
            message_id,
            f"{status['name']} ({status['system_name']})\n실제 사이트 점검을 실행할까요?",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "취소", "callback_data": "cancel"}],
                    [{"text": "실행", "callback_data": f"run:{confirm.nonce}"}],
                ]
            },
        )

    async def _on_run_tap(self, query: dict, nonce: str) -> None:
        confirm = self._confirm
        if confirm is None or confirm.nonce != nonce:
            await self._answer(query, _EXPIRED_TEXT)
            return
        age = self._now() - confirm.issued_at
        if age < _CONFIRM_MIN_AGE_S:
            await self._answer(query, "내용을 확인한 뒤 다시 눌러 주세요.")
            return
        # 첫 await 전에 소비해야 재전달된 탭이 이중 발사되지 않는다.
        self._confirm = None
        if age > _CONFIRM_TTL_S:
            await self._answer(query, _EXPIRED_TEXT)
            return
        await self._answer(query)
        await self._start(query["message"]["message_id"], confirm.schedule_id)

    async def _start(self, message_id: int, schedule_id: str) -> None:
        try:
            status = await self._schedules.trigger_now(schedule_id)
        except (KeyError, ValueError):
            await self._edit(message_id, _START_FAILED_TEXT)
            return
        text = _progress_text(status)
        if status["already_running"]:
            text = f"이미 실행 중입니다.\n{text}"
        # 메시지 편집이 실패해도 결과 알림은 받도록 감시를 먼저 건다.
        if schedule_id not in self._watchers:
            self._watchers[schedule_id] = asyncio.create_task(
                self._watch(schedule_id, message_id, text)
            )
        await self._edit(message_id, text)

    async def _watch(self, schedule_id: str, message_id: int, shown: str | None = None) -> None:
        """진행은 메시지 하나를 편집하고, 알림이 필요한 OTP 요청·결과는 새 메시지로 보낸다."""
        prompt_id: int | None = None
        try:
            while True:
                await asyncio.sleep(self._watch_interval)
                try:
                    status = await self._schedules.trigger_status(schedule_id)
                    if status["waiting_input"] and prompt_id is None:
                        prompt = await self._send(
                            _OTP_PROMPT_TEXT, reply_markup={"force_reply": True}
                        )
                        self._otp_prompts[prompt["message_id"]] = schedule_id
                        prompt_id = prompt["message_id"]
                    elif not status["waiting_input"] and prompt_id is not None:
                        self._otp_prompts.pop(prompt_id, None)
                        await self._delete(prompt_id)
                        prompt_id = None
                    if status["status"] not in _ACTIVE_RUN_STATUSES:
                        await self._send(f"점검 완료: {status['name']}\n결과: {_label(status)}")
                        return
                    text = _progress_text(status)
                    if text != shown:
                        await self._edit(message_id, text)
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
            self._watchers.pop(schedule_id, None)

    async def _submit_otp(self, schedule_id: str, code: str, message_id: int) -> None:
        try:
            await self._schedules.submit_trigger_otp(schedule_id, code)
            notice = "인증번호를 전달했습니다."
        except (KeyError, ValueError):
            notice = "인증번호를 전달하지 못했습니다. 대시보드에서 확인해 주세요."
        finally:
            await self._delete(message_id)
        await self._send(notice)

    async def _delete(self, message_id: int) -> None:
        try:
            await self._call("deleteMessage", chat_id=self._owner_id, message_id=message_id)
        except TelegramApiError as exc:
            logger.warning(
                "텔레그램 메시지 삭제 실패",
                log_event="schedule.telegram_delete_failed",
                error=str(exc),
            )

    async def _send(self, text: str, **params: Any) -> dict:
        return await self._call("sendMessage", chat_id=self._owner_id, text=text, **params)

    async def _edit(self, message_id: int, text: str, **params: Any) -> None:
        await self._call(
            "editMessageText", chat_id=self._owner_id, message_id=message_id, text=text, **params
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


def build_telegram_bot(settings: E2ESettings, schedules: SchedulerService) -> TelegramBot | None:
    """토큰과 소유자 ID 가 모두 있을 때만 봇을 만든다(인가 없는 봇은 띄우지 않는다)."""
    secret = settings.telegram_bot_token
    token = secret.get_secret_value().strip() if secret is not None else ""
    owner_id = settings.telegram_owner_id
    if token and owner_id is not None:
        return TelegramBot(token, owner_id, schedules)
    if token or owner_id is not None:
        logger.warning(
            "E2E_TELEGRAM_BOT_TOKEN 과 E2E_TELEGRAM_OWNER_ID 를 모두 설정해야 봇이 켜집니다.",
            log_event="schedule.telegram_config_incomplete",
        )
    return None
