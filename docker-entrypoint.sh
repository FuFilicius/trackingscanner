#!/usr/bin/env sh
set -eu

if printf '%s\n' " $* " | grep -q ' --headed '; then
  export DISPLAY=:99
  Xvfb :99 -screen 0 1920x1080x24 &
  xvfb_pid=$!

  cleanup() {
    kill "$xvfb_pid" 2>/dev/null || true
  }
  trap cleanup EXIT INT TERM

  exec python -u main.py "$@"
  # exec xvfb-run -a -s "-screen 0 1920x1080x24" python main.py "$@"
else
  exec python -u main.py "$@"
fi