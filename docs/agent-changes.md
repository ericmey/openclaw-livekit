# Agent-side code changes

Small — roughly 10-20 lines per agent. Each persona currently reads
caller info from `ctx.job.metadata` because the bridge packs it there.
Under SIP, caller info lives on the SIP participant's attributes
instead.

## What changes conceptually

### Today (bridge path)

The bridge puts this string in `ctx.job.metadata`:

```json
{"callSid": "CAxxx...", "from": "+14155551234", "to": "+14155559999"}
```

Each agent does:

```python
meta = json.loads(ctx.job.metadata or "{}")
caller_from = meta.get("from")
call_sid = meta.get("callSid")
```

### Under SIP

The dispatch rule can still set a metadata string on the room (useful
for agent routing hints), but **caller ID does not live there**. It
lives on the SIP participant's attributes:

```python
for participant in ctx.room.remote_participants.values():
    if participant.kind == rtc.ParticipantKind.SIP:
        caller_from = participant.attributes.get("sip.from")
        call_sid = participant.attributes.get("sip.callID")
        trunk_did = participant.attributes.get("sip.trunkPhoneNumber")
```

The tricky part: at `entrypoint` time the SIP participant may not have
joined yet. You need to either:

- Wait for the `participant_connected` event and resolve caller info
  there, OR
- Use a small helper that awaits the first SIP participant with a
  timeout.

## Recommended: dual-path compatibility shim in the SDK

Add a helper to
[openclaw-livekit-agent-sdk](https://github.com/ericmey/openclaw-livekit-agent-sdk)
that each agent can call. Roughly:

```python
# openclaw_livekit_agent_sdk/telephony.py (NEW FILE)
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from livekit import rtc
from livekit.agents import JobContext

logger = logging.getLogger("openclaw-livekit.telephony")


@dataclass(frozen=True)
class CallerInfo:
    call_id: str | None         # bridge: callSid / sip: sip.callID
    caller_from: str | None     # bridge: from    / sip: sip.from
    dialed_number: str | None   # bridge: to      / sip: sip.trunkPhoneNumber
    source: str                 # "bridge" | "sip"


async def resolve_caller(ctx: JobContext, timeout: float = 5.0) -> CallerInfo:
    """Resolve caller info regardless of transport (bridge vs SIP).

    Tries job.metadata first (bridge path); falls back to waiting for a
    SIP participant (SIP path).
    """
    # Path 1: bridge packs everything into metadata as JSON.
    if ctx.job.metadata:
        try:
            meta = json.loads(ctx.job.metadata)
            if "from" in meta or "callSid" in meta:
                return CallerInfo(
                    call_id=meta.get("callSid"),
                    caller_from=meta.get("from"),
                    dialed_number=meta.get("to"),
                    source="bridge",
                )
        except json.JSONDecodeError:
            logger.warning("job.metadata was not JSON: %r", ctx.job.metadata)

    # Path 2: SIP participant attributes.
    async def _wait_for_sip_participant() -> rtc.RemoteParticipant:
        while True:
            for p in ctx.room.remote_participants.values():
                if p.kind == rtc.ParticipantKind.SIP:
                    return p
            await asyncio.sleep(0.1)

    try:
        sip = await asyncio.wait_for(_wait_for_sip_participant(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("no SIP participant joined within %.1fs", timeout)
        return CallerInfo(None, None, None, source="unknown")

    return CallerInfo(
        call_id=sip.attributes.get("sip.callID"),
        caller_from=sip.attributes.get("sip.from"),
        dialed_number=sip.attributes.get("sip.trunkPhoneNumber"),
        source="sip",
    )
```

Then each persona's entrypoint changes from:

```python
meta = json.loads(ctx.job.metadata or "{}") if ctx.job.metadata else {}
caller_from = meta.get("from")
call_sid = meta.get("callSid")
```

To:

```python
from openclaw_livekit_agent_sdk.telephony import resolve_caller

caller = await resolve_caller(ctx)
caller_from = caller.caller_from
call_sid = caller.call_id
```

**Advantage:** agents keep working under both bridge and SIP during
the cutover window, no branching on env. After cutover + cleanup phase,
the bridge path in `resolve_caller()` can be deleted.

## Per-agent impact

### openclaw-livekit-agent-nyla

- `src/agent.py` — swap metadata parsing to `resolve_caller()`
- `src/agent_text.py` — same
- `src/_shared.py` — no change (doesn't touch metadata)
- Integration tests — add a SIP-path fixture that stubs a SIP participant

### openclaw-livekit-agent-aoi

- `src/agent.py` — swap metadata parsing. Same diff as Nyla minus the text variant.

### openclaw-livekit-agent-party

- `src/agent.py` — swap metadata parsing.

### openclaw-livekit-agent-sdk

- New file: `src/openclaw_livekit_agent_sdk/telephony.py` per above
- Update `__init__.py` exports
- Add tests for `resolve_caller()` — both bridge-metadata and SIP-participant paths, plus the timeout case
- Bump version in `pyproject.toml`

## Order of operations

1. Land the SDK helper on a branch, add tests — merge to main.
2. Rebuild SDK venv, cycle agents — everything still works on the
   bridge path because the helper falls through to the metadata shape.
3. Stand up SIP infrastructure + Twilio trunk per
   [MIGRATION.md](../MIGRATION.md) Phases 1-3.
4. Point a test DID at SIP, make a call. Agent resolves caller via the
   SIP branch. Log messages should confirm `source=sip`.
5. Move production DIDs over (Phase 7).

## What about extra metadata in the room?

Dispatch rules set an arbitrary `metadata` string on the room itself.
If we want to pass routing hints (e.g., "this call is VIP, use the warm
greeting") the dispatch rule can put them there. `resolve_caller()`
doesn't need to see that — handle it separately where relevant. Shape
it as JSON for consistency.
