"""Shared setup for the Aoi voice agent.

Mirrors the structure of openclaw-livekit-agent-nyla/src/_shared.py so
the two agents stay in lockstep until Aoi gets her own specialized
configuration. When Aoi diverges (her own model tuning, her own tools,
her own persona quirks), this is the file that changes — the rest of
agent.py stays generic.
"""

from __future__ import annotations

import logging
from pathlib import Path

from livekit.agents import Agent
from livekit.agents.beta import EndCallTool
from google.genai import types as genai_types
from livekit.plugins import google as google_plugin
from livekit.plugins.google.tools import GoogleSearch

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
_DEFAULT_PERSONA = "You are Aoi, a voice assistant on a phone call with Eric."


def load_persona() -> str:
    path = _PROMPTS_DIR / "system.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    logger.warning("persona file not found: %s", path)
    return _DEFAULT_PERSONA


# --- agent class -------------------------------------------------------
class AoiAgent(
    CoreToolsMixin,
    MemoryToolsMixin,
    SessionsToolsMixin,
    AcademyToolsMixin,
    Agent,
):
    """Aoi with all OpenClaw platform tools."""

    # Memories stored during Aoi's calls are tagged as hers, not Nyla's.
    memory_agent_tag = "aoi-voice"

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
        await self.session.generate_reply(
            instructions="Greet Eric warmly and casually."
        )


# --- model + tools (shared) -------------------------------------------

def build_model() -> google_plugin.realtime.RealtimeModel:
    """Gemini 2.5 Flash Native Audio — same VAD tuning as Nyla; Kore voice for contrast."""
    # VAD tuning (see project_livekit_agent_status memory):
    # - start=HIGH: commit to user speech faster (reduces barge-in lag).
    # - end=LOW: explicit; don't end user turn eagerly on pauses.
    # - prefix_padding_ms=200: quick speech-onset commit.
    # - silence_duration_ms=1000: Eric can pause up to 1s mid-thought
    #   without Gemini ending his turn.
    # Voice = Kore (firm/clear), differentiated from Nyla's Leda (warm/soft)
    # so Eric can hear which agent he's reached.
    return google_plugin.realtime.RealtimeModel(
        model="gemini-2.5-flash-native-audio-latest",
        voice="Kore",
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
    """Tool set — same as Nyla until Aoi gets specialized tools."""
    return [
        EndCallTool(
            delete_room=True,
            end_instructions="Say a brief, warm goodbye to Eric.",
        ),
        GoogleSearch(),
    ]
