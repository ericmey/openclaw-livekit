"""Shared setup for Nyla voice and text agents.

Everything that must be identical between phone-nyla (voice) and
phone-nyla-text (text-only): model, tools, persona, agent class.

Thin wrapper around :mod:`tools.base_agent` so Nyla-specific config
lives here while shared scaffolding lives in one place.
"""

from __future__ import annotations

from pathlib import Path

from sdk.config import AgentConfig
from sdk.constants import NYLA_DISCORD_ROOM
from tools.base_agent import (
    BaseRealtimeAgent,
    build_common_tools,
    build_realtime_model,
    load_env_once,
)
from tools.base_agent import (
    load_persona as _load_persona,
)

__all__ = [
    "NYLA_CONFIG",
    "NylaAgent",
    "build_model",
    "build_tools",
    "load_env_once",
    "load_persona",
]

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

#: Nyla's operational identity. Household router — no delegation
#: restrictions, delegated work posts to her own Discord room.
NYLA_CONFIG = AgentConfig(
    agent_name="nyla",
    memory_agent_tag="nyla-voice",
    discord_room=NYLA_DISCORD_ROOM,
    allowed_delegation_targets=None,
)


class NylaAgent(BaseRealtimeAgent):
    """Nyla with all OpenClaw platform tools."""

    config = NYLA_CONFIG


def build_model():
    """Gemini 2.5 Flash Native Audio, Leda voice."""
    return build_realtime_model(voice="Leda")


build_tools = build_common_tools


def load_persona() -> str:
    """Load Nyla's persona from prompts/system.md."""
    return _load_persona(_PROMPTS_DIR)
