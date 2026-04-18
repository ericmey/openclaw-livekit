#!/usr/bin/env bash
#
# First-time machine setup. Safe to re-run — every step checks before
# installing. Does NOT deploy agents or register SIP routing; those are
# separate explicit steps so you can review before running them.
#
# Run once on a fresh box:
#   scripts/bootstrap.sh
#
# Then:
#   1. Fill in ~/.openclaw/secrets/livekit-agents.env
#   2. Edit ~/.openclaw/config/*.yaml and *.json for real values
#   3. Bring up infra:     docker compose up -d
#   4. Register SIP:       scripts/register-sip-routing.sh
#   5. Deploy agents:      scripts/deploy-agents.sh
#   6. Verify:             scripts/health-check.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-${HOME}/.openclaw}"

log()  { printf "\033[1;34m[bootstrap]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m      %s\n" "$*"; }
die()  { printf "\033[1;31m[fatal]\033[0m     %s\n" "$*" >&2; exit 1; }

# ---- required tooling --------------------------------------------
command -v brew   >/dev/null 2>&1 || die "Homebrew required: https://brew.sh"
command -v docker >/dev/null 2>&1 || die "Docker Desktop required: https://docker.com"

for tool in uv livekit-cli jq; do
  if brew list "$tool" >/dev/null 2>&1; then
    log "$tool: already installed"
  else
    log "installing $tool via brew"
    brew install "$tool"
  fi
done

# ---- config scaffolding ------------------------------------------
mkdir -p "${OPENCLAW_HOME}/config" \
         "${OPENCLAW_HOME}/secrets" \
         "${OPENCLAW_HOME}/logs/voice"
chmod 700 "${OPENCLAW_HOME}/secrets"

# Copy each .example into place if the real file doesn't exist yet.
copy_if_missing() {
  local src="$1" dst="$2"
  if [[ -f "$dst" ]]; then
    log "$(basename "$dst"): already present — leaving untouched"
  else
    cp "$src" "$dst"
    log "copied template: $(basename "$dst")"
    warn "EDIT ${dst} before using"
  fi
}

copy_if_missing "${REPO_ROOT}/config/livekit.yaml.example"           "${OPENCLAW_HOME}/config/livekit.yaml"
copy_if_missing "${REPO_ROOT}/config/livekit-sip.yaml.example"       "${OPENCLAW_HOME}/config/livekit-sip.yaml"
copy_if_missing "${REPO_ROOT}/config/sip-inbound-trunk.json.example" "${OPENCLAW_HOME}/config/sip-inbound-trunk.json"
for a in nyla aoi party; do
  copy_if_missing "${REPO_ROOT}/config/sip-dispatch-${a}.json.example" "${OPENCLAW_HOME}/config/sip-dispatch-${a}.json"
done
copy_if_missing "${REPO_ROOT}/config/secrets.env.example"            "${OPENCLAW_HOME}/secrets/livekit-agents.env"

# ---- agent venvs --------------------------------------------------
# Each agent project needs its own .venv/ before launchd can run it. uv
# resolves the sibling SDK via the path-based source in pyproject.toml.
for a in sdk nyla aoi party; do
  project="${REPO_ROOT}/openclaw-livekit-agent-${a}"
  [[ -d "${project}" ]] || die "missing project dir: ${project}"
  if [[ -x "${project}/.venv/bin/python" ]]; then
    log "venv: ${a} already synced"
  else
    log "venv: uv syncing ${a}"
    (cd "${project}" && uv sync --all-groups)
  fi
done

# sip is Docker-only — no venv needed.

log "done."
cat <<EOF

Next steps:

  1. Edit ${OPENCLAW_HOME}/secrets/livekit-agents.env
     (GOOGLE_API_KEY, GATEWAY_AUTH_TOKEN, LIVEKIT_API_SECRET)

  2. Edit ${OPENCLAW_HOME}/config/livekit.yaml
     (keys section: set a real api_secret)

  3. Edit ${OPENCLAW_HOME}/config/livekit-sip.yaml
     (api_key/api_secret: match livekit.yaml)

  4. Edit ${OPENCLAW_HOME}/config/sip-inbound-trunk.json
     (numbers: your Twilio DIDs; allowed_numbers: caller allowlist)

  5. Edit ${OPENCLAW_HOME}/config/sip-dispatch-{nyla,aoi,party}.json
     (numbers: the DID each agent owns)

  6. brew services stop redis      # compose ships redis on :6379
     docker compose up -d          # brings up redis, livekit-server, livekit-sip
     scripts/register-sip-routing.sh
     scripts/deploy-agents.sh
     scripts/health-check.sh

EOF
