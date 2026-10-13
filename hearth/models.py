"""Core data model for Hearth.

The unit is a *belief*, not a memory. The difference matters: a memory is
something the system knows, a belief is something a specific person asserted at
a specific time in a specific context, and which may since have stopped being
true. Households run on beliefs.

Every belief carries the three things an ordinary memory store leaves out:

  who   - the member who asserted it (holder), and what authority they hold
  when  - stated_at, plus the context it was asserted inside
  still - whether it is still standing, or superseded / expired, and by what
"""
import time
import uuid
from dataclasses import dataclass, field


def _id() -> str:
    return uuid.uuid4().hex[:12]


# --- authority -------------------------------------------------------------
# Role ranks are the fallback when nobody holds an explicit grant over a domain.
# Deliberately coarse: fine-grained permissions belong in explicit grants, and a
# household that needs more nuance than this is telling you to write it down.
# A paid carer ranks with the adults by default: they are trusted to act, and
# what they may decide is settled by explicit grants like everyone else's.
ROLE_RANK = {"owner": 3, "adult": 2, "carer": 2, "child": 1, "guest": 0}


def _under(domain: str, prefix: str) -> bool:
    """Does `domain` sit at or below `prefix` in the dotted namespace?

    A plain startswith was wrong: `bedroom.*` then covered `bedrooms` and
    `bedroom_annexe` as well, which is somebody silently gaining the say over a
    room that was never theirs. The separator has to be part of the match.
    """
    return domain == prefix or domain.startswith(prefix + ".")


@dataclass
class Member:
    """A person in the household."""
    name: str
    role: str = "adult"                       # owner | adult | child | guest
    id: str = field(default_factory=_id)
    # Domains this member explicitly owns, whatever their role. A child who owns
    # "bedroom.*" outranks an adult there, which is the correct answer and the
    # one a pure role hierarchy gets wrong.
    grants: list = field(default_factory=list)
    # Other names the house uses for this person. Mum is Rose to her carer and
    # "I" to herself, and all three have to land on the same member.
    aliases: list = field(default_factory=list)

    def answers_to(self, name: str) -> bool:
        n = str(name or "").strip().lower()
        return bool(n) and (n == self.name.lower()
                            or n in (a.lower() for a in self.aliases))

    def authority_over(self, domain: str) -> int:
        """Higher wins. Explicit grants beat role rank."""
        for g in self.grants:
            if g == domain or (g.endswith(".*") and _under(domain, g[:-2])):
                return 100 + ROLE_RANK.get(self.role, 0)
        return ROLE_RANK.get(self.role, 0)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "role": self.role,
                "grants": list(self.grants), "aliases": list(self.aliases)}

    @classmethod
    def from_dict(cls, d: dict) -> "Member":
        m = cls(name=d["name"], role=d.get("role", "adult"),
                grants=d.get("grants", []), aliases=d.get("aliases", []))
        m.id = d["id"]
        return m


