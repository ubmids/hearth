"""The HTTP surface: Streamable HTTP MCP endpoint plus the OAuth 2.1 metadata.

Every conformance requirement Alexa+ states is implemented here explicitly and
commented with why, because three of them are traps:

  - the 401 must NOT carry `WWW-Authenticate`, against RFC 9728 convention
  - both well-known documents must exist, not just the RFC 9728 one
  - the bearer token must be rejected if it arrives in the query string
"""
import json
import os
import time
import urllib.parse

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


async def _keepalive(url: str, every: int, log=print):
    """Keep a sleeping free instance awake by calling our own public health URL.

    Render spins a free service down after roughly 15 minutes without an inbound
    request, and the cold start that follows was measured at 641ms against a
    500ms requirement. The request has to arrive through the public URL to count
    as inbound, so this deliberately goes out to the internet and back rather
    than hitting the loopback interface.

    This is a stopgap for the free plan and nothing more. On a paid instance
    there is no spin-down and HEARTH_KEEPALIVE should be turned off: an app that
    pings itself forever is a smell, not an architecture.
    """
    import asyncio

    import httpx

    await asyncio.sleep(30)                    # let the first boot settle
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            try:
                r = await client.get(url)
                log(f"keepalive {r.status_code} {url}")
            except Exception as e:             # a failed ping must never take
                log(f"keepalive failed: {e}")  # the service down with it
            await asyncio.sleep(every)


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
        # Parsed by hand rather than with `await request.form()`, which pulls in
        # python-multipart. That package is not a FastAPI dependency, so the
        # endpoint works on any machine that happens to have it and returns 500
        # on one that does not. It cost a deploy to find. An OAuth token request
        # is always application/x-www-form-urlencoded and never multipart, so
        # the dependency bought nothing and could only ever fail in production.
        raw = (await request.body()).decode("utf-8", "replace")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
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

        t0 = time.perf_counter()
        headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
        sid = request.headers.get("mcp-session-id")

        # A batch is a JSON array; a single call is an object. Both are valid.
        def timed(content, status=200):
            headers["Server-Timing"] = (
                f'app;dur={(time.perf_counter() - t0) * 1000:.3f};desc="hearth"')
            return JSONResponse(content, status_code=status, headers=headers)

        if isinstance(payload, list):
            out = [r for r in (server.handle(m) for m in payload) if r is not None]
            return timed(out) if out else timed(None, 202)

        if payload.get("method") == "initialize":
            sid = server.new_session()
            headers["Mcp-Session-Id"] = sid
        elif sid and sid not in server.sessions:
            return JSONResponse({"error": "no such session"}, status_code=404,
                                headers=headers)

        result = server.handle(payload)
        if result is None:
            return timed(None, 202)          # notifications are accepted with no body
        return timed(result)

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
                "beliefs": sum(1 for b in household.beliefs if b.is_live()),
                "keepalive": bool(app.state.keepalive_task)}

    app.state.keepalive_task = None

    @app.on_event("startup")
    async def _start_keepalive():
        import asyncio
        if os.getenv("HEARTH_KEEPALIVE", "0") not in ("1", "true", "yes"):
            return
        every = int(os.getenv("HEARTH_KEEPALIVE_SECONDS", "600"))
        app.state.keepalive_task = asyncio.create_task(
            _keepalive(f"{issuer}/healthz", every))

    @app.on_event("shutdown")
    async def _stop_keepalive():
        if app.state.keepalive_task:
            app.state.keepalive_task.cancel()

    return app


app = create_app()
