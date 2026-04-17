# Migration checklist: A/B test SIP alongside Media Streams

**Strategy:** keep the existing [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge)
running, stand up `livekit-sip` in parallel, and point exactly **one
Twilio DID** at the SIP path while the others stay on the bridge. Agents
already handle both transports transparently via
[`resolve_caller()`](https://github.com/ericmey/openclaw-livekit-agent-sdk/blob/main/src/openclaw_livekit_agent_sdk/telephony.py)
— no per-call branching anywhere. Compare behavior over ~1 week, then
decide: promote SIP to all lines, or roll back.

Execute top-to-bottom. Each section ends with a **stop line** — don't
move past it until the check passes. Rollback at any point with
[docs/rollback.md](docs/rollback.md).

## Phase 0 — Compatibility shim already deployed

This was the first thing we shipped, so the rest of the migration is
infra work only. Confirm it's live:

- [ ] `openclaw-livekit-agent-sdk` has `src/openclaw_livekit_agent_sdk/telephony.py`
      (module `resolve_caller`)
- [ ] aoi / nyla / party entrypoints call `resolve_caller(ctx)` instead
      of parsing `ctx.job.metadata` directly
- [ ] All agent venvs rebuilt from current SDK: `make install-voice-agents`
- [ ] All agent launchd plists cycled (`bootout` + `bootstrap`)
- [ ] One smoke call through the existing bridge — agent logs show
      `caller resolved ... source=bridge` and the call works normally

**Stop:** bridge still behaves identically to before the SDK refactor.

## Phase 1 — Infrastructure stand-up (no Twilio yet)

Run the setup script:

```bash
./scripts/setup-infra.sh
```

This installs Redis (via brew + services), installs `lk` CLI, and pulls
the `livekit/sip` Docker image. Idempotent — safe to re-run.

- [ ] `redis-cli ping` returns `PONG`
- [ ] `lk --version` prints a version
- [ ] `docker images livekit/sip` lists the image
- [ ] `~/.openclaw/config/livekit-sip.yaml` exists — edit `api_key`,
      `api_secret`, `ws_url` to match your LiveKit server

**Stop:** `lk sip trunk list` runs without error (returns empty list; that's fine).

## Phase 2 — Start livekit-sip (foreground first, launchd later)

In a dedicated terminal so you can watch logs:

```bash
docker run --rm --network=host \
  -v ~/.openclaw/config/livekit-sip.yaml:/config.yaml:ro \
  livekit/sip:latest --config /config.yaml
```

You should see startup logs mentioning Redis connection, LiveKit server
handshake, SIP listener bound on 5060.

- [ ] No errors in the first 10 seconds of startup
- [ ] `lsof -iUDP:5060 -n -P` shows Docker listening
- [ ] LiveKit server logs (wherever yours go) show the new agent
      connection from livekit-sip

**Stop:** livekit-sip runs cleanly. Leave it running — don't CTRL-C yet.

## Phase 3 — Twilio Elastic SIP Trunk

Full walkthrough in [docs/twilio-trunk.md](docs/twilio-trunk.md).

- [ ] Create a new Elastic SIP Trunk in Twilio console (keep separate
      from your existing Programmable Voice setup)
- [ ] Origination Connection Policy points at your public
      `livekit-sip` endpoint (`sip://<your-host>:5060;transport=tcp`)
- [ ] Credential list created for termination auth
- [ ] **Attach ONE test DID** to the trunk. Pick a low-traffic number
      — do NOT attach all your production DIDs. The others stay on
      Programmable Voice → bridge for now.
- [ ] Lock codec to PCMU (G.711 µ-law)
- [ ] Record trunk SID, origination URI, termination credentials

**Stop:** Twilio shows the trunk configured, ONE DID attached, no warnings.

## Phase 4 — Register inbound trunk + dispatch rule

```bash
# Edit config/dispatch-rule-per-call.json.example:
#   - Replace +15550000000 with your actual test DID
#   - Set agentName (recommendation: phone-nyla for the first test)
#   - Save as dispatch-rule-per-call.local.json (gitignored)

# Register the trunk:
lk sip trunk create inbound \
  --name "twilio-primary" \
  --numbers "+1YOUR_TEST_DID" \
  --auth-user "openclaw-sip" \
  --auth-pass "<from-twilio-credlist>"

# Note the returned trunk ID (e.g. ST_xxxxxxxx)
# Then register the dispatch rule:
lk sip dispatch create config/dispatch-rule-per-call.local.json \
  --trunks "<trunk-id-from-above>"

# Verify:
lk sip trunk list
lk sip dispatch list
```

**Stop:** both `list` commands show the new entries.

## Phase 5 — First real SIP call

Pre-flight:

- [ ] Bridge still running (`launchctl print gui/$(id -u)/ai.openclaw.livekit-bridge` reports `running`)
- [ ] livekit-sip still running (foreground terminal from Phase 2)
- [ ] All three Python agents still running

Call the test DID from your cell. Expected timeline:

1. Twilio routes the call to the SIP trunk
2. livekit-sip logs show SIP INVITE received
3. Dispatch rule matches → LiveKit server creates a room
4. Agent (`phone-nyla` per the dispatch rule) gets dispatched into the room
5. Agent's log line: `phone-nyla caller resolved: from=+1... call_id=... source=sip`
6. Agent greets you, conversation proceeds

- [ ] Call connects within 3 seconds
- [ ] Two-way audio, no drops, no one-way audio
- [ ] Agent behavior feels normal (no #3379-style weirdness)
- [ ] Hangup is clean — no orphaned rooms
- [ ] Agent log confirms `source=sip`

Make at least 3 calls across different times of day before declaring victory.

**Stop:** SIP path works end-to-end on the test DID.

## Phase 6 — A/B window (1 week minimum)

Live with both transports running side-by-side. Call the SIP DID when
you want to test SIP; call any other DID for the bridge path.

**What to track** (eyeball in logs; formal metrics optional):

- Subjective: does the agent feel "better" on SIP calls vs bridge calls?
- Objective per call (grep agent logs):
  - Count of "caller resolved source=bridge" vs "source=sip"
  - Any errors/warnings during the call
  - Call duration vs what you remember subjectively
- Agent-level:
  - VAD behavior — fewer spurious turn-endings?
  - STT transcript completeness
  - Gemini "I didn't catch that" / "can you repeat" frequency

**Decision criteria after 1 week:**

| Observation                                                      | Move |
|------------------------------------------------------------------|------|
| SIP calls subjectively better, no new failure modes              | Promote SIP (Phase 7) |
| SIP calls equal to bridge, no new failure modes                  | Promote SIP — less bridge code to maintain |
| SIP introduces new failure modes                                 | Diagnose + extend A/B, don't promote yet |
| SIP worse than bridge (e.g., SIP-specific audio issues)          | Park — keep infrastructure available, but don't promote |

**Stop:** you have data + a decision.

## Phase 7 — Promote (once decision is "go")

- [ ] Move `livekit-sip` from foreground Docker to launchd
      (`config/launchd.plist.example` as a starting point)
- [ ] Re-point remaining Twilio DIDs at the SIP trunk, one at a time
      over a few days so blast radius is bounded
- [ ] Do NOT delete the bridge plist yet — see Phase 8

**Stop:** all DIDs now route via SIP. Bridge still available.

## Phase 8 — Cleanup (2 weeks post-promotion)

Only run this if Phase 7 has been stable for 2+ weeks.

- [ ] `launchctl bootout` the bridge plist; keep the file on disk
- [ ] Archive the [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge)
      repo (GitHub → Settings → Archive) with a README note pointing
      here
- [ ] Delete bridge-specific env vars from anywhere they're set
- [ ] Agent entrypoints: optionally simplify by dropping the bridge
      path inside `resolve_caller()` (or leave it — the code is tiny and
      keeping it means the SDK stays transport-agnostic for any future
      alternative)

Done. Update this repo's README status from "planned" to "deployed."

## Rollback triggers during Phase 5-7

Abort and run [docs/rollback.md](docs/rollback.md) if any of these hit:

- One-way audio on more than one SIP call
- SIP calls succeeding but agents never dispatched
- Codec negotiation failures recurring in livekit-sip logs
- Twilio rejects SIP INVITE with 5xx repeatedly
- Redis crashes and doesn't come back cleanly
- Any symptom that looks unfamiliar and can't be diagnosed in 15 min

Rollback is cheap — it's literally repointing one DID in the Twilio
console back to Programmable Voice. The agents need no changes since
they already handle both transports.
