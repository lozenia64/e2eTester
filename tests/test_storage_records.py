"""영속 DTO(``app/storage/records.py``) 매퍼의 순수 단위 테스트.

영속 스키마 ↔ 도메인 엔티티 분리가 실제로 성립하는지 검증한다:
- 도메인 → 레코드 → 도메인 라운드트립이 상태를 보존한다.
- **모듈 로그는 영속 스키마에 담길 수 없다**(타입 수준 사실) — 라운드트립 후 로그가 비워진다.
- 와이어 JSON 형태가 종전(도메인 model_dump_json − logs)과 동일해 기존 DB 와 호환된다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.contexts.run.contracts.records import RunModuleRecord, RunRecord
from app.contexts.suite.contracts.records import SuiteRecord
from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.run_models import FailureAnalysis, Run, RunComparison, RunModule
from app.core.suite_models import SuiteRun, SuiteStep


def _run() -> Run:
    return Run(
        run_id="run_1",
        system_code="hom",
        system_name="HOM",
        status=RunStatus.PASSED,
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        started_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 0, 0, 9, tzinfo=UTC),
        modules=[
            RunModule(
                module_id="m1",
                name="모듈1",
                group="g",
                order=0,
                status=ModuleStatus.PASSED,
                message="완료",
                artifacts=["a.png"],
                artifact_count=1,
                current_url="https://example.com",
                dialog_messages=["확인"],
                logs=["line-1", "line-2", "line-3"],
                failure_analysis=FailureAnalysis(
                    category="c",
                    probable_cause="p",
                    retryable=True,
                    user_summary="u",
                    developer_details="d",
                    recommended_action="r",
                ),
            )
        ],
        selected_module_ids=["m1"],
        comparison=RunComparison(has_baseline=True, baseline_run_id="run_0"),
        created_by_user_id="u1",
        created_by_user_name="홍길동",
    )


# --- 로그가 영속 스키마에서 구조적으로 제외됨 -------------------------------


def test_run_module_record_has_no_logs_field():
    # 타입 수준 사실: 영속 스키마에 logs 가 아예 없다.
    assert "logs" not in RunModuleRecord.model_fields


def test_run_round_trip_drops_logs_but_keeps_everything_else():
    original = _run()
    restored = RunRecord.from_domain(original).to_domain()

    # 로그만 비워지고(별도 스토어 소유),
    assert restored.modules[0].logs == []
    # 나머지 도메인 상태는 보존된다.
    assert restored.run_id == original.run_id
    assert restored.status == original.status
    assert restored.modules[0].status == ModuleStatus.PASSED
    assert restored.modules[0].artifacts == ["a.png"]
    assert restored.modules[0].current_url == "https://example.com"
    assert restored.modules[0].dialog_messages == ["확인"]
    assert restored.modules[0].failure_analysis is not None
    assert restored.modules[0].failure_analysis.category == "c"
    assert restored.comparison is not None and restored.comparison.baseline_run_id == "run_0"
    assert restored.created_by_user_name == "홍길동"


def test_run_serialize_blob_excludes_logs_and_is_db_compatible():
    blob = RunRecord.serialize(_run())
    parsed = json.loads(blob)
    # 디스크 JSON 에 logs 키가 없다(기존 어댑터의 exclude 결과와 동일 형태).
    assert "logs" not in parsed["modules"][0]
    # 역직렬화로 도메인 복원 가능.
    restored = RunRecord.deserialize(blob)
    assert restored.run_id == "run_1"
    assert restored.modules[0].logs == []


def test_run_record_deserializes_legacy_blob_with_logs_present():
    # 과거 형태(logs 포함)도 읽을 수 있어야 한다(extra 필드 무시 → 호환).
    legacy = _run().model_dump_json()  # logs 포함된 옛 직렬화
    restored = RunRecord.deserialize(legacy)
    assert restored.modules[0].logs == []
    assert restored.modules[0].message == "완료"


# --- Suite 영속 라운드트립 ---------------------------------------------------


def _suite() -> SuiteRun:
    return SuiteRun(
        suite_id="suite_1",
        status=SuiteStatus.PASSED,
        steps=[
            SuiteStep(
                system_code="hom",
                system_name="HOM",
                order=0,
                run_id="run_1",
                status=SuiteStatus.PASSED,
                module_total=8,
            ),
            SuiteStep(system_code="mhm", system_name="MHM", order=1, status=SuiteStatus.SKIPPED),
        ],
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        browser_mode="headed",
        selected_system_codes=["hom"],
        created_by_user_name="홍길동",
    )


def test_suite_round_trip_preserves_state():
    original = _suite()
    restored = SuiteRecord.from_domain(original).to_domain()
    assert restored.suite_id == original.suite_id
    assert restored.status == SuiteStatus.PASSED
    assert [s.status for s in restored.steps] == [SuiteStatus.PASSED, SuiteStatus.SKIPPED]
    assert restored.steps[0].run_id == "run_1"
    assert restored.steps[0].module_total == 8
    assert restored.selected_system_codes == ["hom"]
    assert restored.created_by_user_name == "홍길동"


def test_suite_serialize_round_trip_via_blob():
    restored = SuiteRecord.deserialize(SuiteRecord.serialize(_suite()))
    assert restored.suite_id == "suite_1"
    assert restored.steps[1].system_code == "mhm"
