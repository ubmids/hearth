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
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hearth import extract as ex

STATE = {"reply": None, "status": 200, "last_request": None,
         "last_path": None, "last_headers": None}


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        STATE["last_request"] = json.loads(body)
        # The path and the credential are half the contract with an
        # OpenAI-compatible endpoint, and a stub that answers any POST proves
        # neither unless it writes down what it was actually sent.
        STATE["last_path"] = self.path
        STATE["last_headers"] = {k.lower(): v for k, v in self.headers.items()}
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
    if "model" in over:
        os.environ.pop("HEARTH_LLM_MODEL", None)
    else:
        os.environ["HEARTH_LLM_MODEL"] = "stub-model"
    STATE.update(last_request=None, last_path=None, last_headers=None)


def test_request_is_shaped_the_way_the_api_expects():
    configure()
    STATE.update(status=200, reply={"beliefs": []})
    ex.llm_extract("keep it at 19", NAMES)
    req = STATE["last_request"]
    assert req["model"] == "stub-model"
    assert req["temperature"] == 0
    assert req["response_format"] == {"type": "json_object"}
    assert req["messages"][0]["role"] == "system"
    # Under the key the API reads it from. A prompt filed anywhere else is a
    # model asked to do this job with no instructions at all.
    assert req["messages"][0]["content"] == ex.SYSTEM
    content = req["messages"][1]["content"]
    assert "keep it at 19" in content
    # Each member has to arrive as its own name. Run two together and the model
    # is shown a third person who does not live here, and the name it answers
    # with maps back to nobody.
    for name in NAMES:
        assert re.search(rf"\b{name}\b", content), (name, content)
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




# --- the deterministic half, given the same treatment ------------------------
# Everything above tests the model path. The rule extractor and the context-end
# detector are what actually run in CI and in any deployment without a key, and
# they had never been tested directly: most of the rules, both templates that
# name a situation, and the whole of `detect_context_end` were survivors.


def test_every_household_rule_pulls_out_the_belief_it_names():
    """One sentence per rule, because the rules are ordered and first match
    wins, so a rule can be deleted outright and the one under it will answer
    for it with a different domain. Only the thermostat rules were ever
    exercised; shopping, meals and lights are claimed in the tool descriptions,
    the README and the demo script, and nothing extracted them.
    """
    cases = [
        ("turn the thermostat to 21", "thermostat", "target", "21"),
        ("keep it at 19", "thermostat", "target", "19"),
        ("switch to Lavazza coffee", "shopping", "coffee", "Lavazza"),
        ("with coffee from now on buy Illy", "shopping", "coffee", "Illy"),
        ("dinner is at 18:30", "meals", "dinner", "18:30"),
        ("bedtime is 20:30", "lights", "bedtime", "20:30"),
        ("make it 22", "thermostat", "target", "22"),
    ]
    for said, domain, slot, value in cases:
        out = ex.rule_extract(said, NAMES)
        assert len(out) == 1, (said, out)
        assert (out[0]["domain"], out[0]["slot"], out[0]["value"]) == \
            (domain, slot, value), (said, out)
    print(f"PASS all {len(cases)} household rules pull out the belief they name")


def test_a_sentence_with_nothing_durable_in_it_is_not_remembered():
    """The privacy policy says small talk is discarded and never written. That
    is a claim about this function, and it is the one an extractor that matches
    too eagerly breaks first.
    """
    for said in ("nice weather today", "has anyone seen my keys",
                 "I'll be back later", ""):
        assert ex.rule_extract(said, NAMES) == [], said
    print("PASS a sentence with nothing durable in it is not remembered")


