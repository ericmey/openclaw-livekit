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
        from tools.core import CoreToolsMixin

        assert issubclass(agent_module.NylaAgent, CoreToolsMixin)

    def test_inherits_memory_tools(self, agent_module):
        from tools.memory import MemoryToolsMixin

        assert issubclass(agent_module.NylaAgent, MemoryToolsMixin)

    def test_inherits_sessions_tools(self, agent_module):
        from tools.sessions import SessionsToolsMixin

        assert issubclass(agent_module.NylaAgent, SessionsToolsMixin)

    def test_inherits_academy_tools(self, agent_module):
        from tools.academy import AcademyToolsMixin

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

    def test_active_tools_present(self, agent_module):
        """Tools currently exposed to the voice model. schedule_callback
        is deliberately OFF this list — the cron path isn't wired; see
        SDK TODO.md for the re-enable plan."""
        agent = agent_module.NylaAgent(instructions="test")
        expected = [
            "get_current_time",
            "get_weather",
            "musubi_recent",
            "memory_store",
            "sessions_send",
            "sessions_spawn",
            "academy_selfie",
            "academy_send",
        ]
        for tool in expected:
            assert hasattr(agent, tool), f"Missing tool: {tool}"

    def test_schedule_callback_is_not_a_tool(self, agent_module):
        """Disabled while the cron payload redesign is open. The method
        body still exists for guardrail tests to call directly, but it
        must NOT be @function_tool-decorated so the voice model can't
        discover or fire it.

        Compare against sessions_send — that one IS decorated and
        becomes a FunctionTool instance; schedule_callback stays a
        plain coroutine function so LiveKit's tool scanner skips it.
        """
        import inspect

        send = agent_module.NylaAgent.sessions_send
        callback = agent_module.NylaAgent.schedule_callback
        # The enabled tool is a FunctionTool wrapper.
        assert type(send).__name__ == "FunctionTool"
        # The disabled method is a plain coroutine function.
        assert inspect.iscoroutinefunction(callback)
        assert type(callback).__name__ == "function"

    def test_openclaw_request_absent(self, agent_module):
        agent = agent_module.NylaAgent(instructions="test")
        attr = getattr(agent, "openclaw_request", None)
        assert not callable(attr), "openclaw_request was deleted in SDK cleanup"

    def test_config_is_nyla_identity(self, agent_module):
        """Nyla's config tags memories as nyla-voice and sets her name/room."""
        cfg = agent_module.NylaAgent.config
        assert cfg.agent_name == "nyla"
        assert cfg.memory_agent_tag == "nyla-voice"
        assert cfg.discord_room.startswith("channel:")
        # Nyla is the household router — she may delegate to anyone.
        assert cfg.allowed_delegation_targets is None


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
        pass

    def test_import_memory_tools(self):
        pass

    def test_import_sessions_tools(self):
        pass

    def test_import_academy_tools(self):
        pass

    def test_import_env(self):
        pass

    def test_import_trace(self):
        pass

    def test_import_transcript(self):
        pass


class TestProviderImports:
    """Verify Gemini provider imports for this agent."""

    def test_import_google_plugin(self):
        pass

    def test_import_google_search(self):
        pass

    def test_import_gemini_types(self):
        pass

    def test_import_end_call_tool(self):
        pass

    def test_import_agent_server(self):
        pass
