"""Shared setup for Nyla voice and text agents.

Everything that must be identical between phone-nyla (voice) and
phone-nyla-text (text-only): model, tools, persona, agent class.
"""

from __future__ import annotations

import logging
from pathlib import Path

from livekit.agents import Agent
from livekit.agents.beta import EndCallTool
from google.genai import types as genai_types
from livekit.plugins import google as google_plugin
from livekit.plugins.google.tools import GoogleSearch

from openclaw_livekit_agent_sdk.config import AgentConfig
from openclaw_livekit_agent_sdk.constants import NYLA_DISCORD_ROOM
from openclaw_livekit_agent_sdk.env import load_env
from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin
from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin
from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin
from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin

logger = logging.getLogger("openclaw-livekit.agent")

# --- env ---------------------------------------------------------------
_env_loaded = False


def load_env_once() -> None:
    global _env_loaded
    if not _env_loaded:
        load_env()
        _env_loaded = True


# --- persona -----------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_DEFAULT_PERSONA = "You are Nyla, a voice assistant on a phone call with Eric."


def load_persona() -> str:
    path = _PROMPTS_DIR / "system.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    logger.warning("persona file not found: %s", path)
    return _DEFAULT_PERSONA


# --- agent class -------------------------------------------------------

#: Nyla's operational identity. Household router — no delegation
#: restrictions, delegated work posts to her own Discord room.
NYLA_CONFIG = AgentConfig(
    agent_name="nyla",
    memory_agent_tag="nyla-voice",
    discord_room=NYLA_DISCORD_ROOM,
    allowed_delegation_targets=None,
)


class NylaAgent(
    CoreToolsMixin,
    MemoryToolsMixin,
    SessionsToolsMixin,
    AcademyToolsMixin,
    Agent,
):
    """Nyla with all OpenClaw platform tools."""

    config = NYLA_CONFIG

    def __init__(
        self,
        *,
        caller_from: str | None = None,
        instructions: str = "",
        extra_tools: list | None = None,
    ) -> None:
        super().__init__(instructions=instructions, tools=extra_tools or None)
        self._caller_from: str | None = caller_from

    async def on_enter(self) -> None:
        # Prefetch recent household context deterministically. The prompt
        # used to ask the model to call musubi_recent first thing, but
        # Gemini skips it often enough that Eric would get greetings with
        # no awareness of what happened overnight. Fold a compact summary
        # into the greeting instruction so it's guaranteed to be there.
        try:
            context = await self.fetch_recent_context(hours=24, limit=10)
        except Exception as err:
            logger.warning("on_enter: startup context fetch failed: %s", err)
            context = ""

        if context and context not in {"No recent memories found.",
                                       "Memory lookup timed out."}:
            instructions = (
                "Greet Eric warmly and casually in one sentence. "
                "Use the recent household context below only if something "
                "there is worth picking up on — otherwise just say hi.\n\n"
                f"Recent household context:\n{context}"
            )
        else:
            instructions = "Greet Eric warmly and casually in one sentence."

        await self.session.generate_reply(instructions=instructions)


# --- model + tools (shared) -------------------------------------------

def build_model() -> google_plugin.realtime.RealtimeModel:
    """Gemini 2.5 Flash Native Audio — identical for voice and text."""
    # VAD tuning notes (see project_livekit_agent_status memory):
    # - start=HIGH: commit to user speech faster (reduces barge-in lag).
    # - end=LOW: explicit; don't end user turn eagerly on pauses.
    # - prefix_padding_ms=200: quick speech-onset commit.
    # - silence_duration_ms=1000: Eric can pause up to 1s mid-thought
    #   without Gemini ending his turn.
    return google_plugin.realtime.RealtimeModel(
        model="gemini-2.5-flash-native-audio-latest",
        voice="Leda",
        realtime_input_config=genai_types.RealtimeInputConfig(
            automatic_activity_detection=genai_types.AutomaticActivityDetection(
                start_of_speech_sensitivity=genai_types.StartSensitivity.START_SENSITIVITY_HIGH,
                end_of_speech_sensitivity=genai_types.EndSensitivity.END_SENSITIVITY_LOW,
                prefix_padding_ms=200,
                silence_duration_ms=1000,
            ),
        ),
    )


def build_tools() -> list:
    """Tool set — identical for voice and text."""
    return [
        EndCallTool(
            delete_room=True,
            end_instructions="Say a brief, warm goodbye to Eric.",
        ),
        GoogleSearch(),
    ]
