"""Screenshot site/index.html at 360, 390, 768, 1280 and 1440 px; report horizontal overflow.

The 1440-px top of the page at 2x becomes assets/dashboard.png (the README image).

Canvas rule: every shot is framed by default, the white page as a card (radius 14px,
border #E2EAE8) on 40 px of #F3F8F7. Pass --raw for the bare page.

Run: uv run --with playwright==1.64.1 python scripts/screenshots.py site docs/screenshots
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

PAD = 40


def frame(browser: Browser, png: bytes, width: int, height: int) -> bytes:
    """Lay a 2x page screenshot of CSS size width x height on the canvas as a card."""
    page = browser.new_page(
        viewport={"width": width + 2 * PAD + 2, "height": height + 2 * PAD + 2},
        device_scale_factor=2,
    )
    src = "data:image/png;base64," + base64.b64encode(png).decode()
    page.set_content(
        f'<body style="margin:0;padding:{PAD}px;background:#F3F8F7;width:{width + 2}px">'
        '<div style="border:1px solid #E2EAE8;border-radius:14px;overflow:hidden;'
        f'background:#FFFFFF;width:{width}px;height:{height}px">'
        f'<img style="display:block;width:{width}px;height:{height}px" src="{src}"></div></body>'
    )
    page.wait_for_function("document.images[0].complete")
    out = page.screenshot(full_page=True)
    page.close()
    return out


def main(site: Path, out: Path, raw: bool = False) -> int:
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for width in (360, 390, 768, 1280, 1440):
            page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
            page.emulate_media(reduced_motion="reduce")
            page.goto((site / "index.html").resolve().as_uri())
            page.wait_for_timeout(300)
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            full = page.screenshot(full_page=True)
            height = page.evaluate("document.documentElement.scrollHeight")
            shots = {f"dashboard-{width}.png": (full, height)}
            if width == 1440:  # the README image: the top of the page, at 2x
                shots["dashboard-top.png"] = (page.screenshot(full_page=False), 900)
            for name, (png, h) in shots.items():
                (out / name).write_bytes(png if raw else frame(browser, png, width, h))
            report[width] = {"horizontal_overflow_px": overflow}
            page.close()
        browser.close()
    (out / "screenshots.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if all(v["horizontal_overflow_px"] <= 0 for v in report.values()) else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--raw"]
    sys.exit(main(Path(args[0]), Path(args[1]), raw="--raw" in sys.argv))
