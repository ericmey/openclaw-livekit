"""Tests for AcademyToolsMixin — academy_selfie, academy_send."""

from tools.academy import AcademyToolsMixin


def test_academy_mixin_has_academy_selfie():
    assert hasattr(AcademyToolsMixin, "academy_selfie")
    assert callable(AcademyToolsMixin.academy_selfie)


def test_academy_mixin_has_academy_send():
    assert hasattr(AcademyToolsMixin, "academy_send")
    assert callable(AcademyToolsMixin.academy_send)


def test_composed_agent_has_academy_tools(agent):
    """Academy tools are discoverable on a composed agent instance."""
    assert hasattr(agent, "academy_selfie")
    assert hasattr(agent, "academy_send")
