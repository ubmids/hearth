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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .extract import detect_context_end, extract
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
    server = HearthMCP(household, ledger, extractor=extract,
                       end_detector=detect_context_end)
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

    # --- console surface ---------------------------------------------------
    # The console is an operator view, not a second way in. It speaks to the
    # same bearer-protected API, and the only concession to convenience is that
    # a request arriving from the loopback interface can mint itself a token.
    # A deployed Hearth hands out nothing.
    def _is_local(request: Request) -> bool:
        host = (request.client.host if request.client else "") or ""
        return host in ("127.0.0.1", "::1", "localhost", "testclient")

    def _guard(request: Request):
        return auth.verify(request.headers.get("authorization")) is not None

    @app.get("/api/console-token")
    async def console_token(request: Request):
        if not _is_local(request):
            return JSONResponse({"error": "console tokens are loopback only"},
                                status_code=403)
        return {"access_token": auth.issue_for_testing(subject="console"),
                "token_type": "Bearer"}

    def _state():
        """Everything the console draws, resolved server-side.

        Resolution belongs here, not in the page: the console must show exactly
        what Alexa+ would be told, and a second implementation in JavaScript
        would drift from the real one and quietly lie on camera.
        """
        live = [b for b in household.beliefs if b.is_live()]
        slots, seen = [], set()
        for b in live:
            key = (b.domain, b.slot)
            if key in seen:
                continue
            seen.add(key)
            # Household-wide view, plus a view per member who has a scoped belief.
            audiences = [None] + sorted({x.scope for x in live
                                         if (x.domain, x.slot) == key and x.scope})
            for who in audiences:
                r = household.resolve(b.domain, b.slot, for_member=who)
                if r.winner is None:
                    continue
                slots.append({
                    "domain": b.domain, "slot": b.slot,
                    "about": household.name_of(who) if who else None,
                    "value": r.winner.value, "basis": r.basis,
                    "sentence": r.explain(household.name_of),
                    "winner": {"id": r.winner.id,
                               "holder": household.name_of(r.winner.holder),
                               "context": r.winner.context,
                               "stated_at": r.winner.stated_at},
                    "losers": [{"id": lb.id, "value": lb.value,
                                "holder": household.name_of(lb.holder),
                                "reason": why} for lb, why in r.losers],
                })
        contexts = {}
        for b in live:
            if b.context:
                contexts.setdefault(b.context, []).append(
                    f"{b.domain}.{b.slot}={b.value}")
        return {
            "members": [{"id": m.id, "name": m.name, "role": m.role,
                         "grants": m.grants} for m in household.members.values()],
            "slots": slots,
            "contexts": [{"name": k, "riding": v} for k, v in contexts.items()],
            "beliefs": [{**b.to_dict(), "holder_name": household.name_of(b.holder),
                         "live": b.is_live()} for b in household.beliefs],
            # The spoken explanation is computed here for the same reason the
            # resolution is: the console must show the exact sentence the
            # assistant would say, not a second rendering of it that can drift.
            "actions": [{**a.to_dict(), "why": ledger.why(action_id=a.id)}
                        for a in reversed(ledger.actions)][:25],
        }

    @app.get("/api/state")
    async def api_state(request: Request):
        if not _guard(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return _state()

    @app.post("/api/say")
    async def api_say(request: Request):
        if not _guard(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        said, speaker = body.get("said", ""), body.get("speaker", "")
        res = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": "remember",
                                        "arguments": {"said": said, "speaker": speaker}}})
        return {"reply": res["result"]["content"][0]["text"], "state": _state()}

    @app.post("/api/act")
    async def api_act(request: Request):
        """Act on a slot the way Alexa+ would, and log why."""
        if not _guard(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        domain, slot = body.get("domain"), body.get("slot")
        about = body.get("about")
        mid = next((m.id for m in household.members.values()
                    if m.name.lower() == str(about or "").lower()), None)
        r = household.resolve(domain, slot, for_member=mid)
        if r.winner is None:
            return {"reply": f"Nobody has set {domain}.{slot}.", "state": _state()}
        a = ledger.record(f"set {domain} {slot} to {r.winner.value}", domain,
                          resolution=r)
        return {"reply": f"Set {domain}.{slot} to {r.winner.value}.",
                "why": ledger.why(action_id=a.id), "state": _state()}

    @app.post("/api/retire")
    async def api_retire(request: Request):
        if not _guard(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        b = household.retire(body.get("belief_id"), reason="stood down in the console")
        return {"reply": (f"Stood down {b.domain}.{b.slot}={b.value}." if b
                          else "No standing belief with that id."), "state": _state()}

    @app.get("/console", response_class=HTMLResponse)
    async def console():
        path = os.path.join(os.path.dirname(__file__), "web", "console.html")
        with open(path) as f:
            return HTMLResponse(f.read())

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "protocol": PROTOCOL_VERSION,
                "members": len(household.members),
                "beliefs": sum(1 for b in household.beliefs if b.is_live())}

    return app


app = create_app()
