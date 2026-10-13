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
    # Quarter to wraps round the top of the clock, where the arithmetic that
    # names the next hour is the only place it can be wrong.
    assert p.spoken("meals", "dinner", "12:45") == "quarter to one"
    assert p.spoken("meals", "dinner", "23:45") == "quarter to twelve"
    # A minute under ten keeps its leading zero. 7:23 is the same string either
    # way, so the padding was the one part of this nothing had ever read.
    assert p.spoken("meals", "dinner", "07:05") == "7:05"

    # And the short form keeps the half of the day, which words drop.
    assert p.reading("meals", "dinner", "17:00") == "5:00pm"
    assert p.reading("meals", "dinner", "07:00") == "7:00am"
    # Noon and midnight are the two the half-of-the-day test is decided by, and
    # both were a full twelve hours away from anything asserted here. Midday
    # shown as 12:00am is a dinner moved to the middle of the night.
    assert p.reading("meals", "dinner", "12:00") == "12:00pm"
    assert p.reading("meals", "dinner", "00:00") == "12:00am"
    assert p.reading("meals", "dinner", "11:59") == "11:59am"
    assert p.reading("shopping", "coffee", "Sumatra") == "Sumatra"
    print("PASS a time is read off a clock")


def test_every_hour_of_the_clock_has_a_word():
    """Four of the twelve hours were ever spoken out loud, and the words come
    out of a hand-written table that nothing read the rest of.

    A missing or wrong entry is not an error anywhere. It is the house saying
    "dinner is at" and then nothing, or naming the wrong hour with complete
    confidence, for one hour of the day and no other, which is the sort of
    thing that gets found by a household rather than by a test.
    """
    words = ["twelve", "one", "two", "three", "four", "five", "six",
             "seven", "eight", "nine", "ten", "eleven"]
    for hour, word in enumerate(words):
        assert p.spoken("meals", "dinner", f"{hour:02d}:00") == word, hour
        assert p.spoken("meals", "dinner", f"{hour + 12:02d}:00") == word, hour
        assert p.spoken("meals", "dinner", f"{hour:02d}:30") == f"half past {word}"
    print(f"PASS all {len(words)} hours of the clock have a word")


def test_a_value_that_only_looks_like_a_time_is_left_as_it_was_written():
    """Both ends of the clock are checked and neither end was tested, so the
    range could have been open on either side.

    A household types 25:00 or 7:75 sooner or later, and the failure is silent:
    25:00 read as a clock is spoken as one o'clock, which is a plausible answer
    to the wrong question. Left alone it is obviously a typo, which is the
    behaviour that can be argued with.
    """
    for odd in ("25:00", "24:00", "07:75", "12:60", "99:99"):
        assert p.spoken("meals", "dinner", odd) == odd, odd
        assert p.reading("meals", "dinner", odd) == odd, odd
    # And the last value on each side that is a real time still is one.
    assert p.spoken("meals", "dinner", "23:59") == "11:59"
    assert p.reading("meals", "dinner", "23:59") == "11:59pm"
    assert p.reading("meals", "dinner", "00:01") == "12:01am"
    print("PASS a value that only looks like a time is left as it was written")


def test_a_value_that_is_not_a_temperature_is_not_read_as_one():
    """The unit belongs to the setting, so the thermostat says degrees whatever
    it is handed, and the guard that stops it is exercised by nothing.

    "The thermostat is set to off degrees" is the sentence a judge hears the
    first time anyone turns the heating off. The other direction costs more:
    a household below freezing sets it to -3, and a unit sniff that reads the
    minus sign as "not a number" drops the degrees from the one reading where
    the number alone is ambiguous.
    """
    assert p.spoken("thermostat", "target", "off") == "off"
    assert p.statement("thermostat", "target", "off") == "The thermostat is set to off."
    assert p.reading("thermostat", "target", "off") == "off"
    assert p.spoken("thermostat", "target", "-3") == "-3 degrees"
    assert p.reading("thermostat", "target", "-3") == "-3\u00b0"
    # A number is still a number in a domain nobody described, and it is still
    # not a temperature: the sniff stops at times on purpose, so that a shoe
    # size does not get announced in degrees.
    assert p.spoken("shoes", "size", "9") == "9"
    print("PASS a value that is not a temperature is not read as one")


