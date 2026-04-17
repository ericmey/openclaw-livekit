"""Shared constants — Discord channels, delivery targets, sanitizer regexes."""

from __future__ import annotations

import re

# Mizuki's Discord channel — shared by academy_send and academy_selfie.
MIZUKI_DISCORD_CHANNEL = "1486181468311916674"

# Delivery targets for sessions_send / sessions_spawn.
NYLA_DISCORD_ROOM = "channel:1480975791977140285"
ERIC_DISCORD_DM = "user:527362260486586368"

SESSIONS_DELIVERY_TARGETS: dict[str, str] = {
    "room": NYLA_DISCORD_ROOM,
    "dm": ERIC_DISCORD_DM,
}

# schedule_callback sanitizer — strip shell-meaningful characters from
# caller-supplied text before embedding it in a scheduled command.
SANITIZE_RE = re.compile(r"[\"`$\\!;|&<>(){}[\]\n\r]")
DELAY_RE = re.compile(r"^\d+[mhd]$")
E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")


def sanitize(text: str) -> str:
    """Strip shell-meaningful characters."""
    return SANITIZE_RE.sub("", text).strip()
