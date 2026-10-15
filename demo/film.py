"""Record the simulated Alexa+ run for the video: the screen, and every line
spoken at the moment it happens.

This is the pre-rendered half of the demo video (docs/video/SCRIPT.md). It
plays the film scenes (FILM in hearth/web/alexa.html) on /alexa?film=1 in a
1920x1080 browser against a running Hearth, typing each person's line over the
time it takes to say it, and waits for each answer to be spoken before the
next scene. Every answer is whatever Hearth returned on this run.

  <out>/screen.webm      the screen, silent
  <out>/audio/*.aiff     each line, spoken with macOS `say`. Alexa's voice is a
                         stand-in; the people's voices are placeholders to be
                         replaced by real people (the script says who)
  <out>/timeline.json    when each line starts in screen.webm, who said it, the text
  <out>/sim-run.mp4      the screen with every line mixed in at its time
  <out>/transcript.md    who said what, when; captions.srt for the upload

    export HEARTH_TZ=<a zone where it is now mid-afternoon> HEARTH_ISSUER=http://localhost:8000
    export HEARTH_SIM_LLM_PROVIDER=openai HEARTH_SIM_LLM_BASE_URL=http://localhost:11434/v1
    export HEARTH_SIM_LLM_API_KEY=ollama HEARTH_SIM_LLM_MODEL=qwen2.5:7b-instruct
    export HEARTH_SIM_LLM_TIMEOUT=30 HEARTH_SIM_LLM_WARMUP=1   # a busy laptop: no fallback
    uvicorn hearth.app:app --port 8000 &
    python3 demo/film.py http://localhost:8000 ~/Desktop/hackathons/hearth-video/take1 \
        [--voices=~/Desktop/hackathons/hearth-video/voices]

With --voices, a real person's recording of a line (00-rose.m4a, 01-grace.m4a,
02-tom.m4a ... numbered by scene) is used instead of the placeholder voice,
and the line is typed over the length of that recording.

Start each take on a fresh server (a new HEARTH_DATA, or none): the household
is seeded once per account. macOS only (`say`, `afinfo`); needs playwright and
ffmpeg. demo/rough_cut.py turns a take into the whole video.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time

VOICES = {"Alexa": "Samantha", "Rose": "Grandma", "Grace": "Flo",
          "Ada": "Sandy", "Tom": "Reed"}
RATE = {"Alexa": 195, "Rose": 165}           # words a minute; others default
HOLD_AFTER = 0.5                             # seconds of quiet after each answer
BEAT = 0.8                                   # and before each person speaks
TRAFFIC_SECONDS = 5.5                        # the MCP traffic panel, once, after the hero


def speak(who: str, text: str, path: str) -> float:
    """Render `text` in `who`'s placeholder voice; return its length in seconds."""
    said = re.sub(r"\[[0-9a-f]{12}\]", "", text).strip()
    cmd = ["say", "-v", VOICES.get(who, "Samantha"), "-o", path]
    if who in RATE:
        cmd += ["-r", str(RATE[who])]
    subprocess.run(cmd + [said], check=True)
    out = subprocess.run(["afinfo", path], capture_output=True, text=True).stdout
    return float(re.search(r"estimated duration: ([\d.]+)", out).group(1))


async def last_alexa(page) -> str:
    text = await page.evaluate(
        "[...document.querySelectorAll('#talk .alexa')].pop()?.innerText || ''")
    return re.sub(r"^ALEXA\s*", "", text.strip(), flags=re.I)


