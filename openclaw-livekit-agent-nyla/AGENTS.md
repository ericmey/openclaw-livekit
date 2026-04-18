# openclaw-livekit-agent-nyla

Nyla voice agent — Gemini 2.5 Flash Native Audio, voice "Leda".

## Overview

Real-time voice agent powered by Google's Gemini 2.5 Flash Native Audio API.
Registers as `phone-nyla` with LiveKit. Uses the `-latest` model alias to
track Google's stable pointer instead of dated previews that can break
without warning. The openclaw-livekit bridge dispatches inbound Twilio calls
to this agent by name.

## Project Structure

```
openclaw-livekit-agent-nyla/
  src/agent.py          # Entrypoint — the LiveKit agent
  src/__init__.py       # Package marker
  prompts/system.md     # Nyla's voice persona prompt
  tests/test_agent.py   # Tests (run with pytest)
  pyproject.toml        # Package definition
  .env.example          # Required environment variables
```

## Dependencies

Depends on `openclaw-livekit-agent-sdk` for shared tools (time, weather,
memory, sessions, academy) and utility modules (env, trace, transcript).
The dependency is resolved via a path-based `[tool.uv.sources]` entry in
`pyproject.toml`, so the SDK is always editable against its sibling
checkout at `../openclaw-livekit-agent-sdk`.

## Pinned runtime

- Python: **3.12.13** (see `.python-version`)
- Full transitive tree: `requirements.lock` (includes the local SDK as
  `-e ../openclaw-livekit-agent-sdk`)

### Rebuild from the lockfile

From a fresh venv on Python 3.12.13:

```bash
cd ~/.openclaw/extensions/openclaw-livekit-agent-nyla
uv pip sync requirements.lock
pip install -e .
```

Or from `extensions/`:

```bash
make install-voice-agents   # editable install of all three packages
```

After rebuilding, cycle the launchd agent so it picks up the new venv:

```bash
launchctl bootout  gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-agent-nyla.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-agent-nyla.plist
```

Then run a real phone test — venv changes are not proven until a call
lands transcripts, telemetry, and a call-review in `~/.openclaw/logs/voice/`.

### Regenerate the lockfile

Only after you deliberately change `pyproject.toml` dependencies:

```bash
cd ~/.openclaw/extensions/openclaw-livekit-agent-nyla
uv pip compile pyproject.toml -o requirements.lock
```

Or from `extensions/`:

```bash
make lock-voice-agents
```

Commit the updated lockfile in the same commit as the `pyproject.toml`
change.

## Running

```bash
# Development (auto-reload, single worker)
python src/agent.py dev

# Production (Node bridge spawns this)
python src/agent.py start
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `LIVEKIT_URL` | LiveKit server WebSocket URL |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `GOOGLE_API_KEY` | Google API key for Gemini 2.5 Live |

## References

- [LiveKit Agents SDK docs](https://docs.livekit.io/agents/)
- [Gemini Live API](https://ai.google.dev/gemini-api/docs/live)
