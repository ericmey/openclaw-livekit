"""Aoi voice agent — Gemini 2.5 Flash Native Audio, voice "Leda".

Registers as "phone-aoi" with LiveKit.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from livekit.agents import Agent, AgentSession, JobContext, cli
from livekit.agents.beta import EndCallTool
from livekit.agents.worker import AgentServer
from livekit.plugins import google as google_plugin
from livekit.plugins.google.tools import GoogleSearch

from openclaw_livekit_agent_sdk.env import load_env
from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin
from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin
from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin
from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin
from openclaw_livekit_agent_sdk.postcall import wire_postcall_review
from openclaw_livekit_agent_sdk.telemetry import wire_telemetry_capture
from openclaw_livekit_agent_sdk.trace import trace
from openclaw_livekit_agent_sdk.transcript import wire_transcript_logging

# --- env ---------------------------------------------------------------
load_env()

logger = logging.getLogger("openclaw-livekit.agent")

# --- persona -----------------------------------------------------------
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_DEFAULT_PERSONA = "You are Nyla, a voice assistant on a phone call with Eric."


def _load_persona() -> str:
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
    """Aoi with all OpenClaw platform tools (Nyla persona during testing)."""

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


# --- server + session --------------------------------------------------
server = AgentServer(port=8082)


@server.rtc_session(agent_name="phone-aoi")
async def entrypoint(ctx: JobContext) -> None:
    meta = json.loads(ctx.job.metadata or "{}") if ctx.job.metadata else {}
    caller_from = meta.get("from")
    call_sid = meta.get("callSid")

    logger.info(
        "phone-aoi entrypoint: room=%s caller=%s",
        ctx.room.name,
        caller_from,
    )
    trace(f"entrypoint room={ctx.room.name} caller={caller_from!r}")

    await ctx.connect()

    model = google_plugin.realtime.RealtimeModel(
        model="gemini-2.5-flash-native-audio-latest",
        voice="Leda",
    )

    extra_tools = [
        EndCallTool(
            delete_room=True,
            end_instructions="Say a brief, warm goodbye to Eric.",
        ),
        GoogleSearch(),
    ]

    agent = AoiAgent(
        instructions=_load_persona(),
        caller_from=caller_from,
        extra_tools=extra_tools,
    )

    session = AgentSession(llm=model)
    await session.start(agent=agent, room=ctx.room)

    transcript_sid = call_sid
    if not transcript_sid and ctx.room.name.startswith("phone-"):
        transcript_sid = ctx.room.name[len("phone-"):]
    wire_transcript_logging(session, transcript_sid)
    wire_telemetry_capture(session, transcript_sid, agent_name="phone-aoi")
    wire_postcall_review(session, transcript_sid, agent_name="phone-aoi")

    trace(f"session started room={ctx.room.name}")


if __name__ == "__main__":
    cli.run_app(server)
