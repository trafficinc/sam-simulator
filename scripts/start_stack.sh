#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
mkdir -p "$RUN_DIR"

start_if_needed() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(cat "$pid_file")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "$name already running with PID $existing_pid"
      return
    fi
    rm -f "$pid_file"
  fi

  (
    cd "$ROOT_DIR"
    nohup "$@" >"$log_file" 2>&1 &
    echo $! >"$pid_file"
  )

  echo "Started $name with PID $(cat "$pid_file")"
}

start_if_needed "hub" "$RUN_DIR/hub.pid" "$RUN_DIR/hub.log" uvicorn hub.app:app --reload
start_if_needed "pilot" "$RUN_DIR/pilot.pid" "$RUN_DIR/pilot.log" python -m pilot.client
start_if_needed "shield" "$RUN_DIR/shield.pid" "$RUN_DIR/shield.log" python -m shield.client

echo
echo "Logs:"
echo "  $RUN_DIR/hub.log"
echo "  $RUN_DIR/pilot.log"
echo "  $RUN_DIR/shield.log"
