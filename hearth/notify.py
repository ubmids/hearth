"""Telling people: the family board, and a real push to a phone.

A note on the family board used to be the whole of "told Tom": a row that
surfaced only if Tom later asked what he had missed. Now a post also goes out
on each recipient's own channel, when one is configured:

  HEARTH_NOTIFY_TOM=https://ntfy.sh/<topic>     an ntfy push (free; the ntfy
                                                app on a phone buzzes)
  HEARTH_NOTIFY_ADA=https://example.com/hook    any other URL: a JSON webhook

Every delivery is written into the post itself, with its status, so the board
is a per-person inbox that shows what was actually sent and what failed.
Sending happens off the request thread: a phone push is not allowed to spend
the 500 ms the tool call has.
"""
import os
import threading
import time
from urllib.parse import urlparse


def channel_for(name: str) -> str | None:
    if not name:
        return None
    return os.getenv("HEARTH_NOTIFY_" + "".join(c for c in name.upper() if c.isalnum())) or None


def kind_of(url: str) -> str:
    host = urlparse(url).hostname or ""
    return "ntfy" if (host == "ntfy.sh" or host.startswith("ntfy.")
                      or url.startswith("ntfy:")) else "webhook"


def _send(url: str, post: dict, to: str) -> None:
    import httpx
    timeout = float(os.getenv("HEARTH_NOTIFY_TIMEOUT", "8"))
    if kind_of(url) == "ntfy":
        url = url.removeprefix("ntfy:")
        r = httpx.post(url, content=post["text"].encode(), timeout=timeout,
                       headers={"Title": f"Hearth: from {post.get('by') or 'the house'}",
                                "Tags": "house", "Priority": "default"})
    else:
        r = httpx.post(url, timeout=timeout, json={
            "to": to, "from": post.get("by"), "text": post["text"],
            "at": post["at"], "note": post["id"], "source": "hearth"})
    r.raise_for_status()


class Notifier:
    """Sends a board post to each recipient's channel and records how it went."""

    def __init__(self, save=None, background=True, send=_send):
        self.save, self.background, self.send = save, background, send
        self._threads: list[threading.Thread] = []

    def __call__(self, post: dict) -> list[dict]:
        out = []
        for to in post.get("to", []):
            url = channel_for(to)
            if not url:
                continue
            # Every key exists from the start: the send thread only changes
            # values, so saving the book mid-send never sees the dict resize.
            d = {"to": to, "via": kind_of(url), "status": "sending",
                 "at": time.time(), "done_at": None, "error": None}
            out.append(d)
        if out:
            post["delivered"] = out
            if self.background:
                t = threading.Thread(target=self._deliver, args=(post,), daemon=True)
                self._threads.append(t)
                t.start()
            else:
                self._deliver(post)
        return out

    def _deliver(self, post):
        for d in post.get("delivered", []):
            try:
                self.send(channel_for(d["to"]), post, d["to"])
                d["status"] = "sent"
            except Exception as e:      # a dead phone is a status, not a crash
                d["status"] = "failed"
                d["error"] = type(e).__name__
            d["done_at"] = time.time()
        if self.save:
            try:
                self.save()
            except Exception:
                pass

    def wait(self, timeout=10):
        """For tests and shutdown: let pending sends finish."""
        for t in self._threads:
            t.join(timeout)
        self._threads = [t for t in self._threads if t.is_alive()]
