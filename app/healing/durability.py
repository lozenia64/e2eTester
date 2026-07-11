"""셀렉터 내구성 맵 — steps 소스 정적 스캔 + 치유 이력 결합(순수 빌더).

깨지기 *전에* 어느 셀렉터가 약한지 답한다: 소스에서 하드코딩 셀렉터를 추출해
안정(#id·name·role 기반) / 주의(class 기반) / 취약(텍스트 매칭·인덱스 의존·xpath)으로
점수화하고, 치유 이력(같은 셀렉터가 몇 번 깨졌나)을 결합해 만성 취약 Top N 을 만든다.

파일 I/O 없음 — 입력은 {상대경로: 소스 텍스트} 매핑이며 파일 읽기는 서비스가 담당한다.
"""

from __future__ import annotations

import re
from typing import Any

from app.healing.metrics import heal_counts_by_selector
from app.healing.models import CHRONIC_HEAL_THRESHOLD, HealingEvent

# 셀렉터를 첫 인자로 받는 호출들에서 인라인 셀렉터 문자열을 뽑는다.
_INLINE_CALL_RE = re.compile(
    r"\.(?:locator|frame_locator|wait_for_selector|query_selector(?:_all)?)\(\s*([\"'])(.+?)\1"
)
# 모듈 상단 셀렉터 상수(대문자 상수 = 문자열 리터럴).
_CONSTANT_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*([\"'])(.+?)\2\s*$")
# get_by_role/label 사용(접근성 기반 — 안정 등급으로 집계).
_GET_BY_ROLE_RE = re.compile(r"get_by_role\(\s*[\"']([a-z]+)[\"'](?:\s*,\s*name=([\"'])(.+?)\2)?")
# 셀렉터로 보이는 문자열인지(경로·메시지 등 오탐 제거).
_SELECTOR_SHAPE_RE = re.compile(
    r"^[#.\[/]|^[a-z][a-z0-9]*[\[.#:]|:has-text|>>|^text=|^xpath=|iframe"
)

_AUTO_ID_DIGITS_RE = re.compile(r"\d{3,}")


def looks_like_selector(value: str) -> bool:
    return bool(_SELECTOR_SHAPE_RE.search(value.strip()))


def classify_selector(selector: str) -> tuple[int, str, list[str]]:
    """셀렉터 1개의 (안정성 점수 0~100, 등급 green/amber/red, 사유 노트)를 매긴다."""
    sel = selector.strip()
    notes: list[str] = []

    if sel.startswith("role="):
        return 85, "green", ["접근성 role 기반 — 안정"]

    if sel.startswith("//") or sel.startswith("xpath="):
        score = 35
        notes.append("xpath 경로 의존 — DOM 구조 변경에 취약")
    elif sel.startswith("#") and " " not in sel and ">>" not in sel:
        score = 90
        notes.append("#id 기반 — 안정")
        if _AUTO_ID_DIGITS_RE.search(sel):
            score = 68
            notes.append("숫자 포함 id — 자동 생성 id 의심")
    elif "[name=" in sel or "[id^=" in sel or "[aria-label=" in sel:
        score = 80
        notes.append("속성(name/aria/id-prefix) 기반 — 비교적 안정")
    elif re.match(r"^[a-z][a-z0-9]*\.[-\w]+", sel) or sel.startswith("."):
        score = 60
        notes.append("class 기반 — 스타일 리팩터링에 흔들림")
    else:
        score = 55
        notes.append("복합/기타 패턴")

    if ":has-text(" in sel or sel.startswith("text="):
        score = min(score, 45)
        notes.append("텍스트 매칭 — 문구 변경에 취약")
    if "nth(" in sel or "nth-child" in sel or ">> nth=" in sel:
        score = min(score, 40)
        notes.append("인덱스 의존 — 순서 변경에 취약")
    if len(sel) > 80:
        score = max(score - 15, 5)
        notes.append("긴 셀렉터 — 다단 결합 취약")

    grade = "green" if score >= 80 else ("amber" if score >= 55 else "red")
    return score, grade, notes


def extract_selector_refs(path: str, source: str) -> list[dict[str, Any]]:
    """소스 1파일에서 (셀렉터, 라인, 종류) 목록을 뽑는다."""
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for line_no, line in enumerate(source.splitlines(), start=1):
        constant = _CONSTANT_RE.match(line)
        if constant and looks_like_selector(constant.group(3)):
            key = (constant.group(3), line_no)
            if key not in seen:
                seen.add(key)
                refs.append(
                    {
                        "file": path,
                        "line": line_no,
                        "selector": constant.group(3),
                        "kind": "constant",
                        "constant_name": constant.group(1),
                    }
                )
            continue
        for match in _INLINE_CALL_RE.finditer(line):
            value = match.group(2)
            if not looks_like_selector(value):
                continue
            key = (value, line_no)
            if key in seen:
                continue
            seen.add(key)
            refs.append({"file": path, "line": line_no, "selector": value, "kind": "inline"})
        for match in _GET_BY_ROLE_RE.finditer(line):
            role, _q, name = match.group(1), match.group(2), match.group(3)
            value = f"role={role}" + (f'[name="{name}"]' if name else "")
            key = (value, line_no)
            if key in seen:
                continue
            seen.add(key)
            refs.append({"file": path, "line": line_no, "selector": value, "kind": "role"})
    return refs


def system_of_path(path: str) -> str:
    """소스 경로에서 소속 시스템 코드를 유추한다(공용 스텝은 공용 라벨)."""
    parts = path.replace("\\", "/").split("/")
    if "page_objects" in parts:
        idx = parts.index("page_objects")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    if "systems" in parts:
        idx = parts.index("systems")
        if idx + 1 < len(parts):
            code = parts[idx + 1]
            return "공용(access_common)" if code == "access_common" else code
    if "scenarios" in parts:
        return "공용(rep_homepage · HOM/MHM)"
    return "기타"


def build_durability_map(
    sources: dict[str, str],
    events: list[HealingEvent],
    *,
    top_n: int = 10,
) -> dict[str, Any]:
    """내구성 히트맵 + 만성 취약 Top N + '정비 필요' 묶음 알림을 만든다."""
    heal_counts = heal_counts_by_selector(events)
    # 시스템 구분 없이 셀렉터 문자열만으로도 집계(공용 스텝은 시스템 특정이 어렵다).
    heal_counts_any: dict[str, int] = {}
    for (_system, selector), count in heal_counts.items():
        heal_counts_any[selector] = heal_counts_any.get(selector, 0) + count

    rows: list[dict[str, Any]] = []
    for path, source in sorted(sources.items()):
        for ref in extract_selector_refs(path, source):
            score, grade, notes = classify_selector(ref["selector"])
            heal_count = heal_counts_any.get(ref["selector"], 0)
            rows.append(
                {
                    **ref,
                    "system": system_of_path(path),
                    "score": score,
                    "grade": grade,
                    "notes": notes,
                    "heal_count": heal_count,
                    "chronic": heal_count >= CHRONIC_HEAL_THRESHOLD,
                    # 취약도(낮은 안정성) + 실제 깨짐 이력 결합 위험 순위 점수.
                    "risk": (100 - score) + heal_count * 15,
                }
            )

    summary = {"green": 0, "amber": 0, "red": 0}
    for row in rows:
        summary[row["grade"]] += 1

    top_risky = sorted(rows, key=lambda r: r["risk"], reverse=True)[:top_n]
    needs_repair = [r for r in rows if r["chronic"]]
    needs_repair.sort(key=lambda r: r["heal_count"], reverse=True)

    by_system: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = by_system.setdefault(row["system"], {"green": 0, "amber": 0, "red": 0, "total": 0})
        bucket[row["grade"]] += 1
        bucket["total"] += 1

    return {
        "summary": summary,
        "by_system": by_system,
        "rows": rows,
        "top_risky": top_risky,
        # 알림 피로 저감: 개별 실패 대신 "이 셀렉터 N회+ 깨짐 → 정비 필요" 한 건으로 묶는다.
        "needs_repair": needs_repair,
    }
