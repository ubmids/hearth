"""Alexa+ conformance, asserted rather than assumed.

Everything here is a requirement quoted from the Alexa+ MCP toolkit docs. The
three marked TRAP are the ones that differ from what a general-purpose MCP SDK
would do by default, which is why Hearth implements the transport directly.
"""
import os
import re
import secrets
import shutil
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from hearth import app as app_module
from hearth.app import create_app
from hearth.mcp import PROTOCOL_VERSION
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
    assert r.json()["error"] == "unauthorized", r.text
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
    # A client has to be able to tell this apart from a bad request body, so
    # the code matters as much as the status.
    assert r.json()["error"] == "invalid_request", r.text
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
    assert "26 degrees" in r.json()["result"]["content"][0]["text"]
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
    assert "19 degrees" in truth, truth           # Dad owns the thermostat

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
            # Strings, and whole numbers for counts, which a model fills in
            # as reliably and which the tool would otherwise have to parse.
            assert spec["type"] in ("string", "integer"), (name, prop)
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

    # The tool answers in a sentence rather than a raw value, because the
    # result is prose a model reads before it says something out loud. What
    # matters here is which time it names, not how it is spelled.
    house_answer = said_by(c, tok, "whats_true", domain="meals", slot="dinner")
    assert "seven" in house_answer and "five" not in house_answer, house_answer
    for who in ("Ada", "ada"):                    # names are said, not typed
        ada = said_by(c, tok, "whats_true", domain="meals", slot="dinner",
                      about=who)
        assert "five" in ada and "Ada" in ada, (who, ada)
    # Somebody who does not live here is not somebody: the house answer stands.
    gran = said_by(c, tok, "whats_true", domain="meals", slot="dinner",
                   about="Gran")
    assert "seven" in gran, gran
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
    # What stopped applying is named in words now, not as a field and a value.
    # The tool result is prose a model reads before it says something out loud,
    # and "thermostat.target=23" is not a thing an assistant says.
    assert "23 degrees" in closed and "no longer applies" in closed, closed
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
    # The reference is in brackets at the end rather than woven into the
    # sentence: the tool result is prose a model reads before speaking, and a
    # hex string inside the sentence is a hex string it may read out.
    found = re.search(r"\[([0-9a-f]{6,})\]", reply)
    assert found, reply
    belief_id = found.group(1)

    assert "19 degrees" in said_by(c, tok, "whats_true", domain="thermostat",
                                   slot="target")
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
    assert "19 degrees" in said_by(c, tok, "whats_true", domain="thermostat",
                                   slot="target"), \
        "an unnamed context ended real beliefs"
    print("PASS the tools say plainly when there is nothing to say")



# --- the HTTP surface, given the same treatment ------------------------------
# app.py had never been mutation tested. Everything below is a survivor: a
# change to the running service that this suite would have waved through, on
# endpoints that are either security boundaries, the thing a judge opens, or
# the thing the add-on listing points at.


def console(c, tok, method, path, **body):
    """The console API always speaks bearer, and always answers with state."""
    head = {"Authorization": f"Bearer {tok}"}
    if method == "GET":
        return c.get(path, headers=head)
    return c.post(path, json=body, headers=head)


