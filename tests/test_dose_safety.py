"""A question about a dose must never record one.

The bug this file exists for: Rose asks "Should I take my tablet now?" at
8:55. The planner heard "take" and "tablet", called give_dose, and Hearth
logged a warfarin dose. At 9:10 Grace gave the real one, and Hearth refused
it, so the real dose was missed. In a warfarin product that is the worst
possible failure, so every sentence below goes through the planner and the
real server, and the dose book is checked after each one.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HEARTH_TZ", "America/New_York")

from hearth import sim
from hearth.mcp import TOOLS

from test_care import House

QUESTIONS = [
    "Should I take my tablet now?",
    "should i take my tablet now",
    "Alexa, should I take my blood thinner?",
    "Can I have my warfarin now?",
    "Is it time for my warfarin?",
    "Alexa, time for my warfarin?",
    "Do I need to take my pills?",
    "Has Mom had her warfarin today?",
    "Did Grace give Mom her blood thinner?",
    "Am I due my Coumadin",
    "Shall I give Mom her warfarin?",
    "I'm going to take my warfarin, is that okay?",
    "When do I take my blood thinner?",
]

REPORTS = [
    ("Alexa, I'm just going to take my blood thinner.", "warfarin", 1),
    ("Alexa, time for my warfarin", "warfarin", 1),
    ("I took my warfarin", "warfarin", 1),
    ("I've taken my Jantoven", "warfarin", 1),
    ("I gave Mom her warfarin", "warfarin", 1),
    ("I took two aspirin", "aspirin", 2),
    ("Mom's had 2 paracetamol", "paracetamol", 2),
]

NOT_DOSES = [
    "Mom takes one warfarin a day",
    "I'm not taking my warfarin today",
    "I'll take my blood thinner later",
    "Yes",
    "No, I'll wait",
]


def plan(said, who="Rose", ctx=None):
    return sim.plan_rules(said, who, ctx or {})[0]


def test_questions_are_answered_and_never_logged():
    for said in QUESTIONS:
        p = plan(said)
        assert p["name"] == "check_dose", (said, p)
    print(f"PASS {len(QUESTIONS)} dose questions plan to check_dose")


def test_reports_log_the_medicine_that_was_named_and_how_many():
    for said, med, n in REPORTS:
        p = plan(said)
        assert p["name"] == "give_dose", (said, p)
        assert p["arguments"]["medication"] == med, (said, p)
        assert p["arguments"].get("count", 1) == n, (said, p)
    print("PASS dose reports plan to give_dose with the named medicine and count")


def test_things_that_are_not_doses_are_not_logged():
    for said in NOT_DOSES:
        assert plan(said)["name"] not in ("give_dose",), (said, plan(said))
    print("PASS rules, refusals to take, and bare yes/no are not doses")


def test_an_unnamed_medicine_is_never_guessed_as_warfarin():
    p = plan("I'm taking my pills")
    assert p["name"] == "give_dose" and p["arguments"]["medication"] == "pills", p
    house = House()
    n = len(house.server.care.book.doses)
    reply = house.say("give_dose", **p["arguments"])
    assert reply.startswith("Which medicine do you mean, Rose?"), reply
    assert len(house.server.care.book.doses) == n, "an unnamed dose was logged"
    print("PASS 'my pills' asks which medicine and records nothing")


def test_confirmations_use_the_medicine_just_discussed():
    ctx = {"medication": "warfarin"}
    p = plan("OK, I've taken it now", ctx=ctx)
    assert p == {"name": "give_dose", "arguments": {"medication": "warfarin",
                                                     "given_by": "Rose"}}, p
    # Without that context "it" is not a medicine, and Hearth asks.
    assert plan("OK, I've taken it now")["arguments"]["medication"] == "it"
    # "Yes, go ahead" pays only when a checkout is waiting, and a dose report
    # is never taken as consent to pay.
    assert plan("Yes, go ahead", "Grace", {"checkout": {"quote": "q"}})["host"] == \
        "checkout.complete"
    assert plan("Yes, I took it", "Rose", {"checkout": {"quote": "q"},
                                          **ctx})["name"] == "give_dose"
    print("PASS confirmations follow the conversation, never a guess")


def test_the_demo_question_at_855_does_not_cost_the_910_dose():
    """The exact failure: Rose asks before Grace's dose, then Grace gives it."""
    house = House()
    book = house.server.care.book
    book.doses.clear()                             # it is 8:55; nothing given yet
    for said in ("Should I take my tablet now?", "Can I have my warfarin?"):
        p = plan(said)
        reply = house.say(p["name"], **p["arguments"])
        assert "haven't had your warfarin today" in reply, reply
        assert "write it down" in reply, reply
        assert book.doses == [], f"{said!r} logged a dose"
    p = plan("I've just given Mom her warfarin", "Grace")
    reply = house.say(p["name"], **p["arguments"])
    assert reply.startswith("Logged."), reply
    assert len(book.doses) == 1
    # Now the question gets the answer that matters, still recording nothing.
    p = plan("Should I take my tablet now?")
    reply = house.say(p["name"], **p["arguments"])
    assert reply.startswith("Not now, Rose. Grace gave you today's warfarin"), reply
    assert len(book.doses) == 1
    # And the hero line is still refused.
    p = plan("Alexa, I'm just going to take my blood thinner.")
    reply = house.say(p["name"], **p["arguments"])
    assert reply.startswith("Hold on, Rose."), reply
    assert len(book.doses) == 1
    print("PASS asking at 8:55 leaves Grace's 9:10 dose to be logged")


def test_two_tablets_at_once_count_against_a_once_a_day_rule():
    house = House()
    house.server.care.book.doses.clear()
    reply = house.say("give_dose", medication="warfarin", given_by="Rose", count=2)
    assert reply.startswith("Hold on, Rose."), reply
    assert house.server.care.book.doses == []
    reply = house.say("give_dose", medication="aspirin", given_by="Rose", count=2)
    assert "aspirin" in reply.lower(), reply
    assert house.server.care.book.doses[-1]["count"] == 2
    print("PASS two at once is two doses")


def test_a_model_that_calls_give_dose_for_a_question_is_overruled():
    """The planner guard holds whichever brain plans: a model that reads a
    question as a dose report is corrected to check_dose before any call."""
    orig = sim.plan_model
    sim.plan_model = lambda *a, **k: [{"name": "give_dose", "arguments": {
        "medication": "warfarin", "given_by": "Rose"}}]
    try:
        out = sim.plan("Should I take my tablet now?", "Rose", TOOLS)
        assert [c["name"] for c in out["calls"]] == ["check_dose"], out
        assert "dose guard" in out["planner"], out
    finally:
        sim.plan_model = orig
    print("PASS a model's give_dose on a question is turned into check_dose")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall green (dose safety)")
