#!/usr/bin/env bash
# ralph.sh — autonomous development loop (the "Ralph" pattern).
#
# What it does: feeds PROMPT.md to the coding agent again and again — one run
# per work item — until the work is done (DONE marker) or physical hardware
# testing is needed (READY_FOR_HW marker). Each run is a fresh agent session
# with no memory of the previous one; fix_plan.md is the shared memory.
#
# Where it runs: inside the skywriter-dev container (the agent must not touch
# hardware). From the host, use the same flags as run_sandbox.sh but replace
# the trailing `opencode --auto` with `bash ralph.sh`, e.g.:
#
#   docker run -it --rm \
#     --cap-drop ALL --security-opt no-new-privileges:true \
#     --pids-limit 512 --memory 8g \
#     --env-file /home/user/.config/skywriter-sandbox.env \
#     -v "$PWD:/workspace" \
#     -v skywriter-opencode:/home/dev/.local/share/opencode \
#     -v skywriter-arduino:/home/dev/.arduino15 \
#     skywriter-dev bash ralph.sh
#
# Budgets (override with environment variables):
#   RALPH_MAX_ITER                  max iterations   (default 40)
#   RALPH_MAX_HOURS                 wall-clock hours (default 6)
#   RALPH_MAX_CONSECUTIVE_FAILURES  stop after N failed runs in a row (default 5)
#
# Safety: every iteration ends in a git commit — the agent's own, or an
# automatic snapshot if it left work uncommitted. Logs land in logs/
# (gitignored). At the end the state is pushed to the remote so nothing is
# lost if the container or host dies.

set -euo pipefail

cd "$(dirname "$0")"

MAX_ITER=${RALPH_MAX_ITER:-40}
MAX_HOURS=${RALPH_MAX_HOURS:-6}
MAX_FAILS=${RALPH_MAX_CONSECUTIVE_FAILURES:-5}
LOG_DIR=logs

mkdir -p "$LOG_DIR"
start_ts=$(date +%s)
deadline=$((start_ts + MAX_HOURS * 3600))
fails=0

for i in $(seq 1 "$MAX_ITER"); do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "ralph: ${MAX_HOURS}h time budget exhausted — stopping." >&2
    break
  fi

  iter=$(printf '%03d' "$i")
  log="$LOG_DIR/ralph-${iter}-$(date +%Y%m%d-%H%M%S).log"
  echo "ralph: iteration $i/$MAX_ITER (log: $log)"

  if opencode run --auto "$(cat PROMPT.md)" 2>&1 | tee "$log"; then
    fails=0
  else
    fails=$((fails + 1))
    echo "ralph: iteration $i failed (consecutive failures: $fails)" >&2
    if [ "$fails" -ge "$MAX_FAILS" ]; then
      echo "ralph: too many consecutive failures — stopping." >&2
      break
    fi
  fi

  if [ -f DONE ]; then
    echo "ralph: DONE marker present — all work items complete and tests pass."
    break
  fi
  if [ -f READY_FOR_HW ]; then
    echo "ralph: READY_FOR_HW marker present — hardware validation needed."
    echo "ralph: run the host-side hardware loop (fix_plan.md Phase 4), which"
    echo "ralph: writes HW_REPORT.md, then rerun this loop."
    break
  fi

  # Safety net: never lose work if the agent forgot to commit.
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "ralph: automatic snapshot after iteration $i (work was left uncommitted)" || true
  fi
done

git push || echo "ralph: git push failed — commits are still on the bind mount." >&2

echo "ralph: stopped after $(( $(date +%s) - start_ts ))s. State: see $LOG_DIR/ and fix_plan.md."
