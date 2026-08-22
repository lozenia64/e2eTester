"""레거시 페이지 스크립트의 상태 라벨이 SSOT 와 어긋나지 않는지.

어느 게이트도 `app/web/static/*.js` 를 보지 않는다 — FG-003 은
`frontend/**/*.ts` 만, FG-006 은 템플릿만 본다. 그 사각지대에서 드리프트가
조용히 자랐다.

발견 당시 실측:
  schedules.js   WAITING_INPUT="OTP 대기"  CANCELLED="취소됨"  PENDING="대기 중"
  admin-runs.js  PENDING·RUNNING·WAITING_INPUT 자체가 없어 `labels[value] || value`
                 폴백으로 영문 enum 이 화면에 그대로 나갔다

P4 가 이 파일들을 TS 로 이관하면 `lib/status.generated.ts` 를 쓰게 되므로
이 테스트는 함께 지운다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.enums import RunStatus
from app.core.status_labels import run_status_label

# 파일 → 라벨 맵을 담은 자바스크립트 객체 리터럴의 변수명
LEGACY_LABEL_MAPS = {
    Path("app/web/static/schedules.js"): "STATUS_LABELS",
    Path("app/web/static/admin-runs.js"): "labels",
}

_ENTRY_RE = re.compile(r"""(?P<key>[A-Z_]+)\s*:\s*["'](?P<label>[^"']+)["']""")


def _parse_label_map(path: Path, variable: str) -> dict[str, str]:
    """`const <variable> = { KEY: "라벨", ... };` 의 첫 블록을 읽는다."""
    source = path.read_text(encoding="utf-8")
    match = re.search(rf"{variable}\s*=\s*\{{(.*?)\}};", source, re.S)
    assert match, f"{path} 에서 {variable} 맵을 찾지 못했습니다."
    return {m["key"]: m["label"] for m in _ENTRY_RE.finditer(match.group(1))}


@pytest.mark.parametrize(("path", "variable"), sorted(LEGACY_LABEL_MAPS.items()))
def test_legacy_labels_match_the_ssot(path: Path, variable: str) -> None:
    """맵에 들어 있는 상태는 SSOT 와 같은 문구여야 한다."""
    for key, label in _parse_label_map(path, variable).items():
        try:
            status = RunStatus(key)
        except ValueError:
            continue  # 상태가 아닌 키(뷰 전용)는 대상이 아니다
        assert label == run_status_label(status), (
            f"{path}:{variable} 의 {key} 가 '{label}' 인데 SSOT 는 "
            f"'{run_status_label(status)}' 입니다."
        )


@pytest.mark.parametrize(("path", "variable"), sorted(LEGACY_LABEL_MAPS.items()))
def test_legacy_maps_cover_every_run_status(path: Path, variable: str) -> None:
    """빠진 상태는 `labels[value] || value` 폴백으로 영문 enum 이 화면에 나간다."""
    parsed = _parse_label_map(path, variable)
    missing = [status.value for status in RunStatus if status.value not in parsed]
    assert not missing, f"{path}:{variable} 에 없는 상태: {missing}"
