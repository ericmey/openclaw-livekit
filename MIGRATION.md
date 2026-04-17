# Migration checklist: Media Streams → SIP

Execute top-to-bottom. Each section ends with a **stop line** — don't move
past it until the check passes. Rollback at any point with
[docs/rollback.md](docs/rollback.md).

## Phase 0 — Confirm the trigger

Before spending a weekend on this, run the #3379 diagnostic in
[docs/diagnostic-3379.md](docs/diagnostic-3379.md) against recent
"odd behavior" calls.

- [ ] Collected ≥ 3 CallSids from calls where the agent acted weird
- [ ] Cross-referenced Twilio Voice Insights with bridge logs
- [ ] Decision: frame-count mismatch confirmed → proceed. No mismatch →
      park this migration, investigate agent-side (prompt/VAD/model).

**Stop until decision is made.**

## Phase 1 — Infrastructure stand-up (can do in isolation, no Twilio yet)

### 1.1 Redis

- [ ] Install Redis (`brew install redis` or Docker). No HA needed for
      single-machine deploy.
- [ ] Confirm reachable at `127.0.0.1:6379`
- [ ] Add launchd plist if running natively (sample in `config/`)

### 1.2 livekit-sip binary

Two options — Docker is simpler, native is faster to iterate on.

**Docker (recommended first attempt):**
- [ ] `docker pull livekit/sip:latest`
- [ ] Copy `config/livekit-sip.yaml.example` to `~/.openclaw/config/livekit-sip.yaml`
- [ ] Fill in real LiveKit API key / secret from the existing server
- [ ] Start with host networking: `docker run --network=host -v ~/.openclaw/config/livekit-sip.yaml:/config.yaml livekit/sip --config /config.yaml`

**Native (for production):**
- [ ] `brew install pkg-config opus opusfile libsoxr`
- [ ] `git clone https://github.com/livekit/sip && cd sip && mage build`
- [ ] Copy binary to `/usr/local/bin/livekit-sip`
- [ ] Copy launchd plist template from `config/launchd.plist.example`

### 1.3 livekit-server readiness

- [ ] Confirm version recent enough (check release notes — SIP dispatch
      rules need 1.5+)
- [ ] Redis connection added to `livekit.yaml` if not already present
      (livekit-sip ↔ livekit-server communicate over Redis)

### 1.4 `lk` CLI

- [ ] `brew install livekit-cli`
- [ ] `lk cloud auth` (if using Cloud) or point at local: `export LIVEKIT_URL=... LIVEKIT_API_KEY=... LIVEKIT_API_SECRET=...`
- [ ] `lk sip --help` returns cleanly

**Stop:** `lk sip trunk list` returns an empty list without error. Infrastructure works, just empty.

## Phase 2 — Twilio Elastic SIP Trunk

Do this in the Twilio console. Full walkthrough in
[docs/twilio-trunk.md](docs/twilio-trunk.md).

- [ ] Create a new Elastic SIP Trunk (separate from Programmable Voice)
- [ ] Configure Origination Connection Policy pointing at your public
      `livekit-sip` endpoint (`sip://<public-host>:5060;transport=tcp`)
- [ ] Create a SIP Credential List for termination auth
- [ ] Attach one of your existing Twilio numbers to the new trunk
- [ ] Note down: trunk SID, origination URI, termination credentials
- [ ] Configure IP allowlist to include Twilio's SBC ranges
- [ ] Lock codec to **G.711 µ-law (PCMU)** only

**Stop:** Twilio console shows the trunk as configured, one DID attached, no warnings.

## Phase 3 — Inbound trunk + dispatch rules in LiveKit

- [ ] Register the Twilio trunk with livekit-sip:
      ```bash
      lk sip trunk create inbound \
        --name "twilio-primary" \
        --numbers "+1...YOUR-DID..." \
        --auth-user "<from-twilio-credlist>" \
        --auth-pass "<from-twilio-credlist>"
      ```
      Save the returned trunk ID.
- [ ] Create a dispatch rule mapping the DID to an agent:
      ```bash
      lk sip dispatch create config/dispatch-rule-per-call.json \
        --trunks "<trunk-id>"
      ```
      (Edit the JSON first — `agentName` field picks which Python worker dispatches.)
- [ ] Verify with `lk sip trunk list` and `lk sip dispatch list`

**Stop:** Both lists show the new entries.

## Phase 4 — Agent-side patches

See [docs/agent-changes.md](docs/agent-changes.md) for exact diffs.

- [ ] Patch `openclaw-livekit-agent-nyla/src/_shared.py` to read
      `participant.attributes["sip.from"]` instead of `ctx.job.metadata.from`
- [ ] Patch `openclaw-livekit-agent-aoi/src/agent.py` (inline equivalent)
- [ ] Patch `openclaw-livekit-agent-party/src/agent.py`
- [ ] Keep a compatibility branch on each: if metadata has `from`, use
      it (bridge path); else use `sip.from` (SIP path). This lets
      agents run under either bridge or SIP during cutover.
- [ ] Rebuild locks, cycle each agent's launchd plist

**Stop:** All three agents restart cleanly; text-only test (`make verify-voice-agents`) passes.

## Phase 5 — First real call, single number

- [ ] Call the DID on the new SIP trunk from your cell phone
- [ ] Watch `livekit-sip` logs — should see SIP INVITE, room creation, agent dispatch
- [ ] Agent answers, conversation holds for ≥ 60 seconds
- [ ] Hang up cleanly — no orphaned rooms, no launchd restart

**Stop:** One real call end-to-end works.

## Phase 6 — Outbound migration

- [ ] Create outbound trunk in Twilio (can reuse the same trunk; outbound
      direction just needs termination creds)
- [ ] Register outbound trunk with `lk sip trunk create outbound`
- [ ] Replace the bridge's `POST /voice/outbound` with a small
      `CreateSIPParticipant` call — this can live in the agent's tool
      set, or in a thin wrapper service. Recommendation: keep it as an
      SDK tool (`openclaw_request`-style), not a separate service.
- [ ] Test outbound to the hard-coded `OUTBOUND_ALLOWED_DESTINATION`

**Stop:** Outbound works, destination arrival matches expected caller ID.

## Phase 7 — Cutover

- [ ] Point all Twilio DIDs at the new SIP trunk
- [ ] Watch the next 5-10 real calls live
- [ ] `launchctl bootout` the bridge plist (leave it on disk — do NOT
      delete). Leave disabled for at least 2 weeks.
- [ ] Announce cutover in your personal log / memory

**Stop:** SIP is primary. Bridge is dormant but available.

## Phase 8 — Cleanup (2 weeks post-cutover)

- [ ] No rollback needed? Archive the bridge repo (GitHub → Settings → Archive)
- [ ] Delete `OUTBOUND_*` env vars from bridge plist (leave the plist file for history)
- [ ] Merge agent compatibility branches — drop the dual metadata path,
      keep only the SIP shape
- [ ] Update this repo's README status from "planned" to "deployed"

Done.

## Rollback triggers

Abort and run [docs/rollback.md](docs/rollback.md) if any of these hit
during Phase 5-7:

- One-way audio on more than 1 call
- Calls succeeding but agents never being dispatched
- Codec negotiation failures in livekit-sip logs
- Twilio rejects SIP INVITE with 5xx repeatedly
- Redis crashes and doesn't come back cleanly
