"""완료 이메일 HTML 본문의 모듈별 결과 표 — 자동 복구 배지 렌더링 테스트.

메일은 multipart/alternative 로 발송되고 HTML 파트가 plain 텍스트 뒤에 붙는다
(`run_completion_email.py::_build_email_message`). 거의 모든 실제 메일 클라이언트는 이
경우 마지막 파트(HTML)를 렌더링하므로, 복구 표식이 plain 텍스트 본문에만 있으면
실제 수신자 눈에는 보이지 않는다. 이 테스트는 HTML 렌더링 경로(`_module_table` /
`render_run_report_html`)를 직접 검증한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums import ModuleStatus, RunStatus
from app.core.run_models import Run, RunModule
from app.notifications.report_renderer import _module_table, render_run_report_html
from app.notifications.run_completion_email import (
    EmailContentSelection,
    GeminiPromptSelection,
    _build_email_context,
)


def _module_row(*, recovered: bool) -> dict:
    return {
        "seq": 1,
        "module_id": "m1",
        "module_name": "로그인",
        "status": ModuleStatus.PASSED.value,
        "status_label": "정상",
        "duration_text": "3초",
        "message": "완료",
        "retry_count": 2 if recovered else 0,
        "recovered": recovered,
    }


def test_module_table_shows_recovered_badge_for_recovered_module() -> None:
    html = _module_table([_module_row(recovered=True)])
    assert "자동 복구됨" in html
    assert "2회 재시도" in html


def test_module_table_omits_recovered_badge_for_clean_module() -> None:
    html = _module_table([_module_row(recovered=False)])
    assert "자동 복구됨" not in html


def _run_with_recovered_module() -> Run:
    return Run(
        run_id="run_html_recovered",
        system_code="hom",
        system_name="대표홈페이지(PC)",
        status=RunStatus.PASSED,
        requested_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        modules=[
            RunModule(
                module_id="hom.login",
                name="로그인",
                group="인증",
                order=0,
                status=ModuleStatus.PASSED,
                retry_count=2,
                recovered=True,
            )
        ],
        selected_module_ids=["hom.login"],
    )


def test_run_report_html_end_to_end_includes_recovered_badge() -> None:
    """실제 완료 이메일 HTML 본문(render_run_report_html)에도 복구 배지가 떠야 한다."""
    run = _run_with_recovered_module()
    empty_selection = EmailContentSelection(inline_screenshots=[], log_attachments=[], omitted=[])
    empty_gemini = GeminiPromptSelection(parts=[], omitted=[], included_labels=[])
    context = _build_email_context(run, empty_selection, empty_gemini)

    html = render_run_report_html(context, ai_content=None)

    assert "자동 복구됨" in html
