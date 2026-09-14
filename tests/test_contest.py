"""The behaviours that make Hearth more than a key-value store.

Each test is a household situation that an ordinary memory store gets wrong.
"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hearth import Household, Ledger

WEEK = 604800


def house():
    h = Household("test")
    dad = h.add_member("Dad", role="adult", grants=["thermostat"])
    mum = h.add_member("Mum", role="adult")
    kid = h.add_member("Kid", role="child", grants=["bedroom.*"])
    return h, dad, mum, kid


def test_authority_beats_recency():
    """The demo case. Kid moved the thermostat an hour ago; Dad owns it."""
    h, dad, mum, kid = house()
    now = time.time()
    h.assert_belief(dad.id, "thermostat", "target", "19",
                    content="keep it at 19", stated_at=now - 3 * WEEK)
    h.assert_belief(kid.id, "thermostat", "target", "23",
                    content="make it warmer", stated_at=now - 3600)
    r = h.resolve("thermostat", "target")
    assert r.winner.value == "19", r.winner.value
    assert r.basis == "authority"
    assert "Dad has the say over thermostat" in r.losers[0][1]
    print("PASS authority beats recency:", r.explain(h.name_of))


def test_recency_breaks_ties_between_equals():
    """Two adults, neither owns the domain: the later word stands."""
    h, dad, mum, kid = house()
    now = time.time()
    h.assert_belief(dad.id, "shopping", "coffee", "Lavazza", stated_at=now - WEEK)
    h.assert_belief(mum.id, "shopping", "coffee", "Sumatra", stated_at=now - 60)
    r = h.resolve("shopping", "coffee")
    assert r.winner.value == "Sumatra"
    assert r.basis == "recency"
    print("PASS recency between equals:", r.explain(h.name_of))


def test_explicit_grant_beats_role_rank():
    """A child who owns their bedroom outranks an adult there."""
    h, dad, mum, kid = house()
    h.assert_belief(dad.id, "bedroom.kid", "lights", "off at 20:00")
    h.assert_belief(kid.id, "bedroom.kid", "lights", "off at 21:00")
    r = h.resolve("bedroom.kid", "lights")
    assert r.winner.value == "off at 21:00", r.winner.value
    print("PASS grant beats role:", r.explain(h.name_of))


def test_scope_beats_everything():
    """'We eat at 7' and 'the baby eats at 5' are both true.

    Mutiny found that the first version of this test passed for the wrong
    reason. The scoped belief was also the most recent, from a member of equal
    authority, so recency alone produced the same answer and the scope rule was
    never exercised: deleting it entirely left this test green.

    So the household-wide rule is now BOTH more recent AND from higher
    authority. Nothing except scope can produce the scoped answer.
    """
    h = Household("test")
    dad = h.add_member("Dad", role="owner", grants=["meals"])   # outranks Mum
    mum = h.add_member("Mum", role="adult")
    kid = h.add_member("Kid", role="child")
    now = time.time()

    h.assert_belief(mum.id, "meals", "dinner", "17:00", scope=kid.id,
                    stated_at=now - WEEK)          # older, lower authority
    h.assert_belief(dad.id, "meals", "dinner", "19:00", stated_at=now)

    assert h.resolve("meals", "dinner").winner.value == "19:00"
    r = h.resolve("meals", "dinner", for_member=kid.id)
    assert r.winner.value == "17:00", (
        "the household rule won for Kid, so scope is not being applied")
    assert r.basis == "scope"
    print("PASS scope:", r.explain(h.name_of))


def test_the_reason_given_is_the_one_that_settled_it():
    """With more than one loser, the basis must describe how the winner beat the
    runner-up, not the last-placed belief. Nothing had two losers before, so
    `losers[0]` could have been `losers[-1]` unnoticed."""
    h = Household("test")
    dad = h.add_member("Dad", role="adult", grants=["thermostat"])
    mum = h.add_member("Mum", role="adult")
    kid = h.add_member("Kid", role="child")
    now = time.time()

    h.assert_belief(dad.id, "thermostat", "target", "19", stated_at=now - WEEK)
    h.assert_belief(mum.id, "thermostat", "target", "21", stated_at=now - 60)
    h.assert_belief(kid.id, "thermostat", "target", "25", stated_at=now)

    r = h.resolve("thermostat", "target")
    assert r.winner.value == "19"
    assert len(r.losers) == 2
    # The runner-up is Mum, and Dad beat her on authority.
    assert r.losers[0][0].value == "21", [l[0].value for l in r.losers]
    assert r.basis == "authority"
    print("PASS the basis explains how the runner-up was beaten:",
          r.explain(h.name_of))


def test_context_expiry_without_deletion():
    """Gran goes home. The belief stops applying but is not erased.

    Both assertions are Dad's, so authority ties and the contextual one wins on
    recency. When the context closes, his standing rule resurfaces by itself:
    nothing had to be remembered, corrected or re-stated by anyone.
    """
    h, dad, mum, kid = house()
    now = time.time()
    h.assert_belief(dad.id, "thermostat", "target", "19", stated_at=now - WEEK)
    warm = h.assert_belief(dad.id, "thermostat", "target", "23",
                           context="Gran's visit", stated_at=now - 3600)
    assert h.resolve("thermostat", "target").winner.id == warm.id  # mum is later
    h.end_context("Gran's visit")
    r = h.resolve("thermostat", "target")
    assert r.winner.value == "19"
    assert warm.status == "expired" and warm.ended_reason
    assert warm in h.beliefs, "an expired belief must survive for the audit trail"
    print("PASS context expiry:", r.explain(h.name_of))


# --- the four below were found by Mutiny, not by thinking harder -------------
# Each corresponds to a mutation of household.py that the suite above waved
# through: a change you could have shipped with everything green.

def test_a_belief_from_someone_who_does_not_live_here():
    """`if m else 0` on the authority lookup. A belief whose holder is not in the
    household had no test at all, so the fallback could have returned anything.
    It must rank below every real member, or a stranger outranks the family."""
    h, dad, mum, kid = house()
    now = time.time()
    h.assert_belief(kid.id, "shopping", "coffee", "Lavazza", stated_at=now - WEEK)
    ghost = h.assert_belief("not-a-member", "shopping", "coffee", "Sumatra",
                            stated_at=now)
    r = h.resolve("shopping", "coffee")
    assert r.winner.value == "Lavazza", r.winner.value
    assert h._authority(ghost) == 0
    print("PASS a belief from a stranger ranks below every member")


def test_retiring_something_already_retired():
    """`b is None or b.status != "active"`. Standing down a belief twice had no
    test, so the guard could have been removed and the second call would have
    rewritten the reason on an already-retired belief."""
    h, dad, mum, kid = house()
    b = h.assert_belief(dad.id, "thermostat", "target", "19")
    assert h.retire(b.id, reason="first") is not None
    assert h.retire(b.id, reason="second") is None, "it retired it twice"
    assert b.ended_reason == "first", b.ended_reason
    assert h.retire("no-such-id") is None
    print("PASS retiring an already-retired belief is refused, reason preserved")


def test_asking_about_something_nobody_has_set():
    """`Resolution(winner=None, basis="no live belief")` was never exercised.
    An assistant asking about a setting the house has no opinion on is the
    common case, not an edge one."""
    h, dad, mum, kid = house()
    r = h.resolve("thermostat", "target")
    assert r.winner is None and r.losers == []
    assert r.basis == "no live belief"
    assert r.explain(h.name_of) == "Nobody has set that."
    print("PASS an unset domain resolves to nothing, with a sentence to say")


def test_ending_a_context_reports_what_it_ended():
    """`return ended`. The caller needs the list to tell the household what just
    stopped applying, and nothing checked it was returned."""
    h, dad, mum, kid = house()
    a = h.assert_belief(dad.id, "thermostat", "target", "23", context="Gran's visit")
    b = h.assert_belief(mum.id, "meals", "dinner", "18:00", context="Gran's visit")
    h.assert_belief(dad.id, "lights", "bedtime", "22:00")
    ended = h.end_context("Gran's visit")
    assert {x.id for x in ended} == {a.id, b.id}, [x.id for x in ended]
    assert h.end_context("Gran's visit") == [], "it ended the same context twice"
    assert h.end_context("a situation nobody opened") == []
    print("PASS ending a context returns exactly what stopped applying")


def test_why_then_repair():
    """The 20-second demo, end to end: wrong action, why, repair, right action."""
    h, dad, mum, kid = house()
    stale = h.assert_belief(dad.id, "thermostat", "target", "19",
                            content="keep it at 19", context="the cold snap")
    led = Ledger(h)
    r = h.resolve("thermostat", "target")
    led.record("set the thermostat to 19", "thermostat", resolution=r)

    why = led.why()
    assert "Dad" in why and "19" in why, why
    print("  asked why ->", why)

    h.retire(stale.id, reason="Dad stood it down")
    h.assert_belief(mum.id, "thermostat", "target", "22")
    r2 = h.resolve("thermostat", "target")
    assert r2.winner.value == "22"
    led.record("set the thermostat to 22", "thermostat", resolution=r2)
    print("  after repair ->", led.why())
    print("PASS why then repair")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall green")
