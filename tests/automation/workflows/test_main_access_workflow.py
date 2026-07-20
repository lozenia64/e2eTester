"""MainAccessWorkflow 단위 테스트 — fake page/adapter만 사용(브라우저·네트워크 없음)."""

from __future__ import annotations

import pytest

from app.automation.channel_adapters.fake import FakeChannelAdapter
from app.automation.channel_adapters.mhm import MhmChannelAdapter
from app.automation.channel_adapters.recording import RecordingChannelAdapter
from app.automation.workflows.rep_homepage.main_access import (
    MAIN_ACCESS_TIMEOUT_MS,
    MainAccessWorkflow,
    _close_home_popup,
)


class _FakeLocator:
    def __init__(self, visible: bool) -> None:
        self._visible = visible
        self.clicked = False

    def is_visible(self, *, timeout: int = 0) -> bool:
        return self._visible

    def click(self) -> None:
        self.clicked = True


class _FakeLocatorChain:
    def __init__(self, visible: bool) -> None:
        self.first = _FakeLocator(visible)


class _FakePage:
    def __init__(self, *, popup_visible: bool = False) -> None:
        self.url = "https://example.com/after"
        self.goto_calls: list[tuple] = []
        self._popup_visible = popup_visible
        self._locator = _FakeLocatorChain(popup_visible)

    def goto(self, url: str, *, wait_until: str, timeout: int) -> None:
        self.goto_calls.append((url, wait_until, timeout))

    def get_by_role(self, role: str, *, name):
        assert role == "button"
        return self._locator


def test_precondition_runs_before_goto():
    adapter = FakeChannelAdapter()
    page = _FakePage()
    workflow = MainAccessWorkflow()

    workflow.run(adapter, page, "https://www.example.com")

    assert adapter.calls[0][0] == "ensure_navigation_precondition"
    assert len(page.goto_calls) == 1


def test_goto_uses_expected_arguments():
    adapter = FakeChannelAdapter()
    page = _FakePage()
    base_url = "https://www.example.com"

    MainAccessWorkflow().run(adapter, page, base_url)

    assert page.goto_calls == [
        (base_url, "domcontentloaded", MAIN_ACCESS_TIMEOUT_MS),
    ]


@pytest.mark.parametrize("popup_visible", [True, False])
def test_close_home_popup_matches_maybe_close_home_popup(popup_visible: bool):
    page = _FakePage(popup_visible=popup_visible)

    _close_home_popup(page)

    assert page._locator.first.clicked is popup_visible


def test_recording_adapter_preserves_workflow_call_order():
    inner = FakeChannelAdapter()
    recording = RecordingChannelAdapter(inner)
    page = _FakePage()

    MainAccessWorkflow().run(recording, page, "https://www.example.com")

    assert [name for name, *_ in recording.calls] == ["ensure_navigation_precondition"]
    assert inner.calls == recording.calls
    assert page.goto_calls


def test_mhm_adapter_requires_mobile_mode_flag():
    adapter = MhmChannelAdapter()
    page = _FakePage()

    with pytest.raises(RuntimeError, match="모바일 디바이스 모드"):
        adapter.ensure_navigation_precondition(page)


def test_mhm_adapter_passes_when_mobile_mode_applied():
    adapter = MhmChannelAdapter()
    page = _FakePage()
    page._mhm_mobile_mode_applied = True

    adapter.ensure_navigation_precondition(page)


def test_workflow_returns_success_message():
    result = MainAccessWorkflow().run(FakeChannelAdapter(), _FakePage(), "https://example.com")
    assert result == "메인화면 접속 성공"