def test_the_seeded_household_has_the_shape_the_demo_needs():
    """The demo is the submission. A judge opening the console sees this house
    before anyone says a word, and every sentence in the walkthrough depends on
    its shape: one adult who owns the thermostat, one who does not, and a child
    who owns their own room. Nothing checked any of it, so the roles and the
    grants could have gone empty and the demo would have quietly become a
    first-past-the-post memory store like every other entry.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    by_name = {m.name: m for m in app.state.household.members.values()}
    assert set(by_name) == {"Dad", "Mum", "Ada"}, sorted(by_name)
    assert by_name["Dad"].role == "adult" and by_name["Dad"].grants == ["thermostat"]
    assert by_name["Mum"].role == "adult" and by_name["Mum"].grants == ["shopping"]
    assert by_name["Ada"].role == "child" and by_name["Ada"].grants == ["bedroom.ada"]

    # And the grant has to still decide the contest, which is the only reason
    # any of it is there. Mum speaks last; Dad owns the thermostat.
    said_by(c, tok, "remember", said="keep it at 19 in here", speaker="Dad")
    said_by(c, tok, "remember", said="make it 24", speaker="Mum")
    truth = said_by(c, tok, "whats_true", domain="thermostat", slot="target")
    assert "19 degrees" in truth, truth
    print("PASS the seeded household is the one the demo walks through")


def test_the_protected_resource_document_is_served_at_both_paths():
    """RFC 9728 clients derive the metadata URL from the resource by inserting
    the well-known segment before the path, so a resource of /mcp is looked up
    at /.well-known/oauth-protected-resource/mcp. Hearth serves both spellings
    and only the bare one was ever fetched, so the suffixed route could have
    been deleted and the discovery Alexa+ performs would have 404'd.
    """
    c, _ = client()
    bare = c.get("/.well-known/oauth-protected-resource")
    suffixed = c.get("/.well-known/oauth-protected-resource/mcp")
    assert suffixed.status_code == 200, suffixed.status_code
    assert suffixed.json() == bare.json(), suffixed.json()
    assert suffixed.json()["resource"] == RESOURCE
    print("PASS the protected resource document is served at both paths")


def test_a_body_that_is_not_a_json_rpc_request_is_refused_not_crashed():
    """A REAL BUG, found here. `"hello"`, `42` and `null` are all valid JSON and
    none of them is a request object. The handler went straight to
    `payload.get` and raised, so the endpoint answered a malformed body with a
    500 rather than the Invalid Request the spec names for exactly this case.
    A 500 from the MCP endpoint is the worst thing a conformance reviewer can
    find, because it is indistinguishable from the server being broken.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    head = {"Authorization": f"Bearer {tok}"}

    broken = c.post("/mcp", content="{not json at all", headers=head)
    assert broken.status_code == 400, broken.status_code
    assert broken.json()["jsonrpc"] == "2.0", broken.json()
    assert broken.json()["id"] is None, broken.json()
    assert broken.json()["error"]["code"] == -32700, broken.json()
    assert "message" in broken.json()["error"], broken.json()

    for body in ('"hello"', "42", "null", "true"):
        r = c.post("/mcp", content=body, headers=head)
        assert r.status_code == 400, (body, r.status_code, r.text)
        assert r.json() == {"jsonrpc": "2.0", "id": None,
                            "error": {"code": -32600,
                                      "message": "Invalid Request"}}, (body, r.text)

    # The token endpoint takes a raw body too, and decodes it by hand.
    bad_bytes = c.post("/token", content=b"\xff\xfe grant_type=x")
    assert bad_bytes.status_code == 400, bad_bytes.status_code
    print("PASS a malformed body is an error, not a crash")


def test_a_session_id_is_issued_and_an_unknown_one_is_refused():
    """The session header is how Streamable HTTP keeps a conversation together.
    Nothing read it back, so the whole branch could have gone: a client could
    have presented any session id, including one from a server restart ago, and
    been served as though it were live.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    init = rpc(c, tok, "initialize", {"protocolVersion": PROTOCOL_VERSION})
    sid = init.headers.get("mcp-session-id")
    assert sid, dict(init.headers)

    assert rpc(c, tok, "ping", sid=sid).status_code == 200
    stale = rpc(c, tok, "ping", sid="00000000000000000000000000000000")
    assert stale.status_code == 404, stale.status_code
    assert stale.json()["error"] == "no such session", stale.text
    print("PASS a session id is issued, and an unknown one is refused")


def test_server_timing_reports_the_time_the_request_actually_took():
    """The 500ms budget is the requirement Alexa+ states, and this header is
    what Hearth reports about itself. A header that reports a number from a
    different unit, or the wrong side of a subtraction, is worse than no header:
    it is a latency claim in the submission that nothing checks.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    t0 = time.perf_counter()
    r = rpc(c, tok, "tools/call", {"name": "remember",
                                   "arguments": {"said": "keep it at 19",
                                                 "speaker": "Dad"}})
    wall_ms = (time.perf_counter() - t0) * 1000
    m = re.fullmatch(r'app;dur=([0-9.]+);desc="hearth"', r.headers["server-timing"])
    assert m, r.headers.get("server-timing")
    dur = float(m.group(1))
    # Milliseconds, measured over this request: positive, and never longer than
    # the round trip the client just timed, since it is a slice of it.
    assert 0 < dur <= wall_ms, (dur, wall_ms)
    print(f"PASS Server-Timing reports {dur:.3f}ms of a {wall_ms:.1f}ms round trip")


