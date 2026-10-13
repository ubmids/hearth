"""The care household, the honest ledger, and what a screen draws.

Each test is a situation in a home looking after an elderly parent where being
wrong costs something: a second blood thinner, a sibling who was never told, a
charge nobody approved, an assistant that says it checked when it did not.
"""
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HEARTH_TZ", "America/New_York")

from fastapi.testclient import TestClient

from hearth import care as carelib
from hearth.app import create_app
from hearth.extract import detect_context_end, rule_extract
from hearth.mcp import APP_MIME, CARD_URI, TOOLS
from hearth.trace import Trace

ISSUER = "https://hearth.test"
RESOURCE = f"{ISSUER}/mcp"


class House:
    """One care household behind the real HTTP surface, one MCP session."""

    def __init__(self, data_path=None, subject="care-house"):
        self.app = create_app(issuer=ISSUER, resource=RESOURCE, seed="care",
                              data_path=data_path)
        self.c = TestClient(self.app)
        self.tok = self.app.state.auth.issue_for_testing(subject=subject)
        self.subject = subject
        self.sid = self.initialize()

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.tok}", "Mcp-Session-Id": self.sid}

    def initialize(self):
        r = self.c.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                                      "method": "initialize", "params": {}},
                        headers={"Authorization": f"Bearer {self.tok}"})
        return r.headers["mcp-session-id"]

    def rpc(self, method, params=None):
        return self.c.post("/mcp", json={"jsonrpc": "2.0", "id": 7, "method": method,
                                         "params": params or {}},
                           headers=self.headers).json()

    def call(self, name, **args):
        return self.rpc("tools/call", {"name": name, "arguments": args})["result"]

    def say(self, name, **args):
        return self.call(name, **args)["content"][0]["text"]

    @property
    def home(self):
        return self.app.state.home_for(self.subject)

    @property
    def server(self):
        return self.home[2]


# --- the hero: a second dose is refused, by the server ---------------------
def test_a_second_warfarin_is_refused_and_the_refusal_is_on_the_record():
    house = House()
    reply = house.say("give_dose", medication="my blood thinner", given_by="Rose")
    assert reply.startswith("Hold on, Rose."), reply
    assert "Grace gave you today's warfarin" in reply, reply
    assert "once a day" in reply and "not another until tomorrow" in reply, reply
    # Nothing was given: the book still holds only Grace's morning dose.
    assert len(house.server.care.book.doses) == 1
    # The ledger has it as Hearth's own refusal, not something the agent said.
    a = house.home[1].actions[-1]
    assert a.outcome == "refused" and a.source == "hearth", a.to_dict()
    # And the record of calls has it, marked refused, whatever the agent does next.
    e = house.server.trace.entries[-1]
    assert e.tool == "give_dose" and e.outcome == "refused", e.to_dict()
    assert e.action == a.id
    print("PASS a second warfarin is refused by the server and recorded:", reply)


def test_why_names_the_rule_who_set_it_and_the_dose_already_given():
    house = House()
    house.say("give_dose", medication="warfarin", given_by="Mom")
    why = house.say("why")
    assert "stopped a second warfarin for Mom" in why, why
    assert "Ada set it" in why and "once a day" in why, why
    # Read back to Tom later, so in the third person, not "you".
    assert "Grace gave Mom today's warfarin" in why, why
    print("PASS why:", why)


def test_a_first_dose_is_logged_and_the_next_one_refused():
    house = House()
    house.server.care.book.doses.clear()
    first = house.say("give_dose", medication="warfarin", given_by="Grace")
    assert first.startswith("Logged."), first
    assert "That is all for today" in first, first
    second = house.say("give_dose", medication="warfarin", given_by="Tom")
    assert second.startswith("Hold on."), second
    assert "Grace gave Mom today's warfarin" in second, second
    print("PASS first dose logged, second refused")


def test_a_medicine_with_no_rule_is_logged_and_says_it_cannot_check():
    house = House()
    reply = house.say("give_dose", medication="paracetamol", given_by="Grace")
    assert reply.startswith("Logged."), reply
    assert "cannot check the limit" in reply, reply
    print("PASS an unknown medicine is logged with a warning")


