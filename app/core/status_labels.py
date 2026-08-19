from __future__ import annotations

from app.core.enums import AnomalyState, ModuleStatus, RunStatus, SuiteStatus

# 레거시 FAILED 는 과거 Run/모듈 JSON 호환용. 집계·표시 시 ANOMALY 로 취급한다.
MODULE_ANOMALY_STATUSES = frozenset({ModuleStatus.ANOMALY, ModuleStatus.FAILED})
MODULE_ERROR_STATUSES = frozenset({ModuleStatus.ERROR})
RUN_ANOMALY_STATUSES = frozenset({RunStatus.ANOMALY, RunStatus.FAILED})
RUN_ERROR_STATUSES = frozenset({RunStatus.ERROR})
RUN_TERMINAL_OUTCOME_STATUSES = frozenset(
    {RunStatus.PASSED, RunStatus.ANOMALY, RunStatus.ERROR, RunStatus.FAILED}
)
# 사용량 통계에 노출할 Run (정상·이상징후; 점검실패·취소 제외)
ADMIN_VISIBLE_RUN_STATUSES = frozenset({RunStatus.PASSED, *RUN_ANOMALY_STATUSES})
# 관리자 대시보드 Run 목록·삭제 관리 대상 (종료 결과 전체 + 취소)
ADMIN_DASHBOARD_RUN_STATUSES = frozenset({*RUN_TERMINAL_OUTCOME_STATUSES, RunStatus.CANCELLED})
# 일일 보존 정리 배치에서 삭제할 Run (점검실패·취소; 정상·이상징후는 유지)
RUN_DAILY_PURGE_STATUSES = frozenset({RunStatus.ERROR, RunStatus.CANCELLED})
SUITE_ANOMALY_STATUSES = frozenset({SuiteStatus.ANOMALY, SuiteStatus.FAILED})
SUITE_ERROR_STATUSES = frozenset({SuiteStatus.ERROR})
SUITE_TERMINAL_OUTCOME_STATUSES = frozenset(
    {SuiteStatus.PASSED, SuiteStatus.ANOMALY, SuiteStatus.ERROR, SuiteStatus.FAILED}
)

RUN_STATUS_LABELS: dict[RunStatus, str] = {
    RunStatus.PENDING: "대기",
    RunStatus.RUNNING: "실행 중",
    RunStatus.WAITING_INPUT: "입력 대기",
    RunStatus.PASSED: "정상",
    RunStatus.ANOMALY: "이상징후",
    RunStatus.ERROR: "점검실패",
    RunStatus.FAILED: "이상징후",
    RunStatus.CANCELLED: "취소",
}

MODULE_STATUS_LABELS: dict[ModuleStatus, str] = {
    ModuleStatus.PENDING: "대기",
    ModuleStatus.QUEUED: "대기",
    ModuleStatus.RUNNING: "실행 중",
    ModuleStatus.WAITING_INPUT: "입력 대기",
    ModuleStatus.PASSED: "정상",
    ModuleStatus.ANOMALY: "이상징후",
    ModuleStatus.ERROR: "점검실패",
    ModuleStatus.FAILED: "이상징후",
    ModuleStatus.BLOCKED: "차단",
    ModuleStatus.SKIPPED: "제외",
    ModuleStatus.CANCELLED: "취소",
}

SUITE_STATUS_LABELS: dict[SuiteStatus, str] = {
    SuiteStatus.PENDING: "대기",
    SuiteStatus.RUNNING: "실행 중",
    SuiteStatus.WAITING_INPUT: "입력 대기",
    SuiteStatus.PASSED: "정상",
    SuiteStatus.ANOMALY: "이상징후",
    SuiteStatus.ERROR: "점검실패",
    SuiteStatus.FAILED: "이상징후",
    SuiteStatus.SKIPPED: "제외",
    SuiteStatus.CANCELLED: "취소",
}


ANOMALY_STATE_LABELS: dict[AnomalyState, str] = {
    AnomalyState.UNRESOLVED: "미확인",
    AnomalyState.ACKNOWLEDGED: "확인함",
    AnomalyState.RESOLVED: "처리완료",
}


def run_status_label(status: RunStatus) -> str:
    return RUN_STATUS_LABELS.get(status, str(status))


def anomaly_state_label(state: AnomalyState) -> str:
    return ANOMALY_STATE_LABELS.get(state, str(state))


def module_status_label(status: ModuleStatus) -> str:
    return MODULE_STATUS_LABELS.get(status, str(status))


def suite_status_label(status: SuiteStatus) -> str:
    return SUITE_STATUS_LABELS.get(status, str(status))


# 배지·점·막대의 색 축(SSOT). 프론트 토큰(tokens.generated.css)과
# TS union(status.generated.ts)이 이 튜플에서 생성된다.
# 순서는 생성물의 출력 순서이므로 임의로 바꾸지 않는다.
STATUS_TONES: tuple[str, ...] = (
    "passed",
    "anomaly",
    "error",
    "running",
    "waiting_input",
    "blocked",
    "skipped",
    "cancelled",
    "pending",
)


def run_status_badge_tone(status: RunStatus) -> str:
    if status == RunStatus.PASSED:
        return "passed"
    if status in RUN_ERROR_STATUSES:
        return "error"
    if status in RUN_ANOMALY_STATUSES:
        return "anomaly"
    if status == RunStatus.RUNNING:
        return "running"
    if status == RunStatus.WAITING_INPUT:
        return "waiting_input"
    if status == RunStatus.CANCELLED:
        return "cancelled"
    return "pending"


def module_status_badge_tone(status: ModuleStatus) -> str:
    if status == ModuleStatus.PASSED:
        return "passed"
    if status in MODULE_ERROR_STATUSES:
        return "error"
    if status in MODULE_ANOMALY_STATUSES:
        return "anomaly"
    if status == ModuleStatus.RUNNING:
        return "running"
    if status == ModuleStatus.WAITING_INPUT:
        return "waiting_input"
    if status == ModuleStatus.BLOCKED:
        return "blocked"
    if status == ModuleStatus.SKIPPED:
        return "skipped"
    if status == ModuleStatus.CANCELLED:
        return "cancelled"
    return "pending"
