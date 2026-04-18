"""Party voice agent — chained STT/LLM/TTS, the Harem World line.

Registers as "phone-party" with LiveKit. Uses separate components:
  - STT: OpenAI Whisper-1 (non-streaming, needs Silero VAD)
  - VAD: Silero (segments caller audio into utterances for Whisper)
  - LLM: Gemini 3.1 Flash Lite Preview (text model, not multimodal)
  - TTS: ElevenLabs eleven_v3

Inherits the full OpenClaw platform tool set (Core, Memory, Sessions,
Academy). memory_agent_tag defaults to ``"nyla-voice"`` because the
Harem World line is Nyla-on-chained-pipeline — same person, different
voice engine. Override when/if Party gets its own identity.

Greeting uses session.say() — Gemini text LLM rejects generate_reply()
at session start (sends tools without a preceding user turn).
"""

from __future__ import annotations

import logging
from pathlib import Path

from livekit.agents import Agent, AgentSession, JobContext, cli
from livekit.agents.beta import EndCallTool
from livekit.agents.worker import AgentServer
from livekit.plugins import elevenlabs as elevenlabs_plugin
from livekit.plugins import google as google_plugin
from livekit.plugins import openai as openai_plugin
from livekit.plugins import silero as silero_plugin

from openclaw_livekit_agent_sdk.env import load_env
from openclaw_livekit_agent_sdk.telephony import resolve_caller
from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin
from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin
from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin
from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin
from openclaw_livekit_agent_sdk.trace import trace
from openclaw_livekit_agent_sdk.transcript import wire_transcript_logging

# --- env ---------------------------------------------------------------
load_env()

logger = logging.getLogger("openclaw-livekit.agent")

# ElevenLabs voice ID (Harem World default — Nyla's voice for now).
_ELEVENLABS_VOICE_ID = "AEW6JTgnyoPaoB9zlK3S"
_ELEVENLABS_MODEL = "eleven_flash_v2_5"  # streaming-compatible; eleven_v3 doesn't support multi-stream WS
_CHAINED_LLM_MODEL = "gemini-3.1-flash-lite-preview"

# --- persona -----------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_DEFAULT_PERSONA = "You are the Harem World host on a phone call with Eric."


def _load_persona() -> str:
    path = _PROMPTS_DIR / "system.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    logger.warning("persona file not found: %s", path)
    return _DEFAULT_PERSONA


# --- agent class -------------------------------------------------------
class PartyAgent(
    CoreToolsMixin,
    MemoryToolsMixin,
    SessionsToolsMixin,
    AcademyToolsMixin,
    Agent,
):
    """Harem World agent with full OpenClaw platform tool set.

    Uses the default ``memory_agent_tag = "nyla-voice"`` since the
    Harem World line is Nyla on the chained pipeline.
    """

    def __init__(
        self,
        *,
        caller_from: str | None = None,
        instructions: str = "",
        extra_tools: list | None = None,
    ) -> None:
        super().__init__(instructions=instructions, tools=extra_tools or None)
        self._caller_from: str | None = caller_from


# --- server + session --------------------------------------------------
server = AgentServer(port=8083)


@server.rtc_session(agent_name="phone-party")
async def entrypoint(ctx: JobContext) -> None:
    logger.info("phone-party entrypoint: room=%s", ctx.room.name)
    trace(f"entrypoint room={ctx.room.name}")

    await ctx.connect()

    caller = await resolve_caller(ctx)
    caller_from = caller.caller_from
    call_sid = caller.call_id
    logger.info(
        "phone-party caller resolved: from=%s call_id=%s source=%s",
        caller_from, call_sid, caller.source,
    )
    trace(f"caller source={caller.source} from={caller_from!r} call_id={call_sid!r}")

    stt = openai_plugin.STT(model="whisper-1", language="en")

    vad = silero_plugin.VAD.load(
        min_speech_duration=0.1,
        min_silence_duration=0.65,
        prefix_padding_duration=0.4,
    )

    llm = google_plugin.LLM(model=_CHAINED_LLM_MODEL, temperature=0.8)

    tts = elevenlabs_plugin.TTS(
        voice_id=_ELEVENLABS_VOICE_ID,
        model=_ELEVENLABS_MODEL,
        language="en",
    )

    extra_tools = [
        EndCallTool(
            delete_room=True,
            end_instructions="Say a brief, warm goodbye to Eric.",
        ),
    ]

    agent = PartyAgent(
        instructions=_load_persona(),
        caller_from=caller_from,
        extra_tools=extra_tools,
    )

    session = AgentSession(stt=stt, vad=vad, llm=llm, tts=tts)
    await session.start(agent=agent, room=ctx.room)
    trace("party session: silero-vad -> whisper-1 -> gemini-3.1-flash-lite -> elevenlabs")

    transcript_sid = call_sid
    if not transcript_sid and ctx.room.name.startswith("phone-"):
        transcript_sid = ctx.room.name[len("phone-"):]
    wire_transcript_logging(session, transcript_sid)

    await session.say("Hey Eric, what's up?")
    trace("party: sent canned greeting via session.say()")


if __name__ == "__main__":
    cli.run_app(server)
