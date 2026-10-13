"""JSON-file persistence for members, beliefs and the action ledger.

Zero infra in dev, atomic writes so a crash mid-save cannot truncate the house's
history. Swap the internals for a managed store at deploy time; nothing above
this file knows or cares.
"""
import json
import os
import threading

from .models import Belief, Member


class Store:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def _actions_path(self):
        return self.path + ".actions.json"

    def _read(self, path):
        if not os.path.exists(path):
            return None
        with open(path) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return None

    def _write(self, path, data):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)               # atomic

    def load(self):
        with self._lock:
            d = self._read(self.path) or {}
        members = {m["id"]: Member.from_dict(m) for m in d.get("members", [])}
        beliefs = [Belief.from_dict(b) for b in d.get("beliefs", [])]
        return members, beliefs

    def save(self, members, beliefs):
        with self._lock:
            self._write(self.path, {
                "members": [m.to_dict() for m in members.values()],
                "beliefs": [b.to_dict() for b in beliefs],
            })

    def load_actions(self):
        with self._lock:
            return self._read(self._actions_path()) or []

    def save_actions(self, actions):
        with self._lock:
            self._write(self._actions_path(), [a.to_dict() for a in actions])

    # The record of every tool call is one JSON line per call, appended. It
    # used to be rewritten whole on every call, which made each call O(n) in
    # the size of the record: Server-Timing for check_dose went from 2 ms at
    # 500 calls to 22 ms at 3,000 (red-team audit 028, #14). Appending is also
    # what an append-only record should look like on disk.
    #
    # The care services' own books (doses, appointments, orders, the board)
    # are each their own file, so a service that writes often never rewrites
    # the household's beliefs.
    def _trace_path(self):
        return f"{self.path}.trace.jsonl"

    def load_trace(self):
        with self._lock:
            path = self._trace_path()
            if not os.path.exists(path):
                # A record written by the old whole-file format moves over once.
                legacy = self._read(f"{self.path}.trace.json") or []
                if legacy:
                    with open(path, "w") as f:
                        f.writelines(json.dumps(e, sort_keys=True) + "\n"
                                     for e in legacy)
                return legacy
            with open(path) as f:
                lines = [ln for ln in f.read().split("\n") if ln.strip()]
            out = []
            for i, line in enumerate(lines):
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    if i == len(lines) - 1:
                        break         # a crash mid-append tears the last line only
                    # Anywhere else it is damage, and it must show as damage:
                    # an entry that cannot verify, so Trace.verify() reports
                    # the chain broken here rather than quietly ending early.
                    out.append({"seq": len(out) + 1, "at": 0.0, "tool": "(unreadable)",
                                "args": {}, "outcome": "error", "summary": line[:80],
                                "hash": "unreadable"})
            return out

    def append_trace(self, entry: dict):
        with self._lock:
            with open(self._trace_path(), "a") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")

    def load_aux(self, name):
        with self._lock:
            return self._read(f"{self.path}.{name}.json")

    def save_aux(self, name, data):
        with self._lock:
            self._write(f"{self.path}.{name}.json", data)
