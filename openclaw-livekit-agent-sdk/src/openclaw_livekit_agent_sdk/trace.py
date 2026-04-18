"""Out-of-band debug trace — bypasses multiprocessing log bridge.

livekit-agents pre-forks job workers via multiprocessing.spawn and bridges
their stdlib logs back to the parent over IPC. The bridge drops records from
workers that were spawned after the first job cycle. This writes a line to
a file on disk regardless of whether the log bridge cooperates.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

_OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
_TRACE_PATH = _OPENCLAW_HOME / "logs" / "voice" / "agent.trace"


def trace(msg: str) -> None:
    """Append a timestamped trace line. Never raises."""
    try:
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} pid={os.getpid()} {msg}\n")
    except Exception:
        pass
