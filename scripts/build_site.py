"""Build GitHub Pages from canonical Markdown and the actual operation catalog."""

# HTML templates intentionally keep a few attribute/text lines together.
# ruff: noqa: E501
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from folava_mcp.catalog import discover  # noqa: E402

REPO = "https://github.com/liltaket/folava-mcp"
SITE = "https://liltaket.github.io/folava-mcp/"
DOCUMENTS = {
    "getting-started": ("Get started", "docs/getting-started.md"),
    "agent-setup": ("Set up with your agent", "docs/agent-setup.md"),
    "authentication": ("Authentication", "docs/authentication.md"),
    "tools": ("Tools and files", "docs/tools.md"),
    "events": ("Change feed", "docs/events.md"),
    "architecture": ("Architecture", "docs/architecture.md"),
    "privacy": ("Data handling", "docs/privacy.md"),
    "release-readiness": ("Deployment limits", "docs/release-readiness.md"),
    "validation": ("Validation", "docs/validation.md"),
    "testing": ("Test scenarios", "docs/testing.md"),
    "contributing": ("Contribute", "CONTRIBUTING.md"),
    "security": ("Security", "SECURITY.md"),
    "changelog": ("Changelog", "CHANGELOG.md"),
}
RELEASE_MANIFEST = ROOT / "site" / "release.json"
ESC = html.escape
SETUP_URL = SITE + "install.md"
AGENT_PROMPT = (
    f"Set up Folava MCP using {SETUP_URL}. "
    "Install the published release, connect its demo to my MCP client, and check that it works. "
    "Then guide me through connecting Canvas; keep credentials outside this conversation."
)


def release_version() -> str:
    version = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("The site release must name a published numeric version.")
    return version


def version_install() -> str:
    version = release_version()
    return (
        f"uv tool install {REPO}/releases/download/v{version}/folava_mcp-{version}-py3-none-any.whl"
    )


def verify_release() -> None:
    """Fail before deployment if the human-selected installer is not published."""
    from urllib.request import Request, urlopen

    url = version_install().removeprefix("uv tool install ")
    with urlopen(Request(url, method="HEAD"), timeout=20) as response:
        if response.status != 200 or urlsplit(response.url).scheme != "https":
            raise ValueError("The selected release installer is not available over HTTPS.")


def relative_base(route: str, base_path: str) -> str:
    if base_path:
        return base_path
    depth = len(Path(route).parent.parts)
    return "../" * depth if depth else "./"


def frame(title: str, content: str, base: str, *, route: str, active: str = "") -> str:
    def nav(label, path, key):
        current = ""
        if active == key:
            value = "page" if route == path + "index.html" else "location"
            current = f' aria-current="{value}"'
        return f'<a href="{base}{path}"{current}>{label}</a>'

    canonical = SITE + route.removesuffix("index.html")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{ESC(title)} · Folava MCP</title>
