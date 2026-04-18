# openclaw-livekit-agent-aoi

Aoi voice agent — Gemini 2.5 Flash Live, voice "Leda".

Currently running Nyla's persona for A/B testing against the Gemini 3.1
agent. Once a model is selected, this becomes the real Aoi agent with
her own personality and prompts.

## Overview

Real-time voice agent powered by Google's Gemini 2.5 Flash Native Audio API.
Registers as `phone-aoi` with LiveKit. Uses the `-latest` model alias to
track Google's stable pointer instead of dated previews that can break
without warning.

## Project Structure

```
openclaw-livekit-agent-aoi/
  src/agent.py          # Entrypoint — the LiveKit agent
  src/__init__.py       # Package marker
  prompts/system.md     # Voice persona prompt (currently Nyla for testing)
  tests/test_agent.py   # Tests (run with pytest)
  pyproject.toml        # Package definition
  .env.example          # Required environment variables
```

## Dependencies

Depends on `openclaw-livekit-agent-sdk` for shared tools and utilities.
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
cd ~/.openclaw/extensions/openclaw-livekit-agent-aoi
uv pip sync requirements.lock
pip install -e .
```

Or from `extensions/`:

```bash
make install-voice-agents   # editable install of all three packages
```

After rebuilding, cycle the launchd agent so it picks up the new venv:

```bash
launchctl bootout  gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-agent-aoi.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-agent-aoi.plist
```

Then run a real phone test — venv changes are not proven until a call
lands transcripts, telemetry, and a call-review in `~/.openclaw/logs/voice/`.

### Regenerate the lockfile

Only after you deliberately change `pyproject.toml` dependencies:

```bash
cd ~/.openclaw/extensions/openclaw-livekit-agent-aoi
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
python src/agent.py dev    # Development
python src/agent.py start  # Production
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `LIVEKIT_URL` | LiveKit server WebSocket URL |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `GOOGLE_API_KEY` | Google API key for Gemini 2.5 Live |
