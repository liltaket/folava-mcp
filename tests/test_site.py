import hashlib
import json
import runpy
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / "scripts" / "build_site.py"))


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = []
        self.elements = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
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

    operations = json.loads((output / "operations.json").read_text(encoding="utf-8"))
    search_indexes = set()
    for page, parsed in pages.items():
        search_elements = [attrs for _, attrs in parsed.elements if attrs.get("data-search-index")]
        assert len(search_elements) == 1, page
        search_element = search_elements[0]
        assert "data-search-base" in search_element
        index_url = urlsplit(search_element["data-search-index"])
        assert index_url.path.endswith("/search-index.json")
        version = parse_qs(index_url.query).get("v", [""])[0]
        assert len(version) >= 8 and all(char in "0123456789abcdef" for char in version), page
        if index_url.scheme or index_url.netloc:
            pytest.fail((page, search_element["data-search-index"]))
        if index_url.path.startswith("/"):
            assert not base_path or index_url.path.startswith(base_path)
            index_path = (
                index_url.path[len(base_path) :] if base_path else index_url.path.lstrip("/")
            )
            index_file = output / unquote(index_path)
        else:
            index_file = (page.parent / unquote(index_url.path)).resolve()
        assert index_file.exists(), (page, search_element["data-search-index"])
        assert version == hashlib.sha256(index_file.read_bytes()).hexdigest()[:12], page
        search_indexes.add(index_file)

        base_url = urlsplit(search_element.get("data-search-base", ""))
        assert not base_url.scheme and not base_url.netloc, (page, base_url)
        if base_url.path.startswith("/"):
            assert not base_path or base_url.path.startswith(base_path)
            base_root = output / (
                base_url.path[len(base_path) :] if base_path else base_url.path.lstrip("/")
            )
        else:
            base_root = (page.parent / unquote(base_url.path)).resolve()
        assert base_root.resolve() == output.resolve(), (page, base_url.path, base_root)

    assert len(search_indexes) == 1
    search_index = json.loads(next(iter(search_indexes)).read_text(encoding="utf-8"))
    assert search_index["version"] == 1
    entries = search_index["entries"]
    required_entry_fields = {"title", "kind", "context", "url", "text"}
    assert entries and all(required_entry_fields <= entry.keys() for entry in entries)
    assert all(entry["kind"] in {"guide", "api"} for entry in entries)

    guide_urls = set()
    api_operation_ids = set()
    for entry in entries:
        result_url = urlsplit(entry["url"])
        assert not result_url.scheme and not result_url.netloc
        assert not result_url.path.startswith("/")
        assert all(part != ".." for part in result_url.path.split("/"))
        result_path = unquote(result_url.path)
        target = (output / result_path).resolve() if result_path else output / "index.html"
        if target.is_dir():
            target /= "index.html"
        assert target.exists(), entry["url"]
        if result_url.fragment:
            rendered_page = target if target.is_file() else target / "index.html"
            parsed_target = pages.get(rendered_page)
            assert (
                parsed_target is not None and unquote(result_url.fragment) in parsed_target.ids
            ), entry["url"]
        if entry["kind"] == "guide":
            guide_urls.add((result_url.path.rstrip("/"), result_url.fragment))
        else:
            assert result_url.path.rstrip("/") == "catalog"
            assert result_url.fragment.startswith("op-")
            api_operation_ids.add(result_url.fragment.removeprefix("op-"))

    assert api_operation_ids == {operation["id"] for operation in operations}
    for page in output.glob("docs/*/index.html"):
        slug = page.parent.name
        rendered = pages[page]
        for tag, attrs in rendered.elements:
            if tag == "h1":
                assert any(path == f"docs/{slug}" for path, _ in guide_urls), page
            elif tag in {"h2", "h3"}:
                assert (f"docs/{slug}", attrs["id"]) in guide_urls, (page, attrs.get("id"))

    catalog = pages[output / "catalog/index.html"]
    assert any(attrs.get("data-operation-group") is not None for _, attrs in catalog.elements)
    assert any(
        tag == "nav" and attrs.get("aria-label") == "API groups" for tag, attrs in catalog.elements
    )
    assert all(
        path.suffix not in (".sqlite", ".py", ".md") or path == output / "install.md"
        for path in output.rglob("*")
        if path.is_file()
    )
    guide = (output / "install.md").read_text(encoding="utf-8")
    assert guide == (ROOT / "docs/agent-setup.md").read_text(encoding="utf-8")
    assert BUILD["version_install"]() in guide


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


def test_section_links_preserve_existing_markdown_heading_links(tmp_path):
    source = tmp_path / "reference.md"
    source.write_text("## [Reference](https://example.org/)\n", encoding="utf-8")
    parsed = Links()
    parsed.feed(BUILD["markdown_document"](source, "./"))
    assert len(parsed.ids) == 1
    assert parsed.links == ["https://example.org/"]


def test_public_asset_urls_are_stable_until_the_asset_changes(tmp_path, monkeypatch):
    assets = tmp_path / "site/assets"
    assets.mkdir(parents=True)
    source = assets / "site.css"
    source.write_text("body { color: black }", encoding="utf-8")
    monkeypatch.setitem(BUILD["asset_url"].__globals__, "ROOT", tmp_path)
    first = BUILD["asset_url"]("/folava-mcp/", "site.css")
    assert BUILD["asset_url"]("/folava-mcp/", "site.css") == first
    source.write_text("body { color: white }", encoding="utf-8")
    changed = BUILD["asset_url"]("/folava-mcp/", "site.css")
    assert changed != first
    assert urlsplit(changed).path == urlsplit(first).path == "/folava-mcp/assets/site.css"
