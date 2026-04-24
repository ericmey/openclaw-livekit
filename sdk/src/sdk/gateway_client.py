"""OpenClaw gateway config lookup — port + auth token from env vars.

The gateway itself is an external OpenClaw service the agents call into
(for memory store, session management, etc.). The agent doesn't know or
care where the gateway lives on disk — the deploy env sets
``GATEWAY_PORT`` and ``GATEWAY_AUTH_TOKEN`` directly.

If either env var is missing, ``get_gateway_config`` returns None and
the caller is expected to treat gateway functionality as unavailable.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("openclaw-livekit.agent")

_gateway_cache: tuple[int, str] | None = None


def get_gateway_config() -> tuple[int, str] | None:
    """Return ``(port, token)`` for the gateway, or None if not configured.

    The result is cached for the lifetime of the process. If you rotate
    secrets and need the new values picked up without restarting the
    agent, call ``invalidate_gateway_cache()`` first.
    """
    global _gateway_cache
    if _gateway_cache is not None:
        return _gateway_cache

    port_str = os.environ.get("GATEWAY_PORT", "").strip()
    token = os.environ.get("GATEWAY_AUTH_TOKEN", "").strip()

    if not port_str or not token:
        logger.warning(
            "gateway config unavailable: GATEWAY_PORT set=%s GATEWAY_AUTH_TOKEN set=%s",
            bool(port_str),
            bool(token),
        )
        return None

    try:
        port = int(port_str)
    except ValueError:
        logger.warning("GATEWAY_PORT is not a valid integer: %r", port_str)
        return None

    _gateway_cache = (port, token)
    return _gateway_cache


def invalidate_gateway_cache() -> None:
    """Clear the cached gateway config so the next call re-reads env.

    Call this after rotating ``GATEWAY_AUTH_TOKEN`` or ``GATEWAY_PORT``
    if you need the new values picked up without restarting the process.
    """
    global _gateway_cache
    _gateway_cache = None
