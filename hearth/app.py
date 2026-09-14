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
from fastapi.staticfiles import StaticFiles

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
    # Without a path the household lives in memory and a restart wipes it. That
    # is wrong for something whose entire pitch is that it remembers who said
    # what and when: a judge who adds a belief, comes back after the instance
    # recycles, and finds an empty house has been shown the opposite of the
    # product. The filesystem here is still ephemeral across deploys, which is
    # honest for a demo and noted in the README.
    data_path = data_path or os.getenv("HEARTH_DATA") or None
    issuer = (issuer or os.getenv("HEARTH_ISSUER", "http://localhost:8000")).rstrip("/")
    resource = (resource or os.getenv("HEARTH_RESOURCE", f"{issuer}/mcp")).rstrip("/")

    # The allowlist existed in AuthServer from the start and nothing ever filled
    # it, so the "redirect_uri not registered" branch was dead code in every
    # deployment and any redirect_uri was honoured. Comma separated, exact match,
    # and empty means the shape check in AuthServer.authorize is the only guard.
    registered = [u.strip() for u in
                  os.getenv("HEARTH_REDIRECT_URIS", "").split(",") if u.strip()]
    auth = AuthServer(issuer=issuer, resource=resource,
                      redirect_uris=registered or None)

    # One household per authenticated subject. A single shared house was fine
    # while the only client was a test, and wrong the moment the thing was
    # reachable: every visitor wrote into the same home, and the demo filled up
    # with other people's thermostats.
    homes: dict[str, tuple] = {}

    def home_for(subject: str):
        if subject not in homes:
            st = Store(f"{data_path}.{subject}") if data_path else None
            h = Household("home", store=st)
            if seed:
                seed_demo_household(h)
            led = Ledger(h, store=st)
            homes[subject] = (h, led, HearthMCP(h, led, extractor=extract,
                                                end_detector=detect_context_end))
        return homes[subject]

    # The default household backs anything that arrives without a subject, and
    # is what `app.state.household` exposes for tests and local tooling.
    household, ledger, server = home_for("default")

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
        caller = auth.verify(request.headers.get("authorization"))
        if caller is None:
            return _unauthorized()
        _, _, server = home_for(caller.subject)

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

    def _state(house=None, led=None):
        """Everything the console draws, resolved server-side.

        Resolution belongs here, not in the page: the console must show exactly
        what Alexa+ would be told, and a second implementation in JavaScript
        would drift from the real one and quietly lie on camera.
        """
        household, ledger = (house or homes["default"][0],
                             led or homes["default"][1])
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
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return _state(*home_for(tok.subject)[:2])

    @app.post("/api/say")
    async def api_say(request: Request):
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        said, speaker = body.get("said", ""), body.get("speaker", "")
        h, led, srv = home_for(tok.subject)
        res = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "remember",
                                     "arguments": {"said": said, "speaker": speaker}}})
        return {"reply": res["result"]["content"][0]["text"], "state": _state(h, led)}

    @app.post("/api/act")
    async def api_act(request: Request):
        """Act on a slot the way Alexa+ would, and log why."""
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        domain, slot = body.get("domain"), body.get("slot")
        about = body.get("about")
        h, led, _ = home_for(tok.subject)
        mid = next((m.id for m in h.members.values()
                    if m.name.lower() == str(about or "").lower()), None)
        r = h.resolve(domain, slot, for_member=mid)
        if r.winner is None:
            return {"reply": f"Nobody has set {domain}.{slot}.", "state": _state(h, led)}
        a = led.record(f"set {domain} {slot} to {r.winner.value}", domain,
                       resolution=r)
        return {"reply": f"Set {domain}.{slot} to {r.winner.value}.",
                "why": led.why(action_id=a.id), "state": _state(h, led)}

    @app.post("/api/retire")
    async def api_retire(request: Request):
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        h, led, _ = home_for(tok.subject)
        b = h.retire(body.get("belief_id"), reason="stood down in the console")
        return {"reply": (f"Stood down {b.domain}.{b.slot}={b.value}." if b
                          else "No standing belief with that id."),
                "state": _state(h, led)}

    # The add-on manifest requires HTTPS URLs for six icons, a carousel image,
    # a privacy policy and terms of use. Serving them from the service itself
    # means the listing has no dependency on a second host that could be down,
    # expire, or quietly start returning a parked-domain page during judging.
    app.mount("/assets", StaticFiles(directory=os.path.join(
        os.path.dirname(__file__), "web", "assets")), name="assets")

    def _page(title: str, body: str) -> HTMLResponse:
        return HTMLResponse(f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{title} · Hearth</title>
<style>
 body{{margin:0;background:#14100e;color:#f2e9e1;
      font:16px/1.65 ui-sans-serif,-apple-system,"Segoe UI",sans-serif}}
 main{{max-width:64ch;margin:0 auto;padding:56px 20px 80px}}
 h1{{font-size:27px;letter-spacing:-.02em;margin:0 0 6px}}
 h2{{font-size:15px;letter-spacing:.1em;text-transform:uppercase;color:#6f5f54;
     margin:34px 0 10px}}
 p,li{{color:#cbbcb0}} a{{color:#ff7a45}} strong{{color:#f2e9e1}}
 .sub{{color:#a4907f;margin:0 0 8px}}
</style><main><h1>{title}</h1>{body}
<p style="margin-top:44px"><a href="/console">Back to the console</a></p></main>""")

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy():
        return _page("Privacy", """
<p class=sub>Hearth, household memory for Alexa+.</p>
<h2>What it stores</h2>
<p>Hearth stores the household preferences a member states out loud, and for
each one: who said it, when, the situation it was said in, and whether it still
stands. It also stores a record of the actions taken on the household's behalf
and the beliefs that justified each one.</p>
<h2>What it does not store</h2>
<p>No audio. No transcripts of conversation. Nothing a member says that is not a
durable household preference. The extraction step is explicitly instructed to
discard small talk, and anything it does not classify as a durable preference is
never written.</p>
<h2>Where it lives</h2>
<p>Data is held by this deployment and is not sold, shared, or used to train
anything. Every access is recorded in the same audit trail members can read.</p>
<h2>Getting it out, and getting rid of it</h2>
<p>Any member can ask what the house knows and have any belief stood down in
conversation. A belief that is stood down stops applying immediately and stays
in the audit trail so the household can see it was there and when it ended.</p>
<h2>This deployment</h2>
<p>This is a demonstration built for the Amazon Developer Hackathon 2026. Treat
the household on it as public and do not put anything real into it.</p>""")

    @app.get("/terms", response_class=HTMLResponse)
    async def terms():
        return _page("Terms of use", """
<p class=sub>Hearth, household memory for Alexa+.</p>
<h2>What this is</h2>
<p>A demonstration of a self-hosted MCP server, built for the Amazon Developer
Hackathon 2026. It is offered as is, with no warranty and no guarantee of
availability, and it may be changed or taken down at any time.</p>
<h2>What it is not</h2>
<p>It is not a safety system. Do not connect Hearth to anything where acting on
a stale or contested preference could cause harm. Its whole purpose is to make
an assistant's reasoning inspectable, which is a different thing from making it
correct.</p>
<h2>Your content</h2>
<p>You keep whatever you put in. The operator claims no rights over it and will
not use it for anything other than running the service for you.</p>
<h2>Source</h2>
<p>Open source under the MIT licence at
<a href="https://github.com/ubmids/hearth">github.com/ubmids/hearth</a>.</p>""")

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
