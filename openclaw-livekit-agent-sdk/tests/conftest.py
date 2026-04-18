"""Shared fixtures for SDK tests."""

import pytest
from livekit.agents import Agent

from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin
from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin
from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin
from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin


class ComposedAgent(
    CoreToolsMixin,
    MemoryToolsMixin,
    SessionsToolsMixin,
    AcademyToolsMixin,
    Agent,
):
    """Test agent with all mixins composed."""

    def __init__(self) -> None:
        super().__init__(instructions="test persona")
        self._caller_from: str | None = "+15551234567"


@pytest.fixture
def agent() -> ComposedAgent:
    return ComposedAgent()
