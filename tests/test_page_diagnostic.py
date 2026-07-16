"""page_diagnostic 모듈 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from app.runner.page_diagnostic import capture_page_html_diagnostic


class _FakeOverlayPage:
    url = "https://example.test/consent"

    def content(self) -> str:
        return "<html><body><main>consent page</main></body></html>"

    def evaluate(self, _script: str, _selector: str) -> list[dict[str, str]]:
        return [
            {
                "id": "detailPopup",
                "className": "pop_round open",
                "tag": "DIV",
                "html": '<div id="detailPopup" class="pop_round open"><button class="btn_close">X</button></div>',
            }
        ]


def test_capture_page_html_diagnostic_writes_log_and_artifact(tmp_path: Path) -> None:
    logs: list[str] = []
    artifact_dir = tmp_path / "module"

    capture_page_html_diagnostic(_FakeOverlayPage(), artifact_dir, logs.append)

    html_path = artifact_dir / "page.html"
    assert html_path.exists()
    assert "<main>consent page</main>" in html_path.read_text(encoding="utf-8")
    assert any("[diagnostic] anomaly page HTML captured" in line for line in logs)
    assert any(line == "[diagnostic] page_html_begin" for line in logs)
    assert any(line == "[diagnostic] page_html_end" for line in logs)
    assert any("[diagnostic] overlay_html_begin index=0" in line for line in logs)
    assert 'id="detailPopup"' in "\n".join(logs)
