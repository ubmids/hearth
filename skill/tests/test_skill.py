"""The classic Alexa skill, end to end, against a running Hearth.

Starts a real Hearth (uvicorn, its own port and data dir, HEARTH_SKILL_TOKEN
set) and drives the skill's real Lambda entry point with the request envelopes
Alexa sends: the same JSON shape, intents and slots filled as Alexa's NLU would
fill them, session attributes carried from one turn to the next as Alexa
carries them. Every reply is checked against what Hearth itself recorded for
that call, so "the skill speaks Hearth's text verbatim" is asserted, not said.

    pip install -r requirements.txt ask-sdk-core
    python3 skill/tests/test_skill.py          # or: pytest skill/tests
"""
import atexit
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "skill")
sys.path.insert(0, os.path.join(SKILL, "lambda"))

TOKEN = "skill-test-" + "x" * 32
TZ = "America/New_York"
_server = {}


def hearth_url() -> str:
    """One real Hearth for the whole module, started on first use."""
    if "url" in _server:
        return _server["url"]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    data = tempfile.mkdtemp(prefix="hearth-skill-")
    env = {**os.environ, "HEARTH_SKILL_TOKEN": TOKEN, "HEARTH_TZ": TZ,
           "HEARTH_ISSUER": url, "HEARTH_DATA": os.path.join(data, "h.json")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "hearth.app:app",
                             "--host", "127.0.0.1", "--port", str(port),
                             "--log-level", "warning"], cwd=ROOT, env=env)
    atexit.register(proc.terminate)
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/healthz", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Hearth did not start")
    os.environ.update({"HEARTH_URL": url, "HEARTH_TOKEN": TOKEN,
                       "HEARTH_DEFAULT_SPEAKER": "Rose", "HEARTH_CARED_FOR": "Mom",
                       "HEARTH_DEVICES": json.dumps({"toms-echo-dot": "Tom",
                                                     "adas-phone": "Ada"}),
                       "HEARTH_PEOPLE": json.dumps({"amzn1.ask.person.GRACE": "Grace"})})
    _server.update(url=url, proc=proc)
    return url


def skill():
    hearth_url()
    import lambda_function
    return lambda_function


def envelope(intent=None, slots=None, *, kind="IntentRequest", attrs=None,
             device="kitchen-echo-show", screen=True, person=None, resolved=None):
    system = {"application": {"applicationId": "amzn1.ask.skill.test"},
              "user": {"userId": "amzn1.ask.account.test"},
              "device": {"deviceId": device, "supportedInterfaces": (
                  {"Alexa.Presentation.APL": {"runtime": {"maxVersion": "2023.3"}}}
                  if screen else {})},
              "apiEndpoint": "https://api.amazonalexa.com"}
    if person:
        system["person"] = {"personId": person}
    request = {"type": kind, "requestId": "amzn1.echo-api.request.t",
               "timestamp": "2026-10-14T00:00:00Z", "locale": "en-US"}
    if intent:
        sl = {}
        for k, v in (slots or {}).items():
            sl[k] = {"name": k, "value": v, "confirmationStatus": "NONE"}
            if resolved and k in resolved:
                sl[k]["resolutions"] = {"resolutionsPerAuthority": [{
                    "authority": "amzn1.er-authority.echo-sdk.test.MEDICATION",
                    "status": {"code": "ER_SUCCESS_MATCH"},
                    "values": [{"value": {"name": resolved[k], "id": "x"}}]}]}
        request["intent"] = {"name": intent, "confirmationStatus": "NONE", "slots": sl}
    return {"version": "1.0",
            "session": {"new": False, "sessionId": "amzn1.echo-api.session.t",
                        "application": {"applicationId": "amzn1.ask.skill.test"},
                        "attributes": attrs or {},
                        "user": {"userId": "amzn1.ask.account.test"}},
            "context": {"System": system}, "request": request}


class Turn:
    def __init__(self, raw):
        self.raw = raw
        r = raw["response"]
        self.speech = re.sub(r"</?speak>", "", r["outputSpeech"]["ssml"]).strip()
        self.directives = r.get("directives") or []
        self.attrs = raw.get("sessionAttributes") or {}
        self.ends = r.get("shouldEndSession")

    @property
    def card(self):
        d = next((d for d in self.directives
                  if d["type"] == "Alexa.Presentation.APL.RenderDocument"), None)
        return d and d["datasources"]["payload"]["card"]


def say(intent=None, slots=None, **kw) -> Turn:
    return Turn(skill().lambda_handler(envelope(intent, slots, **kw), None))


def record():
    """Hearth's own record for the skill's household, newest first."""
    req = urllib.request.Request(hearth_url() + "/api/state",
                                 headers={"Authorization": f"Bearer {TOKEN}"})
    return json.load(urllib.request.urlopen(req))["record"]["entries"]


