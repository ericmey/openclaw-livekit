"""Tests for MemoryToolsMixin — musubi_recent, musubi_search, memory_store, fetch_recent_context."""

from typing import Any, cast

import pytest
from sdk.config import NYLA_DEFAULT_CONFIG, AgentConfig
from tools.memory import MemoryToolsMixin


def _unwrap(tool: Any) -> Any:
    """LiveKit's `function_tool` wraps the underlying coroutine in a
    ``FunctionTool`` whose declared interface doesn't expose
    ``__wrapped__``, but the runtime always sets it (functools.wraps).
    Cast through ``Any`` so pyright doesn't complain on the test side
    while still asserting on real wire shape."""
    return cast(Any, tool).__wrapped__


def test_memory_mixin_has_musubi_recent():
    assert hasattr(MemoryToolsMixin, "musubi_recent")
    assert callable(MemoryToolsMixin.musubi_recent)


def test_memory_mixin_has_musubi_search():
    assert hasattr(MemoryToolsMixin, "musubi_search")
    assert callable(MemoryToolsMixin.musubi_search)


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
    assert hasattr(agent, "musubi_search")
    assert hasattr(agent, "memory_store")
    assert hasattr(agent, "fetch_recent_context")
    # Default composed agent doesn't override, so tag is "nyla-voice".
    assert agent.config.memory_agent_tag == "nyla-voice"


# ---------------------------------------------------------------------------
# musubi_search behaviour — namespace shape, state_filter, mode
# ---------------------------------------------------------------------------


class _StubClient:
    """Records a single retrieve() call so tests can assert the wire shape
    without standing up a real Musubi server. Mirrors `MusubiV2Client.retrieve`
    keyword arguments exactly so signature drift breaks the test."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self._response = response or {"results": []}
        self.calls: list[dict[str, Any]] = []

    async def retrieve(
        self,
        *,
        namespace: str,
        query_text: str,
        mode: str = "fast",
        limit: int = 10,
        planes: list[str] | None = None,
        include_archived: bool = False,
        state_filter: list[str] | None = None,
        session: object | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "namespace": namespace,
                "query_text": query_text,
                "mode": mode,
                "limit": limit,
                "planes": planes,
                "include_archived": include_archived,
                "state_filter": state_filter,
            }
        )
        return self._response


@pytest.mark.asyncio
async def test_musubi_search_uses_tenant_wildcard_namespace(agent):
    """`musubi_search` must use `<tenant>/*/episodic` so cross-channel
    recall works (per Musubi ADR 0031). A regression to the agent's own
    channel breaks the multimodality contract — phone Nyla would stop
    seeing Openclaw-Nyla's deliberate stores."""
    stub = _StubClient(response={"results": []})
    agent._musubi_v2_client = lambda: stub
    # Force a known 2-segment presence so the test isn't sensitive to fixture defaults.
    agent.config = AgentConfig(
        agent_name="nyla",
        memory_agent_tag="nyla-voice",
        discord_room="channel:0",
        musubi_v2_namespace="nyla/voice",
        musubi_v2_presence="nyla/voice",
    )

    await _unwrap(MemoryToolsMixin.musubi_search)(agent, query="prank", limit=5)

    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["namespace"] == "nyla/*/episodic"


@pytest.mark.asyncio
async def test_musubi_search_passes_state_filter_for_fresh_save_recall(agent):
    """The whole point of musubi_search is recalling a deliberate
    memory_store BEFORE the maturation cron runs (otherwise voice-Nyla
    can't remember what Openclaw-Nyla just saved). Asserts state_filter
    explicitly includes `provisional` so fresh stores are visible."""
    stub = _StubClient(response={"results": []})
    agent._musubi_v2_client = lambda: stub
    agent.config = AgentConfig(
        agent_name="nyla",
        memory_agent_tag="nyla-voice",
        discord_room="channel:0",
        musubi_v2_namespace="nyla/voice",
        musubi_v2_presence="nyla/voice",
    )

    await _unwrap(MemoryToolsMixin.musubi_search)(agent, query="anything", limit=5)

    call = stub.calls[0]
    assert call["state_filter"] == ["provisional", "matured", "promoted"]
    # Mode "deep" — recall waits on full hybrid + rerank for best hit.
    assert call["mode"] == "deep"


@pytest.mark.asyncio
async def test_musubi_search_returns_origin_channel_in_each_row(agent):
    """Result rows must surface their concrete stored namespace's
    presence segment so the LLM can attribute "you told me on Openclaw"
    vs "on the call". Without this, channel provenance is lost in
    rendering even though the API preserves it."""
    stub = _StubClient(
        response={
            "results": [
                {
                    "object_id": "a" * 27,
                    "score": 0.9,
                    "plane": "episodic",
                    "content": "the cocoa-pods prank",
                    "namespace": "nyla/openclaw/episodic",
                },
            ],
        },
    )
    agent._musubi_v2_client = lambda: stub
    agent.config = AgentConfig(
        agent_name="nyla",
        memory_agent_tag="nyla-voice",
        discord_room="channel:0",
        musubi_v2_namespace="nyla/voice",
        musubi_v2_presence="nyla/voice",
    )

    rendered = await _unwrap(MemoryToolsMixin.musubi_search)(agent, query="prank")
    assert "[openclaw]" in rendered, rendered
    assert "cocoa-pods prank" in rendered, rendered
