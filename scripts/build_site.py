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
    "chatgpt": ("Use in ChatGPT", "docs/chatgpt.md"),
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
DOCUMENT_GROUPS = (
    ("Start here", ("getting-started", "agent-setup", "chatgpt", "authentication")),
    ("Using Folava", ("tools", "events", "privacy", "security", "release-readiness")),
    (
        "Project",
        (
            "architecture",
            "validation",
            "testing",
            "contributing",
            "branding",
            "releasing",
            "changelog",
        ),
    ),
)
CATALOG_GROUPS = (
    ("courses", "Courses"),
    ("assignments", "Assignments & feedback"),
    ("content", "Course content"),
    ("files", "Files & folders"),
    ("planning", "Calendar & planning"),
    ("people", "People & groups"),
    ("messages", "Messages"),
)
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


def catalog_group(operation: dict) -> str:
    """Group the public reference without changing the software's operation registry."""
    path = operation["path"]
    if any(part in path for part in ("/files", "/folders")):
        return "files"
    if any(part in path for part in ("/calendar_events", "/planner", "/todo", "/activity_stream")):
        return "planning"
    if "/conversations" in path:
        return "messages"
    if any(
        part in path
        for part in (
            "/assignments",
            "/assignment_groups",
            "/submissions",
            "/rubrics",
            "/grading_standards",
            "/outcome",
            "/missing_submissions",
        )
    ):
        return "assignments"
    if any(
        part in path
        for part in ("/modules", "/pages", "/discussion_topics", "/quizzes", "/announcements")
    ):
        return "content"
    if operation["id"] in {"courses", "course", "user_courses", "course_settings", "course_tabs"}:
        return "courses"
    return "people"


def document_tokens(source: Path):
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = md.parse(source.read_text(encoding="utf-8"))
    used = set()
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        slug = re.sub(r"[^\w\s-]", "", tokens[index + 1].content.lower()).replace(" ", "-")
        unique, number = slug, 1
        while unique in used:
            unique, number = f"{slug}-{number}", number + 1
        used.add(unique)
        token.attrSet("id", unique)
    return md, tokens


def plain_text(tokens) -> str:
    parts = []
    for token in tokens:
        if token.type == "inline":
            parts.extend(
                child.content if child.type in {"text", "code_inline", "image"} else " "
                for child in token.children or []
            )
        elif token.type in {"fence", "code_block"}:
            parts.append(token.content)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def search_index() -> dict:
    entries = [
        {
            "title": "Terminal setup",
            "kind": "guide",
            "context": "Get started",
            "url": "index.html#install",
            "text": "Install Folava MCP with uv. Connect the demo to Codex.",
        }
    ]
    for slug, (label, filename) in DOCUMENTS.items():
        _, tokens = document_tokens(ROOT / filename)
        title = next(
            (
                plain_text(tokens[i + 1 : i + 2])
                for i, token in enumerate(tokens)
                if token.tag == "h1" and token.type == "heading_open"
            ),
            label,
        )
        entries.append(
            {
                "title": title,
                "kind": "guide",
                "context": next(label for label, keys in DOCUMENT_GROUPS if slug in keys),
                "url": f"docs/{slug}/",
                "text": plain_text(tokens)[:1800],
            }
        )
        for index, token in enumerate(tokens):
            if token.type != "heading_open" or token.tag not in {"h2", "h3"}:
                continue
            end = next(
                (i for i in range(index + 3, len(tokens)) if tokens[i].type == "heading_open"),
                len(tokens),
            )
            entries.append(
                {
                    "title": plain_text(tokens[index + 1 : index + 2]),
                    "kind": "guide",
                    "context": label,
                    "url": f"docs/{slug}/#{token.attrGet('id')}",
                    "text": plain_text(tokens[index + 3 : end])[:1800],
                }
            )
    labels = dict(CATALOG_GROUPS)
    for operation in discover():
        entries.append(
            {
                "title": operation["id"],
                "kind": "api",
                "context": labels[catalog_group(operation)],
                "summary": operation["description"],
                "url": f"catalog/#op-{operation['id']}",
                "text": " ".join(
                    [
                        operation["description"],
                        operation["path"],
                        *operation["query_keys"],
                        "canvas_read GET",
                    ]
                ),
            }
        )
    return {"version": 1, "entries": entries}