def test_a_situation_is_named_from_the_words_that_open_it():
    """A belief tied to a situation expires when the situation does, so the
    name is the handle everything else hangs off. Only the "while X is staying"
    spelling was ever used, and the name it builds is what `end_context` and the
    detector both have to match later.
    """
    cases = [("make it 23 while Gran is staying", "Gran's visit"),
             ("keep it at 23 until Gran goes home", "Gran's visit"),
             ("make it 21 during the cold snap", "the cold snap"),
             ("keep it at 24 in this heatwave", "the heatwave")]
    for said, context in cases:
        out = ex.rule_extract(said, NAMES)
        assert out and out[0]["context"] == context, (said, out)
    # And an ordinary sentence opens nothing, or every belief in the house
    # would be riding on a situation that never ends.
    assert ex.rule_extract("keep it at 19", NAMES)[0]["context"] is None
    print("PASS a situation is named from the words that open it")


def test_a_belief_is_scoped_to_who_it_is_about_not_to_who_said_it():
    """The distinction the whole scope feature rests on, and the one an
    over-eager pattern destroys. "Ada says keep it at 22" is Ada speaking for
    the house; "dinner for Ada is at five" is about Ada. Scoping the first would
    quietly file every rule a person states under that person, and the household
    would stop having any shared preferences at all.
    """
    about = ex.rule_extract("dinner for Ada is at 17:00", NAMES)
    assert about[0]["scope"] == "m-ada", about
    possessive = ex.rule_extract("Ada's bedtime is 20:30", NAMES)
    assert possessive[0]["scope"] == "m-ada", possessive

    for said in ("Ada says keep it at 22", "keep it at 22"):
        spoken = ex.rule_extract(said, NAMES)
        assert spoken[0]["scope"] is None, (said, spoken)
    # Somebody who does not live here cannot be scoped to.
    stranger = ex.rule_extract("dinner for Gran is at 17:00", NAMES)
    assert stranger[0]["scope"] is None, stranger
    print("PASS a belief is scoped to who it is about, not to who said it")


def test_a_sentence_closes_the_situation_it_names_and_no_other():
    """A context that can open but never close is a leak: the house obeys a rule
    nobody remembers setting. The detector had one test through the tools and
    none of its own, so five of its six patterns and both of its direct-naming
    branches were survivors.
    """
    closes = [
        (["Gran's visit"], "Gran's gone home"),
        (["Gran's visit"], "Gran's visit is over"),
        (["Gran's visit"], "Gran is better now"),
        (["the cold snap"], "the cold snap is over"),
        (["the cold snap"], "that cold snap is done"),
        (["the cold snap"], "it's not cold any more"),
        (["the cold snap"], "stop the cold snap"),
        (["the heatwave"], "the heatwave has broken"),
    ]
    for open_contexts, said in closes:
        assert ex.detect_context_end(said, open_contexts) == open_contexts[0], \
            (said, open_contexts)

    closes_nothing = [
        # Naming a situation is not ending it.
        (["the cold snap"], "I miss the cold snap"),
        (["Gran's visit"], "keep it at 19"),
        # A situation nobody opened closes nothing, and must not take an
        # unrelated one down with it.
        (["Gran's visit"], "the heatwave is over"),
        (["Gran's visit", "the cold snap"], "Sam is better now"),
        ([], "Gran's gone home"),
    ]
    for open_contexts, said in closes_nothing:
        assert ex.detect_context_end(said, open_contexts) is None, \
            (said, open_contexts)
    print(f"PASS {len(closes)} sentences close the situation they name, "
          f"{len(closes_nothing)} close nothing")


def test_the_model_is_asked_at_the_endpoint_with_the_credential_it_was_given():
    """The stub answers any POST to any path, so the URL and the Authorization
    header were both unverified: Hearth could have been calling the wrong path
    with no credential and the only symptom in production would have been a
    silent, permanent fall back to the rules.
    """
    configure()
    STATE.update(status=200, reply={"beliefs": []})
    ex.llm_extract("keep it at 19", NAMES)
    assert STATE["last_path"] == "/chat/completions", STATE["last_path"]
    assert STATE["last_headers"]["authorization"] == "Bearer test-key", \
        STATE["last_headers"].get("authorization")

    # A base URL with a trailing slash must not become a doubled one.
    configure(base=BASE + "/")
    STATE.update(status=200, reply={"beliefs": []})
    ex.llm_extract("keep it at 19", NAMES)
    assert STATE["last_path"] == "/chat/completions", STATE["last_path"]

    # And the model has to be named even when the deployment does not name one,
    # since an empty model is a request every provider rejects.
    configure(model=None)
    STATE.update(status=200, reply={"beliefs": []})
    ex.llm_extract("keep it at 19", NAMES)
    assert STATE["last_request"]["model"], STATE["last_request"]
    assert STATE["last_request"]["messages"][1]["role"] == "user", \
        STATE["last_request"]["messages"]
    print("PASS the model is asked at the right path with the right credential")