def test_check_dose_answers_who_and_when():
    house = House()
    reply = house.say("check_dose", medication="her blood thinner", asked_by="Tom")
    assert reply.startswith("Yes. Grace gave Mom warfarin"), reply
    assert "not another until tomorrow" in reply, reply
    house.server.care.book.doses.clear()
    reply = house.say("check_dose", medication="warfarin")
    assert reply.startswith("No, Mom has not had warfarin today."), reply
    assert "due at nine" in reply, reply
    print("PASS check_dose")


# --- the honest ledger -----------------------------------------------------
def test_every_tool_call_is_recorded_by_the_server_including_failures():
    house = House()
    n0 = len(house.server.trace.entries)
    house.say("whats_true", domain="diet", slot="coffee_cutoff", about="Mom")
    house.rpc("tools/call", {"name": "arrange", "arguments": {
        "what": "dentist", "when": "the twelfth of never", "asked_by": "Ada"}})
    house.rpc("tools/call", {"name": "no_such_tool", "arguments": {}})
    entries = house.server.trace.entries[n0:]
    assert [e.tool for e in entries] == ["whats_true", "arrange", "no_such_tool"]
    assert [e.outcome for e in entries] == ["ok", "error", "error"]
    # Reads are computed from the resolution, not claimed: both coffee rules.
    assert len(entries[0].reads) == 2, entries[0].reads
    assert all(e.session == house.sid for e in entries)
    ok, bad = house.server.trace.verify()
    assert ok and bad is None
    print("PASS every call is recorded, failures included")


def test_editing_or_removing_a_record_entry_breaks_the_chain():
    t = Trace()
    for i in range(5):
        t.append(tool="whats_true", args={"i": i}, outcome="ok", summary=str(i))
    assert t.verify() == (True, None)
    t.entries[2].summary = "something nicer"
    assert t.verify() == (False, 3)
    t.entries[2].summary = "2"
    assert t.verify() == (True, None)
    del t.entries[1]
    assert t.verify()[0] is False
    print("PASS the record is tamper evident")


def test_a_reported_action_says_whether_the_agent_asked_first():
    house = House()
    # Reported with no whats_true beforehand in this session.
    house.say("did", what="set the thermostat to 80", domain="thermostat",
              slot="target")
    a = house.home[1].actions[-1]
    assert a.source == "reported" and a.checked is False, a.to_dict()
    why = house.say("why", domain="thermostat")
    assert "I was not asked before it was taken" in why, why
    # Asked first, in the same session: checked.
    house.say("whats_true", domain="thermostat", slot="target")
    reply = house.say("did", what="set the thermostat to 72", domain="thermostat",
                      slot="target")
    assert house.home[1].actions[-1].checked is True
    assert "not asked" not in reply
    # A different session asking does not count for this one.
    other = house.initialize()
    house.sid = other
    house.say("did", what="set the thermostat to 72", domain="thermostat",
              slot="target")
    assert house.home[1].actions[-1].checked is False
    print("PASS a reported action is checked against the server's own record")


def test_the_record_survives_a_restart_and_still_verifies():
    tmp = tempfile.mkdtemp(prefix="hearth-care-")
    try:
        path = os.path.join(tmp, "house")
        house = House(data_path=path)
        house.say("give_dose", medication="warfarin", given_by="Rose")
        house.say("check_dose", medication="warfarin")
        again = House(data_path=path)
        entries = again.server.trace.entries
        assert [e.tool for e in entries][-2:] == ["give_dose", "check_dose"]
        assert again.server.trace.verify() == (True, None)
        # The care books came back too: the dose, and the refusal in the ledger.
        assert len(again.server.care.book.doses) == 1
        assert again.home[1].actions[-1].outcome == "refused"
        reply = again.say("record", limit=3)
        assert "the chain is intact" in reply and "1 refused" in reply, reply
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("PASS the record survives a restart")


