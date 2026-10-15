"""No label clips (design/DESIGN.md rule 4): every scene on /alexa, in a real
browser, at the sizes the video and a judge's laptop use.

It plays all ten scenes against a local Hearth with the offline planner and,
after each answer, checks the label as drawn:

- on Ada's phone, the card fits the phone's screen whole: nothing below the
  fold (the "sort it out" and record cards used to run off the bottom);
- on the Echo Show, no row is cut by the label's edge;
- rows that do not fit are counted ("N more lines"), never cut in half.

Needs playwright (requirements-dev.txt); without it the test says SKIP.
"""
import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = [(1920, 1080, "film"), (1600, 900, ""), (1280, 720, "")]

# The host side: the phone's feed must show the card without scrolling.
HOST = """() => {
  const f = document.querySelector('#device iframe');
  const feed = document.getElementById('feed');
  if (!f) return null;
  return {phone: !!feed, below: feed ? feed.scrollHeight - feed.clientHeight : 0};
}"""
# The card side: no row cut by the rows box, the label inside its frame.
CARD = """() => {
  const ul = document.querySelector('.rows'), label = document.querySelector('.label');
  if (!label) return null;
  const more = document.querySelector('.more');
  return {cut: ul ? ul.scrollHeight - ul.clientHeight : 0,
          past: Math.ceil(label.getBoundingClientRect().bottom - innerHeight),
          title: (document.querySelector('h1') || {}).textContent || '',
          more: more ? more.textContent : ''};
}"""


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def serve():
    port = free_port()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("HEARTH_SIM_LLM", "HEARTH_BEDROCK", "HEARTH_DATA", "HEARTH_NOTIFY"))}
    env.update(HEARTH_ISSUER=f"http://127.0.0.1:{port}", HEARTH_TZ="America/New_York")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "hearth.app:app", "--port", str(port),
                             "--log-level", "warning"], cwd=ROOT, env=env)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/healthz", timeout=1); return proc, base
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit("Hearth did not start")


async def play(base, w, h, mode, async_playwright):
    bad = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": w, "height": h})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"{base}/alexa?mute=1" + ("&film=1" if mode else ""))
        await page.wait_for_selector("#wiresub:has-text('Session')", timeout=30000)
        n = await page.evaluate("SCRIPT.length")
        for i in range(n):
            await page.evaluate("nextScene()")
            await page.wait_for_function("!busy", timeout=30000)
            await page.wait_for_timeout(500)                  # the card and its resize settle
            host = await page.evaluate(HOST)
            if host is None:
                continue                                       # the Echo Dot: no screen
            frames = [f for f in page.frames if f != page.main_frame]
            card = await frames[-1].evaluate(CARD) if frames else None
            where = f"{w}x{h}{' film' if mode else ''} scene {i} ({'phone' if host['phone'] else 'show'})"
            if host["below"] > 1:
                bad.append(f"{where}: the card runs {host['below']} px off the phone's screen")
            if card and card["cut"] > 1:
                bad.append(f"{where}: {card['title']!r} cuts a row ({card['cut']} px)")
            if card and not host["phone"] and card["past"] > 1:
                bad.append(f"{where}: {card['title']!r} runs {card['past']} px past the canvas")
        await browser.close()
        bad += [f"{w}x{h}: page error {e}" for e in errors]
    return bad


def test_no_card_clips():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("SKIP no card clips (pip install -r requirements-dev.txt for playwright)")
        return
    proc, base = serve()
    try:
        bad = []
        for w, h, mode in SIZES:
            bad += asyncio.run(play(base, w, h, mode, async_playwright))
    finally:
        proc.terminate(); proc.wait(10)
    assert not bad, "\n".join(bad)
    print(f"PASS no card clips: 10 scenes at {', '.join(f'{w}x{h}' for w, h, _ in SIZES)}")


if __name__ == "__main__":
    test_no_card_clips()
    print("\nall green (cards fit)")
