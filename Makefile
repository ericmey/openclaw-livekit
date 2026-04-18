# OpenClaw LiveKit — operational verbs.
#
# Prefer `make <target>` over invoking scripts/ directly; the Makefile is
# the stable public surface. Scripts can change; these names don't.

SHELL := /usr/bin/env bash

.PHONY: help bootstrap up down logs health test \
        deploy teardown cycle \
        register-sip tail truncate-logs \
        sync-venvs

help: ## List the common verbs
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[1;34m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- first-time setup ----------------------------------------------

bootstrap: ## First-time machine setup (deps, config dir, venvs)
	scripts/bootstrap.sh

sync-venvs: ## Re-sync all agent venvs via uv
	@for a in sdk nyla aoi party; do \
	  echo ">> openclaw-livekit-agent-$$a"; \
	  (cd openclaw-livekit-agent-$$a && uv sync --all-groups); \
	done

# ---- infrastructure ------------------------------------------------

up: ## docker compose up -d (livekit-server + livekit-sip + redis)
	docker compose up -d

down: ## docker compose down
	docker compose down

logs: ## docker compose logs -f (server + sip + redis)
	docker compose logs -f

health: ## Run the health-check script
	scripts/health-check.sh

# ---- SIP routing ---------------------------------------------------

register-sip: ## Register/refresh SIP trunk + dispatch rules from ~/.openclaw/config/
	scripts/register-sip-routing.sh

# ---- agents --------------------------------------------------------

deploy: ## Render plists, install, kickstart (all three agents)
	scripts/deploy-agents.sh

teardown: ## Bootout and remove all agent plists
	scripts/teardown-agents.sh

cycle: ## Restart all three agents in place (picks up code changes)
	scripts/cycle-agents.sh

# ---- observability -------------------------------------------------

tail: ## Follow all three agent logs with color-coded prefix
	scripts/tail-logs.sh

truncate-logs: ## Zero out all agent logs (clean baseline for testing)
	scripts/truncate-logs.sh

# ---- tests ---------------------------------------------------------

test: ## Run pytest across all five subprojects
	@for d in openclaw-livekit-agent-sdk openclaw-livekit-agent-nyla openclaw-livekit-agent-aoi openclaw-livekit-agent-party; do \
	  echo ">> $$d"; \
	  (cd $$d && uv run pytest -q) || exit 1; \
	done
