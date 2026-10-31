"""텔레그램 봇 예약 실행 단위 테스트.

실 네트워크 없이 httpx.MockTransport 로 Bot API 를 흉내 내고, 예약·사용자 서비스는 페이크를
주입해 ① 사용자별 인가와 예약 범위 ② 계정 연결 ③ 지연·중복 입력 차단 ④ 진행 알림
⑤ OTP 전달 ⑥ 토큰/PII 비노출을 검증한다.
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

ALICE = 111
BOB = 222
ADMIN = 333
TOKEN = "123:secret-token"
NOW = 1_800_000_000.0


class _FakeSchedules:
    def __init__(self) -> None:
        self.items = [
            {
                "schedule_id": "sch_a",
                "name": "앨리스 점검",
                "system_name": "대표홈페이지",
                "owner": "usr_alice",
                "trigger_token": "tok-secret",
            },
            {
                "schedule_id": "sch_b",
                "name": "밥 점검",
                "system_name": "모바일홈페이지",
                "owner": "usr_bob",
                "trigger_token": "tok-secret-2",
            },
        ]
        self.list_filters: list[str | None] = []
        self.triggered: list[tuple[str, str | None, str | None]] = []
        self.otp_calls: list[tuple[str, str]] = []
        self.statuses: list[dict] = []
        self.trigger_error: Exception | None = None
        self.otp_error: Exception | None = None
        self.already_running = False

    async def list_schedules(self, user_id: str | None = None) -> list[dict]:
        self.list_filters.append(user_id)
        return [s for s in self.items if user_id is None or s["owner"] == user_id]

    async def trigger_now(self, schedule_id, user_id=None, user_name=None) -> dict:
        if self.trigger_error is not None:
            raise self.trigger_error
        self.triggered.append((schedule_id, user_id, user_name))
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


class _FakeUsers:
    def __init__(self) -> None:
        self.by_telegram = {
            ALICE: _user("usr_alice", "앨리스"),
            BOB: _user("usr_bob", "밥"),
            ADMIN: _user("usr_admin", "관리자", role="admin"),
        }
        self.linked: list[tuple[str, int]] = []

    async def get_user_by_telegram_id(self, telegram_user_id: int):
        return self.by_telegram.get(telegram_user_id)

    async def link_telegram(self, user_id: str, telegram_user_id: int):
        self.linked.append((user_id, telegram_user_id))
        linked = _user(user_id, "연결된 사용자")
        self.by_telegram[telegram_user_id] = linked
        return linked


def _user(user_id: str, name: str, *, role: str = "user", active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, name=name, role=role, is_active=active)


def _status(status: str | None, *, progress: str | None = None, waiting: bool = False) -> dict:
    return {
        "name": "앨리스 점검",
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
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"username": "e2e_check_bot"}})
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
    users = _FakeUsers()
    clock = _Clock()
    bot = TelegramBot(
        TOKEN,
        users,
        schedules,
        client=httpx.AsyncClient(transport=httpx.MockTransport(telegram)),
        now=clock,
        watch_interval=0,
    )
    return SimpleNamespace(
        bot=bot, telegram=telegram, schedules=schedules, users=users, clock=clock
    )


def _message(text: str, *, sender: int = ALICE, age: float = 0, **extra) -> dict:
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


def _tap(data: str, *, sender: int = ALICE, chat: int | None = None) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb",
            "from": {"id": sender},
            "data": data,
            "message": {"message_id": 20, "chat": {"id": chat or sender, "type": "private"}},
        },
    }


async def _open_confirm_card(h, *, schedule_id: str = "sch_a", sender: int = ALICE) -> str:
    """예약을 골라 확인 카드를 띄우고 [실행] 버튼의 callback_data 를 돌려준다."""
    await h.bot.handle_update(_tap(f"pick:{schedule_id}", sender=sender))
    rows = h.telegram.of("editMessageText")[-1]["reply_markup"]["inline_keyboard"]
    return next(b["callback_data"] for row in rows for b in row if b["text"] == "실행")


async def _wait_watchers(bot: TelegramBot) -> None:
    await asyncio.gather(*bot._watchers.values())


# --- 인가 ---------------------------------------------------------------- #
async def test_unlinked_sender_gets_no_reply_to_run(harness):
    await harness.bot.handle_update(_message("/run", sender=999))
    assert harness.telegram.calls == []


async def test_unlinked_sender_gets_link_guide_on_start(harness):
    await harness.bot.handle_update(_message("/start", sender=999))
    assert "연결" in harness.telegram.of("sendMessage")[0]["text"]
    assert harness.telegram.of("sendMessage")[0]["chat_id"] == 999


async def test_inactive_user_is_treated_as_unlinked(harness):
    harness.users.by_telegram[ALICE] = _user("usr_alice", "앨리스", active=False)
    await harness.bot.handle_update(_message("/run"))
    assert harness.telegram.calls == []


@pytest.mark.parametrize("chat_id", [-5, ALICE])
async def test_linked_user_message_in_group_is_ignored(harness, chat_id):
    update = _message("/run")
    update["message"]["chat"] = {"id": chat_id, "type": "group"}
    await harness.bot.handle_update(update)
    assert harness.telegram.calls == []


async def test_unlinked_button_tap_cannot_run(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data, sender=999))
    assert harness.schedules.triggered == []


async def test_message_without_sender_is_ignored(harness):
    update = _message("/run")
    del update["message"]["from"]
    await harness.bot.handle_update(update)
    assert harness.telegram.calls == []


# --- 사용자별 예약 범위 ---------------------------------------------------- #
async def test_user_lists_only_own_schedules(harness):
    await harness.bot.handle_update(_message("/run"))
    rows = harness.telegram.of("sendMessage")[0]["reply_markup"]["inline_keyboard"]
    assert [row[0]["text"] for row in rows] == ["앨리스 점검"]
    assert harness.schedules.list_filters == ["usr_alice"]
    assert harness.schedules.triggered == []
    assert "tok-secret" not in json.dumps(harness.telegram.calls)


async def test_admin_lists_all_schedules(harness):
    await harness.bot.handle_update(_message("/run", sender=ADMIN))
    rows = harness.telegram.of("sendMessage")[0]["reply_markup"]["inline_keyboard"]
    assert len(rows) == 2
    assert harness.schedules.list_filters == [None]


async def test_user_cannot_open_card_for_others_schedule(harness):
    await harness.bot.handle_update(_tap("pick:sch_b"))
    assert "찾을 수 없습니다" in harness.telegram.of("editMessageText")[0]["text"]
    assert "밥 점검" not in json.dumps(harness.telegram.calls, ensure_ascii=False)


async def test_run_is_refused_when_schedule_left_user_scope(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    harness.schedules.items[0]["owner"] = "usr_other"
    await harness.bot.handle_update(_tap(run_data))
    assert harness.schedules.triggered == []


async def test_run_is_attributed_to_the_tapping_user(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    assert harness.schedules.triggered == [("sch_a", "usr_alice", "앨리스")]


async def test_cards_of_two_users_do_not_invalidate_each_other(harness):
    alice_data = await _open_confirm_card(harness)
    bob_data = await _open_confirm_card(harness, schedule_id="sch_b", sender=BOB)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(alice_data))
    await harness.bot.handle_update(_tap(bob_data, sender=BOB))
    await _wait_watchers(harness.bot)
    assert {item[0] for item in harness.schedules.triggered} == {"sch_a", "sch_b"}


async def test_user_cannot_use_another_users_card(harness):
    alice_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(alice_data, sender=BOB))
    assert harness.schedules.triggered == []


async def test_result_goes_to_the_user_who_started(harness):
    run_data = await _open_confirm_card(harness, schedule_id="sch_b", sender=BOB)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data, sender=BOB))
    await _wait_watchers(harness.bot)
    assert harness.telegram.of("sendMessage")[-1]["chat_id"] == BOB


# --- 계정 연결 ------------------------------------------------------------ #
async def test_issue_link_returns_code_and_bot_url(harness):
    link = await harness.bot.issue_link("usr_new")
    assert link.bot_username == "e2e_check_bot"
    assert link.url == f"https://t.me/e2e_check_bot?start={link.code}"
    await harness.bot.issue_link("usr_new")
    assert len(harness.telegram.of("getMe")) == 1


@pytest.mark.parametrize("command", ["/start", "/link"])
async def test_valid_code_links_sender(harness, command):
    link = await harness.bot.issue_link("usr_new")
    await harness.bot.handle_update(_message(f"{command} {link.code}", sender=999))
    assert harness.users.linked == [("usr_new", 999)]
    assert "연결" in harness.telegram.of("sendMessage")[-1]["text"]


async def test_code_is_case_insensitive(harness):
    link = await harness.bot.issue_link("usr_new")
    await harness.bot.handle_update(_message(f"/link {link.code.lower()}", sender=999))
    assert harness.users.linked == [("usr_new", 999)]


async def test_code_is_single_use(harness):
    link = await harness.bot.issue_link("usr_new")
    await harness.bot.handle_update(_message(f"/link {link.code}", sender=999))
    await harness.bot.handle_update(_message(f"/link {link.code}", sender=998))
    assert harness.users.linked == [("usr_new", 999)]


async def test_expired_code_does_not_link(harness):
    link = await harness.bot.issue_link("usr_new")
    harness.clock.value += 601
    await harness.bot.handle_update(_message(f"/link {link.code}", sender=999))
    assert harness.users.linked == []
    assert "만료" in harness.telegram.of("sendMessage")[-1]["text"]


async def test_wrong_code_does_not_link(harness):
    await harness.bot.issue_link("usr_new")
    await harness.bot.handle_update(_message("/link WRONG", sender=999))
    assert harness.users.linked == []


async def test_new_code_replaces_users_previous_code(harness):
    first = await harness.bot.issue_link("usr_new")
    await harness.bot.issue_link("usr_new")
    await harness.bot.handle_update(_message(f"/link {first.code}", sender=999))
    assert harness.users.linked == []


async def test_group_cannot_consume_code(harness):
    link = await harness.bot.issue_link("usr_new")
    update = _message(f"/link {link.code}", sender=999)
    update["message"]["chat"] = {"id": -5, "type": "group"}
    await harness.bot.handle_update(update)
    assert harness.users.linked == []


# --- 메시지 처리 ---------------------------------------------------------- #
async def test_other_text_gets_help(harness):
    await harness.bot.handle_update(_message("안녕"))
    assert "/run" in harness.telegram.of("sendMessage")[0]["text"]


async def test_stale_command_is_refused_with_notice(harness):
    await harness.bot.handle_update(_message("/run", age=600))
    sent = harness.telegram.of("sendMessage")
    assert len(sent) == 1
    assert "10분 전" in sent[0]["text"]
    assert "reply_markup" not in sent[0]


async def test_no_schedules_notice(harness):
    harness.schedules.items.clear()
    await harness.bot.handle_update(_message("/run"))
    assert "없습니다" in harness.telegram.of("sendMessage")[0]["text"]


# --- 확인 카드 ------------------------------------------------------------ #
async def test_pick_alone_does_not_start(harness):
    await _open_confirm_card(harness)
    assert harness.schedules.triggered == []


async def test_redelivered_confirm_tap_starts_once(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data))
    await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    assert len(harness.schedules.triggered) == 1


async def test_concurrent_confirm_taps_start_once(harness):
    run_data = await _open_confirm_card(harness)
    harness.clock.value += 5
    await asyncio.gather(
        harness.bot.handle_update(_tap(run_data)), harness.bot.handle_update(_tap(run_data))
    )
    await _wait_watchers(harness.bot)
    assert len(harness.schedules.triggered) == 1


async def test_double_tap_on_fresh_card_does_not_start(harness):
    run_data = await _open_confirm_card(harness)
    await harness.bot.handle_update(_tap(run_data))
    assert harness.schedules.triggered == []
    # 확인할 시간을 둔 다음 탭은 그대로 유효하다.
    harness.clock.value += 5
    await harness.bot.handle_update(_tap(run_data))
    await _wait_watchers(harness.bot)
    assert len(harness.schedules.triggered) == 1


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
    await harness.bot._watch(ALICE, "sch_a", 20)
    assert len(harness.telegram.of("editMessageText")) == 2
    result = harness.telegram.of("sendMessage")[-1]
    assert "완료" in result["text"]
    assert "2/3" in result["text"]


async def test_watch_stops_when_schedule_is_deleted(harness):
    await harness.bot._watch(ALICE, "gone", 20)
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
    await harness.bot._watch(ALICE, "sch_a", 20)
    assert len(attempts) == 2
    assert len(harness.telegram.of("sendMessage")) == 1


# --- OTP ---------------------------------------------------------------- #
async def test_waiting_input_prompts_once_without_site_prompt(harness):
    waiting = _status("WAITING_INPUT", waiting=True)
    harness.schedules.statuses = [waiting, waiting, _status("RUNNING"), _status("PASSED")]
    await harness.bot._watch(ALICE, "sch_a", 20)
    prompts = [p for p in harness.telegram.of("sendMessage") if "reply_markup" in p]
    assert len(prompts) == 1
    assert prompts[0]["reply_markup"]["force_reply"] is True
    assert "010-1234-5678" not in prompts[0]["text"]


async def test_prompt_is_removed_when_otp_arrives_by_sms(harness):
    harness.schedules.statuses = [_status("WAITING_INPUT", waiting=True), _status("PASSED")]
    await harness.bot._watch(ALICE, "sch_a", 20)
    assert len(harness.telegram.of("deleteMessage")) == 1
    assert harness.bot._otp_prompts == {}


async def _prompt_otp(h, chat_id: int = ALICE, schedule_id: str = "sch_a") -> int:
    h.schedules.statuses = [_status("WAITING_INPUT", waiting=True)]
    before = set(h.bot._otp_prompts)
    task = asyncio.create_task(h.bot._watch(chat_id, schedule_id, 20))
    while set(h.bot._otp_prompts) == before:
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return next(iter(set(h.bot._otp_prompts) - before))[1]


async def test_otp_reply_is_submitted_then_deleted(harness):
    prompt_id = await _prompt_otp(harness)
    await harness.bot.handle_update(
        _message(" 123456 ", reply_to_message={"message_id": prompt_id})
    )
    assert harness.schedules.otp_calls == [("sch_a", "123456")]
    assert harness.telegram.of("deleteMessage")[-1]["message_id"] == 10
    assert "123456" not in json.dumps(harness.telegram.of("sendMessage"))


async def test_otp_prompt_of_another_chat_is_not_matched(harness):
    prompt_id = await _prompt_otp(harness, chat_id=BOB, schedule_id="sch_b")
    await harness.bot.handle_update(_message("123456", reply_to_message={"message_id": prompt_id}))
    assert harness.schedules.otp_calls == []


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
        _FakeUsers(),
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
            # date 가 없어 처리 중 예외가 나는 연결 사용자 메시지
            chat = {"id": ALICE, "type": "private"}
            bad = {"update_id": 7, "message": {"chat": chat, "from": {"id": ALICE}}}
            return httpx.Response(200, json={"ok": True, "result": [bad]})
        raise asyncio.CancelledError  # 앱 종료와 같은 경로로 루프를 끝낸다

    bot = TelegramBot(
        TOKEN,
        _FakeUsers(),
        _FakeSchedules(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(asyncio.CancelledError):
        await bot.run_forever()
    assert offsets == [None, None, 8]


# --- 설정 ---------------------------------------------------------------- #
@pytest.mark.parametrize("token", [None, SecretStr("  ")])
def test_bot_stays_off_without_token(token):
    settings = SimpleNamespace(telegram_bot_token=token)
    assert build_telegram_bot(settings, _FakeSchedules(), _FakeUsers()) is None


def test_bot_is_built_with_token():
    settings = SimpleNamespace(telegram_bot_token=SecretStr(TOKEN))
    assert isinstance(build_telegram_bot(settings, _FakeSchedules(), _FakeUsers()), TelegramBot)
