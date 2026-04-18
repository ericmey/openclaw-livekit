"""Tests for env loading module."""

from openclaw_livekit_agent_sdk.env import load_env


def test_load_env_callable():
    """load_env is a callable function."""
    assert callable(load_env)
