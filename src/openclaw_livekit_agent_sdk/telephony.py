"""Transport-agnostic caller info resolver.

The OpenClaw voice stack ingests phone calls via two transports:

1. **Twilio Media Streams** (current) — the Node bridge
   (``openclaw-livekit-bridge``) packs ``{"callSid", "from", "to"}`` into
   ``ctx.job.metadata`` as a JSON string before the agent's entrypoint
   runs. Metadata is available immediately.

2. **SIP trunking** (planned) — ``livekit-sip`` creates the room and the
   caller joins as a ``SIP`` participant. Caller identity lives on
   ``participant.attributes`` keyed by ``sip.from``, ``sip.callID``,
   ``sip.trunkPhoneNumber``. The dispatch rule may additionally set a
   string on ``ctx.job.metadata``, but it will NOT have the Twilio
   bridge shape — it carries routing hints only.

``resolve_caller()`` papers over both so personas can be A/B'd across
transports without branching in their entrypoints. Call it AFTER
``await ctx.connect()`` — the SIP path needs a connected room to read
remote participants.

The ``source`` field on the returned ``CallerInfo`` records which
transport served the call. Useful for telemetry comparisons during the
A/B window.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Literal

from livekit import rtc
from livekit.agents import JobContext

logger = logging.getLogger("openclaw-livekit.telephony")

# Default wait budget for a SIP participant to show up after the agent
# joins the room. In practice SIP participants arrive before the agent
# does (livekit-sip creates the room + participant, then dispatches the
# agent), so this timeout is rarely exercised — it's just a safety net
# so the entrypoint can't hang forever on a misconfigured dispatch.
DEFAULT_SIP_WAIT_SECONDS = 5.0

CallerSource = Literal["bridge", "sip", "unknown"]


@dataclass(frozen=True)
class CallerInfo:
    """Transport-normalized caller information.

    All fields are best-effort — callers should handle ``None``
    gracefully. ``source`` is always set.
    """

    call_id: str | None
    """Unique identifier for this call.

    Bridge: Twilio's ``CallSid`` (e.g. ``CA1234...``).
    SIP: the SIP ``Call-ID`` header (e.g. a UUID-ish string).
    """

    caller_from: str | None
    """Caller's phone number in E.164, if available."""

    dialed_number: str | None
    """The DID the caller reached (the 'to' number)."""

    source: CallerSource
    """Which transport delivered this call: ``"bridge"``, ``"sip"``, or
    ``"unknown"`` (neither path produced identifying info — rare;
    logged as a warning)."""


def _parse_bridge_metadata(raw: str | None) -> CallerInfo | None:
    """Return a CallerInfo if ``raw`` looks like bridge-shape metadata, else None."""
    if not raw:
        return None
    try:
        meta = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("job.metadata was not JSON: %r", raw)
        return None
    if not isinstance(meta, dict):
        return None
    # The bridge always includes at least one of these two keys. If
    # neither is present, treat the metadata as "something else"
    # (likely a SIP dispatch rule's routing hint) and fall through.
    if "from" not in meta and "callSid" not in meta:
        return None
    return CallerInfo(
        call_id=meta.get("callSid"),
        caller_from=meta.get("from"),
        dialed_number=meta.get("to"),
        source="bridge",
    )


async def _wait_for_sip_participant(
    room: rtc.Room,
    timeout: float,
) -> rtc.RemoteParticipant | None:
    """Poll remote_participants for a SIP-kind participant.

    Returns the first one found or None on timeout. A polling loop is
    fine here: in the normal case the SIP participant is already in the
    room by the time we check, so we return on the first iteration.
    """

    async def _scan() -> rtc.RemoteParticipant:
        while True:
            for p in room.remote_participants.values():
                if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                    return p
            await asyncio.sleep(0.05)

    try:
        return await asyncio.wait_for(_scan(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


def _caller_info_from_sip_participant(
    participant: rtc.RemoteParticipant,
) -> CallerInfo:
    attrs = participant.attributes or {}
    return CallerInfo(
        call_id=attrs.get("sip.callID"),
        caller_from=attrs.get("sip.from"),
        dialed_number=attrs.get("sip.trunkPhoneNumber"),
        source="sip",
    )


async def resolve_caller(
    ctx: JobContext,
    *,
    sip_wait_seconds: float = DEFAULT_SIP_WAIT_SECONDS,
) -> CallerInfo:
    """Resolve caller info regardless of transport.

    Checks ``ctx.job.metadata`` first (bridge path). If that's empty or
    doesn't look like a bridge payload, waits for a SIP participant in
    ``ctx.room.remote_participants`` (SIP path). Falls back to an
    all-``None`` CallerInfo with ``source="unknown"`` if neither
    produces anything within ``sip_wait_seconds``.

    Call AFTER ``await ctx.connect()``.
    """
    bridge = _parse_bridge_metadata(ctx.job.metadata)
    if bridge is not None:
        return bridge

    participant = await _wait_for_sip_participant(ctx.room, sip_wait_seconds)
    if participant is not None:
        return _caller_info_from_sip_participant(participant)

    logger.warning(
        "resolve_caller: no bridge metadata and no SIP participant within %.1fs "
        "(room=%s metadata=%r)",
        sip_wait_seconds,
        ctx.room.name,
        ctx.job.metadata,
    )
    return CallerInfo(
        call_id=None,
        caller_from=None,
        dialed_number=None,
        source="unknown",
    )