# --- several services, one request ------------------------------------------
def test_arrange_moves_the_appointment_and_does_everything_that_follows():
    house = House()
    result = house.call("arrange", what="cardiology", when="Thursday at 10am",
                        asked_by="Ada")
    speech = result["content"][0]["text"]
    steps = result["structuredContent"]["steps"]
    services = [s["service"] for s in steps]
    assert services[:4] == ["calendar", "rota", "rides", "rides"], services
    assert services[-1] == "board", services
    # Spoken short; the card carries every step.
    assert speech.startswith("Done. Mom's cardiology is now Thursday at 10:00 am."), speech
    assert "Tom is taking Mom, since Tom does Thursdays" in speech, speech
    assert "cancelled the old ride" in speech and "9:15 am" in speech, speech
    lines = [s["line"] for s in steps]
    assert "Moved Mom's cardiology from Tuesday 2:00 pm to Thursday 10:00 am." in lines
    assert "Cancelled the Tuesday ride (Hearth sandbox rides)." in lines, lines
    card = result["structuredContent"]["card"]
    assert card["pattern"] == "list" and len(card["items"]) == len(steps)
    book = house.server.care.book
    appt = next(a for a in book.appointments if a["what"] == "cardiology")
    assert carelib.local(appt["at"]).strftime("%A %H:%M") == "Thursday 10:00"
    assert appt["escort"] == "Tom"
    assert [r["status"] for r in book.rides] == ["cancelled", "booked"]
    assert "Tom is taking Mom" in book.board[-1]["text"]
    # Every step is its own ledger action, bound to the rule that decided it.
    rota = next(a for a in house.home[1].actions if a.domain == "rota")
    assert rota.resolution.winner.holder == house.home[0].member_named("Tom").id
    print("PASS one request, five services:", speech)


def test_arrange_flags_a_day_nobody_covers():
    house = House()
    result = house.call("arrange", what="podiatrist", when="Saturday at 11am",
                        asked_by="Ada")
    rota = next(s for s in result["structuredContent"]["steps"]
                if s["service"] == "rota")
    assert rota["status"] == "needs_attention", rota
    assert "Nobody is on the rota for Saturdays" in rota["line"]
    print("PASS a day nobody covers is flagged, not guessed")


def test_arrange_reminds_about_a_dose_due_during_the_trip():
    house = House()
    result = house.call("arrange", what="eye clinic", when="Friday at 9:30am",
                        asked_by="Ada")
    doses = [s for s in result["structuredContent"]["steps"] if s["service"] == "doses"]
    assert doses and "warfarin is due at 9:00 am" in doses[0]["line"], doses
    print("PASS a dose due during the trip is called out")


# --- purchases ---------------------------------------------------------------
def pay(house, hint, key="k1", buyer="Grace"):
    """What Alexa+ does on "yes": create the session from the tool's hint,
    then complete it, as its checkout contract describes."""
    h = {"Authorization": f"Bearer {house.tok}", "UCP-Agent": 'profile="test"',
         "Request-Id": "req-1"}
    made = house.c.post("/checkout-sessions", headers=h, json={
        "line_items": hint["line_items"], "buyer": {"first_name": buyer},
        "context": {"hearth_quote": hint["quote"]}})
    sess = made.json()
    done = house.c.post(f"/checkout-sessions/{sess['id']}/complete",
                        headers={**h, "Idempotency-Key": key}, json={})
    return made, done


