"""셀렉터 치유의 **순수 계산** 부분 — 파싱·힌트 추출·후보 스코어링.

브라우저/Playwright 를 import 하지 않는다. 입력은 (깨진 셀렉터 문자열, DOM 스캔 결과
dict 목록)이고 출력은 신뢰도 순 후보 목록이다. 실행/검증 I/O 는 ``engine`` 이 담당한다.
2026 셀렉터 치유 관행을 따른다: 요소 지문(id·name·text·role·class)을 동시에 비교해
최고 신뢰도 후보를 고르고, 신뢰도는 임계치 게이팅과 감사 로그에 그대로 남긴다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.contexts.healing.models import ScoredCandidate, SelectorHints

# Playwright 오류 메시지에서 깨진 셀렉터를 뽑는 패턴(마지막 locator 가 실제 대상).
_LOCATOR_DQ_RE = re.compile(r'locator\("((?:[^"\\]|\\.)+)"\)')
_LOCATOR_SQ_RE = re.compile(r"locator\('((?:[^'\\]|\\.)+)'\)")
_WAITING_SELECTOR_RE = re.compile(r'waiting for selector "((?:[^"\\]|\\.)+)"')

_ID_RE = re.compile(r"#([A-Za-z_][-\w]*)")
_ID_PREFIX_RE = re.compile(r"\[id\^=[\"']?([^\"'\]]+?)[\"']?\]")
_NAME_ATTR_RE = re.compile(r"\[name=[\"']?([^\"'\]]+?)[\"']?\]")
_HAS_TEXT_RE = re.compile(r":has-text\([\"']([^\"']+)[\"']\)")
_TEXT_ENGINE_RE = re.compile(r"^text=(.+)$")
_LEADING_TAG_RE = re.compile(r"^([a-z][a-z0-9]*)\b")
_CLASS_RE = re.compile(r"\.([-\w]+)")

# 자동 적용 대상에서 아예 제외하는 최저 신뢰도(이 미만 후보는 제안조차 하지 않는다).
CANDIDATE_FLOOR = 0.35


def _unescape_selector(selector: str) -> str:
    return selector.replace('\\"', '"').replace("\\'", "'")


def parse_broken_selector(error_text: str) -> str | None:
    """Playwright 오류 문자열에서 실패한 셀렉터를 추출한다.

    frame_locator("...").locator("#x") 처럼 체인이면 **마지막** locator 가 실제 실패
    대상이다. locator 기반이 아닌 실패(get_by_role, URL 대기 등)는 대체 셀렉터를
    주입할 방법이 없으므로 None 을 돌려 치유를 건너뛴다.
    """
    last: tuple[int, str] | None = None
    for pattern in (_LOCATOR_DQ_RE, _LOCATOR_SQ_RE):
        for match in pattern.finditer(error_text):
            pos = match.start()
            selector = _unescape_selector(match.group(1))
            if last is None or pos >= last[0]:
                last = (pos, selector)
    if last:
        return last[1]
    waiting = _WAITING_SELECTOR_RE.findall(error_text)
    if waiting:
        return waiting[-1].replace('\\"', '"')
    return None


def extract_hints(selector: str) -> SelectorHints:
    """깨진 셀렉터를 요소 지문 힌트(id/name/text/tag/class)로 분해한다."""
    text_match = _TEXT_ENGINE_RE.match(selector.strip())
    has_text = _HAS_TEXT_RE.search(selector)
    id_match = _ID_RE.search(selector)
    return SelectorHints(
        raw=selector,
        element_id=id_match.group(1) if id_match else None,
        id_prefix=_first(_ID_PREFIX_RE, selector),
        name=_first(_NAME_ATTR_RE, selector),
        text=(text_match.group(1).strip() if text_match else None)
        or (has_text.group(1).strip() if has_text else None),
        tag=_first(_LEADING_TAG_RE, selector),
        classes=tuple(_CLASS_RE.findall(selector)),
    )


def _first(pattern: re.Pattern[str], value: str) -> str | None:
    match = pattern.search(value)
    return match.group(1) if match else None


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _strip_digits(value: str) -> str:
    return re.sub(r"\d+", "", value)


_CSS_IDENT_RE = re.compile(r"^[A-Za-z_][-\w]*$")


def build_candidate_selector(candidate: dict) -> str | None:
    """스캔된 요소 1건을 가리키는 가장 견고한 셀렉터 문자열을 만든다(안정성 우선순위)."""
    tag = candidate.get("tag") or ""
    element_id = candidate.get("id") or ""
    name = candidate.get("name") or ""
    aria = candidate.get("aria") or ""
    text = _norm_text(candidate.get("text") or "")
    classes = [c for c in (candidate.get("cls") or "").split() if _CSS_IDENT_RE.match(c)]

    if element_id:
        if _CSS_IDENT_RE.match(element_id):
            return f"#{element_id}"
        return f'[id="{element_id}"]'
    if name:
        return f'{tag}[name="{name}"]'
    if aria:
        return f'{tag}[aria-label="{aria}"]'
    if text:
        escaped = text[:40].replace('"', '\\"')
        return f'{tag}:has-text("{escaped}")'
    if classes:
        return f"{tag}.{classes[0]}"
    return None


def score_candidates(hints: SelectorHints, candidates: list[dict]) -> list[ScoredCandidate]:
    """요소 지문 힌트와 DOM 스캔 결과를 대조해 신뢰도 내림차순 후보를 만든다."""
    scored: list[ScoredCandidate] = []
    for candidate in candidates:
        selector = build_candidate_selector(candidate)
        if not selector or selector == hints.raw:
            continue
        confidence, reason = _score_one(hints, candidate)
        if confidence < CANDIDATE_FLOOR:
            continue
        summary = _summarize(candidate)
        scored.append(
            ScoredCandidate(
                selector=selector,
                confidence=round(min(confidence, 0.99), 3),
                reason=reason,
                summary=summary,
            )
        )
    scored.sort(key=lambda item: item.confidence, reverse=True)
    return scored


def _score_one(hints: SelectorHints, candidate: dict) -> tuple[float, str]:
    signals: list[tuple[float, str]] = []
    cand_id = candidate.get("id") or ""
    cand_name = candidate.get("name") or ""
    cand_text = _norm_text(candidate.get("text") or "")
    cand_aria = _norm_text(candidate.get("aria") or "")
    cand_tag = candidate.get("tag") or ""
    cand_classes = set((candidate.get("cls") or "").split())

    if hints.element_id and cand_id:
        if cand_id == hints.element_id:
            signals.append((0.97, "동일 id 재발견"))
        elif _strip_digits(cand_id) and _strip_digits(cand_id) == _strip_digits(hints.element_id):
            signals.append((0.88, "숫자 접미사만 바뀐 id"))
        else:
            ratio = SequenceMatcher(None, hints.element_id.lower(), cand_id.lower()).ratio()
            if ratio >= 0.6:
                signals.append((ratio * 0.9, f"유사 id (유사도 {ratio:.2f})"))
    if hints.id_prefix and cand_id.startswith(hints.id_prefix):
        signals.append((0.85, "id prefix 일치"))
    if hints.element_id and cand_name and cand_name == hints.element_id:
        signals.append((0.82, "id 가 name 속성으로 이동"))
    if hints.name and cand_name and cand_name == hints.name:
        signals.append((0.9, "동일 name 속성"))
    if hints.text:
        target = _norm_text(hints.text)
        for value, label in ((cand_text, "텍스트"), (cand_aria, "aria-label")):
            if not value:
                continue
            if value == target:
                signals.append((0.93, f"{label} 완전 일치"))
            elif target in value or value in target:
                signals.append((0.76, f"{label} 부분 일치"))
    if hints.classes and cand_classes:
        overlap = len(set(hints.classes) & cand_classes)
        union = len(set(hints.classes) | cand_classes)
        if overlap:
            signals.append(((overlap / union) * 0.6, "class 중첩"))

    if not signals:
        return 0.0, ""
    confidence, reason = max(signals, key=lambda item: item[0])
    if hints.tag and cand_tag == hints.tag:
        confidence += 0.03
    if not candidate.get("visible", True):
        confidence *= 0.5
        reason += " (비가시 요소)"
    return confidence, reason


def _summarize(candidate: dict) -> str:
    parts = [candidate.get("tag") or "?"]
    if candidate.get("id"):
        parts.append(f"#{candidate['id']}")
    text = _norm_text(candidate.get("text") or "")
    if text:
        parts.append(f"“{text[:30]}”")
    return " ".join(parts)
