"""The record: every tool call, written by the server at the moment it happens.

The action ledger used to be only as honest as the agent. Hearth did not take
actions, Alexa+ did, and then called `did` to say what it had done and why. A
model that skipped the call, or reported something it never checked, left no
trace, and "why did you do that?" was answered from the agent's own account of
itself. That is a diary, not a ledger.

This is the other half. `HearthMCP.handle` writes one entry here for every
`tools/call` it serves, before the response leaves, whatever the agent later
chooses to say. Each entry names the tool, its arguments, the outcome, the
beliefs it read and the ones it wrote, the MCP session, and how long it took.
Entries are hash-chained, so an entry edited or removed after the fact breaks
`verify()` at that point and every entry after it.

Nothing here is a model call or a network call: it is a dictionary and a
SHA-256, inside the 500ms the read path has to fit.
"""
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field

GENESIS = "0" * 64


@dataclass
class Entry:
    seq: int
    at: float
    tool: str
    args: dict
    outcome: str                         # ok | refused | error
    summary: str                         # the first line of what was answered
    session: str | None = None
    reads: list = field(default_factory=list)      # belief ids consulted
    writes: list = field(default_factory=list)     # belief / record ids written
    action: str | None = None            # ledger action id, if one was taken
    ms: float = 0.0
    prev: str = GENESIS
    hash: str = ""

    def body(self) -> dict:
        d = asdict(self)
        d.pop("hash")
        return d

    def digest(self) -> str:
        raw = json.dumps(self.body(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Entry":
        return cls(**d)


class Trace:
    """Append-only, hash-chained, persisted alongside the household."""

    def __init__(self, store=None):
        self.store = store
        self.entries: list[Entry] = (
            [Entry.from_dict(e) for e in store.load_trace()] if store else [])

    def append(self, *, tool, args, outcome, summary, session=None,
               reads=(), writes=(), action=None, ms=0.0, at=None) -> Entry:
        prev = self.entries[-1].hash if self.entries else GENESIS
        e = Entry(seq=len(self.entries) + 1, at=at or time.time(), tool=tool,
                  args=_clean(args), outcome=outcome, summary=summary[:240],
                  session=session, reads=list(reads), writes=list(writes),
                  action=action, ms=round(ms, 3), prev=prev)
        e.hash = e.digest()
        self.entries.append(e)
        if self.store:
            self.store.append_trace(e.to_dict())       # one line, O(1)
        return e

    def verify(self) -> tuple[bool, int | None]:
        """(True, None) if the chain is intact, else (False, first bad seq)."""
        prev = GENESIS
        for i, e in enumerate(self.entries, start=1):
            if e.seq != i or e.prev != prev or e.digest() != e.hash:
                return False, i
            prev = e.hash
        return True, None

    def head(self) -> str:
        return self.entries[-1].hash if self.entries else GENESIS

    def since(self, at: float) -> list[Entry]:
        return [e for e in self.entries if e.at > at]

    def last_by(self, speaker: str, tools=None) -> Entry | None:
        """The last call made on behalf of a named person, which is how Hearth
        knows when somebody last asked anything, across sessions and devices."""
        who = (speaker or "").lower()
        for e in reversed(self.entries):
            # `person` is the asker only for catch_up; elsewhere it is the
            # person being cared for, who did not necessarily say anything.
            named = str(e.args.get("speaker") or e.args.get("asked_by")
                        or e.args.get("given_by") or e.args.get("by")
                        or (e.args.get("person") if e.tool == "catch_up" else "")
                        or "").lower()
            if named == who and (tools is None or e.tool in tools):
                return e
        return None

    def consulted(self, domain: str, slot: str, session: str | None,
                  within: float = 600.0, now=None) -> Entry | None:
        """Did the agent ask Hearth about this setting, in this session, shortly
        before it says it acted on it? The answer is Hearth's own record, not the
        agent's account."""
        now = now or time.time()
        for e in reversed(self.entries):
            if now - e.at > within:
                break
            if (e.tool == "whats_true" and e.session == session
                    and e.args.get("domain") == domain
                    and e.args.get("slot") == slot):
                return e
        return None


def _clean(args) -> dict:
    """Arguments as they arrived, made JSON-safe and bounded. A model can send
    anything, and the record of what it sent must not be what breaks."""
    out = {}
    for k, v in (args or {}).items() if isinstance(args, dict) else []:
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)] = v if not isinstance(v, str) else v[:500]
        else:
            out[str(k)] = json.dumps(v, default=str)[:500]
    return out
