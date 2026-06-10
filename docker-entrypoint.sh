#!/usr/bin/env sh
set -eu

headed=0
for arg in "$@"; do
  if [ "$arg" = "--headed" ]; then
    headed=1
    break
  fi
done

if [ "$headed" -eq 1 ]; then
  export DISPLAY=:99
  Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
  xvfb_pid=$!

  cleanup() {
    kill "$xvfb_pid" 2>/dev/null || true
  }
  trap cleanup EXIT INT TERM

  python -u main.py "$@"
  exit_code=$?
  exit "$exit_code"
fi

exec python -u main.py "$@"
