"""Tests for env loading module."""

from sdk.env import load_env


def test_load_env_callable():
    """load_env is a callable function."""
    assert callable(load_env)
