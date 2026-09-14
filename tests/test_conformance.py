"""Alexa+ conformance, asserted rather than assumed.

Everything here is a requirement quoted from the Alexa+ MCP toolkit docs. The
three marked TRAP are the ones that differ from what a general-purpose MCP SDK
would do by default, which is why Hearth implements the transport directly.
"""
import os
import re
import secrets
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from hearth.app import create_app
from hearth.oauth import AUTH_CODE_TTL, TOKEN_TTL, AuthServer, s256

ISSUER = "https://hearth.test"
RESOURCE = "https://hearth.test/mcp"


def client():
    app = create_app(issuer=ISSUER, resource=RESOURCE, seed=True)
    return TestClient(app), app


def rpc(c, token, method, params=None, rpc_id=1, sid=None):
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/json, text/event-stream"}
    if sid:
        headers["Mcp-Session-Id"] = sid
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return c.post("/mcp", json=body, headers=headers)


def test_401_has_no_www_authenticate():
    """TRAP. RFC 9728 says advertise the challenge; Alexa+ says do not."""
    c, _ = client()
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401
    assert "www-authenticate" not in {k.lower() for k in r.headers}, dict(r.headers)
    print("PASS 401 without WWW-Authenticate")


def test_both_well_known_documents():
    """TRAP. Two documents are required, not just the RFC 9728 one."""
    c, _ = client()
    prm = c.get("/.well-known/oauth-protected-resource")
    assert prm.status_code == 200
    assert prm.json()["resource"] == RESOURCE
    assert prm.json()["authorization_servers"] == [ISSUER]
    assert prm.json()["bearer_methods_supported"] == ["header"]

    asm = c.get("/.well-known/oauth-authorization-server")
    assert asm.status_code == 200
    meta = asm.json()
    assert "code_challenge_methods_supported" in meta, "must be present, not defaulted"
    assert "S256" in meta["code_challenge_methods_supported"]
    print("PASS both well-known documents, S256 advertised")


