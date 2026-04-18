# Target architecture

## Why migrate

The current [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge)
uses **Twilio Media Streams**: a WebSocket that Twilio opens to a Node
process, streaming G.711 µ-law audio frames as JSON messages. The bridge
decodes, publishes to a LiveKit Room, and sends agent audio back the same
way.

This pattern is functional but **not the officially-recommended LiveKit
integration path**. The recommended path is SIP trunking.

Three concrete reasons to migrate:

1. **Known packet-drop pattern.** [livekit/agents#3379](https://github.com/livekit/agents/issues/3379)
   documents Media Streams WebSockets silently dropping audio frames
   when integrated with LiveKit. The drop is probabilistic, not reported
   in the WS protocol, and presents as agents behaving oddly (partial
   STT, bad turn-taking, random re-prompts) rather than as dropped calls.
2. **Architectural complexity we don't need.** The bridge owns the µ-law
   codec, per-call Room lifecycle, WebSocket concurrency caps, and
   audio pump goroutines. SIP offloads every one of those responsibilities
   to `livekit-sip`, which is purpose-built, battle-tested, and gets
   updates from the LiveKit team.
3. **Test coverage is easier.** Media Streams has no first-party test
   harness (confirmed via research — `@livekit/rtc-node` has no mock
   mode, and LiveKit's testing docs cover agents only). SIP has standard
   `sipp`-based testing and works with `livekit-server --dev`.

## What changes

```
BEFORE (Media Streams)                     AFTER (SIP)
─────────────────────                      ─────────────

┌────────┐                                ┌────────┐
│ Twilio │                                │ Twilio │
└───┬────┘                                └───┬────┘
    │ HTTPS webhook                           │ SIP/TCP, G.711 PCMU
    │ + μ-law WebSocket                       │
    │                                         │
    ▼                                         ▼
┌──────────────────┐                      ┌──────────────────┐
│ openclaw-livekit-│                      │ livekit-sip      │
│ bridge (Node)    │                      │ (Go binary)      │
│                  │                      │                  │
│ - HMAC verify    │                      │ - SIP INVITE     │
│ - TwiML builder  │        REPLACED BY   │ - Dispatch rule  │
│ - μ-law codec    │       ─────────────▶ │   matching       │
│ - WS pump        │                      │ - Opus transcode │
│ - Room publish   │                      │ - Room create    │
│ - Agent dispatch │                      │                  │
└────────┬─────────┘                      └────────┬─────────┘
         │                                         │
         │ rtc-node                                │ internal
         ▼                                         ▼
┌──────────────────┐                      ┌──────────────────┐
│  livekit-server  │                      │  livekit-server  │
│  (per-call room) │                      │  (per-call room) │
└────────┬─────────┘                      └────────┬─────────┘
         │                                         │
         │ dispatch                                │ dispatch
         ▼                                         ▼
┌──────────────────┐                      ┌──────────────────┐
│  phone-nyla      │     (unchanged)      │  phone-nyla      │
│  phone-aoi       │    ────────────▶     │  phone-aoi       │
│  phone-party     │                      │  phone-party     │
└──────────────────┘                      └──────────────────┘
```

### Lines of code we delete

| File in bridge                   | Lines | Fate     |
|----------------------------------|-------|----------|
| `src/media-stream.ts`            | ~540  | **delete** |
| `src/audio/mulaw.ts`             | ~80   | **delete** |
| `src/livekit-bridge.ts`          | ~460  | **delete** (90% of it) |
| `src/twiml.ts`                   | ~130  | **delete** (SIP doesn't use TwiML) |
| `src/twilio-signature.ts`        | ~90   | keep iff we still receive any Twilio webhooks; otherwise delete |
| `src/webhook-server.ts`          | ~580  | trim by ~70% — only health + outbound (if we keep outbound there) |
| `src/runtime.ts`                 | ~130  | simplify |

Total: roughly **1600 lines removed**, ~200 lines remain or move.

### What we add

- A `livekit-sip` service running somewhere (Docker on this box, or a
  dedicated host).
- A **Redis** instance (single-machine, no HA — livekit-sip uses Redis
  for SIP session state).
- One YAML config file for `livekit-sip`.
- One or more JSON dispatch rules registered via `lk` CLI.
- A Twilio Elastic SIP Trunk configured in the Twilio console.
- Public UDP 5060 (SIP signaling) + UDP 10000-20000 (RTP media) on the
  bridge host, or wherever livekit-sip runs.

## How agents find the caller

Today, the bridge packs `{callSid, from, to}` into `ctx.job.metadata` as
a JSON string. Every agent `json.loads()` it in the entrypoint.

Under SIP, that metadata doesn't exist. Caller info surfaces through
**participant attributes** on the SIP participant that LiveKit creates:

| Attribute                     | Meaning                                |
|-------------------------------|----------------------------------------|
| `sip.callID`                  | SIP Call-ID header (unique per call)   |
| `sip.trunkID`                 | Which inbound trunk accepted the call  |
| `sip.trunkPhoneNumber`        | Your DID (the callee)                  |
| `sip.from`                    | Caller phone number (SIP From header)  |

Dispatch rules can *also* set an arbitrary `metadata` string on the
room, which becomes `ctx.job.metadata` — so we can still pack agent
routing info there. But caller ID comes from the participant, not the job.

See [agent-changes.md](agent-changes.md) for the exact Python diffs.

## Outbound calling

Today the bridge exposes `POST /voice/outbound` which calls Twilio REST
API. Under SIP:

- Create an **outbound trunk** in livekit-sip (can use the same Twilio
  trunk; just needs termination credentials configured)
- Call `SipServiceClient.create_sip_participant(room_name, sip_call_to,
  sip_trunk_id, ...)` from Python. The destination phone rings, picks up,
  and the participant joins the existing room.
- The hard-coded `OUTBOUND_ALLOWED_DESTINATION` safety guard moves from
  env var to a check in whatever code calls `create_sip_participant`.

Recommendation: move outbound initiation into the SDK as a tool (the
same pattern as `openclaw_request`, `sessions_spawn`, etc.) rather than
keeping a separate HTTP service just for it. That collapses the bridge
repo to near-empty.

## What happens to openclaw-livekit-bridge

- Keep the repo. Archive it after the 2-week rollback window expires.
- Retain the launchd plist **disabled** on disk for fast rollback.
- All its env vars and secrets can be retired after cutover.

## Gotchas documented up front

1. **Redis is mandatory.** No in-memory fallback. If Redis goes down,
   new calls fail. Plan monitoring.
2. **Public IP requirement.** `livekit-sip` must be reachable from
   Twilio's SBC on UDP 5060 + the RTP range. `livekit-server --dev` on
   localhost + external Twilio does not work.
3. **Codec lock.** Twilio offers PCMU and PCMA; force PCMU in the trunk
   config to avoid renegotiation loops.
4. **TLS on signaling ≠ SRTP on media.** If you enable only TLS, audio
   still travels in the clear. For a home setup probably fine; document
   the decision.
5. **SIP dispatch rule metadata is a string, not a dict.** If you want
   structured routing info, `json.dumps()` it into the metadata field.
