import json
import runpy
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / "scripts" / "build_site.py"))


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag in ("a", "link") and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "script" and attrs.get("src"):
            self.links.append(attrs["src"])


@pytest.mark.parametrize("base_path", ["", "/folava-mcp/"])
def test_site_build_links_and_catalog_match_software(tmp_path, base_path):
    output = tmp_path / "public"
    BUILD["build"](output, base_path)
    from folava_mcp.catalog import discover

    assert json.loads((output / "operations.json").read_text()) == json.loads(
        json.dumps(discover())
    )
    pages = {}
    for page in output.rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert "{{" not in text
        parsed = Links()
        parsed.feed(text)
        assert len(parsed.ids) == len(set(parsed.ids)), page
        pages[page] = parsed
    for page, parsed in pages.items():
        for link in parsed.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            if url.path.startswith("/"):
                assert url.path.startswith(base_path)
                target = output / unquote(url.path[len(base_path) :])
            else:
                target = (page.parent / unquote(url.path)).resolve() if url.path else page
            if target.is_dir():
                target /= "index.html"
            assert target.exists(), (page, link)
            if url.fragment and target in pages:
                assert unquote(url.fragment) in pages[target].ids, (page, link)
    assert all(
        path.suffix not in (".sqlite", ".py", ".md") or path == output / "install.md"
        for path in output.rglob("*")
        if path.is_file()
    )
    assert (output / "install.md").read_text() == (ROOT / "docs/agent-setup.md").read_text()
    assert BUILD["version_install"]() in (output / "install.md").read_text()


def test_reject_dangerous_site_output_and_base(tmp_path):
    for target in (ROOT, ROOT.parent, ROOT / "site"):
        with pytest.raises(ValueError):
            BUILD["build"](target)
    with pytest.raises(ValueError):
        BUILD["build"](tmp_path / "public", "https://evil.example/")


def test_site_installer_uses_explicit_published_version(tmp_path, monkeypatch):
    manifest = tmp_path / "release.json"
    manifest.write_text('{"version":"0.1.0"}')
    monkeypatch.setitem(BUILD["version_install"].__globals__, "RELEASE_MANIFEST", manifest)
    assert "/download/v0.1.0/folava_mcp-0.1.0-" in BUILD["version_install"]()
    manifest.write_text('{"version":"../../not-a-release"}')
    with pytest.raises(ValueError):
        BUILD["version_install"]()


def test_unpublished_installer_check_stops_deployment(monkeypatch):
    import urllib.error
    import urllib.request

    def missing(request, **kwargs):
        assert request.get_method() == "HEAD" and kwargs["timeout"] == 20
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", missing)
    with pytest.raises(urllib.error.HTTPError):
        BUILD["verify_release"]()
