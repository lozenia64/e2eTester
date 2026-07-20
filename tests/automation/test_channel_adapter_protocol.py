"""ChannelAdapter Protocol 구조적 만족 검증."""

from __future__ import annotations

from app.automation.channel_adapters.fake import FakeChannelAdapter
from app.automation.channel_adapters.hom import HomChannelAdapter
from app.automation.channel_adapters.mhm import MhmChannelAdapter
from app.automation.channel_adapters.protocol import ChannelAdapter


def test_fake_channel_adapter_satisfies_protocol():
    assert isinstance(FakeChannelAdapter(), ChannelAdapter)


def test_hom_channel_adapter_satisfies_protocol():
    assert isinstance(HomChannelAdapter(), ChannelAdapter)


def test_mhm_channel_adapter_satisfies_protocol():
    assert isinstance(MhmChannelAdapter(), ChannelAdapter)
