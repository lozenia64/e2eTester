"""인사이트 순수 집계 빌더 단위 테스트(브라우저·DB 없이 규칙만 검증)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.enums import AnomalyState, ModuleStatus, RunStatus
from app.core.run_models import AnomalyHandling, FailureAnalysis
from app.core.system_models import ModuleDefinition, SystemDefinition
from app.orchestrator.insights_anomalies import build_anomaly_items
from app.orchestrator.insights_breakdown import build_module_breakdown
from app.orchestrator.insights_common import (
    ModuleHistoryView,
    RunComparisonView,
    RunHistoryView,
)
from app.orchestrator.insights_health import build_system_health
from app.orchestrator.insights_timeline import build_system_timeline

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 7, 9, 3, 0, tzinfo=UTC)

_FA = FailureAnalysis(
    category="셀렉터 불일치",
    probable_cause="c",
    retryable=False,
    user_summary="로그인 버튼을 못 찾음",
    developer_details="d",
    recommended_action="셀렉터 수정",
)


def _mod(mid, order, status, dur, *, depends=None, analysis=None, arts=None, ts=NOW):
    del order, depends  # 뷰는 실행 이력 행이라 정의 순서/의존성을 갖지 않는다.
    return ModuleHistoryView(
        module_id=mid,
        name=mid.upper(),
        status=status,
        message="",
        duration_ms=dur,
        current_url=None,
        artifacts=tuple(arts or []),
        started_at=ts,
        ended_at=ts,
        ai_category=analysis.category if analysis else None,
        ai_summary=analysis.user_summary if analysis else None,
        ai_action=analysis.recommended_action if analysis else None,
    )


def _system():
    return SystemDefinition(
        system_code="hom",
        name="대표홈(PC)",
        description="d",
        modules=[
            ModuleDefinition(
                module_id="access",
                system_code="hom",
                name="접속",
                description="d",
                group="g",
                order=1,
            ),
            ModuleDefinition(
                module_id="login",
                system_code="hom",
                name="로그인",
                description="d",
                group="g",
                order=2,
                depends_on=["access"],
            ),
            ModuleDefinition(
                module_id="claim",
                system_code="hom",
                name="보상청구",
                description="d",
                group="g",
                order=3,
                depends_on=["login"],
            ),
        ],
    )


def _runs():
    runs = []
    for i in range(8):
        ts = NOW - timedelta(days=i)
        login_status = ModuleStatus.PASSED if i % 3 else ModuleStatus.ANOMALY
        claim_status = ModuleStatus.ERROR if i == 0 else ModuleStatus.PASSED
        run_status = (
            RunStatus.ERROR if i == 0 else (RunStatus.PASSED if i % 3 else RunStatus.ANOMALY)
        )
        modules = [
            _mod("access", 1, ModuleStatus.PASSED, 1200, ts=ts),
            _mod(
                "login",
                2,
                login_status,
                3400,
                depends=["access"],
                analysis=None if i % 3 else _FA,
                arts=[f"/artifacts/r{i}/login/final.png"],
                ts=ts,
            ),
            _mod(
                "claim",
                3,
                claim_status,
                5600,
                depends=["login"],
                analysis=_FA if i == 0 else None,
                arts=[f"/artifacts/r{i}/claim/final.png"],
                ts=ts,
            ),
        ]
        comp = RunComparisonView(
            newly_failed=("login",) if i == 2 else (),
            recovered=("login",) if i == 1 else (),
            still_failing=(),
        )
        runs.append(
            RunHistoryView(
                run_id=f"r{i}",
                system_code="hom",
                system_name="대표홈(PC)",
                status=run_status,
                requested_at=ts,
                started_at=ts,
                ended_at=ts,
                triggered_by="schedule" if i % 2 else "manual",
                suite_id=None,
                schedule_id=None,
                created_by_user_id=None,
                created_by_user_name="홍길동",
                modules=tuple(modules),
                comparison=comp,
            )
        )
    return runs


# ── 이상징후 인박스 ──────────────────────────────────────────────────────────
def test_anomaly_items_counts_and_join():
    handlings = {
        "r0::claim": AnomalyHandling(
            module_run_id="r0::claim",
            state=AnomalyState.ACKNOWLEDGED,
            assignee_name="김담당",
            memo="조사중",
        )
    }
    out = build_anomaly_items([_system()], _runs(), handlings)
    # login 이상(i=0,3,6 → 3건) + claim 에러(i=0 → 1건) = 4건
    assert out["counts"]["total"] == 4
    assert out["counts"]["error"] == 1
    assert out["counts"]["anomaly"] == 3
    # 처리 레코드 조인 확인
    claim = next(it for it in out["items"] if it["module_run_id"] == "r0::claim")
    assert claim["handling"]["state"] == AnomalyState.ACKNOWLEDGED
    assert claim["handling"]["assignee_name"] == "김담당"
    assert claim["ai_summary"] == "로그인 버튼을 못 찾음"
    assert claim["screenshot"] == "/artifacts/r0/claim/final.png"
    # 최신순 정렬
    times = [it["occurred_at"] for it in out["items"]]
    assert times == sorted(times, reverse=True)


def test_anomaly_items_allowed_filter():
    out = build_anomaly_items([_system()], _runs(), {}, allowed_system_codes=["other"])
    assert out["counts"]["total"] == 0


# ── 헬스 ─────────────────────────────────────────────────────────────────────
def test_system_health_shape():
    h = build_system_health(_system(), _runs(), days=30, now=NOW, tz=KST)
    assert len(h["daily"]) == 30
    assert 0 <= h["header"]["score"] <= 100
    assert len(h["stability"]) == 3
    login = next(r for r in h["stability"] if r["module_id"] == "login")
    assert login["flaky_score"] > 0  # 이상/정상 뒤집힘


# ── 타임라인 ─────────────────────────────────────────────────────────────────
def test_system_timeline_regression_marker():
    t = build_system_timeline(_system(), _runs(), limit=50)
    assert len(t["cards"]) == 8
    card2 = next(c for c in t["cards"] if c["run_id"] == "r2")
    assert [m["module_id"] for m in card2["regression_modules"]] == ["login"]
    card1 = next(c for c in t["cards"] if c["run_id"] == "r1")
    assert [m["module_id"] for m in card1["recovered"]] == ["login"]


# ── 모듈 딥다이브 ────────────────────────────────────────────────────────────
def test_module_breakdown_flaky_and_no_false_bottleneck():
    b = build_module_breakdown(_system(), _runs())
    assert len(b["modules"]) == 3
    login = next(m for m in b["modules"] if m["module_id"] == "login")
    assert login["is_flaky"] is True
    claim = next(m for m in b["modules"] if m["module_id"] == "claim")
    assert claim["duration_series"]  # 시계열 존재
    # 절대 소요가 가장 길어도(스텝이 많을 뿐) '느려짐'으로 오인하지 않는다 —
    # 소요가 일정하면 어떤 모듈도 느려짐으로 잡히지 않는다.
    assert all(not m["is_slowing"] for m in b["modules"])
    assert b["summary"]["slowing_module_id"] is None


def test_module_breakdown_slowdown_detection():
    # 'login' 모듈이 시간이 갈수록 느려지면(자기 과거 대비) '느려짐'으로 잡힌다.
    runs = []
    for i in range(6):
        ts = NOW - timedelta(days=5 - i)  # 오래된 것 → 최근 순
        login_dur = 2000 + i * 700  # 2000ms → 5500ms 점증
        runs.append(
            RunHistoryView(
                run_id=f"s{i}",
                system_code="hom",
                system_name="대표홈(PC)",
                status=RunStatus.PASSED,
                requested_at=ts,
                started_at=ts,
                ended_at=ts,
                triggered_by="manual",
                suite_id=None,
                schedule_id=None,
                created_by_user_id=None,
                created_by_user_name=None,
                modules=(
                    _mod("access", 1, ModuleStatus.PASSED, 1000, ts=ts),
                    _mod("login", 2, ModuleStatus.PASSED, login_dur, depends=["access"], ts=ts),
                    _mod("claim", 3, ModuleStatus.PASSED, 3000, depends=["login"], ts=ts),
                ),
                comparison=None,
            )
        )
    b = build_module_breakdown(_system(), runs)
    login = next(m for m in b["modules"] if m["module_id"] == "login")
    assert login["is_slowing"] is True
    assert login["slowdown_pct"] > 20
    assert b["summary"]["slowing_module_id"] == "login"
    # 소요가 일정한 claim 은 느려짐이 아니다.
    assert next(m for m in b["modules"] if m["module_id"] == "claim")["is_slowing"] is False
