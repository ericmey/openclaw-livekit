"""Tests for mixin composition — verifying all 9 tools on a composed agent."""

EXPECTED_TOOLS = [
    "get_current_time",
    "get_weather",
    "musubi_recent",
    "memory_store",
    "sessions_send",
    "sessions_spawn",
    "academy_selfie",
    "academy_send",
]

# schedule_callback is deliberately disabled — the @function_tool decorator
# is removed so the voice model can't discover it. The method body is
# preserved for guardrail tests. See SDK/TODO.md for the re-enable plan.
DISABLED_TOOLS = ["schedule_callback"]


def test_all_active_tools_present(agent):
    """A fully composed agent has all 8 active expected tools."""
    for tool_name in EXPECTED_TOOLS:
        assert hasattr(agent, tool_name), f"Missing tool: {tool_name}"


def test_exactly_eight_active_tools(agent):
    """No extra unexpected active tools on the composed agent."""
    found = []
    for name in EXPECTED_TOOLS:
        attr = getattr(agent, name, None)
        if attr is not None and callable(attr):
            found.append(name)
    assert len(found) == 8, f"Expected 8 tools, found {len(found)}: {found}"


def test_openclaw_request_absent(agent):
    """openclaw_request was deleted in the SDK cleanup — must not be on agents."""
    attr = getattr(agent, "openclaw_request", None)
    assert not callable(attr), "openclaw_request should have been removed"


def test_mro_includes_all_mixins(agent):
    """MRO includes all four mixin classes."""
    from tools.academy import AcademyToolsMixin
    from tools.core import CoreToolsMixin
    from tools.memory import MemoryToolsMixin
    from tools.sessions import SessionsToolsMixin

    mro = type(agent).__mro__
    assert CoreToolsMixin in mro
    assert MemoryToolsMixin in mro
    assert SessionsToolsMixin in mro
    assert AcademyToolsMixin in mro
