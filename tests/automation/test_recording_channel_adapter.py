"""RecordingChannelAdapter 위임·기록·tracing 비활성 경로 검증."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.automation.channel_adapters.fake import FakeChannelAdapter
from app.automation.channel_adapters.recording import RecordingChannelAdapter


def test_recording_delegates_and_records_calls():
    inner = FakeChannelAdapter()
    recording = RecordingChannelAdapter(inner)
    page = object()

    recording.ensure_navigation_precondition(page)

    assert inner.calls == [("ensure_navigation_precondition", (page,), {})]
    assert recording.calls == [("ensure_navigation_precondition", (page,), {})]


def test_recording_preserves_call_order():
    inner = FakeChannelAdapter()
    recording = RecordingChannelAdapter(inner)
    pages = [object(), object()]

    for page in pages:
        recording.ensure_navigation_precondition(page)

    assert [call[1][0] for call in recording.calls] == pages
    assert recording.calls == inner.calls


def test_tracing_not_touched_when_disabled():
    context = MagicMock()
    recording = RecordingChannelAdapter(
        FakeChannelAdapter(),
        enabled=False,
        context=context,
    )

    recording.ensure_navigation_precondition(object())

    context.tracing.start.assert_not_called()


def test_tracing_starts_only_when_enabled():
    context = MagicMock()
    recording = RecordingChannelAdapter(
        FakeChannelAdapter(),
        enabled=True,
        context=context,
    )

    recording.ensure_navigation_precondition(object())

    context.tracing.start.assert_called_once_with(
        screenshots=True,
        snapshots=True,
        sources=True,
    )


def test_tracing_skipped_when_enabled_but_no_context():
    recording = RecordingChannelAdapter(FakeChannelAdapter(), enabled=True, context=None)
    recording.ensure_navigation_precondition(object())
