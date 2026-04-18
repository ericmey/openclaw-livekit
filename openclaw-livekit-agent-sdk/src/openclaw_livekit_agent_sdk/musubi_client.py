"""Qdrant / Musubi client — direct REST for musubi_recent and memory_store."""

from __future__ import annotations

import os

import aiohttp

# Qdrant is reached directly over localhost:6333 — no MCP, no subprocess,
# no Python client library.
QDRANT_URL = (
    f"http://{os.environ.get('QDRANT_HOST', 'localhost')}"
    f":{os.environ.get('QDRANT_PORT', '6333')}"
)
MUSUBI_COLLECTION = "musubi_memories"
MUSUBI_TIMEOUT_S = 0.5  # hard 500ms budget — same as vcr's musubi-client.ts

# Gemini embedding config for memory_store — matches musubi's embedding.py
GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-embedding-001:embedContent"
)
GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY")
    or os.environ.get("GOOGLE_API_KEY")
    or ""
)


async def async_embed_text(text: str) -> list[float]:
    """Get a Gemini embedding vector for *text* via async HTTP.

    Uses the REST API directly to stay on the async event loop — no sync
    ``google.genai`` import, no thread executor. Matches the musubi library's
    model (gemini-embedding-001) and vector size (3072).
    """
    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not api_key:
        raise RuntimeError("No GEMINI_API_KEY or GOOGLE_API_KEY in environment")
    url = f"{GEMINI_EMBED_URL}?key={api_key}"
    body = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text}]},
    }
    async with aiohttp.ClientSession() as http:
        async with http.post(
            url,
            json=body,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                err_text = (await resp.text())[:200]
                raise RuntimeError(f"Gemini embedding API {resp.status}: {err_text}")
            data = await resp.json()
    values = data.get("embedding", {}).get("values")
    if not values:
        raise RuntimeError("Gemini returned no embedding values")
    return values
