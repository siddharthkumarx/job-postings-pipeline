import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from commit_guard import clean, problems

MSG = "feat: add a thing\n\nBody text explaining why.\n"


def test_plain_message_passes() -> None:
    assert problems(MSG) == []
    assert clean(MSG) == MSG


def test_signed_off_by_is_allowed() -> None:
    msg = MSG + "\nSigned-off-by: A <a@example.com>\n"
    assert problems(msg) == []
    assert clean(msg) == msg


def test_other_trailers_are_removed_and_flagged() -> None:
    msg = MSG + "\nReviewed-by: A\nSigned-off-by: B <b@example.com>\nHelped-by: C\n"
    assert problems(msg) == ["trailer: Reviewed-by: A", "trailer: Helped-by: C"]
    assert clean(msg) == MSG + "\nSigned-off-by: B <b@example.com>\n"


def test_generated_with_footer_is_removed_and_flagged() -> None:
    msg = MSG + "\nGenerated with SomeTool\n"
    assert problems(msg) == ["footer: Generated with SomeTool"]
    assert clean(msg) == MSG
    assert problems(MSG + "\n* Generated with a tool (example.com)\n")


def test_colon_lines_in_the_body_are_not_trailers() -> None:
    msg = "fix: x\n\nNote: this explains something.\n\nMore prose after it.\n"
    assert problems(msg) == []
    assert problems("docs: subject only: with a colon\n") == []
