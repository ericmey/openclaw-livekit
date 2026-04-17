"""Tests for MemoryToolsMixin — musubi_recent, memory_store."""

from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin


def test_memory_mixin_has_musubi_recent():
    assert hasattr(MemoryToolsMixin, "musubi_recent")
    assert callable(getattr(MemoryToolsMixin, "musubi_recent"))


def test_memory_mixin_has_memory_store():
    assert hasattr(MemoryToolsMixin, "memory_store")
    assert callable(getattr(MemoryToolsMixin, "memory_store"))


def test_composed_agent_has_memory_tools(agent):
    """Memory tools are discoverable on a composed agent instance."""
    assert hasattr(agent, "musubi_recent")
    assert hasattr(agent, "memory_store")
