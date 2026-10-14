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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import care as carelib
from . import phrasing, sim
from .care import Care, CareBook
from .extract import detect_context_end, extract
from .household import Household
from .ledger import Ledger
from .mcp import PROTOCOL_VERSION, SUPPORTED_VERSIONS, HearthMCP
from .oauth import AuthServer
from .store import Store
from .trace import Trace

DAY = 86400


def seed_demo_household(h: Household) -> None:
    """A house with a real shape: one member who owns the thermostat, one who
    does not, and a child who owns their own room."""
    if h.members:
        return
    h.add_member("Dad", role="adult", grants=["thermostat"])
    h.add_member("Mum", role="adult", grants=["shopping"])
    h.add_member("Ada", role="child", grants=["bedroom.ada"])


def seed_care_household(h: Household, book: CareBook, now=None) -> None:
    """The household Hearth is for: three people looking after a fourth.

    Rose is 84, lives alone with an Echo Show in the kitchen, and takes
    warfarin, a blood thinner where a second dose in a day is a bleeding risk.
    Ada, her daughter, holds her health care proxy and has the say over her
    medication, diet, appointments and spending. Tom, her son, lives two
    states away and does Thursdays. Grace is the home aide, mornings.

    This is the scene the demo opens on, so it is set in the recent past
    relative to `now`: the rules were stated days ago, and Grace gave this
    morning's warfarin at 9:10. All of it is visible, labelled as seeded, in
    the console. Nothing here is hidden from the record.
    """
    if h.members:
        return
    now = now or time.time()
    mom = h.add_member("Mom", role="owner", grants=["thermostat", "meals"],
                       aliases=["Rose", "Mum", "Grandma", "me", "I"])
    ada = h.add_member("Ada", role="adult",
                       grants=["medication.*", "diet", "appointments", "purchases"])
    tom = h.add_member("Tom", role="adult", grants=["transport"])
    grace = h.add_member("Grace", role="carer")

    def said(who, domain, slot, value, content, days, scope=None, context=None):
        h.assert_belief(who.id, domain, slot, value, content=content,
                        scope=scope, context=context, stated_at=now - days * DAY)

    letter = "Dr. Patel says Mom takes one warfarin a day, at nine in the morning"
    said(ada, "medication.warfarin", "per_day", "1", letter, 12, scope=mom.id)
    said(ada, "medication.warfarin", "time", "09:00", letter, 12, scope=mom.id)
    said(ada, "purchases", "limit", "50",
         "Up to fifty dollars without asking me", 12)
    said(ada, "diet", "coffee_cutoff", "15:00",
         "No coffee for Mom after three, it's keeping her up at night", 12,
         scope=mom.id)
    said(tom, "rota", "thursday", "Tom", "I'll take Mom to anything on a Thursday", 9)
    said(grace, "rota", "tuesday", "Grace", "I can do Tuesdays", 9)
    said(ada, "diet", "alcohol", "none",
         "No wine for Mom while she's on the antibiotics", 5,
         scope=mom.id, context="the antibiotics")
    # Tom last spoke to the house on a Sunday-evening call, two days back.
    evening = carelib.local(now - 2 * DAY).replace(hour=19, minute=30, second=0,
                                                   microsecond=0).timestamp()
    said(tom, "diet", "coffee_cutoff", "18:00",
         "Mom can have coffee till six, it's fine", (now - evening) / DAY,
         scope=mom.id)

    # This morning's dose. At 9:10 if that has passed, else half an hour ago,
    # so the scene reads true whenever it is filmed.
    today = carelib.local(now).replace(hour=9, minute=10, second=0, microsecond=0)
    given = today.timestamp() if today.timestamp() < now - 1800 else now - 1800
    book.doses.append({"id": "dose_seed_morning", "medication": "warfarin",
                       "person": mom.id, "given_by": grace.id, "at": given})

    # Cardiology next Tuesday at two, Grace escorting, ride booked.
    d = carelib.local(now)
    ahead = (1 - d.weekday()) % 7 or 7
    tue = (d.replace(hour=14, minute=0, second=0, microsecond=0)
           + carelib.timedelta(days=ahead)).timestamp()
    book.rides.append({"id": "ride_seed_tue", "appointment": "appt_seed_cardio",
                       "pickup": tue - 45 * 60, "for": mom.id, "with": "Grace",
                       "status": "booked", "provider": carelib.RIDES})
    book.appointments.append({"id": "appt_seed_cardio", "what": "cardiology",
                              "person": mom.id, "at": tue,
                              "where": "St. Mary's Heart Center",
                              "status": "booked", "escort": "Grace",
                              "ride": "ride_seed_tue"})
    book.post("Mom slept well and ate all her lunch.", to=["Ada", "Tom"],
              by="Grace", now=now - 1 * DAY)
    book.save()


