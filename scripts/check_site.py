"""Exercise the static site without opening a web server or a shared browser tab."""

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://folava.test/folava-mcp/"


def check_theme(page, expected):
    expect(page.locator("html")).to_have_attribute("data-theme", expected)
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute(
        "content", "#18181b" if expected == "dark" else "#ffffff"
    )
    # Read the actual surfaces, including nested code, controls and status colors.
    failures = page.evaluate(
        """() => {
          const canvas = document.createElement('canvas');
          canvas.width = canvas.height = 1;
          const context = canvas.getContext('2d', {willReadFrequently: true});
          const rgba = value => {
            context.clearRect(0, 0, 1, 1);
            context.fillStyle = value;
            context.fillRect(0, 0, 1, 1);
            const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
            return [r, g, b, a / 255];
          };
          const luminance = color => color.slice(0, 3).map(c => {
            c /= 255;
            return c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
          }).reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
          const background = element => {
            if (!element) return [255, 255, 255];
            const [r, g, b, alpha] = rgba(getComputedStyle(element).backgroundColor);
            const underneath = background(element.parentElement);
            return [r, g, b].map((channel, i) =>
              channel * alpha + underneath[i] * (1 - alpha));
          };
          const selectors = ['body', '.muted', '.site-nav a', '.theme-control',
            '.theme-control select', '.primary', '.source-type', '.source-meta',
            '.install-band', '.install-band .small', '.code-block', '.copy-button',
            '.operation summary span', '.docs-sidebar a', 'input', '.copy-status',
            '.agent-setup', '.setup-prompt', '.copy-link'];
          return selectors.flatMap(selector => [...document.querySelectorAll(selector)]
            .filter(element => element.getClientRects().length)
            .flatMap(element => {
              const a = luminance(rgba(getComputedStyle(element).color));
              const b = luminance(background(element));
              const ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
              return ratio < 4.5 ? [`${selector}: ${ratio.toFixed(2)}`] : [];
            }));
        }"""
    )
    assert not failures, failures


