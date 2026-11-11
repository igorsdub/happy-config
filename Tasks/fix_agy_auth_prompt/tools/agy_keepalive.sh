#!/bin/zsh
# Keeps agy's keychain token fresh. Run by launchd every 30 minutes (outside the sandbox).
# Uses `agy models` (goes through the auth chain, spends no prompt quota).
# Retries once on AGY_AUTH_FALLBACK (exit 75); never opens a browser; never loops.
DIR=${0:A:h}
LOCK=$HOME/.gemini/agy_keepalive.lock
LOGF=$DIR/../.context/keepalive.log
mkdir -p "${LOGF:h}"
mkdir "$LOCK" 2>/dev/null || { echo "$(date -Iseconds) skip: another keepalive running" >>"$LOGF"; exit 0; }
trap 'rmdir "$LOCK"' EXIT

for attempt in 1 2; do
  AGY_SAFE_LIMIT=60 "$DIR/agy_safe.sh" models </dev/null >/dev/null 2>&1
  rc=$?
  echo "$(date -Iseconds) attempt=$attempt rc=$rc" >>"$LOGF"
  [[ $rc -eq 0 ]] && exit 0
  [[ $rc -eq 75 ]] || break
done
echo "$(date -Iseconds) FAILED: needs user attention (rc=$rc)" >>"$LOGF"
exit $rc
