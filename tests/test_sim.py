"""The simulated Alexa+ client: what it plans, how it speaks, what it admits.

The simulator is the part of the video a judge sees first, so it is held to the
same standard as the server: every scripted line must reach the tool it is
meant to, a configured model must be used when present and fallen back from
when it fails, the voice must never spend somebody's AWS key for an anonymous
caller, and the page must say it is a simulation.
"""
import datetime as dt
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from hearth import sim
from hearth.app import create_app
from hearth.mcp import TOOLS

ISSUER = "https://hearth.test"
PAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "hearth", "web", "alexa.html")


def script():
    """The scenes, read out of the page itself, so the test and the video
    cannot drift apart."""
    src = open(PAGE).read()
    block = src[src.index("const SCRIPT = ["):src.index("];", src.index("const SCRIPT = ["))]
    return re.findall(r'\["(\w+)", "([^"]+)"\]', block)


def test_every_scripted_line_reaches_the_tool_it_is_for():
    expected = ["give_dose", "catch_up", "why", "arrange", "reorder",
                "checkout.complete", "whats_true", "remember", "record"]
    lines = script()
    assert len(lines) == len(expected), lines
    for (who, said), want in zip(lines, expected):
        plan = sim.plan_rules(said, who, {"checkout": "chk_x"})
        got = plan[0].get("name") or plan[0].get("host")
        assert got == want, (said, plan)
    first = sim.plan_rules(*reversed(lines[0]))
    print("PASS the script plans as intended")


def test_the_rules_planner_fills_the_arguments_a_tool_needs():
    p = sim.plan_rules("Alexa, I'm just going to take my blood thinner.", "Rose")[0]
    assert p == {"name": "give_dose", "arguments": {"medication": "warfarin",
                                                    "given_by": "Rose"}}
    p = sim.plan_rules("Has Mom had her warfarin today?", "Tom")[0]
    assert p["name"] == "check_dose" and p["arguments"]["asked_by"] == "Tom"
    p = sim.plan_rules("Mom's cardiology moved to Thursday at 10. Sort it out.", "Ada")[0]
    assert p["arguments"] == {"what": "cardiology", "when": "thursday at 10",
                              "asked_by": "Ada"}, p
    p = sim.plan_rules("Can Mom have a glass of wine?", "Tom")[0]
    assert p["arguments"]["slot"] == "alcohol"
    # "Yes" means pay only when something is waiting to be paid for.
    assert sim.plan_rules("Yes, go ahead.", "Grace", {})[0]["name"] == "remember"
    # Anything else is a household statement, which is what remember is for.
    p = sim.plan_rules("Grace does Mondays from now on", "Ada")[0]
    assert p == {"name": "remember", "arguments": {
        "said": "Grace does Mondays from now on", "speaker": "Ada"}}
    # A rule about a dose is a rule, not somebody taking one.
    assert sim.plan_rules("Mom takes two metformin a day", "Ada")[0]["name"] == "remember"
    print("PASS the rules planner fills arguments")


