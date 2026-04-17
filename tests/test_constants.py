"""Tests for constants module."""

from openclaw_livekit_agent_sdk.constants import (
    DELAY_RE,
    E164_RE,
    ERIC_DISCORD_DM,
    MIZUKI_DISCORD_CHANNEL,
    NYLA_DISCORD_ROOM,
    SANITIZE_RE,
    SESSIONS_DELIVERY_TARGETS,
    sanitize,
)


def test_discord_channels_are_numeric_strings():
    assert MIZUKI_DISCORD_CHANNEL.isdigit()
    assert NYLA_DISCORD_ROOM.startswith("channel:")
    assert ERIC_DISCORD_DM.startswith("user:")


def test_delivery_targets_has_room_and_dm():
    assert "room" in SESSIONS_DELIVERY_TARGETS
    assert "dm" in SESSIONS_DELIVERY_TARGETS


def test_sanitize_strips_shell_chars():
    assert sanitize('hello "world"') == "hello world"
    assert sanitize("safe text") == "safe text"
    assert sanitize("rm -rf /; echo bad") == "rm -rf / echo bad"


def test_delay_regex_accepts_valid():
    assert DELAY_RE.match("5m")
    assert DELAY_RE.match("30m")
    assert DELAY_RE.match("1h")
    assert DELAY_RE.match("2d")


def test_delay_regex_rejects_invalid():
    assert not DELAY_RE.match("5")
    assert not DELAY_RE.match("m")
    assert not DELAY_RE.match("5x")
    assert not DELAY_RE.match("")


def test_e164_regex_accepts_valid():
    assert E164_RE.match("+13175551234")
    assert E164_RE.match("+442071234567")


def test_e164_regex_rejects_invalid():
    assert not E164_RE.match("3175551234")
    assert not E164_RE.match("+0123")
    assert not E164_RE.match("")