def check(site: Path, screenshots: Path | None = None):
    site = site.resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            device_scale_factor=1,
            color_scheme="light",
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
            if target.name == "theme.js":
                # Observe the initializer when it executes, before body content can paint.
                return route.fulfill(
                    body=target.read_text() + "\nwindow.themeAtInit = {"
                    "theme: document.documentElement.dataset.theme, body: !!document.body};",
                    content_type="application/javascript",
                )
            route.fulfill(
                path=str(target), content_type=mimetypes.guess_type(target)[0] or "text/plain"
            )

        context.route(ORIGIN + "**", serve)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(ORIGIN)
        expect(page.get_by_role("heading", level=1)).to_have_text("Your agent,meet Canvas.")
        theme = page.get_by_role("combobox", name="Theme")
        expect(theme).to_have_value("system")
        check_theme(page, "light")
        page.emulate_media(color_scheme="dark")
        check_theme(page, "dark")
        theme.select_option("light")
        page.emulate_media(color_scheme="light")
        page.emulate_media(color_scheme="dark")
        check_theme(page, "light")
        theme.select_option("dark")
        page.goto(ORIGIN + "catalog/")
        check_theme(page, "dark")
        expect(page.get_by_role("combobox", name="Theme")).to_have_value("dark")
        page.goto(ORIGIN + "docs/getting-started/")
        check_theme(page, "dark")
        page.goto(ORIGIN)
        assert page.evaluate("window.themeAtInit") == {"theme": "dark", "body": False}
        # Native select behavior remains usable without a pointer.
        theme.focus()
        theme.press("Home")
        expect(theme).to_have_value("system")
        theme.press("ArrowDown")
        expect(theme).to_have_value("light")
        check_theme(page, "light")
        assert theme.evaluate("element => getComputedStyle(element).outlineStyle") == "solid"
        theme.select_option("system")
        page.goto(ORIGIN)
        expect(theme).to_have_value("system")
        page.emulate_media(color_scheme="light")
        check_theme(page, "light")
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
        page.get_by_role("button", name="Copy setup prompt").click()
        expect(page.get_by_role("status")).to_have_text("Setup prompt copied.")
        expect(page.get_by_role("button", name="Copy setup prompt")).to_have_text(
            "Copy setup prompt"
        )
        prompt = page.evaluate("window.copied")
        assert "https://liltaket.github.io/folava-mcp/install.md" in prompt
        assert "demo" in prompt and "credentials outside" in prompt
        page.get_by_role("button", name="Copy link", exact=True).click()
        assert page.evaluate("window.copied") == "https://liltaket.github.io/folava-mcp/install.md"
        expect(page.get_by_role("status")).to_have_text("Setup link copied.")
        page.get_by_role("button", name="Copy installation command").click()
        expect(page.get_by_role("status")).to_have_text("Command copied.")
        check_theme(page, "light")
        theme.select_option("dark")
        check_theme(page, "dark")
        theme.select_option("light")
        assert "uv tool install https://github.com/liltaket/folava-mcp/releases/" in page.evaluate(
            "window.copied"
        )
        page.evaluate(
            "() => {navigator.clipboard.writeText = async () => {throw new Error('denied')};}"
        )
        page.reload()
        page.evaluate(
            "() => {navigator.clipboard.writeText = async () => {throw new Error('denied')};}"
        )
        page.get_by_role("button", name="Copy setup prompt").click()
        expect(page.get_by_role("status")).to_contain_text("copy it manually")
        assert page.evaluate("window.getSelection().toString()") == prompt
        page.get_by_role("button", name="Copy demo connection command").click()
        expect(page.get_by_role("status")).to_contain_text("copy it manually")
        assert (
            page.evaluate("window.getSelection().toString()")
            == "codex mcp add canvas-demo -- folava-mcp serve --demo"
        )
        page.goto(ORIGIN)
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(
                path=str(screenshots / "home-desktop.png"), full_page=True, animations="disabled"
            )
        for width in (390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            expect(theme).to_be_visible()
            theme.select_option("dark")
            check_theme(page, "dark")
            theme.select_option("light")
        if screenshots:
            page.set_viewport_size({"width": 390, "height": 900})
            page.reload()
            page.screenshot(
                path=str(screenshots / "home-mobile.png"), full_page=True, animations="disabled"
            )
        page.goto(ORIGIN + "catalog/")
        check_theme(page, "light")
        operations = page.locator("[data-operation]")
        total = operations.count()
        assert total == len(json.loads((site / "operations.json").read_text())) > 0
        search = page.get_by_role("searchbox", name="Search operations")
        search.fill("submission")
        assert 1 < page.locator("[data-operation]:visible").count() < total
        page.locator("[data-operation]:visible").first.locator("summary").click()
        expect(page.locator("details[open]")).to_contain_text('"operation"')
        check_theme(page, "light")
        theme.select_option("dark")
        check_theme(page, "dark")
        theme.select_option("light")
        search.fill("an-operation-that-does-not-exist")
        expect(page.locator("#empty-search")).to_be_visible()
        search.fill("")
        assert page.locator("[data-operation]:visible").count() == total
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.goto(ORIGIN + "docs/getting-started/")
        check_theme(page, "light")
        expect(page.get_by_role("heading", name="Getting started", exact=True)).to_be_visible()
        page.get_by_role("navigation", name="Documentation sections").get_by_role(
            "link", name="Authentication", exact=True
        ).click()
        expect(page.get_by_role("heading", name="Connect Canvas", exact=True)).to_be_visible()
        expect(
            page.get_by_role("navigation", name="Main navigation").get_by_role(
                "link", name="Guide", exact=True
            )
        ).to_have_attribute("aria-current", "location")
        for width in (1440, 390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            page.get_by_role("combobox", name="Theme").select_option("dark")
            check_theme(page, "dark")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.goto(ORIGIN + "docs/getting-started/#codex")
        heading = page.get_by_role("heading", name="Codex", exact=True)
        expect(heading).to_be_visible()
        bounds = page.locator(".header-inner").bounding_box()
        assert bounds["y"] >= 0 and bounds["y"] < 25
        assert heading.bounding_box()["y"] >= bounds["y"] + bounds["height"]
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        if screenshots:
            page.screenshot(
                path=str(screenshots / "docs-mobile.png"), full_page=True, animations="disabled"
            )
        # Exercise skip navigation and theme control in the keyboard order on each surface.
        for route in ("", "catalog/", "docs/getting-started/"):
            page.goto(ORIGIN + route)
            page.keyboard.press("Tab")
            expect(page.get_by_role("link", name="Skip to content")).to_be_focused()
            page.keyboard.press("Enter")
            assert page.evaluate("document.activeElement.id") == "main"
            page.get_by_role("combobox", name="Theme").focus()
            page.keyboard.press("Home")
            page.keyboard.press("End")
            expect(page.get_by_role("combobox", name="Theme")).to_have_value("dark")
        page.goto(ORIGIN)
        page.emulate_media(reduced_motion="reduce")
        assert (
            page.locator(".agent-setup").evaluate(
                "element => getComputedStyle(element).animationName"
            )
            == "none"
        )
        assert (
            page.locator(".text-link").first.evaluate(
                "element => getComputedStyle(element).transitionDuration"
            )
            == "0s"
        )
        page.emulate_media(reduced_motion="no-preference")
        page.reload()
        assert (
            page.locator(".agent-setup").evaluate(
                "element => getComputedStyle(element).animationIterationCount"
            )
            == "1"
        )
        assert (
            page.locator(".agent-setup").evaluate(
                "element => getComputedStyle(element).animationName"
            )
            == "sample-arrive"
        )
        if screenshots:
            page.set_viewport_size({"width": 1440, "height": 1100})
            page.screenshot(
                path=str(screenshots / "home-dark-desktop.png"),
                full_page=True,
                animations="disabled",
            )
            page.set_viewport_size({"width": 390, "height": 900})
            page.screenshot(
                path=str(screenshots / "home-dark-mobile.png"),
                full_page=True,
                animations="disabled",
            )
        # Mock browsers that block storage: initial OS theme and the control still work.
        blocked = browser.new_context(color_scheme="dark", viewport={"width": 320, "height": 900})
        blocked.route(ORIGIN + "**", serve)
        blocked.add_init_script("""Object.defineProperty(window, 'localStorage', {
          get() { throw new DOMException('Storage is blocked', 'SecurityError'); }
        });""")
        blocked_page = blocked.new_page()
        blocked_page.on("pageerror", lambda error: errors.append(str(error)))
        blocked_page.goto(ORIGIN)
        check_theme(blocked_page, "dark")
        assert blocked_page.evaluate("window.themeAtInit") == {"theme": "dark", "body": False}
        blocked_page.get_by_role("combobox", name="Theme").select_option("light")
        check_theme(blocked_page, "light")
        blocked_page.reload()
        check_theme(blocked_page, "dark")
        blocked_page.get_by_role("combobox", name="Theme").select_option("system")
        blocked_page.emulate_media(color_scheme="light")
        check_theme(blocked_page, "light")
        blocked.close()
        # CSS alone gives a usable reading surface when scripting is unavailable.
        no_script = browser.new_context(java_script_enabled=False, color_scheme="dark")
        no_script.route(ORIGIN + "**", serve)
        no_script_page = no_script.new_page()
        no_script_page.goto(ORIGIN)
        expect(no_script_page.get_by_role("heading", level=1)).to_be_visible()
        expect(no_script_page.locator(".theme-control")).to_be_hidden()
        assert (
            no_script_page.locator("html").evaluate(
                "element => getComputedStyle(element).colorScheme"
            )
            == "dark"
        )
        no_script.close()
        page.keyboard.press("Tab")
        assert page.locator("main#main").count() == 1
        assert not errors, errors
        browser.close()
    print(
        "Browser checks passed: tabs/keyboard, clipboard success/failure, "
        "catalog, docs, 320/390px layout, themes/persistence/system changes, "
        "pre-paint initialization, blocked storage, no-JS fallback, contrast, reduced motion."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "_site")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    check(args.site, args.screenshots)
