#!/usr/bin/env bash
# The five MCP 2025-11-25 transport probes from the red-team audit (028, #3),
# as curl, against a running Hearth. Prints one line per probe: what was sent,
# the status, and the body. Used for the before/after evidence in the report.
#
#   scripts/transport_probes.sh http://127.0.0.1:8775
#
# Needs a local Hearth (the token comes from the loopback-only console route).
set -u
BASE="${1:-http://127.0.0.1:8775}"
TOK=$(curl -s "$BASE/api/console-token" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
A=(-H "Authorization: Bearer $TOK" -H "Content-Type: application/json"
   -H "Accept: application/json, text/event-stream")
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"probe","version":"1"}}}'

probe() {  # name, then curl args
  local name="$1"; shift
  local out; out=$(curl -s -w '\n%{http_code}' "$@")
  printf '%-34s -> %s %s\n' "$name" "$(tail -n1 <<<"$out")" "$(head -n -1 <<<"$out" | head -c 200)"
}

SID=$(curl -s -D - -o /dev/null "${A[@]}" -d "$INIT" "$BASE/mcp" | tr -d '\r' | awk -F': ' 'tolower($1)=="mcp-session-id"{print $2}')
probe "1 Origin: http://evil.example.com" "${A[@]}" -H "Origin: http://evil.example.com" -d "$INIT" "$BASE/mcp"
probe "2 MCP-Protocol-Version: 1999-01-01" "${A[@]}" -H "Mcp-Session-Id: $SID" -H "MCP-Protocol-Version: 1999-01-01" -d '{"jsonrpc":"2.0","id":2,"method":"ping"}' "$BASE/mcp"
probe "3 ping without Mcp-Session-Id" "${A[@]}" -d '{"jsonrpc":"2.0","id":3,"method":"ping"}' "$BASE/mcp"
probe "4 JSON-RPC batch" "${A[@]}" -H "Mcp-Session-Id: $SID" -d '[{"jsonrpc":"2.0","id":4,"method":"ping"},{"jsonrpc":"2.0","id":5,"method":"tools/list"}]' "$BASE/mcp"
probe "5 give_dose with bogus argument" "${A[@]}" -H "Mcp-Session-Id: $SID" -d '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"give_dose","arguments":{"medication":"warfarin","given_by":"Rose","bogus":1}}}' "$BASE/mcp"
