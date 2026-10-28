"""Exercise the static site without opening a web server or a shared browser tab."""

from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://folava.test/folava-mcp/"


def check(site: Path, screenshots: Path | None = None):
    site = site.resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100}, device_scale_factor=1
        )
        errors = []

        def serve(route):
            url = urlsplit(route.request.url)
            path = unquote(url.path).removeprefix("/folava-mcp/")
            target = (site / path).resolve()
            if not target.is_relative_to(site):
                return route.fulfill(status=403, body="Forbidden")
            if target.is_dir():
                target /= "index.html"
            if not target.exists():
                errors.append("Missing asset: " + url.path)
                return route.fulfill(status=404, body="Not found")
            route.fulfill(
                path=str(target), content_type=mimetypes.guess_type(target)[0] or "text/plain"
            )

        context.route(ORIGIN + "**", serve)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(ORIGIN)
        expect(page.get_by_role("heading", level=1)).to_have_text("Your courses.Within reach.")
        # Proper roving tab state and keyboard focus, including wrapping.
        feedback = page.get_by_role("tab", name="Feedback")
        feedback.click()
        expect(feedback).to_have_attribute("aria-selected", "true")
        expect(page.get_by_role("tabpanel")).to_contain_text("Help me understand")
        feedback.press("ArrowRight")
        expect(page.get_by_role("tab", name="Course files")).to_be_focused()
        expect(page.get_by_role("tabpanel")).to_contain_text("field-guide.txt")
        page.get_by_role("tab", name="Course files").press("Home")
        expect(page.get_by_role("tab", name="This week")).to_be_focused()
        # Clipboard success and an actual blocked-permission fallback.
        page.evaluate(
            "() => {navigator.clipboard.writeText = async text => {window.copied = text};}"
        )
        page.get_by_role("button", name="Copy installation command").click()
        expect(page.get_by_role("status")).to_have_text("Command copied.")
        assert "uv tool install https://github.com/liltaket/folava-mcp/releases/" in page.evaluate(
            "window.copied"
        )
        page.evaluate(
            "() => {navigator.clipboard.writeText = async () => {throw new Error('denied')};}"
        )
        page.get_by_role("button", name="Copy demo connection command").click()
        expect(page.get_by_role("status")).to_contain_text("copy it manually")
        assert (
            page.evaluate("window.getSelection().toString()")
            == "codex mcp add canvas-demo -- folava-mcp serve --demo"
        )
        page.goto(ORIGIN)
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshots / "home-desktop.png"), full_page=True)
        for width in (390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        if screenshots:
            page.set_viewport_size({"width": 390, "height": 900})
            page.screenshot(path=str(screenshots / "home-mobile.png"), full_page=True)
        page.goto(ORIGIN + "catalog/")
        operations = page.locator("[data-operation]")
        total = operations.count()
        assert total >= 100
        search = page.get_by_role("searchbox", name="Search operations")
        search.fill("submission")
        assert 1 < page.locator("[data-operation]:visible").count() < total
        page.locator("[data-operation]:visible").first.locator("summary").click()
        expect(page.locator("details[open]")).to_contain_text('"operation"')
        search.fill("an-operation-that-does-not-exist")
        expect(page.locator("#empty-search")).to_be_visible()
        search.fill("")
        assert page.locator("[data-operation]:visible").count() == total
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.goto(ORIGIN + "docs/getting-started/")
        expect(page.get_by_role("heading", name="Getting started", exact=True)).to_be_visible()
        page.get_by_role("navigation", name="Documentation sections").get_by_role(
            "link", name="Authentication", exact=True
        ).click()
        expect(page.get_by_role("heading", name="Connect Canvas", exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        if screenshots:
            page.screenshot(path=str(screenshots / "docs-mobile.png"), full_page=True)
        # Every page must expose a main landmark and a usable skip link.
        page.keyboard.press("Tab")
        assert page.locator("main#main").count() == 1
        assert not errors, errors
        browser.close()
    print(
        "Browser checks passed: tabs/keyboard, clipboard success/failure, "
        "catalog, docs, 320/390px layout."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "_site")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    check(args.site, args.screenshots)
