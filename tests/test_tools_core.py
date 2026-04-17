"""Tests for CoreToolsMixin — get_current_time, get_weather, openclaw_request."""

from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin


def test_core_mixin_has_get_current_time():
    assert hasattr(CoreToolsMixin, "get_current_time")
    assert callable(getattr(CoreToolsMixin, "get_current_time"))


def test_core_mixin_has_get_weather():
    assert hasattr(CoreToolsMixin, "get_weather")
    assert callable(getattr(CoreToolsMixin, "get_weather"))


def test_core_mixin_has_openclaw_request():
    assert hasattr(CoreToolsMixin, "openclaw_request")
    assert callable(getattr(CoreToolsMixin, "openclaw_request"))


def test_composed_agent_has_core_tools(agent):
    """Core tools are discoverable on a composed agent instance."""
    assert hasattr(agent, "get_current_time")
    assert hasattr(agent, "get_weather")
    assert hasattr(agent, "openclaw_request")