def test_bearer_in_query_string_is_refused():
    """TRAP. 'Don't send the Bearer token in the query string.'"""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    r = c.post(f"/mcp?access_token={tok}",
               json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
               headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400, r.status_code
    print("PASS bearer in query string refused")


def test_full_pkce_authorization_code_flow():
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    r = c.get("/authorize", params={
        "client_id": app.state.auth.client_id, "redirect_uri": "https://cb.test/done",
        "response_type": "code", "code_challenge": s256(verifier),
        "code_challenge_method": "S256", "resource": RESOURCE,
        "scope": "household.read", "state": "abc123"},
        follow_redirects=False)
    assert r.status_code == 302, r.status_code
    loc = r.headers["location"]
    assert "state=abc123" in loc
    code = loc.split("code=")[1].split("&")[0]

    t = c.post("/token", data={"grant_type": "authorization_code", "code": code,
                               "code_verifier": verifier,
                               "client_id": app.state.auth.client_id,
                               "redirect_uri": "https://cb.test/done",
                               "resource": RESOURCE})
    assert t.status_code == 200, t.text
    assert t.headers.get("cache-control") == "no-store"
    tok = t.json()["access_token"]
    assert rpc(c, tok, "ping").status_code == 200
    print("PASS full PKCE authorization code flow")


def test_plain_pkce_is_rejected():
    """OAuth 2.1 removed `plain`. Accepting it is a silent downgrade."""
    c, app = client()
    r = c.get("/authorize", params={
        "client_id": app.state.auth.client_id, "redirect_uri": "https://cb.test/done",
        "code_challenge": "whatever", "code_challenge_method": "plain",
        "resource": RESOURCE}, follow_redirects=False)
    assert r.status_code == 400 and r.json()["error"] == "invalid_request"
    print("PASS plain PKCE rejected")


def test_wrong_resource_is_rejected():
    """RFC 8707: a code bound to another resource must not be issued."""
    c, app = client()
    r = c.get("/authorize", params={
        "client_id": app.state.auth.client_id, "redirect_uri": "https://cb.test/done",
        "code_challenge": s256("x" * 50), "code_challenge_method": "S256",
        "resource": "https://someone-elses-server/mcp"}, follow_redirects=False)
    assert r.status_code == 400 and r.json()["error"] == "invalid_target"
    print("PASS audience binding enforced")


def test_initialize_and_session():
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    r = rpc(c, tok, "initialize", {"protocolVersion": "2025-11-25",
                                   "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "1"}})
    assert r.status_code == 200
    assert r.json()["result"]["protocolVersion"] == "2025-11-25"
    assert r.headers.get("mcp-session-id"), "initialize must issue a session id"
    assert r.headers.get("mcp-protocol-version") == "2025-11-25"
    print("PASS initialize, session id, protocol header")


def test_tools_are_listed_with_schemas():
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    tools = rpc(c, tok, "tools/list").json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"remember", "whats_true", "why", "did", "stand_down",
            "end_context", "household"} <= names, names
    for t in tools:
        assert t["inputSchema"]["type"] == "object", t["name"]
        assert t["description"], t["name"]
    print(f"PASS {len(tools)} tools listed with schemas")


def test_notification_gets_202_and_no_body():
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    r = c.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"},
               headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 202, r.status_code
    print("PASS notification accepted with 202")


def test_unknown_method_is_jsonrpc_error():
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    body = rpc(c, tok, "does/not/exist").json()
    assert body["error"]["code"] == -32601
    print("PASS unknown method returns -32601")


def test_read_path_fits_the_500ms_budget():
    """'Your MCP server must meet a round-trip query response latency of less
    than 500 ms.' Measured on the whole HTTP call, not the resolver alone."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    rpc(c, tok, "tools/call", {"name": "remember",
                               "arguments": {"said": "keep it at 19", "speaker": "Dad"}})
    worst = 0.0
    for _ in range(50):
        t0 = time.perf_counter()
        r = rpc(c, tok, "tools/call", {"name": "whats_true",
                                       "arguments": {"domain": "thermostat",
                                                     "slot": "target"}})
        worst = max(worst, (time.perf_counter() - t0) * 1000)
        assert r.status_code == 200
    assert worst < 500, f"worst round trip {worst:.1f}ms"
    print(f"PASS read path worst round trip {worst:.1f}ms of 500ms budget")


def test_two_households_never_see_each_other():
    """Every authenticated subject gets its own home.

    A single shared household was fine while the only client was a test and
    wrong the moment the service was reachable: two people opening the demo
    wrote into the same house, and a judge arriving third saw the wreckage of
    the first two. In a real add-on the subject arrives from account linking,
    and the same leak would be between actual families.
    """
    c, app = client()
    alice = app.state.auth.issue_for_testing(subject="hh-alice")
    bob = app.state.auth.issue_for_testing(subject="hh-bob")

    def say(tok, said, who):
        return c.post("/api/say", json={"said": said, "speaker": who},
                      headers={"Authorization": f"Bearer {tok}"}).json()

    say(alice, "keep it at 19", "Dad")
    say(bob, "make it 26", "Dad")

    def seen(tok):
        r = c.get("/api/state", headers={"Authorization": f"Bearer {tok}"})
        return [x["value"] for x in r.json()["slots"]]

    assert seen(alice) == ["19"], seen(alice)
    assert seen(bob) == ["26"], seen(bob)

    # And through MCP, which is the path Alexa+ actually uses.
    r = rpc(c, bob, "tools/call", {"name": "whats_true",
                                   "arguments": {"domain": "thermostat",
                                                 "slot": "target"}})
    assert r.json()["result"]["content"][0]["text"].startswith("26")
    print("PASS two households never see each other")


def test_authorize_issues_a_distinct_household_each_time():
    c, app = client()
    subjects = set()
    for _ in range(3):
        verifier = secrets.token_urlsafe(48)
        r = c.get("/authorize", params={
            "client_id": app.state.auth.client_id,
            "redirect_uri": "https://cb.test/done", "response_type": "code",
            "code_challenge": s256(verifier), "code_challenge_method": "S256",
            "resource": RESOURCE}, follow_redirects=False)
        code = r.headers["location"].split("code=")[1].split("&")[0]
        t = c.post("/token", data={"grant_type": "authorization_code", "code": code,
                                   "code_verifier": verifier,
                                   "client_id": app.state.auth.client_id,
                                   "redirect_uri": "https://cb.test/done",
                                   "resource": RESOURCE})
        subjects.add(app.state.auth.verify(
            f"Bearer {t.json()['access_token']}").subject)
    assert len(subjects) == 3, subjects
    print("PASS each authorisation opens its own household")


def test_end_to_end_household_story():
    """The demo, driven entirely through MCP tool calls."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()

    def call(name, **args):
        r = rpc(c, tok, "tools/call", {"name": name, "arguments": args})
        return r.json()["result"]["content"][0]["text"]

    print("  ", call("remember", said="keep it at 19 in here", speaker="Dad"))
    print("  ", call("remember", said="make it 23 while Gran is staying", speaker="Ada"))
    truth = call("whats_true", domain="thermostat", slot="target")
    print("   whats_true ->", truth)
    assert truth.startswith("19"), truth          # Dad owns the thermostat

    print("  ", call("did", what="set the thermostat to 19",
                     domain="thermostat", slot="target"))
    why = call("why", domain="thermostat")
    print("   why ->", why)
    assert "Dad" in why

    print("  ", call("end_context", context="Gran's visit"))
    print("   house ->\n     " + call("household").replace("\n", "\n     "))
    print("PASS end to end household story")


# --- the OAuth tests below were found by Mutiny, not by thinking harder -------
# Every security check in oauth.py was mutated one at a time. The ones that
# survived are listed here by what they let through: each of these could have
# been deleted outright, and the suite above stayed green while it happened.


def code_for(c, app, verifier, **over):
    """Drive /authorize and hand back the code it issued.

    Most of the tests below need a real code from a real authorization, and
    inlining that request eleven times hides what each test is actually about.
    """
    params = {"client_id": app.state.auth.client_id,
              "redirect_uri": "https://cb.test/done", "response_type": "code",
              "code_challenge": s256(verifier), "code_challenge_method": "S256",
              "resource": RESOURCE}
    params.update(over)
    r = c.get("/authorize", params=params, follow_redirects=False)
    assert r.status_code == 302, r.text
    return r.headers["location"].split("code=")[1].split("&")[0]


def redeem(c, app, code, verifier, **over):
    """POST /token. A field set to None is left out of the form entirely, which
    is how an attacker skips a check they cannot satisfy."""
    form = {"grant_type": "authorization_code", "code": code,
            "code_verifier": verifier, "client_id": app.state.auth.client_id,
            "redirect_uri": "https://cb.test/done", "resource": RESOURCE}
    form.update(over)
    return c.post("/token", data={k: v for k, v in form.items() if v is not None})


def test_pkce_cannot_be_skipped_or_faked():
    """The most valuable finding here. The code_verifier check could be deleted
    outright and every test stayed green, so nothing was proving PKCE did
    anything at all: a code read out of a redirect, a log or a browser history
    could be exchanged for a token by whoever read it.

    Both halves matter. A wrong verifier must fail, and a missing one must fail
    too, because leaving the parameter out is the first thing anyone tries.
    """
    c, app = client()
    verifier = secrets.token_urlsafe(48)

    code = code_for(c, app, verifier)
    wrong = redeem(c, app, code, secrets.token_urlsafe(48))
    assert wrong.status_code == 400, wrong.text
    assert wrong.json()["error"] == "invalid_grant", wrong.text

    absent = redeem(c, app, code_for(c, app, verifier), None)
    assert absent.status_code == 400, absent.text
    assert absent.json()["error"] == "invalid_request", absent.text

    # And the other way to skip it: name S256 and then send no challenge, so
    # there is nothing for the verifier to be checked against. No code at all
    # may be issued for that, since a code with an empty challenge is a code
    # anybody can redeem.
    naked = c.get("/authorize", params={
        "client_id": app.state.auth.client_id,
        "redirect_uri": "https://cb.test/done", "code_challenge": "",
        "code_challenge_method": "S256", "resource": RESOURCE},
        follow_redirects=False)
    assert naked.status_code == 400, naked.status_code
    assert naked.json()["error"] == "invalid_request", naked.text

    # The failed attempt burned the code, so whoever holds a stolen one gets a
    # single guess at the verifier rather than as many as they care to make.
    assert redeem(c, app, code, verifier).status_code == 400, "the code survived a failed PKCE attempt"
    print("PASS PKCE cannot be skipped or faked, and a failed attempt burns the code")


def test_an_authorization_code_cannot_be_used_twice():
    """A code is a one-time credential, and nothing checked that. If a code
    still works after the real client has redeemed it, PKCE has bought nothing:
    the attacker just replays the whole exchange the client already made."""
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    code = code_for(c, app, verifier)

    assert redeem(c, app, code, verifier).status_code == 200
    again = redeem(c, app, code, verifier)
    assert again.status_code == 400, again.text
    assert again.json()["error"] == "invalid_grant", again.text
    print("PASS an authorization code is refused the second time")


def test_an_expired_authorization_code_is_refused():
    """Sixty seconds is the whole window in which a leaked code is worth
    anything, and the expiry check could be removed without a single test
    noticing. Aged in place rather than by sleeping, because a test that waits
    a minute is a test that gets commented out.
    """
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    code = code_for(c, app, verifier)
    app.state.auth._pending[code].issued_at -= AUTH_CODE_TTL + 5

    r = redeem(c, app, code, verifier)
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_grant", r.text
    print("PASS an expired authorization code is refused")


def test_an_expired_access_token_stops_working():
    """`expires_in` is a promise about when the credential dies. Nothing tested
    that it ever does, so the check could have gone and every token issued by
    this server would have been permanent.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    assert rpc(c, tok, "ping").status_code == 200

    app.state.auth._tokens[tok].issued_at -= TOKEN_TTL + 5
    assert rpc(c, tok, "ping").status_code == 401
    assert app.state.auth.verify(f"Bearer {tok}") is None
    print("PASS an expired access token is refused")


def test_only_the_bearer_scheme_is_accepted():
    """A token is only a bearer token when it arrives as one. With the scheme
    check gone, `Authorization: Basic <token>` was accepted, which means a
    credential meant for one scheme is honoured under another.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    body = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    for header in (f"Basic {tok}", f"Token {tok}", tok, f"Bearer{tok}", "Bearer", ""):
        r = c.post("/mcp", json=body, headers={"Authorization": header})
        assert r.status_code == 401, (header[:12], r.status_code)

    # RFC 7235 makes the scheme itself case-insensitive, so this one must work.
    assert c.post("/mcp", json=body,
                  headers={"Authorization": f"bearer {tok}"}).status_code == 200
    print("PASS only the Bearer scheme is accepted, case-insensitively")


def test_the_redirect_uri_is_checked_even_when_the_client_omits_it():
    """A real hole, not a missing test. The check read
    `if redirect_uri and redirect_uri != pending.redirect_uri`, so anyone
    redeeming a code skipped it by not sending the parameter, and it only ever
    ran for clients that were behaving anyway. It now keys off what the code
    was issued with: a mismatch is refused, and so is silence.
    """
    c, app = client()
    verifier = secrets.token_urlsafe(48)

    elsewhere = redeem(c, app, code_for(c, app, verifier), verifier,
                       redirect_uri="https://attacker.test/cb")
    assert elsewhere.status_code == 400, elsewhere.text
    assert elsewhere.json()["error"] == "invalid_grant", elsewhere.text

    omitted = redeem(c, app, code_for(c, app, verifier), verifier, redirect_uri=None)
    assert omitted.status_code == 400, "omitting redirect_uri skipped the check entirely"
    assert omitted.json()["error"] == "invalid_grant", omitted.text
    print("PASS the redirect_uri is bound to the code and cannot be omitted")


def test_authorize_refuses_a_redirect_uri_it_does_not_know():
    """The other real hole. AuthServer had an allowlist and create_app never
    filled it, so the "not registered" branch was dead code in every deployment
    and /authorize handed a live authorization code to any host that asked.

    Two guards now. An allowlist when the operator sets one, and a shape check
    always, because an unconfigured allowlist must not mean `javascript:` is an
    acceptable place to send a credential.
    """
    c, app = client()
    for bad in ("javascript:alert(1)", "data:text/html,x", "http://evil.test/cb",
                "/console", ""):
        r = c.get("/authorize", params={
            "client_id": app.state.auth.client_id, "redirect_uri": bad,
            "code_challenge": s256("x" * 50), "code_challenge_method": "S256",
            "resource": RESOURCE}, follow_redirects=False)
        assert r.status_code == 400, (bad, r.status_code)
        assert r.json()["error"] == "invalid_request", (bad, r.text)

    registered = AuthServer(issuer=ISSUER, resource=RESOURCE,
                            redirect_uris=["https://cb.test/done"])
    args = {"client_id": registered.client_id, "code_challenge": s256("x" * 50),
            "code_challenge_method": "S256", "resource": RESOURCE}
    url, err = registered.authorize(redirect_uri="https://cb.test/done", **args)
    assert url and not err, err
    url, err = registered.authorize(redirect_uri="https://cb.test/elsewhere", **args)
    assert not url and err["error"] == "invalid_request", (url, err)

    # And a deployment has to be able to register them, which is the half that
    # was missing: create_app passed none, so the allowlist was always empty.
    os.environ["HEARTH_REDIRECT_URIS"] = "https://cb.test/done, https://cb.test/other"
    try:
        c2, app2 = client()
        assert app2.state.auth.redirect_uris == ["https://cb.test/done",
                                                 "https://cb.test/other"]
        for uri, expected in (("https://cb.test/other", 302),
                              ("https://cb.test/unregistered", 400)):
            r = c2.get("/authorize", params={
                "client_id": app2.state.auth.client_id, "redirect_uri": uri,
                "code_challenge": s256("x" * 50), "code_challenge_method": "S256",
                "resource": RESOURCE}, follow_redirects=False)
            assert r.status_code == expected, (uri, r.status_code)
    finally:
        del os.environ["HEARTH_REDIRECT_URIS"]
    print("PASS /authorize refuses redirect URIs it was not configured with")


def test_a_code_cannot_be_redeemed_by_a_different_client():
    """The code is issued to one client id and must only be honoured for that
    one. Nothing exercised the check, so it could have been dropped."""
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    r = redeem(c, app, code_for(c, app, verifier), verifier,
               client_id="some-other-client")
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_client", r.text
    print("PASS a code cannot be redeemed by another client")


def test_an_unknown_client_cannot_start_a_flow():
    """There is one registered client and no Dynamic Client Registration, so an
    unrecognised client id is the end of the conversation."""
    c, app = client()
    r = c.get("/authorize", params={
        "client_id": "not-hearth", "redirect_uri": "https://cb.test/done",
        "code_challenge": s256("x" * 50), "code_challenge_method": "S256",
        "resource": RESOURCE}, follow_redirects=False)
    assert r.status_code == 400, r.status_code
    assert r.json()["error"] == "invalid_client", r.text
    print("PASS an unknown client cannot start a flow")


def test_only_the_authorization_code_grant_is_supported():
    """OAuth 2.1 removed the implicit and password grants, and Hearth issues no
    refresh tokens. Anything but authorization_code is refused by name rather
    than falling through to code handling with an empty code."""
    c, app = client()
    for grant in ("password", "implicit", "refresh_token", "client_credentials", ""):
        r = c.post("/token", data={"grant_type": grant, "code": "x",
                                   "code_verifier": "y",
                                   "client_id": app.state.auth.client_id})
        assert r.status_code == 400, (grant, r.status_code)
        assert r.json()["error"] == "unsupported_grant_type", (grant, r.text)
    print("PASS only the authorization_code grant is supported")


def test_a_code_cannot_be_exchanged_for_another_resource():
    """RFC 8707 at the token endpoint. The authorize side was tested and this
    side was not, so a code bound to this MCP server could have been swapped
    for a token naming somebody else's, which is the exact replay the binding
    exists to stop."""
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    r = redeem(c, app, code_for(c, app, verifier), verifier,
               resource="https://someone-elses-server/mcp")
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_target", r.text

    good = redeem(c, app, code_for(c, app, verifier), verifier)
    tok = app.state.auth.verify("Bearer " + good.json()["access_token"])
    assert tok.resource == RESOURCE, tok.resource
    print("PASS a code cannot be exchanged for a token naming another resource")


def test_codes_and_tokens_are_unguessable():
    """Nothing constrained either one. `secrets.token_urlsafe(0)` gives every
    household the same empty string for both, so every visitor's token would be
    every other visitor's token, and the suite stayed green throughout: the
    flow works perfectly when all of its secrets are identical."""
    c, app = client()
    codes, tokens = set(), set()
    for _ in range(5):
        verifier = secrets.token_urlsafe(48)
        code = code_for(c, app, verifier)
        codes.add(code)
        tokens.add(redeem(c, app, code, verifier).json()["access_token"])

    assert len(codes) == 5, codes
    assert len(tokens) == 5, tokens
    assert min(len(s) for s in codes | tokens) >= 32, "under 192 bits of entropy"
    print("PASS codes and tokens are distinct and long enough to be unguessable")


def test_s256_matches_the_rfc_7636_test_vector():
    """The challenge is computed twice by two different programs, ours and the
    client's, and the two only ever meet as strings. Every other test computes
    the challenge with our own s256, so both sides agree even when both are
    wrong: leaving the base64 padding on cancels out perfectly here and fails
    against every real client. The vector is RFC 7636 appendix B."""
    assert s256("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == \
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    assert "=" not in s256("x" * 50)
    print("PASS S256 matches the RFC 7636 test vector")


def test_the_token_response_carries_what_a_client_needs():
    """RFC 6749 5.1 requires access_token and token_type, and a client that
    caches by expires_in has to be told one. Only access_token was asserted
    anywhere, so the rest of the response could have quietly gone missing.
    The advertised lifetime must also be the one actually enforced."""
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    body = redeem(c, app, code_for(c, app, verifier, scope="household.read"),
                  verifier).json()

    assert body["token_type"] == "Bearer", body
    assert body["scope"] == "household.read", body
    assert body["expires_in"] == TOKEN_TTL, body

    tok = body["access_token"]
    app.state.auth._tokens[tok].issued_at -= body["expires_in"] + 5
    assert rpc(c, tok, "ping").status_code == 401, "it outlived its own expires_in"
    print("PASS the token response is complete and its expires_in is enforced")


def test_authorization_server_metadata_is_complete():
    """RFC 8414. Only code_challenge_methods_supported was ever checked, so the
    rest of the document could have been empty and a client would have had
    nowhere to send anything. Everything a pre-registered client needs is
    discovered here, including the client id, since there is no DCR."""
    c, app = client()
    meta = c.get("/.well-known/oauth-authorization-server").json()

    assert meta["issuer"] == ISSUER, meta
    assert meta["authorization_endpoint"] == ISSUER + "/authorize", meta
    assert meta["token_endpoint"] == ISSUER + "/token", meta
    assert meta["response_types_supported"] == ["code"], meta
    assert meta["grant_types_supported"] == ["authorization_code"], meta
    assert meta["token_endpoint_auth_methods_supported"] == ["none"], meta
    assert meta["client_id_hint"] == app.state.auth.client_id, meta

    # The scopes a client may ask for are the same document to document, or a
    # client that read one of them asks for something the other refuses.
    prm = c.get("/.well-known/oauth-protected-resource").json()
    assert meta["scopes_supported"] == prm["scopes_supported"], meta
    assert meta["scopes_supported"] == ["household.read", "household.write"], meta

    # A deployment that names its own scopes has to get them published, not
    # silently replaced by the default pair.
    narrowed = AuthServer(issuer=ISSUER, resource=RESOURCE,
                          scopes=["household.read"])
    assert narrowed.protected_resource_metadata()["scopes_supported"] == \
        ["household.read"]
    assert narrowed.authorization_server_metadata()["scopes_supported"] == \
        ["household.read"]
    print("PASS authorization server metadata is complete")


def test_the_code_comes_back_as_a_query_parameter():
    """A redirect_uri may already carry a query string, and the code has to be
    appended as another parameter rather than glued onto the last one. Get the
    separator wrong and the client never sees a code, which fails as a silent
    account-linking failure rather than as an error anyone can read."""
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    for uri in ("https://cb.test/done", "https://cb.test/done?tenant=7"):
        r = c.get("/authorize", params={
            "client_id": app.state.auth.client_id,
            "redirect_uri": uri, "response_type": "code",
            "code_challenge": s256(verifier), "code_challenge_method": "S256",
            "resource": RESOURCE, "state": "abc123"}, follow_redirects=False)
        assert r.status_code == 302, r.text

        parsed = urllib.parse.urlparse(r.headers["location"])
        q = urllib.parse.parse_qs(parsed.query)
        assert parsed.path == "/done", (uri, parsed.path)
        assert q["state"] == ["abc123"], (uri, q)
        assert len(q["code"][0]) >= 32, (uri, q)
        if "tenant" in uri:
            assert q["tenant"] == ["7"], q
    print("PASS the code is appended to a redirect_uri that already has a query")


def test_a_trailing_slash_does_not_change_the_audience():
    """Deployment reality: the issuer and resource arrive from environment
    variables and people put trailing slashes in them. The canonical form is
    without, and if that normalisation is dropped anywhere the published
    metadata stops matching what clients send and every authorization fails at
    the last hurdle, for a reason nobody can see."""
    a = AuthServer(issuer=ISSUER + "/", resource=RESOURCE + "/")
    assert a.protected_resource_metadata()["resource"] == RESOURCE
    assert a.authorization_server_metadata()["issuer"] == ISSUER

    c, app = client()
    verifier = secrets.token_urlsafe(48)
    code = code_for(c, app, verifier, resource=RESOURCE + "/")
    assert redeem(c, app, code, verifier, resource=RESOURCE).status_code == 200
    print("PASS a trailing slash on the resource does not change the audience")


# --- MCP dispatch, given the same treatment ----------------------------------
# The transport tests above read the payload inside the response and never the
# envelope around it, and they call tools without ever looking at what comes
# back when one is asked for something it cannot do.


def result_of(c, tok, name, **args):
    """tools/call, returning the whole result object. `isError` is half of what
    a tool call answers and reading only the text throws it away."""
    r = rpc(c, tok, "tools/call", {"name": name, "arguments": args})
    assert r.status_code == 200, r.text
    return r.json()


def said_by(c, tok, name, **args):
    return result_of(c, tok, name, **args)["result"]["content"][0]["text"]


def test_every_response_is_a_json_rpc_envelope():
    """A client matches responses to requests by id, and JSON-RPC 2.0 says both
    fields are on every response. Nothing here ever read them, so Hearth could
    have answered with somebody else's id, or none."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    for rpc_id in (7, "a-string-id"):
        for r in (rpc(c, tok, "ping", rpc_id=rpc_id),
                  rpc(c, tok, "tools/list", rpc_id=rpc_id),
                  rpc(c, tok, "no/such/method", rpc_id=rpc_id),
                  rpc(c, tok, "tools/call", {"name": "household", "arguments": {}},
                      rpc_id=rpc_id)):
            got = r.json()
            assert got["jsonrpc"] == "2.0", got
            assert got["id"] == rpc_id, got
    print("PASS every response carries jsonrpc 2.0 and echoes the request id")


def test_a_message_that_is_not_json_rpc_2_is_refused():
    """-32600. No malformed envelope was ever sent, so the check could have
    gone and Hearth would answer anything shaped roughly like a request."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    for msg in ({"id": 1, "method": "ping"},
                {"jsonrpc": "1.0", "id": 1, "method": "ping"},
                {"jsonrpc": "2", "id": 1, "method": "ping"}):
        got = c.post("/mcp", json=msg,
                     headers={"Authorization": f"Bearer {tok}"}).json()
        assert got["error"]["code"] == -32600, got
        assert "result" not in got, got
    print("PASS a message that is not JSON-RPC 2.0 is refused with -32600")


def test_ping_answers_with_an_empty_result():
    """Asserting a 200 proves nothing about ping: a JSON-RPC error is a 200 as
    well, so with the ping branch gone every ping came back as method-not-found
    and the transport test stayed green through it."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    got = rpc(c, tok, "ping").json()
    assert got.get("result") == {}, got
    assert "error" not in got, got
    print("PASS ping answers with an empty result")


def test_initialize_says_who_the_client_is_talking_to():
    """serverInfo and capabilities are how a client decides what it may call,
    and the instructions are what make the model call whats_true before acting
    rather than after. Only protocolVersion was ever asserted."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    result = rpc(c, tok, "initialize", {"protocolVersion": "2025-11-25",
                                        "capabilities": {},
                                        "clientInfo": {"name": "test",
                                                       "version": "1"}}).json()["result"]
    assert result["serverInfo"]["name"] == "hearth", result
    assert result["serverInfo"]["version"], result
    assert result["capabilities"]["tools"] == {"listChanged": False}, result
    for tool in ("whats_true", "did", "why"):
        assert tool in result["instructions"], result["instructions"]
    print("PASS initialize names the server and how to use it")


