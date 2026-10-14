"""'Told Tom' means Tom's phone got it, and the board says whether it did.

A fake ntfy server stands in for ntfy.sh: the test checks the push that
arrives there, the delivery status written on the board post, Tom's inbox,
and what Alexa says, with a channel configured and without one.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HEARTH_TZ", "America/New_York")

from hearth import notify

from test_care import House

GOT = []


class Ntfy(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        GOT.append({"path": self.path, "title": self.headers.get("Title"), "body": body})
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


def test_arrange_pushes_the_note_to_toms_phone_and_says_so():
    srv = HTTPServer(("127.0.0.1", 0), Ntfy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["HEARTH_NOTIFY_TOM"] = f"ntfy:http://127.0.0.1:{srv.server_port}/hearth-tom"
    try:
        house = House()
        out = house.call("arrange", what="cardiology", when="Thursday at 10am", asked_by="Ada")
        speech = out["content"][0]["text"]
        assert "left a note for Tom and Grace on the family board and sent it to " \
               "Tom's phone" in speech, speech
        assert out["structuredContent"]["notified"] == [{"to": "Tom", "via": "ntfy"}]
        house.server.care.book.notifier.wait()
        assert GOT and GOT[-1]["path"] == "/hearth-tom", GOT
        assert "cardiology is now Thursday" in GOT[-1]["body"], GOT[-1]
        post = house.server.care.book.board[-1]
        assert post["delivered"][0]["status"] == "sent", post
        inbox = house.c.get("/inbox/tom", headers=house.headers).json()
        assert inbox["notes"][0]["phone"]["status"] == "sent", inbox
        assert house.c.get("/inbox/tom").status_code == 401
    finally:
        os.environ.pop("HEARTH_NOTIFY_TOM", None)
        srv.shutdown()
    print("PASS Tom's phone gets the note, and the board records that it did")


def test_without_a_channel_the_board_is_all_and_alexa_says_only_that():
    house = House()
    speech = house.say("arrange", what="cardiology", when="Thursday at 10am", asked_by="Ada")
    assert "left a note for Tom and Grace on the family board." in speech, speech
    assert "phone" not in speech, speech
    assert "delivered" not in house.server.care.book.board[-1]
    print("PASS without a channel nobody is said to have been pushed")


def test_a_failed_push_is_a_status_not_a_crash():
    os.environ["HEARTH_NOTIFY_TOM"] = "http://127.0.0.1:9/hook"      # nothing listens
    try:
        n = notify.Notifier(background=False)
        post = {"id": "note_x", "at": 0, "to": ["Tom", "Grace"], "by": "Ada", "text": "hi"}
        n(post)
        assert post["delivered"] == [{"to": "Tom", "via": "webhook", "status": "failed",
                                      "at": post["delivered"][0]["at"],
                                      "done_at": post["delivered"][0]["done_at"],
                                      "error": post["delivered"][0]["error"]}], post
        assert post["delivered"][0]["error"]
    finally:
        os.environ.pop("HEARTH_NOTIFY_TOM", None)
    print("PASS a failed push is recorded as failed")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall green (notify)")
