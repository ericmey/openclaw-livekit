"""Shared fixtures for agent tests."""

import sys
from pathlib import Path

import pytest

# Add src/ to path so `import agent` works from tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
