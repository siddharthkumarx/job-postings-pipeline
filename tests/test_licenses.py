"""Licences (docs/decisions.md D-019): code under PolyForm Noncommercial 1.0.0, data under
CC BY-NC 4.0. The earlier terms are named only in LICENSE-HISTORY.md."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from jobpipe import readme
from jobpipe.site import build as site_build
from tests.test_site import _data

ROOT = Path(__file__).resolve().parents[1]
CODE = "PolyForm Noncommercial License 1.0.0"
DATA = "CC BY-NC 4.0"
# Names of the earlier terms (this file is skipped by the scan, since it names them too).
OLD = re.compile(
    "|".join(
        [
            r"\bMIT" + r" License\b",
            r"\bLICENSE\W+\(MIT\)",
            r"\bCC[ -]BY[ -]4\.0\b",
            r"\bcc-by-4" + r"\.0\b",
            r"creativecommons\.org/licenses/by/4\.0",
            r"open[- ]source pipeline",
        ]
    ),
    re.IGNORECASE,
)
SKIP = {"LICENSE-HISTORY.md", "uv.lock", "tests/test_licenses.py"}
TEXT = {".md", ".j2", ".py", ".js", ".yml", ".yaml", ".cff", ".toml", ".txt", ".html", ".css",
        ".json", ".jsonl", ".csv", ".svg", ""}  # fmt: skip


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [f for f in out.splitlines() if f]


def test_earlier_licences_only_in_the_history() -> None:
    hits = []
    for name in _tracked():
        path = ROOT / name
        if name in SKIP or name.startswith("checks/results/") or path.suffix not in TEXT:
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits += [f"{name}: {m.group(0)}" for m in OLD.finditer(text)]
    assert hits == []
    history = (ROOT / "LICENSE-HISTORY.md").read_text(encoding="utf-8")
    assert "MIT" in history and "CC BY 4.0" in history


def test_readme_and_dataset_card_render_the_current_licences(tmp_path: Path) -> None:
    text = readme.render(out=tmp_path / "README.md")  # also renders docs/dataset-card.md
    section = text[text.index("## License") :]
    assert f"[{CODE}](LICENSE)" in section and f"[{DATA}](LICENSE-DATA.md)" in section
    assert "[license history](LICENSE-HISTORY.md)" in section
    assert "](LICENSE)" in text.split("## What you get")[0]  # badge row
    assert "](LICENSE-DATA.md)" in text.split("## What you get")[0]
    card = (ROOT / "docs" / "dataset-card.md").read_text(encoding="utf-8")
    assert re.search(r"^license: cc-by-nc-4\.0$", card, flags=re.M)
    assert DATA in card and CODE in card and "source-available" in card


def test_citation_pyproject_and_dashboard_footer() -> None:
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert re.search(r"^license: PolyForm-Noncommercial-1\.0\.0$", cff, flags=re.M)
    assert re.search(r"^    license: CC-BY-NC-4\.0$", cff, flags=re.M)
    assert 'license = "PolyForm-Noncommercial-1.0.0"' in (ROOT / "pyproject.toml").read_text()
    assert "Noncommercial License 1.0.0" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "CC BY-NC 4.0" in (ROOT / "LICENSE-DATA.md").read_text(encoding="utf-8")
    html = site_build.render(_data(), {})
    footer = html[html.index("<footer") :]
    assert f'/blob/main/LICENSE">{CODE}</a>' in footer
    assert f'/blob/main/LICENSE-DATA.md">{DATA}</a>' in footer
