"""openclaw CLI spawner — fire-and-forget subprocess for tool methods.

Python equivalent of vcr's fireAndForgetArgs(): find the openclaw binary,
spawn it with an explicit argv list (no shell, no injection surface),
fully detach so the phone call ending doesn't kill the subprocess.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger("openclaw-livekit.agent")

_openclaw_bin_cache: str | None = None


def _resolve_openclaw_bin() -> str:
    """Locate the ``openclaw`` CLI. Env var wins, then PATH, then bare name."""
    global _openclaw_bin_cache
    if _openclaw_bin_cache is not None:
        return _openclaw_bin_cache
    env_path = os.environ.get("OPENCLAW_BIN")
    if env_path:
        _openclaw_bin_cache = env_path
        return env_path
    which = shutil.which("openclaw")
    if which:
        _openclaw_bin_cache = which
        return which
    _openclaw_bin_cache = "openclaw"
    return _openclaw_bin_cache


def fire_and_forget(args: list[str]) -> None:
    """Spawn ``openclaw <args...>`` fully detached. Raises on spawn failure.

    Spawn failure (FileNotFoundError when the binary can't be found, or
    PermissionError on a non-executable) IS raised. Tool callers MUST wrap
    in try/except and return an honest error to the model.
    """
    bin_path = _resolve_openclaw_bin()
    subprocess.Popen(
        [bin_path, *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    logger.info("[voice-tools] spawned: openclaw %s", " ".join(args[:3]))
