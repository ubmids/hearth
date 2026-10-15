"""The Devpost thumbnail and gallery images, and the README hero, from the real
simulated Alexa+ page (design/DESIGN.md, "Submission assets").

It plays the scenes on /alexa in a headless browser, photographs each device
as it stands after the scene, and sets each photograph in the same frame: one
sentence of caption, the device, the "Simulated Alexa+" label. Nothing in a
picture is drawn by hand; every card is Hearth's own MCP App.

    pip install playwright && python -m playwright install chromium
    uvicorn hearth.app:app --port 8000 &      # HEARTH_ISSUER=http://localhost:8000
    python3 demo/gallery.py http://localhost:8000 docs/img
"""
import asyncio
import base64
import html
import os
import sys

from playwright.async_api import async_playwright

W, H = 1500, 1000
CHROME = os.getenv("HEARTH_CHROME")         # a local Chrome, if Playwright has none

ARCH = ('<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M7 27V14a9 9 0 0 1 18 0v13" '
        'fill="none" stroke="currentColor" stroke-width="3.2"/><path d="M4 27.5h24" '
        'stroke="currentColor" stroke-width="3.2"/><rect x="13" y="18" width="6" height="9" '
        'fill="currentColor"/></svg>')

FRAME = """<!doctype html><html lang="en"><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Condensed:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root{--desk:#ECECE7;--paper:#FFFFFF;--rule:#111111;--ink:#0B0B0B;--ink-2:#3A3A3A;--ink-3:#595954;
        --red:#C8201A;--on-red:#FFFFFF;--yellow:#FFD43B;--on-yellow:#0B0B0B;--blue:#1F4FB5;--on-blue:#FFFFFF}
  *{box-sizing:border-box}
  html,body{margin:0;width:%(w)dpx;height:%(h)dpx;overflow:hidden;background:var(--desk);color:var(--ink);
            font-family:"IBM Plex Sans Condensed","Arial Narrow",sans-serif}
  .wrap{position:absolute;inset:0;padding:52px 72px 56px;display:flex;flex-direction:column}
  .top{display:flex;align-items:center;gap:16px}
  .brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:34px}
  .brand svg{width:34px;height:34px}
  .grow{flex:1}
  .stk{font-weight:700;font-size:20px;letter-spacing:.06em;text-transform:uppercase;line-height:1;padding:10px 12px}
  .sim{background:var(--rule);color:var(--paper)}
  .n{font:600 20px "IBM Plex Mono",monospace;color:var(--ink-3)}
  h1{margin:26px 0 0;font-size:48px;line-height:1.06;font-weight:700;max-width:1250px;text-wrap:balance}
  .said{margin:10px 0 0;font-size:25px;color:var(--ink-2);max-width:1250px}
  .said b{color:var(--ink);font-weight:600}
  .dev{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;gap:48px;margin-top:28px}
  .dev img{max-width:100%%;max-height:100%%;display:block}
  .dev img.page{border:3px solid var(--rule)}
  .label{background:var(--paper);border:3px solid var(--rule);width:640px}
  .lh{display:flex;justify-content:space-between;padding:12px 18px;border-bottom:3px solid var(--rule);
      font-weight:700;font-size:18px;letter-spacing:.06em;text-transform:uppercase}
  .lb{padding:18px 18px 22px;font-size:27px;line-height:1.38}
  /* the thumbnail */
  .rx{background:var(--paper);border:5px solid var(--rule);width:720px;display:flex;flex-direction:column}
  .rx .lh{background:var(--rule);color:var(--paper);font-size:26px;padding:16px 24px;border:0}
  .rx h2{margin:0;padding:34px 24px 0;font-size:128px;line-height:.95;font-weight:700}
  .rx .stk{align-self:flex-start;margin:26px 24px 0;font-size:34px;padding:12px 16px;background:var(--red);color:var(--on-red)}
  .rx table{border-collapse:collapse;margin:30px 0 0;font-size:36px;width:100%%}
  .rx td{border-top:3px solid var(--rule);padding:14px 24px}
  .rx td:first-child{width:28%%;font-size:24px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding-right:0}
  .rx .mono{font-family:"IBM Plex Mono",monospace;font-weight:600}
  .rx .lf{display:flex;justify-content:space-between;border-top:3px solid var(--rule);padding:14px 24px;
          font-size:22px;color:var(--ink-2)}
</style><body>%(body)s</body></html>"""


def b64(png):
    return "data:image/png;base64," + base64.b64encode(png).decode()


def header(n=None):
    return (f'<div class="top"><div class="brand">{ARCH}hearth</div><div class="grow"></div>'
            + (f'<span class="n">{n} / 6</span>' if n else "")
            + '<span class="stk sim">Simulated Alexa+</span></div>')


def slide(n, caption, said, device_html):
    return FRAME % {"w": W, "h": H, "body": f"""<div class="wrap">{header(n)}
      <h1>{caption}</h1><p class="said">{said}</p><div class="dev">{device_html}</div></div>"""}


