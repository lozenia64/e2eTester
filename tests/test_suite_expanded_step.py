"""자동 펼침 규칙 — 어느 스텝을 펼칠지는 수트 상태의 순수 함수다(설계 D4·D8).

클라이언트가 같은 규칙을 다시 구현하면 서버 렌더와 WS 갱신이 두 벌이 되어
어긋난다. 규칙은 여기 하나뿐이다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.contexts.suite.views.view import SuiteView, compute_expanded_step_order
from app.core.enums import SuiteStatus
from app.core.suite_models import SuiteRun, SuiteStep


def _steps(*specs: tuple[str, SuiteStatus, str | None]) -> list[SuiteStep]:
    return [
        SuiteStep(
            system_code=code,
            system_name=code.upper(),
            order=index,
            run_id=run_id,
            status=status,
            module_total=3,
        )
        for index, (code, status, run_id) in enumerate(specs)
    ]


def test_running_expands_current_step() -> None:
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.RUNNING, "r2"),
        ("fp", SuiteStatus.PENDING, None),
    )
    assert compute_expanded_step_order(SuiteStatus.RUNNING, steps, 1, None) == 1


def test_waiting_input_wins_over_current_index() -> None:
    """입력 대기가 현재 인덱스와 어긋나도 사람이 볼 곳은 대기 중인 스텝이다."""
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.WAITING_INPUT, "r2"),
        ("fp", SuiteStatus.PENDING, None),
    )
    assert compute_expanded_step_order(SuiteStatus.WAITING_INPUT, steps, 2, "r2") == 1


def test_terminal_expands_first_error() -> None:
    steps = _steps(
        ("hom", SuiteStatus.ANOMALY, "r1"),
        ("mhm", SuiteStatus.ERROR, "r2"),
        ("fp", SuiteStatus.ERROR, "r3"),
    )
    assert compute_expanded_step_order(SuiteStatus.ERROR, steps, 2, None) == 1


def test_terminal_falls_back_to_first_anomaly() -> None:
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.ANOMALY, "r2"),
        ("fp", SuiteStatus.PASSED, "r3"),
    )
    assert compute_expanded_step_order(SuiteStatus.ANOMALY, steps, 2, None) == 1


def test_all_passed_expands_nothing() -> None:
    """전부 정상이면 6줄이 그대로 결과 목록이 된다."""
    steps = _steps(
        ("hom", SuiteStatus.PASSED, "r1"),
        ("mhm", SuiteStatus.PASSED, "r2"),
    )
    assert compute_expanded_step_order(SuiteStatus.PASSED, steps, 1, None) is None


def test_empty_steps_returns_none() -> None:
    assert compute_expanded_step_order(SuiteStatus.PENDING, [], 0, None) is None


def test_current_index_out_of_range_returns_none() -> None:
    """인덱스가 스텝 수를 넘어도 예외를 던지지 않는다."""
    steps = _steps(("hom", SuiteStatus.PASSED, "r1"))
    assert compute_expanded_step_order(SuiteStatus.RUNNING, steps, 9, None) is None


def _suite() -> SuiteRun:
    return SuiteRun(
        suite_id="suite_test",
        status=SuiteStatus.RUNNING,
        steps=_steps(
            ("hom", SuiteStatus.PASSED, "r1"),
            ("mhm", SuiteStatus.RUNNING, "r2"),
        ),
        current_step_index=1,
        requested_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
        selected_system_codes=["hom", "mhm"],
    )


def test_dump_carries_the_field() -> None:
    payload = SuiteView.dump(_suite())
    assert payload["expanded_step_order"] == 1


def test_dump_from_summary_carries_the_field() -> None:
    """실시간 프로젝터 경로. 여기가 빠지면 소켓 이벤트마다 펼침이 사라진다."""
    suite = _suite()
    summary = SuiteView.dump(suite)
    payload = SuiteView.dump_from_summary(suite.suite_id, summary)
    assert payload["expanded_step_order"] == 1