def verbatim(turn: Turn, tool: str):
    """The reply is exactly the text Hearth recorded answering that call."""
    entry = next(e for e in record() if e["tool"] == tool)
    said = re.sub(r"\s*\[[0-9a-f]{6,}\]", "", entry["summary"]).strip()
    assert turn.speech.startswith(said[:200]), (turn.speech, said)
    return entry


def next_thursday() -> str:
    from zoneinfo import ZoneInfo
    d = dt.datetime.now(ZoneInfo(TZ)).date()
    return (d + dt.timedelta(days=(3 - d.weekday()) % 7 or 7)).isoformat()


# --- the nine demo scenes, on a real skill handler --------------------------
def test_the_household_on_a_real_skill_handler():
    url = hearth_url()
    hello = say(kind="LaunchRequest")
    assert hello.speech == "Hearth here. Go ahead, Rose.", hello.speech

    # 1. Rose, kitchen Echo Show: the hero.
    t = say("GiveDoseIntent", {"medication": "blood thinner"})
    assert t.speech.startswith("Hold on, Rose. Grace gave you today's warfarin at "), t.speech
    assert t.speech.endswith("Your warfarin is once a day, so not another until tomorrow."), t.speech
    e = verbatim(t, "give_dose")
    assert e["outcome"] == "refused" and e["session"] == t.attrs["mcp_session"], e
    assert t.card["title"] == "Already taken today" and t.card["toneColor"] == "#ff6b4a"
    assert f"record #{e['seq']} refused" in t.card["source"], t.card["source"]
    attrs = t.attrs

    # 2-3. Tom, his Echo Dot (no screen): what he missed, and why.
    t = say("CatchUpIntent", device="toms-echo-dot", screen=False)
    assert "I stopped her" in t.speech, t.speech
    assert t.directives == [], "drew a card on a device with no screen"
    verbatim(t, "catch_up")
    t = say("WhyIntent", device="toms-echo-dot", screen=False, attrs=t.attrs)
    assert t.speech.startswith("I stopped a second warfarin for Mom because Ada set it"), t.speech
    verbatim(t, "why")

    # 4. Ada, her phone: one request, every step.
    t = say("ArrangeIntent", {"appointment": "cardiology", "day": next_thursday(),
                              "time": "10:00"}, device="adas-phone")
    assert t.speech.startswith("Done. Mom's cardiology is now Thursday at 10:00 am. "
                               "Tom is taking Mom, since Tom does Thursdays."), t.speech
    verbatim(t, "arrange")
    assert t.card["title"].startswith("Mom's cardiology"), t.card

    # 5-6. Grace (recognised by voice): reorder, then "yes" pays the sandbox.
    t = say("ReorderIntent", {"item": "warfarin"}, person="amzn1.ask.person.GRACE",
            attrs=attrs)
    assert t.speech.endswith("Shall I place the order?"), t.speech
    assert t.attrs["checkout"]["line_items"][0]["item"]["id"] == "rx-warfarin-5mg-30"
    verbatim(t, "reorder")
    t = say("AMAZON.YesIntent", person="amzn1.ask.person.GRACE", attrs=t.attrs)
    assert t.speech == ("Done. Warfarin 5 mg, 30 tablets is ordered, 12 dollars 40, "
                        "arriving tomorrow. I've told the family."), t.speech
    assert "checkout" not in t.attrs
    assert t.card["footer"] == "Sandbox merchant: no payment was taken"
    assert record()[0]["tool"] == "checkout.complete"

    # 7. Tom: coffee, settled by authority.
    t = say("CanHaveIntent", {"thing": "coffee"}, device="toms-echo-dot", screen=False)
    assert t.speech.startswith("Mom's coffee stops at three."), t.speech
    assert "Ada has the say" in t.speech
    verbatim(t, "whats_true")

    # 8. Ada: a sentence no intent matches goes to Hearth's planner.
    t = say("RememberIntent", {"statement": "mom finished the antibiotics"},
            device="adas-phone")
    assert t.speech.startswith("Understood, the antibiotics are over."), t.speech
    verbatim(t, "remember")

    # 9. The record, from the server.
    t = say("RecordIntent", device="adas-phone")
    assert re.match(r"\d+ calls on the record, 1 refused, and it matches the server's signed checkpoint", t.speech), t.speech
    verbatim(t, "record")
    print(f"PASS the nine scenes on a real skill handler against {url}")


def test_a_brand_name_resolved_by_alexa_still_reaches_the_refusal():
    t = say("GiveDoseIntent", {"medication": "coumadin"}, resolved={"medication": "warfarin"})
    assert t.speech.startswith("Hold on, Rose."), t.speech
    t = say("GiveDoseIntent", {"medication": "warfarin sodium"})
    assert t.speech.startswith("Hold on, Rose."), t.speech
    print("PASS Coumadin and warfarin sodium are refused through the skill")


