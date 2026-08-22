"""일간 리포트 내용 조립 — 요약 dict → 메일에 넣을 구조.

I/O 없음. ``DailyReportEmailService`` 가 ``get_daily_summary(date_label=어제)`` 결과를
넘겨 호출한다(``build_daily_summary``·``build_wall_view`` 와 같은 순수 빌더 패턴).

제목 규칙이 상황판(P3-2)과 다른 이유: 발송 시각(다음 날 아침)에는 어제의 OTP 대기가
이미 끝났거나 무의미하다. 하루가 닫힌 뒤의 결론만 담는다.

한국어 상태 라벨을 하드코딩하지 않는다 — status_labels.py 가 유일한 출처다.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import ModuleStatus
from app.core.status_labels import module_status_label

# 점검이 하루 종일 한 번도 돌지 않은 상태. 어느 enum 에도 대응하지 않는
# 리포트 전용 문구라 여기서 정의한다(상태 라벨 복제가 아니다).
NOT_INSPECTED_HEADLINE = "점검 미실행"

# 시스템 블록의 최악 버킷 우선순위. daily_dashboard 의 버킷 이름을 쓴다.
_WORST_BUCKETS: tuple[tuple[str, ModuleStatus], ...] = (
    ("error", ModuleStatus.ERROR),
    ("anomaly", ModuleStatus.ANOMALY),
    ("running", ModuleStatus.RUNNING),
    ("other", ModuleStatus.BLOCKED),
    ("not_inspected", ModuleStatus.PENDING),
)


def _count(totals: dict[str, Any], key: str) -> int:
    return int(totals.get(key, 0) or 0)


def _headline(totals: dict[str, Any]) -> tuple[str, str]:
    """(제목, 상태값). 라벨은 status_labels.py 에서 가져온다."""
    error = _count(totals, "error")
    if error > 0:
        return f"{module_status_label(ModuleStatus.ERROR)} {error}건", ModuleStatus.ERROR.value
    anomaly = _count(totals, "anomaly")
    if anomaly > 0:
        return (
            f"{module_status_label(ModuleStatus.ANOMALY)} {anomaly}건",
            ModuleStatus.ANOMALY.value,
        )
    modules = _count(totals, "modules")
    if modules > 0 and _count(totals, "not_inspected") == modules:
        return NOT_INSPECTED_HEADLINE, ModuleStatus.PENDING.value
    return module_status_label(ModuleStatus.PASSED), ModuleStatus.PASSED.value


def _system_status(counts: dict[str, Any]) -> ModuleStatus:
    for bucket, status in _WORST_BUCKETS:
        if int(counts.get(bucket, 0) or 0) > 0:
            return status
    return ModuleStatus.PASSED


def build_daily_report(summary: dict[str, Any], *, date_label: str) -> dict[str, Any]:
    """일간 요약 → 리포트 메일 컨텍스트."""
    totals = summary.get("totals", {})
    headline, status_value = _headline(totals)

    systems: list[dict[str, Any]] = []
    for system in summary.get("systems", []):
        counts = system.get("counts", {})
        status = _system_status(counts)
        systems.append(
            {
                "code": system["system_code"],
                "name": system["system_name"],
                "passed": int(counts.get("passed", 0) or 0),
                "total": int(system.get("module_total", 0) or 0),
                "status_value": status.value,
                "status_label": module_status_label(status),
            }
        )

    issues = [
        {
            "system": item.get("system_name") or item.get("system_code") or "",
            "module": item.get("module_name") or "",
            "status_label": item.get("status_label") or "",
        }
        for item in summary.get("attention", [])
    ]

    return {
        "date_label": date_label,
        "headline": headline,
        "status_value": status_value,
        "kpis": [
            (card["label"], str(card["value"]), card.get("unit", ""))
            for card in summary.get("cards", [])
        ],
        "systems": systems,
        "issues": issues,
    }
