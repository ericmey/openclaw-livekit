# openclaw-livekit-agent-nyla

Nyla voice agent — a realtime voice persona built on the LiveKit Agents SDK
and Google's Gemini 2.5 Flash Native Audio API. Registers as `phone-nyla`
with LiveKit; the livekit-sip container (bind-mounted config at
`../config/livekit-sip.yaml`) routes inbound PSTN calls to it via dispatch
rule.

Ships with both a voice entrypoint (`src/agent.py`) and a text-only
variant (`src/agent_text.py`) sharing model / tool / persona configuration
through `src/_shared.py`.

## Status

Personal project — shared publicly for reference and portfolio. Not
actively maintained as an open-source community project; issues and PRs
may not be reviewed.

## Requirements

- Python **3.12.13** (pinned in `.python-version`)
- A LiveKit server reachable at `LIVEKIT_URL`
- Google API key for Gemini
- The sibling SDK at [`../openclaw-livekit-agent-sdk`](../openclaw-livekit-agent-sdk)
  (resolved via path-based `[tool.uv.sources]`)

## Running

```bash
python src/agent.py dev    # development
python src/agent.py start  # production
```

See [../AGENTS.md](../AGENTS.md) for rebuild procedures, launchd
integration, and the required environment variables.

## Sibling subprojects (same monorepo)

- [`../openclaw-livekit-agent-sdk`](../openclaw-livekit-agent-sdk) — shared runtime
- [`../openclaw-livekit-agent-aoi`](../openclaw-livekit-agent-aoi) — sister persona
- [`../openclaw-livekit-agent-party`](../openclaw-livekit-agent-party) — chained-pipeline variant

## License

MIT — see [../LICENSE](../LICENSE).
