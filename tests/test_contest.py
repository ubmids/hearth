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
    """'We eat at 7' and 'the baby eats at 5' are both true."""
    h, dad, mum, kid = house()
    h.assert_belief(dad.id, "meals", "dinner", "19:00")
    h.assert_belief(mum.id, "meals", "dinner", "17:00", scope=kid.id)
    assert h.resolve("meals", "dinner").winner.value == "19:00"
    r = h.resolve("meals", "dinner", for_member=kid.id)
    assert r.winner.value == "17:00"
    assert r.basis == "scope"
    print("PASS scope:", r.explain(h.name_of))


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
