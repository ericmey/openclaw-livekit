"""Shared setup for the Aoi voice agent.

Thin wrapper around :mod:`tools.base_agent` so Aoi-specific config
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
    "AOI_CONFIG",
    "AoiAgent",
    "build_model",
    "build_tools",
    "load_env_once",
    "load_persona",
]

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

#: Aoi's operational identity. Shares Nyla's Discord room for now
#: (she doesn't have her own channel yet); swap ``discord_room`` when
#: Eric carves one out. Memory goes to the aoi-voice bucket so her
#: stored context is separable from Nyla's.
#:
#: Delegation allowlist is the tight version matching her prompt: she
#: routes research to Yumi, ops to Rin, spawns herself (``aoi``) for
#: long-running code work, hands inbox stuff to Momo, and can kick
#: things back to Nyla for household routing. Creative and image
#: work (hana, tama) is NOT on the list — her prompt says avoid
#: image/selfie unless Eric explicitly asks, and the rejection here
#: forces her to either hand to Nyla or say so plainly. Adjust as we
#: use her and find gaps.
AOI_CONFIG = AgentConfig(
    agent_name="aoi",
    memory_agent_tag="aoi-voice",
    discord_room=NYLA_DISCORD_ROOM,
    allowed_delegation_targets=frozenset(
        {
            "yumi",  # research / planning (her prompt's explicit default)
            "rin",  # ops / health checks (her prompt's explicit default)
            "aoi",  # spawn herself for long-running code work
            "momo",  # inbox / email — common technical-adjacent asks
            "nyla",  # hand back to the household router on explicit ask
        }
    ),
)


class AoiAgent(BaseRealtimeAgent):
    """Aoi with all OpenClaw platform tools."""

    config = AOI_CONFIG


def build_model():
    """Gemini 2.5 Flash Native Audio, Kore voice."""
    return build_realtime_model(voice="Kore")


build_tools = build_common_tools


def load_persona() -> str:
    """Load Aoi's persona from prompts/system.md."""
    return _load_persona(_PROMPTS_DIR)