def test_a_refill_is_priced_by_the_tool_and_paid_through_checkout():
    house = House()
    r = house.call("reorder", item="warfarin", asked_by="Grace")
    sc = r["structuredContent"]
    assert sc["approved"] is True and sc["total"] == 1240
    assert sc["card"]["cta"]["message"] == "Pay for this order"
    assert sc["checkout"]["line_items"] == [{"item": {"id": "rx-warfarin-5mg-30"},
                                             "quantity": 1}]
    assert "Shall I place the order?" in r["content"][0]["text"]
    # The tool charged nothing and opened nothing at the merchant.
    assert house.server.care.book.checkouts == []
    made, done = pay(house, sc["checkout"])
    assert made.status_code == 201 and made.json()["status"] == "ready_for_complete"
    assert made.headers["cache-control"] == "no-store"
    assert made.headers["request-id"] == "req-1"
    assert "com.amazon.payments.network_token" in made.json()["ucp"]["payment_handlers"]
    order = done.json()
    assert done.status_code == 200 and order["status"] == "completed" and order["order_id"]
    # The same Idempotency-Key replays the result; never a second order.
    again = house.c.post(f"/checkout-sessions/{order['id']}/complete",
                         headers={"Authorization": f"Bearer {house.tok}",
                                  "Idempotency-Key": "k1"}).json()
    assert again["order_id"] == order["order_id"]
    tools = [e.tool for e in house.server.trace.entries]
    assert tools[-3:] == ["checkout.create", "checkout.complete", "checkout.complete"]
    assert "paid through Alexa+ checkout" in house.home[1].actions[-1].what
    # A second refill within the week is flagged as a likely duplicate.
    r2 = house.call("reorder", item="warfarin", asked_by="Tom")
    assert "already ordered" in r2["content"][0]["text"], r2["content"][0]["text"]
    print("PASS a refill is priced by the tool and paid through checkout")


def test_a_refill_card_shows_the_rules_that_held():
    # The screen shows what was checked and passed, not only what failed.
    house = House()
    card = house.call("reorder", item="warfarin", asked_by="Grace")["structuredContent"]["card"]
    checked = [i["detail"] for i in card["items"] if i["label"] == "Checked"]
    assert checked == ["Within Ada's $50 limit",
                       "Not ordered in the last week"], checked
    assert card["items"][-1]["label"] == "Paid through Alexa+"
    # Over the limit: no "within the limit", and no payment line either.
    over = house.call("reorder", item="ensure", asked_by="Tom", quantity=2)
    labels = [(i["label"], i["detail"]) for i in over["structuredContent"]["card"]["items"]]
    assert ("Error", over["structuredContent"]["card"]["items"][0]["detail"]) == labels[0]
    assert not any("Within" in d for _, d in labels), labels
    assert not any(l == "Paid through Alexa+" for l, _ in labels), labels
    print("PASS a refill card shows the rules that held")


def test_spending_over_the_limit_needs_the_person_who_set_it():
    house = House()
    r = house.call("reorder", item="ensure", asked_by="Tom", quantity=2)
    sc = r["structuredContent"]
    assert sc["approved"] is False
    assert "Ada has to approve it" in r["content"][0]["text"]
    assert "cta" not in sc["card"]
    # Alexa+ opening a checkout for it anyway gets an incomplete session, and
    # completing that is a business failure: HTTP 200, reason in messages[].
    made, done = pay(house, sc["checkout"], buyer="Tom")
    assert made.json()["status"] == "incomplete"
    assert done.status_code == 200 and done.json()["status"] == "incomplete"
    assert any(m["code"] == "not_ready" for m in done.json()["messages"])
    ok = house.call("reorder", item="ensure", asked_by="Ada", quantity=2)
    assert ok["structuredContent"]["approved"] is True
    made, done = pay(house, ok["structuredContent"]["checkout"], buyer="Ada", key="k2")
    assert done.json()["status"] == "completed"
    print("PASS over the limit needs Ada")


def test_checkout_endpoints_need_a_bearer_and_publish_a_profile():
    house = House()
    assert house.c.post("/checkout-sessions/x/complete").status_code == 401
    assert "www-authenticate" not in house.c.post(
        "/checkout-sessions", json={}).headers
    prof = house.c.get("/.well-known/ucp").json()
    assert prof["sandbox"] is True
    assert "dev.ucp.shopping.checkout" in prof["ucp"]["capabilities"]
    h = {"Authorization": f"Bearer {house.tok}"}
    made = house.c.post("/checkout-sessions", headers=h, json={
        "line_items": [{"item": {"id": "rx-warfarin-5mg-30", "price": 1},
                        "quantity": 1}]})
    # The merchant owns the price: a price in the request is ignored.
    assert made.status_code == 201 and made.json()["totals"][-1]["amount"] == 1240
    sid = made.json()["id"]
    up = house.c.put(f"/checkout-sessions/{sid}", headers=h, json={
        "line_items": [{"item": {"id": "rx-warfarin-5mg-30"}, "quantity": 2}]}).json()
    assert up["id"] == sid and up["totals"][-1]["amount"] == 2480
    assert house.c.get(f"/checkout-sessions/{sid}", headers=h).json()["line_items"][0]["quantity"] == 2
    gone = house.c.post(f"/checkout-sessions/{sid}/cancel", headers=h).json()
    assert gone["status"] == "canceled"
    bad = house.c.post("/checkout-sessions", headers=h, json={
        "line_items": [{"item": {"id": "rx-nonsense"}}]})
    assert bad.status_code == 400
    print("PASS checkout endpoints follow the contract")


