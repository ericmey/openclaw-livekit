# tools/ — voice-agent tool catalog

Browseable list of every `@function_tool` available to the voice agents.
Each tool lives in a **mixin class**; agents compose the mixins they want
in their `__mro__`:

```python
class NylaAgent(CoreToolsMixin, MemoryToolsMixin, SessionsToolsMixin,
                AcademyToolsMixin, Agent):
    ...
```

LiveKit discovers `@function_tool`-decorated methods via MRO walk and
exposes them to the voice model as callable tools.

## Catalog

| Tool | Module | Mixin | Description | Args |
|---|---|---|---|---|
| `get_current_time` | [core.py](src/tools/core.py) | `CoreToolsMixin` | Current local date + time on the server | — |
| `get_weather` | [core.py](src/tools/core.py) | `CoreToolsMixin` | Current weather in Carmel, IN | — |
| `musubi_recent` | [memory.py](src/tools/memory.py) | `MemoryToolsMixin` | Recent memories across the household (alpha Musubi, direct Qdrant) | `hours=24`, `limit=10` |
| `memory_store` | [memory.py](src/tools/memory.py) | `MemoryToolsMixin` | Persist a memory for future recall (alpha Musubi, direct Qdrant) | `content`, `tags=[]` |
| `musubi_recall` | [musubi_voice.py](src/tools/musubi_voice.py) | `MusubiVoiceToolsMixin` | Hybrid retrieve across Musubi planes (**new** canonical API) | `query`, `limit=5` |
| `musubi_remember` | [musubi_voice.py](src/tools/musubi_voice.py) | `MusubiVoiceToolsMixin` | Explicit episodic capture at importance 7 (**new** canonical API) | `content`, `tags=[]`, `importance=7` |
| `musubi_think` | [musubi_voice.py](src/tools/musubi_voice.py) | `MusubiVoiceToolsMixin` | Presence-to-presence thought delivery (**new** canonical API) | `to_agent`, `content`, `channel="default"` |
| `sessions_send` | [sessions.py](src/tools/sessions.py) | `SessionsToolsMixin` | Send a task/message to another AI agent | `agent_id`, `message`, `deliver_to="room"` |
| `sessions_spawn` | [sessions.py](src/tools/sessions.py) | `SessionsToolsMixin` | Spawn a new agent session to handle a task | `agent_id`, `task`, `deliver_to="room"` |
| `academy_selfie` | [academy.py](src/tools/academy.py) | `AcademyToolsMixin` | Request a selfie of the speaking agent from Mizuki | `mood`, `nsfw=False` |
| `academy_send` | [academy.py](src/tools/academy.py) | `AcademyToolsMixin` | Request an image of any character from Mizuki | `character`, `prompt`, `rating="general"` |

### Disabled but preserved

| Tool | Module | Status |
|---|---|---|
| `schedule_callback` | [sessions.py](src/tools/sessions.py) | `@function_tool` decorator removed so the model can't call it. Method body + validation + tests preserved for re-enable. See [../sdk/TODO.md](../sdk/TODO.md) for the preferred cron-payload redesign. |

## Mixins and who uses them

| Mixin | Agents that compose it |
|---|---|
| `CoreToolsMixin` | nyla, aoi, party |
| `MemoryToolsMixin` | nyla, aoi, party (alpha Musubi path) |
| `MusubiVoiceToolsMixin` | — *(new-stack path; not composed into any agent yet — dormant until Musubi v2 cutover)* |
| `SessionsToolsMixin` | nyla, aoi, party |
| `AcademyToolsMixin` | nyla, aoi, party |

## Musubi: alpha vs new-stack

Two memory mixins exist side-by-side during the migration window:

- `MemoryToolsMixin` talks **directly to Qdrant** (`localhost:6333`,
  collection `musubi_memories`) — the alpha Musubi. This is what every
  agent currently composes.
- `MusubiVoiceToolsMixin` talks to the **new Musubi canonical API**
  (`MUSUBI_V2_BASE_URL`, default `http://localhost:8100/v1`) with
  bearer auth. Three tools: `musubi_recall`, `musubi_remember`,
  `musubi_think`.

The new-stack mixin is **not composed into any agent yet**. It exists
so the new API gets exercised (tests, dev use) without touching the
live voice path. Cutover is a single-line MRO swap per agent once
Musubi v2 passes load + perf testing and the legacy corpus has been
migrated. Do **not** compose both simultaneously — conflicting
`@function_tool` names.

## How tools reach side effects

Actuator-shaped tools (Discord messaging, image generation, delegation)
don't talk to Discord / ComfyUI / cron directly. They spawn the OpenClaw
CLI via [`sdk.cli_spawner.fire_and_forget`](../sdk/src/sdk/cli_spawner.py)
with an explicit argv — safe, testable, no shell-injection surface.

The `OPENCLAW_VOICE_TOOLS_DRY_RUN=1` env var short-circuits every spawn
to a logged no-op — lets tests exercise the full tool path without firing
real Discord messages or kicking off real agent sessions.

## Adding a new tool

1. Either extend an existing mixin with a new `@function_tool`-decorated
   method, or drop a new module into `src/tools/<name>.py` with its own
   mixin class.
2. Export the mixin from [src/tools/__init__.py](src/tools/__init__.py).
3. Add a row to the catalog table above.
4. Update the "Mixins and who uses them" table if it's a new mixin class.
5. `make verify` to confirm the change is lint/type/test clean.

## Per-agent customization

Each tool reads `self.config` (an `AgentConfig` instance set by the
concrete agent class) for per-agent behavior:

- `config.agent_name` — "nyla" | "aoi" | "party" — used for self-reference
  in prompts and as the `--agent` slot in CLI spawns.
- `config.discord_room` — default target for `deliver_to="room"`.
- `config.allowed_delegation_targets` — optional allowlist for
  `sessions_send` / `sessions_spawn` (None = no restriction).
- `config.memory_agent_tag` — tag used when storing memories so recall
  can filter per-agent.

Agents set `config` as a class attribute in their `_shared.py`; the
mixin's method body reads `self.config.X` polymorphically.
