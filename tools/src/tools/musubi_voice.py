"""MusubiVoiceToolsMixin — new-stack Musubi tools for voice agents.

Mirrors the three tools exposed by the `openclaw-musubi` browser plugin
(`musubi_recall`, `musubi_remember`, `musubi_think`) so a voice agent
can reach the same Musubi core as the browser extension. Different
surface (voice), same memory plane.

This mixin is **not wired into any agent's MRO today.** It exists so
we can exercise the new canonical API against a dev Musubi without
touching the live alpha path (`MemoryToolsMixin` + direct-Qdrant
`musubi_client.py`). Cutover happens by:

    1. Loading musubi.mey.house with the migrated data.
    2. Passing Musubi-side load + perf tests.
    3. Setting `AgentConfig.musubi_v2_namespace` + `MUSUBI_V2_*` env.
    4. Swapping `MemoryToolsMixin` → `MusubiVoiceToolsMixin` in the
       agent's class definition (single-line MRO change).

Until that cutover, this mixin is dormant dev surface.

Environment:

    MUSUBI_V2_BASE_URL   — default http://localhost:8100/v1
    MUSUBI_V2_TOKEN      — bearer token; required for real calls
"""

from __future__ import annotations

import asyncio
import logging
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

#: Cap on per-tool response length read aloud to the user. Keeps the
#: voice model from monologuing a 50-row retrieve dump.
_MAX_RECALL_RESULTS = 5
_DEGRADED_MESSAGE = "Couldn't reach memory right now — continuing without it."


