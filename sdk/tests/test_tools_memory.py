"""Tests for MemoryToolsMixin — musubi_recent, memory_store, fetch_recent_context."""

from sdk.config import NYLA_DEFAULT_CONFIG, AgentConfig
from tools.memory import MemoryToolsMixin


def test_memory_mixin_has_musubi_recent():
    assert hasattr(MemoryToolsMixin, "musubi_recent")
    assert callable(MemoryToolsMixin.musubi_recent)


def test_memory_mixin_has_memory_store():
    assert hasattr(MemoryToolsMixin, "memory_store")
    assert callable(MemoryToolsMixin.memory_store)


def test_memory_mixin_exposes_fetch_recent_context_helper():
    """The plain-async helper used by on_enter must exist and be callable
    without the function_tool wrapping that musubi_recent carries."""
    assert hasattr(MemoryToolsMixin, "fetch_recent_context")
    assert callable(MemoryToolsMixin.fetch_recent_context)


def test_memory_mixin_default_config_is_nyla():
    """Absent an override, stored memories are tagged as Nyla's."""
    assert MemoryToolsMixin.config is NYLA_DEFAULT_CONFIG
    assert MemoryToolsMixin.config.memory_agent_tag == "nyla-voice"


def test_memory_mixin_config_is_overridable():
    """A subclass can point config at a different AgentConfig."""
    aoi_cfg = AgentConfig(
        agent_name="aoi",
        memory_agent_tag="aoi-voice",
        discord_room="channel:0",
    )

    class _AoiMemory(MemoryToolsMixin):
        config = aoi_cfg

    assert _AoiMemory.config.memory_agent_tag == "aoi-voice"
    # Parent class unaffected.
    assert MemoryToolsMixin.config.memory_agent_tag == "nyla-voice"


def test_composed_agent_has_memory_tools(agent):
    """Memory tools are discoverable on a composed agent instance."""
    assert hasattr(agent, "musubi_recent")
    assert hasattr(agent, "memory_store")
    assert hasattr(agent, "fetch_recent_context")
    # Default composed agent doesn't override, so tag is "nyla-voice".
    assert agent.config.memory_agent_tag == "nyla-voice"
