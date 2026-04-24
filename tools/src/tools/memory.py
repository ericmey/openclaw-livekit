"""MemoryToolsMixin — musubi_recent, memory_store (canonical-API backed)."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from livekit.agents import Agent, function_tool
from sdk.config import NYLA_DEFAULT_CONFIG, AgentConfig
from sdk.musubi_v2_client import (
    MusubiV2AuthError,
    MusubiV2Client,
    MusubiV2ClientConfig,
    MusubiV2ClientError,
    MusubiV2Error,
    MusubiV2ServerError,
    MusubiV2TimeoutError,
)
from sdk.trace import trace

logger = logging.getLogger("openclaw-livekit.agent")

_DEGRADED_LOOKUP = "Couldn't check memory — Musubi is unavailable right now."
_DEGRADED_STORE = "Memory didn't save — Musubi is unavailable right now."
_MAX_RECENT_LIMIT = 20
_MAX_RECENT_HOURS = 72
_SCROLL_MULTIPLIER = 5


class MemoryToolsMixin(Agent):
    """Provides ``musubi_recent`` and ``memory_store`` tools.

    Per-agent scope: each agent reads and writes only its own episodic
    namespace (``eric/<agent>/episodic``). Cross-agent "what's been
    going on" is a separate concern — see ``HouseholdToolsMixin``.

    Reads:
      - ``self.config.musubi_v2_presence`` — resolves the 3-segment
        namespace ``<presence>/episodic``. Falls back to
        ``eric/<agent_name>/episodic`` when unset so existing configs
        work without an explicit presence.
      - ``MUSUBI_V2_BASE_URL`` / ``MUSUBI_V2_TOKEN`` env.
    """

    config: AgentConfig = NYLA_DEFAULT_CONFIG

    def _musubi_v2_client(self) -> MusubiV2Client:
        """One place to construct the client so tests can monkeypatch."""
        return MusubiV2Client(config=MusubiV2ClientConfig.from_env())

    def _own_episodic_namespace(self) -> str:
        """Resolve this agent's own episodic namespace.

        Prefers ``config.musubi_v2_presence`` (2-segment presence like
        ``eric/nyla``) and appends ``/episodic``. Falls back to
        ``eric/<agent_name>/episodic`` so an agent without explicit
        v2 config still lands writes in a coherent namespace.
        """
        presence = self.config.musubi_v2_presence or f"eric/{self.config.agent_name}"
        return f"{presence}/episodic"

    async def fetch_recent_context(self, hours: int = 24, limit: int = 10) -> str:
        """Plain-async fetch of recent memories from this agent's own namespace.

        Exposed without ``@function_tool`` so ``on_enter`` can prefetch
        deterministically before the LLM gets a chance to skip the tool.

        Strategy: list the namespace (up to a generous cap), filter
        client-side by ``created_epoch > now - hours``, sort descending
        by ``created_epoch``, format. ``GET /v1/episodic`` doesn't
        natively time-filter, so we over-fetch and trim.
        """
        trace(f"fetch_recent_context hours={hours} limit={limit}")
        hours = max(1, min(hours, _MAX_RECENT_HOURS))
        limit = max(1, min(limit, _MAX_RECENT_LIMIT))
        cutoff = time.time() - (hours * 3600)
        namespace = self._own_episodic_namespace()

        try:
            page = await self._musubi_v2_client().list_episodic(
                namespace=namespace,
                limit=min(limit * _SCROLL_MULTIPLIER, 500),
            )
        except (MusubiV2TimeoutError, MusubiV2ServerError) as err:
            logger.warning("musubi_recent: transient %s", err)
            return _DEGRADED_LOOKUP
        except MusubiV2AuthError as err:
            logger.error("musubi_recent: auth failure: %s", err)
            return _DEGRADED_LOOKUP
        except MusubiV2ClientError as err:
            logger.error("musubi_recent: bad request: %s", err)
            return _DEGRADED_LOOKUP
        except MusubiV2Error as err:
            logger.warning("musubi_recent: %s", err)
            return _DEGRADED_LOOKUP

        items = page.get("items") or []
        recent = [r for r in items if (r.get("created_epoch") or 0) >= cutoff]
        recent.sort(key=lambda r: r.get("created_epoch") or 0, reverse=True)
        top = recent[:limit]

        if not top:
            return "No recent memories found."

        return "\n\n".join(_format_row(r) for r in top)

    @function_tool
    async def musubi_recent(self, hours: int = 24, limit: int = 10) -> str:
        """Fetch recent memories from your own episodic stream.

        Invocation Condition: Invoke this tool whenever the user asks
        about your own recent activity, what you talked about before,
        or what's been going on with you. Examples: "What did we talk
        about yesterday?", "What have you been up to?" You MUST call
        this tool before making any claims about past conversations.

        Start-of-call context is already injected into your instructions
        by the runtime — you don't need to call this tool just to greet.

        Args:
            hours: How many hours back to look (default 24, max 72).
            limit: Maximum number of memories to return (default 10, max 20).
        """
        return await self.fetch_recent_context(hours=hours, limit=limit)

    @function_tool
    async def memory_store(self, content: str, tags: list[str] | None = None) -> str:
        """Store a memory to Musubi for future recall.

        Invocation Condition: Invoke this tool whenever the user asks you
        to remember something, save something for later, or make a note.
        Also invoke proactively at the end of calls to save important
        context. Examples: "Remember I have a dentist appointment Tuesday",
        "Save that for later", "Don't forget about the deploy". You MUST
        call this tool to store the memory. Saying you'll remember it
        without calling this tool means the memory is lost.

        Args:
            content: What to remember. Write it the way you'd want to
                read it next time — natural language, not raw data.
            tags: Optional keywords for retrieval (e.g. ['joke', 'eric',
                'deploy']). Keep them short and relevant.
        """
        trace(f"tool=memory_store content={content[:60]!r} tags={tags!r}")
        if not content.strip():
            return "Error: content is required."

        tag_list = list(tags or [])
        # Route the legacy ``memory_agent_tag`` into a tag so the row
        # still carries the speaker identity — the old direct-Qdrant
        # path wrote it into ``payload.agent``; canonical doesn't have
        # that field. Tagging keeps filter parity for older queries.
        speaker_tag = self.config.memory_agent_tag
        if speaker_tag and speaker_tag not in tag_list:
            tag_list.append(speaker_tag)

        namespace = self._own_episodic_namespace()
        idem = f"livekit-memory-store:{uuid.uuid4().hex}"

        try:
            ack = await self._musubi_v2_client().capture_memory(
                namespace=namespace,
                content=content,
                tags=tag_list,
                importance=7,
                idempotency_key=idem,
            )
        except (MusubiV2TimeoutError, MusubiV2ServerError) as err:
            logger.warning("memory_store: transient %s", err)
            return _DEGRADED_STORE
        except MusubiV2AuthError as err:
            logger.error("memory_store: auth failure: %s", err)
            return "Memory didn't save — auth failed."
        except MusubiV2ClientError as err:
            logger.error("memory_store: bad request: %s", err)
            return "Memory didn't save — request rejected."
        except MusubiV2Error as err:
            logger.warning("memory_store: %s", err)
            return "Memory didn't save — unknown error."

        object_id = ack.get("object_id") or "<unknown>"
        trace(f"tool=memory_store DONE id={object_id}")
        return "Got it, stored."


def _format_row(row: dict[str, Any]) -> str:
    """One-line render for a scrolled episodic row.

    Used by ``fetch_recent_context`` and (via the shared helper in
    ``tools.household``) household status. Kept simple — LLM reads
    this, not a human in a terminal.
    """
    tags = row.get("tags") or []
    agent_tag = next(
        (t for t in tags if isinstance(t, str) and t.endswith("-voice")),
        None,
    )
    speaker = agent_tag.removesuffix("-voice") if agent_tag else (row.get("namespace") or "?")
    content = (row.get("content") or "").strip()
    return f"[{speaker}] {content}"


__all__ = ["MemoryToolsMixin"]
