# Rollback plan

If SIP misbehaves during or after cutover, bring the Media Streams
bridge back. The plan is designed so rollback takes **< 2 minutes** and
requires no code changes.

## Pre-cutover safeguards

Before you run Phase 7 (cutover), confirm all of these:

- [ ] Bridge launchd plist still on disk (just unloaded, not deleted)
- [ ] Bridge code still builds from `dist/` — no `rm -rf dist`
- [ ] Bridge's JSON config at `~/.openclaw/config/livekit-bridge.json`
      is intact
- [ ] Bridge env vars (LIVEKIT_API_*, TWILIO_AUTH_TOKEN, etc.) still
      present in the plist or a separately-maintained source
- [ ] Twilio DIDs have their **Programmable Voice webhook URL**
      recorded (the bridge URL you originally pointed them at) — you'll
      re-enter this during rollback
- [ ] Agent code compatibility shim (the dual-path `resolve_caller()`)
      is deployed. If you've already stripped it, rollback requires
      reverting that commit too.

## Rollback procedure

### Step 1: Re-point Twilio DIDs at the Programmable Voice webhook

Twilio Console → **Phone Numbers** → **Active numbers** → [each DID] →
**Voice Configuration**:

- Change **"A Call Comes In"** from "SIP Trunk: openclaw-livekit" back
  to "Webhook" with the bridge's public URL (e.g.,
  `https://voip.example.com/voice/webhook`)
- Method: `HTTP POST`
- Save

This alone re-routes new calls to the bridge. In-flight SIP calls stay
alive until they hang up.

### Step 2: Re-enable the bridge launchd plist

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-bridge.plist
launchctl print gui/$(id -u)/ai.openclaw.livekit-bridge | grep -E "state|last exit"
```

Expected: `state = running`, `last exit code = 0` (fresh start).

### Step 3: Confirm health

- `curl http://127.0.0.1:3334/voice/health` returns `{"ok": true, ...}`
- `tail -f ~/.openclaw/logs/voice/bridge.log` shows no errors
- Make a test call to a DID — should ring through to an agent

### Step 4 (optional): Stop livekit-sip

Keep it running if you're going to retry soon; stop it if the cause is
suspected infrastructure fault.

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-sip.plist
# or, if running under Docker:
docker stop livekit-sip
```

Redis can keep running — it's useful for other things and livekit-sip
just stops consuming it.

## When to pull the trigger

Don't wait for the perfect signal. Roll back if **any** of these hit
within 24 hours of cutover:

- More than one call with one-way audio
- Agent dispatch failures on > 5% of calls
- `livekit-sip` crash loops (> 3 restarts via launchd in an hour)
- Twilio 5xx responses sustained for > 5 minutes
- Any error pattern that looks unfamiliar and you can't diagnose in 15 min

Rolling back early is cheap. Rolling back late means angry callers.

## Post-rollback

1. Leave DIDs pointed at the bridge until root cause is understood.
2. `livekit-sip` and Redis can keep running locally for further testing.
3. File a note in `~/.openclaw/memory/` (or your project log) capturing
   the observed symptom + current hypothesis. Don't rely on memory —
   the detail that mattered at 11pm is never the detail you remember
   at 9am.
4. Before the next cutover attempt, update this repo's
   [MIGRATION.md](../MIGRATION.md) with the new lesson as a checklist
   item.

## Cleaning up post-rollback decisively

If after 2-3 attempts SIP just isn't viable for this setup:

- Archive this `openclaw-livekit-sip` repo on GitHub with a note in
  the README explaining why
- Revert the SDK's `telephony.resolve_caller()` helper to the pure
  bridge path (simpler)
- Keep the #3379 diagnostic doc somewhere — it has standalone value
  for investigating any future audio weirdness

SIP being wrong for OpenClaw wouldn't be a failure of planning, just
a reality about this particular setup. Budget for it.