def search_icon() -> str:
    return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>'


def copy_icons() -> str:
    return (
        '<svg class="copy-glyph" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<rect x="8" y="8" width="12" height="12" rx="2"/>'
        '<path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>'
        '<svg class="check-glyph" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path d="m5 12 4 4 10-10"/></svg>'
    )


def frame(
    title: str, content: str, base: str, *, route: str, active: str = "", search_version: str = ""
) -> str:
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
<script src="{asset_url(base, "theme.js")}"></script><link rel="stylesheet" href="{asset_url(base, "site.css")}"><link rel="stylesheet" href="{asset_url(base, "reference.css")}"><script defer src="{asset_url(base, "site.js")}"></script><script defer src="{asset_url(base, "search.js")}"></script>
</head><body><a class="skip-link" href="#main">Skip to content</a>
<header class="site-header"><div class="wrap header-inner"><a class="brand" href="{base}" aria-label="Folava MCP home">{brand_mark()}folava <span>MCP</span></a>
<div class="header-controls"><nav id="site-navigation" class="site-nav" aria-label="Main navigation">{nav("Guide", "docs/getting-started/", "docs")}{nav("API catalog", "catalog/", "catalog")}<a href="{REPO}">GitHub</a></nav>
<button id="site-search-open" class="search-trigger" type="button" aria-label="Search guides and API" aria-haspopup="dialog" aria-keyshortcuts="Meta+K Control+K" data-search-index="{base}search-index.json?v={search_version}" data-search-base="{base}" hidden>{search_icon()}<span class="search-trigger-label">Search…</span><kbd data-search-shortcut>Ctrl K</kbd></button>
<button id="theme-toggle" class="theme-toggle" type="button" aria-label="Switch to dark theme" title="Switch to dark theme" hidden>
<svg class="theme-moon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20.5 13.2A8.7 8.7 0 0 1 10.8 3.5a8.7 8.7 0 1 0 9.7 9.7Z"/></svg>
<svg class="theme-sun" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
</button><button id="site-menu-toggle" class="menu-toggle" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="site-navigation" hidden><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path class="menu-line-top" d="M5 8h14"/><path class="menu-line-bottom" d="M5 16h14"/></svg></button></div></div></header>
<main id="main" tabindex="-1">{content}</main>
<footer class="site-footer"><div class="wrap footer-inner"><p>Folava MCP · Independent open source · Apache-2.0</p><div class="footer-links"><a href="{base}docs/security/">Security</a><a href="{REPO}/releases">Releases</a><a href="{REPO}/issues">Issues</a></div></div></footer>
<div id="copy-status" class="visually-hidden" role="status" aria-live="polite" aria-atomic="true"></div>
<dialog id="site-search" class="search-dialog" aria-labelledby="site-search-title">
<div class="search-input-row">{search_icon()}<label id="site-search-title" class="visually-hidden" for="site-search-input">Search guides and API</label><input id="site-search-input" type="search" role="combobox" aria-autocomplete="list" aria-controls="site-search-results" aria-expanded="true" placeholder="Search guides and API…" autocomplete="off" spellcheck="false"><button id="site-search-close" class="search-close" type="button" aria-label="Close search"><span class="search-escape-label">Esc</span><svg class="search-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m6 6 12 12M18 6 6 18"/></svg></button></div>
<div class="search-panel"><p id="site-search-state" class="search-state" role="status" aria-live="polite"></p><ul id="site-search-results" role="listbox" aria-label="Search results"></ul><button id="site-search-retry" type="button" hidden>Retry search</button></div>
<footer class="search-footer"><span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span><span><kbd>↵</kbd> Open</span><span><kbd>Esc</kbd> Close</span></footer>
</dialog>
</body></html>'''


def markdown_document(source: Path, base: str) -> str:
    md, tokens = document_tokens(source)
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
            '<div class="code-block">' + block + '<button class="copy-button icon-copy" '
            'data-copy hidden aria-label="Copy code block">' + copy_icons() + "</button></div>"
        )

    md.renderer.rules["fence"] = fence
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
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


def reference_sidebar(base: str, navigation: str, *, catalog: bool = False) -> str:
    label = "API catalog" if catalog else "Guide"
    browse = "Browse API" if catalog else "Browse guides"
    landmark = "API groups" if catalog else "Documentation sections"
    related = (
        f'<a href="{base}docs/getting-started/">Read the guide</a>'
        if catalog
        else f'<a href="{base}catalog/">API catalog</a>'
    )
    return (
        f'<aside class="docs-sidebar reference-sidebar" aria-label="{label}">'
        f'<p class="reference-space-label">{label}</p>'
        f'<details id="reference-navigation" class="reference-menu" data-responsive-details="900" open>'
        f'<summary>{browse}</summary><nav aria-label="{landmark}">{navigation}</nav></details>'
        f'<p class="reference-related">{related}</p></aside>'
    )


def document_page(slug: str, base: str) -> str:
    title, filename = DOCUMENTS[slug]
    groups = []
    order = []
    for label, keys in DOCUMENT_GROUPS:
        links = []
        for key in keys:
            order.append(key)
            current = ' aria-current="page"' if key == slug else ""
            links.append(
                f'<li><a href="{base}docs/{key}/"{current}>{ESC(DOCUMENTS[key][0])}</a></li>'
            )
        groups.append(
            f'<div class="reference-nav-group"><p class="reference-nav-heading">{label}</p><ul>{"".join(links)}</ul></div>'
        )
    _, tokens = document_tokens(ROOT / filename)
    toc_links = [
        f'<a class="toc-{token.tag}" href="#{ESC(token.attrGet("id"))}">{ESC(plain_text(tokens[index + 1 : index + 2]))}</a>'
        for index, token in enumerate(tokens)
        if token.type == "heading_open" and token.tag in {"h2", "h3"}
    ]
    toc = (
        '<details id="page-navigation" class="page-toc" data-responsive-details="1200" open>'
        f'<summary>On this page</summary><nav aria-label="On this page">{"".join(toc_links)}</nav></details>'
        if toc_links
        else ""
    )
    position = order.index(slug)
    neighbors = []
    for label, index, relation in (
        ("Previous", position - 1, "prev"),
        ("Next", position + 1, "next"),
    ):
        if 0 <= index < len(order):
            key = order[index]
            neighbors.append(
                f'<a href="{base}docs/{key}/" rel="{relation}"><small>{label}</small><strong>{ESC(DOCUMENTS[key][0])}</strong></a>'
            )
    content = markdown_document(ROOT / filename, base)
    return (
        f'<div class="wrap reference-layout docs-layout">{reference_sidebar(base, "".join(groups))}'
        f'<div class="reference-main"><p class="reference-breadcrumb"><a href="{base}docs/getting-started/">Guide</a> / {ESC(title)}</p>'
        f'<div class="doc-grid">{toc}<article class="prose">{content}'
        f'<footer class="doc-footer"><a href="{REPO}/blob/main/{filename}">View source on GitHub</a>'
        f'<nav class="doc-pagination" aria-label="Guide pages">{"".join(neighbors)}</nav></footer>'
        "</article></div></div></div>"
    )


def catalog_page(base: str) -> str:
    operations = discover()
    groups = {key: [] for key, _ in CATALOG_GROUPS}
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
        groups[
            catalog_group(op)
        ].append(f'''<details class="operation" id="op-{ESC(op["id"])}" data-operation data-search="{ESC(search)}">
