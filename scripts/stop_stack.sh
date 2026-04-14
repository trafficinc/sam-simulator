#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_if_running() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    echo "$name not running"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "Stopped $name (PID $pid)"
  else
    echo "$name stale PID file removed"
  fi

  rm -f "$pid_file"
}

stop_if_running "shield" "$RUN_DIR/shield.pid"
stop_if_running "pilot" "$RUN_DIR/pilot.pid"
stop_if_running "hub" "$RUN_DIR/hub.pid"
