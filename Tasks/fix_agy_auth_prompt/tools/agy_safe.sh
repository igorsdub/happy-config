#!/bin/zsh
# Non-interactive agy wrapper: never lets agy sit in the browser OAuth flow.
# Run it WITH network + keychain access (outside the sandbox).
# Usage: agy_safe.sh [agy args...]
# Env:   AGY_SAFE_LIMIT  wall-clock seconds for the whole run (default 300)
# Exit:  agy's own code on normal finish
#        75  agy fell back to interactive OAuth (refresh failed or was too slow); retry once
#        76  wall-clock limit hit
LIMIT=${AGY_SAFE_LIMIT:-300}
LOGDIR=$HOME/.gemini/antigravity-cli/log
OUT=$(mktemp "${TMPDIR:-/tmp}/agysafe.XXXXXX") || exit 1
MARK=$(mktemp "${TMPDIR:-/tmp}/agysafe.mark.XXXXXX") || exit 1

perl -e 'setpgrp(0,0); exec @ARGV' agy "$@" </dev/null >"$OUT" 2>&1 &
pid=$!
killgrp() { kill -TERM -$pid 2>/dev/null; sleep 1; kill -KILL -$pid 2>/dev/null; }
cleanup() { killgrp; rm -f "$OUT" "$MARK"; }
trap 'cleanup; exit 130' INT TERM

start=$SECONDS
while kill -0 $pid 2>/dev/null; do
  # agy writes its auth fallback to its own log, not to stdout
  log=$(find "$LOGDIR" -name 'cli-*.log' -newer "$MARK" 2>/dev/null)
  if [[ -n $log ]] && grep -qs "triggering interactive OAuth" $=log; then
    killgrp
    echo "AGY_AUTH_FALLBACK: silent refresh failed or exceeded agy's 10s limit; retry once" >&2
    rm -f "$OUT" "$MARK"; exit 75
  fi
  if (( SECONDS - start > LIMIT )); then
    killgrp; cat "$OUT"; rm -f "$OUT" "$MARK"
    echo "AGY_TIMEOUT after ${LIMIT}s" >&2; exit 76
  fi
  sleep 1
done
wait $pid; rc=$?
cat "$OUT"; rm -f "$OUT" "$MARK"; exit $rc
