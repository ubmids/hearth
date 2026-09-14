"""The behaviours that make Hearth more than a key-value store.

Each test is a household situation that an ordinary memory store gets wrong.
"""
import os, shutil, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hearth import Household, Ledger
from hearth.models import _ago
from hearth.store import Store

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



def test_the_ledger_survives_a_restart():
    """"Why did you do that?" has to still work tomorrow.

    This was a real bug, and the worst one in the tree. The ledger read its
    actions back from the store as raw dictionaries and never turned them into
    Actions again, so after any restart the first `why` raised AttributeError,
    the next `did` could not save, and the console's /api/state answered 500.
    Every test built a ledger in memory and never reopened one, so nothing saw
    it. A product whose entire claim is that it remembers why it acted cannot
    be tested only inside the process that did the acting.
    """
    tmp = tempfile.mkdtemp(prefix="hearth-ledger-")
    try:
        store = Store(os.path.join(tmp, "house"))
        h = Household("test", store=store)
        dad = h.add_member("Dad", role="adult", grants=["thermostat"])
        kid = h.add_member("Kid", role="child")
        h.assert_belief(dad.id, "thermostat", "target", "19",
                        content="keep it at 19", stated_at=time.time() - WEEK)
        h.assert_belief(kid.id, "thermostat", "target", "23", stated_at=time.time())
        led = Ledger(h, store=store)
        acted = led.record("set the thermostat to 19", "thermostat",
                           resolution=h.resolve("thermostat", "target"))
        said_then = led.why()

        reopened = Store(os.path.join(tmp, "house"))
        h2 = Household("test", store=reopened)
        led2 = Ledger(h2, store=reopened)

        assert [a.id for a in led2.actions] == [acted.id]
        # The sentence, not just the row: the losing belief and the rule that
        # beat it are the part that makes the answer worth anything, and they
        # live inside the resolution rather than on the action.
        assert led2.why() == said_then, (led2.why(), said_then)
        assert "Dad has the say over thermostat" in led2.why()
        assert led2.why(action_id=acted.id) == said_then

        # And it can still be written to. The first `did` after a restart used
        # to fail while saving, which lost the new action as well as the old.
        led2.record("set the thermostat to 22", "thermostat")
        assert len(Ledger(h2, store=Store(os.path.join(tmp, "house"))).actions) == 2
        print("PASS the ledger and its reasons survive a restart")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_an_action_with_nothing_behind_it_says_so():
    """The ledger can be written to without a resolution, and then it must not
    invent one. An assistant that says "because Dad set it" when it recorded no
    such thing is worse than one that admits it did not write the reason
    down."""
    h, dad, mum, kid = house()
    led = Ledger(h)
    led.record("turned the lights off", "lights")
    assert led.why() == "I turned the lights off, but I did not record what that was based on."
    assert Ledger(h).why() == "I have not done anything like that."

    # A refusal is an action too, and the audit trail is worth less if only the
    # things that went ahead are in it.
    assert led.actions[0].outcome == "done"
    refused = led.record("turned the heating up", "thermostat", outcome="refused")
    assert refused.outcome == "refused"
    assert refused.to_dict()["outcome"] == "refused"
    print("PASS an action with no recorded reason says exactly that")


def test_why_answers_about_the_domain_that_was_asked_about():
    """`why` takes a domain because a household asks "why is it cold?", not
    "why did you do the last thing you did". The most recent action in another
    domain must not be the answer."""
    h, dad, mum, kid = house()
    led = Ledger(h)
    h.assert_belief(dad.id, "thermostat", "target", "19")
    led.record("set the thermostat to 19", "thermostat",
               resolution=h.resolve("thermostat", "target"))
    led.record("added coffee to the list", "shopping")

    assert "thermostat" in led.why(domain="thermostat")
    assert led.last(domain="thermostat").what == "set the thermostat to 19"
    assert led.last().what == "added coffee to the list"
    assert led.why(domain="laundry") == "I have not done anything like that."

    # And each action is addressable on its own, which is how the console asks
    # for a reason per row. Ids that collide would answer every row with the
    # first action's reason and look entirely plausible doing it.
    first, second = led.actions
    assert first.id != second.id
    assert "thermostat" in led.why(action_id=first.id)
    assert "coffee" in led.why(action_id=second.id)
    print("PASS why answers about the domain it was asked about")


