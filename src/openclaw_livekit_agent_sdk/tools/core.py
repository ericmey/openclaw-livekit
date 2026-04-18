"""CoreToolsMixin — get_current_time, get_weather."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiohttp
from livekit.agents import Agent, function_tool

from ..trace import trace

logger = logging.getLogger("openclaw-livekit.agent")


class CoreToolsMixin(Agent):
    """Provides get_current_time and get_weather tools."""

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