def test_a_batch_is_answered_as_a_batch():
    """JSON-RPC allows an array, Alexa+ may send one, and nothing had ever sent
    one. The notification filter inside it is the part that matters: a
    notification must not produce a response object, and a batch that is nothing
    but notifications must answer 202 with no body at all.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    head = {"Authorization": f"Bearer {tok}",
            "Accept": "application/json, text/event-stream"}

    r = c.post("/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                             {"jsonrpc": "2.0", "method": "notifications/ready"},
                             {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}],
               headers=head)
    assert r.status_code == 200, r.status_code
    out = r.json()
    assert [x["id"] for x in out] == [1, 2], out
    assert "tools" in out[1]["result"], out[1]

    quiet = c.post("/mcp", json=[{"jsonrpc": "2.0", "method": "notifications/ready"}],
                   headers=head)
    assert quiet.status_code == 202, quiet.status_code
    print("PASS a batch is answered as a batch, and notifications stay silent")


def test_console_tokens_are_never_handed_to_a_remote_caller():
    """The one place Hearth mints a credential without being asked for one. It
    is loopback only because an operator running it on their own machine should
    not have to paste a token to see their own house, and the deployed service
    must hand out nothing at all. Every guard in it was unexercised: the host
    list, the refusal, and the status code.
    """
    app = create_app(issuer=ISSUER, resource=RESOURCE, seed=True)
    for host in ("203.0.113.9", "10.0.0.4", "2001:db8::1"):
        remote = TestClient(app, client=(host, 41234)).get("/api/console-token")
        assert remote.status_code == 403, (host, remote.status_code)
        assert "access_token" not in remote.text, (host, remote.text)
        assert remote.json()["error"], (host, remote.text)

    # Four spellings of the same machine. An operator running Hearth locally
    # reaches it over IPv4, IPv6 or by name depending on nothing they control,
    # and being refused by their own instance is the whole feature failing.
    for host in ("127.0.0.1", "::1", "localhost"):
        near = TestClient(app, client=(host, 41234)).get("/api/console-token")
        assert near.status_code == 200, (host, near.status_code)

    local = TestClient(app).get("/api/console-token")
    assert local.status_code == 200, local.text
    assert local.json()["token_type"] == "Bearer", local.text
    # And the token it mints has to actually work, or the console is broken in
    # the one configuration this endpoint exists for.
    tok = local.json()["access_token"]
    assert TestClient(app).get(
        "/api/state", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    print("PASS console tokens are loopback only, and the one it mints works")


def test_the_console_api_refuses_every_caller_without_a_bearer_token():
    """Four endpoints that read and write a household, added late and never
    tested for the thing that matters about them. /api/state leaks the whole
    house, /api/say writes to it, /api/act acts on it and /api/retire takes
    something away, and the 401 on each was a survivor: it could have been
    deleted, one endpoint at a time, with this suite green.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing(subject="hh-guarded")
    calls = [("GET", "/api/state", {}),
             ("POST", "/api/say", {"said": "keep it at 19", "speaker": "Dad"}),
             ("POST", "/api/act", {"domain": "thermostat", "slot": "target"}),
             ("POST", "/api/retire", {"belief_id": "nope"})]

    for method, path, body in calls:
        for headers in ({}, {"Authorization": "Bearer not-a-real-token"},
                        {"Authorization": "Basic aGk6dGhlcmU="},
                        {"Authorization": f"{tok}"}):
            r = (c.get(path, headers=headers) if method == "GET"
                 else c.post(path, json=body, headers=headers))
            assert r.status_code == 401, (path, headers, r.status_code)
            assert r.json()["error"] == "unauthorized", (path, r.text)
        # And the same call goes through once it carries a real one.
        assert console(c, tok, method, path, **body).status_code == 200, path
    print("PASS all four console endpoints refuse a caller without a token")


