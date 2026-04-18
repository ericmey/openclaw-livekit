"""Tests for MemoryToolsMixin — musubi_recent, memory_store, memory_agent_tag."""

from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin


def test_memory_mixin_has_musubi_recent():
    assert hasattr(MemoryToolsMixin, "musubi_recent")
    assert callable(getattr(MemoryToolsMixin, "musubi_recent"))


def test_memory_mixin_has_memory_store():
    assert hasattr(MemoryToolsMixin, "memory_store")
    assert callable(getattr(MemoryToolsMixin, "memory_store"))


def test_memory_agent_tag_default_is_nyla_voice():
    """Unless a subclass overrides it, stored memories are tagged as Nyla's."""
    assert MemoryToolsMixin.memory_agent_tag == "nyla-voice"


def test_memory_agent_tag_is_overridable():
    """A subclass can set memory_agent_tag to a different voice identity."""
    class _AoiMemory(MemoryToolsMixin):
        memory_agent_tag = "aoi-voice"

    assert _AoiMemory.memory_agent_tag == "aoi-voice"
    # Parent class unaffected.
    assert MemoryToolsMixin.memory_agent_tag == "nyla-voice"


def test_composed_agent_has_memory_tools(agent):
    """Memory tools are discoverable on a composed agent instance."""
    assert hasattr(agent, "musubi_recent")
    assert hasattr(agent, "memory_store")
    # Default composed agent doesn't override, so tag is "nyla-voice".
    assert agent.memory_agent_tag == "nyla-voice"