def test_role_ranks_decide_when_nobody_owns_the_domain():
    """The fallback authority model, never exercised as a hierarchy. Every test
    about authority used an explicit grant, so the role ranks could have been
    flattened to a single number and only the ordering of two of them would
    ever have been noticed.

    A role nobody defined must rank bottom rather than crash or win: roles
    arrive from account linking in a real add-on, and an unrecognised one
    outranking the family is not a failure anyone would spot in time.
    """
    h = Household("test")
    owner = h.add_member("Owner", role="owner")
    adult = h.add_member("Adult", role="adult")
    child = h.add_member("Child", role="child")
    guest = h.add_member("Guest", role="guest")
    stranger = h.add_member("Stranger", role="houseplant")

    ranks = [m.authority_over("media") for m in (owner, adult, child, guest)]
    assert ranks == sorted(ranks, reverse=True), ranks
    assert len(set(ranks)) == 4, ranks
    assert stranger.authority_over("media") == 0
    assert guest.authority_over("media") == 0

    now = time.time()
    h.assert_belief(owner.id, "media", "volume", "quiet", stated_at=now - WEEK)
    h.assert_belief(guest.id, "media", "volume", "loud", stated_at=now)
    r = h.resolve("media", "volume")
    assert r.winner.value == "quiet", "a guest outranked the owner"
    assert r.basis == "authority"
    print("PASS role ranks order the house when nobody owns the domain")


def test_a_wildcard_grant_covers_the_domain_it_names():
    """`bedroom.*` has to cover `bedroom` and everything under it, and nothing
    else. Only one wildcard case was ever resolved, so the prefix could have
    been sliced anywhere and the neighbouring domains it wrongly swallowed
    would have gone unnoticed: a grant that leaks is somebody quietly gaining
    the say over a room that is not theirs."""
    h = Household("test")
    kid = h.add_member("Kid", role="child", grants=["bedroom.*"])
    adult = h.add_member("Adult", role="adult")

    for mine in ("bedroom", "bedroom.kid", "bedroom.kid.lamp"):
        assert kid.authority_over(mine) > adult.authority_over(mine), mine
    for theirs in ("bedrooms", "bedroom_annexe", "kitchen", "thermostat"):
        assert kid.authority_over(theirs) < adult.authority_over(theirs), theirs

    # Between two people who both own a domain, role still decides. Otherwise
    # granting a child the run of a room quietly puts them above the owner
    # everywhere they overlap.
    owner = h.add_member("Owner", role="owner", grants=["bedroom.*"])
    assert owner.authority_over("bedroom.kid") > kid.authority_over("bedroom.kid")

    # An exact grant is exact: it covers its own domain and nothing beneath it.
    exact = h.add_member("Exact", role="child", grants=["thermostat"])
    assert exact.authority_over("thermostat") > adult.authority_over("thermostat")
    assert exact.authority_over("thermostat.upstairs") < adult.authority_over(
        "thermostat.upstairs")
    print("PASS a wildcard grant covers its own domain and nothing beside it")


def test_a_belief_with_an_expiry_stops_winning_when_it_passes():
    """`expires_at` is the other way a belief ends, and it had no test at all.
    "Only until Friday" is a thing people say, it is stored, it is persisted,
    and nothing anywhere checked that Friday ever arrives."""
    h, dad, mum, kid = house()
    now = time.time()
    h.assert_belief(dad.id, "thermostat", "target", "19", stated_at=now - WEEK)
    until = h.assert_belief(dad.id, "thermostat", "target", "23",
                            expires_at=now + 3600, stated_at=now)

    assert until.is_live(now)
    assert h.resolve("thermostat", "target", now=now).winner.value == "23"

    later = now + 3601
    assert not until.is_live(later)
    assert h.resolve("thermostat", "target", now=later).winner.value == "19"
    # It is spent, not deleted, exactly like a context that ended.
    assert until in h.beliefs and until.status == "active"
    print("PASS a belief with an expiry stops winning once it passes")


def test_ending_a_situation_with_no_name_ends_nothing():
    """A real bug. `b.context == context` matched every belief that was never
    tied to a situation, so ending a context of None expired the household's
    whole standing memory and reported it as a situation closing. The MCP tool
    takes that argument straight from a language model."""
    h, dad, mum, kid = house()
    h.assert_belief(dad.id, "thermostat", "target", "19")
    h.assert_belief(mum.id, "shopping", "coffee", "Sumatra")
    h.assert_belief(dad.id, "lights", "bedtime", "22:00", context="half term")

    assert h.end_context(None) == [], "an unnamed context ended real beliefs"
    assert h.end_context("") == []
    assert all(b.is_live() for b in h.beliefs), [b.status for b in h.beliefs]
    assert len(h.end_context("half term")) == 1
    print("PASS ending a situation with no name ends nothing")


