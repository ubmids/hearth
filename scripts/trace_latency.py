"""Server-Timing for check_dose as the record grows (red-team audit 028, #6/#14).

Makes N tools/call requests on one session against a running Hearth and prints
the median server-side time (the Server-Timing header, not the round trip) for
each block of calls, so growth with the size of the record is visible.

    python3 scripts/trace_latency.py http://127.0.0.1:8765 5000

Run Hearth with HEARTH_DATA set: the cost being measured is persistence.
"""
import http.client
import json
import statistics
import sys
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
BLOCK = int(sys.argv[3]) if len(sys.argv) > 3 else 500

tok = json.load(urllib.request.urlopen(BASE + "/api/console-token"))["access_token"]
u = urllib.parse.urlparse(BASE)
conn = http.client.HTTPConnection(u.netloc, timeout=30)
head = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"}
conn.request("POST", "/mcp", json.dumps({
    "jsonrpc": "2.0", "id": 0, "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {},
               "clientInfo": {"name": "latency", "version": "1"}}}), head)
r = conn.getresponse(); r.read()
head["Mcp-Session-Id"] = r.getheader("Mcp-Session-Id") or ""
head["MCP-Protocol-Version"] = "2025-11-25"
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "check_dose",
                              "arguments": {"medication": "warfarin",
                                            "asked_by": "Tom"}}})
block = []
for i in range(1, N + 1):
    conn.request("POST", "/mcp", body, head)
    r = conn.getresponse(); r.read()
    assert r.status == 200, r.status
    st = r.getheader("Server-Timing", "")
    block.append(float(st.split("dur=")[1].split(";")[0]))
    if i % BLOCK == 0:
        print(f"calls {i - BLOCK + 1:>5}-{i:<5} server p50 {statistics.median(block):6.2f} ms"
              f"  p95 {sorted(block)[int(len(block) * .95)]:6.2f} ms", flush=True)
        block = []
