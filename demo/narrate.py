"""Cut a first-person narrated demo from footage, chunk by chunk.

A plan is a list of chunks. Each chunk is a stretch of a clip (or a still) and
the narration lines that play over it. The chunk is retimed to its lines:

  * still            shown for as long as its lines take
  * clip, fixed      plays at 1x for its own length; lines start at `at`
                     offsets (or one after another from `lead`); the clip's
                     own sound is kept at `keep` and dips to `duck` under the
                     narration
  * clip, otherwise  sound dropped; if the lines need longer than the clip,
                     it plays at 1x and holds its last frame; if they need
                     less, it is sped up (up to `speed_max`, then trimmed)

Narration audio comes from voice.line(), cached per line, so a rebuild never
spends credits. Writes the video, a sidecar .srt of the narration and a .json
report (every chunk, its length, each line's time).
"""
import json
import re
import pathlib
import subprocess

W, H, FPS = 1920, 1080, 30
VENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
        "-r", str(FPS)]
AENC = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(p) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout
    return float(out.strip())


def has_audio(p) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True).stdout
    return bool(out.strip())


def stamp(t):
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build(plan, lines, voice_fn, work: pathlib.Path, final: pathlib.Path,
          gap=0.35, lead=0.35, tail=0.45, narr_gain=1.0, say=None):
    """plan: list of dicts; lines: {id: text spoken (or (srt text, tts text))};
    voice_fn(text) -> audio path."""
    work.mkdir(parents=True, exist_ok=True)
    audio, srt_text = {}, {}
    for k, v in lines.items():
        shown, spoken = (v, v) if isinstance(v, str) else v
        srt_text[k] = shown
        audio[k] = voice_fn(spoken)
    dur = {k: duration(p) for k, p in audio.items()}

    parts, report, srt, t0 = [], [], [], 0.0
    for i, c in enumerate(plan):
        ids = c.get("lines", [])
        g, ld, tl = c.get("gap", gap), c.get("lead", lead), c.get("tail", tail)
        # Where each line starts inside the chunk.
        starts, t = {}, ld
        for k in ids:
            t = max(t, c.get("at", {}).get(k, t))
            starts[k] = t
            t += dur[k] + g
        need = (t - g + tl) if ids else 0.0
        src = c.get("src")
        is_still = str(src).endswith((".png", ".jpg"))
        if is_still:
            L = max(need, c.get("min", 0.0))
        else:
            D = c["to"] - c["ss"]
            L = D + c.get("hold", 0.0) if c.get("fixed") else max(need, c.get("min", 0.0))
        out = work / f"{i:02d}-{c['name']}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        graph = []
        if is_still and c.get("zoom"):
            # A slow push in towards (cx, cy) in 1920x1080 coordinates.
            cx, cy, z1 = c["zoom"]
            n = max(2, int(round(L * FPS)))
            cmd += ["-i", str(src)]
            z = f"(1+({z1}-1)*on/{n})"
            graph.append(f"[0:v]scale={W * 2}:{H * 2},zoompan=z='{z}':d={n}:s={W}x{H}:fps={FPS}:"
                         f"x='max(0,min(iw-iw/zoom,{cx * 2}-iw/zoom/2))':"
                         f"y='max(0,min(ih-ih/zoom,{cy * 2}-ih/zoom/2))',"
                         f"format=yuv420p,setsar=1[v0]")
        elif is_still:
            cmd += ["-loop", "1", "-t", f"{L:.3f}", "-i", str(src)]
            graph.append(f"[0:v]scale={W}:{H},fps={FPS},format=yuv420p,setsar=1[v0]")
        else:
            cmd += ["-ss", f"{c['ss']:.3f}", "-to", f"{c['to']:.3f}", "-i", str(src)]
            fit = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                   f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={c.get('pad', '0x000000')}")
            if c.get("fixed") and c.get("hold"):
                retime = f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={c['hold'] + 0.1:.3f}"
            elif c.get("fixed") or abs(L - D) < 0.05:
                retime = "setpts=PTS-STARTPTS"
            elif L > D:
                retime = f"setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={L - D + 0.1:.3f}"
            else:
                f = min(D / L, c.get("speed_max", 2.5))
                retime = f"setpts=(PTS-STARTPTS)/{f:.4f}"
            graph.append(f"[0:v]{retime},{fit},fps={FPS},format=yuv420p,setsar=1[v0]")
        v, k = "[v0]", 1
        for j, ov in enumerate(c.get("overlays", [])):
            png, a, b = ov
            b = L if b is None else b
            cmd += ["-loop", "1", "-t", f"{L:.3f}", "-i", str(png)]
            graph.append(f"{v}[{k}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[o{j}]")
            v, k = f"[o{j}]", k + 1
        # Sound: the clip's own (kept and ducked) or silence, plus the lines.
        keep = c.get("keep", 0.0)
        if not is_still and keep > 0 and has_audio(src):
            spans = "+".join(f"between(t,{starts[x] - 0.15:.2f},{starts[x] + dur[x] + 0.1:.2f})"
                             for x in ids) or "0"
            duck = c.get("duck", 0.3)
            graph.append(f"[0:a]asetpts=PTS-STARTPTS,aresample=48000,apad,"
                         f"volume='{keep}*if({spans},{duck},1)':eval=frame[bed]")
        else:
            cmd += ["-f", "lavfi", "-t", f"{L:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            graph.append(f"[{k}:a]anull[bed]")
            k += 1
        mix = ["[bed]"]
        for x in ids:
            cmd += ["-i", str(audio[x])]
            ms = int(starts[x] * 1000)
            graph.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,"
                         f"volume={narr_gain},adelay={ms}:all=1[n{k}]")
            mix.append(f"[n{k}]")
            k += 1
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,"
                     f"atrim=0:{L:.3f}[a]")
        cmd += ["-filter_complex", ";".join(graph), "-map", v, "-map", "[a]"]
        run(cmd + VENC + AENC + ["-t", f"{L:.3f}", str(out)])
        real = duration(out)
        for x in ids:
            srt.append((t0 + starts[x], t0 + starts[x] + dur[x], srt_text[x]))
        report.append({"chunk": c["name"], "start": round(t0, 2), "seconds": round(real, 2),
                       "lines": {x: round(t0 + starts[x], 2) for x in ids},
                       "source": str(src if is_still else f"{pathlib.Path(src).name} "
                                     f"{c['ss']:g}-{c['to']:g}s")})
        parts.append(out)
        t0 += real

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(joined)])
    # One loudness pass over the whole mix; the picture is copied as is.
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), "-map", "0:v", "-map", "0:a",
         "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", *AENC,
         "-movflags", "+faststart", str(final)])
    joined.unlink()
    rows, n = [], 0
    for a, b, text in srt:
        # One cue per sentence (short ones merged), timed by its share of characters.
        parts = re.split(r"(?<=[.?!])\s+", text.strip())
        cues = []
        for s in parts:
            if cues and (len(cues[-1]) < 28 or len(s) < 18) and len(cues[-1]) + len(s) < 90:
                cues[-1] += " " + s
            else:
                cues.append(s)
        total = sum(len(c) for c in cues)
        t = a
        for c in cues:
            e = t + (b - a) * len(c) / total
            n += 1
            rows += [str(n), f"{stamp(t)} --> {stamp(e)}", c, ""]
            t = e
    final.with_suffix(".srt").write_text("\n".join(rows))
    total = duration(final)
    final.with_suffix(".json").write_text(json.dumps(
        {"total_seconds": round(total, 2), "chunks": report}, indent=1))
    return total, report
