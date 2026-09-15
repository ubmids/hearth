"""The demo, spoken.

Hearth's whole claim is about something you hear: an assistant that acts on its
own, and can tell you why. Read on a page that is an idea. Heard in a room it is
either obvious or it is nothing, and there is no way to find out which by
looking at a console.

Amazon's rules allow "a simulated Alexa+ experience built using any AI or
agentic tool", which is what this is. The one rule it holds to: **every line the
assistant says comes back from the real server**, over HTTP, through the real
bearer path, from the real resolver. The household's lines are scripted because
a person saying a sentence is not the part under test. The assistant's are not
scripted at all, and if the resolution logic changed tomorrow this demo would
say something different.

That distinction is the difference between a demo and a mock-up, and it is worth
more than any amount of polish: a judge who suspects the answers are hardcoded
has learned nothing from watching it.

Run: python3 demo/voice.py
"""
import os
import re
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from hearth.app import create_app

# A cast, so the ear can tell three people apart without being told.
DAD, ADA, ALEXA = "Daniel", "Junior", "Samantha"

BASE = "https://hearth.local"
WEEK = 7 * 24 * 3600


class Room:
    """One household, one server, one running tape."""

    def __init__(self, out_dir):
        self.app = create_app(issuer=BASE, resource=f"{BASE}/mcp", seed=True)
        self.client = TestClient(self.app)
        self.token = self.app.state.auth.issue_for_testing(subject="demo-house")
        self.dir = out_dir
        self.clips = []
        self.transcript = []

    # --- the real server -------------------------------------------------
    def _tool(self, name, **args):
        r = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": name, "arguments": args}},
            headers={"Authorization": f"Bearer {self.token}"})
        r.raise_for_status()
        return r.json()["result"]["content"][0]["text"]

    # --- the tape --------------------------------------------------------
    def _speak(self, voice, text, rate=None):
        stem = os.path.join(self.dir, f"{len(self.clips):03d}")
        aiff, wav = stem + ".aiff", stem + ".wav"
        cmd = ["say", "-v", voice, "-o", aiff]
        if rate:
            cmd += ["-r", str(rate)]
        subprocess.run(cmd + [text], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", aiff,
                        "-ac", "1", "-ar", "22050", wav],
                       check=True, capture_output=True)
        os.remove(aiff)
        self.clips.append(wav)
        return wav

    def silence(self, seconds):
        stem = os.path.join(self.dir, f"{len(self.clips):03d}.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", f"anullsrc=r=22050:cl=mono", "-t", str(seconds),
                        stem], check=True, capture_output=True)
        self.clips.append(stem)

    def backdate_last(self, seconds):
        """Move the most recent belief back in time, for the narration's sake."""
        house, _led, _srv = self.app.state.home_for("demo-house")
        if house.beliefs:
            house.beliefs[-1].stated_at -= seconds

    def person(self, who, voice, line):
        self.transcript.append((who, line))
        print(f"  {who:>6}: \"{line}\"")
        self._speak(voice, line)
        self.silence(0.55)

    def assistant(self, line):
        """Say what the server said. Never what the script wished it said.

        One thing is removed and only one: the belief reference in brackets.
        A tool result is read by a model, which composes the spoken reply, and
        the reference exists so it can stand a belief down later. Reading a hex
        string aloud is not a thing any assistant does, and leaving it in would
        misrepresent the product rather than be faithful to it. The sentence
        itself is untouched.
        """
        spoken = re.sub(r"\s*\[[0-9a-f]{6,}\]", "", line).strip()
        self.transcript.append(("Alexa", line))
        print(f"   Alexa: {spoken}")
        self._speak(ALEXA, spoken, rate=185)
        self.silence(0.7)

    def narrate(self, line):
        print(f"\n  [{line}]")
        self.transcript.append(("", f"[{line}]"))
        self._speak("Moira", line, rate=165)
        self.silence(0.9)

    def render(self, out_path):
        lst = os.path.join(self.dir, "list.txt")
        with open(lst, "w") as f:
            for c in self.clips:
                f.write(f"file '{c}'\n")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat",
                        "-safe", "0", "-i", lst, "-ac", "1", "-ar", "22050",
                        out_path], check=True, capture_output=True)
        with wave.open(out_path) as w:
            return w.getnframes() / float(w.getframerate())


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    tmp = tempfile.mkdtemp(prefix="hearth-voice-")
    r = Room(tmp)

    r.narrate("Three weeks ago, during a cold snap.")
    r.person("Dad", DAD, "Alexa, turn it up to twenty four, it's freezing.")
    r.assistant(r._tool("remember", said="turn it up to 24 during the cold snap",
                        speaker="Dad"))
    # The story turns on this being old. The `remember` tool stamps the moment
    # it is called, which is correct for a tool and wrong for a demo pretending
    # three weeks passed, so the clock is moved back here rather than the
    # assistant being made to say something untrue about when it was told.
    r.backdate_last(WEEK * 3)

    r.narrate("This morning.")
    r.person("Ada", ADA, "Alexa, make it twenty.")
    r.assistant(r._tool("remember", said="make it 20", speaker="Ada"))

    # The assistant acts on its own. This is the moment that needs explaining.
    r.assistant(r._tool("did", what="set the thermostat",
                        domain="thermostat", slot="target"))

    r.person("Ada", ADA, "Alexa, why is it so warm in here?")
    r.assistant(r._tool("why", domain="thermostat"))

    r.narrate("The cold snap ended two weeks ago. Nobody told it.")

    r.person("Dad", DAD, "Alexa, the cold snap is over.")
    r.assistant(r._tool("remember", said="the cold snap is over", speaker="Dad"))
    r.assistant(r._tool("did", what="set the thermostat",
                        domain="thermostat", slot="target"))
    r.person("Ada", ADA, "Alexa, why did you change it?")
    r.assistant(r._tool("why", domain="thermostat"))

    wav = os.path.join(tmp, "demo.wav")
    length = r.render(wav)
    # Committed as m4a: the wav is several megabytes of a repository that goes
    # public, and nothing about this demo needs lossless audio.
    path = os.path.join(out, "why-did-you-do-that.m4a")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav,
                    "-c:a", "aac", "-b:a", "64k", path],
                   check=True, capture_output=True)
    print(f"\n  wrote {path}  ({length:.1f}s, "
          f"{os.path.getsize(path)//1024}KB)")

    with open(os.path.join(out, "transcript.md"), "w") as f:
        f.write("# Why did you do that\n\n")
        f.write("Every line marked **Alexa** is the response the real server "
                "returned over HTTP, not a script.\n\n")
        for who, line in r.transcript:
            f.write(f"- **{who}**: {line}\n" if who else f"\n_{line}_\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
