"""Tests for SessionsToolsMixin — sessions_send, sessions_spawn, schedule_callback."""

from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin


def test_sessions_mixin_has_sessions_send():
    assert hasattr(SessionsToolsMixin, "sessions_send")
    assert callable(getattr(SessionsToolsMixin, "sessions_send"))


def test_sessions_mixin_has_sessions_spawn():
    assert hasattr(SessionsToolsMixin, "sessions_spawn")
    assert callable(getattr(SessionsToolsMixin, "sessions_spawn"))


def test_sessions_mixin_has_schedule_callback():
    assert hasattr(SessionsToolsMixin, "schedule_callback")
    assert callable(getattr(SessionsToolsMixin, "schedule_callback"))


def test_composed_agent_has_sessions_tools(agent):
    """Session tools are discoverable on a composed agent instance."""
    assert hasattr(agent, "sessions_send")
    assert hasattr(agent, "sessions_spawn")
    assert hasattr(agent, "schedule_callback")


def test_schedule_callback_reads_caller_from(agent):
    """schedule_callback accesses _caller_from set by concrete class."""
    assert agent._caller_from == "+15551234567"