# --- memory across sessions ------------------------------------------------
def test_catch_up_tells_a_sibling_what_happened_since_they_last_asked():
    house = House()
    house.say("give_dose", medication="warfarin", given_by="Rose")
    house.say("arrange", what="cardiology", when="Thursday at 10am", asked_by="Ada")
    # Tom, from his own Echo, two states away: a new MCP session.
    house.sid = house.initialize()
    reply = house.say("catch_up", person="Tom")
    assert reply.startswith("Since you last checked in"), reply
    assert "Mom went to take a second warfarin and I stopped her" in reply, reply
    assert "Tom is taking Mom" in reply, reply
    assert "A note from Grace. Mom slept well" in reply, reply
    assert "From " not in reply and ": " not in reply, reply
    # Asking again straight away: nothing new, because Hearth remembers he asked.
    again = house.say("catch_up", person="Tom")
    assert again.startswith("Nothing new since you last checked in"), again
    print("PASS catch up across sessions:", reply)


# --- what a screen draws -----------------------------------------------------
def test_tools_name_their_view_and_the_view_is_served_as_an_mcp_app():
    house = House()
    tools = {t["name"]: t for t in house.rpc("tools/list")["result"]["tools"]}
    for name in ("give_dose", "check_dose", "arrange", "reorder", "catch_up",
                 "why", "whats_true", "record"):
        assert tools[name]["_meta"]["ui"]["resourceUri"] == CARD_URI, name
    for t in tools.values():
        assert "readOnlyHint" in t["annotations"], t["name"]
    assert tools["check_dose"]["annotations"]["readOnlyHint"] is True
    assert tools["reorder"]["annotations"]["openWorldHint"] is True
    assert CARD_URI.startswith("ui://hearth/card-") and CARD_URI.endswith(".html")
    listed = house.rpc("resources/list")["result"]["resources"]
    assert listed[0]["uri"] == CARD_URI and listed[0]["mimeType"] == APP_MIME
    read = house.rpc("resources/read", {"uri": CARD_URI})["result"]["contents"][0]
    assert read["mimeType"] == APP_MIME and "ui/notifications/tool-result" in read["text"]
    missing = house.rpc("resources/read", {"uri": "ui://nope"})
    assert missing["error"]["code"] == -32002
    init = house.c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                        headers={"Authorization": f"Bearer {house.tok}"}).json()
    assert "resources" in init["result"]["capabilities"]
    print("PASS the view is an MCP App, named on the tool and the result")


def test_a_result_carries_its_card_its_speech_and_its_record_receipt():
    house = House()
    r = house.call("give_dose", medication="warfarin", given_by="Rose")
    sc = r["structuredContent"]
    assert r["_meta"]["ui"]["resourceUri"] == CARD_URI
    assert sc["card"]["tone"] == "stop" and sc["card"]["title"] == "Already taken today"
    assert sc["speech"] == r["content"][0]["text"]
    last = house.server.trace.entries[-1]
    assert sc["record"] == {"seq": last.seq, "hash": last.hash[:12],
                            "outcome": "refused"}
    # A voice-only reply carries no formatting a speaker would read out.
    assert "|" not in r["content"][0]["text"] and "*" not in r["content"][0]["text"]
    print("PASS a result carries card, speech and receipt")


