"""Bearer-injecting loopback proxy for the official MCP conformance suite.

`npx @modelcontextprotocol/conformance server` has no way to send an
Authorization header, and Hearth answers every unauthenticated /mcp request
with 401 (as Alexa+ requires). This forwards each request to Hearth with a
bearer token added and nothing else changed: Host, Origin, MCP-Protocol-Version
and Mcp-Session-Id pass through as the suite sent them, so the transport
checks (DNS rebinding, version header, sessions) are exercised against Hearth
itself, not against this proxy.

    HEARTH_UPSTREAM=http://127.0.0.1:8775 \
    HEARTH_CONFORMANCE_TOKEN=... \
    uvicorn scripts.conformance_proxy:app --port 8776

Without HEARTH_CONFORMANCE_TOKEN the token is minted from the upstream's
loopback-only /api/console-token, which only works when Hearth is local.
Loopback only: it holds a live token, so never bind it to 0.0.0.0.
"""
import os

import httpx
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

UP = os.getenv("HEARTH_UPSTREAM", "http://127.0.0.1:8775").rstrip("/")
_TOKEN = {"value": os.getenv("HEARTH_CONFORMANCE_TOKEN", "")}
HOP = {"content-length", "transfer-encoding", "connection", "keep-alive"}


async def token(client: httpx.AsyncClient) -> str:
    if not _TOKEN["value"]:
        r = await client.get(UP + "/api/console-token")
        r.raise_for_status()
        _TOKEN["value"] = r.json()["access_token"]
    return _TOKEN["value"]


async def forward(request):
    async with httpx.AsyncClient(timeout=30) as client:
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
        headers["authorization"] = f"Bearer {await token(client)}"
        r = await client.request(request.method, UP + request.url.path,
                                 params=request.query_params, headers=headers,
                                 content=await request.body())
    out = {k: v for k, v in r.headers.items()
           if k.lower() not in HOP | {"content-encoding"}}
    return Response(r.content, status_code=r.status_code, headers=out)


app = Starlette(routes=[Route("/{path:path}", forward,
                              methods=["GET", "POST", "DELETE"])])
