"""MemoryToolsMixin — musubi_recent, musubi_search, memory_store (canonical-API backed)."""

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
_MAX_SEARCH_LIMIT = 10
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

    def _own_episodic_namespace(self) -> str | None:
        """Resolve this agent's own episodic namespace.

        Uses ``config.musubi_v2_namespace`` (documented as the
        namespace-scoping field) and appends ``/episodic``. Falls
        back to ``config.musubi_v2_presence`` for backward compat
        with configs that set presence but not namespace, then to
        ``eric/<agent_name>/episodic``.

        Returns ``None`` when the config prefix is malformed (not
        2-segment), matching ``MusubiVoiceToolsMixin._ns()``
        degradation behavior.
        """
        prefix = self.config.musubi_v2_namespace or self.config.musubi_v2_presence
        if not prefix:
            prefix = f"eric/{self.config.agent_name}"
        segments = prefix.split("/")
        if len(segments) != 2:
            logger.warning(
                "musubi_v2_namespace/presence %r is not 2-segment; episodic namespace will degrade",
                prefix,
            )
            return None
        return f"{prefix}/episodic"

    def _tenant_wildcard_episodic_namespace(self) -> str | None:
        """Resolve a tenant-wide wildcard namespace for cross-channel search.

        Per Musubi ADR 0031: ``<tenant>/*/episodic`` fans an episodic
        retrieve across every channel the tenant has captured into. For
        Nyla on the voice channel that means voice + openclaw + discord
        + any future surface — all read in one call. The agent still
        knows where each row came from because every result row carries
        its concrete stored namespace.

        Returns ``None`` when the agent's namespace is malformed (same
        degradation path as :meth:`_own_episodic_namespace`).
        """
        prefix = self.config.musubi_v2_namespace or self.config.musubi_v2_presence
        if not prefix:
            prefix = f"eric/{self.config.agent_name}"
        segments = prefix.split("/")
        if len(segments) != 2:
            logger.warning(
                "musubi_v2_namespace/presence %r is not 2-segment; tenant-wide search will degrade",
                prefix,
            )
            return None
        tenant = segments[0]
        return f"{tenant}/*/episodic"

    async def _scroll_episodic(
        self,
        namespace: str,
        cutoff: float,
        need: int,
        *,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Paginate ``GET /v1/episodic`` until we have ``need`` rows
        newer than ``cutoff`` or pages/cursors are exhausted.

        Returns a list already sorted descending by ``created_epoch``.
        """
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        client = self._musubi_v2_client()
        page_size = min(need * _SCROLL_MULTIPLIER, 500)

        for _ in range(max_pages):
            page = await client.list_episodic(
                namespace=namespace,
                limit=page_size,
                cursor=cursor,
            )
            items = page.get("items") or []
            for r in items:
                if (r.get("created_epoch") or 0) >= cutoff:
                    rows.append(r)
            cursor = page.get("next_cursor")
            if not cursor:
                break

        rows.sort(key=lambda r: r.get("created_epoch") or 0, reverse=True)
        return rows

    async def fetch_recent_context(self, hours: int = 24, limit: int = 10) -> str:
        """Plain-async fetch of recent memories from this agent's own namespace.

        Exposed without ``@function_tool`` so ``on_enter`` can prefetch
        deterministically before the LLM gets a chance to skip the tool.

        Strategy: paginate ``GET /v1/episodic`` (follow ``next_cursor``
        until we have enough), filter client-side by
        ``created_epoch > now - hours``, sort descending, format.
        The endpoint doesn't natively time-filter, so we over-fetch
        and trim.
        """
        trace(f"fetch_recent_context hours={hours} limit={limit}")
        hours = max(1, min(hours, _MAX_RECENT_HOURS))
        limit = max(1, min(limit, _MAX_RECENT_LIMIT))
        cutoff = time.time() - (hours * 3600)
        namespace = self._own_episodic_namespace()
        if namespace is None:
            return _DEGRADED_LOOKUP

        try:
            rows = await self._scroll_episodic(namespace, cutoff, limit)
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

        top = rows[:limit]
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
    async def musubi_search(self, query: str, limit: int = 5) -> str:
        """Semantic-search your memory across every channel you've spoken on.

        Invocation Condition: Invoke this tool when the user asks about
        a SPECIFIC topic, fact, or event you might know about — anything
        that isn't just "what did we talk about recently". Examples:
        "Do you remember the prank we discussed?", "What do you know
        about the dentist appointment?", "Did I tell you about the
        Stable Diffusion update?", "What's the deploy plan you saved?"

        Unlike musubi_recent (which is your VOICE channel only, last
        24h), this searches across voice + Openclaw + Discord + every
        other surface you exist on. If the user told Openclaw-you to
        remember something, THIS is the tool that finds it on a phone
        call. Each result row carries its origin namespace so you can
        say "we talked about that on Openclaw" vs "on our last call".

        You MUST call this tool when answering recall questions. Saying
        "I remember…" without calling this tool is hallucination.

        Args:
            query: What you're searching for. Plain English; the server
                runs hybrid + rerank.
            limit: Max rows to return (default 5).
        """
        trace(f"tool=musubi_search query={query[:60]!r} limit={limit}")
        if not query.strip():
            return "Error: query is required."
        limit = max(1, min(limit, _MAX_SEARCH_LIMIT))

        namespace = self._tenant_wildcard_episodic_namespace()
        if namespace is None:
            return _DEGRADED_LOOKUP

        try:
            response = await self._musubi_v2_client().retrieve(
                namespace=namespace,
                query_text=query,
                mode="deep",
                limit=limit,
            )
        except (MusubiV2TimeoutError, MusubiV2ServerError) as err:
            logger.warning("musubi_search: transient %s", err)
            return _DEGRADED_LOOKUP
        except MusubiV2AuthError as err:
            logger.error("musubi_search: auth failure: %s", err)
            return _DEGRADED_LOOKUP
        except MusubiV2ClientError as err:
            logger.error("musubi_search: bad request: %s", err)
            return _DEGRADED_LOOKUP
        except MusubiV2Error as err:
            logger.warning("musubi_search: %s", err)
            return _DEGRADED_LOOKUP

        rows = response.get("results") or []
        if not rows:
            return "No memories matched."
        return "\n\n".join(_format_search_row(r) for r in rows)

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
        if namespace is None:
            return _DEGRADED_STORE
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


def _format_search_row(row: dict[str, Any]) -> str:
    """One-line render for a retrieve hit. Surfaces the row's origin
    channel (the ``presence`` segment of the stored namespace) so the
    LLM can attribute "you told me this on Openclaw" vs "on our last
    call". Falls back to the raw namespace if the row's namespace
    isn't 3-segment for any reason."""
    ns = row.get("namespace") or ""
    parts = ns.split("/")
    channel = parts[1] if len(parts) >= 2 else ns or "?"
    content = (row.get("content") or "").strip()
    return f"[{channel}] {content}"


__all__ = ["MemoryToolsMixin"]
