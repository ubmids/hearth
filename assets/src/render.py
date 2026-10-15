"""Render the skill listing's images into hearth/web/assets/: the icon at the
six sizes Amazon asks for, from icon.svg, and the carousel image, from
carousel.html. Needs Playwright (requirements-dev.txt).

    python3 assets/src/render.py
"""
import asyncio
import os
import pathlib

from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent.parent / "hearth" / "web" / "assets"
SIZES = [64, 72, 88, 126, 180, 241]


async def main():
    chrome = os.getenv("HEARTH_CHROME")
    async with async_playwright() as p:
        b = await p.chromium.launch(**({"executable_path": chrome} if chrome else {}))
        svg = (HERE / "icon.svg").read_text()
        for n in SIZES:
            page = await b.new_page(viewport={"width": n, "height": n})
            sized = svg.replace("<svg ", f'<svg style="display:block;width:{n}px;height:{n}px" ', 1)
            await page.set_content(f'<html><body style="margin:0">{sized}</body></html>')
            await page.screenshot(path=str(OUT / f"icon-{n}x{n}.png"))
            await page.close()
        page = await b.new_page(viewport={"width": 600, "height": 900})
        await page.goto((HERE / "carousel.html").as_uri())
        await page.evaluate("document.fonts.ready")
        await page.wait_for_timeout(200)
        await page.screenshot(path=str(OUT / "carousel-1.png"))
        await b.close()
    print("wrote", ", ".join(f"icon-{n}x{n}.png" for n in SIZES), "and carousel-1.png")


if __name__ == "__main__":
    asyncio.run(main())
