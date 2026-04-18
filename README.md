# openclaw-livekit

Monorepo for the OpenClaw voice stack: SIP trunking, realtime voice agents, and
the operations layer that wires them together.

## What's in here

```
openclaw-livekit/
├── docker-compose.yaml            livekit-server + livekit-sip + redis
├── config/                        templates for ~/.openclaw/config/
├── scripts/                       ops verbs (deploy, cycle, health, etc.)
├── docs/                          architecture, operations, gotchas
├── Makefile                       stable wrapper around scripts/
├── openclaw-livekit-agent-sdk/    shared tools, mixins, config dataclass
├── openclaw-livekit-agent-nyla/   realtime persona (Gemini 2.5 native audio)
├── openclaw-livekit-agent-aoi/    realtime persona, technical partner
├── openclaw-livekit-agent-party/  chained STT/LLM/TTS variant
└── openclaw-livekit-sip/          livekit-sip image config + migration notes
```

The five subprojects used to live as sibling repos; they're folded into this
monorepo with `git subtree` so their history is preserved in the unified log.

## Quickstart

```bash
# Clone into ~/Projects/
mkdir -p ~/Projects
git clone git@github.com:ericmey/openclaw-livekit.git ~/Projects/openclaw-livekit
cd ~/Projects/openclaw-livekit

# First time on a new machine
make bootstrap

# Then edit the files bootstrap dropped in ~/.openclaw/config/ and
# ~/.openclaw/secrets/ (it'll tell you exactly which ones).

# Bring up infrastructure
brew services stop redis    # compose ships redis; one-time cleanup
make up                     # docker compose up -d
make register-sip           # register trunk + dispatch rules from config
make deploy                 # render plists, install, kickstart agents
make health                 # verify everything is green
```

## Common operational verbs

| Verb | What it does |
|------|--------------|
| `make help` | List all verbs |
| `make up` / `make down` | Bring the docker-compose stack up/down |
| `make deploy` | Render launchd plists + install + kickstart agents |
| `make teardown` | Bootout agents, remove plists (source stays put) |
| `make cycle` | Kickstart all three agents in place |
| `make register-sip` | Idempotent SIP trunk + dispatch rule refresh |
| `make health` | Exit-nonzero if any component is unhealthy |
| `make tail` | Follow all three agent logs with color prefix |
| `make truncate-logs` | Clean baseline for a test session |
| `make test` | Run pytest across all four Python subprojects |

## Architecture & operations

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — how the pieces fit
- **[docs/OPERATIONS.md](docs/OPERATIONS.md)** — deploy / cycle / debug runbook
- **[docs/DISPATCH-RULE-GOTCHAS.md](docs/DISPATCH-RULE-GOTCHAS.md)** — the `numbers` vs `inbound_numbers` trap we fell into

## Status

Personal project, running in my house. Shared publicly for reference and
portfolio. Not actively maintained as an open-source community project.

## License

MIT — see [LICENSE](LICENSE).
