# Project status

**Last updated:** 2026-04-18 (cutover day)

A snapshot of what's done, what's in flight, and what's next. Update
when state materially changes — ideally alongside a commit that
reflects the change in code.

## Current stage

**Monorepo cutover complete.** The voice stack is now organized as a
single repo at `~/Projects/openclaw-livekit/` with five subprojects
imported as subtrees (full history preserved) plus the operations
layer. The five former sibling repos at the previous OpenClaw
extensions path were archived to `~/Projects/_archive/` and the live
agents were redeployed from the new paths.

The phone line is operational:
- `+1 (317) 653-4945`, `+1 (765) 754-4435` → `phone-nyla`
- `+1 (765) 415-4237` → `phone-aoi`
- `+1 (765) 335-7384` → `phone-party`

Caller allowlist: `+1 (317) 995-7066` (Eric's cell) only.

## What shipped today (2026-04-18)

Too many changes for one list. In order of depth:

### Infrastructure / ops
- Full monorepo layout with pinned image tags in `docker-compose.yaml`
  (livekit-server v1.10.1, livekit-sip v1.2.0, redis 7-alpine).
- Launchd plist template with substitution tokens, rendered by
  `scripts/deploy-agents.sh` from `secrets/livekit-agents.env`.
- Idempotent `scripts/register-sip-routing.sh` reads config JSON, diffs
  against live Redis state, delete+recreates as needed.
- `scripts/health-check.sh` with `--json` mode for future cron wiring.
- Portable shell (POSIX case statements, no bash-4 associative arrays
  — works on stock macOS bash 3.2).

### SIP routing
- Fixed the `numbers` vs `inbound_numbers` dispatch-rule bug
  (documented in `docs/DISPATCH-RULE-GOTCHAS.md`). Every call before
  the fix 486'd with `reason: flood` which is livekit-sip's label for
  `DispatchNoRuleDrop`.
- Removed the deprecated Twilio Media Streams bridge (`livekit-bridge`
  launchd plist, config, log). Agents now resolve callers exclusively
  via SIP participant attributes — no dual-path code in `telephony.py`.

### Agents + SDK
- `AgentConfig` dataclass — per-agent operational identity (`agent_name`,
  `memory_agent_tag`, `discord_room`, `allowed_delegation_targets`).
  Tool mixins read from `self.config` instead of hardcoded constants.
- Aoi's delegation allowlist tightened to `{yumi, rin, aoi, momo, nyla}`
  per her prompt's "technical partner, not household router" framing.
- `schedule_callback` tool disabled (function_tool decorator removed).
  Method body + guardrails + tests preserved for re-enable. See
  `openclaw-livekit-agent-sdk/TODO.md` for the preferred cron payload
  redesign (Option A: OpenClaw CLI verb, no LLM in the loop).
- `OPENCLAW_VOICE_TOOLS_DRY_RUN=1` env var gates all actuator tools
  (`sessions_send`, `academy_*`). Tests exercise full tool paths
  without firing real Discord messages or cron jobs.
- Actionable error strings across every tool — "I couldn't reach X —
  Y failed" instead of "couldn't do that right now."
- Deterministic startup context: `on_enter` prefetches recent household
  memories and folds them into the greeting instruction, so the model
  can't skip the call.
- Prompt reorg for all three agents — voice+action first, user-language
  → tool routing examples, explicit failure style, lore moved lower.
- Test gates: Nyla integration tests skipped unless
  `RUN_INTEGRATION_TESTS=1` (they hit real services). SDK/aoi/party
  declare pytest + pytest-asyncio as dev deps so fresh venvs work.

### Tests
- SDK: 83 passing
- Nyla: 30 passing, 4 skipped (integration)
- Aoi: 26 passing
- Party: 24 passing

Run from monorepo root: `make test`.

## Known state that's not in code

- `secrets/livekit-sip-trunk.md` — has the final cutover values
  (Twilio trunk SID, termination URI, credential username/password,
  livekit-sip trunk + dispatch rule IDs, attached DIDs). Never in git.
- `secrets/livekit-agents.env` — runtime secrets for the launchd
  plists (API keys, Discord bot tokens). Never in git.
- Twilio Elastic SIP Trunk — console state only. IP ACL attached
  to source `104.254.222.24/32`.
- Brew `redis` service still serving `127.0.0.1:6379` — compose's
  redis service is in the file but `brew services stop redis` is
  required before `make up` or the two will fight for the port.
  (Future: move fully to compose redis or document the brew-only path.)

## Open issue from cutover verification (2026-04-18)

**Dead air after Nyla answers.** Inbound call on
`+1 (317) 653-4945` reaches `phone-nyla`, the worker picks up the job,
and the caller hears silence — no greeting, no audio on the return
path. Confirmed working up to agent dispatch; broken somewhere in
media or in the agent's first turn.

Call path up to pickup is fine: trunk matched, dispatch rule matched,
agent dispatched, worker registered the job, call connected. Media
return is the problem. Likely suspects:

- **RTP return path blocked.** Container uses `network_mode: host` but
  Docker Desktop on macOS has had host-networking footguns — worth
  confirming UDP 10000-20000 actually reaches the container.
- **`on_enter` never fired the greeting.** Check agent logs for
  `on_enter` entry + `generate_reply` being called. The deterministic
  startup-context prefetch could be stalling if Qdrant blocks.
- **TTS not publishing an audio track.** Agent joined the room but
  never published audio (SDK regression, permission, or session
  setup issue).

First triage: `make tail --grep "on_enter|generate_reply|publish|track"`
during a fresh inbound call. If `on_enter` fired but no audio left the
agent, it's media plane. If `on_enter` errored, agent side. If no
`on_enter` at all, the job never ran `on_enter` (session setup issue).

Deferred to the next Claude session per Eric's instruction.

## Next-up work (roughly prioritized)

### High-leverage, soon
1. **Re-enable `schedule_callback`** — blocks any voice-call callback
   feature. Preferred path is the OpenClaw CLI verb redesign documented
   in `openclaw-livekit-agent-sdk/TODO.md`. Requires a CLI change
   outside this monorepo.
2. **Drift detection** — cron that reads `config/*.json` and compares
   to `lk sip ... list --json` output. Alerts on mismatch. Catches the
   "someone CLI'd around the checked-in config" class of bug.
3. **CI on PR** — `.github/workflows/ci.yml` running `make test` +
   shellcheck on scripts. Monorepo change only.

### Hardening (medium-term)
4. Discord webhook on `make health --json` failures (cron-runnable today).
5. Aoi gets her own Discord room (currently shares Nyla's channel —
   `AgentConfig.discord_room` just needs a new channel ID).
6. Containerize the Python agents if we move off Mac. Currently
   launchd-managed; `docker-compose.yaml` handles infrastructure only.
7. Redis in compose (stop the brew redis service dependency).

### Deferred / unknowns
- Outbound call path (agent dials Eric). Outbound trunk
  `ST_CoEHgW6A7sUg` exists but no agent tool currently dials through
  it — callback scheduling is the canonical consumer and it's disabled.
- Per-agent quiet-hours / callback-allowlist tuning beyond the
  current shared defaults in `constants.py`.
- Aoi's allowlist (currently `{yumi, rin, aoi, momo, nyla}`) may
  need adjustment as Eric uses her and finds gaps.

## Migration debts

- Five individual GitHub repos (`ericmey/openclaw-livekit-agent-*`,
  `ericmey/openclaw-livekit-sip`) are still live with identical content
  to what's imported here as subtrees. They should be renamed with
  `-archived-` suffix and their READMEs updated to point at this
  monorepo. Pending as a cleanup step after the cutover settles.
- `~/Projects/_archive/openclaw-livekit-*/` contains the pre-cutover
  working trees. Kept for legacy reference (commit history in the
  archived repos is also available). Safe to delete after a
  reasonable soak period.