<meta name="description" content="Read-only Canvas LMS access for your agents. Install Folava MCP, explore the tools, and connect your own environment.">
<meta name="theme-color" content="#ffffff"><meta name="color-scheme" content="light dark">
<link rel="canonical" href="{canonical}"><link rel="icon" href="{base}assets/favicon.svg" type="image/svg+xml">
<script src="{base}assets/theme.js"></script><link rel="stylesheet" href="{base}assets/site.css"><script defer src="{base}assets/site.js"></script>
</head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><div class="wrap header-inner"><a class="brand" href="{base}" aria-label="Folava MCP home">folava <span>MCP</span></a>
<div class="header-controls"><nav class="site-nav" aria-label="Main navigation">{nav("Guide", "docs/getting-started/", "docs")}{nav("API catalog", "catalog/", "catalog")}<a href="{REPO}">GitHub</a></nav>
<label class="theme-control" hidden for="theme-choice"><span>Theme</span><select id="theme-choice"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label></div></div></header>
<main id="main" tabindex="-1">{content}</main>
<footer class="site-footer"><div class="wrap footer-inner"><p>Folava MCP · Independent open source · Apache-2.0</p><div class="footer-links"><a href="{base}docs/security/">Security</a><a href="{REPO}/releases">Releases</a><a href="{REPO}/issues">Issues</a></div></div></footer>
<div id="copy-status" class="copy-status" role="status" aria-live="polite"></div>
</body></html>'''


def markdown_document(source: Path, base: str) -> str:
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    link_rule = md.renderer.rules.get("link_open", md.renderer.renderToken)

    def link_open(tokens, idx, options, env):
        href = tokens[idx].attrGet("href") or ""
        parsed = urlsplit(href)
        if not parsed.scheme and not parsed.netloc and parsed.path:
            target = (source.parent / parsed.path).resolve()
            suffix = "#" + parsed.fragment if parsed.fragment else ""
            slug = next(
                (key for key, (_, file) in DOCUMENTS.items() if (ROOT / file).resolve() == target),
                None,
            )
            if slug:
                tokens[idx].attrSet("href", base + "docs/" + slug + "/" + suffix)
            elif target.is_relative_to(ROOT):
                tokens[idx].attrSet(
                    "href", REPO + "/blob/main/" + target.relative_to(ROOT).as_posix() + suffix
                )
        return link_rule(tokens, idx, options, env)

    md.renderer.rules["link_open"] = link_open
    fence_rule = md.renderer.rules["fence"]

    def fence(tokens, idx, options, env):
        block = fence_rule(tokens, idx, options, env)
        return (
            '<div class="code-block">' + block + '<button class="copy-button" '
            'data-copy hidden aria-label="Copy code block">Copy</button></div>'
        )

    md.renderer.rules["fence"] = fence
    tokens = md.parse(source.read_text(encoding="utf-8"))
    used = set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            text = tokens[index + 1].content
            slug = re.sub(r"[^\w\s-]", "", text.lower()).replace(" ", "-")
            unique, number = slug, 1
            while unique in used:
                unique, number = f"{slug}-{number}", number + 1
            used.add(unique)
            token.attrSet("id", unique)
    return md.renderer.render(tokens, md.options, {})


def document_page(slug: str, base: str) -> str:
    title, filename = DOCUMENTS[slug]
    links = []
    for key, (label, _) in DOCUMENTS.items():
        current = ' aria-current="page"' if key == slug else ""
        links.append(f'<li><a href="{base}docs/{key}/"{current}>{label}</a></li>')
    content = markdown_document(ROOT / filename, base)
    return (
        f'<div class="wrap docs-layout"><aside class="docs-sidebar" aria-label="Documentation">'
        f'<p>Documentation</p><nav aria-label="Documentation sections"><ul>{"".join(links)}</ul></nav></aside>'
        f'<article class="prose">{content}<p class="edit-link">'
        f'<a href="{REPO}/blob/main/{filename}">View this document on GitHub</a></p></article></div>'
    )


def catalog_page(base: str) -> str:
    operations = discover()
    rows = []
    for op in operations:
        search = " ".join([op["id"], op["path"], op["description"], *op["query_keys"]]).lower()
        required = ", ".join(op["required_path"]) or "None"
        keys = ", ".join(op["query_keys"]) or "No operation-specific parameters"
        example = {"operation": op["id"]}
        if op["required_path"]:
            example["path"] = {
                key: (
                    "self"
                    if key == "user_id"
                    else "reading-notes"
                    if key == "page_url"
                    else "101"
                    if key == "course_id"
                    else "1"
                )
                for key in op["required_path"]
            }
        code = ESC(json.dumps(example, indent=2, ensure_ascii=False))
        rows.append(f'''<details class="operation" id="op-{ESC(op["id"])}" data-operation data-search="{ESC(search)}">
<summary><div><strong>{ESC(op["id"])}</strong><span>{ESC(op["description"])}</span></div></summary>
<div class="operation-body"><p><code>GET {ESC(op["path"])}</code></p>
<p><strong>Path arguments:</strong> {ESC(required)}</p><p><strong>Query keys:</strong> {ESC(keys)}</p>
<p>Common pagination: <code>page</code>, <code>per_page</code>, <code>bookmark</code>, <code>cursor</code>.
Permissions and token scopes still apply. <a href="{ESC(op["docs"])}">Official endpoint documentation</a></p>
<div class="code-block"><pre><code>{code}</code></pre><button class="copy-button" data-copy hidden aria-label="Copy {ESC(op["id"])} example">Copy</button></div></div></details>''')
    return f'''<section class="wrap catalog-intro"><h1>The read catalog</h1><p>Find a resource, inspect its arguments, then call <code>canvas_read</code>.
