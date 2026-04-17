"""Unit tests for transport-agnostic caller resolution."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from livekit import rtc

from openclaw_livekit_agent_sdk.telephony import (
    CallerInfo,
    resolve_caller,
    _parse_bridge_metadata,
)


# -- bridge path --------------------------------------------------------


def test_parse_bridge_metadata_full_payload() -> None:
    info = _parse_bridge_metadata(
        '{"callSid": "CA123", "from": "+14155551234", "to": "+14155559999"}'
    )
    assert info == CallerInfo(
        call_id="CA123",
        caller_from="+14155551234",
        dialed_number="+14155559999",
        source="bridge",
    )


def test_parse_bridge_metadata_partial_payload_only_from() -> None:
    # "from" alone is enough to classify as bridge shape.
    info = _parse_bridge_metadata('{"from": "+14155551234"}')
    assert info is not None
    assert info.source == "bridge"
    assert info.caller_from == "+14155551234"
    assert info.call_id is None


def test_parse_bridge_metadata_returns_none_for_non_bridge_shape() -> None:
    # A SIP dispatch rule might pack unrelated routing info here.
    assert _parse_bridge_metadata('{"route": "vip", "source": "sip"}') is None


def test_parse_bridge_metadata_returns_none_for_empty() -> None:
    assert _parse_bridge_metadata(None) is None
    assert _parse_bridge_metadata("") is None


def test_parse_bridge_metadata_returns_none_for_malformed_json() -> None:
    assert _parse_bridge_metadata("not-json-at-all") is None
    assert _parse_bridge_metadata("{unterminated") is None


def test_parse_bridge_metadata_returns_none_for_non_dict_json() -> None:
    # JSON array instead of object — not bridge shape.
    assert _parse_bridge_metadata('["+14155551234"]') is None
    assert _parse_bridge_metadata('"just a string"') is None


# -- resolve_caller integration -----------------------------------------


def _make_ctx(metadata: str | None, participants: dict) -> MagicMock:
    """Build a fake JobContext sufficient for resolve_caller()."""
    ctx = MagicMock()
    ctx.job.metadata = metadata
    ctx.room.name = "test-room"
    ctx.room.remote_participants = participants
    return ctx


def _sip_participant(
    *,
    call_id: str = "abc123@sip",
    caller_from: str = "+14155551234",
    dialed: str = "+14155559999",
) -> SimpleNamespace:
    return SimpleNamespace(
        kind=rtc.ParticipantKind.PARTICIPANT_KIND_SIP,
        attributes={
            "sip.callID": call_id,
            "sip.from": caller_from,
            "sip.trunkPhoneNumber": dialed,
        },
    )


def _non_sip_participant() -> SimpleNamespace:
    # agent participant, not SIP — should be ignored by the scan.
    return SimpleNamespace(
        kind=rtc.ParticipantKind.PARTICIPANT_KIND_AGENT,
        attributes={},
    )


@pytest.mark.asyncio
async def test_resolve_caller_bridge_path_skips_sip_lookup() -> None:
    ctx = _make_ctx(
        metadata='{"callSid": "CA999", "from": "+14155551234", "to": "+14155559999"}',
        participants={},  # deliberately empty — should not be consulted
    )
    info = await resolve_caller(ctx)
    assert info.source == "bridge"
    assert info.call_id == "CA999"


@pytest.mark.asyncio
async def test_resolve_caller_sip_path_with_participant_present() -> None:
    ctx = _make_ctx(
        metadata=None,
        participants={"p1": _sip_participant(call_id="SIP-ABC")},
    )
    info = await resolve_caller(ctx, sip_wait_seconds=0.5)
    assert info.source == "sip"
    assert info.call_id == "SIP-ABC"
    assert info.caller_from == "+14155551234"


@pytest.mark.asyncio
async def test_resolve_caller_sip_path_ignores_non_sip_participants() -> None:
    ctx = _make_ctx(
        metadata=None,
        participants={
            "agent1": _non_sip_participant(),
            "sip1": _sip_participant(call_id="SIP-XYZ"),
        },
    )
    info = await resolve_caller(ctx, sip_wait_seconds=0.5)
    assert info.source == "sip"
    assert info.call_id == "SIP-XYZ"


@pytest.mark.asyncio
async def test_resolve_caller_sip_path_with_dispatch_metadata() -> None:
    # Dispatch rule set non-bridge metadata; SIP participant has caller info.
    ctx = _make_ctx(
        metadata='{"route": "vip", "source": "sip"}',
        participants={"p1": _sip_participant(call_id="SIP-DISP")},
    )
    info = await resolve_caller(ctx, sip_wait_seconds=0.5)
    assert info.source == "sip"
    assert info.call_id == "SIP-DISP"


@pytest.mark.asyncio
async def test_resolve_caller_unknown_when_nothing_resolves() -> None:
    ctx = _make_ctx(metadata=None, participants={})
    info = await resolve_caller(ctx, sip_wait_seconds=0.1)
    assert info.source == "unknown"
    assert info.call_id is None
    assert info.caller_from is None
    assert info.dialed_number is None


@pytest.mark.asyncio
async def test_resolve_caller_unknown_with_only_non_sip_participants() -> None:
    ctx = _make_ctx(
        metadata=None,
        participants={"agent1": _non_sip_participant()},
    )
    info = await resolve_caller(ctx, sip_wait_seconds=0.1)
    assert info.source == "unknown"
