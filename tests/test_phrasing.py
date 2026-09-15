"""The layer that stops the inside of the machine reaching the household.

Hearth thinks in (domain, slot, value) because that is what makes a contest a
dictionary lookup, and every test in test_contest.py is about getting that part
right. This file is about the other half: none of it may show up in front of
anybody. A judge reading `thermostat.target = 19` is being shown a debug view,
and a household would never say it, so the phrasing is as much a part of the
product as the resolver is and is tested the same way.

The tests that matter most are the degrading ones. A house can name a domain
anything it likes, and the phrasing meets domains this file has never heard of
every time somebody speaks.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from hearth import phrasing as p
from hearth.app import create_app

ISSUER = "https://hearth.test"


def console(c, tok, method, path, **body):
    head = {"Authorization": f"Bearer {tok}"}
    if method == "GET":
        return c.get(path, headers=head).json()
    return c.post(path, json=body, headers=head).json()


def house():
    app = create_app(issuer=ISSUER, resource=f"{ISSUER}/mcp", seed=True)
    return TestClient(app), app.state.auth.issue_for_testing(subject="phrasing")


def test_a_setting_reads_as_a_sentence_not_a_slot():
    """The two the rubric would have been read against."""
    assert p.statement("thermostat", "target", "19") == \
        "The thermostat is set to 19 degrees."
    assert p.statement("meals", "dinner", "17:00") == "Dinner is at five."
    assert p.statement("shopping", "coffee", "Sumatra") == "The coffee is Sumatra."
    assert p.describe("thermostat", "target", "19")["title"] == "The thermostat"
    assert p.describe("thermostat", "target", "19")["reading"] == "19°"
    print("PASS a setting reads as a sentence:", p.statement("meals", "dinner", "17:00"))


def test_a_time_is_read_off_a_clock_rather_than_a_field():
    """Dinner is at five, not at 17:00. The quarters are worth saying out loud
    and nothing else is: "twenty-three minutes past seven" is not an improvement
    on 7:23, so the phrasing stops trying at that point rather than getting
    worse than the digits it replaced."""
    assert p.spoken("meals", "dinner", "17:00") == "five"
    assert p.spoken("meals", "dinner", "21:30") == "half past nine"
    assert p.spoken("meals", "dinner", "08:15") == "quarter past eight"
    assert p.spoken("meals", "dinner", "19:45") == "quarter to eight"
    assert p.spoken("meals", "dinner", "07:23") == "7:23"
    assert p.spoken("meals", "dinner", "00:30") == "half past twelve"
    assert p.spoken("meals", "dinner", "12:00") == "twelve"
    # And the short form keeps the half of the day, which words drop.
    assert p.reading("meals", "dinner", "17:00") == "5:00pm"
    assert p.reading("meals", "dinner", "07:00") == "7:00am"
    print("PASS a time is read off a clock")


def test_a_domain_nobody_wrote_phrasing_for_still_speaks():
    """The one that decides whether this layer is safe to ship. A household
    names its own domains, so most of what this file meets after today is
    something nobody wrote a line for, and the failure has to be a plainer
    sentence rather than a KeyError in front of a judge."""
    assert p.statement("greenhouse", "humidity", "60") == \
        "The greenhouse humidity is set to 60."
    # A dotted domain reads from the inside out, because the tail is the
    # specific thing: "the left garage door", not "the garage left door".
    assert p.statement("garage.left", "door", "closed") == \
        "The left garage door is set to closed."
    # A time is still a time in a domain nobody has described.
    assert p.statement("sauna", "booking", "18:00") == "The sauna booking is at six."
    # And a bare number in an unknown domain is not assumed to be degrees.
    assert p.spoken("shoes", "size", "9") == "9"
    for domain, slot, value in [("", "", ""), ("a.b.c.d", "e", "1"),
                                ("UPPER", "Slot", "Value"), ("x_y", "p_q", "8")]:
        assert p.statement(domain, slot, value).endswith(".")
    print("PASS an unknown domain still speaks:",
          p.statement("garage.left", "door", "closed"))


def test_a_setting_about_one_person_belongs_to_her():
    """"We eat at seven" and "Ada eats at five" are both true, and the console
    draws a row for each, so the phrasing has to distinguish them by name."""
    assert p.statement("meals", "dinner", "17:00", "Ada") == "Ada's dinner is at five."
    assert p.statement("thermostat", "target", "19", "Ada") == \
        "Ada's thermostat is set to 19 degrees."     # never "Ada's the thermostat"
    assert p.possessive("Gus") == "Gus'" and p.possessive("Ada") == "Ada's"
    # A dotted domain fills the same slot from its own tail when nobody is named.
    assert p.statement("bedroom.ada", "lights", "off at 21:00") == \
        "Ada's bedroom lights are off at 21:00."
    print("PASS a setting about one person belongs to her")


def test_the_contest_is_settled_in_the_terms_a_house_argues_in():
    """`basis` names the rule the resolver used, which is a fact about Hearth
    and not about the house. "won on authority" tells a visitor nothing."""
    auth = p.verdict("authority", winner="Dad", about=None,
                     domain="thermostat", slot="target")
    assert auth["line"] == "Dad has the final say over the thermostat."
    assert "Dad" in auth["chip"] and "authority" not in auth["chip"]

    recent = p.verdict("recency", winner="Mum", about=None,
                       domain="shopping", slot="coffee")
    assert "most recent" in recent["line"] and "Mum" in recent["line"]

    mine = p.verdict("scope", winner="Mum", about="Ada",
                     domain="meals", slot="dinner")
    assert "about Ada" in mine["line"] and mine["chip"] == "about Ada"

    # A sole belief is not a contest, and an unknown rule name is not a sentence.
    assert p.verdict("sole live belief", winner="Dad", about=None,
                     domain="meals", slot="dinner") == {"chip": "", "line": ""}
    print("PASS the contest is settled in household terms:", auth["line"])


def test_what_a_member_has_the_say_over_is_said_in_words():
    assert p.authority_line(["thermostat"]) == "has the say over the thermostat"
    assert p.authority_line(["bedroom.ada"]) == "has the say over Ada's bedroom"
    assert "everything under it" in p.authority_line(["bedroom.*"])
    assert p.authority_line(["thermostat", "shopping"]) == \
        "has the say over the thermostat and the shopping"
    # Having no grant is a real position in the house, not a missing field.
    assert "recency" in p.authority_line([])
    print("PASS authority is said in words:", p.authority_line(["bedroom.*"]))


def test_a_belief_shows_the_sentence_somebody_actually_said():
    """The quote is the evidence. A rendering of the belief it became is only
    for the ones that arrived some other way, such as a backdated import."""
    assert p.said("thermostat", "target", "19", "keep it at 19 in here") == \
        "“keep it at 19 in here”"
    assert p.said("thermostat", "target", "19", "   ") == \
        "The thermostat is set to 19 degrees."
    print("PASS a belief shows what was actually said")


def test_where_a_belief_stands_distinguishes_ended_from_taken_back():
    """Superseded beliefs are kept on purpose, so the list that shows them has
    to say what happened to each one. `status` alone flattens "somebody took
    this back" and "the situation it belonged to is over" into one word."""
    assert p.standing(True, "active") == "standing"
    assert p.standing(False, "expired", "context ended: the cold snap") == \
        "the cold snap ended"
    assert p.standing(False, "superseded", "Dad changed his mind") == \
        "Dad changed his mind"
    assert p.standing(False, "superseded") == "stood down"
    print("PASS where a belief stands says how it got there")


