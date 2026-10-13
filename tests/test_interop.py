"""Hearth against the official MCP Python SDK client, over a real socket.

Every other suite drives Hearth with requests written by hand, which proves
Hearth does what its author thinks the spec says. This one hands the
conversation to the reference client from the MCP project (`pip install mcp`),
which has its own reading of the spec: it negotiates the version, opens and
closes the session, and parses every result into its own types.

The bearer token comes from the ordinary OAuth 2.1 + PKCE flow, over HTTP.

Skipped, and says so, if the SDK is not installed.
"""
import asyncio
import os
import socket
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "demo"))
os.environ.setdefault("HEARTH_TZ", "America/New_York")

try:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client
except ImportError:                                    # pragma: no cover
    ClientSession = None

import uvicorn

from hearth.app import create_app


def serve():
    """A real Hearth on a free loopback port, in this process."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    app = create_app(issuer=base, resource=f"{base}/mcp", seed="care")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{base}/healthz", timeout=1)
            return base, app, server
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("server did not start")


async def converse(base, token):
    http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
    async with streamable_http_client(f"{base}/mcp", http_client=http) as streams:
        async with ClientSession(streams[0], streams[1]) as s:
            init = await s.initialize()
            tools = await s.list_tools()
            refused = await s.call_tool("give_dose", {"medication": "warfarin",
                                                      "given_by": "Rose"})
            why = await s.call_tool("why", {"domain": "medication"})
            return init, tools, refused, why


def test_the_reference_client_negotiates_lists_and_calls():
    if ClientSession is None:
        print("SKIP the official MCP SDK is not installed (pip install mcp)")
        return
    import assistant                                   # the PKCE helper
    base, app, server = serve()
    try:
        token = assistant.token_for(base)
        init, tools, refused, why = asyncio.run(converse(base, token))
        assert getattr(init, "protocol_version", None) == "2025-11-25", init
        names = {t.name for t in tools.tools}
        assert {"give_dose", "arrange", "reorder", "catch_up", "record"} <= names, names
        text = refused.content[0].text
        assert text.startswith("Hold on, Rose."), text
        sc = refused.structured_content
        assert sc["outcome"] == "refused" and sc["card"]["tone"] == "stop", sc
        assert "Ada set it" in why.content[0].text, why.content[0].text
        # The SDK closed its session with DELETE; the record kept both calls.
        subject = app.state.auth.verify(f"Bearer {token}").subject
        mcp = app.state.home_for(subject)[2]
        assert not mcp.sessions, mcp.sessions
        assert [e.tool for e in mcp.trace.entries] == ["give_dose", "why"]
    finally:
        server.should_exit = True
    print("PASS the official MCP SDK client negotiates 2025-11-25, lists, calls, "
          "and gets the refusal with its card")


if __name__ == "__main__":
    test_the_reference_client_negotiates_lists_and_calls()
    print("\nall green (interop)")
