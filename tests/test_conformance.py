"""Alexa+ conformance, asserted rather than assumed.

Everything here is a requirement quoted from the Alexa+ MCP toolkit docs. The
three marked TRAP are the ones that differ from what a general-purpose MCP SDK
would do by default, which is why Hearth implements the transport directly.
"""
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from hearth.app import create_app
from hearth.oauth import s256

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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"\nall green ({len(fns)} conformance tests)")
