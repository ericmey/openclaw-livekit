# Diagnostic: is #3379 biting us?

[livekit/agents#3379](https://github.com/livekit/agents/issues/3379)
describes Twilio Media Streams WebSockets **silently dropping audio
packets** when bridged to LiveKit. The drop is probabilistic, and
Twilio/LiveKit never surface it as an error. The agent just gets
incomplete audio and makes bad decisions.

Before committing to a weekend of SIP migration, confirm (or rule out)
that this is what's driving the "odd agent behavior."

## Symptom profile

If you've been seeing any of these, #3379 is a strong candidate:

- [ ] Agent responds to words the caller didn't quite say
- [ ] Agent interrupts unexpectedly or gets interrupted without reason
- [ ] Random awkward pauses where agent thinks caller finished
- [ ] "Huh?" / "Can you repeat that?" / "I didn't catch that" more than once a call
- [ ] Identical-sounding calls behave differently
- [ ] VAD tuning (`start_sensitivity`, `silence_duration_ms`, etc.) seems
      to compensate for "bad audio" rather than real VAD decisions
- [ ] Problem worsens under network load or at specific times of day
- [ ] Behavior differs between agents using the same model (implies an
      input-audio problem, not a model problem)

A clean #3379 signature is: **agent behavior is the symptom, but audio
frame counts don't match what Twilio says it sent.**

## Quick check — no code changes

1. Pick 3 recent CallSids where the agent misbehaved. Get them from
   `~/.openclaw/logs/voice/bridge.log` (grep for `start: streamSid=...
   callSid=...`).

2. **Twilio side:** For each CallSid, go to
   Twilio Console → Monitor → Logs → Calls → [CallSid] → Voice Insights.
   Note:
   - Call duration
   - Any "Warnings" listed (Twilio flags several jitter/loss patterns)
   - If Media Streams-specific metrics are shown (varies by account),
     note outbound packets from Twilio

3. **Bridge side:** Count `media` events received for the same CallSid.
   The bridge doesn't log per-frame today, so you have two options:

   **Option A — passive:** check session duration from the logs
   (`start` timestamp → `stop` / teardown timestamp) and compare against
   Twilio's reported duration. Big disparities (5 s+) are suspicious.

   **Option B — instrument briefly.** Apply the temporary patch below,
   run the bridge for an hour, reproduce the issue, then revert.

4. **Agent side:** Pull the transcript from
   `~/.openclaw/logs/voice/{CallSid}.transcript` (or wherever your
   transcript writer puts them). If the STT transcript has gaps that
   don't correspond to actual caller silence, that's your tell.

## Temporary frame-count instrumentation

Apply this diff to [openclaw-livekit-bridge/src/media-stream.ts](https://github.com/ericmey/openclaw-livekit-bridge/blob/main/src/media-stream.ts)
to log frame count per second per call. **Revert before cutover** — it's
a 50-line-per-second log spam and not appropriate for production.

```ts
// Near the top of ActiveSession type:
interface ActiveSession {
  callSid: string;
  streamSid: string;
  ws: WebSocket;
  bridge: LivekitBridge;
  stopped: boolean;
  // ADD:
  diagFrameCount: number;
  diagLastLogAt: number;
}

// When creating session in handleStart(), add:
diagFrameCount: 0,
diagLastLogAt: Date.now(),

// In the "media" switch case, BEFORE the early return, add:
if (session) {
  session.diagFrameCount++;
  const now = Date.now();
  if (now - session.diagLastLogAt >= 1000) {
    log.info(
      `[diag-3379] callSid=${session.callSid} frames/s=${session.diagFrameCount}`,
    );
    session.diagFrameCount = 0;
    session.diagLastLogAt = now;
  }
}
```

Expected baseline: **~50 frames/sec** (8 kHz / 160 samples-per-frame =
50 fps). Anything consistently below 45 fps mid-call is evidence of drops.

## Interpretation

| Observation                                                | Verdict                                    |
|------------------------------------------------------------|--------------------------------------------|
| Twilio duration ≈ bridge duration, STT transcript complete | Not #3379. Investigate prompt/VAD/model.   |
| Frame rate drops below 45 fps during agent-misbehavior windows | #3379 confirmed. Prioritize SIP migration. |
| Frame rate drops at specific times of day                  | #3379 likely + possibly network-quality.   |
| Frame rate is fine but transcript has holes                | Probably STT-side (whisper batching) or Gemini input buffering, not Media Streams. |
| Large frame-count disparity but Twilio shows no warnings   | Classic #3379 pattern — Twilio doesn't know. |

## What to do with the answer

- **Confirmed** → [MIGRATION.md](../MIGRATION.md), go.
- **Not confirmed** → Pause the SIP migration, redirect focus to:
  1. Review `_shared.py` VAD params (Nyla) — maybe they've drifted away
     from optimal now that you have a non-broken baseline.
  2. Check if Gemini 2.5 Flash Native Audio had any API-level regressions
     in the last two weeks (Google's changelog + status page).
  3. Run the persona prompt through a thought-experiment: does it
     actually handle ambiguous input gracefully?

## Revert the instrumentation

Don't forget. In production:

```bash
cd ~/.openclaw/extensions/openclaw-livekit-bridge
git diff src/media-stream.ts    # confirm only diag lines
git checkout src/media-stream.ts
npm run build
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-bridge.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-bridge.plist
```