def test_every_tool_schema_is_one_a_model_can_actually_fill_in():
    """The schemas are the entire contract with the model. A required argument
    that is not in properties is unfillable, and `required` going missing is
    worse: the model then leaves out the speaker, and a belief attributed to
    nobody is the one thing Hearth must never store."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    tools = {t["name"]: t for t in rpc(c, tok, "tools/list").json()["result"]["tools"]}

    for name, t in tools.items():
        schema = t["inputSchema"]
        assert schema["type"] == "object", name
        props = schema["properties"]
        for prop, spec in props.items():
            assert spec["type"] == "string", (name, prop)
        for req in schema.get("required", []):
            assert req in props, (name, req)
        assert t["title"] and t["description"], name

    assert set(tools["remember"]["inputSchema"]["required"]) == {"said", "speaker"}
    assert set(tools["whats_true"]["inputSchema"]["required"]) == {"domain", "slot"}
    assert set(tools["did"]["inputSchema"]["required"]) == {"what", "domain", "slot"}
    assert set(tools["stand_down"]["inputSchema"]["required"]) == {"belief_id"}
    assert set(tools["end_context"]["inputSchema"]["required"]) == {"context"}
    assert tools["household"]["inputSchema"]["properties"] == {}
    print("PASS every tool schema is fillable and names what it cannot work without")


def test_an_unknown_tool_and_a_missing_argument_are_invalid_params():
    """-32602 for both. A tool name that does not exist and a call missing a
    required argument are the two things a model actually gets wrong, and
    neither had a test, so the dispatcher could have failed the whole request
    instead of answering it."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()

    unknown = rpc(c, tok, "tools/call",
                  {"name": "forget_everything", "arguments": {}}).json()
    assert unknown["error"]["code"] == -32602, unknown
    assert "forget_everything" in unknown["error"]["message"], unknown

    missing = rpc(c, tok, "tools/call",
                  {"name": "remember",
                   "arguments": {"said": "keep it at 19"}}).json()
    assert missing["error"]["code"] == -32602, missing
    assert "remember" in missing["error"]["message"], missing

    # Only what tools/list published is callable. The dispatcher finds handlers
    # by name, so this is worth pinning: an internal helper must not be one.
    private = rpc(c, tok, "tools/call",
                  {"name": "member_id", "arguments": {"name": "Dad"}}).json()
    assert private["error"]["code"] == -32602, private
    print("PASS an unknown tool and a missing argument are both -32602")


