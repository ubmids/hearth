"""An existing AI assistant, calling the same Hearth server the simulator calls.

The Alexa+ rules call this "a nice bonus": besides the simulated Alexa+ client,
show a real, shipping assistant using the add-on. This runs Claude Code as the
MCP client, headless, with Hearth's Agent Skill (skills/hearth-care/SKILL.md) as
its instructions, against a Hearth server it reaches over Streamable HTTP with
a bearer token minted by the ordinary OAuth 2.1 + PKCE flow.

Nothing is stubbed. The assistant chooses the tools; Hearth's server writes the
record. At the end the script reads that record back from the server, so what
the assistant claims it did can be checked against what the server saw.

Run (needs a logged-in `claude` on PATH, or CLAUDE_BIN):
    uvicorn hearth.app:app --port 8765 &      # HEARTH_ISSUER=http://127.0.0.1:8765
    python3 demo/assistant.py http://127.0.0.1:8765

Writes demo/assistant.md: each request, the tool calls the assistant made, its
answer, and the server's record of the same calls.
"""
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# One conversation per line, as separate sessions: memory across sessions is
# the server's job, not the assistant's context window.
TURNS = [
    ("Rose", "I'm just going to take my blood thinner."),
    ("Tom", "What did I miss with Mom today?"),
    ("Ada", "Mom's cardiology moved to Thursday at 10. Sort it out."),
    ("Tom", "Can Mom have a coffee this afternoon?"),
]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def token_for(base: str) -> str:
    """The authorization code flow with PKCE S256, the way a host does it."""
    meta = json.load(urllib.request.urlopen(f"{base}/.well-known/oauth-authorization-server"))
    prm = json.load(urllib.request.urlopen(f"{base}/.well-known/oauth-protected-resource"))
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect = f"{base}/callback"
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": meta.get("client_id_hint", "hearth-dev-client"),
        "redirect_uri": redirect, "code_challenge": challenge,
        "code_challenge_method": "S256", "resource": prm["resource"], "state": "x"})
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(f"{meta['authorization_endpoint']}?{q}")
        raise SystemExit("authorize did not redirect")
    except urllib.error.HTTPError as e:
        loc = e.headers["Location"]
    code = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["code"][0]
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "client_id": meta.get("client_id_hint", "hearth-dev-client"),
        "redirect_uri": redirect, "resource": prm["resource"]}).encode()
    return json.load(urllib.request.urlopen(meta["token_endpoint"], body))["access_token"]


def mcp(base, token, method, params=None, sid=None):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
         "Accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": "2025-11-25"}
    if sid:
        h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(f"{base}/mcp", json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}).encode(), h)
    r = urllib.request.urlopen(req)
    return json.load(r), r.headers.get("Mcp-Session-Id")


def ask(claude, cfg, skill, who, said):
    prompt = (f"{who} says to the kitchen speaker: \"{said}\"\n\n"
              "Answer as the household's voice assistant, in one or two spoken "
              "sentences, using the Hearth tools.")
    out = subprocess.run(
        [claude, "-p", prompt, "--output-format", "stream-json", "--verbose",
         "--mcp-config", cfg, "--strict-mcp-config",
         "--allowedTools", "mcp__hearth",
         "--append-system-prompt", skill, "--model", "sonnet"],
        capture_output=True, text=True, timeout=300, cwd=tempfile.gettempdir())
    calls, answer = [], ""
    for line in out.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use" and c["name"].startswith("mcp__hearth__"):
                    calls.append((c["name"].removeprefix("mcp__hearth__"), c["input"]))
        if ev.get("type") == "result":
            answer = ev.get("result", "")
    if not answer:
        sys.stderr.write(out.stderr[-2000:])
    return calls, answer.strip()


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765").rstrip("/")
    claude = os.getenv("CLAUDE_BIN", "claude")
    token = token_for(base)
    skill = open(os.path.join(ROOT, "skills", "hearth-care", "SKILL.md")).read()
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"mcpServers": {"hearth": {
            "type": "http", "url": f"{base}/mcp",
            "headers": {"Authorization": f"Bearer {token}"}}}}, f)
        cfg = f.name
    lines = ["# An existing assistant on the same server",
             "",
             "Claude Code, headless, as the MCP client, with Hearth's Agent Skill "
             "(`skills/hearth-care/SKILL.md`) as its instructions. It reached Hearth "
             "over Streamable HTTP with a token from the OAuth 2.1 + PKCE flow. "
             "Each request is a fresh session; the tool calls are the ones it chose. "
             "Generated by `demo/assistant.py`.", ""]
    try:
        for who, said in TURNS:
            print(f"{who}: {said}", flush=True)
            calls, answer = ask(claude, cfg, skill, who, said)
            lines += [f"**{who}:** {said}", ""]
            for name, args in calls:
                lines.append(f"- `tools/call {name} {json.dumps(args)}`")
            lines += ["", f"**Assistant:** {answer}", ""]
            print(f"  calls: {[c[0] for c in calls]}\n  says: {answer}\n", flush=True)
    finally:
        os.unlink(cfg)
    # The server's own account of the same calls.
    _, sid = mcp(base, token, "initialize", {
        "protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "assistant-demo-audit", "version": "1"}})
    rec, _ = mcp(base, token, "tools/call", {"name": "record", "arguments": {"limit": 20}}, sid)
    r = rec["result"]
    lines += ["## What the server recorded", "", r["content"][0]["text"], ""]
    for item in reversed(r.get("structuredContent", {}).get("card", {}).get("items", [])
                         or r.get("structuredContent", {}).get("items", [])):
        lines.append(f"- {item['label']}: {item['detail']}")
    with open(os.path.join(HERE, "assistant.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote demo/assistant.md")


if __name__ == "__main__":
    main()
