"""텔레그램 봇 예약 실행 단위 테스트.

실 네트워크 없이 httpx.MockTransport 로 Bot API 를 흉내 내고, 예약 서비스는 페이크를 주입해
① 소유자 인가 ② 지연·중복 입력 차단 ③ 진행 알림 ④ OTP 전달 ⑤ 토큰/PII 비노출을 검증한다.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.contexts.scheduling import telegram_bot as bot_module
from app.contexts.scheduling.telegram_bot import (
    TelegramApiError,
    TelegramBot,
    build_telegram_bot,
)

OWNER = 111
TOKEN = "123:secret-token"
NOW = 1_800_000_000.0


class _FakeSchedules:
    def __init__(self) -> None:
        self.triggered: list[str] = []
        self.otp_calls: list[tuple[str, str]] = []
        self.statuses: list[dict] = []
        self.trigger_error: Exception | None = None
        self.otp_error: Exception | None = None
        self.already_running = False

    async def list_schedules(self) -> list[dict]:
        return [{"schedule_id": "sch_1", "name": "대표홈 점검", "trigger_token": "tok-secret"}]

    async def trigger_now(self, schedule_id: str) -> dict:
        if self.trigger_error is not None:
            raise self.trigger_error
        self.triggered.append(schedule_id)
        payload = _status("RUNNING", progress="0/3")
        payload["already_running"] = self.already_running
        return payload

    async def trigger_status(self, schedule_id: str) -> dict:
        if schedule_id == "gone":
            raise KeyError(schedule_id)
        return self.statuses.pop(0) if self.statuses else _status("PASSED", progress="3/3")

    async def submit_trigger_otp(self, schedule_id: str, otp_code: str) -> dict:
        if self.otp_error is not None:
            raise self.otp_error
        self.otp_calls.append((schedule_id, otp_code))
        return _status("RUNNING")


def _status(status: str | None, *, progress: str | None = None, waiting: bool = False) -> dict:
    return {
        "name": "대표홈 점검",
        "system_name": "대표홈페이지",
        "status": status,
        "progress": progress,
        "waiting_input": waiting,
        "awaiting_prompt": "010-1234-5678 로 받은 인증번호",
        "preparation_error": None,
    }


class _Telegram:
    """Bot API 호출을 기록하는 MockTransport 핸들러."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.next_message_id = 500
        self.fail_methods: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        self.calls.append((method, json.loads(request.content)))
        if method in self.fail_methods:
            return httpx.Response(400, json={"ok": False, "description": "Bad Request"})
        self.next_message_id += 1
        return httpx.Response(
            200, json={"ok": True, "result": {"message_id": self.next_message_id}}
        )

    def of(self, method: str) -> list[dict]:
        return [params for name, params in self.calls if name == method]


class _Clock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> float:
        return self.value


@pytest.fixture
def harness():
    telegram = _Telegram()
    schedules = _FakeSchedules()
    clock = _Clock()
    bot = TelegramBot(
        TOKEN,
        OWNER,
        schedules,
        client=httpx.AsyncClient(transport=httpx.MockTransport(telegram)),
        now=clock,
        watch_interval=0,
    )
    return SimpleNamespace(bot=bot, telegram=telegram, schedules=schedules, clock=clock)


def _message(text: str, *, sender: int = OWNER, age: float = 0, **extra) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "date": int(NOW - age),
            "chat": {"id": sender, "type": "private"},
            "from": {"id": sender},
            "text": text,
            **extra,
        },
    }


def _tap(data: str, *, sender: int = OWNER) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb",
            "from": {"id": sender},
            "data": data,
            "message": {"message_id": 20, "chat": {"id": sender, "type": "private"}},
        },
    }


async def _open_confirm_card(h) -> str:
    """예약을 골라 확인 카드를 띄우고 [실행] 버튼의 callback_data 를 돌려준다."""
    await h.bot.handle_update(_tap("pick:sch_1"))
    rows = h.telegram.of("editMessageText")[-1]["reply_markup"]["inline_keyboard"]
    return next(b["callback_data"] for row in rows for b in row if b["text"] == "실행")