def test_the_explanation_speaks_the_same_language_as_the_card():
    """explain() is the sentence the product is really about, and it used to
    read out the stored value in the middle of it: "Mum set it just now, to
    19:00" under a card that said seven o'clock. The renderer is a hook rather
    than an import because the model layer must not know how anything is worded,
    and the tools keep the stored value because a tool result is not a sentence
    anybody hears."""
    from hearth import Household, Ledger

    h = Household("test")
    mum, dad = h.add_member("Mum"), h.add_member("Dad")
    # Two adults and no grant over mealtimes, so recency decides and both
    # values end up in the sentence, which is what this is about.
    h.assert_belief(mum.id, "meals", "dinner", "19:00", stated_at=time.time() - 600)
    h.assert_belief(dad.id, "meals", "dinner", "17:30")
    r = h.resolve("meals", "dinner")

    assert r.explain(h.name_of).endswith(
        "to 17:30. Mum said 19:00, but it was set earlier.")
    assert r.explain(h.name_of, p.value_spoken).endswith(
        "to half past five. Mum said seven, but it was set earlier.")

    # And the ledger, because "why did you do that?" is asked out loud.
    led = Ledger(h)
    a = led.record("set dinner to 17:30", "meals", resolution=r)
    assert "to half past five" in led.why(action_id=a.id), led.why(action_id=a.id)
    print("PASS the explanation speaks the same language as the card")


def test_the_console_payload_carries_the_household_wording():
    """End to end, because the phrasing being right in isolation is worth
    nothing if `_state` does not put it where the page reads it."""
    c, tok = house()
    say = console(c, tok, "POST", "/api/say",
                  said="keep it at 19 in here", speaker="Dad")
    assert say["line"] == ("Noted, on Dad's word. The thermostat is set to "
                           "19 degrees."), say["line"]
    # The exact text the MCP tool returned is still there, because that is what
    # Alexa+ would hear and the console must not quietly say something else.
    assert "thermostat.target" in say["reply"], say["reply"]

    console(c, tok, "POST", "/api/say", said="make it 23", speaker="Ada")
    state = console(c, tok, "GET", "/api/state")
    row = next(r for r in state["slots"] if r["domain"] == "thermostat")
    assert row["title"] == "The thermostat" and row["reading"] == "19°", row
    assert row["statement"] == "The thermostat is set to 19 degrees.", row
    assert row["verdict"]["line"] == "Dad has the final say over the thermostat."
    assert "to 19 degrees" in row["sentence"], row["sentence"]
    assert row["losers"][0]["reading"] == "23°", row["losers"]
    # The internal names stay in the payload, because the buttons act on them.
    assert row["slot"] == "target" and row["value"] == "19", row

    assert any(m["authority"] == "has the say over the thermostat"
               for m in state["members"]), state["members"]
    assert state["beliefs"][0]["said"] == "“keep it at 19 in here”"
    assert state["beliefs"][0]["standing"] == "standing"
    print("PASS the console payload carries the household wording")


