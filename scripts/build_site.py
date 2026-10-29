"""Build GitHub Pages from canonical Markdown and the actual operation catalog."""

# HTML templates intentionally keep a few attribute/text lines together.
# ruff: noqa: E501
from __future__ import annotations

import argparse
import hashlib
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
    "branding": ("Project identity", "docs/branding.md"),
    "releasing": ("Release checklist", "docs/releasing.md"),
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


def brand_mark() -> str:
    return (
        (ROOT / "site/assets/mark.svg")
        .read_text(encoding="utf-8")
        .replace("<svg ", '<svg class="brand-mark" aria-hidden="true" focusable="false" ', 1)
    )


def asset_url(base: str, name: str) -> str:
    source = "mark.svg" if name == "favicon.svg" else name
    digest = hashlib.sha256((ROOT / "site/assets" / source).read_bytes()).hexdigest()[:12]
    return f"{base}assets/{name}?v={digest}"


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
<meta name="description" content="Canvas courses, deadlines and feedback for your agent. Folava MCP is an independent open-source development preview.">
<meta name="theme-color" content="#ffffff"><meta name="color-scheme" content="light dark">
<link rel="canonical" href="{canonical}"><link rel="icon" href="{asset_url(base, "favicon.svg")}" type="image/svg+xml">
<script src="{asset_url(base, "theme.js")}"></script><link rel="stylesheet" href="{asset_url(base, "site.css")}"><script defer src="{asset_url(base, "site.js")}"></script>
</head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><div class="wrap header-inner"><a class="brand" href="{base}" aria-label="Folava MCP home">{brand_mark()}folava <span>MCP</span></a>
<div class="header-controls"><nav class="site-nav" aria-label="Main navigation">{nav("Guide", "docs/getting-started/", "docs")}{nav("API catalog", "catalog/", "catalog")}<a href="{REPO}">GitHub</a></nav>
<button id="theme-toggle" class="theme-toggle" type="button" aria-label="Switch to dark theme" title="Switch to dark theme" hidden>
<svg class="theme-moon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20.5 13.2A8.7 8.7 0 0 1 10.8 3.5a8.7 8.7 0 1 0 9.7 9.7Z"/></svg>
<svg class="theme-sun" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
</button></div></div></header>
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
            children = tokens[index + 1].children or []
            if token.tag in ("h2", "h3") and not any(
                child.type == "link_open" for child in children
            ):
                token.meta["section_link"] = True
                tokens[index + 2].meta["section_link"] = True

    def heading_open(tokens, idx, options, env):
        opening = md.renderer.renderToken(tokens, idx, options, env)
        if tokens[idx].meta.get("section_link"):
            opening += f'<a class="heading-link" href="#{ESC(tokens[idx].attrGet("id"))}">'
        return opening

    def heading_close(tokens, idx, options, env):
        prefix = "</a>" if tokens[idx].meta.get("section_link") else ""
        return prefix + md.renderer.renderToken(tokens, idx, options, env)

    md.renderer.rules["heading_open"] = heading_open
    md.renderer.rules["heading_close"] = heading_close
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
        f'<a href="{REPO}/blob/main/{filename}">View source on GitHub</a></p></article></div>'
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
<p><strong>Path parameters:</strong> {ESC(required)}</p><p><strong>Query parameters:</strong> {ESC(keys)}</p>
<p>Common pagination: <code>page</code>, <code>per_page</code>, <code>bookmark</code>, <code>cursor</code>.
Permissions and token scopes still apply. <a href="{ESC(op["docs"])}">Canvas endpoint documentation</a></p>
<div class="code-block"><pre><code>{code}</code></pre><button class="copy-button" data-copy hidden aria-label="Copy {ESC(op["id"])} example">Copy</button></div></div></details>''')
    return f'''<section class="wrap catalog-intro"><h1>API catalog</h1><p>Find an operation and its arguments, then call <code>canvas_read</code>.</p>
<p class="catalog-guide">Your agent can browse the same catalog with <code>canvas_discover</code>.
<a href="{base}docs/tools/">Tool guide</a>.</p>
<div id="catalog-controls" class="catalog-controls" hidden><div class="search-field"><label class="search-label" for="operation-search">Search operations<input id="operation-search" type="search" placeholder="Try submission, file, calendar…" autocomplete="off" spellcheck="false"></label><button id="clear-search" class="clear-search" type="button" hidden>Clear search</button></div>
<p id="operation-count" class="catalog-count" aria-live="polite">{len(operations)} of {len(operations)} operations</p></div></section>
<p id="catalog-fallback" class="wrap catalog-guide">All operations are shown. Use your browser’s Find command to search this page.</p>
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
    shutil.copyfile(ROOT / "site/assets/mark.svg", output / "assets/favicon.svg")

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
            .replace("{{BRAND_MARK}}", brand_mark())
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