def length(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return float(out.strip())


def recorded(voices: str | None, n: int, who: str) -> str | None:
    """A real person's recording of scene n's line, if one was made:
    <voices>/<NN>-<who>.<m4a|wav|aiff|mp3>, e.g. 00-rose.m4a."""
    if not voices:
        return None
    for ext in ("m4a", "wav", "aiff", "mp3", "caf"):
        p = os.path.join(voices, f"{n:02d}-{who.lower()}.{ext}")
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


async def main(base: str, out: str, voices: str | None = None):
    from playwright.async_api import async_playwright   # here: rough_cut imports this file
    os.makedirs(os.path.join(out, "audio"), exist_ok=True)
    events = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # The device clock is the browser's: give it Hearth's zone, so the
        # Echo Show agrees with "3:07 this afternoon".
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080},
                                        timezone_id=os.getenv("HEARTH_TZ") or None,
                                        device_scale_factor=1,
                                        record_video_dir=out,
                                        record_video_size={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        t0 = time.monotonic()
        at = lambda: round(time.monotonic() - t0, 3)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"{base}/alexa?mute=1&film=1")
        await page.wait_for_selector("#wiresub:has-text('Session')", timeout=30000)
        await page.wait_for_timeout(1200)
        planner = await page.evaluate("document.body.innerText.match(/planner: [^\\n]+/)?.[0] || ''")
        scenes = await page.evaluate("FILM.map(i => SCRIPT[i])")
        # Every person's line is ready before the take starts: rendering one
        # between scenes is dead air on screen, seconds of it on a busy machine.
        said = []
        for n, (who, line) in enumerate(scenes):
            human = recorded(voices, n, who)
            if human:
                said.append((human, length(human)))   # a real person's take: type to it
            else:
                human = os.path.join(out, "audio", f"{n:02d}a-{who.lower()}.aiff")
                said.append((human, speak(who, line, human)))
        events.append({"at": at(), "kind": "ready", "planner": planner})
        for n, (who, line) in enumerate(scenes):
            human, dur = said[n]
            await page.wait_for_timeout(int(BEAT * 1000))
            before = await page.evaluate("document.querySelectorAll('#talk .alexa').length")
            start = at()
            events.append({"at": start, "kind": "line", "who": who, "text": line,
                           "audio": os.path.relpath(human, out), "seconds": dur, "scene": n,
                           "real_voice": human.startswith(os.path.abspath(voices)) if voices else False})
            # Type it over the time it takes to say it, then send, as a person would.
            per_char = max(15, int(dur * 1000 * 0.9 / max(1, len(line))))
            await page.evaluate("""async ([who, line, ms]) => {
                setWho(who); const box = document.querySelector('#said'); box.value = '';
                for (const ch of line) { box.value += ch; await new Promise(r => setTimeout(r, ms)); }
                await new Promise(r => setTimeout(r, 200)); send(); }""", [who, line, per_char])
            await page.wait_for_function(
                f"document.querySelectorAll('#talk .alexa').length > {before} && !busy",
                timeout=60000)
            await page.wait_for_timeout(250)                     # the card settles
            answer = await last_alexa(page)
            planned = await page.evaluate(
                "document.body.innerText.match(/planner: [^\\n]+/)?.[0] || ''")
            reply_at = max(at(), start + dur + 0.3)              # never over the person
            alexa = os.path.join(out, "audio", f"{n:02d}b-alexa.aiff")
            adur = speak("Alexa", answer, alexa)
            events.append({"at": reply_at, "kind": "line", "who": "Alexa", "text": answer,
                           "audio": os.path.relpath(alexa, out), "seconds": adur,
                           "scene": n, "planner": planned})
            await page.wait_for_timeout(int((reply_at + adur + HOLD_AFTER - at()) * 1000))
            if n == 0:
                # The only time the protocol is on screen: the hero's tools/call.
                events.append({"at": at(), "kind": "traffic-on"})
                await page.keyboard.press("t")
                await page.wait_for_timeout(int(TRAFFIC_SECONDS * 1000))
                await page.keyboard.press("t")
                await page.wait_for_timeout(700)
                events.append({"at": at(), "kind": "traffic-off"})
            events.append({"at": at(), "kind": "scene-end", "scene": n})
        video = page.video
        await ctx.close()
        await browser.close()
        os.replace(await video.path(), os.path.join(out, "screen.webm"))
    with open(os.path.join(out, "timeline.json"), "w") as f:
        json.dump({"base": base, "events": events}, f, indent=1)
    mix(out, events)
    write_transcript(out, events, planner)
    if errors:
        raise SystemExit(f"page errors: {errors}")
    for e in events:
        if e["kind"] == "line":
            print(f"{e['at']:7.2f}s {e['who']:5} {e['text'][:110]}")
    print(f"\n{out}/sim-run.mp4  ({planner})")
    # A scene the model did not plan (it timed out, or a guard stepped in)
    # is not the take to cut: SHOTS.md says redo it.
    off = [e["scene"] for e in events if e.get("who") == "Alexa" and re.search(
        r"offline rules|dose guard|day as said", e.get("planner", ""))]
    if off:
        print(f"REDO: scenes {off} were not planned by the model alone "
              "(raise HEARTH_SIM_LLM_TIMEOUT, set HEARTH_SIM_LLM_WARMUP=1)")


def _stamp(t: float, srt=False) -> str:
    m, sec = divmod(max(0.0, t), 60)
    if srt:
        h, m = divmod(int(m), 60)
        return f"{h:02d}:{m:02d}:{int(sec):02d},{int((sec % 1) * 1000):03d}"
    return f"{int(m)}:{sec:04.1f}"


def write_transcript(out: str, events: list, planner: str):
    """transcript.md (who said what, when) and captions.srt for the upload."""
    lines = [e for e in events if e["kind"] == "line"]
    t0 = next(e["at"] for e in events if e["kind"] == "ready")
    md = ["# Hold on, Rose: the filmed afternoon", "",
          "Recorded by `demo/film.py` on the simulated Alexa+ client "
          f"(`/alexa?film=1`), {planner}. Every **Alexa** line is the text "
          "Hearth's tools returned on this run, over the real MCP endpoint. "
          "Times are from the start of the take.", ""]
    md += [f"- `{_stamp(e['at'] - t0)}` **{e['who']}**: {e['text']}" for e in lines]
    with open(os.path.join(out, "transcript.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    srt = []
    for i, e in enumerate(lines, 1):
        srt += [str(i), f"{_stamp(e['at'], True)} --> {_stamp(e['at'] + e['seconds'], True)}",
                f"{e['who']}: {e['text']}", ""]
    with open(os.path.join(out, "captions.srt"), "w") as f:
        f.write("\n".join(srt))


def mix(out: str, events: list):
    """screen.webm plus every line at its time, as sim-run.mp4."""
    lines = [e for e in events if e["kind"] == "line"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(out, "screen.webm")]
    for e in lines:
        cmd += ["-i", os.path.join(out, e["audio"])]
    parts = [f"[{i}:a]adelay={int(e['at'] * 1000)}:all=1[a{i}]"
             for i, e in enumerate(lines, 1)]
    graph = ";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(1, len(lines) + 1)) \
        + f"amix=inputs={len(lines)}:normalize=0:dropout_transition=0[a]"
    cmd += ["-filter_complex", graph, "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-r", "30", "-c:a", "aac", "-b:a", "160k", os.path.join(out, "sim-run.mp4")]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--voices=")]
    voices = next((os.path.expanduser(a.split("=", 1)[1]) for a in sys.argv[1:]
                   if a.startswith("--voices=")), None)
    asyncio.run(main(args[0].rstrip("/") if args else "http://localhost:8000",
                     os.path.expanduser(args[1]) if len(args) > 1 else "take", voices))
