"""Per-call telemetry capture — structured event + metrics logging.

Hooks into AgentSession events to capture:
- Per-turn latency (e2e, LLM TTFT, TTS TTFB, transcription delay)
- User/agent state transitions with timestamps
- Overlapping speech and interruption data
- VAD-level inference stats (when available)
- Tool execution timing
- Token usage breakdown
- Session-level summary stats

Writes structured JSON to logs/voice/call-telemetry/{call_sid}.json on session close.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from livekit.agents import AgentSession

from .trace import trace

logger = logging.getLogger("openclaw-livekit.agent")

_OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
_TELEMETRY_DIR = _OPENCLAW_HOME / "logs" / "voice" / "call-telemetry"


def _ensure_telemetry_dir() -> None:
    try:
        _TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


class TelemetryCollector:
    """Accumulates session events and writes a structured JSON on flush."""

    def __init__(self, call_sid: str, agent_name: str) -> None:
        self.call_sid = call_sid
        self.agent_name = agent_name
        self.started_at = time.time()
        self.started_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        # Per-turn latency metrics (one entry per assistant response)
        self.turns: list[dict[str, Any]] = []

        # State transitions
        self.user_states: list[dict[str, Any]] = []
        self.agent_states: list[dict[str, Any]] = []

        # Interruptions and overlapping speech
        self.overlapping_speech: list[dict[str, Any]] = []
        self.false_interruptions: int = 0

        # Tool calls
        self.tool_calls: list[dict[str, Any]] = []

        # Usage (accumulated)
        self.usage_snapshots: list[dict[str, Any]] = []

        # Errors
        self.errors: list[dict[str, Any]] = []

        # Close event
        self.close_reason: str | None = None
        self.close_error: str | None = None

    def record_turn(self, metrics: dict[str, Any], role: str, text: str) -> None:
        """Record per-turn latency from ChatMessage.metrics."""
        entry: dict[str, Any] = {
            "turn_index": len(self.turns),
            "timestamp": time.time() - self.started_at,
            "role": role,
            "text_preview": text[:100] if text else "",
        }
        # Extract the latency fields we care about
        for key in (
            "e2e_latency",
            "llm_node_ttft",
            "tts_node_ttfb",
            "transcription_delay",
            "end_of_turn_delay",
            "on_user_turn_completed_delay",
        ):
            val = metrics.get(key)
            if val is not None:
                entry[key] = round(val, 4)
        self.turns.append(entry)

    def record_user_state(self, old: str, new: str) -> None:
        self.user_states.append({
            "timestamp": time.time() - self.started_at,
            "old": old,
            "new": new,
        })

    def record_agent_state(self, old: str, new: str) -> None:
        self.agent_states.append({
            "timestamp": time.time() - self.started_at,
            "old": old,
            "new": new,
        })

    def record_overlap(self, event: Any) -> None:
        entry: dict[str, Any] = {
            "timestamp": time.time() - self.started_at,
            "is_interruption": getattr(event, "is_interruption", None),
            "probability": None,
            "detection_delay": None,
            "prediction_duration": None,
            "total_duration": None,
        }
        for field in ("probability", "detection_delay", "prediction_duration", "total_duration"):
            val = getattr(event, field, None)
            if val is not None:
                entry[field] = round(val, 4)
        self.overlapping_speech.append(entry)

    def record_tool_execution(self, event: Any) -> None:
        calls = getattr(event, "function_calls", []) or []
        outputs = getattr(event, "function_call_outputs", []) or []
        for i, call in enumerate(calls):
            name = getattr(call, "name", "unknown")
            output = outputs[i] if i < len(outputs) else None
            self.tool_calls.append({
                "timestamp": time.time() - self.started_at,
                "name": name,
                "success": output is not None,
            })

    def record_usage(self, event: Any) -> None:
        usage = getattr(event, "usage", None)
        if not usage:
            return
        model_usage = getattr(usage, "model_usage", []) or []
        snapshot: dict[str, Any] = {
            "timestamp": time.time() - self.started_at,
            "models": [],
        }
        for mu in model_usage:
            entry: dict[str, Any] = {
                "type": type(mu).__name__,
                "provider": getattr(mu, "provider", None),
                "model": getattr(mu, "model", None),
            }
            # Token fields (LLM)
            for field in ("input_tokens", "output_tokens"):
                val = getattr(mu, field, None)
                if val is not None:
                    entry[field] = val
            # Audio duration (STT/TTS)
            for field in ("audio_duration", "characters_count"):
                val = getattr(mu, field, None)
                if val is not None:
                    entry[field] = round(val, 2) if isinstance(val, float) else val
            snapshot["models"].append(entry)
        self.usage_snapshots.append(snapshot)

    def record_error(self, event: Any) -> None:
        self.errors.append({
            "timestamp": time.time() - self.started_at,
            "error": str(getattr(event, "error", event)),
        })

    def record_close(self, event: Any) -> None:
        self.close_reason = str(getattr(event, "reason", "unknown"))
        self.close_error = str(getattr(event, "error", "")) or None

    def build_summary(self) -> dict[str, Any]:
        """Compute session-level summary stats from accumulated data."""
        duration = time.time() - self.started_at

        # Latency stats from turns
        e2e_values = [t["e2e_latency"] for t in self.turns if "e2e_latency" in t]
        ttft_values = [t["llm_node_ttft"] for t in self.turns if "llm_node_ttft" in t]

        def _stats(values: list[float]) -> dict[str, float | None]:
            if not values:
                return {"min": None, "max": None, "avg": None, "p90": None, "count": 0}
            s = sorted(values)
            p90_idx = int(len(s) * 0.9)
            return {
                "min": round(s[0], 4),
                "max": round(s[-1], 4),
                "avg": round(sum(s) / len(s), 4),
                "p90": round(s[min(p90_idx, len(s) - 1)], 4),
                "count": len(s),
            }

        interruptions = [o for o in self.overlapping_speech if o.get("is_interruption")]
        backchannels = [o for o in self.overlapping_speech if not o.get("is_interruption")]

        return {
            "duration_seconds": round(duration, 1),
            "total_turns": len(self.turns),
            "e2e_latency": _stats(e2e_values),
            "llm_ttft": _stats(ttft_values),
            "interruptions": len(interruptions),
            "false_interruptions": self.false_interruptions,
            "backchannels": len(backchannels),
            "overlapping_speech_events": len(self.overlapping_speech),
            "tool_calls_total": len(self.tool_calls),
            "tool_calls_failed": sum(1 for t in self.tool_calls if not t["success"]),
            "errors": len(self.errors),
        }

    def flush(self) -> Path | None:
        """Write the telemetry JSON to disk. Returns the path or None on failure."""
        _ensure_telemetry_dir()
        path = _TELEMETRY_DIR / f"{self.call_sid}.json"

        doc = {
            "call_sid": self.call_sid,
            "agent": self.agent_name,
            "started_at": self.started_at_iso,
            "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "close_reason": self.close_reason,
            "close_error": self.close_error,
            "summary": self.build_summary(),
            "turns": self.turns,
            "user_states": self.user_states,
            "agent_states": self.agent_states,
            "overlapping_speech": self.overlapping_speech,
            "tool_calls": self.tool_calls,
            "usage": self.usage_snapshots[-1] if self.usage_snapshots else None,
            "errors": self.errors,
        }

        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2)
            logger.info("telemetry written: %s", path)
            trace(f"telemetry written: {path}")
            return path
        except Exception as err:
            logger.error("telemetry write failed: %s", err)
            trace(f"telemetry write failed: {err}")
            return None


def wire_telemetry_capture(
    session: AgentSession,
    call_sid: str | None,
    agent_name: str = "unknown",
) -> TelemetryCollector | None:
    """Register event listeners on *session* that capture structured telemetry.

    Call this AFTER session.start() and BEFORE generate_reply().
    Returns the collector so callers can access it if needed.
    """
    if not call_sid:
        return None

    collector = TelemetryCollector(call_sid, agent_name)

    @session.on("conversation_item_added")
    def _on_item(ev: Any) -> None:
        item = getattr(ev, "item", None)
        if item is None:
            return
        role = getattr(item, "role", None) or "unknown"
        metrics = getattr(item, "metrics", None)
        if not metrics or role != "assistant":
            return

        text = ""
        if hasattr(item, "text_content"):
            text = item.text_content or ""
        elif hasattr(item, "content"):
            content = item.content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(c for c in content if isinstance(c, str))

        collector.record_turn(metrics, role, text)

    @session.on("user_state_changed")
    def _on_user_state(ev: Any) -> None:
        old = str(getattr(ev, "old_state", "?"))
        new = str(getattr(ev, "new_state", "?"))
        collector.record_user_state(old, new)

    @session.on("agent_state_changed")
    def _on_agent_state(ev: Any) -> None:
        old = str(getattr(ev, "old_state", "?"))
        new = str(getattr(ev, "new_state", "?"))
        collector.record_agent_state(old, new)

    @session.on("overlapping_speech")
    def _on_overlap(ev: Any) -> None:
        collector.record_overlap(ev)

    @session.on("agent_false_interruption")
    def _on_false_interrupt(ev: Any) -> None:
        collector.false_interruptions += 1

    @session.on("function_tools_executed")
    def _on_tools(ev: Any) -> None:
        collector.record_tool_execution(ev)

    @session.on("session_usage_updated")
    def _on_usage(ev: Any) -> None:
        collector.record_usage(ev)

    @session.on("error")
    def _on_error(ev: Any) -> None:
        collector.record_error(ev)

    @session.on("close")
    def _on_close(ev: Any) -> None:
        collector.record_close(ev)
        collector.flush()

    trace(f"telemetry capture wired for call_sid={call_sid}")
    logger.info("telemetry capture wired for call_sid=%s", call_sid)
    return collector
