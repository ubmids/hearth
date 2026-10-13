"""The action ledger: what the agent did on its own, and what made it think so.

An agentic assistant that only answers questions can afford to be a black box.
One that acts cannot. The ledger binds every autonomous action to the exact
resolution that justified it, so "why did you do that?" has a real answer and
the household can repair the cause rather than argue with the symptom.
"""
import time
import uuid
from dataclasses import dataclass, field

from .models import Resolution
from .phrasing import value_spoken


@dataclass
class Action:
    what: str                                   # "set the thermostat to 19"
    domain: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    at: float = field(default_factory=time.time)
    resolution: Resolution | None = None
    outcome: str = "done"                       # done | refused | failed
    # Who the action was taken for or at the word of, as the house names them.
    by: str | None = None
    # "hearth": Hearth took the action itself and wrote this at that moment.
    # "reported": the agent told Hearth, through `did`, that it acted. The two
    # are kept apart because only the first is something Hearth can vouch for.
    source: str = "hearth"
    # For a reported action: had the agent asked Hearth about this setting, in
    # the same MCP session, before it says it acted? Read off Hearth's own
    # record of calls, never off the agent's say-so. None when not applicable.
    checked: bool | None = None
    note: str = ""                              # a fact the reason needs, e.g. the dose already given

    def to_dict(self) -> dict:
        return {"id": self.id, "what": self.what, "domain": self.domain,
                "at": self.at, "outcome": self.outcome, "by": self.by,
                "source": self.source, "checked": self.checked, "note": self.note,
                "resolution": self.resolution.to_dict() if self.resolution else None}

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        a = cls(what=d["what"], domain=d["domain"],
                outcome=d.get("outcome", "done"),
                resolution=(Resolution.from_dict(d["resolution"])
                            if d.get("resolution") else None),
                by=d.get("by"), source=d.get("source", "hearth"),
                checked=d.get("checked"), note=d.get("note", ""))
        a.id = d["id"]
        a.at = d["at"]
        return a


class Ledger:
    def __init__(self, household, store=None):
        self.household = household
        self.store = store
        # load_actions hands back raw dictionaries, and this line used to keep
        # them. Every Action attribute access after a restart then hit a dict:
        # `why` raised, the next `did` could not save, and the console's state
        # endpoint returned 500. For a product whose whole claim is that it
        # remembers why it acted, the memory not surviving a restart was the
        # worst bug in the tree, and no test saw it because every test built a
        # ledger in memory and never reopened one.
        self.actions: list[Action] = (
            [Action.from_dict(a) for a in store.load_actions()] if store else [])

    def record(self, what, domain, resolution=None, outcome="done", *, by=None,
               source="hearth", checked=None, note="", at=None) -> Action:
        a = Action(what=what, domain=domain, resolution=resolution, outcome=outcome,
                   by=by, source=source, checked=checked, note=note)
        if at is not None:
            a.at = at
        self.actions.append(a)
        if self.store:
            self.store.save_actions(self.actions)
        return a

    def last(self, domain=None) -> Action | None:
        for a in reversed(self.actions):
            if domain is None or a.domain == domain:
                return a
        return None

    def why(self, action_id=None, domain=None) -> str:
        """The sentence the assistant says when asked why it did something.

        Defaults to the most recent action, because that is what "why did you do
        that?" means out loud. Nobody asks by id.
        """
        a = self._find(action_id) if action_id else self.last(domain)
        if a is None:
            return "I have not done anything like that."
        if a.resolution is None or a.resolution.winner is None:
            line = f"I {a.what}, but I did not record what that was based on."
        else:
            line = (f"I {a.what} because "
                    + a.resolution.explain(self.household.name_of, value_spoken))
        if a.note:
            line += " " + a.note
        if a.source == "reported" and a.checked is False:
            # Hearth's own record says the agent never asked before it acted.
            # Saying so is the difference between a ledger and a diary.
            line += (" That action was reported to me afterwards; I was not "
                     "asked before it was taken.")
        return line

    def _find(self, action_id):
        return next((a for a in self.actions if a.id == action_id), None)
