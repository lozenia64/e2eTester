"""이름 붙은 상태 목록 — 필터·범례가 라벨을 다시 적지 않게 한다.

admin/runs.html 은 같은 4개 항목을 한 파일 안에서 두 번 적고 있었다
(체크박스 팝오버 + 숨은 select). SSOT 와의 중복 이전에 자기들끼리 중복이었다.
"""

from __future__ import annotations

import pytest

from app.core.enums import RunStatus
from app.core.status_labels import run_status_label
from app.core.status_view import status_options


def test_admin_runs_filter_covers_the_four_terminal_states() -> None:
    values = [option.value for option in status_options("admin_runs")]
    assert values == [
        RunStatus.PASSED.value,
        RunStatus.ANOMALY.value,
        RunStatus.ERROR.value,
        RunStatus.CANCELLED.value,
    ]


def test_labels_come_from_the_ssot() -> None:
    for option in status_options("admin_runs"):
        assert option.label == run_status_label(RunStatus(option.value))


def test_schedule_legend_omits_cancelled() -> None:
    """예약 캘린더는 취소를 칠하지 않는다 — 목록이 화면마다 다르다는 사실을 고정한다."""
    values = [option.value for option in status_options("schedule_legend")]
    assert RunStatus.CANCELLED.value not in values
    assert values == [
        RunStatus.PASSED.value,
        RunStatus.ANOMALY.value,
        RunStatus.ERROR.value,
    ]


def test_unknown_name_raises_with_the_valid_names() -> None:
    """오타가 조용히 빈 목록이 되면 필터가 통째로 사라진다."""
    with pytest.raises(KeyError, match="admin_runs"):
        status_options("no_such_list")