@dataclass
class Belief:
    """One assertion by one member.

    `domain` and `slot` are what make conflict detection deterministic, and that
    is not a detail: Alexa+ gives a self-hosted MCP server a 500ms round-trip
    budget, so there is no room for a model call on the read path. Two beliefs
    conflict when they fill the same slot of the same domain with different
    values. That is a dictionary lookup, not an inference. The language model
    does its work at *write* time, turning "keep it at 19 in here" into
    (domain=thermostat, slot=target, value=19), and never on the hot path.
    """
    domain: str                                # thermostat | shopping | media ...
    slot: str                                  # target | brand | bedtime ...
    value: str                                 # "19" | "Sumatra" | "21:00"
    holder: str                                # member id who asserted it
    content: str = ""                          # the sentence as actually said
    id: str = field(default_factory=_id)
    stated_at: float = field(default_factory=time.time)

    # Scope: None = the whole household. A member id = about that person only.
    # A belief about one person beats a household-wide one for that person, which
    # is how "we eat at 7" and "the baby eats at 5" coexist without contradiction.
    scope: str | None = None

    # Context the belief was asserted inside. When the context ends, so does the
    # belief. This is the "during the cold snap" problem: the belief was never
    # wrong, it just stopped applying, and no store models that.
    context: str | None = None
    expires_at: float | None = None

    status: str = "active"                     # active | superseded | expired
    superseded_by: str | None = None
    ended_reason: str = ""
    audit: list = field(default_factory=list)

    def key(self) -> tuple:
        """Two beliefs contest each other iff their keys match."""
        return (self.domain, self.slot, self.scope)

    def is_live(self, now: float | None = None) -> bool:
        now = now or time.time()
        if self.status != "active":
            return False
        if self.expires_at is not None and now >= self.expires_at:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id, "domain": self.domain, "slot": self.slot,
            "value": self.value, "holder": self.holder, "content": self.content,
            "stated_at": self.stated_at, "scope": self.scope,
            "context": self.context, "expires_at": self.expires_at,
            "status": self.status, "superseded_by": self.superseded_by,
            "ended_reason": self.ended_reason, "audit": self.audit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Belief":
        b = cls(domain=d["domain"], slot=d["slot"], value=d["value"],
                holder=d["holder"], content=d.get("content", ""))
        b.id = d["id"]
        b.stated_at = d["stated_at"]
        b.scope = d.get("scope")
        b.context = d.get("context")
        b.expires_at = d.get("expires_at")
        b.status = d.get("status", "active")
        b.superseded_by = d.get("superseded_by")
        b.ended_reason = d.get("ended_reason", "")
        b.audit = d.get("audit", [])
        return b


@dataclass
class Resolution:
    """Why one belief won.

    This is the object the whole product is really about. Any store can pick a
    winner; the reason a household can trust an agent that acts on its own is
    that it can show which assertions it weighed, which it set aside, and why.
    Losers are kept, with a per-belief reason, never silently dropped.
    """
    winner: Belief | None
    losers: list = field(default_factory=list)   # [(Belief, reason)]
    basis: str = ""                              # the rule that decided it

    def explain(self, name_of, say=None) -> str:
        """Plain sentence a voice assistant can say out loud.

        `say` renders a belief's value. It defaults to the value as stored,
        which is what the MCP tools answer with, and the surfaces a person reads
        pass hearth.phrasing so the sentence says "19 degrees" and "five" rather
        than 19 and 17:00. The hook lives here rather than a phrasing import
        because the model layer must not depend on how anything is worded.
        """
        if self.winner is None:
            return "Nobody has set that."
        say = say or (lambda b: b.value)
        who, when = name_of(self.winner.holder), _ago(self.winner.stated_at)
        line = f"{who} set it {when}"
        if self.winner.context:
            line += f", during {self.winner.context}"
        line += f", to {say(self.winner)}."
        if self.losers:
            b, why = self.losers[0]
            line += f" {name_of(b.holder)} said {say(b)}, but {why}."
        return line

    def to_dict(self) -> dict:
        return {
            "winner": self.winner.to_dict() if self.winner else None,
            "losers": [{"belief": b.to_dict(), "reason": r} for b, r in self.losers],
            "basis": self.basis,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Resolution":
        """The other half of to_dict, which was missing.

        A resolution is written to disk inside every ledger entry, so without a
        way back the reason an action was taken survives a restart as JSON and
        nothing more. See Ledger.__init__ for what that cost.
        """
        return cls(
            winner=Belief.from_dict(d["winner"]) if d.get("winner") else None,
            losers=[(Belief.from_dict(x["belief"]), x["reason"])
                    for x in d.get("losers", [])],
            basis=d.get("basis", ""))


def _ago(then: float, now: float | None = None) -> str:
    secs = (now or time.time()) - then
    for unit, n in (("week", 604800), ("day", 86400), ("hour", 3600)):
        if secs >= n:
            v = int(secs // n)
            return f"{v} {unit}{'s' if v > 1 else ''} ago"
    return "just now"
