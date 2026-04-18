"""AgentConfig — operational identity for a voice agent.

One source of truth for the behavioral/infra fields that multiple tools
and telemetry paths need. Concrete agents build an AgentConfig and
assign it to ``self.config``; the mixin stack reads from ``self.config``
instead of module-level constants. Centralizing this here is what keeps
Aoi's memories from being attributed to Nyla and keeps Aoi's delegated
work from landing in Nyla's Discord room.
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import NYLA_DISCORD_ROOM


@dataclass(frozen=True)
class AgentConfig:
    """Per-agent behavioral/infra identity.

    Attributes:
        agent_name: Short canonical id ("nyla", "aoi", "party"). Used in
            telemetry, the cron callback ``--agent`` slot, and in the
            agent's own self-reference (e.g. "selfie of Nyla").
        memory_agent_tag: Value written into stored Musubi memories'
            ``payload.agent`` field. Separates voice identities so the
            household can filter memories by speaker.
        discord_room: Discord target (``channel:<id>`` or ``user:<id>``)
            where delegated work results should post when the voice agent
            delegates with ``deliver_to="room"``. Typically the agent's
            own Discord channel.
        allowed_delegation_targets: Optional whitelist of agent ids this
            voice agent may delegate to via ``sessions_send`` /
            ``sessions_spawn``. ``None`` means no restriction (household
            router behavior — Nyla's default). A frozenset means any
            ``agent_id`` outside the set is rejected with an error
            message rather than firing.
    """

    agent_name: str
    memory_agent_tag: str
    discord_room: str
    allowed_delegation_targets: frozenset[str] | None = None


# Default config preserves the pre-AgentConfig behavior: tag everything
# as Nyla-voice, deliver room-targeted work to Nyla's channel, no
# delegation restrictions. Any mixin instance that somehow doesn't get
# a concrete config falls back to this.
NYLA_DEFAULT_CONFIG = AgentConfig(
    agent_name="nyla",
    memory_agent_tag="nyla-voice",
    discord_room=NYLA_DISCORD_ROOM,
    allowed_delegation_targets=None,
)
