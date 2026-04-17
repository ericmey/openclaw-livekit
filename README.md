# openclaw-livekit-agent-sdk

Shared Python runtime for the OpenClaw LiveKit voice agents. Provides the
worker bootstrap, telemetry / trace / transcript writers, tool mixins
(time, weather, memory, sessions, academy), and the post-call review
pipeline that feeds Rin's review queue.

This is the common substrate the persona agents (Aoi, Nyla, Party) all
import from.

## Status

Personal project — shared publicly for reference and portfolio. Not
actively maintained as an open-source community project; issues and PRs
may not be reviewed.

## Requirements

- Python **3.12.13** (pinned in `.python-version`)
- `uv` for lockfile operations

## Rebuild

```bash
uv pip sync requirements.lock
pip install -e .
```

See [AGENTS.md](AGENTS.md) for the full rebuild / lockfile regeneration
procedure.

## Sibling projects

- [openclaw-livekit-agent-aoi](https://github.com/ericmey/openclaw-livekit-agent-aoi) — Aoi persona (Gemini 2.5 realtime)
- [openclaw-livekit-agent-nyla](https://github.com/ericmey/openclaw-livekit-agent-nyla) — Nyla persona (Gemini 2.5 realtime)
- [openclaw-livekit-agent-party](https://github.com/ericmey/openclaw-livekit-agent-party) — chained STT/LLM/TTS baseline
- [openclaw-livekit-bridge](https://github.com/ericmey/openclaw-livekit-bridge) — Twilio ↔ LiveKit telephony bridge

## License

MIT — see [LICENSE](LICENSE).
