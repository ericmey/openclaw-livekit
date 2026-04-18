# openclaw-livekit-agent-party

Chained voice agent — baseline for multi-agent room experiments.

## Overview

Uses a chained pipeline instead of a single realtime model:

- **STT:** OpenAI Whisper-1 (speech-to-text)
- **VAD:** Silero (segments caller audio into utterances)
- **LLM:** Gemini 3.1 Flash Lite (text reasoning)
- **TTS:** ElevenLabs eleven_v3 (speech synthesis)

Starts as a basic single-agent baseline. The goal is to evolve this into
a multi-agent chat room where multiple characters can participate.

Registers as `phone-party` with LiveKit.

## Project Structure

```
openclaw-livekit-agent-party/
  src/agent.py          # Entrypoint — the LiveKit agent
  src/__init__.py       # Package marker
  prompts/system.md     # Voice persona prompt
  tests/test_agent.py   # Tests (run with pytest)
  pyproject.toml        # Package definition
  .env.example          # Required environment variables
```

## Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ../openclaw-livekit-agent-sdk
pip install -e .
```

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
| `GOOGLE_API_KEY` | Google API key for Gemini LLM |
| `ELEVEN_API_KEY` | ElevenLabs API key for TTS |
