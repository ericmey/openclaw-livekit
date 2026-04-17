#!/usr/bin/env bash
# Bootstrap the SIP infrastructure on macOS.
#
# Idempotent: re-runs safely. Does NOT touch Twilio — that's console
# work (see docs/twilio-trunk.md). Does NOT register trunks or dispatch
# rules — those come in Phase 3 of MIGRATION.md after you have a
# working livekit-sip process.
#
# What it does:
#   1. Installs Redis via brew, starts it as a launch service
#   2. Installs livekit-cli
#   3. Pulls the livekit/sip Docker image
#   4. Creates ~/.openclaw/config/ and copies livekit-sip.yaml template
#      (if not already present)
#   5. Prints next steps

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${HOME}/.openclaw/config"
CONFIG_FILE="${CONFIG_DIR}/livekit-sip.yaml"

log() { printf "\033[1;34m[setup]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[warn]\033[0m  %s\n" "$*"; }
die() { printf "\033[1;31m[fatal]\033[0m %s\n" "$*" >&2; exit 1; }

# --- pre-flight -------------------------------------------------------
command -v brew >/dev/null 2>&1 || die "Homebrew required: https://brew.sh"
command -v docker >/dev/null 2>&1 || warn "Docker not found — Docker Desktop must be installed + running for the livekit-sip container path. You can still proceed with native builds."

# --- Redis ------------------------------------------------------------
if brew list redis >/dev/null 2>&1; then
  log "redis: already installed"
else
  log "redis: installing via brew"
  brew install redis
fi

if brew services list | awk '$1=="redis"{print $2}' | grep -q started; then
  log "redis: service already running"
else
  log "redis: starting as launch service"
  brew services start redis
fi

# Probe
if redis-cli -h 127.0.0.1 -p 6379 ping 2>/dev/null | grep -q PONG; then
  log "redis: responding on 127.0.0.1:6379"
else
  warn "redis: not responding yet — may take a few seconds"
fi

# --- livekit-cli ------------------------------------------------------
if command -v lk >/dev/null 2>&1; then
  log "livekit-cli: already installed ($(lk --version 2>/dev/null | head -1))"
else
  log "livekit-cli: installing via brew"
  brew install livekit-cli
fi

# --- livekit/sip docker image -----------------------------------------
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    log "docker: daemon running — pulling livekit/sip:latest"
    docker pull livekit/sip:latest
  else
    warn "docker: daemon not running — start Docker Desktop and re-run this step manually: docker pull livekit/sip:latest"
  fi
fi

# --- config scaffolding -----------------------------------------------
mkdir -p "${CONFIG_DIR}"
if [[ -f "${CONFIG_FILE}" ]]; then
  log "config: ${CONFIG_FILE} already exists — leaving untouched"
else
  log "config: copying template to ${CONFIG_FILE}"
  cp "${REPO_DIR}/config/livekit-sip.yaml.example" "${CONFIG_FILE}"
  warn "config: EDIT ${CONFIG_FILE} before starting livekit-sip — api_key and api_secret must match your LiveKit server"
fi

# --- summary ----------------------------------------------------------
cat <<EOF

$(log "done")

Next steps:

  1. Edit ${CONFIG_FILE}:
     - Set api_key / api_secret to match your LiveKit server
     - Set ws_url to your LiveKit WebSocket URL
     - Confirm use_external_ip is appropriate for your network

  2. Start livekit-sip (in a separate terminal first, to watch logs):
     docker run --rm --network=host \\
       -v "${CONFIG_FILE}":/config.yaml:ro \\
       livekit/sip:latest --config /config.yaml

     Once that looks healthy, promote to launchd later:
     cp ${REPO_DIR}/config/launchd.plist.example ~/Library/LaunchAgents/ai.openclaw.livekit-sip.plist
     # edit REPLACE_ME paths
     launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/ai.openclaw.livekit-sip.plist

  3. Configure Twilio Elastic SIP Trunk — see docs/twilio-trunk.md

  4. Register inbound trunk + dispatch rule — see MIGRATION.md Phase 3

  5. Point ONE Twilio DID at the new trunk (leave others on the bridge
     for the A/B window)

EOF
