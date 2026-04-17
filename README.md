# openclaw-livekit-agent-nyla

Nyla voice agent — a realtime voice persona built on the LiveKit Agents SDK
and Google's Gemini 2.5 Flash Native Audio API. Registers as `phone-nyla`
with LiveKit; the [bridge](https://github.com/ericmey/openclaw-livekit-bridge)
dispatches per-call rooms to it.

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
- Sibling [openclaw-livekit-agent-sdk](https://github.com/ericmey/openclaw-livekit-agent-sdk)
  checked out at `../openclaw-livekit-agent-sdk` (resolved via path-based
  `[tool.uv.sources]`)

## Running

```bash
python src/agent.py dev    # development
python src/agent.py start  # production
```

See [AGENTS.md](AGENTS.md) for rebuild procedures, launchd integration,
and the required environment variables.

## Sibling projects

- [openclaw-livekit-agent-sdk](https://github.com/ericmey/openclaw-livekit-agent-sdk) — shared runtime
- [openclaw-livekit-agent-aoi](https://github.com/ericmey/openclaw-livekit-agent-aoi) — sister persona
- [openclaw-livekit-agent-party](https://github.com/ericmey/openclaw-livekit-agent-party) — chained-pipeline variant
- [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge) — Twilio ↔ LiveKit bridge

## License

MIT — see [LICENSE](LICENSE).
