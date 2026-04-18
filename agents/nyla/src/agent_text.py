"""Nyla text-only agent — same model, tools, persona as phone-nyla.

Registers as "phone-nyla-text" with LiveKit. Audio I/O disabled so the
text simulator can drive conversations for isolated LLM + tool validation.
If text works and voice doesn't, the bug is in the audio path.
"""

from __future__ import annotations

import logging

from _shared import NylaAgent, build_model, build_tools, load_env_once, load_persona
from livekit.agents import AgentSession, JobContext, cli
from livekit.agents.voice.room_io import RoomOptions
from livekit.agents.worker import AgentServer
from sdk.telemetry import wire_telemetry_capture
from sdk.telephony import resolve_caller
from sdk.trace import trace
from sdk.transcript import wire_transcript_logging

# --- env ---------------------------------------------------------------
load_env_once()

logger = logging.getLogger("openclaw-livekit.agent")

# --- server + session --------------------------------------------------
server = AgentServer(port=8084)  # 8083 is reserved for phone-party


@server.rtc_session(agent_name="phone-nyla-text")
async def entrypoint_text(ctx: JobContext) -> None:
    """Text-only variant — same model, same tools, no audio I/O."""
    logger.info("phone-nyla-text entrypoint: room=%s", ctx.room.name)
    trace(f"entrypoint-text room={ctx.room.name}")

    await ctx.connect()

    caller = await resolve_caller(ctx)
    caller_from = caller.caller_from
    call_sid = caller.call_id
    logger.info(
        "phone-nyla-text caller resolved: from=%s call_id=%s source=%s",
        caller_from,
        call_sid,
        caller.source,
    )
    trace(f"caller-text source={caller.source} from={caller_from!r} call_id={call_sid!r}")

    agent = NylaAgent(
        instructions=load_persona(),
        caller_from=caller_from,
        extra_tools=build_tools(),
    )

    session = AgentSession(llm=build_model())
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=RoomOptions(
            audio_input=False,
            audio_output=False,
        ),
    )

    transcript_sid = call_sid
    if not transcript_sid and ctx.room.name.startswith("sim-"):
        transcript_sid = ctx.room.name[len("sim-") :]
    wire_transcript_logging(session, transcript_sid)
    wire_telemetry_capture(session, transcript_sid, agent_name="phone-nyla-text")

    trace(f"text session started room={ctx.room.name}")


if __name__ == "__main__":
    cli.run_app(server)