def test_the_house_is_read_back_exactly_as_it_was_written():
    """Everything the product claims to remember goes through to_dict and
    from_dict, and a field dropped there is data lost silently at the next
    restart. Nothing round-tripped a belief with anything interesting on it,
    so scope, context, expiry, status and the audit trail could all have gone
    missing and every in-memory test would still pass."""
    tmp = tempfile.mkdtemp(prefix="hearth-store-")
    try:
        path = os.path.join(tmp, "house")
        h = Household("test", store=Store(path))
        dad = h.add_member("Dad", role="owner", grants=["thermostat", "bedroom.*"])
        kid = h.add_member("Kid", role="child")
        warm = h.assert_belief(dad.id, "thermostat", "target", "23",
                               content="make it 23 while Gran is staying",
                               context="Gran's visit", stated_at=time.time() - WEEK)
        early = h.assert_belief(dad.id, "meals", "dinner", "17:00", scope=kid.id,
                                expires_at=time.time() + 600)
        gone = h.assert_belief(kid.id, "media", "volume", "loud")
        h.retire(gone.id, reason="Kid stood it down")

        back = Household("test", store=Store(path))
        assert {m.name: (m.role, tuple(m.grants)) for m in back.members.values()} == \
            {"Dad": ("owner", ("thermostat", "bedroom.*")),
             "Kid": ("child", ())}
        by_id = {b.id: b for b in back.beliefs}
        assert set(by_id) == {warm.id, early.id, gone.id}
        for original in (warm, early, gone):
            assert by_id[original.id].to_dict() == original.to_dict(), original.domain

        # And the house still behaves, rather than merely still parsing.
        assert back.resolve("thermostat", "target").winner.value == "23"
        assert back.resolve("meals", "dinner", for_member=kid.id).winner.value == "17:00"
        assert back.resolve("media", "volume").winner is None
        assert back.end_context("Gran's visit")[0].id == warm.id
        print("PASS the house is read back exactly as it was written")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_the_sentence_the_assistant_says_out_loud():
    """The explanation is the product. Every test so far printed it and
    asserted a word or two, so the sentence could have lost the person, the
    time, the situation or the belief it beat and stayed green throughout.

    The times are pinned at the boundaries because "3 weeks ago" and "just
    now" are the difference between a household trusting the answer and
    wondering what it is talking about.
    """
    h = Household("test")
    dad = h.add_member("Dad", role="adult", grants=["thermostat"])
    kid = h.add_member("Kid", role="child")
    gran = h.add_member("Gran", role="guest")
    now = time.time()
    h.assert_belief(dad.id, "thermostat", "target", "19", content="keep it at 19",
                    context="the cold snap", stated_at=now - 3 * WEEK)
    h.assert_belief(kid.id, "thermostat", "target", "23", stated_at=now - 60)
    h.assert_belief(gran.id, "thermostat", "target", "25", stated_at=now)

    # Two losers, so the sentence has to name the runner-up rather than
    # whoever came last. The resolver already had that pinned for `basis` and
    # the sentence people actually hear did not.
    assert h.resolve("thermostat", "target").explain(h.name_of) == (
        "Dad set it 3 weeks ago, during the cold snap, to 19. "
        "Kid said 23, but Dad has the say over thermostat.")

    # An assertion with nothing standing against it says only what happened.
    quiet = Household("test")
    mum = quiet.add_member("Mum")
    quiet.assert_belief(mum.id, "shopping", "coffee", "Sumatra", stated_at=now - 7200)
    assert quiet.resolve("shopping", "coffee").explain(quiet.name_of) == (
        "Mum set it 2 hours ago, to Sumatra.")

    # And the boundaries either side of each unit, including the singulars.
    ago = {secs: _ago(now - secs, now) for secs in
           (0, 3599, 3600, 7200, 86400, 172800, 604800, 3 * WEEK)}
    assert ago == {0: "just now", 3599: "just now", 3600: "1 hour ago",
                   7200: "2 hours ago", 86400: "1 day ago", 172800: "2 days ago",
                   604800: "1 week ago", 3 * WEEK: "3 weeks ago"}, ago
    print("PASS the sentence the assistant says out loud")

def test_a_save_that_fails_does_not_destroy_the_house():
    """The store writes to a temp file and renames it, and the rename is the
    only reason a half-written save is survivable. Nothing tested that, because
    the guarantee only shows itself on the one run that goes wrong: write
    straight to the real path and any failure mid-write leaves a truncated file
    where the household used to be, which reads back as an empty house.

    Forced here by handing `save` something that cannot be serialised, which is
    what a crash in the middle of a write looks like from the file's point of
    view.
    """
    tmp = tempfile.mkdtemp(prefix=f"hearth-atomic-{os.getpid()}-")
    try:
        path = os.path.join(tmp, "house")
        store = Store(path)
        h = Household("test", store=store)
        dad = h.add_member("Dad", role="adult", grants=["thermostat"])
        h.assert_belief(dad.id, "thermostat", "target", "19", content="keep it at 19")

        class Unserialisable:
            """A member whose grants json cannot write. The failure has to land
            inside the dump rather than before it, which is the whole point."""
            id = "m-broken"

            def to_dict(self):
                return {"id": self.id, "name": "Broken", "role": "adult",
                        "grants": {"a set", "json cannot write"}}

        try:
            store.save({"m-broken": Unserialisable()}, h.beliefs)
            raise AssertionError("the unserialisable save was supposed to fail")
        except TypeError:
            pass

        members, beliefs = Store(path).load()
        assert [m.name for m in members.values()] == ["Dad"], members
        assert [b.value for b in beliefs] == ["19"], beliefs
        print("PASS a save that fails does not destroy the house")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nall green")