def test_the_models_answer_is_the_one_that_is_used():
    """The fallback is what makes this path safe and it is also what hides it.
    Every other test here uses a sentence the rules can parse, so a model path
    that failed and fell back returned the right answer anyway and the test
    passed. This one asks about a sentence where the two disagree.
    """
    configure()
    STATE.update(status=200, reply={"beliefs": [
        {"domain": "shopping", "slot": "coffee", "value": "Illy",
         "scope": None, "context": None}]})
    out = ex.llm_extract("keep it at 19", NAMES)
    assert len(out) == 1 and out[0]["domain"] == "shopping", \
        f"the rules answered, not the model: {out}"
    assert out[0]["value"] == "Illy", out
    print("PASS the model's answer is the one that is used, not the rules'")


def test_a_half_configured_model_is_never_called_at_all():
    """Half-configured is the state a deployment is actually found in: the URL
    set, the key forgotten. Calling out anyway sends the household's sentences
    to a third party with an empty credential, and gets a 401 in return, so it
    leaks and does not even work.

    This test used to watch the stub and pass for a reason that had nothing to
    do with the guard it is named after. httpx refuses to put `Bearer ` on the
    wire at all, that refusal is swallowed by the fall back that exists for
    network failures, and the stub therefore saw no request whichever way the
    condition was written. `base and key` could be loosened to `base or key`
    and every test in this file stayed green. The attempt is now watched one
    layer further down, where nothing else can quietly prevent it.
    """
    import httpx

    tried = []
    real_post = httpx.post

    def watched(url, **kw):
        tried.append(url)
        return real_post(url, **kw)

    httpx.post = watched
    try:
        configure(key="")
        out = ex.llm_extract("keep it at 19", NAMES)
        assert tried == [], f"it called the model with no key: {tried}"
        assert out and out[0]["value"] == "19", out

        # The mirror of it, a key with nowhere to send it, which is what a
        # deployment looks like the moment the endpoint is renamed.
        configure(base="")
        out = ex.llm_extract("keep it at 19", NAMES)
        assert tried == [], f"it called the model with no endpoint: {tried}"
        assert out and out[0]["value"] == "19", out

        # And fully configured it does call, so the two assertions above are
        # about the guard rather than about a path that never runs at all.
        configure()
        STATE.update(status=200, reply={"beliefs": []})
        ex.llm_extract("keep it at 19", NAMES)
        assert len(tried) == 1, tried
    finally:
        httpx.post = real_post
    print("PASS a half configured model is never called at all")


def test_the_system_prompt_asks_for_the_shape_the_parser_expects():
    """The prompt is the contract with the model, and the parser below it reads
    exactly three fields. If they ever stop matching, every extraction comes
    back empty and the household silently stops learning anything.
    """
    for field in ("domain", "slot", "value", "scope", "context", "beliefs"):
        assert field in ex.SYSTEM, field
    assert "JSON" in ex.SYSTEM, ex.SYSTEM
    print("PASS the system prompt asks for the shape the parser expects")


def teardown_module(module=None):
    """Under pytest the model settings must not outlive this file: left set,
    every later suite in the same process saw a configured model and the
    planner and extractor stopped behaving like the defaults they test."""
    SRV.shutdown()
    for k in ("HEARTH_LLM_BASE_URL", "HEARTH_LLM_API_KEY", "HEARTH_LLM_MODEL"):
        os.environ.pop(k, None)


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