def test_the_console_shows_who_said_it_and_what_was_done_about_it():
    """The console is the demo. Everything on it comes from one payload, and
    every key in that payload is read by name in console.html, so a renamed or
    emptied key is a blank panel on camera with a green suite behind it. The
    action list is the part that matters most: the whole product claim is that
    it can say why, and `actions` was sliced, reversed and never once read.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing(subject="hh-console")

    say = console(c, tok, "POST", "/api/say",
                  said="keep it at 19 in here", speaker="Dad").json()
    assert "19" in say["reply"], say["reply"]
    state = say["state"]
    assert {"members", "slots", "contexts", "beliefs", "actions"} <= set(state)

    # Attribution is the product. A belief with no holder is a preference
    # nobody owns, and the resolver cannot rank what it cannot attribute.
    mine = [b for b in state["beliefs"] if b["value"] == "19"]
    assert mine and mine[0]["holder_name"] == "Dad", state["beliefs"]
    assert mine[0]["live"] is True, mine[0]

    slot = next(s for s in state["slots"] if s["domain"] == "thermostat")
    assert slot["slot"] == "target" and slot["value"] == "19", slot
    assert slot["basis"] and "Dad" in slot["sentence"], slot
    assert slot["winner"]["holder"] == "Dad", slot["winner"]
    assert "losers" in slot and slot["about"] is None, slot

    assert [m["name"] for m in state["members"]].count("Dad") == 1, state["members"]
    assert any(m["grants"] == ["thermostat"] for m in state["members"])

    # A slot gets a household row and one row per person who has a scoped
    # belief about it, and only for that slot. Attaching one person's scope to
    # every slot on the board is the failure worth guarding: the console would
    # claim Ada has a thermostat of her own.
    console(c, tok, "POST", "/api/say", said="we eat at 19:00", speaker="Mum")
    console(c, tok, "POST", "/api/say", said="dinner for Ada is at 17:00",
            speaker="Mum")
    rows = console(c, tok, "GET", "/api/state").json()["slots"]
    meals = {(r["about"], r["value"]) for r in rows if r["domain"] == "meals"}
    assert meals == {(None, "19:00"), ("Ada", "17:00")}, meals
    assert {r["about"] for r in rows if r["domain"] == "thermostat"} == {None}, rows

    # The losing belief and the rule that beat it are the part of the payload
    # that makes Hearth more than a key-value store, and the console draws it.
    console(c, tok, "POST", "/api/say", said="make it 24", speaker="Mum")
    contested = next(r for r in console(c, tok, "GET", "/api/state").json()["slots"]
                     if r["domain"] == "thermostat")
    assert contested["value"] == "19", contested
    assert [(l["value"], l["holder"]) for l in contested["losers"]] == \
        [("24", "Mum")], contested["losers"]
    assert contested["losers"][0]["reason"], contested["losers"]
    assert contested["winner"]["stated_at"] and "context" in contested["winner"]
    # The ids tie a row on the board back to a belief, which is how anything on
    # the console can be stood down or argued with.
    ids = {b["id"] for b in console(c, tok, "GET", "/api/state").json()["beliefs"]}
    assert contested["winner"]["id"] in ids, contested["winner"]
    assert contested["losers"][0]["id"] in ids, contested["losers"]
    assert all({"id", "name", "role", "grants"} <= set(m)
               for m in state["members"]), state["members"]

    # And a situation shows what is riding on it, which is how anyone can see
    # what ending it would take away.
    console(c, tok, "POST", "/api/say", said="make it 23 while Gran is staying",
            speaker="Ada")
    contexts = console(c, tok, "GET", "/api/state").json()["contexts"]
    assert [x["name"] for x in contexts] == ["Gran's visit"], contexts
    assert contexts[0]["riding"] == ["thermostat.target=23"], contexts[0]

    act = console(c, tok, "POST", "/api/act",
                  domain="thermostat", slot="target").json()
    assert "19" in act["reply"] and "Dad" in act["why"], act
    actions = act["state"]["actions"]
    assert actions, "the console showed no action after acting"
    assert "thermostat" in actions[0]["what"], actions[0]
    assert "Dad" in actions[0]["why"], actions[0]
    print("PASS the console payload carries the house, the reasons and the actions")


def test_the_console_acts_on_the_person_it_was_asked_about():
    """"Dinner is at seven, and five for Ada" is the demo's second act. The
    console passes `about` through to the resolver, and the lookup that turns a
    spoken name into a member could have been dropped or inverted without a
    single test noticing, which would have answered every question with the
    household-wide value and lost the feature entirely.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing(subject="hh-about")
    console(c, tok, "POST", "/api/say", said="we eat at 19:00", speaker="Mum")
    console(c, tok, "POST", "/api/say", said="dinner for Ada is at 17:00",
            speaker="Mum")

    house = console(c, tok, "POST", "/api/act", domain="meals", slot="dinner").json()
    assert "19:00" in house["reply"], house["reply"]
    for spelling in ("Ada", "ada"):
        her = console(c, tok, "POST", "/api/act", domain="meals", slot="dinner",
                      about=spelling).json()
        assert "17:00" in her["reply"], (spelling, her["reply"])
    # Somebody who does not live here is not somebody.
    stranger = console(c, tok, "POST", "/api/act", domain="meals", slot="dinner",
                       about="Gran").json()
    assert "19:00" in stranger["reply"], stranger["reply"]
    print("PASS the console acts on the person it was asked about")