def test_this_is_tom_changes_who_is_speaking_for_the_session():
    t = say("IAmIntent", {"name": "tom"})
    assert t.speech == "Hello, Tom." and t.attrs["speaker"] == "Tom"
    t = say("RememberIntent", {"statement": "mom's warfarin is twice a day"}, attrs=t.attrs)
    assert t.speech.startswith("Noted, Tom. Ada has the say over Mom's warfarin, so it "
                               "stays once a day until Ada confirms."), t.speech
    print("PASS 'this is Tom' is who the next call is made for")


def test_a_lost_session_is_reopened_without_the_user_noticing():
    t = say("CheckDoseIntent", {"medication": "warfarin"},
            attrs={"mcp_session": "0" * 32})
    assert t.speech.startswith("Yes. Grace gave Mom warfarin"), t.speech
    assert t.attrs["mcp_session"] != "0" * 32
    print("PASS a session Hearth no longer knows is reopened")


def test_when_hearth_cannot_be_reached_the_dose_waits():
    """The safe answer to "can I take it" when the record is out of reach is
    "not until someone checks", never a guess."""
    lf = skill()
    old = os.environ["HEARTH_URL"], os.environ["HEARTH_TOKEN"]
    try:
        os.environ["HEARTH_URL"] = "http://127.0.0.1:9"
        t = Turn(lf.lambda_handler(envelope("GiveDoseIntent", {"medication": "warfarin"}), None))
        assert t.speech == ("I can't reach Hearth to check today's doses, so please "
                            "don't take it until someone has checked."), t.speech
        os.environ["HEARTH_URL"], os.environ["HEARTH_TOKEN"] = old[0], "wrong-" + "y" * 32
        t = Turn(lf.lambda_handler(envelope("GiveDoseIntent", {"medication": "warfarin"}), None))
        assert t.speech.startswith("I can't reach Hearth to check today's doses"), t.speech
    finally:
        os.environ["HEARTH_URL"], os.environ["HEARTH_TOKEN"] = old
    print("PASS no Hearth, or the wrong credential: the dose waits")


def test_the_skill_never_reads_out_a_reference_or_markup():
    t = say("RememberIntent", {"statement": "no coffee for mom after three"},
            device="adas-phone")
    assert not re.search(r"\[[0-9a-f]{6,}\]|[<>&]", t.speech), t.speech
    print("PASS belief references and markup never reach the speaker")


# --- the interaction model ---------------------------------------------------
def model():
    with open(os.path.join(SKILL, "skill-package", "interactionModels", "custom",
                           "en-US.json")) as f:
        return json.load(f)["interactionModel"]["languageModel"]


def test_every_intent_has_a_handler_and_every_slot_a_type():
    lm = model()
    lf = skill()
    src = open(os.path.join(SKILL, "lambda", "lambda_function.py")).read()
    types = {t["name"] for t in lm["types"]}
    seen = set()
    for i in lm["intents"]:
        assert f'"{i["name"]}"' in src, f"no handler for {i['name']}"
        for s in i.get("slots", []):
            assert s["type"].startswith("AMAZON.") or s["type"] in types, s
            assert "{" + s["name"] + "}" in " ".join(i["samples"]), (i["name"], s)
        for u in i.get("samples", []):
            assert u not in seen, f"sample used twice: {u}"
            assert re.fullmatch(r"[a-z' {}]+", u), f"invalid sample: {u!r}"
            seen.add(u)
    assert lm["invocationName"] == lm["invocationName"].lower()
    assert set(lf.INTENTS) <= {i["name"] for i in lm["intents"]}
    print(f"PASS {len(lm['intents'])} intents, {len(seen)} samples, all handled")


def test_every_demo_line_matches_an_intent_sample():
    """The nine lines from the simulator's script, as Alexa would hear them,
    each land on the intent the scene needs."""
    src = open(os.path.join(ROOT, "hearth", "web", "alexa.html")).read()
    block = src[src.index("const SCRIPT = ["):src.index("];", src.index("const SCRIPT = ["))]
    lines = [s for _, s in re.findall(r'\["(\w+)", "([^"]+)"\]', block)]
    want = ["GiveDoseIntent", "CatchUpIntent", "WhyIntent", "ArrangeIntent",
            "ReorderIntent", "AMAZON.YesIntent", "CanHaveIntent", "RememberIntent",
            "RecordIntent"]
    lm = model()
    for line, intent in zip(lines, want):
        heard = re.sub(r"^alexa,? ", "", line.lower())
        heard = re.sub(r"[.,?!]", "", heard).replace("10", "ten")
        if intent == "AMAZON.YesIntent":
            assert heard in ("yes go ahead",), heard
            continue
        samples = next(i for i in lm["intents"] if i["name"] == intent)["samples"]
        pats = [re.sub(r"\\{\w+\\}", ".+", re.escape(s)) for s in samples]
        assert any(re.fullmatch(p, heard) for p in pats), (intent, heard)
    print("PASS every demo line has a sample in the interaction model")


if __name__ == "__main__":
    fns = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"\nall green ({len(fns)} skill tests)")
