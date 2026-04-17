"""Post-call review system — manifest tracking + Rin QC dispatch.

Every call that closes gets logged in the manifest. Rin is spawned for
review. If spawn fails, the manifest records the failure so the hourly
catch-up sweep can retry.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from .cli_spawner import fire_and_forget
from .trace import trace

logger = logging.getLogger("openclaw-livekit.agent")

_OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
_VOICE_LOGS = _OPENCLAW_HOME / "logs" / "voice"
_TRANSCRIPT_DIR = _VOICE_LOGS / "phone-transcripts"
_TRACE_PATH = _VOICE_LOGS / "agent.trace"
_REVIEW_DIR = _VOICE_LOGS / "call-reviews"
_MANIFEST_PATH = _VOICE_LOGS / "call-manifest.jsonl"


# --- manifest -----------------------------------------------------------

def _append_manifest(entry: dict) -> None:
    """Append one JSON line to the call manifest."""
    try:
        _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _MANIFEST_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except Exception as err:
        logger.error("postcall: manifest write failed: %s", err)


# --- wiring -------------------------------------------------------------

def wire_postcall_review(
    session: "AgentSession",
    call_sid: str | None,
    agent_name: str = "unknown",
) -> None:
    """Register a ``close`` handler that logs the call and spawns Rin.

    Call this AFTER ``wire_transcript_logging`` in the agent entrypoint.
    """
    if not call_sid:
        return

    @session.on("close")
    def _on_close(ev: Any) -> None:
        error = getattr(ev, "error", None)
        reason = str(getattr(ev, "reason", "unknown"))
        ended_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        transcript_path = _TRANSCRIPT_DIR / f"{call_sid}.txt"
        has_transcript = transcript_path.exists()

        # Always log to manifest — even if no transcript
        manifest_entry = {
            "call_sid": call_sid,
            "agent": agent_name,
            "ended_at": ended_at,
            "close_reason": reason,
            "has_error": error is not None,
            "error_detail": str(error) if error else None,
            "has_transcript": has_transcript,
            "review_status": "pending",
        }

        if not has_transcript:
            manifest_entry["review_status"] = "skipped_no_transcript"
            _append_manifest(manifest_entry)
            trace(f"postcall: no transcript for {call_sid}, logged as skipped")
            return

        # Build and dispatch review task
        task = build_review_task(
            call_sid=call_sid,
            agent_name=agent_name,
            error=str(error) if error else None,
            close_reason=reason,
        )

        try:
            fire_and_forget(
                [
                    "agent",
                    "--agent", "rin",
                    "--message", task,
                    "--json",
                ]
            )
            manifest_entry["review_status"] = "spawned"
            trace(f"postcall: spawned rin for call {call_sid}")
            logger.info("postcall: spawned rin review for call_sid=%s", call_sid)
        except Exception as err:
            manifest_entry["review_status"] = "spawn_failed"
            manifest_entry["spawn_error"] = str(err)
            logger.error("postcall: failed to spawn rin: %s", err)
            trace(f"postcall: spawn failed for {call_sid}: {err}")

        _append_manifest(manifest_entry)

    trace(f"postcall review wired for call_sid={call_sid}")


# --- review task builder ------------------------------------------------

_REVIEW_DIR_STR = str(_REVIEW_DIR)
_TRANSCRIPT_DIR_STR = str(_TRANSCRIPT_DIR)
_TELEMETRY_DIR_STR = str(_VOICE_LOGS / "call-telemetry")
_TRACE_PATH_STR = str(_TRACE_PATH)


def build_review_task(
    *,
    call_sid: str,
    agent_name: str,
    error: str | None = None,
    close_reason: str = "unknown",
    is_catchup: bool = False,
) -> str:
    """Build the review task message sent to Rin."""

    source = "catch-up sweep" if is_catchup else "post-call hook"

    parts = [
        f"## Voice Ops: Post-Call Review [{source}]",
        "",
        f"Call: `{call_sid}` | Agent: `{agent_name}` | Close: `{close_reason}`",
    ]

    if error:
        parts.append(f"**Session error:** `{error}`")

    parts.extend([
        "",
        "Read your voice ops runbook at `~/.openclaw/workspace-rin/VOICE_OPS.md` first.",
        "",
        "### Data Sources",
        "",
        f"1. **Transcript:** `{_TRANSCRIPT_DIR_STR}/{call_sid}.txt`",
        f"2. **Telemetry:** `{_TELEMETRY_DIR_STR}/{call_sid}.json` — structured per-turn latency, state transitions, interruptions, tool timing, usage. **Read this first if it exists.** It has exact millisecond data; don't guess from transcript timestamps when telemetry is available.",
        f"3. **Trace log:** grep `{_TRACE_PATH_STR}` for `{call_sid}`",
        f"4. **Gateway errors:** grep `~/.openclaw/logs/gateway.err.log` for the call's PID (find PID in trace)",
        "5. **Embeddings:** use `memory_recent` MCP tool (last 4 hours) to check if call content was stored",
        "",
        "### Analysis Checklist",
        "",
        "Score each dimension and flag issues. **Use telemetry data for latency and turn-taking — do not guess from transcript text.**",
        "",
        "- [ ] **Greeting** — Single clean greeting? Double greeting? No greeting? (check first 2 agent_states in telemetry)",
        "- [ ] **Audio/Speech** — Was user speech transcribed? Check user_states for speaking→listening transitions. Long gaps with no user_state changes may indicate VAD failure.",
        "- [ ] **Tool Execution** — Check telemetry `tool_calls[]` for success/failure. Every tool call should have `success: true`.",
        "- [ ] **Response Latency** — Use telemetry `summary.e2e_latency` stats. Flag: avg >3s (yellow), avg >5s (red), any single turn >8s (critical). Report min/max/avg/p90.",
        "- [ ] **Persona Adherence** — Does the agent sound like their persona? (warm, casual for Nyla; read the prompt at `~/.openclaw/extensions/openclaw-livekit-agent-{agent}/prompts/system.md`)",
        "- [ ] **Turn-Taking** — Check telemetry `overlapping_speech[]` and `false_interruptions`. How many times did the user interrupt? How many were false? Report `summary.interruptions`, `summary.backchannels`, `summary.false_interruptions`.",
        "- [ ] **Conversation Quality** — Natural flow? Awkward transitions? Use state transitions to check for rapid speaking↔listening flicker (indicates crosstalk).",
        "- [ ] **Transcription Quality** — Excessive `<noise>` or `[noise]` tags? Garbled text?",
        "- [ ] **Embedding Audit** — If call had >3 substantive turns, were memories stored? Check `memory_recent`. If not, flag as missing embedding.",
        "- [ ] **Session Health** — Check telemetry `close_reason` and `close_error`. Any errors in `errors[]`? Clean disconnect?",
        "",
        "### Output",
        "",
        f"Write your review as JSON to: `{_REVIEW_DIR_STR}/{call_sid}.json`",
        f"Create the directory `{_REVIEW_DIR_STR}` if it doesn't exist.",
        "",
        "```json",
        "{",
        f'  "call_sid": "{call_sid}",',
        f'  "agent": "{agent_name}",',
        f'  "close_reason": "{close_reason}",',
        f'  "reviewed_at": "<ISO timestamp>",',
        '  "source": "<post-call | catch-up>",',
        '  "duration_turns": <number of user+assistant turns>,',
        '  "call_duration_seconds": <approx from first to last transcript timestamp>,',
        '  "score": <1-10 overall quality>,',
        '  "scores": {',
        '    "greeting": <1-10>,',
        '    "tool_execution": <1-10 or null if no tools used>,',
        '    "response_latency": <1-10>,',
        '    "persona_adherence": <1-10>,',
        '    "conversation_quality": <1-10>,',
        '    "transcription_quality": <1-10>',
        '  },',
        '  "issues": [',
        '    {',
        '      "type": "double_greeting|silent_gap|tool_failure|missing_embedding|transcription_noise|session_error|persona_drift|slow_response",',
        '      "severity": "low|medium|high|critical",',
        '      "detail": "...",',
        '      "timestamp": "HH:MM:SS from transcript"',
        '    }',
        '  ],',
        '  "tool_calls": [',
        '    {"name": "...", "success": true/false, "response_time_seconds": <number or null>}',
        '  ],',
        '  "embedding_check": {',
        '    "substantive_call": true/false,',
        '    "memories_found": <count from memory_recent>,',
        '    "memories_expected": true/false,',
        '    "flagged": true/false',
        '  },',
        '  "latency": {',
        '    "e2e_avg": <from telemetry summary, or null if no telemetry>,',
        '    "e2e_p90": <from telemetry summary>,',
        '    "e2e_max": <from telemetry summary>,',
        '    "llm_ttft_avg": <from telemetry summary>,',
        '    "worst_turn": {"index": <N>, "e2e_latency": <seconds>, "text_preview": "..."}',
        '  },',
        '  "turn_taking": {',
        '    "interruptions": <from telemetry summary>,',
        '    "false_interruptions": <from telemetry summary>,',
        '    "backchannels": <from telemetry summary>,',
        '    "overlapping_speech_events": <from telemetry summary>',
        '  },',
        '  "has_telemetry": true/false,',
        '  "recommendations": ["specific, actionable suggestions for improvement — include tuning recommendations based on latency/interruption data"],',
        '  "log_snippets": ["relevant error or warning lines from trace/gateway logs"],',
        '  "prompt_suggestions": ["if a prompt change would fix a recurring issue, draft the specific edit here"]',
        "}",
        "```",
        "",
        "### After Writing the Review",
        "",
        "Complete ALL of these post-review actions. Do not skip any.",
        "",
        f"1. **Manifest update** — Append `{{\"{call_sid}\": \"review_complete\": true}}` to `{str(_MANIFEST_PATH)}`",
        "",
        "2. **Working files** — Update the appropriate files in `~/.openclaw/workspace-rin/voice-ops/`:",
        "   - **Any issue with severity high or critical** → append a row to `incident_log.md`",
        "   - **Any tool_failure issue** → append a row to `known_tool_issues.md` (check if the tool+issue combo already exists first; if so, increment frequency instead of adding a duplicate)",
        "   - **Any prompt_suggestions in your review** → append a row to `prompt_changelog.md` with status `pending`",
        "",
        "3. **Escalation** (only if triggered):",
        "   - **Score < 4** → Post to Discord (account: rin, channel: 1480975834150866956) with: call SID, score, top issue, and what you're investigating. Tag Eric.",
        "   - **Same issue type in 3+ consecutive calls** → Send a Musubi thought to `aoi-terminal` with a fix brief: what's broken, how often, and your recommended fix.",
        "   - **Critical severity** → Do both of the above regardless of score.",
        "",
        "4. **Verify** — Confirm the review JSON was written by reading it back. If the write failed, retry once.",
    ])

    return "\n".join(parts)
