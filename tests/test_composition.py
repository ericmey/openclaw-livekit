"""Tests for mixin composition — verifying all 10 tools on a composed agent."""


EXPECTED_TOOLS = [
    "get_current_time",
    "get_weather",
    "openclaw_request",
    "musubi_recent",
    "memory_store",
    "sessions_send",
    "sessions_spawn",
    "schedule_callback",
    "academy_selfie",
    "academy_send",
]


def test_all_ten_tools_present(agent):
    """A fully composed agent has all 10 expected tools."""
    for tool_name in EXPECTED_TOOLS:
        assert hasattr(agent, tool_name), f"Missing tool: {tool_name}"


def test_exactly_ten_tools(agent):
    """No extra unexpected tools on the composed agent."""
    found = []
    for name in EXPECTED_TOOLS:
        attr = getattr(agent, name, None)
        if attr is not None and callable(attr):
            found.append(name)
    assert len(found) == 10, f"Expected 10 tools, found {len(found)}: {found}"


def test_mro_includes_all_mixins(agent):
    """MRO includes all four mixin classes."""
    from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin
    from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin
    from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin
    from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin

    mro = type(agent).__mro__
    assert CoreToolsMixin in mro
    assert MemoryToolsMixin in mro
    assert SessionsToolsMixin in mro
    assert AcademyToolsMixin in mro