class MusubiVoiceToolsMixin(Agent):
    """Provides ``musubi_recall``, ``musubi_remember``, ``musubi_think``
    against the new Musubi canonical API.

    Coexists with :class:`tools.memory.MemoryToolsMixin` (the alpha
    Qdrant-direct path). Only one of the two should be in an agent's
    MRO at a time; composing both would register conflicting
    `@function_tool` names.

    Reads:
      - ``self.config.musubi_v2_namespace`` — target namespace. If
        ``None``, all three tools return the degraded-mode message so
        voice calls don't block.
      - ``self.config.musubi_v2_presence`` — from-presence for thought
        sends. Defaults to ``eric/<agent_name>`` if ``None``.
      - ``MUSUBI_V2_BASE_URL`` / ``MUSUBI_V2_TOKEN`` env.
    """

    #: Class-level fallback. Concrete agents set their own
    #: ``config = AgentConfig(...)`` class attribute, same as the
    #: established pattern in `tools/memory.py`.
    config: AgentConfig = NYLA_DEFAULT_CONFIG

    def _musubi_v2_client(self) -> MusubiV2Client:
        """One place to construct the client so tests can monkeypatch."""
        return MusubiV2Client(config=MusubiV2ClientConfig.from_env())

    def _musubi_v2_presence(self) -> str:
        """Resolve a from-presence for thought sends. Prefers an explicit
        config value; falls back to the conventional `eric/<agent>` shape."""
        if self.config.musubi_v2_presence:
            return self.config.musubi_v2_presence
        return f"eric/{self.config.agent_name}"

    def _ns(self, plane: str) -> str | None:
        """Derive a 3-segment canonical namespace from the 2-segment
        config prefix. Returns ``None`` when the prefix isn't
        configured (the mixin degrades) or when the prefix is already
        3-segment (back-compat: trust the caller)."""
        prefix = self.config.musubi_v2_namespace
        if not prefix:
            return None
        segments = prefix.split("/")
        if len(segments) == 3:
            # Back-compat with any deployment that still has an
            # explicit 3-segment value: swap the trailing plane.
            return f"{segments[0]}/{segments[1]}/{plane}"
        if len(segments) == 2:
            return f"{prefix}/{plane}"
        # Anything else (1 or 4+ segments) is malformed. Fail closed
        # so the agent reports degraded rather than blasting the server.
        logger.warning(
            "musubi_v2_namespace %r is not 2-segment tenant/presence; voice tool will degrade",
            prefix,
        )
        return None

    def _read_namespaces(self) -> list[tuple[str, str]]:
        """Resolve the (namespace, plane) targets a recall should
        fan out across. Canonical retrieve requires a 3-segment
        namespace and the stored-row filter is literal, so a single
        call can only surface hits from one plane. Fan out across
        episodic + shared curated + shared concept.

        Returns an empty list when the config prefix isn't available
        or is malformed, matching ``_ns()`` degradation behavior.
        """
        prefix = self.config.musubi_v2_namespace
        if not prefix:
            return []
        segments = prefix.split("/")
        # Same validation as _ns(): 2 or 3 segments are valid; anything
        # else (1 or 4+) is malformed — fail closed so recall degrades
        # consistently with remember/think.
        if len(segments) == 3:
            owner = segments[0]
            two_seg = f"{segments[0]}/{segments[1]}"
        elif len(segments) == 2:
            owner = segments[0]
            two_seg = prefix
        else:
            logger.warning(
                "musubi_v2_namespace %r is not 2- or 3-segment; recall will degrade",
                prefix,
            )
            return []
        return [
            (f"{two_seg}/episodic", "episodic"),
            (f"{owner}/_shared/curated", "curated"),
            (f"{owner}/_shared/concept", "concept"),
        ]

    async def recall_impl(self, query: str, limit: int = 5) -> str:
        """Plain-async body of ``musubi_recall``. Extracted so tests
        can target the helper directly without going through the
        ``@function_tool`` descriptor (which pyright cannot statically
        unwrap). Matches the separation ``fetch_recent_context`` /
        ``musubi_recent`` uses in ``memory.py``."""
        trace(f"tool=musubi_recall query={query[:60]!r} limit={limit}")
        targets = self._read_namespaces()
        if not targets:
            logger.debug("musubi_recall: no v2 namespace configured; degrading")
            return _DEGRADED_MESSAGE
        if not query.strip():
            return "Error: query is required."

        capped = max(1, min(limit, _MAX_RECALL_RESULTS))
        client = self._musubi_v2_client()

        # Canonical retrieve scopes to one namespace per call (see
        # Musubi #209). Fan out across episodic + shared curated +
        # shared concept, merge by object_id, keep the top N by
        # score. `asyncio.gather` with `return_exceptions=True` so a
        # single plane failing doesn't blank the whole recall.
        coros = [
            client.retrieve(namespace=ns, query_text=query, mode="deep", limit=capped)
            for ns, _plane in targets
        ]
        settled = await asyncio.gather(*coros, return_exceptions=True)

        successes: list[dict[str, Any]] = []
        transient = False
        for result in settled:
            if isinstance(result, (MusubiV2TimeoutError, MusubiV2ServerError)):
                logger.warning("musubi_recall: transient %s", result)
                transient = True
                continue
            if isinstance(result, MusubiV2AuthError):
                # A plane-scoped auth failure is NOT a whole-recall
                # failure — a voice token may have scope on
                # episodic + curated but not concept, and the user
                # still deserves the hits we can fetch. Log the
                # plane failure, continue, and only fall back to
                # degraded if ALL planes failed.
                logger.warning("musubi_recall: per-plane auth denied: %s", result)
                continue
            if isinstance(result, MusubiV2ClientError):
                logger.error("musubi_recall: bad request: %s", result)
                continue
            if isinstance(result, MusubiV2Error):
                logger.warning("musubi_recall: %s", result)
                continue
            if isinstance(result, BaseException):
                logger.warning("musubi_recall: unexpected %r", result)
                continue
            if isinstance(result, dict):
                successes.append(result)

        if not successes:
            # Every plane either erred or auth-denied — we have
            # nothing to return. Surface the degraded message so
            # the voice model doesn't claim "no memories" when the
            # system couldn't look.
            if transient:
                return _DEGRADED_MESSAGE
            return _DEGRADED_MESSAGE

        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for resp in successes:
            for row in resp.get("results") or []:
                oid = row.get("object_id")
                # Dedup rows with a stable id; rows without one
                # (synthetic responses, legacy fixtures) fall through
                # to the merge list as-is.
                if isinstance(oid, str):
                    if oid in seen:
                        continue
                    seen.add(oid)
                merged.append(row)

        merged.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        if not merged:
            return "No matching memories found."
        return _format_recall(merged[:capped])

    @function_tool
    async def musubi_recall(self, query: str, limit: int = 5) -> str:
        """Search Musubi memory for anything matching *query*.

        Invocation Condition: Invoke this tool whenever the user asks
        about something you might have stored before — past
        conversations, decisions, preferences, reminders. Prefer this
        over guessing. Examples: "Have we talked about this before?",
        "Remind me what Eric said about the deploy", "What do I know
        about X?". You MUST call this tool before claiming you don't
        remember something.

        Args:
            query: Natural-language search string. Describe what you're
                looking for the way Eric would — "the thing we decided
                about dentist Tuesday", not raw keywords.
            limit: Max number of results to return (default 5, max 10).
        """
        return await self.recall_impl(query=query, limit=limit)

    async def remember_impl(
        self,
        content: str,
        tags: list[str] | None = None,
        importance: int = 7,
    ) -> str:
        """Plain-async body of ``musubi_remember``."""
        trace(f"tool=musubi_remember content={content[:60]!r} tags={tags!r}")
        namespace = self._ns("episodic")
        if not namespace:
            logger.debug("musubi_remember: no v2 namespace configured; degrading")
            return _DEGRADED_MESSAGE
        if not content.strip():
            return "Error: content is required."

        importance = max(0, min(int(importance), 10))
        # Per-remember idempotency key so an LLM-level retry of the same
        # call doesn't double-capture. UUID — stable within a single
        # call, fresh across calls.
        idem = f"livekit-remember:{uuid.uuid4().hex}"

        try:
            ack = await self._musubi_v2_client().capture_memory(
                namespace=namespace,
                content=content,
                tags=tags or [],
                importance=importance,
                idempotency_key=idem,
            )
        except (MusubiV2TimeoutError, MusubiV2ServerError) as err:
            logger.warning("musubi_remember: transient %s", err)
            return "Memory didn't save — Musubi is unavailable right now."
        except MusubiV2AuthError as err:
            logger.error("musubi_remember: auth failure: %s", err)
            return "Memory didn't save — auth failed."
        except MusubiV2ClientError as err:
            logger.error("musubi_remember: bad request: %s", err)
            return "Memory didn't save — request rejected."
        except MusubiV2Error as err:
            logger.warning("musubi_remember: %s", err)
            return "Memory didn't save — unknown error."

        object_id = ack.get("object_id") or "<unknown>"
        return f"Saved. (id={object_id})"

    @function_tool
    async def musubi_remember(
        self,
        content: str,
        tags: list[str] | None = None,
        importance: int = 7,
    ) -> str:
        """Store a memory in Musubi.

        Invocation Condition: Invoke this tool whenever the user asks
        you to remember something, save something for later, or make a
        note. Also invoke proactively at the end of calls for important
        context. Examples: "Remember I have a dentist appointment
        Tuesday", "Save that for later", "Don't forget the deploy". You
        MUST call this tool — promising to remember without calling it
        means the memory is lost.

        Args:
            content: What to remember. Natural language, written the
                way you'd want to read it back.
            tags: Optional keywords (['joke', 'eric', 'deploy']).
            importance: 0-10 (default 7 — above the passive capture
                baseline of 5 to reflect "the user explicitly said so").
        """
        return await self.remember_impl(content=content, tags=tags, importance=importance)

    async def think_impl(
        self,
        to_agent: str,
        content: str,
        channel: str = "default",
    ) -> str:
        """Plain-async body of ``musubi_think``."""
        trace(f"tool=musubi_think to={to_agent!r} content={content[:60]!r} channel={channel!r}")
        namespace = self._ns("thought")
        if not namespace:
            logger.debug("musubi_think: no v2 namespace configured; degrading")
            return _DEGRADED_MESSAGE
        if not to_agent.strip():
            return "Error: to_agent is required."
        if not content.strip():
            return "Error: content is required."

        from_presence = self._musubi_v2_presence()
        to_presence = to_agent if "/" in to_agent else f"eric/{to_agent}"

        try:
            ack = await self._musubi_v2_client().send_thought(
                namespace=namespace,
                from_presence=from_presence,
                to_presence=to_presence,
                content=content,
                channel=channel,
                importance=5,
            )
        except (MusubiV2TimeoutError, MusubiV2ServerError) as err:
            logger.warning("musubi_think: transient %s", err)
            return "Thought didn't deliver — Musubi is unavailable."
        except MusubiV2AuthError as err:
            logger.error("musubi_think: auth failure: %s", err)
            return "Thought didn't deliver — auth failed."
        except MusubiV2ClientError as err:
            logger.error("musubi_think: bad request: %s", err)
            return "Thought didn't deliver — request rejected."
        except MusubiV2Error as err:
            logger.warning("musubi_think: %s", err)
            return "Thought didn't deliver — unknown error."

        object_id = ack.get("object_id") or "<unknown>"
        return f"Sent to {to_presence}. (id={object_id})"

    @function_tool
    async def musubi_think(
        self,
        to_agent: str,
        content: str,
        channel: str = "default",
    ) -> str:
        """Send a presence-to-presence thought — deliver a message to
        another agent's Musubi inbox.

        Invocation Condition: Invoke this tool whenever the user wants
        you to tell another agent something. Examples: "Tell my Claude
        Code session the deploy is done", "Let Aoi know I'm heading
        out", "Send a note to Nyla". You MUST call this tool to
        actually deliver — saying it without calling means nothing was
        sent.

        Args:
            to_agent: Recipient agent id ("aoi", "nyla", "party", or
                "claude-code", etc.). Resolved to presence
                ``eric/<to_agent>`` — a future slice can add custom
                routing via AgentConfig.
            content: The thought to deliver. Short, natural. Recipient
                reads it as if you paged them.
            channel: Channel within the recipient's inbox. Defaults to
                "default"; use "scheduler" for time-boxed reminders.
        """
        return await self.think_impl(to_agent=to_agent, content=content, channel=channel)


def _format_recall(rows: list[dict[str, Any]]) -> str:
    """Render retrieve results into a voice-friendly string. One line
    per row, plane-prefixed so the model can judge provenance."""
    lines: list[str] = []
    for row in rows:
        plane = (row.get("plane") or "memory").lower()
        content = (row.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"[{plane}] {content}")
    if not lines:
        return "No matching memories found."
    return "\n\n".join(lines)
