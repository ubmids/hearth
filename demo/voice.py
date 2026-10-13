"""The demo, spoken: the scenes from /alexa, rendered to audio offline.

Every line marked Alexa is what the real server returned, over the real bearer
path, from the real tools, chosen by the same planner the simulated client
uses. The household's lines are scripted, because a person saying a sentence
is not the part under test. If the resolver changed tomorrow, this would say
something different.

Voices are Piper (offline, neural, CPU). Point HEARTH_PIPER_DIR at a folder
holding the .onnx voices named below (from huggingface.co/rhasspy/piper-voices).

Writes, next to this file:
  hold-on-rose.m4a   the conversation
  transcript.md      who said what, with timestamps
  hold-on-rose.srt   captions for the video edit

Run: HEARTH_PIPER_DIR=/path/to/voices python3 demo/voice.py
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HEARTH_TZ", "America/New_York")

# The scenes are set at 1:40 in the afternoon, household time, whenever this
# runs, so the morning dose reads "9:10 this morning" as it does on camera.
# The clock is shifted, not frozen: everything still happens in order.
_real = time.time


def _afternoon():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(os.environ["HEARTH_TZ"])
    now = datetime.now(tz)
    return now.replace(hour=13, minute=40, second=0, microsecond=0).timestamp() - now.timestamp()


_shift = _afternoon()
time.time = lambda: _real() + _shift

from fastapi.testclient import TestClient  # noqa: E402

from hearth import sim  # noqa: E402
from hearth.app import create_app  # noqa: E402

VOICES = {"Alexa": "en_US-amy-medium", "Rose": "en_US-kristin-medium",
          "Tom": "en_US-ryan-high", "Ada": "en_US-lessac-medium",
          "Grace": "en_US-hfc_female-medium"}
SCRIPT = [
    ("Rose", "Alexa, I'm just going to take my blood thinner."),
    ("Tom", "Alexa, what did I miss with Mom today?"),
    ("Tom", "Why did you stop her?"),
    ("Ada", "Alexa, Mom's cardiology moved to Thursday at 10. Sort it out."),
    ("Grace", "Alexa, we're nearly out of her warfarin. Reorder it."),
    ("Grace", "Yes, go ahead."),
    ("Tom", "Alexa, can Mom have a coffee?"),
    ("Ada", "Mom finished the antibiotics."),
    ("Ada", "Alexa, show me the record."),
]
RATE = 22050


class Room:
    def __init__(self):
        base = "https://hearth.local"
        self.app = create_app(issuer=base, resource=f"{base}/mcp", seed="care")
        self.c = TestClient(self.app)
        self.h = {"Authorization": "Bearer "
                  + self.app.state.auth.issue_for_testing(subject="demo-house")}
        self.checkout = None
        from piper import PiperVoice
        root = os.environ["HEARTH_PIPER_DIR"]
        self.voices = {who: PiperVoice.load(os.path.join(root, f"{v}.onnx"))
                       for who, v in VOICES.items()}
        self.pcm, self.cues = [], []

    def tool(self, name, args):
        r = self.c.post("/mcp", headers=self.h, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args}}).json()["result"]
        sc = r.get("structuredContent") or {}
        if sc.get("checkout") and sc.get("approved"):
            self.checkout = sc["checkout"]
        return r["content"][0]["text"]

    def pay(self, hint):
        """The host's part, as Alexa+ checkout would do it."""
        made = self.c.post("/checkout-sessions", headers=self.h, json={
            "line_items": hint["line_items"], "buyer": {"first_name": "Grace"},
            "context": {"hearth_quote": hint["quote"]}}).json()
        done = self.c.post(f"/checkout-sessions/{made['id']}/complete",
                           headers={**self.h, "Idempotency-Key": made["id"]}).json()
        total = done["totals"][-1]["amount"]
        return (f"Done. {done['line_items'][0]['item']['title']} is ordered, "
                f"{total // 100} dollars {total % 100}, arriving tomorrow. "
                "I've told the family.")

    def answer(self, who, said):
        plan = sim.plan_rules(said, who, {"checkout": self.checkout})
        out = []
        for call in plan:
            if call.get("host") == "checkout.complete":
                out.append(self.pay(call["checkout"]))
                self.checkout = None
            else:
                out.append(self.tool(call["name"], call["arguments"]))
        return re.sub(r"\s*\[[0-9a-f]{6,}\]", "", " ".join(out)).strip()

    def say(self, who, text, gap=0.6):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            self.voices[who].synthesize_wav(text.replace("$", "").replace("12.40", "12 40"), w)
        buf.seek(0)
        with wave.open(buf) as w:
            rate, frames = w.getframerate(), w.readframes(w.getnframes())
        if rate != RATE:
            frames = _resample(frames, rate)
        start = self.length()
        self.pcm.append(frames)
        self.cues.append((start, self.length(), who, text))
        self.pcm.append(b"\0\0" * int(RATE * gap))

    def length(self):
        return sum(len(p) for p in self.pcm) / 2 / RATE


def _resample(frames, rate):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, "a.wav"), os.path.join(d, "b.wav")
        with wave.open(a, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(frames)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a, "-ar", str(RATE),
                        "-ac", "1", b], check=True)
        with wave.open(b) as w:
            return w.readframes(w.getnframes())


def _ts(t, srt=False):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return (f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",") if srt
            else f"{int(m)}:{s:04.1f}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    room = Room()
    for who, line in SCRIPT:
        print(f"  {who:>5}: {line}")
        room.say(who, line, gap=0.45)
        reply = room.answer(who, line)
        print(f"  Alexa: {reply}\n")
        room.say("Alexa", reply, gap=1.0)
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "demo.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
            w.writeframes(b"".join(room.pcm))
        out = os.path.join(here, "hold-on-rose.m4a")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "aac",
                        "-b:a", "64k", out], check=True)
    with open(os.path.join(here, "transcript.md"), "w") as f:
        f.write("# Hold on, Rose\n\nThe scenes from the simulated Alexa+ client, "
                "rendered offline by `demo/voice.py`. Every **Alexa** line is the "
                "text Hearth's tools returned for that request, over the real "
                "MCP endpoint. Voices: Piper, offline.\n\n")
        for start, end, who, text in room.cues:
            f.write(f"- `{_ts(start)}` **{who}**: {text}\n")
    with open(os.path.join(here, "hold-on-rose.srt"), "w") as f:
        for i, (start, end, who, text) in enumerate(room.cues, 1):
            f.write(f"{i}\n{_ts(start, True)} --> {_ts(end, True)}\n{who}: {text}\n\n")
    print(f"wrote {out} ({room.length():.1f}s)")


if __name__ == "__main__":
    main()
