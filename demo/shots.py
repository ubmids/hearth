"""Play every scene on the simulated Alexa+ page in a headless browser and
screenshot each one: a rehearsal of the video, and the README's images.

It drives the real /alexa page against a running server (OAuth, MCP session,
tools/call, MCP App), muted. A scene that errors fails the run.

    pip install playwright && python -m playwright install chromium
    uvicorn hearth.app:app --port 8765 &      # HEARTH_ISSUER=http://localhost:8765
    python3 demo/shots.py http://localhost:8765 out/shots
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

NAMES = ["hold-on-rose", "catch-up", "why", "sort-it-out", "reorder", "paid",
         "coffee", "antibiotics", "record"]


async def main(base, out):
    os.makedirs(out, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(f"{base}/alexa?mute=1")
        await page.wait_for_selector("#wiresub:has-text('Session')", timeout=20000)
        await page.screenshot(path=os.path.join(out, "00-connected.png"))
        for i, name in enumerate(NAMES, 1):
            await page.evaluate("nextScene()")
            await page.wait_for_function("!busy", timeout=30000)
            await page.wait_for_timeout(400)          # let the card settle
            await page.screenshot(path=os.path.join(out, f"{i:02d}-{name}.png"))
            said = await page.evaluate(
                "[...document.querySelectorAll('#talk .alexa')].pop()?.innerText || ''")
            print(f"{i:02d} {name}: {said.replace(chr(10), ' ')[:150]}")
        await browser.close()
    if errors:
        raise SystemExit(f"page errors: {errors}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8765",
                     sys.argv[2] if len(sys.argv) > 2 else "shots"))