def test_the_console_answers_an_action_without_naming_a_slot():
    """The reply line is the one piece of the page a judge makes appear by
    typing, so it is the last place a dotted key should survive. The value in
    it stays raw: a record of what was done has to say what the device was
    actually given, and "dinner is at five" is the wrong thing to find in a log.
    """
    c, tok = house()
    console(c, tok, "POST", "/api/say", said="keep it at 19 in here", speaker="Dad")
    console(c, tok, "POST", "/api/say", said="we eat at 19:00", speaker="Mum")
    console(c, tok, "POST", "/api/say", said="dinner for Ada is at 17:00", speaker="Mum")

    did = console(c, tok, "POST", "/api/act", domain="thermostat", slot="target")
    assert did["reply"] == "Set the thermostat to 19.", did["reply"]
    assert did["state"]["actions"][0]["what"] == "set the thermostat to 19"

    hers = console(c, tok, "POST", "/api/act", domain="meals", slot="dinner",
                   about="Ada")
    assert hers["reply"] == "Set Ada's dinner to 17:00.", hers["reply"]
    # Somebody who does not live here gets the household answer, so the sentence
    # must not claim the setting was theirs.
    guest = console(c, tok, "POST", "/api/act", domain="meals", slot="dinner",
                    about="Gran")
    assert guest["reply"] == "Set dinner to 19:00.", guest["reply"]

    nothing = console(c, tok, "POST", "/api/act", domain="security", slot="alarm")
    assert nothing["reply"] == "Nobody has set the security alarm.", nothing["reply"]

    bid = next(b["id"] for b in did["state"]["beliefs"] if b["value"] == "19")
    gone = console(c, tok, "POST", "/api/retire", belief_id=bid)
    assert gone["reply"] == "Stood down Dad's 19 for the thermostat.", gone["reply"]
    print("PASS the console answers an action without naming a slot")


def test_a_situation_says_what_it_is_holding_up():
    """Ending a situation takes beliefs away with it, so the panel has to show
    what would go, in a form somebody can weigh before saying the word."""
    c, tok = house()
    ctx = console(c, tok, "POST", "/api/say",
                  said="make it 23 while Gran is staying", speaker="Dad")
    assert ctx["line"].endswith("That holds only while Gran's visit lasts."), ctx["line"]
    riding = console(c, tok, "GET", "/api/state")["contexts"][0]
    assert riding["holds"] == ["The thermostat is set to 23 degrees."], riding
    # The machine-shaped list stays beside it: an operator greps for that one.
    assert riding["riding"] == ["thermostat.target=23"], riding

    over = console(c, tok, "POST", "/api/say", said="Gran's gone home", speaker="Dad")
    assert over["line"] == ("Understood, Gran's visit is over. One thing stopped "
                            "applying. The thermostat is set to 23 degrees."), over["line"]
    print("PASS a situation says what it is holding up")


def test_the_page_reads_nothing_the_server_does_not_send():
    """The console draws one payload and every key it names is a blank panel if
    it is missing, which is a failure with a green suite behind it. The humanised
    keys are new, so this pins them by the names the page actually uses."""
    here = os.path.dirname(os.path.abspath(__file__))
    page = open(os.path.join(here, "..", "hearth", "web", "console.html")).read()
    c, tok = house()
    console(c, tok, "POST", "/api/say", said="keep it at 19 in here", speaker="Dad")
    console(c, tok, "POST", "/api/say", said="make it 23", speaker="Ada")
    state = console(c, tok, "GET", "/api/state")

    for key in ("title", "reading", "statement", "verdict"):
        assert key in state["slots"][0], (key, state["slots"][0])
        assert f"x.{key}" in page, key
    assert {"chip", "line"} == set(state["slots"][0]["verdict"])
    assert "x.verdict.chip" in page and "x.verdict.line" in page
    for key in ("said", "standing"):
        assert key in state["beliefs"][0] and f"b.{key}" in page, key
    assert "authority" in state["members"][0] and "m.authority" in page
    assert "l.reading" in page and "reading" in state["slots"][0]["losers"][0]
    # And nothing the page draws from a slot leaks the internal naming.
    assert "${esc(x.domain)}.${esc(x.slot)}" not in page
    print("PASS the page reads nothing the server does not send")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall green")
