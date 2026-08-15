"""SDD Spec ↔ pytest ``@pytest.mark.spec`` 추적성 검증.

모든 ``@pytest.mark.spec("SPEC-...", "AC-...")`` 마커가 실제 Spec 문서·AC 섹션을
가리키는지 검사한다. P0 Spec부터 점진적으로 마커를 붙인다.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPECS_ROOT = REPO_ROOT / "docs" / "specs"
SPEC_ID_RE = re.compile(r"`(SPEC-[A-Z0-9-]+)`")
AC_HEADING_RE = re.compile(r"^### (AC-\d+):", re.MULTILINE)
MARKER_RE = re.compile(
    r'@pytest\.mark\.spec\(\s*["\'](SPEC-[^"\']+)["\']\s*,\s*["\'](AC-\d+)["\']\s*\)'
)


def _collect_spec_markers() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        text = path.read_text(encoding="utf-8")
        for spec_id, ac_id in MARKER_RE.findall(text):
            found.append((path.name, spec_id, ac_id))
    return found


def _spec_id_to_paths() -> dict[str, list[Path]]:
    mapping: dict[str, list[Path]] = {}
    for path in SPECS_ROOT.rglob("*.md"):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        for spec_id in SPEC_ID_RE.findall(text):
            mapping.setdefault(spec_id, []).append(path)
    return mapping


def _ac_ids_in_spec(path: Path) -> set[str]:
    return set(AC_HEADING_RE.findall(path.read_text(encoding="utf-8")))


def test_all_spec_markers_reference_valid_spec_ac() -> None:
    markers = _collect_spec_markers()
    assert markers, "최소 1개 @pytest.mark.spec 마커가 필요합니다."
    id_to_paths = _spec_id_to_paths()
    problems: list[str] = []
    for test_file, spec_id, ac_id in markers:
        paths = id_to_paths.get(spec_id)
        if not paths:
            problems.append(f"{test_file}: unknown spec_id {spec_id}")
            continue
        if not any(ac_id in _ac_ids_in_spec(p) for p in paths):
            problems.append(f"{test_file}: {spec_id} 에 {ac_id} 섹션 없음")
    assert not problems, "Spec 마커 정합성 실패:\n" + "\n".join(problems)
