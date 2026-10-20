"""Narration lines in Subomi's approved ElevenLabs voice, one request per line.

    from voice import line
    mp3 = line("Hey, I'm Subomi.", cache_dir)        # cached: never re-spends

Each line is cached by a hash of its text and the voice settings, so a rebuild
costs nothing and a bad take is redone alone with `retake=True` (or by deleting
its file). The key is read from ~/.config/elevenlabs/key and never printed or
written anywhere. Characters spent are appended to <cache_dir>/ledger.json.
"""
import hashlib
import json
import pathlib
import time
import urllib.request

VOICE = "U7wWSnxIJwCjioxt86mk"          # Olaniyi Victor, approved by Subomi
MODEL = "eleven_v4"
SETTINGS = {"stability": 0.3, "similarity_boost": 0.7, "style": 0.35,
            "use_speaker_boost": False}
KEY = pathlib.Path.home() / ".config" / "elevenlabs" / "key"


def _key(text):
    blob = json.dumps([VOICE, MODEL, SETTINGS, text], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def line(text: str, cache_dir, retake: bool = False, take: int = 0) -> pathlib.Path:
    cache = pathlib.Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{_key(text)}{'-t%d' % take if take else ''}.mp3"
    if out.exists() and not retake:
        return out
    body = json.dumps({"text": text, "model_id": MODEL, "voice_settings": SETTINGS}).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_128",
        data=body, method="POST",
        headers={"xi-api-key": KEY.read_text().strip(), "Content-Type": "application/json",
                 "Accept": "audio/mpeg"})
    offline_since = None
    for attempt in range(200):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                want = r.headers.get("Content-Length")
            if not data or (want and int(want) != len(data)):
                raise urllib.error.URLError("short read")
            tmp = out.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.rename(out)                      # never cache a partial take
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            if e.code in (429, 500, 502, 503) and attempt < 5:
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit(f"ElevenLabs {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # Offline: wait and retry for up to about two hours.
            offline_since = offline_since or time.time()
            if time.time() - offline_since > 7200:
                raise SystemExit(f"ElevenLabs unreachable for 2 hours: {e}")
            print(f"ElevenLabs unreachable ({e}); retrying in 60 s", flush=True)
            time.sleep(60)
    led = cache / "ledger.json"
    rows = json.loads(led.read_text()) if led.exists() else []
    rows.append({"file": out.name, "chars": len(text), "text": text,
                 "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    led.write_text(json.dumps(rows, indent=1))
    return out


def spent(cache_dir) -> int:
    led = pathlib.Path(cache_dir) / "ledger.json"
    return sum(r["chars"] for r in json.loads(led.read_text())) if led.exists() else 0
