"""The model write path, exercised against a stub that speaks its protocol.

This path had never run. Without a key the pipeline quietly used the rule
extractor, every test passed, and the model branch, its request shape, its
response parsing and its name-to-id mapping were all unverified code shipping to
a deadline. A stub that speaks the OpenAI chat-completions protocol closes that:
it does not prove a model writes good beliefs, but it proves this code would
handle it correctly when one does, and that it degrades the way it claims to
when one does not.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hearth import extract as ex

STATE = {"reply": None, "status": 200, "last_request": None}


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        STATE["last_request"] = json.loads(body)
        if STATE["status"] != 200:
            self.send_response(STATE["status"])
            self.end_headers()
            self.wfile.write(b'{"error":"nope"}')
            return
        payload = {"choices": [{"message": {"content":
                   json.dumps(STATE["reply"])}}]}
        out = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def serve():
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


SRV, BASE = serve()
NAMES = {"Dad": "m-dad", "Ada": "m-ada"}


def configure(**over):
    os.environ["HEARTH_LLM_BASE_URL"] = over.get("base", BASE)
    os.environ["HEARTH_LLM_API_KEY"] = over.get("key", "test-key")
    os.environ["HEARTH_LLM_MODEL"] = "stub-model"


def test_request_is_shaped_the_way_the_api_expects():
    configure()
    STATE.update(status=200, reply={"beliefs": []})
    ex.llm_extract("keep it at 19", NAMES)
    req = STATE["last_request"]
    assert req["model"] == "stub-model"
    assert req["temperature"] == 0
    assert req["response_format"] == {"type": "json_object"}
    assert req["messages"][0]["role"] == "system"
    assert "Dad" in req["messages"][1]["content"], "member names must reach the model"
    assert "keep it at 19" in req["messages"][1]["content"]
    print("PASS request shape, and the household reaches the model")


def test_response_is_parsed_into_beliefs():
    configure()
    STATE.update(status=200, reply={"beliefs": [
        {"domain": "thermostat", "slot": "target", "value": "19",
         "scope": None, "context": None}]})
    out = ex.llm_extract("keep it at 19", NAMES)
    assert out == [{"domain": "thermostat", "slot": "target", "value": "19",
                    "scope": None, "context": None}], out
    print("PASS a model response becomes a belief")


def test_a_person_name_becomes_a_member_id():
    """The model answers in names because that is what it was shown. Storing a
    name where an id belongs would silently break every scoped lookup, since
    resolution matches on id."""
    configure()
    STATE.update(status=200, reply={"beliefs": [
        {"domain": "meals", "slot": "dinner", "value": "17:00",
         "scope": "Ada", "context": None}]})
    out = ex.llm_extract("dinner for Ada at five", NAMES)
    assert out[0]["scope"] == "m-ada", out
    print("PASS a name in the model's answer is mapped to a member id")


def test_an_unknown_name_does_not_become_a_bogus_scope():
    configure()
    STATE.update(status=200, reply={"beliefs": [
        {"domain": "meals", "slot": "dinner", "value": "17:00",
         "scope": "Somebody Else", "context": None}]})
    out = ex.llm_extract("dinner for the dog", NAMES)
    assert out[0]["scope"] is None, out
    print("PASS an unknown name scopes to the household, not to a stranger")


def test_incomplete_beliefs_are_dropped():
    configure()
    STATE.update(status=200, reply={"beliefs": [
        {"domain": "thermostat", "slot": "target", "value": "19"},
        {"domain": "thermostat", "slot": "", "value": "20"},
        {"domain": "", "slot": "target", "value": "21"},
        {"domain": "shopping", "slot": "coffee", "value": ""},
    ]})
    out = ex.llm_extract("several things", NAMES)
    assert len(out) == 1 and out[0]["value"] == "19", out
    print("PASS beliefs missing a domain, slot or value are dropped")


def test_an_api_failure_falls_back_rather_than_losing_what_was_said():
    """A write path that fails closed loses what someone just told the house."""
    configure()
    STATE.update(status=500, reply=None)
    out = ex.llm_extract("keep it at 19", NAMES)
    assert out and out[0]["domain"] == "thermostat", out
    print("PASS an API failure falls back to the rule extractor")


def test_malformed_json_falls_back():
    configure()
    STATE.update(status=200, reply="not an object at all")
    out = ex.llm_extract("keep it at 19", NAMES)
    assert out and out[0]["value"] == "19", out
    print("PASS a malformed response falls back")


def test_no_key_configured_uses_the_rules_without_calling_out():
    configure(base="", key="")
    STATE["last_request"] = None
    out = ex.llm_extract("keep it at 19", NAMES)
    assert out and out[0]["value"] == "19"
    assert STATE["last_request"] is None, "it called the API with no key configured"
    print("PASS with no key it uses the rules and makes no network call")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    try:
        for fn in fns:
            fn()
        print(f"\nall green ({len(fns)} tests)")
    finally:
        SRV.shutdown()
        for k in ("HEARTH_LLM_BASE_URL", "HEARTH_LLM_API_KEY", "HEARTH_LLM_MODEL"):
            os.environ.pop(k, None)