def test_acting_on_a_slot_nobody_has_set_records_nothing():
    """An assistant that logs an action it did not take is worse than one that
    logs nothing, because `why` will later explain a thing that never happened.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing(subject="hh-empty")
    r = console(c, tok, "POST", "/api/act", domain="security", slot="alarm").json()
    assert "security" in r["reply"] and "alarm" in r["reply"], r["reply"]
    assert "nobody has set" in r["reply"].lower(), r["reply"]
    assert "why" not in r, r
    assert r["state"]["actions"] == [], r["state"]["actions"]
    print("PASS acting on a slot nobody has set records no action")


def test_the_console_can_stand_a_belief_down():
    """Standing something down is the one destructive thing the console can do,
    and the id it acts on comes straight off the payload it drew. Nothing had
    ever followed that loop round: read a belief id from the state, send it
    back, and check the house actually changed.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing(subject="hh-retire")
    state = console(c, tok, "POST", "/api/say",
                    said="keep it at 19 in here", speaker="Dad").json()["state"]
    bid = next(b["id"] for b in state["beliefs"] if b["value"] == "19")

    gone = console(c, tok, "POST", "/api/retire", belief_id=bid).json()
    assert "19" in gone["reply"] and "thermostat" in gone["reply"], gone["reply"]
    assert gone["state"]["slots"] == [], gone["state"]["slots"]
    assert [b["live"] for b in gone["state"]["beliefs"]] == [False], gone["state"]

    stood = next(b for b in gone["state"]["beliefs"] if b["id"] == bid)
    assert stood["ended_reason"], stood

    again = console(c, tok, "POST", "/api/retire", belief_id=bid).json()
    assert "no standing belief" in again["reply"].lower(), again["reply"]
    missing = console(c, tok, "POST", "/api/retire").json()
    assert "no standing belief" in missing["reply"].lower(), missing["reply"]
    print("PASS the console can stand a belief down, once")