async def _wait_watchers(bot: TelegramBot) -> None:
    await asyncio.gather(*bot._watchers.values())


# --- 인가 ---------------------------------------------------------------- #
async def test_stranger_message_gets_no_reply(harness):
    await harness.bot.handle_update(_message("/run", sender=999))
    assert harness.telegram.calls == []


@pytest.mark.parametrize("chat_id", [-5, OWNER])
async def test_owner_message_in_group_is_ignored(harness, chat_id):
    update = _message("/run")
    update["message"]["chat"] = {"id": chat_id, "type": "group"}
    await harness.bot.handle_update(update)
    assert harness.telegram.calls == []


async def test_stranger_button_tap_cannot_run(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data, sender=999))
    assert harness.schedules.triggered == []


async def test_message_without_sender_is_ignored(harness):
    update = _message("/run")
    del update["message"]["from"]
    await harness.bot.handle_update(update)
    assert harness.telegram.calls == []


# --- 목록 ---------------------------------------------------------------- #
async def test_run_command_lists_schedules_without_starting_anything(harness):
    await harness.bot.handle_update(_message("/run"))
    sent = harness.telegram.of("sendMessage")[0]
    button = sent["reply_markup"]["inline_keyboard"][0][0]
    assert button == {"text": "대표홈 점검", "callback_data": "pick:sch_1"}
    assert harness.schedules.triggered == []
    assert "tok-secret" not in json.dumps(harness.telegram.calls)


async def test_other_text_gets_help(harness):
    await harness.bot.handle_update(_message("/start"))
    assert "/run" in harness.telegram.of("sendMessage")[0]["text"]


async def test_stale_command_is_refused_with_notice(harness):
    await harness.bot.handle_update(_message("/run", age=600))
    sent = harness.telegram.of("sendMessage")
    assert len(sent) == 1
    assert "10분 전" in sent[0]["text"]
    assert "reply_markup" not in sent[0]


# --- 확인 카드 ------------------------------------------------------------ #
async def test_pick_alone_does_not_start(harness):
    await _open_confirm_card(harness)
    assert harness.schedules.triggered == []


async def test_pick_deleted_schedule_shows_notice(harness):
    await harness.bot.handle_update(_tap("pick:gone"))
    assert "삭제" in harness.telegram.of("editMessageText")[0]["text"]


async def test_confirm_starts_schedule(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    assert harness.schedules.triggered == ["sch_1"]


async def test_redelivered_confirm_tap_starts_once(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data))
    await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    assert harness.schedules.triggered == ["sch_1"]


async def test_concurrent_confirm_taps_start_once(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await asyncio.gather(
        harness.bot.handle_update(_tap(run_data)), harness.bot.handle_update(_tap(run_data))
    )
    await _wait_watchers(harness.bot)
    assert harness.schedules.triggered == ["sch_1"]


async def test_double_tap_on_fresh_card_does_not_start(harness):
    run_data = await _open_confirm_card(harness)
    await harness.bot.handle_update(_tap(run_data))
    assert harness.schedules.triggered == []
    # 확인할 시간을 둔 다음 탭은 그대로 유효하다.
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    assert harness.schedules.triggered == ["sch_1"]


async def test_expired_confirm_does_not_start(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 61
    await harness.bot.handle_update(_tap(run_data))
    assert harness.schedules.triggered == []
    assert "만료" in harness.telegram.of("answerCallbackQuery")[-1]["text"]


async def test_confirm_from_before_restart_does_not_start(harness):
    await harness.bot.handle_update(_tap("run:nonce-from-old-process"))
    assert harness.schedules.triggered == []


async def test_newer_card_invalidates_older_card(harness):
    old = await _open_confirm_card(harness)
    await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(old))
    assert harness.schedules.triggered == []


async def test_cancel_invalidates_card(harness):
    run_data = await _open_confirm_card(harness)
    await harness.bot.handle_update(_tap("cancel"))
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data))
    assert harness.schedules.triggered == []
    assert harness.telegram.of("editMessageText")[-1]["text"] == "취소했습니다."