def test_a_tool_that_fails_reports_it_as_a_result_not_a_protocol_error():
    """MCP draws this line deliberately. A protocol error means the server
    could not handle the request; a tool error means the tool ran and failed,
    and the model is meant to see the second and try something else. Neither
    branch was exercised, so every success could have been reported as a
    failure and every failure as a success without a test moving.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()

    ok = result_of(c, tok, "remember", said="make it 23 while Gran is staying",
                   speaker="Ada")
    assert ok["result"]["isError"] is False, ok
    assert ok["result"]["content"][0]["type"] == "text", ok
    assert "error" not in ok, ok

    # A model that sends a number where a sentence goes. The request was
    # well formed, so this is the tool failing and not the protocol.
    broken = result_of(c, tok, "remember", said=19, speaker="Ada")
    assert "error" not in broken, broken
    assert broken["result"]["isError"] is True, broken
    assert broken["result"]["content"][0]["text"], broken
    print("PASS a failing tool answers with isError, not with a protocol error")


def test_a_belief_about_one_person_stays_apart_through_the_tools():
    """"We eat at seven" and "the baby eats at five" are both true, and the
    resolver test proves that in Python. Nothing proved it through the tools,
    where the name has to survive extraction, be mapped to a member id, and be
    mapped back when the question is asked about that person."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    said_by(c, tok, "remember", said="we eat at 19:00", speaker="Mum")
    said_by(c, tok, "remember", said="dinner for Ada is at 17:00", speaker="Mum")

    assert said_by(c, tok, "whats_true", domain="meals",
                   slot="dinner").startswith("19:00")
    for who in ("Ada", "ada"):                    # names are said, not typed
        assert said_by(c, tok, "whats_true", domain="meals", slot="dinner",
                       about=who).startswith("17:00"), who
    # Somebody who does not live here is not somebody: the house answer stands.
    assert said_by(c, tok, "whats_true", domain="meals", slot="dinner",
                   about="Gran").startswith("19:00")
    print("PASS a belief about one person stays apart through the tools")


