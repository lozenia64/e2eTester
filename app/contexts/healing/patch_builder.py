"""셀렉터 오토픽스 패치 제안 — 순수 빌더(소스 텍스트 → before/after diff).

런타임 치유는 일회성이므로, 깨진 하드코딩 셀렉터를 대체 셀렉터로 바꾸는 소스 수정을
**diff 로 제안**한다. 자동 병합은 하지 않는다 — 승인 게이트(사람)가 통과시켜야
``HealingService`` 가 파일에 적용한다. 파일 I/O 없음: 입력은 {상대경로: 소스 텍스트}.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from app.contexts.healing.durability import classify_selector


@dataclass(frozen=True)
class PatchDraft:
    """파일 1개에 대한 대체 셀렉터 반영 제안(영속 전 드래프트)."""

    file_path: str
    occurrences: int
    diff: str
    new_source: str
    warnings: list[str] = field(default_factory=list)


def _quoted_tokens(selector: str) -> list[str]:
    """소스에 등장할 수 있는 셀렉터 리터럴 표기(양쪽 따옴표 스타일)를 만든다."""
    tokens: list[str] = []
    if '"' not in selector:
        tokens.append(f'"{selector}"')
    if "'" not in selector:
        tokens.append(f"'{selector}'")
    return tokens


def _replacement_literal(healed: str, quote: str) -> str:
    if quote not in healed:
        chosen = quote
    elif '"' not in healed:
        chosen = '"'
    elif "'" not in healed:
        chosen = "'"
    else:
        chosen = quote
    escaped = healed.replace("\\", "\\\\").replace(chosen, f"\\{chosen}")
    return f"{chosen}{escaped}{chosen}"


def apply_replacement(source: str, broken: str, healed: str) -> tuple[str, int]:
    """소스 텍스트에서 깨진 셀렉터 리터럴을 대체 셀렉터 리터럴로 치환한다."""
    replaced = source
    count = 0
    for token in _quoted_tokens(broken):
        occurrences = replaced.count(token)
        if not occurrences:
            continue
        replaced = replaced.replace(token, _replacement_literal(healed, token[0]))
        count += occurrences
    return replaced, count


def build_patch_drafts(
    sources: dict[str, str],
    *,
    broken_selector: str,
    healed_selector: str,
) -> list[PatchDraft]:
    """깨진 셀렉터 리터럴이 등장하는 모든 소스 파일에 대해 패치 드래프트를 만든다."""
    drafts: list[PatchDraft] = []
    warnings = _tech_debt_warnings(healed_selector)
    for path in sorted(sources):
        original = sources[path]
        new_source, count = apply_replacement(original, broken_selector, healed_selector)
        if not count:
            continue
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                new_source.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        drafts.append(
            PatchDraft(
                file_path=path,
                occurrences=count,
                diff=diff,
                new_source=new_source,
                warnings=list(warnings),
            )
        )
    return drafts


def _tech_debt_warnings(healed_selector: str) -> list[str]:
    """기술부채 가드("More Code, Less Reuse") — 취약 패턴 대체 셀렉터에 경고를 단다."""
    warnings: list[str] = []
    score, grade, notes = classify_selector(healed_selector)
    if grade == "red":
        warnings.append(
            f"대체 셀렉터가 취약 패턴입니다(안정성 {score}점: {' / '.join(notes)}). "
            "접근성 role/label 기반 셀렉터로의 재작성을 검토하세요."
        )
    elif grade == "amber":
        warnings.append(
            f"대체 셀렉터의 안정성이 보통입니다({score}점). "
            "기존 공용 헬퍼(app/systems/access_common/browser.py)의 패턴 재사용을 우선 검토하세요."
        )
    if ">> nth=" in healed_selector:
        warnings.append(
            "인덱스 고정(>> nth=0)이 포함되어 있습니다 — 요소 순서 변경에 다시 깨질 수 있습니다."
        )
    return warnings
