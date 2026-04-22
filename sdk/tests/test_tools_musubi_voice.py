"""Tests for MusubiVoiceToolsMixin — new-stack Musubi voice tools.

Mirror the style of `test_tools_memory.py`: structural checks (methods
exist, tool decorators applied, config overridable), plus behavioral
tests that monkeypatch the mixin's `_musubi_v2_client` hook so no
real HTTP flies.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sdk.config import NYLA_DEFAULT_CONFIG, AgentConfig
from tools.musubi_voice import MusubiVoiceToolsMixin


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Structural — mirrors test_tools_memory.py
# ---------------------------------------------------------------------------


def test_mixin_has_musubi_recall() -> None:
    assert hasattr(MusubiVoiceToolsMixin, "musubi_recall")
    assert callable(MusubiVoiceToolsMixin.musubi_recall)


def test_mixin_has_musubi_remember() -> None:
    assert hasattr(MusubiVoiceToolsMixin, "musubi_remember")
    assert callable(MusubiVoiceToolsMixin.musubi_remember)


def test_mixin_has_musubi_think() -> None:
    assert hasattr(MusubiVoiceToolsMixin, "musubi_think")
    assert callable(MusubiVoiceToolsMixin.musubi_think)


def test_mixin_default_config_is_nyla() -> None:
    assert MusubiVoiceToolsMixin.config is NYLA_DEFAULT_CONFIG


def test_mixin_config_is_overridable_with_v2_fields() -> None:
    aoi_cfg = AgentConfig(
        agent_name="aoi",
        memory_agent_tag="aoi-voice",
        discord_room="channel:0",
        musubi_v2_namespace="eric/aoi-voice/episodic",
        musubi_v2_presence="eric/aoi",
    )

    class _AoiV2Tools(MusubiVoiceToolsMixin):
        config = aoi_cfg

    assert _AoiV2Tools.config.musubi_v2_namespace == "eric/aoi-voice/episodic"
    assert _AoiV2Tools.config.musubi_v2_presence == "eric/aoi"
    # Parent class unaffected.
    assert MusubiVoiceToolsMixin.config.musubi_v2_namespace is None


# ---------------------------------------------------------------------------
# Behavioral — tool-body path, with a fake client injected
# ---------------------------------------------------------------------------


class _FakeV2Client:
    """Records calls and returns canned responses; stands in for
    `MusubiV2Client` via the `_musubi_v2_client` override point."""

    def __init__(
        self,
        *,
        capture_returns: dict[str, Any] | None = None,
        retrieve_returns: dict[str, Any] | None = None,
        send_returns: dict[str, Any] | None = None,
        capture_raises: Exception | None = None,
        retrieve_raises: Exception | None = None,
        send_raises: Exception | None = None,
    ) -> None:
        self._capture_returns = capture_returns
        self._retrieve_returns = retrieve_returns
        self._send_returns = send_returns
        self._capture_raises = capture_raises
        self._retrieve_raises = retrieve_raises
        self._send_raises = send_raises
        self.captures: list[dict[str, Any]] = []
        self.retrieves: list[dict[str, Any]] = []
        self.sends: list[dict[str, Any]] = []

    async def capture_memory(self, **kwargs: Any) -> dict[str, Any]:
        self.captures.append(kwargs)
        if self._capture_raises:
            raise self._capture_raises
        return self._capture_returns or {}

    async def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.retrieves.append(kwargs)
        if self._retrieve_raises:
            raise self._retrieve_raises
        return self._retrieve_returns or {}

    async def send_thought(self, **kwargs: Any) -> dict[str, Any]:
        self.sends.append(kwargs)
        if self._send_raises:
            raise self._send_raises
        return self._send_returns or {}


def _make_instance(
    fake: _FakeV2Client,
    namespace: str | None = "eric/test-voice/episodic",
    presence: str | None = "eric/aoi",
    agent_name: str = "aoi",
) -> MusubiVoiceToolsMixin:
    """Build a mixin instance bypassing Agent.__init__ — the existing
    memory-mixin tests do the same to keep structural tests independent
    of the full LiveKit Agent construction path."""
    cfg = AgentConfig(
        agent_name=agent_name,
        memory_agent_tag=f"{agent_name}-voice",
        discord_room="channel:0",
        musubi_v2_namespace=namespace,
        musubi_v2_presence=presence,
    )
    inst = MusubiVoiceToolsMixin.__new__(MusubiVoiceToolsMixin)
    inst.config = cfg  # type: ignore[misc]
    # Override the client factory so no real HTTP goes out.
    inst._musubi_v2_client = lambda: fake  # type: ignore[method-assign]
    return inst


# ----- musubi_recall --------------------------------------------------------


def test_recall_degrades_when_namespace_is_none() -> None:
    fake = _FakeV2Client()
    inst = _make_instance(fake, namespace=None)
    out = _run(inst.recall_impl("anything"))
    assert "Couldn't reach memory" in out
    assert fake.retrieves == []


def test_recall_rejects_empty_query() -> None:
    fake = _FakeV2Client(retrieve_returns={"results": []})
    inst = _make_instance(fake)
    out = _run(inst.recall_impl("   "))
    assert out.startswith("Error:")
    assert fake.retrieves == []


def test_recall_returns_no_match_on_empty_results() -> None:
    fake = _FakeV2Client(retrieve_returns={"results": []})
    inst = _make_instance(fake)
    out = _run(inst.recall_impl("anything"))
    assert out == "No matching memories found."
    assert len(fake.retrieves) == 1


def test_recall_formats_rows_with_plane_prefix() -> None:
    fake = _FakeV2Client(
        retrieve_returns={
            "results": [
                {"plane": "curated", "content": "deploy is done"},
                {"plane": "episodic", "content": "user asked about dentist"},
            ]
        }
    )
    inst = _make_instance(fake)
    out = _run(inst.recall_impl("what happened"))
    assert "[curated] deploy is done" in out
    assert "[episodic] user asked about dentist" in out


def test_recall_caps_limit() -> None:
    fake = _FakeV2Client(retrieve_returns={"results": []})
    inst = _make_instance(fake)
    _run(inst.recall_impl("anything", limit=99))
    # Capped at _MAX_RECALL_RESULTS = 5.
    assert fake.retrieves[0]["limit"] == 5


# ----- musubi_remember ------------------------------------------------------


def test_remember_degrades_when_namespace_is_none() -> None:
    fake = _FakeV2Client()
    inst = _make_instance(fake, namespace=None)
    out = _run(inst.remember_impl("something"))
    assert "Couldn't reach memory" in out
    assert fake.captures == []


def test_remember_rejects_empty_content() -> None:
    fake = _FakeV2Client(capture_returns={"object_id": "m" * 27})
    inst = _make_instance(fake)
    out = _run(inst.remember_impl("   "))
    assert out.startswith("Error:")
    assert fake.captures == []


def test_remember_returns_id_on_success() -> None:
    fake = _FakeV2Client(capture_returns={"object_id": "m" * 27, "state": "provisional"})
    inst = _make_instance(fake)
    out = _run(inst.remember_impl("note this"))
    assert "Saved" in out
    assert "m" * 27 in out
    # Default importance = 7 for explicit remembers.
    assert fake.captures[0]["importance"] == 7


def test_remember_clamps_importance() -> None:
    fake = _FakeV2Client(capture_returns={"object_id": "m" * 27})
    inst = _make_instance(fake)
    _run(inst.remember_impl("content", importance=99))
    assert fake.captures[0]["importance"] == 10
    _run(inst.remember_impl("content", importance=-5))
    assert fake.captures[1]["importance"] == 0


def test_remember_attaches_idempotency_key() -> None:
    fake = _FakeV2Client(capture_returns={"object_id": "m" * 27})
    inst = _make_instance(fake)
    _run(inst.remember_impl("content"))
    key = fake.captures[0].get("idempotency_key")
    assert key and key.startswith("livekit-remember:")


# ----- musubi_think ---------------------------------------------------------


def test_think_degrades_when_namespace_is_none() -> None:
    fake = _FakeV2Client()
    inst = _make_instance(fake, namespace=None)
    out = _run(inst.think_impl("nyla", "hi"))
    assert "Couldn't reach memory" in out
    assert fake.sends == []


def test_think_rejects_empty_recipient_or_content() -> None:
    fake = _FakeV2Client()
    inst = _make_instance(fake)
    assert _run(inst.think_impl("", "msg")).startswith("Error:")
    assert _run(inst.think_impl("nyla", "")).startswith("Error:")
    assert fake.sends == []


def test_think_resolves_bare_agent_to_eric_prefix() -> None:
    fake = _FakeV2Client(send_returns={"object_id": "t" * 27})
    inst = _make_instance(fake)
    out = _run(inst.think_impl("nyla", "deploy done"))
    assert "Sent to eric/nyla" in out
    assert fake.sends[0]["to_presence"] == "eric/nyla"


def test_think_preserves_fully_qualified_presence() -> None:
    fake = _FakeV2Client(send_returns={"object_id": "t" * 27})
    inst = _make_instance(fake)
    _run(inst.think_impl("someone/claude-code", "deploy done"))
    assert fake.sends[0]["to_presence"] == "someone/claude-code"


def test_think_uses_configured_presence_as_from() -> None:
    fake = _FakeV2Client(send_returns={"object_id": "t" * 27})
    inst = _make_instance(fake, presence="eric/aoi")
    _run(inst.think_impl("nyla", "hi"))
    assert fake.sends[0]["from_presence"] == "eric/aoi"


def test_think_falls_back_to_agent_name_when_presence_none() -> None:
    fake = _FakeV2Client(send_returns={"object_id": "t" * 27})
    inst = _make_instance(fake, presence=None, agent_name="party")
    _run(inst.think_impl("nyla", "hi"))
    assert fake.sends[0]["from_presence"] == "eric/party"


# ----- Degraded-mode exception paths ---------------------------------------


def test_recall_returns_degraded_on_timeout() -> None:
    from sdk.musubi_v2_client import MusubiV2TimeoutError

    fake = _FakeV2Client(retrieve_raises=MusubiV2TimeoutError("slow"))
    inst = _make_instance(fake)
    out = _run(inst.recall_impl("anything"))
    assert out.startswith("Couldn't reach memory")


def test_remember_returns_auth_message_on_auth_error() -> None:
    from sdk.musubi_v2_client import MusubiV2AuthError

    fake = _FakeV2Client(capture_raises=MusubiV2AuthError("bad token"))
    inst = _make_instance(fake)
    out = _run(inst.remember_impl("content"))
    assert "auth failed" in out


def test_think_returns_unavailable_on_server_error() -> None:
    from sdk.musubi_v2_client import MusubiV2ServerError

    fake = _FakeV2Client(send_raises=MusubiV2ServerError("5xx"))
    inst = _make_instance(fake)
    out = _run(inst.think_impl("nyla", "hi"))
    assert "Musubi is unavailable" in out
