"""Two-layer .env loading for OpenClaw LiveKit agents.

Layer 1: ~/.openclaw/.env — shared OpenClaw secrets (mode 600).
Layer 2: ./.env (next to the agent script) — agent-specific knobs.

In production, the Node side exports all vars directly before spawning
the worker, so .env files are a dev-mode convenience.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    """Load environment from the two-layer .env chain and alias keys."""
    openclaw_env = (
        Path(os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
        / ".env"
    )
    load_dotenv(openclaw_env)
    load_dotenv(Path.cwd() / ".env")

    # The xAI plugin reads XAI_API_KEY. The existing openclaw .env file has
    # XAI_REALTIME_API_KEY (the name voice-call-realtime uses). Alias it so a
    # single secret works for both extensions during the cutover window.
    if not os.environ.get("XAI_API_KEY") and os.environ.get("XAI_REALTIME_API_KEY"):
        os.environ["XAI_API_KEY"] = os.environ["XAI_REALTIME_API_KEY"]

    # ElevenLabs plugin reads ELEVEN_API_KEY. Our .env has ELEVENLABS_API_KEY.
    if not os.environ.get("ELEVEN_API_KEY") and os.environ.get("ELEVENLABS_API_KEY"):
        os.environ["ELEVEN_API_KEY"] = os.environ["ELEVENLABS_API_KEY"]
