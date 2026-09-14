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
