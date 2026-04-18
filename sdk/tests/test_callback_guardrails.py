"""Tests for schedule_callback guardrails.

Uses the composed ``agent`` fixture and the dry-run env var so calls
never actually spawn the OpenClaw CLI. The assertions focus on the
guardrail strings the tool returns BEFORE scheduling — the scheduling
side effect is covered separately.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sdk.constants import (
    CALLBACK_QUIET_END_HOUR,
    CALLBACK_QUIET_START_HOUR,
    ERIC_TZ,
    is_quiet_hour,
    parse_delay_seconds,
)

from sdk import cli_spawner

# --- helper-level ------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1m", 60),
        ("30m", 1800),
        ("1h", 3600),
        ("2h", 7200),
        ("1d", 86400),
        ("garbage", -1),
        ("", -1),
        ("5s", -1),
    ],
)
def test_parse_delay_seconds(text: str, expected: int) -> None:
    assert parse_delay_seconds(text) == expected


def test_is_quiet_hour_inside_window() -> None:
    assert is_quiet_hour(23) is True
    assert is_quiet_hour(2) is True
    assert is_quiet_hour(CALLBACK_QUIET_START_HOUR) is True


def test_is_quiet_hour_outside_window() -> None:
    assert is_quiet_hour(CALLBACK_QUIET_END_HOUR) is False
    assert is_quiet_hour(12) is False
    assert is_quiet_hour(21) is False


# --- end-to-end through schedule_callback -----------------------------


@pytest.fixture(autouse=True)
def dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """All tests in this file run under dry-run so no real CLI spawns."""
    monkeypatch.setenv(cli_spawner.DRY_RUN_ENV, "1")


@pytest.mark.asyncio
async def test_rejects_delay_under_minimum(agent) -> None:
    # DELAY_RE accepts "1m" but not "0m" — use a valid-format-too-short
    # delay. Actually "1m" == MIN so we need something smaller that still
    # parses. Since the regex enforces m/h/d suffixes, the only way to
    # go below 1 minute is to shorten the minimum or use a zero count.
    # "0m" parses as 0 seconds, which is below the floor.
    result = await agent.schedule_callback(delay="0m", reason="x")
    assert "minimum delay" in result.lower()


@pytest.mark.asyncio
async def test_rejects_delay_over_maximum(agent) -> None:
    # 2 days > 24 hour cap.
    result = await agent.schedule_callback(delay="2d", reason="x")
    assert "maximum" in result.lower()


@pytest.mark.asyncio
async def test_short_delay_requires_confirmation(agent) -> None:
    """A 1-minute callback asks for confirmation; it's close enough to
    'call me back right now' to be worth a second check."""
    result = await agent.schedule_callback(delay="1m", reason="x")
    assert "confirm" in result.lower()


@pytest.mark.asyncio
async def test_short_delay_succeeds_when_confirmed(agent) -> None:
    result = await agent.schedule_callback(delay="1m", reason="x", confirmed=True)
    assert "scheduled" in result.lower()


@pytest.mark.asyncio
async def test_different_phone_requires_confirmation(agent) -> None:
    result = await agent.schedule_callback(
        delay="30m",
        reason="x",
        phone="+15550000000",  # not the caller's number
    )
    assert "confirm" in result.lower()


@pytest.mark.asyncio
async def test_different_phone_succeeds_when_confirmed(agent) -> None:
    result = await agent.schedule_callback(
        delay="30m",
        reason="x",
        phone="+15550000000",
        confirmed=True,
    )
    assert "scheduled" in result.lower()


@pytest.mark.asyncio
async def test_quiet_hours_require_confirmation(agent) -> None:
    """Pin local time to 23:00 so any short-ish delay lands in quiet
    hours. The composed agent's caller_from is +15551234567 and the
    delay is safely above CALLBACK_SHORT_DELAY_S and safely below quiet
    window's start, so the only guardrail that should trip is quiet hours."""
    fake_now_local = datetime(2026, 4, 18, 23, 0, tzinfo=ERIC_TZ)
    fake_now_utc = fake_now_local.astimezone(UTC)

    real_datetime = datetime

    class _FakeDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fake_now_utc if tz else fake_now_local

    with patch(
        "tools.sessions.datetime",
        _FakeDatetime,
    ):
        result = await agent.schedule_callback(delay="30m", reason="x")

    assert "quiet hours" in result.lower()


@pytest.mark.asyncio
async def test_successful_schedule_has_actionable_language(agent) -> None:
    """The happy path returns a confirmation the model can read aloud."""
    result = await agent.schedule_callback(delay="30m", reason="check deploy")
    assert "scheduled" in result.lower()
    assert "30m" in result
