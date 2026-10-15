"""Assemble the whole demo video from a film.py take, the title cards, and
whatever real footage exists. Anything not yet filmed is a labelled
placeholder, so the cut is watchable today and becomes the final video as the
real pieces are dropped in. docs/video/SCRIPT.md is the script it follows.

    python3 demo/rough_cut.py ~/Desktop/hackathons/hearth-video/take1 \\
        [--inserts=~/Desktop/hackathons/hearth-video/inserts] [--skip=record]

--skip drops segments by name (hero, oncam, handover, buzz, catchup, arrange,
order, amazon, record, tech, close) when a take runs long.

Inserts (real footage, any format ffmpeg reads; drop them in and run again):

  oncam.mp4    Subomi, or a carer, to camera, about 13 s (else: the stats
               card with a placeholder narrator)
  buzz.mp4     Ada's phone getting the push, about 3 s (else: a slate)
  amazon.mp4   the classic skill in the Alexa developer console's simulator,
               about 10 s (else: a slate)
  n-traffic.m4a, n-tech.m4a, n-close.m4a, n-oncam.m4a
               narration in a real voice (else: macOS `say`, voice Daniel)

Writes <take>/hearth-demo.mp4, hearth-demo.srt (captions for the upload) and <take>/cut.json (each segment, its source,
its length, and whether it is still a placeholder). macOS only (`say`); needs
ffmpeg and playwright.
"""
import asyncio
import json
import os
import pathlib
import subprocess
import sys
from urllib.parse import urlencode

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
W, H, FPS = 1920, 1080, 30
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
       "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]

NARRATION = {
    "traffic": "Over MCP, a model chose give dose. Hearth's server refused it, "
               "and signed the refusal into the record.",
    "oncam": "I built Hearth for families splitting the care of a parent: a daughter "
             "with the doctor's letters, a son two states away, an aide on weekday "
             "mornings. Nobody holds the whole picture. That gap is where doses get doubled.",
    "tech": "MCP 2025-11-25, passing the official conformance suite. And the model "
            "choosing every call is a small open one on this laptop. It doesn't need "
            "to know warfarin. Hearth does.",
    "close": "Hearth. The memory, and the conscience, of a family caring for someone.",
}