def test_a_sentence_can_close_a_situation():
    """"Gran's gone home" is not a new belief, it is the end of several old
    ones, and closing is the half that gets forgotten. The detector was only
    ever tested on its own, never through `remember`, so the list of open
    contexts handed to it could have been anything, including contexts nobody
    opened and beliefs that have none."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    said_by(c, tok, "remember", said="keep it at 19 in here", speaker="Dad")
    said_by(c, tok, "remember", said="make it 23 while Gran is staying", speaker="Ada")
    assert "Gran's visit" in said_by(c, tok, "household")

    closed = said_by(c, tok, "remember", said="Gran's gone home", speaker="Dad")
    assert "Gran's visit" in closed, closed
    assert "thermostat.target=23" in closed, closed
    house = said_by(c, tok, "household")
    assert "Gran's visit" not in house, house
    assert "19" in house, house              # Dad's standing rule is back by itself
    print("PASS a sentence can close a situation, and only the situation")


def test_a_remembered_belief_can_be_stood_down_by_the_id_it_reported():
    """The reply to `remember` carries the belief id because that is the only
    way the model can retire it later, and nothing checked the id was real. An
    id that does not resolve is worse than no id at all: the model tells the
    household it has stood something down and nothing changed."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    reply = said_by(c, tok, "remember", said="keep it at 19 in here", speaker="Dad")
    found = re.search(r"\bid ([0-9a-f]{6,})", reply)
    assert found, reply
    belief_id = found.group(1)

    assert said_by(c, tok, "whats_true", domain="thermostat",
                   slot="target").startswith("19")
    stood = said_by(c, tok, "stand_down", belief_id=belief_id,
                    reason="Dad changed his mind")
    assert "19" in stood and "Dad changed his mind" in stood, stood
    assert said_by(c, tok, "whats_true", domain="thermostat",
                   slot="target").lower().startswith("nobody has set")

    for gone in (belief_id, "not-an-id"):
        again = said_by(c, tok, "stand_down", belief_id=gone)
        assert "no standing belief" in again.lower(), (gone, again)
    print("PASS a remembered belief can be stood down by the id it reported")


