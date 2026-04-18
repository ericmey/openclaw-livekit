# openclaw-livekit-sip

Operational notes for the planned SIP migration of the OpenClaw voice
stack. When this repo goes from "plan" to "running," this doc becomes
the day-two runbook.

## What it will be (once implemented)

A supervised `livekit-sip` service that:

1. Terminates SIP calls coming from a Twilio Elastic SIP Trunk
2. Translates between SIP (G.711 µ-law) and LiveKit Opus
3. Routes each call to a LiveKit Room according to dispatch rules
4. Joins the configured agent (`phone-aoi`, `phone-nyla`, `phone-party`)
   into the room via the existing dispatch mechanism
5. Places outbound calls on demand via `CreateSIPParticipant`

## What this repo will eventually own

- Config for the `livekit-sip` service (`config/livekit-sip.yaml`)
- Dispatch rule JSON(s) for the routing table
- A launchd plist that supervises the SIP service alongside
  `livekit-server` and Redis
- Deployment + rollback scripts
- Smoke tests that exercise the SIP path end-to-end using
  `livekit-server --dev` (for the LK side) + a SIP sipp scenario or
  real Twilio sandbox number

## Required infrastructure

| Component        | Status | Notes                                                          |
|------------------|--------|----------------------------------------------------------------|
| `livekit-server` | ✅ running | Already hosting rooms for the Media Streams bridge            |
| `livekit-sip`    | ❌ new     | New service, Docker or native binary, needs public IP for Twilio |
| `redis`          | ❌ new     | livekit-sip uses Redis for SIP session state — no in-mem fallback |
| Public IP / DNS  | ⚠️  existing | Bridge already runs behind Kong; SIP needs UDP 5060 + RTP 10000-20000 exposed |
| Twilio Elastic SIP Trunk | ❌ new | Configured in Twilio console, separate from existing Programmable Voice |

**Read this before starting:** [docs/architecture.md](docs/architecture.md)
has the full rationale. [MIGRATION.md](MIGRATION.md) has the actual
day-of-migration checklist.

## Dependencies on other repos

- [openclaw-livekit-agent-{aoi,nyla,party}](https://github.com/ericmey) —
  each needs a ~10-line patch to read SIP participant attributes instead
  of Twilio-shaped `ctx.job.metadata`. See [docs/agent-changes.md](docs/agent-changes.md).
- [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge) —
  will be retired but kept disabled-but-present for 2 weeks post-cutover
  as a rollback target. See [docs/rollback.md](docs/rollback.md).

## License

MIT — see [LICENSE](LICENSE).