These {len(operations)} operation IDs come directly from the software’s reviewed registry, including workflow aliases.</p>
<p class="catalog-guide">Use <code>canvas_discover</code> from your agent for the same catalog.
Unknown methods, routes and query keys are rejected. <a href="{base}docs/tools/">Read the tool guide</a>.</p>
<div class="catalog-controls"><label class="search-label" for="operation-search">Search operations<input id="operation-search" type="search" placeholder="Try submission, file, calendar…" autocomplete="off" spellcheck="false"></label>
<p id="operation-count" class="catalog-count" aria-live="polite">{len(operations)} of {len(operations)} operations</p></div></section>
<section class="wrap operation-list" aria-label="Reviewed operations"><div id="empty-search" class="empty-search" hidden><p>No operations match. Try a broader resource name.</p></div>{"".join(rows)}</section>'''


def build(output: Path, base_path: str = "/folava-mcp/") -> None:
    output = output.resolve()
    if output == ROOT or ROOT.is_relative_to(output) or output == ROOT / "site":
        raise ValueError("Output must be a dedicated build directory.")
    if base_path and (
        not base_path.startswith("/")
        or not base_path.endswith("/")
        or ".." in base_path
        or any(c in base_path for c in '\\<>"?#')
    ):
        raise ValueError("Base path must be an absolute URL path ending with /, or empty.")
    # Never copy the repository wholesale; only deliberate public assets and docs.
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "site" / "assets", output / "assets", dirs_exist_ok=True)

    def write(route, title, body, active=""):
        target = output / route
        target.parent.mkdir(parents=True, exist_ok=True)
        base = relative_base(route, base_path)
        target.write_text(
            frame(title, body(base), base, route=route, active=active), encoding="utf-8"
        )

    def home(base):
        return (
            (ROOT / "site" / "index.html")
            .read_text(encoding="utf-8")
            .replace("{{BASE}}", base)
            .replace("{{VERSION}}", release_version())
            .replace("{{INSTALL_COMMAND}}", ESC(version_install()))
            .replace("{{AGENT_PROMPT}}", ESC(AGENT_PROMPT))
            .replace("{{SETUP_URL}}", ESC(SETUP_URL))
        )

    write("index.html", "Your agent, meet Canvas.", home)
    write("catalog/index.html", "API catalog", catalog_page, "catalog")
    for slug, (title, _) in DOCUMENTS.items():
        write(
            f"docs/{slug}/index.html",
            title,
            lambda base, slug=slug: document_page(slug, base),
            "docs",
        )
    write(
        "404.html",
        "Page not found",
        lambda base: (
            '<section class="wrap not-found"><h1>That page isn’t here.</h1><p>The link may have changed. Find the guide or return to the homepage.</p>'
            f'<a class="button primary" href="{base}">Go to Folava</a></section>'
        ),
    )
    (output / ".nojekyll").touch()
    # A deliberate, public plain-text entry point for agent-driven installation.
    shutil.copyfile(ROOT / "docs" / "agent-setup.md", output / "install.md")
    (output / "operations.json").write_text(
        json.dumps(discover(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE}sitemap.xml\n", encoding="utf-8"
    )
    urls = [SITE, SITE + "catalog/"] + [SITE + f"docs/{slug}/" for slug in DOCUMENTS]
    (output / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{url}</loc></url>" for url in urls)
        + "</urlset>\n",
        encoding="utf-8",
    )
    print(f"Built {len(DOCUMENTS) + 3} pages and {len(discover())} catalog entries in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    parser.add_argument("--base-path", default="/folava-mcp/")
    parser.add_argument("--verify-release", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify_release:
        verify_release()
    build(arguments.output, arguments.base_path)