<summary><div><strong>{ESC(op["id"])}</strong><span>{ESC(op["description"])}</span></div><small class="operation-method">GET</small></summary>
<div class="operation-body"><p><code>GET {ESC(op["path"])}</code></p>
<p><strong>Path parameters:</strong> {ESC(required)}</p><p><strong>Query parameters:</strong> {ESC(keys)}</p>
<p>Common pagination: <code>page</code>, <code>per_page</code>, <code>bookmark</code>, <code>cursor</code>.
Permissions and token scopes still apply. <a href="{ESC(op["docs"])}">Canvas endpoint documentation</a></p>
<div class="code-block"><pre><code>{code}</code></pre><button class="copy-button icon-copy" data-copy hidden aria-label="Copy {ESC(op["id"])} example">{copy_icons()}</button></div></div></details>''')
    sections = []
    navigation = []
    for key, label in CATALOG_GROUPS:
        rows = groups[key]
        if not rows:
            continue
        count = f'<span data-group-count="{key}">{len(rows)}</span>'
        navigation.append(
            f'<li><a href="#group-{key}" data-catalog-link="{key}">{ESC(label)} {count}</a></li>'
        )
        sections.append(
            f'<section class="operation-group" id="group-{key}" data-operation-group="{key}"><h2>{ESC(label)} <span class="operation-group-count" data-group-count="{key}">{len(rows)}</span></h2>{"".join(rows)}</section>'
        )
    sidebar = reference_sidebar(
        base,
        f'<div class="reference-nav-group"><p class="reference-nav-heading">Resources</p><ul>{"".join(navigation)}</ul></div>',
        catalog=True,
    )
    return f'''<div class="wrap reference-layout catalog-layout">{sidebar}<div class="reference-main"><p class="reference-breadcrumb">Reference / API catalog</p><section class="catalog-intro"><h1>API catalog</h1><p>Find an operation and its arguments, then call <code>canvas_read</code>.</p>