SPOKEN_BY_THE_HOUSE = {
    ("thermostat", "target", "19", None): "The thermostat is set to 19 degrees.",
    ("thermostat", "night", "17", None):
        "The thermostat overnight is set to 17 degrees.",
    ("meals", "dinner", "19:00", None): "Dinner is at seven.",
    ("meals", "lunch", "13:00", None): "Lunch is at one.",
    ("meals", "breakfast", "07:30", None): "Breakfast is at half past seven.",
    ("lights", "bedtime", "21:00", None): "Lights out is at nine.",
    ("lights", "brightness", "dim", None): "The lights are set to dim.",
    ("shopping", "coffee", "Sumatra", None): "The coffee is Sumatra.",
    ("shopping", "milk", "oat", None): "The milk is oat.",
    ("media", "volume", "4", None): "The volume is set to 4.",
    ("bedroom", "lights", "off", "Ada"): "Ada's bedroom lights are off.",
    ("bedroom", "bedtime", "20:00", "Ada"): "Ada's bedtime is at eight.",
    # The care household, where the wording is the difference between a
    # sentence an 84 year old can act on and a field name.
    ("medication.warfarin", "per_day", "1", "Mum"): "Mum's warfarin is once a day.",
    ("medication.warfarin", "time", "09:00", "Mum"): "Mum's warfarin is due at nine.",
    ("diet", "coffee_cutoff", "15:00", "Mum"): "Mum's coffee stops at three.",
    ("diet", "alcohol", "none", "Mum"): "Mum's alcohol is off limits.",
    ("purchases", "limit", "50", None):
        "The spending limit without asking is 50 dollars.",
    **{("rota", d, "Tom", None): f"The {d.title()} escort is Tom."
       for d in ("monday", "tuesday", "wednesday", "thursday", "friday",
                 "saturday", "sunday")},
}


def test_every_setting_the_house_knows_is_said_in_the_words_written_for_it():
    """Two of the twelve rows were ever spoken. The rest are a table nothing
    reads, which is the same as a table nobody wrote.

    A row that loses its subject, its verb or the key it is filed under does
    not fail. It falls through to the wording built for a domain this file has
    never met, and the house starts saying "the meals lunch is at one" in front
    of whoever is listening. The sentences are written out here rather than
    read back out of SETTINGS, because a test that asks the table what the
    table says agrees with it whatever it has become.
    """
    assert set(p.SETTINGS) == {(d.partition(".")[0], s)
                               for d, s, _, _ in SPOKEN_BY_THE_HOUSE}, \
        "a setting was added or removed without a sentence to go with it"
    for (domain, slot, value, about), said in SPOKEN_BY_THE_HOUSE.items():
        assert p.statement(domain, slot, value, about) == said, (domain, slot)
    print(f"PASS all {len(SPOKEN_BY_THE_HOUSE)} settings are said in their own words")


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
    # A repeated word is dropped rather than stuttered, which is the one rule
    # the generic wording has and the one thing nothing asked it for.
    assert p.subject("lights", "lights") == "the lights"
    # A room nobody is named for still has an article. The {whose} slot is
    # filled from the member, then the tail of the domain, then a plain "the",
    # and the last of those is what a house-wide bedroom setting gets.
    assert p.subject("bedroom", "lights") == "the bedroom lights"
    assert p.statement("bedroom", "bedtime", "20:00") == "The bedtime is at eight."
    assert p.subject("garden.hose", "hose") == "the hose garden"
    # An underscore is a word break, not a character. "The games_room lamp" is
    # the inside of a config file reaching a sentence somebody reads.
    assert p.statement("games_room", "lamp", "on") == \
        "The games room lamp is set to on."
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
    # The chip is the half of this a person reads first and it was only ever
    # checked for a name and the absence of a rule name, which two words of
    # anything would satisfy.
    assert auth["chip"] == "Dad has the say", auth["chip"]

    recent = p.verdict("recency", winner="Mum", about=None,
                       domain="shopping", slot="coffee")
    assert recent["chip"] == "most recent word", recent["chip"]
    assert recent["line"] == (
        "Nobody here outranks anyone else on this, so the most recent word "
        "stands, and it was Mum's."), recent["line"]

    mine = p.verdict("scope", winner="Mum", about="Ada",
                     domain="meals", slot="dinner")
    assert mine["chip"] == "about Ada"
    assert mine["line"] == ("This one is about Ada, so it comes ahead of the "
                            "rule for the whole house."), mine["line"]

    # A scoped belief whose subject nobody named still has to read as a
    # sentence. The console draws this row from whatever the caller asked
    # about, and it asks about nobody more often than it asks about Ada.
    anon = p.verdict("scope", winner="Mum", about=None,
                     domain="meals", slot="dinner")
    assert anon["chip"] == "about one person"
    assert anon["line"].startswith("This one is about one person, so it comes")

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
    # Three is the first length where the list needs a separator as well as an
    # "and", so two grants proved nothing about the join.
    assert p.authority_line(["thermostat", "shopping", "media"]) == \
        "has the say over the thermostat, the shopping and what plays"
    # Having no grant is a real position in the house, not a missing field.
    assert "recency" in p.authority_line([])

    # And each label the house was given words for, said whole. A wildcard
    # keeps its own domain in front of the phrase that widens it, and an
    # underscore in a domain nobody described is a word break rather than a
    # character somebody has to read out.
    assert p.domain_label("bedroom.*") == "the bedroom and everything under it"
    assert p.domain_label("games_room") == "the games room"
    for domain, label in {"thermostat": "the thermostat", "shopping": "the shopping",
                          "meals": "mealtimes", "lights": "the lights",
                          "media": "what plays",
                          "security": "the locks and alarm"}.items():
        assert p.domain_label(domain) == label, domain
        assert p.domain_label(domain + ".*") == label + " and everything under it"
    assert set(p.DOMAIN_LABELS) == {"thermostat", "shopping", "meals", "lights",
                                    "media", "security", "medication", "diet",
                                    "appointments", "purchases", "transport",
                                    "rota"}
    # A medicine is named by itself, never as somebody's possession: the say
    # over medication.warfarin is "warfarin", not "Warfarin's medication".
    assert p.domain_label("medication.warfarin") == "warfarin"
    print("PASS authority is said in words:", p.authority_line(["bedroom.*"]))


