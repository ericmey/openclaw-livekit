"""Tests for trace module."""

from sdk.trace import trace


def test_trace_callable():
    """trace is a callable function."""
    assert callable(trace)


def test_trace_does_not_raise():
    """trace never raises, even on weird input."""
    trace("test message")
    trace("")
    trace("unicode: 日本語 emoji: 🔥")