def test_the_console_page_and_the_policy_pages_are_served():
    """Three pages a human opens: the demo, and the two the add-on listing is
    rejected for if they are missing. They are generated in Python, so an empty
    string is a valid, servable, 200-answering blank page, and every one of them
    could have gone blank with this suite green.
    """
    c, _ = client()
    page = c.get("/console")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert len(page.text) > 500, len(page.text)

    privacy = c.get("/privacy")
    assert privacy.status_code == 200, privacy.status_code
    assert "<title>Privacy" in privacy.text, privacy.text[:200]
    for tag in ("</title>", "<style>", "</style>", "</h1>", "</main>"):
        assert tag in privacy.text, tag
    # A privacy policy that does not say what is stored is not a privacy policy,
    # and Amazon's reviewer reads it.
    for claim in ("What it stores", "What it does not store", "No audio",
                  "Where it lives"):
        assert claim in privacy.text, claim

    terms = c.get("/terms")
    assert terms.status_code == 200, terms.status_code
    assert "<title>Terms of use" in terms.text, terms.text[:200]
    for claim in ("no warranty", "not a safety system", "github.com/ubmids/hearth"):
        assert claim.lower() in terms.text.lower(), claim
    print("PASS the console and both policy pages are served with their content")


def test_healthz_answers_with_the_state_of_this_instance():
    """The keepalive pings it, the platform health check reads it, and it is the
    first thing anyone curls. It reports counts, and nothing had ever compared
    one against the house it claims to describe.

    The house it describes is the default one, which is the household a caller
    whose subject is "default" writes into. Counting live beliefs rather than
    all of them is the part worth pinning: a retired belief is still in the
    list, and a health check that counts it is reporting a house that is fuller
    than the one the assistant is answering from.
    """
    c, app = client()
    tok = app.state.auth.issue_for_testing(subject="default")
    before = c.get("/healthz").json()
    assert before["ok"] is True, before
    assert before["protocol"] == PROTOCOL_VERSION, before
    assert before["members"] == len(app.state.household.members), before
    assert before["beliefs"] == 0, before
    assert before["keepalive"] is False, before

    reply = said_by(c, tok, "remember", said="keep it at 19 in here", speaker="Dad")
    after = c.get("/healthz").json()
    assert after["beliefs"] == before["beliefs"] + 1, (before, after)

    said_by(c, tok, "stand_down",
            belief_id=re.search(r"\[([0-9a-f]{6,})\]", reply).group(1))
    assert c.get("/healthz").json()["beliefs"] == before["beliefs"], "counted a dead belief"
    print("PASS healthz describes the instance it is running in")


def test_the_token_response_may_not_be_cached_anywhere():
    """OAuth 2.1 requires `Cache-Control: no-store` on a token response and RFC
    6749 asks for the legacy `Pragma: no-cache` beside it. A cached bearer token
    is a bearer token handed to whoever shares the cache.
    """
    c, app = client()
    verifier = secrets.token_urlsafe(48)
    t = redeem(c, app, code_for(c, app, verifier), verifier)
    assert t.status_code == 200, t.text
    assert t.headers.get("cache-control") == "no-store", dict(t.headers)
    assert t.headers.get("pragma") == "no-cache", dict(t.headers)
    print("PASS the token response forbids caching in both spellings")


