"""The HTTP surface: Streamable HTTP MCP endpoint plus the OAuth 2.1 metadata.

Every conformance requirement Alexa+ states is implemented here explicitly and
commented with why, because three of them are traps:

  - the 401 must NOT carry `WWW-Authenticate`, against RFC 9728 convention
  - both well-known documents must exist, not just the RFC 9728 one
  - the bearer token must be rejected if it arrives in the query string
"""
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .extract import extract
from .household import Household
from .ledger import Ledger
from .mcp import PROTOCOL_VERSION, HearthMCP
from .oauth import AuthServer
from .store import Store


def seed_demo_household(h: Household) -> None:
    """A house with a real shape: one member who owns the thermostat, one who
    does not, and a child who owns their own room."""
    if h.members:
        return
    h.add_member("Dad", role="adult", grants=["thermostat"])
    h.add_member("Mum", role="adult", grants=["shopping"])
    h.add_member("Ada", role="child", grants=["bedroom.ada"])


def create_app(*, data_path=None, issuer=None, resource=None, seed=True) -> FastAPI:
    issuer = (issuer or os.getenv("HEARTH_ISSUER", "http://localhost:8000")).rstrip("/")
    resource = (resource or os.getenv("HEARTH_RESOURCE", f"{issuer}/mcp")).rstrip("/")

    store = Store(data_path) if data_path else None
    household = Household("home", store=store)
    if seed:
        seed_demo_household(household)
    ledger = Ledger(household, store=store)
    server = HearthMCP(household, ledger, extractor=extract)
    auth = AuthServer(issuer=issuer, resource=resource)

    app = FastAPI(title="Hearth", version="0.1.0")
    app.state.household = household
    app.state.ledger = ledger
    app.state.mcp = server
    app.state.auth = auth

    # --- metadata ----------------------------------------------------------
    @app.get("/.well-known/oauth-protected-resource")
    @app.get("/.well-known/oauth-protected-resource/mcp")
    async def prm():
        return auth.protected_resource_metadata()

    @app.get("/.well-known/oauth-authorization-server")
    async def asm():
        return auth.authorization_server_metadata()

    # --- authorization code flow ------------------------------------------
    @app.get("/authorize")
    async def authorize(request: Request):
        q = request.query_params
        url, err = auth.authorize(
            client_id=q.get("client_id", ""),
            redirect_uri=q.get("redirect_uri", ""),
            code_challenge=q.get("code_challenge", ""),
            code_challenge_method=q.get("code_challenge_method", ""),
            resource=q.get("resource", ""),
            scope=q.get("scope", ""),
            state=q.get("state", ""),
        )
        if err:
            return JSONResponse(err, status_code=400)
        return RedirectResponse(url, status_code=302)

    @app.post("/token")
    async def token(request: Request):
        form = await request.form()
        body, err = auth.exchange(
            grant_type=form.get("grant_type", ""),
            code=form.get("code", ""),
            code_verifier=form.get("code_verifier", ""),
            client_id=form.get("client_id", ""),
            redirect_uri=form.get("redirect_uri", ""),
            resource=form.get("resource", ""),
        )
        if err:
            return JSONResponse(err, status_code=400)
        # OAuth 2.1 forbids caching token responses anywhere.
        return JSONResponse(body, headers={"Cache-Control": "no-store",
                                           "Pragma": "no-cache"})

    # --- the MCP endpoint --------------------------------------------------
    def _unauthorized():
        # No WWW-Authenticate header. Alexa+ states this explicitly, and it is
        # the opposite of what RFC 9728 and most MCP hosts expect, so an SDK
        # that adds the header "correctly" would fail Amazon's conformance check.
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        if "access_token" in request.query_params:
            # Bearer tokens in the query string leak through logs, referrers and
            # history. Alexa+ forbids it, so reject rather than quietly accept.
            return JSONResponse({"error": "invalid_request",
                                 "error_description": "bearer token must be in the "
                                                      "Authorization header"},
                                status_code=400)
        if auth.verify(request.headers.get("authorization")) is None:
            return _unauthorized()

        try:
            payload = json.loads(await request.body() or b"")
        except json.JSONDecodeError:
            return JSONResponse({"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32700, "message": "Parse error"}},
                                status_code=400)

        headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
        sid = request.headers.get("mcp-session-id")

        # A batch is a JSON array; a single call is an object. Both are valid.
        if isinstance(payload, list):
            out = [r for r in (server.handle(m) for m in payload) if r is not None]
            return JSONResponse(out, headers=headers) if out else \
                JSONResponse(None, status_code=202, headers=headers)

        if payload.get("method") == "initialize":
            sid = server.new_session()
            headers["Mcp-Session-Id"] = sid
        elif sid and sid not in server.sessions:
            return JSONResponse({"error": "no such session"}, status_code=404,
                                headers=headers)

        result = server.handle(payload)
        if result is None:
            # Notifications are accepted with no body.
            return JSONResponse(None, status_code=202, headers=headers)
        return JSONResponse(result, headers=headers)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "protocol": PROTOCOL_VERSION,
                "members": len(household.members),
                "beliefs": sum(1 for b in household.beliefs if b.is_live())}

    return app


app = create_app()
