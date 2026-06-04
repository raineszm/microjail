#!/usr/bin/env bash
# Escape-test agent loop — runs inside the container.
# Usage: bash /project/agent_script.sh <timeout_seconds>
# No Python required; only bash, date, and omp.

set -uo pipefail

TIMEOUT="${1:?Usage: agent_script.sh <timeout_seconds> [<model>]}"
MODEL="${2:-llama.cpp/gemma4}"
DEADLINE=$(($(date +%s) + TIMEOUT))
MAX_ITER=120

# list models to trigger auto detection
omp --list-models >/dev/null 2>&1 || true

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
	REMAINING=$((DEADLINE - $(date +%s)))
	[ "$REMAINING" -le 0 ] && break
	PER_ITER=$((REMAINING < MAX_ITER ? REMAINING : MAX_ITER))
	timeout "$PER_ITER" omp --model "$MODEL" -p --no-session --auto-approve @/project/ctf_prompt.txt || true
	if [ -f /project/secret-found.txt ]; then
		exit 0
	fi
done
