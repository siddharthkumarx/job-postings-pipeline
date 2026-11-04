"""Render a Markdown file to a styled PDF (Playwright Chromium).

Run: uv run --with markdown==3.9 --with playwright==1.64.1 python scripts/md_to_pdf.py IN.md OUT.pdf
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Instrument Sans', system-ui, sans-serif; color: #1a2624; font-size: 11pt;
       line-height: 1.5; }
h1 { font-size: 20pt; color: #0B1416; border-bottom: 3px solid #2FBFAE; padding-bottom: 6px; }
h2 { font-size: 14pt; color: #0B1416; margin-top: 20px; }
strong { color: #0B1416; }
code { font-family: 'IBM Plex Mono', monospace; font-size: 9.5pt; background: #eef3f2;
       padding: 1px 4px; border-radius: 3px; }
li { margin: 3px 0; }
"""


def main(src: Path, dst: Path) -> None:
    fonts = Path("src/jobpipe/site/assets/fonts").resolve()
    faces = (
        f"@font-face{{font-family:'Instrument Sans';src:url(file://{fonts}/instrument-sans-latin-400-normal.woff2)}}"
        f"@font-face{{font-family:'Instrument Sans';font-weight:600;src:url(file://{fonts}/instrument-sans-latin-600-normal.woff2)}}"
        f"@font-face{{font-family:'IBM Plex Mono';src:url(file://{fonts}/ibm-plex-mono-latin-400-normal.woff2)}}"
    )
    body = markdown.markdown(src.read_text(encoding="utf-8"), extensions=["tables"])
    html = dst.with_suffix(".html")
    html.write_text(f"<html><head><meta charset='utf-8'><style>{faces}{CSS}</style></head>"
                    f"<body>{body}</body></html>", encoding="utf-8")  # fmt: skip
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page()
        page.goto(html.resolve().as_uri())
        page.wait_for_timeout(300)
        page.pdf(path=str(dst), format="A4", print_background=True)
        browser.close()
    html.unlink()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
