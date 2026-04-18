"""OpenClaw gateway config lookup — port + auth token from openclaw.json."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("openclaw-livekit.agent")

_OPENCLAW_CONFIG_PATH = (
    Path(os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
    / "openclaw.json"
)

_gateway_cache: tuple[int, str] | None = None


def _resolve_env_var(value: Any) -> Any:
    """Expand ${FOO} references from the process env."""
    if isinstance(value, str):

        def _sub(match: re.Match[str]) -> str:
            return os.environ.get(match.group(1), "")

        return re.sub(r"\$\{([^}]+)\}", _sub, value)
    return value


def get_gateway_config() -> tuple[int, str] | None:
    """Return ``(port, token)`` for the local OpenClaw gateway, or None."""
    global _gateway_cache
    if _gateway_cache is not None:
        return _gateway_cache

    try:
        raw = json.loads(_OPENCLAW_CONFIG_PATH.read_text(encoding="utf-8"))
        gw = raw.get("gateway")
        if isinstance(gw, dict) and "$include" in gw:
            include_path = _OPENCLAW_CONFIG_PATH.parent / gw["$include"]
            gw = json.loads(include_path.read_text(encoding="utf-8"))
        if not isinstance(gw, dict):
            logger.warning("openclaw.json has no gateway section")
            return None
        port = gw.get("port")
        auth = gw.get("auth") or {}
        token = _resolve_env_var(auth.get("token"))
        if isinstance(port, int) and isinstance(token, str) and token:
            _gateway_cache = (port, token)
            return _gateway_cache
        logger.warning(
            "gateway config incomplete: port=%r token_set=%s",
            port,
            bool(token),
        )
        return None
    except Exception as err:
        logger.warning("failed to read openclaw.json: %s", err)
        return None