STUB = {"reply": None, "status": 200, "seen": None}


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        STUB["seen"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if STUB["status"] != 200:
            self.send_response(STUB["status"]); self.end_headers(); return
        out = json.dumps({"choices": [{"message": STUB["reply"]}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def test_a_configured_model_plans_with_hearths_own_tool_list_and_falls_back():
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ.update(HEARTH_SIM_LLM_BASE_URL=f"http://127.0.0.1:{srv.server_port}",
                      HEARTH_SIM_LLM_API_KEY="k", HEARTH_SIM_LLM_MODEL="stub-1")
    try:
        STUB["reply"] = {"tool_calls": [{"function": {
            "name": "check_dose",
            "arguments": json.dumps({"medication": "warfarin", "asked_by": "Tom"})}},
            {"function": {"name": "not_a_tool", "arguments": "{}"}}]}
        out = sim.plan("did mom take it", "Tom", TOOLS)
        assert out["planner"] == "model:stub-1 + skill:hearth-care", out
        # The model is taught by the Agent Skill, the same one any other
        # assistant using Hearth loads, front matter stripped.
        system = STUB["seen"]["messages"][0]["content"]
        assert "Say refusals as given" in system and "name: hearth-care" not in system
        assert out["calls"] == [{"name": "check_dose", "arguments": {
            "medication": "warfarin", "asked_by": "Tom"}}], out
        sent = {f["function"]["name"] for f in STUB["seen"]["tools"]}
        assert sent == {t["name"] for t in TOOLS}
        STUB["status"] = 500
        out = sim.plan("Has Mom had her warfarin today?", "Tom", TOOLS)
        assert out["planner"] == "rules" and out["calls"][0]["name"] == "check_dose"
    finally:
        STUB["status"] = 200
        for k in ("HEARTH_SIM_LLM_BASE_URL", "HEARTH_SIM_LLM_API_KEY",
                  "HEARTH_SIM_LLM_MODEL"):
            os.environ.pop(k, None)
        srv.shutdown()
    print("PASS a model plans when configured and the rules catch it when it fails")


def test_the_voice_is_chosen_by_what_is_configured():
    saved = {k: os.environ.pop(k, None) for k in
             ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "HEARTH_PIPER_VOICE",
              "HEARTH_TTS")}
    try:
        assert sim.tts_provider() == "browser"
        assert sim.speak("hello") == (None, "", "browser")
        os.environ.update(AWS_ACCESS_KEY_ID="AKIDEXAMPLE",
                          AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY")
        assert sim.tts_provider() == "polly"
        os.environ["HEARTH_TTS"] = "browser"
        assert sim.tts_provider() == "browser"
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    print("PASS the voice provider follows configuration")


def test_the_polly_request_is_signed_with_sigv4():
    os.environ.update(AWS_ACCESS_KEY_ID="AKIDEXAMPLE",
                      AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY")
    try:
        when = dt.datetime(2026, 10, 13, 12, 0, 0, tzinfo=dt.timezone.utc)
        url, h, body = sim.polly_request("Hold on, Rose.", "Joanna", now=when,
                                         region="us-east-1")
        assert url == "https://polly.us-east-1.amazonaws.com/v1/speech"
        assert json.loads(body) == {"Text": "Hold on, Rose.", "OutputFormat": "mp3",
                                    "VoiceId": "Joanna", "Engine": "neural"}
        assert h["x-amz-date"] == "20261013T120000Z"
        assert h["authorization"].startswith(
            "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261013/us-east-1/polly/aws4_request, "
            "SignedHeaders=content-type;host;x-amz-date, Signature=")
        sig = h["authorization"].rsplit("=", 1)[1]
        assert re.fullmatch(r"[0-9a-f]{64}", sig)
        # Deterministic: same inputs, same signature; any change, a different one.
        assert sim.polly_request("Hold on, Rose.", "Joanna", now=when,
                                 region="us-east-1")[1]["authorization"] == h["authorization"]
        assert sim.polly_request("Hold on.", "Joanna", now=when,
                                 region="us-east-1")[1]["authorization"] != h["authorization"]
    finally:
        os.environ.pop("AWS_ACCESS_KEY_ID"); os.environ.pop("AWS_SECRET_ACCESS_KEY")
    print("PASS the Polly request is SigV4 signed")


def test_the_simulator_endpoints_are_behind_the_bearer_and_say_what_they_are():
    app = create_app(issuer=ISSUER, resource=f"{ISSUER}/mcp", seed="care")
    c = TestClient(app)
    for method, path in (("GET", "/sim/config"), ("POST", "/sim/plan"),
                         ("POST", "/sim/tts")):
        r = c.request(method, path, json={})
        assert r.status_code == 401 and "www-authenticate" not in r.headers, path
    tok = app.state.auth.issue_for_testing(subject="sim")
    h = {"Authorization": f"Bearer {tok}"}
    cfg = c.get("/sim/config", headers=h).json()
    assert cfg["simulated"] is True and cfg["planner"] in ("rules", "model + skill:hearth-care")
    plan = c.post("/sim/plan", json={"said": "Alexa, what did I miss?",
                                     "speaker": "Tom"}, headers=h).json()
    assert plan["calls"] == [{"name": "catch_up", "arguments": {"person": "Tom"}}]
    page = c.get("/alexa")
    assert page.status_code == 200
    # Labelled where a viewer sees it, not only in a comment.
    assert ">Simulated Alexa+<" in page.text
    assert "Simulated ${esc(d.name)}" in page.text
    assert "initialize" in page.text and "tools/list" in page.text \
        and "resources/read" in page.text and "tools/call" in page.text
    print("PASS simulator endpoints are protected and the page says it is a simulation")


def test_the_hero_line_survives_the_ways_people_actually_say_it():
    """Audit 028 #17. "Time for my warfarin" and "I'll have my Coumadin now"
    went to `remember` ("Nothing durable to remember in that"), so a judge who
    typed a variant never saw the refusal."""
    for said, med in (("Alexa, time for my warfarin", "warfarin"),
                      ("Alexa, I'll have my Coumadin now", "warfarin"),
                      ("I'm taking my Jantoven", "warfarin"),
                      ("Alexa, I'm just going to take my blood thinner.", "warfarin"),
                      ("I'm taking my vitamin D", "vitamin d")):
        p = sim.plan_rules(said, "Rose")[0]
        assert p == {"name": "give_dose", "arguments": {"medication": med,
                                                        "given_by": "Rose"}}, (said, p)
    for said, tool in (("Mom finished the antibiotics.", "remember"),
                       ("I'll have my coffee now", "remember"),
                       ("Mom takes one warfarin a day", "remember")):
        assert sim.plan_rules(said, "Ada")[0]["name"] == tool, said
    print("PASS the refusal is reached however the dose is announced")


def test_a_slow_local_model_gets_its_own_timeout_and_a_warm_up():
    """Audit 028 #9. A 3B model on CPU measured 2-12 s per line and ~19 s on
    the first prompt, past the planner's fixed 12 s. The timeout is now
    configurable, and warm_up() spends the first prompt before anyone speaks;
    a model that times out still falls back to the rules."""
    import time as _time

    class Slow(Stub):
        def do_POST(self):
            _time.sleep(STUB.get("delay", 0))
            try:
                Stub.do_POST(self)
            except (BrokenPipeError, ConnectionResetError):
                pass                       # the planner gave up first, as meant

    srv = HTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ.update(HEARTH_SIM_LLM_BASE_URL=f"http://127.0.0.1:{srv.server_port}",
                      HEARTH_SIM_LLM_API_KEY="local", HEARTH_SIM_LLM_MODEL="qwen-3b")
    try:
        STUB["reply"] = {"tool_calls": [{"function": {
            "name": "check_dose",
            "arguments": json.dumps({"medication": "blood thinner", "asked_by": "Tom"})}}]}
        STUB["delay"] = 0.6
        os.environ["HEARTH_SIM_LLM_TIMEOUT"] = "0.2"
        out = sim.plan("Has Mom had her warfarin today?", "Tom", TOOLS)
        assert out["planner"] == "rules" and out["calls"][0]["name"] == "check_dose", out
        os.environ["HEARTH_SIM_LLM_TIMEOUT"] = "5"
        out = sim.plan("Has Mom had her warfarin today?", "Tom", TOOLS)
        assert out["planner"] == "model:qwen-3b + skill:hearth-care", out
        os.environ["HEARTH_SIM_LLM_TIMEOUT"] = "0.2"
        assert sim.warm_up(TOOLS) is True, "warm-up used the short timeout"
        assert os.environ["HEARTH_SIM_LLM_TIMEOUT"] == "0.2", "warm-up leaked its timeout"
    finally:
        STUB["delay"] = 0
        for k in ("HEARTH_SIM_LLM_BASE_URL", "HEARTH_SIM_LLM_API_KEY",
                  "HEARTH_SIM_LLM_MODEL", "HEARTH_SIM_LLM_TIMEOUT"):
            os.environ.pop(k, None)
        srv.shutdown()
    assert sim.warm_up(TOOLS) is False, "warmed a model nobody configured"
    print("PASS a slow local model has its own timeout and a warm-up")


def test_a_dose_announcement_never_depends_on_the_model():
    """Measured: Qwen2.5-3B planned "Alexa, time for my warfarin" as
    `remember`, so the refusal would never have run. A dose being taken is
    routed by the rules whatever the model would say; the rest is the model's."""
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ.update(HEARTH_SIM_LLM_BASE_URL=f"http://127.0.0.1:{srv.server_port}",
                      HEARTH_SIM_LLM_API_KEY="k", HEARTH_SIM_LLM_MODEL="small")
    try:
        STUB["reply"] = {"tool_calls": [{"function": {"name": "remember", "arguments":
            json.dumps({"said": "Rose says: Alexa, time for my warfarin",
                        "speaker": "Rose"})}}]}
        out = sim.plan("Alexa, time for my warfarin", "Rose", TOOLS)
        assert out == {"planner": "rules (dose guard)", "calls": [{"name": "give_dose",
                       "arguments": {"medication": "warfarin", "given_by": "Rose"}}]}, out
        out = sim.plan("Mom finished the antibiotics.", "Ada", TOOLS)
        assert out["planner"] == "model:small + skill:hearth-care", out
    finally:
        for k in ("HEARTH_SIM_LLM_BASE_URL", "HEARTH_SIM_LLM_API_KEY",
                  "HEARTH_SIM_LLM_MODEL"):
            os.environ.pop(k, None)
        srv.shutdown()
    print("PASS a dose announcement is routed by the rules, whatever the model says")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall green (simulator)")
