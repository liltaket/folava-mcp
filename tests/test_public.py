import runpy
from pathlib import Path

import pytest

CHECK = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_public.py"))


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("1234" + "~" + "x" * 60, "canvas_credential"),
        ("ghp" + "_" + "x" * 35, "github_credential"),
        ("-----BEGIN " + "PRIVATE KEY-----", "private_key"),
        ("/home/" + "student/private", "personal_path"),
        ("C:" + "\\Users\\" + "student\\private", "personal_path"),
        ("student" + "@" + "university.edu", "personal_email"),
    ],
)
def test_publication_tripwire_classifies_without_returning_values(value, kind):
    assert CHECK["findings"](value) == {kind}


def test_publication_tripwire_allows_explicit_fixtures_and_public_maintainer_metadata():
    text = (
        "demo@example.com https://user:private@bucket.s3.amazonaws.com/object "
        "maintainer@users.noreply.github.com https://canvas.example/api/v1/users/self"
    )
    assert CHECK["findings"](text) == set()
