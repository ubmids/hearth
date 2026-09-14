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


@dataclass
class Action:
    what: str                                   # "set the thermostat to 19"
    domain: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    at: float = field(default_factory=time.time)
    resolution: Resolution | None = None
    outcome: str = "done"                       # done | refused | failed

    def to_dict(self) -> dict:
        return {"id": self.id, "what": self.what, "domain": self.domain,
                "at": self.at, "outcome": self.outcome,
                "resolution": self.resolution.to_dict() if self.resolution else None}


class Ledger:
    def __init__(self, household, store=None):
        self.household = household
        self.store = store
        self.actions: list[Action] = store.load_actions() if store else []

    def record(self, what, domain, resolution=None, outcome="done") -> Action:
        a = Action(what=what, domain=domain, resolution=resolution, outcome=outcome)
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
        if a.resolution is None:
            return f"I {a.what}, but I did not record what that was based on."
        return f"I {a.what} because " + a.resolution.explain(self.household.name_of)

    def _find(self, action_id):
        return next((a for a in self.actions if a.id == action_id), None)