# Lower thirds over the simulated Alexa+ footage: (segment, from s, to s, tag, text, sub).
THIRDS = [
    ("hero", 0.0, 4.5, "Simulated Alexa+", "Hearth, an Alexa+ add-on on MCP 2025-11-25", ""),
    ("hero", "traffic-on", "traffic-off", "MCP traffic, live", "The server refused it, not the model", ""),
    ("handover", 0.5, 9.0, "One sentence", "The handover, the shopping list, and a flag",
     "To the person with the say over Mom's health"),
    ("catchup", 0.5, 8.0, "Memory", "Across sessions, people and devices", "Tom is two states away"),
    ("arrange", 0.5, 8.0, "One request", "Calendar, rota, ride, family board, phone",
     "The ride provider is a sandbox"),
    ("order", 0.5, 8.0, "The list Grace started", "Paid the Alexa+ way: UCP checkout",
     "Sandbox pharmacy, no card charged"),
    ("record", 0.5, 8.0, "An honest record", "Every call signed as it happens",
     "With a receipt kept off the server"),
]


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def has_audio(path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                          "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout
    return bool(out.strip())


def first(d: pathlib.Path, stem: str, exts) -> pathlib.Path | None:
    for e in exts:
        p = d / f"{stem}.{e}"
        if p.exists():
            return p
    return None


async def render_cards(specs: dict, out: pathlib.Path):
    """{name: query dict} -> out/<name>.png, transparent for lower thirds."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": W, "height": H})
        for name, q in specs.items():
            await page.goto((HERE / "cards.html").as_uri() + "?" + urlencode(q))
            await page.evaluate("document.fonts.ready")       # the label type
            await page.wait_for_timeout(150)
            await page.screenshot(path=str(out / f"{name}.png"),
                                  omit_background=q.get("card") == "third")
        await b.close()


class Cut:
    def __init__(self, take: pathlib.Path, inserts: pathlib.Path):
        self.take, self.inserts = take, inserts
        self.work = take / "cut"
        self.work.mkdir(exist_ok=True)
        self.parts = []                      # (file, record)

    def narration(self, key) -> tuple[pathlib.Path, bool]:
        real = first(self.inserts, f"n-{key}", ("m4a", "wav", "aiff", "mp3", "caf"))
        if real:
            return real, True
        p = self.work / f"n-{key}.aiff"
        run(["say", "-v", "Daniel", "-r", "178", "-o", str(p), NARRATION[key]])
        return p, False

    skip = set()

    def add(self, name, path, source, placeholder):
        if name in self.skip:
            return
        self.parts.append((path, {"segment": name, "source": source,
                                  "seconds": round(duration(path), 2),
                                  "placeholder": placeholder}))

    def card(self, name, png, seconds=None, audio=None, placeholder=False, source="card"):
        out = self.work / f"{len(self.parts):02d}-{name}.mp4"
        if audio:
            seconds = seconds or duration(audio) + 0.8
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{seconds:.2f}",
                   "-i", str(png), "-i", str(audio), "-filter_complex",
                   f"[1:a]apad,atrim=0:{seconds:.2f}[a]", "-map", "0:v", "-map", "[a]"]
        else:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{seconds:.2f}",
                   "-i", str(png), "-f", "lavfi", "-t", f"{seconds:.2f}",
                   "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a"]
        run(cmd + ENC + ["-t", f"{seconds:.2f}", str(out)])
        self.add(name, out, source, placeholder)

    def insert(self, name, clip, third=None):
        """Real footage, fitted to 1920x1080 without stretching, with an
        optional lower third (png, from s, to s)."""
        out = self.work / f"{len(self.parts):02d}-{name}.mp4"
        fit = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
               f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0b0d10,fps={FPS},format=yuv420p")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip)]
        audio = "0:a"
        if not has_audio(clip):
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest"]
            audio = "1:a"
        graph = f"[0:v]{fit}[v]"
        if third:
            png, a, b = third
            cmd += ["-i", str(png)]
            k = 2 if audio == "1:a" else 1
            graph += f";[v][{k}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[v2]"
        cmd += ["-filter_complex", graph, "-map", "[v2]" if third else "[v]", "-map", audio]
        run(cmd + ENC + [str(out)])
        self.add(name, out, str(clip), False)

    def sim(self, name, start, end, thirds, narr=None, narr_at=0.0):
        """A stretch of sim-run.mp4, with lower thirds and optional narration."""
        out = self.work / f"{len(self.parts):02d}-{name}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
               "-i", str(self.take / "sim-run.mp4")]
        for png, *_ in thirds:
            cmd += ["-i", str(png)]
        graph, v = [], "[0:v]"
        for i, (png, a, b) in enumerate(thirds, 1):
            graph.append(f"{v}[{i}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[v{i}]")
            v = f"[v{i}]"
        a = "[0:a]"
        if narr:
            cmd += ["-i", str(narr)]
            k = len(thirds) + 1
            graph.append(f"[{k}:a]adelay={int(narr_at * 1000)}:all=1[n];"
                         f"[0:a]volume=0.55[s];[s][n]amix=inputs=2:normalize=0:duration=first[a]")
            a = "[a]"
        if graph:
            cmd += ["-filter_complex", ";".join(graph), "-map", v if thirds else "0:v",
                    "-map", a if narr else "0:a"]
        run(cmd + ENC + [str(out)])
        self.add(name, out, "sim-run.mp4", False)
        if self.parts and self.parts[-1][1]["segment"] == name:
            self.parts[-1][1]["take_span"] = [round(start, 3), round(end, 3)]

    def captions(self, recs):
        """hearth-demo.srt: every spoken line of the take, at its time in the cut."""
        from film import _stamp
        ev = json.loads((self.take / "timeline.json").read_text())["events"]
        lines = [e for e in ev if e["kind"] == "line"]
        out, at, n = [], 0.0, 0
        for r in recs:
            if "take_span" in r:
                a, b = r["take_span"]
                for e in lines:
                    if a <= e["at"] < b:
                        t = at + e["at"] - a
                        end = min(at + r["seconds"], t + e["seconds"])
                        n += 1
                        out += [str(n), f"{_stamp(t, True)} --> {_stamp(end, True)}",
                                f"{e['who']}: {e['text']}", ""]
            at += r["seconds"]
        (self.take / "hearth-demo.srt").write_text("\n".join(out))

    def finish(self) -> pathlib.Path:
        lst = self.work / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p, _ in self.parts))
        final = self.take / "hearth-demo.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(final)])
        recs = [r for _, r in self.parts]
        total = duration(final)
        self.captions(recs)
        (self.take / "cut.json").write_text(json.dumps(
            {"total_seconds": round(total, 2), "segments": recs}, indent=1))
        return final


def main(take: pathlib.Path, inserts: pathlib.Path, skip=()):
    tl = json.loads((take / "timeline.json").read_text())
    ev = tl["events"]
    at = {e["kind"]: e["at"] for e in ev if e["kind"] in ("ready", "traffic-on", "traffic-off")}
    ends = {e["scene"]: e["at"] for e in ev if e["kind"] == "scene-end"}
    scene_of = {e["scene"]: e["who"] for e in ev if e["kind"] == "line" and e["who"] != "Alexa"}
    placeholder_voices = [e["who"] for e in ev if e["kind"] == "line"
                          and e["who"] != "Alexa" and not e.get("real_voice")]
    # Scenes, by who speaks: 0 Rose, 1 Grace, 2 Tom, 3 Ada (sort it out),
    # 4 Ada (order), 5 Ada (yes), 6 Ada (record).
    assert len(ends) == 7, f"expected the 7 film scenes, got {scene_of}"
    cut = Cut(take, inserts)
    cut.skip = set(skip)

    tech_text = None
    conf = inserts / "conformance.txt"
    if conf.exists():
        tech_text = "\n".join(l for l in conf.read_text().splitlines() if l.startswith("PASS"))
    specs = {"stats": {"card": "stats"},
             "stats-todo": {"card": "stats", "tag": "Placeholder: Subomi on camera", "todo": "1"},
             "buzz": {"card": "slate", "text": "Ada's phone buzzes.",
                      "sub": "A real ntfy push: \"Grace flagged at handover: she was a bit dizzy after her walk.\"",
                      "tag": "Placeholder: film the phone", "todo": "1"},
             "amazon": {"card": "slate", "text": "The same server, on Amazon's own Alexa.",
                        "sub": "A classic Alexa skill in the developer console simulator, calling Hearth over MCP.",
                        "tag": "Placeholder: record the console", "todo": "1"},
             "tech": {"card": "tech", **({"text": tech_text} if tech_text else {})},
             "close": {"card": "close"}}
    specs["third-oncam"] = {"card": "third", "tag": "Why", "pos": "low",
                            "text": "63M Americans care for a family member (AARP 2025)",
                            "sub": "Warfarin is in 1 in 3 overdose hospitalisations of older adults (NEJM 2011)"}
    for i, (seg, a, b, tag, text, sub) in enumerate(THIRDS):
        # Film mode's middle column has room under the device; while the
        # traffic panel is out, the third sits low, bottom left.
        specs[f"third{i}"] = {"card": "third", "tag": tag, "text": text, "sub": sub,
                              "pos": "low" if a == "traffic-on" else "right"}
    asyncio.run(render_cards(specs, cut.work))

    # A scene's lower third comes up with Alexa's answer, not while the
    # person is still talking: its times count from that answer.
    replies = {}
    for e in ev:
        if e["kind"] == "line" and e["who"] == "Alexa":
            replies.setdefault(e["scene"], e["at"])
    first_scene = {"handover": 1, "catchup": 2, "arrange": 3, "order": 4, "record": 6}

    def thirds(seg, origin):
        out = []
        shift = 0.0
        if seg in first_scene:
            n = first_scene[seg]
            shift = replies[n] - ends[n - 1]           # when Alexa answers, in the segment
        for i, (s, a, b, *_rest) in enumerate(THIRDS):
            if s != seg:
                continue
            a = (at[a] - origin) if isinstance(a, str) else a + shift
            b = (at[b] - origin) if isinstance(b, str) else b + shift
            out.append((cut.work / f"third{i}.png", a, b))
        return out

    # 0:00 the hero and the one look at the traffic.
    t0 = max(0.0, at["ready"] - 0.2)
    n, real = cut.narration("traffic")
    cut.sim("hero", t0, ends[0], thirds("hero", t0), narr=n, narr_at=at["traffic-on"] - t0 + 0.3)
    # Why it matters: a real person, or the stats with a placeholder voice.
    clip = first(inserts, "oncam", ("mp4", "mov", "m4v"))
    if clip:
        cut.insert("oncam", clip, third=(cut.work / "third-oncam.png", 1.0, 9.0))
    else:
        n, real = cut.narration("oncam")
        cut.card("oncam", cut.work / ("stats.png" if real else "stats-todo.png"),
                 audio=n, placeholder=not real, source="stats card + narration")
    # The afternoon: handover, the push, Tom's catch-up, sort it out, the order.
    cut.sim("handover", ends[0], ends[1], thirds("handover", 0))
    clip = first(inserts, "buzz", ("mp4", "mov", "m4v"))
    cut.insert("buzz", clip) if clip else cut.card("buzz", cut.work / "buzz.png", 3.0,
                                                   placeholder=True, source="slate")
    cut.sim("catchup", ends[1], ends[2], thirds("catchup", 0))
    cut.sim("arrange", ends[2], ends[3], thirds("arrange", 0))
    cut.sim("order", ends[3], ends[5], thirds("order", 0))
    # The one Amazon surface an entrant can reach.
    clip = first(inserts, "amazon", ("mp4", "mov", "m4v"))
    cut.insert("amazon", clip) if clip else cut.card("amazon", cut.work / "amazon.png", 8.0,
                                                     placeholder=True, source="slate")
    cut.sim("record", ends[5], ends[6], thirds("record", 0))
    n, real = cut.narration("tech")
    cut.card("tech", cut.work / "tech.png", audio=n, placeholder=not real,
             source="conformance card + narration")
    n, real = cut.narration("close")
    cut.card("close", cut.work / "close.png", audio=n, placeholder=not real,
             source="close card + narration")
    final = cut.finish()
    report = json.loads((take / "cut.json").read_text())
    for r in report["segments"]:
        print(f"{r['seconds']:6.2f}s  {r['segment']:9} {'PLACEHOLDER ' if r['placeholder'] else ''}{r['source']}")
    total = report["total_seconds"]
    print(f"\n{final}\n{total:.1f} s ({int(total // 60)}:{total % 60:04.1f})"
          + ("   OVER 3:00, cut something" if total > 179.5 else
             "   under 3:00" + (" but tight" if total > 172 else "")))
    if placeholder_voices:
        print("placeholder voices (macOS say) for: " + ", ".join(placeholder_voices)
              + ". Record real people and re-run film.py with --voices.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ins = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--inserts=")), None)
    skip = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:]
                 if a.startswith("--skip=")), [])
    take = pathlib.Path(os.path.expanduser(args[0] if args else "take")).resolve()
    main(take, pathlib.Path(os.path.expanduser(ins)).resolve() if ins else take / "inserts", skip)
