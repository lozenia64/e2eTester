"""파이썬 SSOT ↔ TS 생성물 ↔ 서버 렌더 3자 일치.

같은 상태를 세 경로가 다르게 그리던 것이 P3-1 이 고친 버그의 본질이다.
어느 한쪽만 바뀌면 이 테스트가 막는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core.enums import ModuleStatus, RunStatus, SuiteStatus
from app.core.status_labels import STATUS_TONES, module_status_label
from app.web.status_view import status_badge_view

GENERATED_TS = Path("app/web/frontend/lib/status.generated.ts")


def _parse_ts_object(source: str, name: str) -> dict[str, str]:
    """생성물 TS 의 `export const <name>: Record<string, string> = { ... };` 를 읽는다.

    생성기가 만드는 형식은 결정적이다(키·값 모두 이중 인용부호, 후행 콤마).
    JSON 으로 바꿔 파싱하므로 정규식으로 값을 하나씩 긁지 않는다.
    """
    match = re.search(
        rf"export const {name}: Record<string, \w+> = \{{(.*?)\n\}};", source, re.S
    )
    assert match, f"{name} 을 {GENERATED_TS} 에서 찾지 못했습니다."
    body = match.group(1).strip().rstrip(",")
    return json.loads("{" + body + "}")


@pytest.fixture(scope="module")
def generated_source() -> str:
    assert GENERATED_TS.exists(), (
        f"{GENERATED_TS} 가 없습니다. `python3 scripts/gen_frontend_tokens.py` 를 실행하세요."
    )
    return GENERATED_TS.read_text(encoding="utf-8")


def test_ts_tone_map_matches_python(generated_source: str) -> None:
    """축 3: TS 생성물의 톤 매핑 == 파이썬 톤 매핑."""
    ts_map = _parse_ts_object(generated_source, "STATUS_TONE_MAP")
    for status in ModuleStatus:
        assert ts_map[status.value.lower()] == status_badge_view(status).tone, status


def test_ts_labels_match_python(generated_source: str) -> None:
    ts_labels = _parse_ts_object(generated_source, "MODULE_STATUS_LABELS")
    for status in ModuleStatus:
        assert ts_labels[status.value.lower()] == module_status_label(status), status


def test_ts_union_covers_the_nine_tones(generated_source: str) -> None:
    for tone in STATUS_TONES:
        assert f'"{tone}"' in generated_source, tone


@pytest.mark.parametrize(
    "enum_cls", [ModuleStatus, RunStatus, SuiteStatus], ids=["module", "run", "suite"]
)
def test_every_status_resolves_into_the_nine_tone_axis(enum_cls) -> None:
    for status in enum_cls:
        assert status_badge_view(status).tone in STATUS_TONES, status
