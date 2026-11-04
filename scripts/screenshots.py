"""Screenshot site/index.html at 360, 768 and 1440 px and report horizontal overflow.

Run: uv run --with playwright==1.64.1 python scripts/screenshots.py site docs/screenshots
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main(site: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for width in (360, 768, 1440):
            page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=2)
            page.emulate_media(reduced_motion="reduce")
            page.goto((site / "index.html").resolve().as_uri())
            page.wait_for_timeout(300)
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            page.screenshot(path=str(out / f"dashboard-{width}.png"), full_page=True)
            if width == 1440:  # the README image: the top of the page, at 2x
                page.screenshot(path=str(out / "dashboard-top.png"), full_page=False)
            report[width] = {"horizontal_overflow_px": overflow}
            page.close()
        browser.close()
    (out / "screenshots.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if all(v["horizontal_overflow_px"] <= 0 for v in report.values()) else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
