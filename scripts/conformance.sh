#!/usr/bin/env bash
# Run the official MCP conformance suite (@modelcontextprotocol/conformance)
# against Hearth, spec 2025-11-25.
#
#   scripts/conformance.sh            # the applicable scenarios; exits 1 on any failure
#   scripts/conformance.sh --all      # every server scenario, for the full picture
#
# What it does:
#   1. starts Hearth on 127.0.0.1:$HEARTH_PORT (default 8765) with a throwaway
#      data dir, unless HEARTH_UPSTREAM points at one already running;
#   2. starts scripts/conformance_proxy.py on 127.0.0.1:$PROXY_PORT (8766),
#      which adds a bearer token to each request and changes nothing else
#      (the suite has no auth option, and Hearth answers 401 without one);
#   3. runs each scenario against http://127.0.0.1:$PROXY_PORT/mcp.
#
# Applicable scenarios are the ones that test a server's own protocol and
# transport behaviour. The rest of the suite calls fixture tools, prompts and
# resources that only the reference "everything" server has (test_simple_text,
# test_prompt_with_image, test://static-text ...), or capabilities Hearth does
# not declare (logging, completions, subscriptions, sampling, elicitation).
# `--all` runs those too; they fail for that reason and are reported, not hidden.
#
# Needs node >= 20 (npx) and the Python deps in requirements-dev.txt.
set -euo pipefail
cd "$(dirname "$0")/.."

SUITE_VERSION="${CONFORMANCE_VERSION:-0.1.16}"
HEARTH_PORT="${HEARTH_PORT:-8765}"
PROXY_PORT="${PROXY_PORT:-8766}"
PY="${PYTHON:-python3}"
OUT="${CONFORMANCE_OUT:-conformance-results}"
APPLICABLE=(server-initialize ping tools-list resources-list
            server-sse-multiple-streams dns-rebinding-protection)

pids=()
cleanup() { for p in "${pids[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

wait_for() {  # url
  for _ in $(seq 1 50); do curl -sf "$1" >/dev/null && return 0; sleep 0.2; done
  echo "timed out waiting for $1" >&2; return 1
}

if [ -z "${HEARTH_UPSTREAM:-}" ]; then
  DATA="$(mktemp -d)"
  HEARTH_DATA="$DATA/h.json" HEARTH_ISSUER="http://127.0.0.1:$HEARTH_PORT" \
    "$PY" -m uvicorn hearth.app:app --host 127.0.0.1 --port "$HEARTH_PORT" \
    --log-level warning & pids+=($!)
  export HEARTH_UPSTREAM="http://127.0.0.1:$HEARTH_PORT"
  wait_for "$HEARTH_UPSTREAM/healthz"
fi

"$PY" -m uvicorn scripts.conformance_proxy:app --host 127.0.0.1 \
  --port "$PROXY_PORT" --log-level warning & pids+=($!)
wait_for "http://127.0.0.1:$PROXY_PORT/healthz"

URL="http://127.0.0.1:$PROXY_PORT/mcp"
mkdir -p "$OUT"
if [ "${1:-}" = "--all" ]; then
  npx -y "@modelcontextprotocol/conformance@$SUITE_VERSION" server \
    --url "$URL" --spec-version 2025-11-25 -o "$OUT" || true
  exit 0
fi

fail=0
for s in "${APPLICABLE[@]}"; do
  if npx -y "@modelcontextprotocol/conformance@$SUITE_VERSION" server \
       --url "$URL" --spec-version 2025-11-25 --scenario "$s" -o "$OUT" \
       > "$OUT/$s.log" 2>&1; then
    echo "PASS $s"
  else
    echo "FAIL $s"; tail -n 20 "$OUT/$s.log"; fail=1
  fi
done
exit $fail
