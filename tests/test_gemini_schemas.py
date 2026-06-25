from __future__ import annotations

from app.ai.gemini_schemas import (
    FailureDetail,
    ModuleFinding,
    RunReportContent,
    SuiteReportContent,
    SuiteSystemContent,
    clean_narrative_text,
)


def test_clean_narrative_text_strips_json_bleed() -> None:
    raw = '요약 문장입니다.","module_findings":[{"module_id":"login"}]'
    assert clean_narrative_text(raw) == "요약 문장입니다."


def test_clean_narrative_text_rejects_embedded_json_object() -> None:
    raw = '{"module_id":"login","screen_observation":"팝업"}'
    assert clean_narrative_text(raw) == ""


def test_run_report_content_validates_and_exports_wire_dict() -> None:
    content = RunReportContent(
        headline="로그인 모듈에서 실패했습니다.",
        comparison_comment="",
        module_findings=[
            ModuleFinding(
                module_id="login",
                screen_observation="오류 팝업이 표시되었습니다.",
                log_observation="타임아웃 로그가 확인되었습니다.",
            )
        ],
        failure_details=[
            FailureDetail(
                module_id="login",
                symptom="로그인 실패",
                evidence="타임아웃",
                probable_cause="네트워크 지연",
                recommended_action="재실행",
            )
        ],
    )
    wire = content.to_wire_dict()
    assert wire["headline"] == "로그인 모듈에서 실패했습니다."
    assert wire["module_findings"][0]["module_id"] == "login"


def test_suite_report_content_normalizes_system_code() -> None:
    content = SuiteReportContent(
        headline="2개 시스템 중 1개 실패",
        systems=[
            SuiteSystemContent(
                system_code="hom",
                summary="대표홈페이지 점검 완료",
            )
        ],
    )
    assert content.systems[0].system_code == "HOM"
    assert content.to_wire_dict()["systems"][0]["system_code"] == "HOM"
