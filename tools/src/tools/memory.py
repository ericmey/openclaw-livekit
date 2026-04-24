"""MemoryToolsMixin — musubi_recent, memory_store."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import aiohttp
from livekit.agents import Agent, function_tool
from sdk.config import NYLA_DEFAULT_CONFIG, AgentConfig
from sdk.musubi_client import (
    MUSUBI_COLLECTION,
    MUSUBI_TIMEOUT_S,
    async_embed_text,
    qdrant_url,
)
from sdk.trace import trace

logger = logging.getLogger("openclaw-livekit.agent")

# Shared TCP connector for Qdrant calls — avoids TCP handshake per request
# while keeping sessions scoped to individual requests (no cross-event-loop
# or unclosed-session issues). The connector is closed at process exit.
_qdrant_connector: aiohttp.TCPConnector | None = None


def _shared_qdrant_connector() -> aiohttp.TCPConnector:
    global _qdrant_connector
    if _qdrant_connector is None or _qdrant_connector.closed:
        _qdrant_connector = aiohttp.TCPConnector(limit=10)
    return _qdrant_connector


# Connector cleanup: TCPConnector.close() may be typed as async in some
# aiohttp stub versions. We skip atexit cleanup — the OS reclaims sockets
# on process exit, and per-request sessions (which reference this connector)
# are properly closed after each call.


class MemoryToolsMixin(Agent):
    """Provides musubi_recent and memory_store tools.

    Reads the voice identity from ``self.config.memory_agent_tag`` so
    stored memories land in the right bucket per speaker. Concrete agents
    build an ``AgentConfig`` and set ``self.config`` before calling
    ``super().__init__()``. If no config is set, the SDK-level default
    (Nyla) applies — safe fallback, matches pre-AgentConfig behavior.
    """

    #: Class-level fallback. Instance-level ``self.config`` set by the
    #: concrete agent takes precedence. Keeping a class default means
    #: agents that forget to set one still behave sanely.
    config: AgentConfig = NYLA_DEFAULT_CONFIG

    async def fetch_recent_context(self, hours: int = 24, limit: int = 10) -> str:
        """Plain-async fetch of recent household memories.

        This is the same logic as the ``musubi_recent`` tool, exposed
        without the ``@function_tool`` wrapper so agent code can prefetch
        context deterministically at ``on_enter`` time — before the LLM
        gets a chance to skip calling the tool.
        """
        trace(f"fetch_recent_context hours={hours} limit={limit}")
        cutoff_epoch = time.time() - (hours * 3600)
        body: dict[str, Any] = {
            "filter": {
                "must": [
                    {
                        "key": "created_epoch",
                        "range": {"gte": cutoff_epoch},
                    }
                ]
            },
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
            "order_by": {"key": "created_epoch", "direction": "desc"},
        }

        try:
            timeout = aiohttp.ClientTimeout(total=MUSUBI_TIMEOUT_S)
            async with aiohttp.ClientSession(
                connector=_shared_qdrant_connector(),
                timeout=timeout,
            ) as http:
                async with http.post(
                    f"{qdrant_url()}/collections/{MUSUBI_COLLECTION}/points/scroll",
                    json=body,
                ) as resp:
                    if resp.status != 200:
                        text = (await resp.text())[:160]
                        logger.warning("musubi_recent: qdrant %d: %s", resp.status, text)
                        return f"Couldn't check memory — Qdrant returned {resp.status}."
                    data = await resp.json()
        except TimeoutError:
            logger.warning("musubi_recent: qdrant timed out (%.0fms)", MUSUBI_TIMEOUT_S * 1000)
            return "Couldn't check memory — Qdrant didn't respond in time."
        except Exception as err:
            logger.warning("musubi_recent: %s", err)
            return f"Couldn't check memory — Qdrant lookup failed: {err}"

        points = (data.get("result") or {}).get("points") or []
        if not points:
            return "No recent memories found."

        lines: list[str] = []
        for p in points:
            payload = p.get("payload") or {}
            agent_name = payload.get("agent") or "?"
            content = payload.get("content") or ""
            lines.append(f"[{agent_name}] {content}")
        return "\n\n".join(lines)

    @function_tool
    async def musubi_recent(self, hours: int = 24, limit: int = 10) -> str:
        """Fetch recent memories from all agents in the household.

        Invocation Condition: Invoke this tool whenever the user asks
        about recent activity, what agents have been doing, what you
        talked about before, or what's been going on. Examples: "What's
        everyone been up to?", "What did we talk about yesterday?",
        "How's the house?" You MUST call this tool before making any
        claims about recent agent activity or past conversations.

        Start-of-call context is already injected into your instructions
        by the runtime — you don't need to call this tool just to greet.

        Args:
            hours: How many hours back to look (default 24, max 72).
            limit: Maximum number of memories to return (default 10, max 20).
        """
        return await self.fetch_recent_context(hours=hours, limit=limit)

    @function_tool
    async def memory_store(self, content: str, tags: list[str] | None = None) -> str:
        """Store a memory to Musubi for future recall between calls.

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

        tag_list = tags or []
        agent_name = self.config.memory_agent_tag

        try:
            vector = await async_embed_text(content)
        except Exception as err:
            logger.error("memory_store: embedding failed: %s", err)
            trace(f"tool=memory_store EMBED_FAIL {err}")
            return "Memory didn't save — embeddings service is unavailable."

        ts = datetime.now(UTC)
        point_id = str(uuid.uuid4())
        payload = {
            "content": content,
            "type": "user",
            "agent": agent_name,
            "tags": tag_list,
            "context": "",
            "created_at": ts.isoformat(),
            "created_epoch": ts.timestamp(),
            "updated_at": ts.isoformat(),
            "updated_epoch": ts.timestamp(),
            "access_count": 0,
        }

        body = {
            "points": [
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": payload,
                }
            ]
        }

        try:
            # Writes need a longer timeout than reads — Qdrant may need to
            # flush to disk. Use 2s while still sharing the connection pool.
            timeout = aiohttp.ClientTimeout(total=2)
            async with aiohttp.ClientSession(
                connector=_shared_qdrant_connector(),
                timeout=timeout,
            ) as http:
                async with http.put(
                    f"{qdrant_url()}/collections/{MUSUBI_COLLECTION}/points",
                    json=body,
                    params={"wait": "true"},
                ) as resp:
                    if resp.status not in (200, 201):
                        text = (await resp.text())[:160]
                        logger.error("memory_store: qdrant %d: %s", resp.status, text)
                        return f"Memory didn't save — Qdrant returned {resp.status}."
        except TimeoutError:
            logger.warning("memory_store: qdrant timed out")
            return "Memory didn't save — Qdrant didn't respond in time."
        except Exception as err:
            logger.error("memory_store: %s", err)
            return f"Memory didn't save — Qdrant write failed: {err}"

        trace(f"tool=memory_store DONE id={point_id}")
        return "Got it, stored."
