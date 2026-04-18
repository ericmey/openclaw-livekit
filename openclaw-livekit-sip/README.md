# openclaw-livekit-sip

Migration staging for moving the OpenClaw voice stack from **Twilio Media
Streams** (the current [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge))
to **SIP trunking** via [`livekit-sip`](https://github.com/livekit/sip) —
the officially-supported LiveKit telephony path.

This repo is **planning + pre-setup only**. No runnable code yet. It holds:

- The migration plan and checklist ([MIGRATION.md](MIGRATION.md))
- Architecture rationale ([docs/architecture.md](docs/architecture.md))
- A diagnostic for confirming the [livekit/agents#3379](https://github.com/livekit/agents/issues/3379)
  Media Streams packet-drop pattern ([docs/diagnostic-3379.md](docs/diagnostic-3379.md))
- Twilio Elastic SIP Trunk setup guide ([docs/twilio-trunk.md](docs/twilio-trunk.md))
- Per-agent code changes ([docs/agent-changes.md](docs/agent-changes.md))
- Rollback plan ([docs/rollback.md](docs/rollback.md))
- Config templates for `livekit-sip`, dispatch rules, Docker Compose, and launchd

## Status

Planned migration. Trigger is whichever comes first:

1. Confirmation via [docs/diagnostic-3379.md](docs/diagnostic-3379.md)
   that current "odd agent behavior" is caused by Media Streams silently
   dropping packets → migration becomes P0.
2. A scheduled weekend where SIP infrastructure (a few new services) can
   be stood up and burned in without production pressure.

Personal project — shared publicly for reference and portfolio. Not
actively maintained as an open-source community project.

## Target architecture (summary)

```
┌──────────┐        ┌─────────────────────┐        ┌──────────────┐
│  Twilio  │  SIP   │ livekit-sip         │  WS    │ livekit-     │
│  Elastic │──────▶│ (inbound/outbound   │──────▶│ server       │
│  Trunk   │ G.711  │  trunks + dispatch  │        │  (rooms,     │
│          │  PCMU  │  rules)             │        │   agents)    │
└──────────┘        └─────────────────────┘        └──────────────┘
                              │                            ▲
                              │ needs redis                │ dispatch
                              ▼                            │
                        ┌─────────┐                 ┌─────────────┐
                        │  redis  │                 │ phone-nyla, │
                        │         │                 │ phone-aoi…  │
                        └─────────┘                 │ (unchanged) │
                                                    └─────────────┘
```

What goes away: the Node bridge, μ-law codec, per-call WebSocket, TwiML.
What stays: the four Python agents (tiny metadata change).
What's new: `livekit-sip` service, Redis, Twilio Elastic SIP Trunk config.

## Sibling projects

- [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge) — **outgoing** Media Streams bridge (to be retired)
- [openclaw-livekit-agent-sdk](https://github.com/ericmey/openclaw-livekit-agent-sdk) — shared Python runtime
- [openclaw-livekit-agent-aoi](https://github.com/ericmey/openclaw-livekit-agent-aoi) — Aoi persona
- [openclaw-livekit-agent-nyla](https://github.com/ericmey/openclaw-livekit-agent-nyla) — Nyla persona
- [openclaw-livekit-agent-party](https://github.com/ericmey/openclaw-livekit-agent-party) — chained persona

## License

MIT — see [LICENSE](LICENSE).
