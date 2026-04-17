"""Tests for the Nyla voice agent (Gemini 3.1 Flash Live)."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def agent_module():
    return importlib.import_module("agent")


class TestModuleExports:
    """Verify the agent module exports what LiveKit expects."""

    def test_server_exists(self, agent_module):
        assert hasattr(agent_module, "server")

    def test_entrypoint_exists(self, agent_module):
        assert hasattr(agent_module, "entrypoint")
        assert callable(agent_module.entrypoint)

    def test_agent_class_exists(self, agent_module):
        assert hasattr(agent_module, "NylaAgent")

    def test_server_is_agent_server(self, agent_module):
        from livekit.agents.worker import AgentServer
        assert isinstance(agent_module.server, AgentServer)


class TestAgentClass:
    """Verify the NylaAgent class is properly composed."""

    def test_inherits_core_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin
        assert issubclass(agent_module.NylaAgent, CoreToolsMixin)

    def test_inherits_memory_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin
        assert issubclass(agent_module.NylaAgent, MemoryToolsMixin)

    def test_inherits_sessions_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin
        assert issubclass(agent_module.NylaAgent, SessionsToolsMixin)

    def test_inherits_academy_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin
        assert issubclass(agent_module.NylaAgent, AcademyToolsMixin)

    def test_construction_with_defaults(self, agent_module):
        agent = agent_module.NylaAgent(instructions="test")
        assert agent._caller_from is None

    def test_construction_with_caller(self, agent_module):
        agent = agent_module.NylaAgent(
            instructions="test",
            caller_from="+13175551234",
        )
        assert agent._caller_from == "+13175551234"

    def test_all_ten_tools_present(self, agent_module):
        agent = agent_module.NylaAgent(instructions="test")
        expected = [
            "get_current_time", "get_weather", "openclaw_request",
            "musubi_recent", "memory_store",
            "sessions_send", "sessions_spawn", "schedule_callback",
            "academy_selfie", "academy_send",
        ]
        for tool in expected:
            assert hasattr(agent, tool), f"Missing tool: {tool}"


class TestPersona:
    """Verify persona loading from prompts/system.md."""

    def test_prompt_file_exists(self):
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
        assert prompt_path.exists(), f"Persona file missing: {prompt_path}"

    def test_prompt_file_not_empty(self):
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
        content = prompt_path.read_text(encoding="utf-8").strip()
        assert len(content) > 100, "Persona file seems too short"

    def test_prompt_contains_nyla_identity(self):
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
        content = prompt_path.read_text(encoding="utf-8")
        assert "Nyla" in content, "Persona must mention Nyla"

    def test_load_persona_function(self):
        from _shared import load_persona
        persona = load_persona()
        assert isinstance(persona, str)
        assert len(persona) > 100
        assert "Nyla" in persona


class TestSDKImports:
    """Verify SDK dependencies import cleanly."""

    def test_import_core_tools(self):
        from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin

    def test_import_memory_tools(self):
        from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin

    def test_import_sessions_tools(self):
        from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin

    def test_import_academy_tools(self):
        from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin

    def test_import_env(self):
        from openclaw_livekit_agent_sdk.env import load_env

    def test_import_trace(self):
        from openclaw_livekit_agent_sdk.trace import trace

    def test_import_transcript(self):
        from openclaw_livekit_agent_sdk.transcript import wire_transcript_logging


class TestProviderImports:
    """Verify Gemini provider imports for this agent."""

    def test_import_google_plugin(self):
        from livekit.plugins import google as google_plugin

    def test_import_google_search(self):
        from livekit.plugins.google.tools import GoogleSearch

    def test_import_gemini_types(self):
        from google.genai import types as gemini_types

    def test_import_end_call_tool(self):
        from livekit.agents.beta import EndCallTool

    def test_import_agent_server(self):
        from livekit.agents.worker import AgentServer
