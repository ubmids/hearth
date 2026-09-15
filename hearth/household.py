"""The household: who lives here, what they have asserted, and who wins.

The one design decision everything else follows from: a contested belief is not
destroyed. Cortex superseded by deleting, which is right for a single user
correcting themselves and wrong for a house, where two people can both be
sincerely asserting different things at the same moment and neither is a mistake.
Hearth keeps every assertion and decides at read time, so the losing belief is
still there to be shown, argued with, and promoted later.
"""
import time

from .models import Belief, Member, Resolution


class Household:
    def __init__(self, name: str = "home", store=None):
        self.name = name
        self.store = store
        self.members: dict[str, Member] = {}
        self.beliefs: list[Belief] = []
        if store:
            self.members, self.beliefs = store.load()

    # --- people ------------------------------------------------------------
    def add_member(self, name, role="adult", grants=None) -> Member:
        m = Member(name=name, role=role, grants=grants or [])
        self.members[m.id] = m
        self._persist()
        return m

    def name_of(self, member_id: str) -> str:
        m = self.members.get(member_id)
        return m.name if m else "someone"

    def _authority(self, belief: Belief) -> int:
        m = self.members.get(belief.holder)
        return m.authority_over(belief.domain) if m else 0

    # --- assertions --------------------------------------------------------
    def assert_belief(self, holder, domain, slot, value, content="",
                      scope=None, context=None, expires_at=None,
                      stated_at=None) -> Belief:
        """Record that someone said something. Never overwrites anything.

        `stated_at` backdates the assertion. Needed for two real cases: importing
        a household's existing history, and tests that must pin the recency
        ordering instead of racing the clock.
        """
        b = Belief(domain=domain, slot=slot, value=str(value), holder=holder,
                   content=content, scope=scope, context=context,
                   expires_at=expires_at)
        if stated_at is not None:
            b.stated_at = stated_at
        self._audit(b, "asserted")
        self.beliefs.append(b)
        self._persist()
        return b

    def retire(self, belief_id, reason="retired by a member") -> Belief | None:
        """Explicitly stand a belief down. Distinct from losing a contest: a
        retired belief is out of the running for good, a losing one is merely
        outranked today and may win tomorrow when the winner expires."""
        b = self._by_id(belief_id)
        if b is None or b.status != "active":
            return None
        b.status = "superseded"
        b.ended_reason = reason
        self._audit(b, "retired", reason=reason)
        self._persist()
        return b

    def end_context(self, context: str, now=None) -> list[Belief]:
        """Close a situational frame. Everything asserted inside it stops applying.

        This is the part no memory store models. "Keep it at 23, Gran's staying"
        was never wrong and must not be corrected: it expires when Gran goes home.
        Deleting it would lose the fact that it was true; leaving it would have
        the house heated for a guest who left in March.
        """
        if not context:
            # `b.context == None` matches every belief that was never tied to a
            # situation, so ending "no context" quietly expires the household's
            # entire standing memory. The MCP tool takes this argument straight
            # from a language model, which is reason enough to refuse it here
            # rather than trust that every caller passes something real.
            return []
        ended = []
        for b in self.beliefs:
            if b.context == context and b.is_live(now):
                b.status = "expired"
                b.ended_reason = f"context ended: {context}"
                self._audit(b, "expired", context=context)
                ended.append(b)
        if ended:
            self._persist()
        return ended

    # --- the contest -------------------------------------------------------
    def resolve(self, domain, slot, for_member=None, now=None,
                name_domain=None) -> Resolution:
        """Decide what is true right now, and be able to say why.

        Pure computation, no model call: Alexa+ allows a 500ms round trip for a
        self-hosted MCP server, and the read path has to fit inside it with the
        network still to pay for.

        Order of precedence, most decisive first:
          1. scope      a belief about this person beats one about the house
          2. authority  whoever owns the domain outranks whoever does not
          3. recency    among equals, the most recent assertion stands
        """
        # `name_domain` renders the domain for the losing reasons, the same hook
        # and the same reason as `say` in Resolution.explain: this module must
        # not know how anything is worded, and a surface a person reads must not
        # say "over thermostat" when the English is "over the thermostat". The
        # default keeps the raw domain, so the model layer stays wording-free.
        name_domain = name_domain or (lambda d: d)
        now = now or time.time()
        live = [b for b in self.beliefs
                if b.domain == domain and b.slot == slot and b.is_live(now)
                and (b.scope is None or b.scope == for_member)]
        if not live:
            return Resolution(winner=None, basis="no live belief")

        def rank(b):
            return (1 if b.scope is not None else 0, self._authority(b), b.stated_at)

        ordered = sorted(live, key=rank, reverse=True)
        winner, rest = ordered[0], ordered[1:]

        losers, basis = [], "sole live belief"
        for b in rest:
            if (b.scope is not None) < (winner.scope is not None):
                reason = f"that one is about the whole house, this is about {self.name_of(for_member)}"
                basis = "scope"
            elif self._authority(b) < self._authority(winner):
                reason = (f"{self.name_of(winner.holder)} has the say over "
                          f"{name_domain(domain)}")
                basis = "authority"
            else:
                reason = "it was set earlier"
                basis = "recency"
            losers.append((b, reason))

        if losers:
            # basis names the rule that separated the winner from the runner-up,
            # not from the last-placed belief, so report the first comparison.
            _, first_reason = losers[0]
            basis = ("scope" if "whole house" in first_reason
                     else "authority" if "the say over" in first_reason
                     else "recency")
        return Resolution(winner=winner, losers=losers, basis=basis)

    # --- internals ---------------------------------------------------------
    def _by_id(self, bid):
        return next((b for b in self.beliefs if b.id == bid), None)

    def _audit(self, b: Belief, action, **detail):
        b.audit.append({"at": time.time(), "action": action, **detail})

    def _persist(self):
        if self.store:
            self.store.save(self.members, self.beliefs)