def test_the_tools_say_plainly_when_there_is_nothing_to_say():
    """Four paths an assistant hits constantly, none of them tested: a setting
    nobody has an opinion on, an action nobody has taken, a situation nobody
    opened, and a situation with no name. Each has to come back as something
    sayable rather than an empty string, a crash, or a claim to have done
    something.

    The unnamed one was a real bug. `end_context(None)` matched every belief
    that was never tied to a situation, so a model calling the tool with a null
    context expired the household's entire standing memory and was told it had
    ended a situation.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    said_by(c, tok, "remember", said="keep it at 19 in here", speaker="Dad")

    nothing_set = said_by(c, tok, "whats_true", domain="security", slot="alarm")
    assert "security" in nothing_set and "alarm" in nothing_set, nothing_set
    assert "nobody has set" in nothing_set.lower(), nothing_set

    assert "not done anything" in said_by(c, tok, "why", domain="security").lower()

    unopened = said_by(c, tok, "end_context", context="a heatwave")
    assert "heatwave" in unopened and "nothing" in unopened.lower(), unopened

    unnamed = said_by(c, tok, "end_context", context=None)
    assert "which situation" in unnamed.lower(), unnamed
    assert said_by(c, tok, "whats_true", domain="thermostat",
                   slot="target").startswith("19"), "an unnamed context ended real beliefs"
    print("PASS the tools say plainly when there is nothing to say")

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nall green ({len(fns)} conformance tests)")