async def test_unknown_callback_only_dismisses_spinner(harness):
    await harness.bot.handle_update(_tap("old-button"))
    assert len(harness.telegram.of("answerCallbackQuery")) == 1
    assert harness.telegram.of("editMessageText") == []


@pytest.mark.parametrize("error", [KeyError("없음"), ValueError("010-1234-5678 입력 오류")])
async def test_trigger_failure_reports_without_detail(harness, error):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    harness.schedules.trigger_error = error
    await harness.bot.handle_update(_tap(run_data))
    text = harness.telegram.of("editMessageText")[-1]["text"]
    assert "시작하지 못했습니다" in text
    assert "010-1234-5678" not in text
    assert harness.bot._watchers == {}


async def test_already_running_is_reported_and_still_watched(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    harness.schedules.already_running = True
    await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    edits = [params["text"] for params in harness.telegram.of("editMessageText")]
    assert any("이미 실행 중" in text for text in edits)
    assert "완료" in harness.telegram.of("sendMessage")[-1]["text"]


async def test_confirm_keeps_watching_when_edit_fails(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    harness.telegram.fail_methods.add("editMessageText")
    with pytest.raises(TelegramApiError):
        await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    assert "완료" in harness.telegram.of("sendMessage")[-1]["text"]


# --- 진행 알림 ------------------------------------------------------------ #
async def test_watch_edits_only_on_change_and_sends_result_as_new_message(harness):
    harness.schedules.statuses = [
        _status("RUNNING", progress="1/3"),
        _status("RUNNING", progress="1/3"),
        _status("RUNNING", progress="2/3"),
        _status("ANOMALY", progress="2/3"),
    ]
    await harness.bot._watch("sch_1", 20)
    assert len(harness.telegram.of("editMessageText")) == 2
    result = harness.telegram.of("sendMessage")[-1]
    assert "완료" in result["text"]
    assert "2/3" in result["text"]


async def test_watch_stops_when_schedule_is_deleted(harness):
    await harness.bot._watch("gone", 20)
    assert harness.telegram.calls == []


async def test_watch_retries_result_after_send_failure(harness, monkeypatch):
    harness.schedules.statuses = [_status("PASSED", progress="3/3")] * 2
    original = harness.bot._send
    attempts = []

    async def flaky(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise TelegramApiError("sendMessage: 500")
        return await original(*args, **kwargs)

    monkeypatch.setattr(harness.bot, "_send", flaky)
    await harness.bot._watch("sch_1", 20)
    assert len(attempts) == 2
    assert len(harness.telegram.of("sendMessage")) == 1


# --- OTP ---------------------------------------------------------------- #
async def test_waiting_input_prompts_once_without_site_prompt(harness):
    waiting = _status("WAITING_INPUT", waiting=True)
    harness.schedules.statuses = [waiting, waiting, _status("RUNNING"), _status("PASSED")]
    await harness.bot._watch("sch_1", 20)
    prompts = [p for p in harness.telegram.of("sendMessage") if "reply_markup" in p]
    assert len(prompts) == 1
    assert prompts[0]["reply_markup"]["force_reply"] is True
    assert "010-1234-5678" not in prompts[0]["text"]


async def test_prompt_is_removed_when_otp_arrives_by_sms(harness):
    harness.schedules.statuses = [_status("WAITING_INPUT", waiting=True), _status("PASSED")]
    await harness.bot._watch("sch_1", 20)
    assert len(harness.telegram.of("deleteMessage")) == 1
    assert harness.bot._otp_prompts == {}


async def _prompt_otp(h) -> int:
    h.schedules.statuses = [_status("WAITING_INPUT", waiting=True)]
    task = asyncio.create_task(h.bot._watch("sch_1", 20))
    while not h.bot._otp_prompts:
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return next(iter(h.bot._otp_prompts))


async def test_otp_reply_is_submitted_then_deleted(harness):
    prompt_id = await _prompt_otp(harness)
    await harness.bot.handle_update(
        _message(" 123456 ", reply_to_message={"message_id": prompt_id})
    )
    assert harness.schedules.otp_calls == [("sch_1", "123456")]
    assert harness.telegram.of("deleteMessage")[-1]["message_id"] == 10
    assert "123456" not in json.dumps(harness.telegram.of("sendMessage"))


async def test_otp_is_deleted_even_when_submit_fails(harness):
    prompt_id = await _prompt_otp(harness)
    harness.schedules.otp_error = KeyError("대기 없음")
    await harness.bot.handle_update(_message("123456", reply_to_message={"message_id": prompt_id}))
    assert harness.telegram.of("deleteMessage")[-1]["message_id"] == 10
    assert "전달하지 못했습니다" in harness.telegram.of("sendMessage")[-1]["text"]


async def test_plain_text_is_not_submitted_as_otp(harness):
    await _prompt_otp(harness)
    await harness.bot.handle_update(_message("123456"))
    assert harness.schedules.otp_calls == []


async def test_stale_otp_reply_is_not_submitted(harness):
    prompt_id = await _prompt_otp(harness)
    await harness.bot.handle_update(
        _message("123456", age=600, reply_to_message={"message_id": prompt_id})
    )
    assert harness.schedules.otp_calls == []


# --- 토큰 비노출 ---------------------------------------------------------- #
async def test_network_error_never_exposes_token():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"연결 실패 {request.url}")

    bot = TelegramBot(
        TOKEN,
        OWNER,
        _FakeSchedules(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(boom)),
    )
    with pytest.raises(TelegramApiError) as caught:
        await bot._call("getUpdates")
    formatted = "".join(traceback.format_exception(caught.value))
    assert TOKEN not in formatted


async def test_api_error_response_raises_with_description(harness):
    harness.telegram.fail_methods.add("sendMessage")
    with pytest.raises(TelegramApiError, match="Bad Request"):
        await harness.bot._call("sendMessage")


# --- 폴링 루프 ------------------------------------------------------------ #
async def test_polling_survives_errors_and_confirms_offset(monkeypatch):
    monkeypatch.setattr(bot_module, "_RETRY_BASE_S", 0)
    offsets: list[int | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = json.loads(request.content)
        if not request.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        assert params["allowed_updates"] == ["message", "callback_query"]
        offsets.append(params.get("offset"))
        if len(offsets) == 1:
            raise httpx.ReadTimeout("절전 복귀")
        if len(offsets) == 2:
            # date 가 없어 처리 중 예외가 나는 소유자 메시지
            chat = {"id": OWNER, "type": "private"}
            bad = {"update_id": 7, "message": {"chat": chat, "from": {"id": OWNER}}}
            return httpx.Response(200, json={"ok": True, "result": [bad]})
        raise asyncio.CancelledError  # 앱 종료와 같은 경로로 루프를 끝낸다

    bot = TelegramBot(
        TOKEN,
        OWNER,
        _FakeSchedules(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(asyncio.CancelledError):
        await bot.run_forever()
    assert offsets == [None, None, 8]


# --- 설정 ---------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("token", "owner"), [(None, None), (SecretStr(TOKEN), None), (None, OWNER)]
)
def test_bot_stays_off_unless_fully_configured(token, owner):
    settings = SimpleNamespace(telegram_bot_token=token, telegram_owner_id=owner)
    assert build_telegram_bot(settings, _FakeSchedules()) is None


def test_bot_is_built_when_configured():
    settings = SimpleNamespace(telegram_bot_token=SecretStr(TOKEN), telegram_owner_id=OWNER)
    assert isinstance(build_telegram_bot(settings, _FakeSchedules()), TelegramBot)


def test_blank_owner_id_in_env_means_unset(monkeypatch):
    from app.core.settings import E2ESettings

    monkeypatch.setenv("E2E_TELEGRAM_OWNER_ID", "")
    assert E2ESettings(_env_file=None).telegram_owner_id is None
