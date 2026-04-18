"""dev-mode .env loading for the agent process.

Loads ``./.env`` (next to the agent script) for agent-specific knobs.
In production, the launchd plist exports all vars directly before
spawning the worker, so .env files are a dev-mode convenience.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    """Load agent-local ``./.env`` and alias provider-specific keys."""
    load_dotenv(Path.cwd() / ".env")

    # The xAI plugin reads XAI_API_KEY. Alias from XAI_REALTIME_API_KEY if
    # the deploy env used that name.
    if not os.environ.get("XAI_API_KEY") and os.environ.get("XAI_REALTIME_API_KEY"):
        os.environ["XAI_API_KEY"] = os.environ["XAI_REALTIME_API_KEY"]

    # ElevenLabs plugin reads ELEVEN_API_KEY. Alias from ELEVENLABS_API_KEY.
    if not os.environ.get("ELEVEN_API_KEY") and os.environ.get("ELEVENLABS_API_KEY"):
        os.environ["ELEVEN_API_KEY"] = os.environ["ELEVENLABS_API_KEY"]
