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
Entries are hash-chained. A chain on its own only proves it is consistent
with itself: cut entries off the end, or edit one and recompute every hash
after it, and it still checks. So the head is anchored in two places the
record file does not control:

  checkpoints  after every append, the server signs (seq, hash) with an
               Ed25519 key that is not in the record file (HEARTH_RECORD_KEY,
               or a key file) and appends it to a separate witness file.
               Truncation, an edit (rehashed or not), a reorder or a deletion
               no longer matches the signed checkpoints.
  receipts     every tool result carries {seq, hash}. A client that keeps the
               last one can present it to `record`, which checks the entry at
               that seq still has that hash. That is the check that holds
               even against someone who has the signing key and rewrites both
               files, for every entry up to the receipt.

What this does not do: stop someone who holds the key from rewriting entries
after the newest receipt any client kept. The copy says exactly that.

Nothing here is a model call or a network call: a dictionary, a SHA-256 and
one signature per call, inside the 500ms the read path has to fit.
"""
import base64
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field

GENESIS = "0" * 64


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


_EPHEMERAL = None


def load_key(key_file: str | None = None):
    """The record's signing key. HEARTH_RECORD_KEY (a base64url 32-byte
    Ed25519 seed) wins; else HEARTH_RECORD_KEY_FILE or `key_file`, created
    on first use; else one key for the life of this process."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    global _EPHEMERAL
    env = os.getenv("HEARTH_RECORD_KEY")
    if env:
        return Ed25519PrivateKey.from_private_bytes(_unb64(env.strip()))
    path = os.getenv("HEARTH_RECORD_KEY_FILE") or key_file
    if path:
        if os.path.exists(path):
            with open(path) as f:
                return Ed25519PrivateKey.from_private_bytes(_unb64(f.read().strip()))
        seed = os.urandom(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(_b64(seed))
        return Ed25519PrivateKey.from_private_bytes(seed)
    if _EPHEMERAL is None:
        _EPHEMERAL = Ed25519PrivateKey.generate()
    return _EPHEMERAL


def public_key_b64(key) -> str:
    from cryptography.hazmat.primitives import serialization
    return _b64(key.public_key().public_bytes(serialization.Encoding.Raw,
                                              serialization.PublicFormat.Raw))


def _message(seq: int, h: str) -> bytes:
    return f"hearth-record:{seq}:{h}".encode()


def verify_checkpoint(public_key: str, cp: dict) -> bool:
    """Anyone with the published public key can check a checkpoint."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(_unb64(public_key)).verify(
            _unb64(cp["sig"]), _message(int(cp["seq"]), cp["hash"]))
        return True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False


class Witness:
    """Signed checkpoints of the record's head, kept apart from the record."""

    def __init__(self, path: str | None = None, key_file: str | None = None):
        self.path = path
        self.key = load_key(key_file)
        self.public_key = public_key_b64(self.key)
        self.checkpoints: list[dict] = []
        if path and os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try:
                        self.checkpoints.append(json.loads(line))
                    except json.JSONDecodeError:
                        break               # a torn last line: a crash mid-write

    def sign(self, seq: int, h: str) -> dict:
        cp = {"seq": seq, "hash": h, "key": self.public_key[:16],
              "sig": _b64(self.key.sign(_message(seq, h)))}
        self.checkpoints.append(cp)
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(cp, sort_keys=True) + "\n")
        return cp

    def latest(self) -> dict | None:
        return self.checkpoints[-1] if self.checkpoints else None


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
    """Append-only, hash-chained, persisted alongside the household, with its
    head signed into a separate witness file after every call."""

    def __init__(self, store=None, witness: Witness | None = None):
        self.store = store
        self.entries: list[Entry] = (
            [Entry.from_dict(e) for e in store.load_trace()] if store else [])
        if witness is None:
            witness = Witness(*store.witness_paths()) if store else Witness()
        self.witness = witness
        if store is not None and getattr(store, "migrated_legacy", False) \
                and not witness.checkpoints and self.entries:
            # A record carried over from the old whole-file format had no
            # checkpoints; it is anchored once, as it stood when it moved.
            for e in self.entries:
                witness.sign(e.seq, e.hash)

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
        # Signed after the entry is on disk, so a crash between the two
        # leaves one entry past the newest checkpoint, never a checkpoint
        # with no entry.
        self.witness.sign(e.seq, e.hash)
        return e

    def audit(self, receipt: dict | None = None) -> dict:
        """Check the record against itself, its signed checkpoints, and (if
        given) a receipt {seq, hash} a client kept from an earlier call.

        Returns {"intact", "broken_at", "reason", "count", "checkpoint",
        "receipt"}. `broken_at` is the first seq that does not hold up."""
        n = len(self.entries)
        out = {"intact": True, "broken_at": None, "reason": None, "count": n,
               "checkpoint": None, "receipt": None}

        def broken(seq, why):
            out.update(intact=False, broken_at=seq, reason=why)
            return out

        prev = GENESIS
        for i, e in enumerate(self.entries, start=1):
            if e.seq != i or e.prev != prev or e.digest() != e.hash:
                return broken(i, "the chain does not link at this entry")
            prev = e.hash
        cps = self.witness.checkpoints
        last = cps[-1] if cps else None
        if last is None:
            if n:
                return broken(1, "there are no signed checkpoints for this record")
        else:
            if not verify_checkpoint(self.witness.public_key, last):
                return broken(int(last.get("seq", 0)) or 1,
                              "the newest checkpoint is not signed by this server's key")
            for cp in cps:
                seq = int(cp["seq"])
                if seq > n:
                    return broken(n + 1, f"entries {n + 1} to {last['seq']} were "
                                         "signed for and are missing")
                if self.entries[seq - 1].hash != cp["hash"]:
                    return broken(seq, "this entry is not the one that was signed for")
            if n - int(last["seq"]) > 1:
                return broken(int(last["seq"]) + 2, "entries after the newest "
                                                    "checkpoint were never signed for")
            out["checkpoint"] = {"seq": int(last["seq"]), "hash": last["hash"]}
        if receipt:
            try:
                seq, h = int(receipt.get("seq")), str(receipt.get("hash") or "")
            except (TypeError, ValueError, AttributeError):
                return broken(None, "the receipt is not a {seq, hash} pair")
            if seq > n:
                return broken(n + 1, f"this device holds a receipt for entry {seq}, "
                                     f"and the record ends at {n}")
            if len(h) < 16 or not self.entries[seq - 1].hash.startswith(h):
                return broken(seq, "this entry does not match the receipt this "
                                   "device holds")
            out["receipt"] = {"seq": seq}
        return out

    def verify(self, receipt: dict | None = None) -> tuple[bool, int | None]:
        """(True, None) if the record holds up, else (False, first bad seq)."""
        a = self.audit(receipt)
        return a["intact"], a["broken_at"]

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