<p class="catalog-guide">Your agent can browse the same catalog with <code>canvas_discover</code>.
<a href="{base}docs/tools/">Tool guide</a>.</p>
<div id="catalog-controls" class="catalog-controls" hidden><div class="search-field"><label class="search-label" for="operation-search">Filter operations<input id="operation-search" type="search" placeholder="Try submission, file, calendar…" autocomplete="off" spellcheck="false"></label><button id="clear-search" class="clear-search" type="button" hidden>Clear search</button></div>
<p id="operation-count" class="catalog-count" aria-live="polite">{len(operations)} of {len(operations)} operations</p></div></section>
<p id="catalog-fallback" class="catalog-guide">All operations are shown. Use your browser’s Find command to search this page.</p>
<div class="operation-list" aria-label="Reviewed operations"><div id="empty-search" class="empty-search" hidden><p>No operations match. Try a broader resource name.</p></div>{"".join(sections)}</div></div></div>'''


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
    index_bytes = (
        json.dumps(search_index(), ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    search_version = hashlib.sha256(index_bytes).hexdigest()[:12]
    (output / "search-index.json").write_bytes(index_bytes)

    def write(route, title, body, active=""):
        target = output / route
        target.parent.mkdir(parents=True, exist_ok=True)
        base = relative_base(route, base_path)
        target.write_text(
            frame(
                title, body(base), base, route=route, active=active, search_version=search_version
            ),
            encoding="utf-8",
        )

    def home(base):
        return (
            (ROOT / "site" / "index.html")
            .read_text(encoding="utf-8")
            .replace("{{BASE}}", base)
            .replace("{{VERSION}}", release_version())
            .replace("{{INSTALL_COMMAND}}", ESC(version_install()))
            .replace("{{AGENT_PROMPT}}", ESC(AGENT_PROMPT))
            .replace("{{COPY_ICONS}}", copy_icons())
            .replace("{{BRAND_MARK}}", brand_mark())
        )

    write("index.html", "Your agent, meet Canvas", home)
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
