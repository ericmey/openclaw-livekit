"""Tests for the Party voice agent (chained STT/LLM/TTS, Harem World line)."""

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
        assert hasattr(agent_module, "PartyAgent")

    def test_server_is_agent_server(self, agent_module):
        from livekit.agents.worker import AgentServer
        assert isinstance(agent_module.server, AgentServer)


class TestAgentClass:
    """Verify the PartyAgent class composition."""

    def test_inherits_core_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.core import CoreToolsMixin
        assert issubclass(agent_module.PartyAgent, CoreToolsMixin)

    def test_inherits_memory_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.memory import MemoryToolsMixin
        assert issubclass(agent_module.PartyAgent, MemoryToolsMixin)

    def test_inherits_sessions_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.sessions import SessionsToolsMixin
        assert issubclass(agent_module.PartyAgent, SessionsToolsMixin)

    def test_inherits_academy_tools(self, agent_module):
        from openclaw_livekit_agent_sdk.tools.academy import AcademyToolsMixin
        assert issubclass(agent_module.PartyAgent, AcademyToolsMixin)

    def test_config_is_nyla_identity(self, agent_module):
        """Harem World line uses Nyla's operational identity — same person,
        different voice engine."""
        cfg = agent_module.PartyAgent.config
        assert cfg.agent_name == "nyla"
        assert cfg.memory_agent_tag == "nyla-voice"
        assert cfg.discord_room.startswith("channel:")

    def test_construction_with_defaults(self, agent_module):
        agent = agent_module.PartyAgent(instructions="test")
        assert agent._caller_from is None

    def test_all_nine_tools_present(self, agent_module):
        agent = agent_module.PartyAgent(instructions="test")
        expected = [
            "get_current_time", "get_weather",
            "musubi_recent", "memory_store",
            "sessions_send", "sessions_spawn", "schedule_callback",
            "academy_selfie", "academy_send",
        ]
        for tool in expected:
            assert hasattr(agent, tool), f"Missing tool: {tool}"

    def test_openclaw_request_absent(self, agent_module):
        agent = agent_module.PartyAgent(instructions="test")
        attr = getattr(agent, "openclaw_request", None)
        assert not callable(attr), "openclaw_request was deleted in SDK cleanup"


class TestPersona:
    """Verify persona loading from prompts/system.md."""

    def test_prompt_file_exists(self):
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
        assert prompt_path.exists(), f"Persona file missing: {prompt_path}"

    def test_prompt_file_not_empty(self):
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
        content = prompt_path.read_text(encoding="utf-8").strip()
        assert len(content) > 100, "Persona file seems too short"

    def test_load_persona_function(self, agent_module):
        persona = agent_module._load_persona()
        assert isinstance(persona, str)
        assert len(persona) > 100


class TestSDKImports:
    """Verify SDK dependencies import cleanly."""

    def test_import_env(self):
        from openclaw_livekit_agent_sdk.env import load_env

    def test_import_telephony(self):
        from openclaw_livekit_agent_sdk.telephony import resolve_caller

    def test_import_trace(self):
        from openclaw_livekit_agent_sdk.trace import trace

    def test_import_transcript(self):
        from openclaw_livekit_agent_sdk.transcript import wire_transcript_logging


class TestProviderImports:
    """Verify chained pipeline provider imports."""

    def test_import_openai_stt(self):
        from livekit.plugins import openai as openai_plugin

    def test_import_silero_vad(self):
        from livekit.plugins import silero as silero_plugin

    def test_import_google_llm(self):
        from livekit.plugins import google as google_plugin

    def test_import_elevenlabs_tts(self):
        from livekit.plugins import elevenlabs as elevenlabs_plugin

    def test_import_end_call_tool(self):
        from livekit.agents.beta import EndCallTool