def thumbnail(device_png):
    return FRAME % {"w": W, "h": H, "body": f"""<div class="wrap" style="flex-direction:row;align-items:center;gap:56px;padding:64px">
      <div class="rx"><div class="lh"><span>Hearth · for Mom</span><span>Warfarin</span></div>
        <h2>Hold on, Rose.</h2><span class="stk">Stopped</span>
        <table><tr><td>Given</td><td><span class="mono">9:10 am</span> by Grace</td></tr>
               <tr><td>Rule</td><td>Once a day, Ada</td></tr></table>
        <div class="lf"><span>An Alexa+ add-on for families</span><span>Simulated Alexa+</span></div></div>
      <div style="flex:1;display:flex;flex-direction:column;gap:28px;align-self:stretch;justify-content:center">
        <div class="brand" style="font-size:56px">{ARCH.replace('<svg ', '<svg style="width:56px;height:56px" ')}hearth</div>
        <img src="{b64(device_png)}" alt="" style="width:100%;display:block"></div></div>"""}


async def main(base, out):
    os.makedirs(out, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": CHROME} if CHROME else {}))
        page = await browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"{base}/alexa?mute=1")
        await page.wait_for_selector("#wiresub:has-text('Session')", timeout=30000)

        async def scene():
            await page.evaluate("nextScene()")
            await page.wait_for_function("!busy", timeout=30000)
            await page.wait_for_timeout(900)

        async def device():
            return await (await page.query_selector("#frameWrap")).screenshot()

        async def said():
            return await page.evaluate(
                "[...document.querySelectorAll('#talk .alexa')].pop()?.innerText.replace(/^ALEXA\\s*/i, '') || ''")

        shots = {}
        await scene()                                   # 1 Rose
        shots["hold-on-rose"] = await device()
        await page.evaluate("hood(true)")
        await page.wait_for_timeout(500)
        shots["under-the-hood"] = await page.screenshot()
        await page.evaluate("hood(false)")
        await scene()                                   # 2 Grace
        shots["handover"] = await device()
        await scene()                                   # 3 Tom, catch-up
        shots["catch-up"] = await device()
        catch_up_line = await said()
        await scene()                                   # 4 why
        await scene()                                   # 5 sort it out
        shots["sort-it-out"] = await device()
        sort_line = await said()
        await scene()                                   # 6 order
        shots["reorder"] = await device()
        reorder_line = await said()

        img = lambda k, cls="": f'<img class="{cls}" src="{b64(shots[k])}" alt="">'
        says = lambda line, where: (f'<div class="label"><div class="lh"><span>Alexa says</span>'
                                    f'<span>{where}</span></div><div class="lb">{html.escape(line)}</div></div>')
        slides = {
            "hold-on-rose": slide(1, "Rose reaches for a second blood thinner. Hearth's server says no.",
                                  "<b>Rose, in her kitchen:</b> “Alexa, I'm just going to take my blood thinner.”",
                                  img("hold-on-rose")),
            "handover": slide(2, "Grace's handover reaches the family, and the one worry reaches Ada.",
                              "<b>Grace, the aide:</b> “I'm off. Mom ate half her lunch, she was a bit dizzy "
                              "after her walk, and we're nearly out of Ensure.”", img("handover")),
            "catch-up": slide(3, "Tom, two states away, hears only what changed since he last asked.",
                              "<b>Tom, on his Echo Dot:</b> “Alexa, what did I miss with Mom today?”",
                              img("catch-up") + says(catch_up_line, "Voice only")),
            "sort-it-out": slide(4, "One sentence, five steps: the calendar, the rota, the ride, the board and Tom's phone.",
                                 "<b>Ada, on her phone:</b> “Mom's cardiology moved to Thursday at 10. Sort it out.”",
                                 img("sort-it-out") + says(sort_line, "Ada's phone")),
            "reorder": slide(5, "The list Grace started, checked against Ada's limit, paid the Alexa+ way.",
                             "<b>Ada:</b> “Alexa, order what's on the list.” The pharmacy is a sandbox.",
                             img("reorder") + says(reorder_line, "Ada's phone")),
            "under-the-hood": slide(6, "Under the hood: MCP 2025-11-25, OAuth 2.1 with PKCE, and a signed record.",
                                    "Every request and answer, live, beside the household it serves.",
                                    img("under-the-hood", "page")),
        }
        frame = await browser.new_page(viewport={"width": W, "height": H})
        for name, doc in slides.items():
            await frame.set_content(doc, wait_until="networkidle")
            await frame.wait_for_timeout(300)
            await frame.screenshot(path=os.path.join(out, f"{name}.jpg"), type="jpeg", quality=90)
            print("wrote", name)
        await frame.set_content(thumbnail(shots["hold-on-rose"]), wait_until="networkidle")
        await frame.wait_for_timeout(300)
        await frame.screenshot(path=os.path.join(out, "thumbnail.png"))
        print("wrote thumbnail")
        if errors:
            raise SystemExit(f"page errors: {errors}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000",
                     sys.argv[2] if len(sys.argv) > 2 else "docs/img"))
