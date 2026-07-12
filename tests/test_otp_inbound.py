"""인바운드 OTP 중계(POST /api/otp/inbound) 단위 테스트.

브라우저/HTTP 서버 없이 ① OTP 추출 헬퍼 ② 라우트 핸들러(토큰 인증·에러 매핑) ③ RunService
의 "대기 Run 자동 탐색" 선택 로직을 검증한다. 비동기 핸들러 테스트는 pytest-asyncio
(asyncio_mode="auto")가 코루틴으로 실행한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes_otp import DEFAULT_OTP_RELAY_REGEX, _extract_code, submit_inbound_otp
from app.core.enums import RunStatus
from app.core.models import InboundOtpRequest
from app.orchestrator.run_service import RunService


# --------------------------------------------------------------------------- #
# 1. OTP 추출 헬퍼
# --------------------------------------------------------------------------- #
def test_extract_code_prefers_explicit_code():
    payload = InboundOtpRequest(code="123456", text="무시되는 999999")
    assert _extract_code(payload, None) == "123456"


def test_extract_code_rejects_bad_code():
    assert _extract_code(InboundOtpRequest(code="12"), None) is None
    assert _extract_code(InboundOtpRequest(code="abcdef"), None) is None


def test_extract_code_parses_text_with_default_regex():
    payload = InboundOtpRequest(text="[한화손해보험] 인증번호는 123456 입니다.")
    assert _extract_code(payload, DEFAULT_OTP_RELAY_REGEX) == "123456"


def test_extract_code_uses_custom_regex_capture_group():
    payload = InboundOtpRequest(text="고객님 인증번호[654321] 유효시간 3분")
    assert _extract_code(payload, r"인증번호\[(\d{6})\]") == "654321"


def test_extract_code_falls_back_when_regex_invalid():
    payload = InboundOtpRequest(text="코드 246810 끝")
    # 깨진 정규식이어도 기본 정규식으로 폴백해 추출한다.
    assert _extract_code(payload, r"(\d{4,8}") == "246810"


def test_extract_code_returns_none_without_digits():
    assert _extract_code(InboundOtpRequest(text="숫자 없음"), None) is None
    assert _extract_code(InboundOtpRequest(), None) is None


# --------------------------------------------------------------------------- #
# 2. 라우트 핸들러 (토큰 인증 · 에러 매핑)
# --------------------------------------------------------------------------- #
class _FakeRunService:
    def __init__(self, *, run=None, raises: Exception | None = None) -> None:
        self._run = run
        self._raises = raises
        self.calls: list[str] = []

    async def submit_otp_to_waiting(self, code: str):
        self.calls.append(code)
        if self._raises is not None:
            raise self._raises
        return self._run


async def _call(**kwargs):
    return await submit_inbound_otp(**kwargs)


async def test_route_disabled_when_token_unset():
    with pytest.raises(HTTPException) as exc:
        await _call(
            payload=InboundOtpRequest(code="123456"),
            x_otp_relay_token="anything",
            configured_token=None,
            relay_regex=None,
            run_service=_FakeRunService(),
        )
    assert exc.value.status_code == 503


async def test_route_rejects_wrong_or_missing_token():
    for header in ("wrong-token", None):
        with pytest.raises(HTTPException) as exc:
            await _call(
                payload=InboundOtpRequest(code="123456"),
                x_otp_relay_token=header,
                configured_token="secret",
                relay_regex=None,
                run_service=_FakeRunService(),
            )
        assert exc.value.status_code == 401


async def test_route_rejects_invalid_code():
    with pytest.raises(HTTPException) as exc:
        await _call(
            payload=InboundOtpRequest(text="no digits here"),
            x_otp_relay_token="secret",
            configured_token="secret",
            relay_regex=None,
            run_service=_FakeRunService(),
        )
    assert exc.value.status_code == 400


async def test_route_submits_code_and_returns_run():
    run = SimpleNamespace(run_id="run_42", status=RunStatus.RUNNING)
    fake = _FakeRunService(run=run)
    result = await _call(
        payload=InboundOtpRequest(text="인증번호 778899"),
        x_otp_relay_token="secret",
        configured_token="secret",
        relay_regex=None,
        run_service=fake,
    )
    assert fake.calls == ["778899"]
    assert result == {"run_id": "run_42", "status": RunStatus.RUNNING.value}


async def test_route_maps_no_waiting_run_to_404():
    fake = _FakeRunService(raises=KeyError("none"))
    with pytest.raises(HTTPException) as exc:
        await _call(
            payload=InboundOtpRequest(code="123456"),
            x_otp_relay_token="secret",
            configured_token="secret",
            relay_regex=None,
            run_service=fake,
        )
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------- #
# 3. RunService.submit_otp_to_waiting — 대기 Run 자동 탐색 선택 로직
# --------------------------------------------------------------------------- #
class _FakeSummaryQuery:
    """``RunSummaryQueryPort.list_summaries`` 흉내 — 상태 필터만 지원(테스트 전용)."""

    def __init__(self, runs):
        self._runs = runs

    async def list_summaries(self, query, page):
        rows = [run for run in self._runs if query.statuses is None or run.status in query.statuses]
        return rows[: page.limit]


class _FakeControl:
    """pending_ids: set(run_id) 또는 dict(run_id → paused_at 또는 None)."""

    def __init__(self, pending_ids):
        if isinstance(pending_ids, dict):
            self._pending = dict(pending_ids)
        else:
            self._pending = dict.fromkeys(pending_ids)

    async def get_pending(self, run_id):
        if run_id not in self._pending:
            return None
        return SimpleNamespace(paused_at=self._pending[run_id])


def _run(run_id, status, minutes_ago=0):
    return SimpleNamespace(
        run_id=run_id,
        status=status,
        requested_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


def _service(runs, pending_ids, recorder):
    svc = RunService.__new__(RunService)
    svc._summary_query = _FakeSummaryQuery(runs)
    svc._control_store = _FakeControl(pending_ids)

    async def fake_submit_otp(run_id, code):
        recorder.append((run_id, code))
        return next(r for r in runs if r.run_id == run_id)

    svc.submit_otp = fake_submit_otp  # type: ignore[method-assign]
    return svc


async def test_waiting_finder_submits_single_pending_run():
    runs = [
        _run("a", RunStatus.PASSED),
        _run("b", RunStatus.WAITING_INPUT),
        _run("c", RunStatus.RUNNING),
    ]
    recorder: list = []
    svc = _service(runs, pending_ids={"b"}, recorder=recorder)
    result = await svc.submit_otp_to_waiting("123456")
    assert result.run_id == "b"
    assert recorder == [("b", "123456")]


async def test_waiting_finder_raises_when_none_waiting():
    runs = [_run("a", RunStatus.PASSED), _run("c", RunStatus.RUNNING)]
    svc = _service(runs, pending_ids=set(), recorder=[])
    with pytest.raises(KeyError):
        await svc.submit_otp_to_waiting("123456")


async def test_waiting_finder_ignores_waiting_without_pending():
    # 상태는 WAITING_INPUT 이지만 제어 스토어에 pending 이 없으면(경합) 후보에서 제외.
    runs = [_run("b", RunStatus.WAITING_INPUT)]
    svc = _service(runs, pending_ids=set(), recorder=[])
    with pytest.raises(KeyError):
        await svc.submit_otp_to_waiting("123456")


async def test_waiting_finder_picks_most_recently_paused_when_multiple():
    # 정렬 키는 OTP 대기 진입 시각(paused_at)이다 — 방금 도착한 SMS 에 대응하는 Run.
    now = datetime.now(UTC)
    runs = [
        _run("paused_earlier", RunStatus.WAITING_INPUT, minutes_ago=1),
        _run("paused_later", RunStatus.WAITING_INPUT, minutes_ago=10),
    ]
    recorder: list = []
    svc = _service(
        runs,
        pending_ids={
            "paused_earlier": now - timedelta(minutes=5),
            "paused_later": now - timedelta(minutes=1),
        },
        recorder=recorder,
    )
    # Run 생성은 paused_earlier 가 더 최근이지만, 대기 진입은 paused_later 가 더 최근 —
    # 생성 시각을 키로 쓰면 오주입되는 바로 그 사례를 고정한다.
    result = await svc.submit_otp_to_waiting("123456")
    assert result.run_id == "paused_later"
    assert recorder == [("paused_later", "123456")]


async def test_waiting_finder_falls_back_to_requested_at_for_legacy_pending():
    # paused_at 이 없는 레거시 pending 행은 Run 생성 시각으로 폴백한다.
    runs = [
        _run("old", RunStatus.WAITING_INPUT, minutes_ago=10),
        _run("new", RunStatus.WAITING_INPUT, minutes_ago=1),
    ]
    recorder: list = []
    svc = _service(runs, pending_ids={"old": None, "new": None}, recorder=recorder)
    result = await svc.submit_otp_to_waiting("123456")
    assert result.run_id == "new"
    assert recorder == [("new", "123456")]


async def test_sqlite_control_store_stamps_and_roundtrips_paused_at(tmp_path):
    from app.storage.sqlite_run_control_store import SqliteRunControlStore

    store = SqliteRunControlStore(tmp_path / "control.db")
    before = datetime.now(UTC)
    await store.set_pending(
        "run-1", session_id="s", execution_mode="m", resume_index=2, module_id="mod"
    )
    pending = await store.get_pending("run-1")
    assert pending is not None
    assert pending.paused_at is not None
    assert before <= pending.paused_at <= datetime.now(UTC)

    await store.clear_pending("run-1")
    assert await store.get_pending("run-1") is None
