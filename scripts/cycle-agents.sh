#!/usr/bin/env bash
#
# Kickstart (restart) one or more agents in place. Useful after a code
# change in the SDK or an agent persona — agents pick up the new files
# on restart without a full deploy.
#
# Usage:
#   scripts/cycle-agents.sh                  # all three
#   scripts/cycle-agents.sh nyla aoi         # subset

set -euo pipefail

log() { printf "\033[1;34m[cycle]\033[0m %s\n" "$*"; }

if [[ $# -eq 0 ]]; then
  agents=(nyla aoi party)
else
  agents=("$@")
fi

for agent in "${agents[@]}"; do
  target="gui/$(id -u)/ai.openclaw.livekit-agent-${agent}"
  launchctl kickstart -k "${target}"
  log "kickstarted ${target}"
done

log "give it ~5s, then scripts/health-check.sh to confirm all three re-registered."
