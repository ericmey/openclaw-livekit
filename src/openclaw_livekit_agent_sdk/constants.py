"""Shared constants — Discord channels, sanitizer regexes."""

from __future__ import annotations

import re

# Mizuki's Discord channel — shared by academy_send and academy_selfie
# across all voice agents (Mizuki is the orchestrator, not a voice).
MIZUKI_DISCORD_CHANNEL = "1486181468311916674"

# Household Discord targets. Individual agents point at their own room
# via ``AgentConfig.discord_room``; for now every agent uses Nyla's
# channel until per-agent rooms exist. Eric's DM is agent-independent.
NYLA_DISCORD_ROOM = "channel:1480975791977140285"
ERIC_DISCORD_DM = "user:527362260486586368"

# schedule_callback sanitizer — strip shell-meaningful characters from
# caller-supplied text before embedding it in a scheduled command.
SANITIZE_RE = re.compile(r"[\"`$\\!;|&<>(){}[\]\n\r]")
DELAY_RE = re.compile(r"^\d+[mhd]$")
E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")


def sanitize(text: str) -> str:
    """Strip shell-meaningful characters."""
    return SANITIZE_RE.sub("", text).strip()