SEEDS = {"family", "care"}


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
    # `seed` is the household a new subject starts in: "care" (the product's
    # household), "family" (the original thermostat house, which most of the
    # conformance suite is written against), True for "family", or False.
    kind = "family" if seed is True else (seed or None)
    if kind and kind not in SEEDS:
        raise ValueError(f"unknown household seed {seed!r}")
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
            book = CareBook(store=st)
            if kind == "family":
                seed_demo_household(h)
            elif kind == "care":
                seed_care_household(h, book)
            led = Ledger(h, store=st)
            homes[subject] = (h, led, HearthMCP(
                h, led, extractor=extract, end_detector=detect_context_end,
                trace=Trace(store=st), care=Care(h, led, book)))
        return homes[subject]

    # The default household backs anything that arrives without a subject, and
    # is what `app.state.household` exposes for tests and local tooling.
    household, ledger, server = home_for("default")

    app = FastAPI(title="Hearth", version="0.1.0")
    app.state.household = household
    app.state.ledger = ledger
    app.state.mcp = server
    app.state.auth = auth
    # Reaching a specific household, for tests and local tooling that need one
    # other than the default. Exposed deliberately rather than by poking at the
    # closure: the demo needs to move a belief back in time to make a narration
    # honest, and doing that through a named accessor is clearer than a script
    # that knows the internals.
    app.state.home_for = home_for

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

    # --- transport security (MCP 2025-11-25, basic/transports) -------------
    # "Servers MUST validate the Origin header on all incoming connections to
    # prevent DNS rebinding attacks. If the Origin header is present and
    # invalid, servers MUST respond with HTTP 403 Forbidden." Absent is fine:
    # a server-side client (Alexa, a Lambda, the SDK) sends none. Present, it
    # must be this service's own origin, a loopback origin, or one listed in
    # HEARTH_ALLOWED_ORIGINS. Matching Origin against the Host header would be
    # no defence at all, since in a rebinding attack both say evil.example.
    issuer_origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(issuer))
    allowed_origins = {issuer_origin.lower()} | {
        o.strip().rstrip("/").lower()
        for o in os.getenv("HEARTH_ALLOWED_ORIGINS", "").split(",") if o.strip()}
    # Host is checked too, because a page on a rebinding domain reaching a
    # Hearth on someone's laptop arrives with Host: evil.example. A hosted
    # Hearth only ever sees its own name, since the platform routes by it.
    # "testserver" is the Starlette test client's name and resolves nowhere.
    allowed_hosts = {urllib.parse.urlsplit(issuer).hostname or "", "testserver"} | {
        h.strip().lower() for h in os.getenv("HEARTH_ALLOWED_HOSTS", "").split(",")
        if h.strip()}
    loopback = {"localhost", "127.0.0.1", "::1"}

    def _origin_ok(origin: str | None) -> bool:
        if origin is None:
            return True
        o = origin.strip().rstrip("/").lower()
        if o in allowed_origins or "*" in allowed_origins:
            return True
        host = urllib.parse.urlsplit(o).hostname or ""
        return host in loopback

    def _host_ok(host_header: str | None) -> bool:
        if "*" in allowed_hosts or not host_header:
            return True
        host = urllib.parse.urlsplit("//" + host_header.strip()).hostname or ""
        return host in loopback or host in allowed_hosts

    def _forbidden(why: str):
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32600, "message": f"Forbidden: {why}"}},
                            status_code=403)

    def _transport_guard(request: Request):
        """403 for a foreign Origin or Host, 400 for a protocol version this
        server does not speak. None when the request may proceed."""
        if not _origin_ok(request.headers.get("origin")):
            return _forbidden("Origin not allowed")
        if not _host_ok(request.headers.get("host")):
            return _forbidden("Host not allowed")
        # "If the server receives a request with an invalid or unsupported
        # MCP-Protocol-Version, it MUST respond with 400 Bad Request." Absent
        # is allowed: the spec says assume 2025-03-26 for backwards
        # compatibility, and initialize itself never carries it.
        pv = request.headers.get("mcp-protocol-version")
        if pv is not None and pv not in SUPPORTED_VERSIONS:
            return JSONResponse(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32600,
                           "message": f"Unsupported MCP-Protocol-Version: {pv}",
                           "data": {"supported": list(SUPPORTED_VERSIONS)}}},
                status_code=400, headers={"MCP-Protocol-Version": PROTOCOL_VERSION})
        return None

    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        refused = _transport_guard(request)
        if refused is not None:
            return refused
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

        def timed(content, status=200):
            headers["Server-Timing"] = (
                f'app;dur={(time.perf_counter() - t0) * 1000:.3f};desc="hearth"')
            return JSONResponse(content, status_code=status, headers=headers)

        if isinstance(payload, list):
            # JSON-RPC batching was removed from MCP in 2025-06-18, and a
            # 2025-11-25 body is "a single JSON-RPC request, notification, or
            # response". This used to answer batches, which a conformant
            # client never sends and a confused one should hear about.
            return JSONResponse({"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32600,
                                           "message": "Invalid Request: JSON-RPC "
                                                      "batches are not supported "
                                                      "in MCP 2025-11-25"}},
                                status_code=400, headers=headers)

        if not isinstance(payload, dict):
            # `"hello"`, `42` and `null` are all valid JSON and none of them is
            # a JSON-RPC request. This used to fall straight through to
            # `payload.get` and raise, so the endpoint answered a malformed body
            # with a 500 and a stack trace rather than the error the spec names
            # for exactly this case. It sits behind the bearer check, so it was
            # never reachable anonymously, but a 500 from the MCP endpoint is
            # indistinguishable from the server being broken and a reviewer with
            # a token is exactly who would have found it.
            return JSONResponse({"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32600,
                                           "message": "Invalid Request"}},
                                status_code=400, headers=headers)

        if payload.get("method") == "initialize":
            sid = server.new_session()
            headers["Mcp-Session-Id"] = sid
        elif not sid:
            # Hearth issues a session on initialize, so it is a server that
            # requires one: "Servers that require a session ID SHOULD respond
            # to requests without an Mcp-Session-Id header (other than
            # initialization) with HTTP 400 Bad Request."
            return JSONResponse({"jsonrpc": "2.0", "id": payload.get("id"),
                                 "error": {"code": -32600,
                                           "message": "Mcp-Session-Id required: "
                                                      "send initialize first"}},
                                status_code=400, headers=headers)
        elif sid not in server.sessions:
            return JSONResponse({"error": "no such session"}, status_code=404,
                                headers=headers)

        result = server.handle(payload, session=sid)
        if result is None:
            return timed(None, 202)          # notifications are accepted with no body
        return timed(result)

    @app.delete("/mcp")
    async def mcp_end_session(request: Request):
        # Streamable HTTP: a client leaving says so with DELETE and its session
        # id. The official SDK client does this on close. Ending a session
        # forgets the transport session only; the household's memory, and the
        # record of what was called in it, stay.
        refused = _transport_guard(request)
        if refused is not None:
            return refused
        caller = auth.verify(request.headers.get("authorization"))
        if caller is None:
            return _unauthorized()
        _, _, server = home_for(caller.subject)
        sid = request.headers.get("mcp-session-id")
        headers = {"MCP-Protocol-Version": PROTOCOL_VERSION}
        if not sid:
            return JSONResponse({"error": "Mcp-Session-Id required"},
                                status_code=400, headers=headers)
        if server.sessions.pop(sid, None) is None:
            return JSONResponse({"error": "no such session"}, status_code=404,
                                headers=headers)
        return Response(status_code=204, headers=headers)

    # --- console surface ---------------------------------------------------
    # The console is an operator view, not a second way in. It speaks to the
    # same bearer-protected API, and the only concession to convenience is that
    # a request arriving from the loopback interface can mint itself a token.
    # A deployed Hearth hands out nothing.
    def _is_local(request: Request) -> bool:
        host = (request.client.host if request.client else "") or ""
        return host in ("127.0.0.1", "::1", "localhost", "testclient")

    @app.get("/api/console-token")
    async def console_token(request: Request):
        if not _is_local(request):
            return JSONResponse({"error": "console tokens are loopback only"},
                                status_code=403)
        return {"access_token": auth.issue_for_testing(subject="console"),
                "token_type": "Bearer"}

    def _state(household, ledger):
        """Everything the console draws, resolved server-side.

        Resolution belongs here, not in the page: the console must show exactly
        what Alexa+ would be told, and a second implementation in JavaScript
        would drift from the real one and quietly lie on camera.

        Both arguments are required. They used to default to the "default"
        household, and every caller passed its own, so the fallback was
        unreachable: code that can only ever be wrong if it starts running.
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
                r = household.resolve(b.domain, b.slot, for_member=who,
                                      name_domain=phrasing.domain_label)
                if r.winner is None:
                    continue
                about = household.name_of(who) if who else None
                slots.append({
                    "domain": b.domain, "slot": b.slot,
                    "about": about,
                    # The household-facing half of the row: title, reading and
                    # statement. Computed here rather than in the page for the
                    # same reason the resolution is, one rendering shared by
                    # whatever draws it.
                    **phrasing.describe(b.domain, b.slot, r.winner.value, about),
                    "value": r.winner.value, "basis": r.basis,
                    "verdict": phrasing.verdict(
                        r.basis, winner=household.name_of(r.winner.holder),
                        about=about, domain=b.domain, slot=b.slot),
                    "sentence": r.explain(household.name_of,
                                          phrasing.value_spoken),
                    "winner": {"id": r.winner.id,
                               "holder": household.name_of(r.winner.holder),
                               "context": r.winner.context,
                               "stated_at": r.winner.stated_at},
                    "losers": [{"id": lb.id, "value": lb.value,
                                "reading": phrasing.reading(lb.domain, lb.slot,
                                                            lb.value),
                                "holder": household.name_of(lb.holder),
                                "reason": why} for lb, why in r.losers],
                })
        contexts = {}
        for b in live:
            if b.context:
                # `riding` is the machine's list and `holds` the household's.
                # Both, because the first is what an operator greps for and the
                # second is what anyone else can actually read.
                riding, holds = contexts.setdefault(b.context, ([], []))
                riding.append(f"{b.domain}.{b.slot}={b.value}")
                holds.append(phrasing.statement(
                    b.domain, b.slot, b.value,
                    household.name_of(b.scope) if b.scope else None))
        return {
            "members": [{"id": m.id, "name": m.name, "role": m.role,
                         "grants": m.grants,
                         "authority": phrasing.authority_line(m.grants)}
                        for m in household.members.values()],
            "slots": slots,
            "contexts": [{"name": k, "riding": v[0], "holds": v[1]}
                         for k, v in contexts.items()],
            "beliefs": [{**b.to_dict(), "holder_name": household.name_of(b.holder),
                         "live": b.is_live(),
                         "standing": phrasing.standing(b.is_live(), b.status,
                                                       b.ended_reason),
                         "said": phrasing.said(
                             b.domain, b.slot, b.value, b.content,
                             household.name_of(b.scope) if b.scope else None)}
                        for b in household.beliefs],
            # The spoken explanation is computed here for the same reason the
            # resolution is: the console must show the exact sentence the
            # assistant would say, not a second rendering of it that can drift.
            "actions": [{**a.to_dict(), "why": ledger.why(action_id=a.id)}
                        for a in reversed(ledger.actions)][:25],
        }

    def _full_state(household, ledger, server):
        """The console's state plus the two things it now has to show: the
        server's own record of calls, and the care books."""
        out = _state(household, ledger)
        audit = server.trace.audit()
        ok, bad = audit["intact"], audit["broken_at"]
        book = server.care.book
        out["record"] = {"intact": ok, "broken_at": bad, "reason": audit["reason"],
                         "checkpoint": audit["checkpoint"],
                         "count": len(server.trace.entries),
                         "head": server.trace.head()[:12],
                         "entries": [e.to_dict() for e in
                                     reversed(server.trace.entries[-40:])]}
        name = household.name_of
        out["care"] = {
            "doses": [{**d, "who": name(d["person"]),
                       "by": (name(d["given_by"]) if d["given_by"] in household.members
                              else d["given_by"]),
                       "when": carelib.when_said(d["at"])}
                      for d in reversed(book.doses[-10:])],
            "appointments": [{**a, "who": name(a["person"]),
                              "when": carelib.when_said(a["at"])}
                             for a in book.appointments if a["status"] == "booked"],
            "rides": [{**r, "when": carelib.when_said(r["pickup"])}
                      for r in book.rides[-6:]],
            "board": [{**p, "when": carelib.when_said(p["at"])}
                      for p in reversed(book.board[-8:])],
            "checkouts": list(reversed(book.checkouts[-5:])),
        }
        return out

    @app.get("/api/state")
    async def api_state(request: Request):
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return _full_state(*home_for(tok.subject))

    @app.post("/api/say")
    async def api_say(request: Request):
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        said, speaker = body.get("said", ""), body.get("speaker", "")
        h, led, srv = home_for(tok.subject)
        # What the tool did is read off the house rather than parsed back out of
        # its reply, so the console can say it in the household's words without
        # a second copy of the write path. `reply` is still the exact text the
        # tool returned, because that is what Alexa+ would hear.
        before = {b.id for b in h.beliefs}
        was_live = {b.id for b in h.beliefs if b.is_live()}
        res = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "remember",
                                     "arguments": {"said": said, "speaker": speaker}}})
        raw = res["result"]["content"][0]["text"]
        added = [b for b in h.beliefs if b.id not in before]
        ended = [b for b in h.beliefs if b.id in was_live and not b.is_live()]

        def phrase(b):
            return phrasing.statement(b.domain, b.slot, b.value,
                                      h.name_of(b.scope) if b.scope else None)

        if added:
            line = phrasing.confirm([phrase(b) for b in added], speaker=speaker,
                                    context=added[0].context)
        elif ended:
            line = phrasing.closed(ended[0].ended_reason.removeprefix(
                "context ended: "), [phrase(b) for b in ended])
        else:
            # Nothing changed, so the tool's own sentence is already the whole
            # answer and any rewording here would only be a worse copy of it.
            line = raw
        return {"reply": raw, "line": line, "state": _state(h, led)}

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
        # Only a name that belongs to somebody who lives here gets to colour the
        # sentence. A stranger resolves household-wide, so saying "Gran's
        # thermostat" would describe an answer nobody was given.
        named = h.name_of(mid) if mid else None
        r = h.resolve(domain, slot, for_member=mid,
                      name_domain=phrasing.domain_label)
        if r.winner is None:
            return {"reply": f"Nobody has set {phrasing.subject(domain, slot, named)}.",
                    "state": _state(h, led)}
        # The raw value, not the spoken one: a record of what was done has to say
        # what the device was actually given. "Dinner is at five" is the right
        # thing to read on a card and the wrong thing to find in a log.
        a = led.record(f"set {phrasing.subject(domain, slot, named)} "
                       f"to {r.winner.value}", domain, resolution=r)
        # The console acting is still an action, so it goes on the record.
        home_for(tok.subject)[2].trace.append(
            tool="console.act", args={"domain": domain, "slot": slot,
                                      "about": about},
            outcome="ok", summary=a.what, reads=[r.winner.id], action=a.id)
        return {"reply": f"Set {phrasing.subject(domain, slot, named)} "
                         f"to {r.winner.value}.",
                "why": led.why(action_id=a.id), "state": _state(h, led)}

    @app.post("/api/retire")
    async def api_retire(request: Request):
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        h, led, _ = home_for(tok.subject)
        b = h.retire(body.get("belief_id"), reason="stood down in the console")
        return {"reply": ((f"Stood down {phrasing.possessive(h.name_of(b.holder))} "
                           f"{b.value} for "
                           f"{phrasing.subject(b.domain, b.slot, h.name_of(b.scope) if b.scope else None)}.")
                          if b else "No standing belief with that id."),
                "state": _state(h, led)}

    # --- checkout: the pharmacy refill, paid the Alexa+ way -----------------
    # Alexa+ owns payment. An add-on exposes checkout sessions shaped by the
    # Universal Commerce Protocol, Alexa collects the confirmation and the card,
    # and then completes the session here. The `reorder` tool only opens one.
    # This is a sandbox merchant: nothing is charged and nothing ships.
    @app.get("/.well-known/ucp")
    async def ucp_profile():
        return {"ucp": {"version": carelib.UCP_VERSION,
                        "services": {"dev.ucp.shopping": {
                            "version": carelib.UCP_VERSION,
                            "rest": {"endpoint": issuer}}},
                        "capabilities": {"dev.ucp.shopping.checkout": [
                            {"version": carelib.UCP_VERSION}]}},
                "payment_handlers": {"com.amazon.payments.network_token": [
                    {"id": "amazon_pay_network_token",
                     "version": carelib.UCP_VERSION}]},
                "merchant": carelib.PHARMACY, "sandbox": True}

    def _caller_home(request: Request):
        tok = auth.verify(request.headers.get("authorization"))
        return home_for(tok.subject) if tok else None

    def _ucp(request: Request, body, status=200):
        # Checkout state must never be cached, and the Request-Id comes back
        # so a support escalation can find the call in both sets of logs.
        h = {"Cache-Control": "no-store"}
        if request.headers.get("request-id"):
            h["Request-Id"] = request.headers["request-id"]
        return JSONResponse(body, status_code=status, headers=h)

    def _receipt(srv, op, sess, outcome="ok", request=None):
        # Checkout calls are not MCP tool calls, and they are the calls that
        # move money, so they go on the same record as everything else.
        srv.trace.append(tool=f"checkout.{op}",
                         args={"session": sess["id"] if sess else None,
                               "request_id": request.headers.get("request-id")
                               if request else None},
                         outcome=outcome,
                         summary=(f"{sess['status']} {sess['id']}" if sess else op),
                         writes=[sess["id"]] if sess else [])

    @app.post("/checkout-sessions")
    async def checkout_create(request: Request):
        home = _caller_home(request)
        if home is None:
            return _unauthorized()
        srv = home[2]
        body = await request.json()
        buyer = body.get("buyer") or {}
        try:
            sess = srv.care.create_session(
                body.get("line_items"),
                buyer=buyer.get("first_name") if isinstance(buyer, dict) else buyer,
                quote_id=(body.get("context") or {}).get("hearth_quote"))
        except (ValueError, TypeError) as e:
            return _ucp(request, {"error": "invalid_request", "message": str(e)}, 400)
        _receipt(srv, "create", sess, request=request)
        return _ucp(request, sess, 201)

    @app.get("/checkout-sessions/{sid}")
    async def checkout_get(sid: str, request: Request):
        home = _caller_home(request)
        if home is None:
            return _unauthorized()
        sess = next((c for c in home[2].care.book.checkouts if c["id"] == sid), None)
        return _ucp(request, sess) if sess else _ucp(request, {"error": "not_found"}, 404)

    @app.put("/checkout-sessions/{sid}")
    async def checkout_update(sid: str, request: Request):
        """Full-resource replace. Hearth's sessions have nothing a buyer can
        change but the quantity, so an update is a fresh pricing of the new
        line items under the same id, with the family's rules applied again."""
        home = _caller_home(request)
        if home is None:
            return _unauthorized()
        srv = home[2]
        book = srv.care.book
        old = next((c for c in book.checkouts if c["id"] == sid), None)
        if old is None:
            return _ucp(request, {"error": "not_found"}, 404)
        if old["status"] == "completed":
            return _ucp(request, old)
        body = await request.json()
        fresh = srv.care.create_session(body.get("line_items") or old["line_items"],
                                        buyer=old["buyer"], quote_id=old.get("quote"))
        book.checkouts.remove(fresh)
        fresh["id"], fresh["created_at"] = old["id"], old["created_at"]
        book.checkouts[book.checkouts.index(old)] = fresh
        book.save()
        _receipt(srv, "update", fresh, request=request)
        return _ucp(request, fresh)

    @app.post("/checkout-sessions/{sid}/complete")
    async def checkout_complete(sid: str, request: Request):
        home = _caller_home(request)
        if home is None:
            return _unauthorized()
        srv = home[2]
        sess, err = srv.care.complete(sid, request.headers.get("idempotency-key"))
        if err == "not_found":
            return _ucp(request, {"error": "not_found"}, 404)
        _receipt(srv, "complete", sess, "refused" if err else "ok", request)
        # A business failure is still a 200 with the reason in messages[].
        return _ucp(request, sess)

    @app.post("/checkout-sessions/{sid}/cancel")
    async def checkout_cancel(sid: str, request: Request):
        home = _caller_home(request)
        if home is None:
            return _unauthorized()
        srv = home[2]
        sess, err = srv.care.cancel(sid)
        if err == "not_found":
            return _ucp(request, {"error": "not_found"}, 404)
        _receipt(srv, "cancel", sess, "refused" if err else "ok", request)
        return _ucp(request, sess)

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

    # --- the simulated Alexa+ client ------------------------------------
    # Labelled as a simulation on every surface. It reaches Hearth only
    # through /mcp and /checkout-sessions, like any client; these three
    # endpoints are the parts of Alexa it has to stand in for.
    @app.get("/")
    async def root():
        # A judge opening the bare URL lands on the product, not a 404.
        return RedirectResponse("/alexa", status_code=307)

    @app.get("/alexa", response_class=HTMLResponse)
    async def alexa_sim():
        path = os.path.join(os.path.dirname(__file__), "web", "alexa.html")
        with open(path) as f:
            return HTMLResponse(f.read())

    @app.get("/sim/config")
    async def sim_config(request: Request):
        if auth.verify(request.headers.get("authorization")) is None:
            return _unauthorized()
        return {"tts": sim.tts_provider(),
                "planner": sim.planner_label(), "model": sim.configured(),
                "simulated": True}

    @app.post("/sim/plan")
    async def sim_plan(request: Request):
        if auth.verify(request.headers.get("authorization")) is None:
            return _unauthorized()
        body = await request.json()
        from .mcp import TOOLS
        return sim.plan(str(body.get("said", "")), str(body.get("speaker", "")),
                        TOOLS, body.get("context") or {})

    @app.post("/sim/tts")
    async def sim_tts(request: Request):
        # Behind the bearer like everything else: a configured Polly key is
        # somebody's money, and an open endpoint would spend it for anyone.
        if auth.verify(request.headers.get("authorization")) is None:
            return _unauthorized()
        body = await request.json()
        audio, mime, provider = sim.speak(str(body.get("text", "")),
                                          str(body.get("who", "alexa")))
        if audio is None:
            return Response(status_code=204, headers={"X-TTS-Provider": provider})
        return Response(audio, media_type=mime, headers={"X-TTS-Provider": provider})

    @app.get("/console", response_class=HTMLResponse)
    async def console():
        path = os.path.join(os.path.dirname(__file__), "web", "console.html")
        with open(path) as f:
            return HTMLResponse(f.read())

    # --- the record's anchor, published -----------------------------------
    # The public key the record's checkpoints are signed with, so anyone can
    # check a checkpoint they were given, and the newest checkpoint for the
    # caller's household, so a client or a family member can keep a copy off
    # this server. A copy kept elsewhere is what catches a rewrite.
    @app.get("/.well-known/hearth-record-key")
    async def record_key():
        return {"alg": "Ed25519", "public_key": server.trace.witness.public_key,
                "message": "hearth-record:{seq}:{hash}"}

    @app.get("/record/checkpoint")
    async def record_checkpoint(request: Request):
        tok = auth.verify(request.headers.get("authorization"))
        if tok is None:
            return _unauthorized()
        srv = home_for(tok.subject)[2]
        audit = srv.trace.audit()
        return {"count": audit["count"], "intact": audit["intact"],
                "checkpoint": srv.trace.witness.latest(),
                "public_key": srv.trace.witness.public_key}

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "protocol": PROTOCOL_VERSION,
                "members": len(household.members),
                "beliefs": sum(1 for b in household.beliefs if b.is_live()),
                "keepalive": bool(app.state.keepalive_task)}

    app.state.keepalive_task = None

    @app.on_event("startup")
    async def _warm_the_planner():
        # A local model on CPU takes ~15 s on its first prompt and ~0 on the
        # shared prefix after that, so warm it before the first scene, off the
        # event loop. Opt in with HEARTH_SIM_LLM_WARMUP=1.
        if os.getenv("HEARTH_SIM_LLM_WARMUP", "0") in ("1", "true", "yes") \
                and sim.configured():
            import threading
            from .mcp import TOOLS
            threading.Thread(target=sim.warm_up, args=(TOOLS,), daemon=True).start()

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


app = create_app(seed=os.getenv("HEARTH_HOUSEHOLD", "care"))
