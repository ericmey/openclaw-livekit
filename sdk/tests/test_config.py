"""Tests for AgentConfig + NYLA_DEFAULT_CONFIG."""

import pytest
from sdk.config import NYLA_DEFAULT_CONFIG, AgentConfig


def test_agent_config_is_frozen():
    """Immutability — a config once built can't be silently mutated."""
    cfg = AgentConfig(
        agent_name="x",
        memory_agent_tag="x-voice",
        discord_room="channel:0",
    )
    with pytest.raises(AttributeError):
        cfg.agent_name = "y"  # type: ignore[misc]


def test_nyla_default_config_values():
    """The SDK-level default tags everything as Nyla and unrestricts delegation."""
    assert NYLA_DEFAULT_CONFIG.agent_name == "nyla"
    assert NYLA_DEFAULT_CONFIG.memory_agent_tag == "nyla-voice"
    assert NYLA_DEFAULT_CONFIG.discord_room.startswith("channel:")
    assert NYLA_DEFAULT_CONFIG.allowed_delegation_targets is None


def test_agent_config_accepts_delegation_allowlist():
    cfg = AgentConfig(
        agent_name="aoi",
        memory_agent_tag="aoi-voice",
        discord_room="channel:0",
        allowed_delegation_targets=frozenset({"yumi", "rin"}),
    )
    assert cfg.allowed_delegation_targets == frozenset({"yumi", "rin"})