def test_a_household_is_kept_on_disk_per_subject_and_survives_a_restart():
    """The instance recycles. Render spins a free service down, a deploy
    replaces it, and the pitch is that the house remembers who said what, so an
    empty house after a restart is the opposite of the product being
    demonstrated. Two families on one instance must come back as two families.

    Nothing had ever run create_app with a data path at all, so persistence
    could have been off in production and every test would still pass.
    """
    tmp = tempfile.mkdtemp(prefix=f"hearth-app-{os.getpid()}-")
    try:
        path = os.path.join(tmp, "house")
        app = create_app(issuer=ISSUER, resource=RESOURCE, data_path=path)
        c = TestClient(app)
        alice = app.state.auth.issue_for_testing(subject="hh-alice")
        bob = app.state.auth.issue_for_testing(subject="hh-bob")
        console(c, alice, "POST", "/api/say", said="keep it at 19", speaker="Dad")
        console(c, bob, "POST", "/api/say", said="make it 26", speaker="Dad")

        # A new process, the same disk. Tokens do not survive a restart, so the
        # subjects are re-minted the way account linking would re-present them.
        again = create_app(issuer=ISSUER, resource=RESOURCE, data_path=path)
        c2 = TestClient(again)
        for subject, expected in (("hh-alice", "19"), ("hh-bob", "26")):
            tok = again.state.auth.issue_for_testing(subject=subject)
            values = [s["value"] for s in
                      console(c2, tok, "GET", "/api/state").json()["slots"]]
            assert values == [expected], (subject, values)

        # And the deployment configures it by environment, which is the only way
        # the running service ever sets it.
        os.environ["HEARTH_DATA"] = os.path.join(tmp, "env-house")
        try:
            env_app = create_app(issuer=ISSUER, resource=RESOURCE)
            env_c = TestClient(env_app)
            tok = env_app.state.auth.issue_for_testing(subject="hh-env")
            console(env_c, tok, "POST", "/api/say", said="make it 21", speaker="Dad")
            reopened = create_app(issuer=ISSUER, resource=RESOURCE)
            tok2 = reopened.state.auth.issue_for_testing(subject="hh-env")
            values = [s["value"] for s in TestClient(reopened).get(
                "/api/state", headers={"Authorization": f"Bearer {tok2}"}
            ).json()["slots"]]
            assert values == ["21"], values
        finally:
            del os.environ["HEARTH_DATA"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS a household is kept on disk per subject and survives a restart")


def test_the_running_service_is_configured_from_its_environment():
    """create_app is called once, by the process the platform starts, with no
    arguments at all. Every test calls it with an issuer and a resource, so the
    branch that the deployment actually takes had never run: the environment
    keys could have been misspelled and every test would still pass while the
    live service advertised localhost in both well-known documents and Alexa+
    refused to link an account against it.
    """
    for key in ("HEARTH_ISSUER", "HEARTH_RESOURCE"):
        assert key not in os.environ, key
    try:
        bare_app = create_app()
        bare = TestClient(bare_app)
        assert bare.get("/.well-known/oauth-authorization-server").json()["issuer"] \
            == "http://localhost:8000"
        assert {m.name for m in bare_app.state.household.members.values()} == \
            {"Dad", "Mum", "Ada"}, bare_app.state.household.members

        os.environ["HEARTH_ISSUER"] = "https://hearth.example/"
        configured = TestClient(create_app())
        meta = configured.get("/.well-known/oauth-authorization-server").json()
        # The trailing slash has to go, or every URL built from it doubles up
        # and the audience the token is bound to stops matching the resource.
        assert meta["issuer"] == "https://hearth.example", meta
        assert meta["token_endpoint"] == "https://hearth.example/token", meta
        # The resource defaults to the MCP endpoint under the issuer, which is
        # the one URL the add-on manifest points Alexa+ at.
        prm = configured.get("/.well-known/oauth-protected-resource").json()
        assert prm["resource"] == "https://hearth.example/mcp", prm
        assert prm["authorization_servers"] == ["https://hearth.example"], prm

        os.environ["HEARTH_RESOURCE"] = "https://elsewhere.example/mcp/"
        split = TestClient(create_app())
        assert split.get("/.well-known/oauth-protected-resource").json()["resource"] \
            == "https://elsewhere.example/mcp"
    finally:
        os.environ.pop("HEARTH_ISSUER", None)
        os.environ.pop("HEARTH_RESOURCE", None)
    print("PASS the running service is configured from its environment")


def test_the_keepalive_runs_only_when_it_is_switched_on():
    """A stopgap for the free plan, and the reason the cold start does not land
    on a judge. It is off by default and on in the deployed environment, and
    both halves were unasserted: the flag could have been inverted, the URL
    could have pointed anywhere, and the interval could have failed to parse.
    """
    started = []

    async def recorder(url, every, log=print):
        started.append((url, every))

    real = app_module._keepalive
    app_module._keepalive = recorder
    try:
        with TestClient(create_app(issuer=ISSUER, resource=RESOURCE)) as c:
            assert started == [], started
            assert c.get("/healthz").json()["keepalive"] is False

        for value in ("1", "true", "yes"):
            started.clear()
            os.environ["HEARTH_KEEPALIVE"] = value
            with TestClient(create_app(issuer=ISSUER, resource=RESOURCE)) as c:
                # It has to go out through the public URL to count as an inbound
                # request, which is the entire reason the function exists.
                assert started == [(f"{ISSUER}/healthz", 600)], (value, started)
                assert c.get("/healthz").json()["keepalive"] is True

        started.clear()
        os.environ["HEARTH_KEEPALIVE_SECONDS"] = "90"
        with TestClient(create_app(issuer=ISSUER, resource=RESOURCE)):
            assert started == [(f"{ISSUER}/healthz", 90)], started
    finally:
        app_module._keepalive = real
        os.environ.pop("HEARTH_KEEPALIVE", None)
        os.environ.pop("HEARTH_KEEPALIVE_SECONDS", None)
    print("PASS the keepalive runs only when switched on, against the public URL")


def test_a_failed_keepalive_ping_never_takes_the_service_down():
    """It is a `while True` around a network call on a live service. If a failed
    ping escaped, the task would die silently and the instance would go back to
    sleeping, which is the one thing it exists to prevent.
    """
    import asyncio

    seen = []
    real_sleep = asyncio.sleep

    async def no_wait(_seconds):
        await real_sleep(0)

    async def drive(url):
        asyncio.sleep = no_wait
        try:
            task = asyncio.create_task(
                app_module._keepalive(url, 600, log=seen.append))
            for _ in range(500):
                await real_sleep(0.002)
                if seen:
                    break
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            asyncio.sleep = real_sleep

    # Nothing is listening on port 9, so the ping cannot succeed.
    asyncio.run(drive("http://127.0.0.1:9/healthz"))
    assert seen, "the keepalive never got as far as one ping"
    assert all(isinstance(line, str) for line in seen), seen
    print("PASS a failed keepalive ping is logged and swallowed")


def test_delete_ends_a_session_and_nothing_else():
    """Streamable HTTP: a client leaving sends DELETE with its session id. The
    session goes; the household and the record of what was called stay."""
    c, app = client()
    tok = app.state.auth.issue_for_testing()
    r = rpc(c, tok, "initialize", {"protocolVersion": PROTOCOL_VERSION})
    sid = r.headers["mcp-session-id"]
    assert rpc(c, tok, "tools/call", {"name": "whats_true", "arguments": {
        "domain": "thermostat", "slot": "target"}}, sid=sid).status_code == 200
    assert c.delete("/mcp", headers={"Mcp-Session-Id": sid}).status_code == 401
    gone = c.delete("/mcp", headers={"Authorization": f"Bearer {tok}",
                                     "Mcp-Session-Id": sid})
    assert gone.status_code == 204, gone.status_code
    assert gone.headers["mcp-protocol-version"] == PROTOCOL_VERSION
    assert rpc(c, tok, "tools/list", sid=sid).status_code == 404
    again = c.delete("/mcp", headers={"Authorization": f"Bearer {tok}",
                                      "Mcp-Session-Id": sid})
    assert again.status_code == 404
    assert c.delete("/mcp", headers={"Authorization": f"Bearer {tok}"}).status_code == 400
    assert [e.tool for e in app.state.home_for("household")[2].trace.entries] == ["whats_true"]
    print("PASS DELETE ends a session, and only the session")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nall green ({len(fns)} conformance tests)")
