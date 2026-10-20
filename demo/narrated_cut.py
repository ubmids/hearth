"""The demo video with Subomi's narration (ElevenLabs, his approved voice),
over take 5 of the filmed demo. The family's macOS `say` voices are dropped:
the screen's "What was said" panel shows every line as it is spoken.

    python3 demo/narrated_cut.py [take] [--out=FILE] [--estimate]

  take        default ~/Desktop/hackathons/hearth-video/take5 (film.py output;
              uses sim-run.mp4 and the cards rough_cut.py rendered into cut/)
  --estimate  print characters and a timing estimate, spend nothing

Each narration line is one ElevenLabs request, cached by its text in
~/Desktop/hackathons/hearth-video/voice/, so a rebuild costs nothing and a bad
take is redone alone (delete its mp3, or change the line). The key is read
from ~/.config/elevenlabs/key and never written anywhere.

Writes ~/Desktop/hackathons/hearth-video/hearth-narrated.mp4, .srt (the
narration, for the upload) and .json (each chunk and line time).
"""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import narrate  # noqa: E402
import voice  # noqa: E402

VIDEO = pathlib.Path.home() / "Desktop/hackathons/hearth-video"

# What Subomi says. A tuple is (caption text, text sent to the voice) where the
# voice needs a spelling hint. No claim here goes beyond what take 5 shows.
LINES = {
    "intro": "Hey, I'm Subomi. This is Hearth, an add-on for Alexa+, for families "
             "who share the care of a parent.",
    "why1": "So, the care gets split up. A daughter with the doctor's letters, a son "
            "two states away, an aide on weekday mornings. Nobody holds the whole picture.",
    "why2": "And that gap is kind of where doses get doubled. Warfarin is in one in three "
            "overdose hospitalisations of older adults.",
    "rose": "So here's Rose. She's eighty-four, and she's about to take her blood thinner.",
    "stop": "Hearth stops her. Grace already gave today's dose this morning, and it's "
            "once a day.",
    "traffic": ("And this is the bit I care about. The model chose give_dose. Hearth's "
                "server refused it, not the model, and recorded the refusal.",
                "And this is the bit I care about. The model chose give dose. Hearth's "
                "server refused it, not the model, and recorded the refusal."),
    "grace": "Later, Grace ends her shift with one sentence.",
    "handover": "Hearth turns it into three things. Ensure on the shopping list, a handover "
                "on the family board, and the dizziness flagged for Ada, who has the say "
                "over Mom's health.",
    "tom": "Tom's two states away, on a different device. What did I miss?",
    "catchup": "Hearth remembers when he last checked in, and catches him up. Including "
               "the dose it stopped.",
    "ada": "Ada, on her phone. Mom's cardiology moved. Sort it out.",
    "arrange": "One request, and Hearth moves the appointment, sees Tom does Thursdays, "
               "rebooks the ride, and tells him. The rides are a sandbox.",
    "order": "Then she orders what's on the list.",
    "checks": "It checks her fifty dollar limit, checks it wasn't ordered this week, and "
              "asks first.",
    "done": "She says yes. It's a sandbox pharmacy, so no card gets charged.",
    "record": "And the record. Seven calls, one refused, each one signed, and it matches a "
              "receipt her own phone kept. If anyone changed the history, you'd know.",
    "tech1": ("Under the hood, it's an MCP server on the 2025-11-25 spec, passing the "
              "official conformance suite.",
              "Under the hood, it's an M C P server on the twenty twenty-five, eleven "
              "twenty-five spec, passing the official conformance suite."),
    "tech2": "And the model picking every call is a small open one, on my laptop. It "
             "doesn't need to know warfarin. Hearth does.",
    "close": "Alexa+ is simulated here, since add-on tools are partner-only for now. "
             "So that's Hearth. The memory, and the conscience, of a family caring for "
             "someone.",
}


def spoken(k):
    v = LINES[k]
    return (v if isinstance(v, str) else v[1]).replace("Alexa+", "Alexa plus")


def still(src, at, name):
    out = VIDEO / "narrated-work" / f"still-{name}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    narrate.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at:.2f}", "-i", str(src),
                 "-frames:v", "1", str(out)])
    return out


def plan(take: pathlib.Path):
    sim, cut = take / "sim-run.mp4", take / "cut"
    th = lambda n: cut / f"third{n}.png"        # the lower thirds rough_cut rendered
    clip = lambda name, a, b, ids, **kw: dict(name=name, src=sim, ss=a, to=b, lines=ids,
                                              pad="0xeceae4", **kw)
    return [
        clip("intro", 9.6, 10.2, ["intro"], overlays=[(th(0), 0.3, None)]),
        # The household panel lists exactly who shares the care.
        dict(name="who", src=still(sim, 10.0, "idle"), lines=["why1"], zoom=(150, 330, 2.2)),
        dict(name="why", src=cut / "stats.png", lines=["why2"]),
        clip("rose", 10.2, 16.5, ["rose"]),
        clip("stop", 16.5, 24.6, ["stop"]),
        clip("traffic", 24.6, 31.0, ["traffic"], overlays=[(th(1), 0.3, None)]),
        clip("grace", 31.0, 41.9, ["grace"]),
        clip("handover", 41.9, 52.2, ["handover"], overlays=[(th(2), 0.3, None)]),
        clip("tom", 52.2, 57.0, ["tom"]),
        clip("catchup", 57.0, 78.0, ["catchup"], speed_max=2.6,
             overlays=[(th(3), 0.3, None)]),
        clip("ada", 78.0, 86.3, ["ada"]),
        clip("arrange", 86.3, 99.5, ["arrange"], overlays=[(th(4), 0.3, None)]),
        clip("order", 99.5, 104.4, ["order"]),
        clip("checks", 104.4, 114.1, ["checks"]),
        clip("done", 114.1, 124.3, ["done"], overlays=[(th(5), 0.3, None)]),
        clip("record", 124.3, 139.0, ["record"], overlays=[(th(6), 0.3, None)]),
        dict(name="tech", src=cut / "tech.png", lines=["tech1"]),
        # The planner line in the traffic panel: the model, on this machine.
        dict(name="model", src=still(sim, 30.0, "planner"), lines=["tech2"],
             zoom=(1650, 640, 2.0)),
        dict(name="close", src=cut / "close.png", lines=["close"], tail=2.0),
    ]


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    opts = dict(a.split("=", 1) for a in argv if a.startswith("--") and "=" in a)
    take = pathlib.Path(os.path.expanduser(args[0] if args else VIDEO / "take5")).resolve()
    final = pathlib.Path(os.path.expanduser(opts.get("--out", VIDEO / "hearth-narrated.mp4")))
    chars = sum(len(spoken(k)) for k in LINES)
    print(f"{len(LINES)} lines, {chars} characters, about {chars / 14.5:.0f} s of speech")
    if "--estimate" in argv:
        return 0
    cache = VIDEO / "voice"
    tts = {spoken(k): k for k in LINES}
    total, report = narrate.build(
        plan(take), {k: (v if isinstance(v, str) else v[0], spoken(k)) for k, v in LINES.items()},
        lambda text: voice.line(text, cache), VIDEO / "narrated-work", final)
    for r in report:
        print(f"{r['start']:7.2f}  {r['seconds']:6.2f}s  {r['chunk']:9} {r['source']}")
    print(f"\n{final}\n{total:.1f} s ({int(total // 60)}:{total % 60:04.1f})"
          + ("   OVER 2:55, cut something" if total > 175 else "   under 3:00"))
    print(f"ElevenLabs characters spent so far (all takes): {voice.spent(cache)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