def test_what_the_house_says_back_is_a_sentence_in_every_shape():
    """Only one shape of each reply was ever produced, and the others are the
    ones a household reaches within a day.

    Nothing had ever confirmed a sentence with no speaker attached, which is
    what the MCP tools produce when Alexa+ does not say who spoke. Nothing had
    ever ended a situation that took more than one belief with it, which is the
    normal case: a visit sets the heating and the mealtimes together. A reply
    that loses its count or its ending is not an error, it is the house
    answering in a fragment on the one occasion somebody is listening closely.
    """
    assert p.confirm(["The coffee is Sumatra."]) == "Noted. The coffee is Sumatra."
    assert p.confirm(["The coffee is Sumatra."], speaker="Dad") == \
        "Noted, on Dad's word. The coffee is Sumatra."
    # A name ending in s is possessed the way the rest of the product does it.
    assert p.confirm(["The coffee is Sumatra."], speaker="Gus") == \
        "Noted, on Gus' word. The coffee is Sumatra."
    assert p.confirm(["Dinner is at seven.", "The coffee is Sumatra."],
                     speaker="Mum") == \
        "Noted, on Mum's word. Dinner is at seven. The coffee is Sumatra."
    assert p.confirm(["Dinner is at seven."], speaker="Mum",
                     context="Gran's visit") == \
        ("Noted, on Mum's word. Dinner is at seven. That holds only while "
         "Gran's visit lasts.")

    assert p.closed("the cold snap", []) == "Understood, the cold snap is over."
    assert p.closed("the cold snap", ["The thermostat is set to 23 degrees."]) == \
        ("Understood, the cold snap is over. One thing stopped applying. "
         "The thermostat is set to 23 degrees.")
    assert p.closed("the cold snap",
                    ["Dinner is at seven.", "Lights out is at nine."]) == \
        ("Understood, the cold snap is over. 2 things stopped applying. "
         "Dinner is at seven. Lights out is at nine.")
    print("PASS what the house says back is a sentence in every shape")


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
    # An ending with no reason recorded still has to be English. `status` is a
    # field name, and "expired" on the page is the store talking about itself.
    assert p.standing(False, "expired") == "no longer applies"
    assert p.standing(False, "something new") == "something new"

    # And the prefix this reads is written a module away, by end_context, so
    # the two halves were each correct on their own and nothing joined them up.
    from hearth import Household

    h = Household("test")
    dad = h.add_member("Dad")
    warm = h.assert_belief(dad.id, "thermostat", "target", "23",
                           context="Gran's visit")
    h.end_context("Gran's visit")
    assert p.standing(warm.is_live(), warm.status, warm.ended_reason) == \
        "Gran's visit ended", warm.ended_reason
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
    # `reply` is still the exact text the MCP tool returned, and the console
    # must not quietly say something else. It used to be the developer-shaped
    # string, which is why this once asserted "thermostat.target". The tool
    # itself now answers in a sentence, because its result is prose a model
    # reads before speaking, so the two have converged. What still has to hold
    # is that the console shows what Alexa+ was actually told.
    assert say["reply"].startswith("Noted, on Dad's word."), say["reply"]
    assert "The thermostat is set to 19 degrees." in say["reply"], say["reply"]
    # The belief reference stays in the tool text: a model needs it to stand
    # the belief down later. It must not reach the sentence a person reads.
    import re
    assert re.search(r"\[[0-9a-f]{6,}\]", say["reply"]), say["reply"]
    assert not re.search(r"\[[0-9a-f]{6,}\]", say["line"]), say["line"]

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

    # A name ending in s is possessed once, and the same way in both places.
    # The tool text and the console line are written out separately on purpose,
    # because only one of them may carry a belief id, and that is exactly the
    # kind of pair that drifts on a name no test ever used.
    gus = console(c, tok, "POST", "/api/say", said="we eat at 18:00", speaker="Gus")
    assert gus["line"].startswith("Noted, on Gus' word."), gus["line"]
    assert gus["reply"].startswith("Noted, on Gus' word."), gus["reply"]
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
