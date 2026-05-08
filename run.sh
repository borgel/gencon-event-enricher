#!/usr/bin/env bash
# End-to-end pipeline driver. Composes the existing Python entry points.
#
#   ./run.sh                              deterministic build only (free, ~3 min)
#   ./run.sh --with-agent                 build → agent matcher → rebuild
#   ./run.sh --with-agent --limit 50      cap agent batches in this run
#   ./run.sh --with-agent --dry-run       preview agent prompts, no API calls
#   ./run.sh --help                       this message
#
# Anything after --with-agent is forwarded verbatim to match_with_agent.py.
set -euo pipefail

# Run from the repo root regardless of where we were invoked from.
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")"

usage() { awk '/^set -euo/{exit} NR>1{sub(/^# ?/,""); print}' "$0"; }

case "${1-}" in
    -h|--help) usage; exit 0 ;;
esac

with_agent=0
if [[ "${1-}" == "--with-agent" ]]; then
    with_agent=1
    shift
fi

if (( with_agent )); then
    echo "==> [1/3] Building events.json (deterministic match)"
    uv run python -m pipeline.build
    echo "==> [2/3] Running agent matcher"
    uv run python -m pipeline.match_with_agent "$@"
    echo "==> [3/3] Rebuilding to integrate new agent mappings"
    uv run python -m pipeline.build
else
    if [[ $# -gt 0 ]]; then
        echo "error: extra args ($*) only meaningful with --with-agent" >&2
        usage >&2
        exit 2
    fi
    echo "==> Building events.json (deterministic match)"
    uv run python -m pipeline.build
fi

echo "==> Done."