# --- the household and its words -----------------------------------------
def test_the_care_household_has_the_shape_the_demo_needs():
    house = House()
    h = house.home[0]
    by = {m.name: m for m in h.members.values()}
    assert set(by) == {"Mom", "Ada", "Tom", "Grace"}
    assert by["Mom"].answers_to("Rose") and by["Mom"].answers_to("mum")
    assert by["Ada"].authority_over("medication.warfarin") >= 100
    assert by["Grace"].role == "carer"
    coffee = house.say("whats_true", domain="diet", slot="coffee_cutoff", about="Mom")
    assert coffee.startswith("Mom's coffee stops at three."), coffee
    assert "Tom said six, but Ada has the say" in coffee, coffee
    print("PASS the care household:", coffee)


def test_the_care_sentences_become_beliefs_and_situations_end():
    names = {"Mom": "m", "Rose": "m", "Ada": "a", "Tom": "t"}
    cases = {
        "No coffee for Mom after three": ("diet", "coffee_cutoff", "15:00", "m", None),
        "Mom can have coffee till six, it's fine": ("diet", "coffee_cutoff", "18:00", "m", None),
        "No wine for Mom while she's on the antibiotics":
            ("diet", "alcohol", "none", "m", "the antibiotics"),
        "Mom takes two metformin a day": ("medication.metformin", "per_day", "2", "m", None),
        "I'll take Mom to anything on a Thursday": ("rota", "thursday", "{speaker}", None, None),
        "Up to fifty dollars without asking me": ("purchases", "limit", "50", None, None),
    }
    for said, (d, s, v, scope, ctx) in cases.items():
        got = rule_extract(said, names)
        assert got and (got[0]["domain"], got[0]["slot"], got[0]["value"],
                        got[0]["scope"], got[0]["context"]) == (d, s, v, scope, ctx), (said, got)
    for said in ("Mom finished the antibiotics", "she's done with the antibiotics",
                 "the antibiotics are finished"):
        assert detect_context_end(said, ["the antibiotics"]) == "the antibiotics", said
    house = House()
    reply = house.say("remember", said="Mom finished the antibiotics", speaker="Ada")
    assert reply.startswith("Understood, the antibiotics are over."), reply
    assert "Ada's rule that Mom's alcohol is off limits no longer applies." in reply, reply
    rota = house.say("remember", said="I can do Saturdays", speaker="Tom")
    assert "The Saturday escort is Tom." in rota, rota
    print("PASS care sentences and endings")


def test_times_are_parsed_the_way_people_and_models_pass_them():
    tz = carelib.tz()
    now = datetime(2026, 10, 13, 16, 0, tzinfo=tz).timestamp()     # a Tuesday
    def at(text):
        ts = carelib.parse_when(text, now)
        return carelib.local(ts).strftime("%a %H:%M") if ts else None
    assert at("Thursday at 10am") == "Thu 10:00"
    assert at("thursday at 10") == "Thu 10:00"
    assert at("tomorrow at 2:30pm") == "Wed 14:30"
    assert at("Tuesday at 3") == "Tue 15:00"            # next week, not today
    assert carelib.local(carelib.parse_when("Tuesday", now)).day == 20
    assert at("2026-10-15T10:00:00") == "Thu 10:00"
    assert at("whenever") is None
    assert carelib.when_said(now - 3600, now) == "at 3:00 this afternoon"
    assert carelib.when_said(now - 86400, now) == "yesterday at 4:00 pm"
    print("PASS times")


def test_the_record_counts_in_english():
    house = House()
    house.say("give_dose", medication="warfarin", given_by="Rose")
    one = house.call("record")
    assert one["content"][0]["text"].startswith("1 call on the record, 1 refused"), one
    assert one["structuredContent"]["card"]["title"] == "1 call"
    house.say("check_dose", medication="warfarin", asked_by="Tom")
    two = house.say("record")
    assert two.startswith("3 calls on the record"), two
    print("PASS the record counts in English:", two)


def test_a_sibling_last_checked_in_on_a_real_evening():
    # Tom's last word to the house is seeded on an evening two days back, so
    # "since you last checked in" reads like a call, not a timestamp.
    house = House()
    reply = house.say("catch_up", person="Tom")
    assert "at 7:30 pm" in reply, reply
    print("PASS catch-up names a real evening:", reply[:60])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall green (care, record, visuals)")
