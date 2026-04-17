"""Nyla voice agent — Gemini 2.5 Flash Native Audio, voice "Leda".

Registers as "phone-nyla" with LiveKit. For the text-only test variant,
see agent_text.py (registers as "phone-nyla-text").
"""

from __future__ import annotations

import logging
from pathlib import Path

from livekit.agents import AgentSession, JobContext, cli
from livekit.agents.worker import AgentServer

from openclaw_livekit_agent_sdk.postcall import wire_postcall_review
from openclaw_livekit_agent_sdk.telemetry import wire_telemetry_capture
from openclaw_livekit_agent_sdk.telephony import resolve_caller
from openclaw_livekit_agent_sdk.trace import trace
from openclaw_livekit_agent_sdk.transcript import wire_transcript_logging

from _shared import NylaAgent, build_model, build_tools, load_env_once, load_persona

# --- env ---------------------------------------------------------------
load_env_once()

logger = logging.getLogger("openclaw-livekit.agent")

# --- server + session --------------------------------------------------
server = AgentServer(port=8081)


@server.rtc_session(agent_name="phone-nyla")
async def entrypoint(ctx: JobContext) -> None:
    logger.info("phone-nyla entrypoint: room=%s", ctx.room.name)
    trace(f"entrypoint room={ctx.room.name}")

    await ctx.connect()

    caller = await resolve_caller(ctx)
    caller_from = caller.caller_from
    call_sid = caller.call_id
    logger.info(
        "phone-nyla caller resolved: from=%s call_id=%s source=%s",
        caller_from, call_sid, caller.source,
    )
    trace(f"caller source={caller.source} from={caller_from!r} call_id={call_sid!r}")

    agent = NylaAgent(
        instructions=load_persona(),
        caller_from=caller_from,
        extra_tools=build_tools(),
    )

    session = AgentSession(llm=build_model())
    await session.start(agent=agent, room=ctx.room)

    transcript_sid = call_sid
    if not transcript_sid and ctx.room.name.startswith("phone-"):
        transcript_sid = ctx.room.name[len("phone-"):]
    wire_transcript_logging(session, transcript_sid)
    wire_telemetry_capture(session, transcript_sid, agent_name="phone-nyla")
    wire_postcall_review(session, transcript_sid, agent_name="phone-nyla")

    trace(f"session started room={ctx.room.name}")


if __name__ == "__main__":
    cli.run_app(server)
