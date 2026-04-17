"""CoreToolsMixin — get_current_time, get_weather, openclaw_request."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

import aiohttp
from livekit.agents import Agent, function_tool

from ..gateway_client import get_gateway_config
from ..trace import trace

logger = logging.getLogger("openclaw-livekit.agent")


class CoreToolsMixin(Agent):
    """Provides get_current_time, get_weather, and openclaw_request tools."""

    @function_tool
    async def get_current_time(self) -> str:
        """Get the current local date and time on the server.

        Invocation Condition: Invoke this tool whenever the user asks
        what time it is, what day it is, or the current date. You MUST
        call this tool to get the time. Never guess or estimate the time
        without calling this tool first.
        """
        trace("tool=get_current_time")
        now = datetime.now().astimezone()
        return now.strftime("%A, %B %-d, %Y %-I:%M:%S %p %Z")

    @function_tool
    async def get_weather(self) -> str:
        """Get the current weather conditions in Carmel, Indiana.

        Invocation Condition: Invoke this tool whenever the user asks
        about the weather, temperature, or conditions outside. Examples:
        "What's the weather like?", "Is it cold outside?", "What's the
        temperature?". You MUST call this tool — never guess the weather.
        """
        trace("tool=get_weather")
        nws_url = "https://api.weather.gov/stations/KTYQ/observations/latest"
        headers = {
            "User-Agent": "(openclaw-voice-agent, user@example.com)",
            "Accept": "application/geo+json",
        }
        try:
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    nws_url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    if resp.status != 200:
                        trace(f"tool=get_weather NWS status={resp.status}")
                        return "Couldn't pull up the weather right now."
                    data = await resp.json()

            props = data.get("properties", {})
            desc = props.get("textDescription", "")
            temp_c = props.get("temperature", {}).get("value")
            humidity = props.get("relativeHumidity", {}).get("value")
            wind_speed_kmh = props.get("windSpeed", {}).get("value")

            parts: list[str] = []
            if temp_c is not None:
                temp_f = round(temp_c * 9 / 5 + 32)
                parts.append(f"{temp_f} degrees")
            if desc:
                parts.append(desc.lower())
            if humidity is not None:
                parts.append(f"{round(humidity)}% humidity")
            if wind_speed_kmh is not None:
                wind_mph = round(wind_speed_kmh * 0.621371)
                parts.append(f"wind {wind_mph} mph")

            result = ", ".join(parts) if parts else "No weather data available."
            trace(f"tool=get_weather DONE result={result[:80]}")
            return f"Current conditions in Carmel: {result}."
        except asyncio.TimeoutError:
            trace("tool=get_weather TIMEOUT")
            return "Weather lookup timed out."
        except Exception as err:
            trace(f"tool=get_weather ERROR {err}")
            return "Couldn't pull up the weather right now."

    @function_tool
    async def openclaw_request(self, request: str, agent: str = "nyla") -> str:
        """Send a request to an OpenClaw agent for processing.

        This connects to the agent's session on the local gateway with full
        memory, context, and tools. Use this for anything beyond casual
        conversation: checking on other agents, accessing files, querying
        house systems, reviewing session history, sending messages, or any
        complex task.

        Args:
            request: Natural language description of what you need. Be
                specific. Examples: "What did Hana work on today?",
                "Check system health and agent status",
                "Send a message to Aoi about the pipeline".
            agent: Which agent should handle this. Defaults to "nyla"
                (the real terminal Nyla). Use another name only if the
                task clearly belongs to them.
        """
        t0 = time.monotonic()
        trace(f"tool=openclaw_request agent={agent} req={request[:80]!r}")
        if not request.strip():
            return "Error: request is required."

        gw = get_gateway_config()
        if gw is None:
            return "Error: gateway not configured — cannot reach agents."
        port, token = gw

        payload = {
            "model": f"openclaw/{agent}",
            "user": "voice",
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{request}\n\n"
                        "IMPORTANT: Be concise. This result will be read aloud "
                        "on a voice call. 2-3 sentences max. Plain text only."
                    ),
                }
            ],
        }

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as http:
                async with http.post(
                    f"http://127.0.0.1:{port}/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    json=payload,
                ) as resp:
                    if resp.status != 200:
                        body_text = (await resp.text())[:200]
                        logger.error(
                            "openclaw_request: gateway %d: %s",
                            resp.status,
                            body_text,
                        )
                        return f"Couldn't reach {agent} right now (error {resp.status})."
                    data = await resp.json()
        except asyncio.TimeoutError:
            logger.warning("openclaw_request: gateway timed out (60s)")
            return f"Request to {agent} timed out."
        except Exception as err:
            logger.error("openclaw_request failed: %s", err)
            return f"Couldn't reach {agent} right now."

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        trace(f"tool=openclaw_request DONE agent={agent} elapsed={elapsed_ms}ms")

        choices = data.get("choices") or []
        content = ""
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content") or ""
        return content.strip() or "No response."
