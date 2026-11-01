"""문서 가드가 실제 누락·오등록을 차단하고 유효한 인덱스는 허용하는지 검증한다."""

from __future__ import annotations

import pytest

from scripts import check_docs_consistency as guard


@pytest.fixture
def spec_index(tmp_path, monkeypatch):
    specs = tmp_path / "docs" / "specs"
    specs.mkdir(parents=True)
    index = specs / "README.md"
    monkeypatch.setattr(guard, "SPECS_INDEX_DOC", index)
    return specs, index


@pytest.mark.spec("SPEC-PLATFORM-005", "AC-003")
@pytest.mark.parametrize("anchor", ["", "#ac-001"])
def test_spec_index_accepts_valid_links_with_optional_fragment(spec_index, anchor):
    specs, index = spec_index
    (specs / "sample.md").write_text(
        "| **ID** | `SPEC-PLATFORM-001` |\n### AC-001: 검증\n", encoding="utf-8"
    )
    index.write_text(f"| SPEC-PLATFORM-001 | [명세](sample.md{anchor}) |\n", encoding="utf-8")

    assert guard.check_spec_index_links_exist().ok


@pytest.mark.spec("SPEC-PLATFORM-005", "AC-003")
def test_spec_index_rejects_wrong_id_even_when_dependency_mentions_indexed_id(spec_index):
    specs, index = spec_index
    (specs / "sample.md").write_text(
        "| **ID** | `SPEC-PLATFORM-002` |\n| **의존** | `SPEC-PLATFORM-001` |\n",
        encoding="utf-8",
    )
    index.write_text("| SPEC-PLATFORM-001 | [명세](sample.md) |\n", encoding="utf-8")

    result = guard.check_spec_index_links_exist()

    assert not result.ok
    assert any("SPEC ID 불일치" in problem for problem in result.problems)


@pytest.mark.spec("SPEC-PLATFORM-005", "AC-003")
def test_spec_index_rejects_unlisted_spec_and_missing_link_target(spec_index):
    specs, index = spec_index
    (specs / "unlisted.md").write_text("# 누락된 명세\n", encoding="utf-8")
    index.write_text("[없는 명세](missing.md#검증)\n", encoding="utf-8")

    result = guard.check_spec_index_links_exist()

    assert not result.ok
    assert any("unlisted.md" in problem for problem in result.problems)
    assert any(
        "missing.md" in problem and "대상 파일이 없음" in problem for problem in result.problems
    )


@pytest.mark.spec("SPEC-PLATFORM-005", "AC-003")
@pytest.mark.parametrize(
    "rows",
    [
        "| — | [명세](sample.md) |\n",
        "| SPEC-PLATFORM-001 | [명세](sample.md) |\n" * 2,
        "| SPEC-PLATFORM-001 | [명세](sample.md) |\n| SPEC-PLATFORM-001 | [복제](copy.md) |\n",
    ],
)
def test_spec_index_rejects_missing_id_and_duplicate_spec_rows(spec_index, rows):
    specs, index = spec_index
    metadata = "| **ID** | `SPEC-PLATFORM-001` |\n"
    (specs / "sample.md").write_text(metadata, encoding="utf-8")
    if "copy.md" in rows:
        (specs / "copy.md").write_text(metadata, encoding="utf-8")
    index.write_text(rows, encoding="utf-8")

    assert not guard.check_spec_index_links_exist().ok
