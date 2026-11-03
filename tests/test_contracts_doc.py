import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import gen_marts_yml


def test_marts_yml_matches_contract_doc() -> None:
    on_disk = Path("dbt/models/marts/_marts.yml").read_text(encoding="utf-8")
    assert on_disk == gen_marts_yml.render(), "run: uv run python scripts/gen_marts_yml.py"
