"""Exercise the static site without opening a web server or a shared browser tab."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
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
    destination = "light" if expected == "dark" else "dark"
    toggle = page.get_by_role("button", name=f"Switch to {destination} theme", exact=True)
    expect(toggle).to_be_visible()
    expect(toggle.locator(".theme-sun" if expected == "dark" else ".theme-moon")).to_be_visible()
    expect(toggle.locator(".theme-moon" if expected == "dark" else ".theme-sun")).to_be_hidden()
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
          const selectors = ['body', '.muted', '.site-nav a', '.theme-toggle', '.menu-toggle',
            '.primary', '.source-type', '.source-meta',
            '.install-band', '.install-band .small', '.code-block', '.copy-button',
            '.operation summary span', '.docs-sidebar a', 'input', '.copy-feedback',
            '.agent-setup', '.setup-prompt', '.icon-copy', '.clear-search',
            '.prompt-details summary', '.setup-command code'];
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


def set_theme(page, theme):
    if page.locator("html").get_attribute("data-theme") != theme:
        page.get_by_role("button", name=f"Switch to {theme} theme", exact=True).click()
    check_theme(page, theme)


def check_header(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    toggle = page.locator("#site-menu-toggle")
    navigation = page.get_by_role("navigation", name="Main navigation", include_hidden=True)
    if page.viewport_size["width"] <= 700:
        expect(toggle).to_be_visible()
        if toggle.get_attribute("aria-expanded") == "true":
            expect(navigation).to_be_visible()
        else:
            expect(navigation).to_be_hidden()
    else:
        expect(toggle).to_be_hidden()
        expect(navigation).to_be_visible()
    targets = page.locator(
        ".brand:visible, .site-nav a:visible, #site-search-open:visible, "
        ".theme-toggle:visible, .menu-toggle:visible"
    )
    boxes = []
    for target in targets.all():
        expect(target).to_be_visible()
        box = target.bounding_box()
        assert box["width"] >= 44 and box["height"] >= 44, box
        assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"], box
        for previous in boxes:
            assert (
                box["x"] >= previous["x"] + previous["width"] - 1
                or previous["x"] >= box["x"] + box["width"] - 1
                or box["y"] >= previous["y"] + previous["height"] - 1
                or previous["y"] >= box["y"] + box["height"] - 1
            ), (box, previous)
        boxes.append(box)


def check_mobile_menu(page):
    page.set_viewport_size({"width": 390, "height": 900})
    toggle = page.locator("#site-menu-toggle")
    navigation = page.locator("#site-navigation")
    links = navigation.get_by_role("link")
    expect(toggle).to_have_attribute("aria-controls", "site-navigation")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(navigation).to_be_hidden()
    toggle.focus()
    page.keyboard.press("Enter")
    expect(toggle).to_have_accessible_name("Close menu")
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(links).to_have_count(3)
    check_header(page)
    page.keyboard.press("Tab")
    expect(links.first).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(toggle).to_be_focused()
    page.keyboard.press("Tab")
    page.keyboard.press("Escape")
    expect(toggle).to_be_focused()
    expect(toggle).to_have_accessible_name("Open menu")
    expect(navigation).to_be_hidden()
    page.keyboard.press("Space")
    expect(navigation).to_be_visible()
    page.get_by_role("heading", level=1).click()
    expect(navigation).to_be_hidden()
    toggle.click()
    toggle.click()
    expect(navigation).to_be_hidden()
    toggle.click()
    links.last.focus()
    page.keyboard.press("Tab")
    expect(navigation).to_be_hidden()
    expect(page.get_by_role("link", name="Agent setup", exact=True)).to_be_focused()

    # Search remains accessible, and its modal never leaves the menu open behind it.
    for shortcut in (None, "Control+k", "Meta+k"):
        toggle.click()
        if shortcut:
            links.first.focus()
            page.keyboard.press(shortcut)
        else:
            page.get_by_role("button", name="Search guides and API", exact=True).click()
        expect(page.locator("#site-search")).to_be_visible()
        expect(navigation).to_be_hidden()
        page.keyboard.press("Escape")
        expect(page.locator("#site-search")).to_be_hidden()
        if shortcut:
            expect(toggle).to_be_focused()

    # A breakpoint change restores full navigation and leaves focus on a usable control.
    toggle.click()
    page.set_viewport_size({"width": 701, "height": 900})
    expect(toggle).to_be_hidden()
    expect(links.first).to_be_focused()
    check_header(page)
    page.set_viewport_size({"width": 700, "height": 900})
    expect(toggle).to_be_focused()
    expect(navigation).to_be_hidden()
    toggle.click()
    links.nth(1).click()
    expect(page).to_have_url(ORIGIN + "catalog/")
    expect(page.locator("#site-menu-toggle")).to_have_attribute("aria-expanded", "false")
    expect(page.locator("#site-navigation")).to_be_hidden()
    page.goto(ORIGIN)


def check_search_shell(page):
    trigger = page.get_by_role("button", name="Search guides and API", exact=True)
    expect(trigger).to_be_visible()
    expect(trigger.locator("svg")).to_be_visible()
    assert "K" in trigger.inner_text().upper()
    expect(trigger).to_have_attribute("aria-keyshortcuts", "Meta+K Control+K")
    expect(page.locator("#site-search")).to_have_js_property("open", False)
    search_input = page.locator("#site-search-input")
    expect(search_input).to_have_attribute("type", "search")
    expect(page.locator("#site-search-results")).to_have_attribute("role", "listbox")
    expect(page.locator("#site-search-results")).to_have_js_property("tagName", "UL")
    expect(page.locator("#site-search-state")).to_have_attribute("role", "status")
    expect(page.locator("#site-search-close")).to_have_attribute("aria-label", "Close search")
    return trigger, search_input


def check_copy_controls(page):
    for route, name in (
        ("", "Copy installation command"),
        ("docs/getting-started/", "Copy code block"),
        ("catalog/#op-assignments", "Copy assignments example"),
    ):
        page.goto(ORIGIN + route)
        page.evaluate(
            "() => { navigator.clipboard.writeText = async text => { window.copied = text; }; }"
        )
        for control in page.locator("[data-copy]").all():
            assert control.inner_text().strip() == ""
            assert control.get_attribute("aria-label")
        button = page.get_by_role("button", name=name, exact=True).first
        block = button.locator("xpath=..")
        expected = block.locator("code").text_content()
        button.click()
        expect(button.locator(".check-glyph")).to_be_visible()
        expect(button.locator(".copy-glyph")).to_be_hidden()
        assert page.evaluate("window.copied") == expected
        bounds = button.bounding_box()
        assert bounds["width"] >= 44 and bounds["height"] >= 44
        # Announcements remain available to assistive tech without a visible toast.
        status = page.locator("#copy-status")
        expect(status).to_have_attribute("role", "status")
        bounds = status.bounding_box()
        assert bounds["width"] <= 1 and bounds["height"] <= 1
        page.evaluate(
            "() => { navigator.clipboard.writeText = async () => { throw new Error('denied'); }; }"
        )
        button.click()
        expect(block.locator(".copy-feedback")).to_have_text("Text selected. Copy it manually.")
        selection = page.evaluate("window.getSelection().toString()")
        # Rendered selection omits a code fence's final newline, preserving internal whitespace.
        assert selection == expected.rstrip("\n"), (route, selection, expected)
        expect(button.locator(".copy-glyph")).to_be_visible()
        button.click()
        expect(block.locator(".copy-feedback")).to_have_count(1)
        page.evaluate(
            "() => { navigator.clipboard.writeText = async text => { window.copied = text; }; }"
        )
        button.click()
        expect(block.locator(".copy-feedback")).to_have_count(0)
        expect(button.locator(".check-glyph")).to_be_visible()
        assert page.evaluate("window.copied") == expected
    page.goto(ORIGIN)


def open_search(page, *, shortcut=None):
    trigger = page.get_by_role("button", name="Search guides and API", exact=True)
    if shortcut:
        page.keyboard.press(shortcut)
    else:
        trigger.click()
    expect(page.locator("#site-search")).to_be_visible()
    search_input = page.get_by_role("combobox", name="Search guides and API", exact=True)
    expect(search_input).to_be_focused()
    return search_input


def search_options(page):
    return page.locator('#site-search-results a[role="option"]')


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
        search_index_requests = []
        page.on(
            "request",
            lambda request: (
                search_index_requests.append(page.url)
                if urlsplit(request.url).path.endswith("/search-index.json")
                else None
            ),
        )
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(ORIGIN)
        expect(page.get_by_role("heading", level=1)).to_have_text("Your agent,meet Canvas")
        theme = page.locator("#theme-toggle")
        expect(page.get_by_role("combobox")).to_have_count(0)
        check_theme(page, "light")
        page.emulate_media(color_scheme="dark")
        check_theme(page, "dark")
        theme.click()
        page.emulate_media(color_scheme="light")
        page.emulate_media(color_scheme="dark")
        check_theme(page, "light")
        theme.click()
        page.goto(ORIGIN + "catalog/")
        check_theme(page, "dark")
        page.goto(ORIGIN + "docs/getting-started/")
        check_theme(page, "dark")
        page.goto(ORIGIN)
        assert page.evaluate("window.themeAtInit") == {"theme": "dark", "body": False}
        # Both native button keys work, with visible focus and an accurate action name.
        theme.focus()
        theme.press("Space")
        check_theme(page, "light")
        assert theme.evaluate("element => getComputedStyle(element).outlineStyle") == "solid"
        theme.press("Enter")
        check_theme(page, "dark")
        # Real storage events keep another open tab's icon and action in sync.
        other = context.new_page()
        other.goto(ORIGIN + "catalog/")
        theme.click()
        check_theme(other, "light")
        other.get_by_role("button", name="Switch to dark theme").click()
        check_theme(page, "dark")
        # Clearing the saved choice restores OS-following behavior in the other tab.
        other.evaluate("localStorage.removeItem('folava-theme')")
        page.wait_for_function("window.folavaTheme.getPreference() === 'system'")
        page.emulate_media(color_scheme="light")
        check_theme(page, "light")
        other.close()
        page.goto(ORIGIN)
        check_theme(page, "light")
        check_copy_controls(page)
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
        expect(page.locator("#copy-status")).to_have_text("Setup prompt copied.")
        expect(page.get_by_role("button", name="Copy setup prompt")).to_have_accessible_name(
            "Copy setup prompt"
        )
        expect(page.locator("#setup-prompt")).to_be_hidden()
        prompt = page.evaluate("window.copied")
        assert prompt == page.locator("#setup-prompt").text_content()
        assert prompt != page.locator(".setup-command code").inner_text()
        assert "https://liltaket.github.io/folava-mcp/install.md" in prompt
        assert "demo" in prompt and "credentials outside" in prompt
        expect(page.get_by_role("link", name="Setup guide", exact=True)).to_have_attribute(
            "href", "/folava-mcp/install.md"
        )
        page.get_by_role("button", name="Copy installation command").click()
        expect(page.locator("#copy-status")).to_have_text("Command copied.")
        check_theme(page, "light")
        theme.click()
        check_theme(page, "dark")
        theme.click()
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
        expect(page.locator("#copy-status")).to_contain_text("copy it manually")
        expect(page.locator(".agent-setup .copy-feedback")).to_have_text(
            "Text selected. Copy it manually."
        )
        expect(page.locator(".prompt-details")).to_have_attribute("open", "")
        expect(page.locator("#setup-prompt")).to_be_visible()
        assert page.evaluate("window.getSelection().toString()") == prompt
        page.get_by_role("button", name="Copy demo connection command").click()
        expect(page.locator("#copy-status")).to_contain_text("copy it manually")
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
        for width in (320, 360, 390, 430, 700, 701, 768, 1024, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            check_header(page)
            assert page.locator(".setup-command code").evaluate(
                "el => el.getBoundingClientRect().height <= "
                "parseFloat(getComputedStyle(el).lineHeight) + 1"
            )
            artwork = page.locator(".hero-annotation").bounding_box()
            assert artwork["x"] >= 0 and artwork["x"] + artwork["width"] <= width + 1
            expect(theme).to_be_visible()
            theme.click()
            check_theme(page, "dark")
            theme.click()
        if screenshots:
            page.set_viewport_size({"width": 390, "height": 900})
            page.reload()
            page.screenshot(
                path=str(screenshots / "home-mobile.png"), full_page=True, animations="disabled"
            )
        check_mobile_menu(page)

        # Search from the homepage, then follow a guide result into the docs.
        page.set_viewport_size({"width": 1440, "height": 900})
        search_index_requests.clear()
        trigger, _ = check_search_shell(page)
        search_input = open_search(page)
        page.keyboard.press("Tab")
        expect(page.get_by_role("button", name="Close search", exact=True)).to_be_focused()
        page.keyboard.press("Tab")
        expect(search_input).to_be_focused()
        page.keyboard.press("Escape")
        expect(page.locator("#site-search")).to_be_hidden()
        expect(trigger).to_be_focused()
        search_input = open_search(page, shortcut="Control+k")
        home_url = page.url
        stored_state = page.evaluate(
            """() => ({local: Object.entries(localStorage).sort(),
                       session: Object.entries(sessionStorage).sort()})"""
        )
        search_input.fill("Getting started")
        guide_result = page.locator(
            '#site-search-results a[role="option"][href*="docs/getting-started/"]'
        )
        expect(guide_result).to_be_visible()
        expect(guide_result).to_have_class(re.compile(r"\bsearch-result\b"))
        expect(guide_result.locator(".search-result-kind")).to_have_text("Guide")
        expect(guide_result.locator(".search-result-context")).to_be_visible()
        assert page.url == home_url
        assert (
            page.evaluate(
                """() => ({local: Object.entries(localStorage).sort(),
                       session: Object.entries(sessionStorage).sort()})"""
            )
            == stored_state
        )
        guide_result.click()
        expect(page.get_by_role("heading", name="Getting started", exact=True)).to_be_visible()
        assert sum(urlsplit(url).path == "/folava-mcp/" for url in search_index_requests) == 1

        # Ctrl+K works from a guide, and exact operation selection survives arrow wrapping.
        search_input = open_search(page, shortcut="Control+k")
        search_input.fill("profile")
        options = search_options(page)
        expect(options.first).to_be_visible()
        assert options.count() > 1
        page.keyboard.press("ArrowUp")
        expect(options.last).to_have_attribute("aria-selected", "true")
        page.keyboard.press("ArrowDown")
        selected = page.locator('#site-search-results a[role="option"][aria-selected="true"]')
        expect(selected).to_have_count(1)
        selected_url = urlsplit(selected.get_attribute("href"))
        assert selected_url.path.endswith("/catalog/")
        assert selected_url.fragment == "op-profile"
        expect(selected.locator(".search-result-kind")).to_have_text("API")
        page.keyboard.press("Enter")
        expect(page.locator("#op-profile")).to_have_attribute("open", "")
        assert page.url.endswith("#op-profile")
        assert (
            sum(
                urlsplit(url).path == "/folava-mcp/docs/getting-started/"
                for url in search_index_requests
            )
            == 1
        )

        check_theme(page, "light")
        operations = page.locator("[data-operation]")
        total = operations.count()
        assert total == len(json.loads((site / "operations.json").read_text())) > 0
        groups = page.locator("[data-operation-group]")
        group_total = groups.count()
        assert group_total > 1
        search = page.get_by_role("searchbox", name="Filter operations")
        search.fill("submission")
        visible_operation_count = page.locator("[data-operation]:visible").count()
        assert 1 < visible_operation_count < total
        expect(page.locator("#operation-count")).to_have_text(
            f"{visible_operation_count} of {total} operations"
        )
        visible_groups = page.locator("[data-operation-group]:visible")
        assert 0 < visible_groups.count() < group_total
        for group in visible_groups.all():
            matching_operations = group.locator("[data-operation]:visible").count()
            assert matching_operations > 0
            key = group.get_attribute("data-operation-group")
            expect(page.locator(f'[data-group-count="{key}"]').first).to_have_text(
                str(matching_operations)
            )
        assert all(
            group.locator("[data-operation]:visible").count() == 0
            for group in page.locator("[data-operation-group][hidden]").all()
        )
        first_visible_operation = page.locator("[data-operation]:visible").first
        first_visible_operation.locator("summary").click()
        expect(first_visible_operation).to_have_attribute("open", "")
        expect(first_visible_operation).to_contain_text('"operation"')
        check_theme(page, "light")
        theme.click()
        check_theme(page, "dark")
        theme.click()
        search.fill("an-operation-that-does-not-exist")
        expect(page.locator("#empty-search")).to_be_visible()
        expect(page.locator("#operation-count")).to_have_text(f"0 of {total} operations")
        page.get_by_role("button", name="Clear search", exact=True).click()
        expect(search).to_be_focused()
        expect(page.locator("#empty-search")).to_be_hidden()
        expect(page.locator("#operation-count")).to_have_text(f"{total} of {total} operations")
        search.fill("submission")
        search.press("Escape")
        expect(search).to_have_value("")
        assert page.locator("[data-operation]:visible").count() == total
        search.fill("submission")
        # The document shortcut is handled even when the local filter owns focus.
        search.press("Meta+k")
        expect(page.locator("#site-search")).to_be_visible()
        search_input = page.get_by_role("combobox", name="Search guides and API", exact=True)
        expect(search_input).to_be_focused()
        search_input.fill("assignments")
        assignment_result = page.locator(
            '#site-search-results a[role="option"][href*="#op-assignments"]'
        )
        expect(assignment_result).to_be_visible()
        options = search_options(page)
        assert options.count() > 1
        page.keyboard.press("ArrowUp")
        expect(options.last).to_have_attribute("aria-selected", "true")
        page.keyboard.press("ArrowDown")
        selected = page.locator('#site-search-results a[role="option"][aria-selected="true"]')
        expect(selected).to_have_count(1)
        assert urlsplit(selected.get_attribute("href")).fragment == "op-assignments"
        page.keyboard.press("Enter")
        assert page.url.endswith("#op-assignments")
        expect(page.locator("#op-assignments")).to_have_attribute("open", "")
        expect(page.locator("#op-assignments")).to_be_in_viewport()
        expect(search).to_have_value("")
        assert page.locator("[data-operation]:visible").count() == total
        assert (
            sum(urlsplit(url).path == "/folava-mcp/catalog/" for url in search_index_requests) == 1
        )

        # Queries stay in the dialog, and an empty search gives an accessible status.
        page.get_by_role("button", name="Search guides and API", exact=True).click()
        search_input = page.get_by_role("combobox", name="Search guides and API", exact=True)
        page_url = page.url
        stored_state = page.evaluate(
            """() => ({local: Object.entries(localStorage).sort(),
                       session: Object.entries(sessionStorage).sort()})"""
        )
        search_input.fill("no-such-guide-or-operation-zzq")
        expect(search_options(page)).to_have_count(0)
        expect(page.locator("#site-search-state")).to_contain_text("No results")
        assert page.url == page_url
        assert (
            page.evaluate(
                """() => ({local: Object.entries(localStorage).sort(),
                       session: Object.entries(sessionStorage).sort()})"""
            )
            == stored_state
        )
        page.get_by_role("button", name="Close search", exact=True).click()
        expect(page.locator("#site-search")).to_be_hidden()
        for width in (320, 390, 768, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            check_header(page)
        page.goto(ORIGIN + "docs/getting-started/")
        check_theme(page, "light")
        expect(page.get_by_role("heading", name="Getting started", exact=True)).to_be_visible()
        expect(page.locator("#reference-navigation")).to_have_attribute("open", "")
        expect(page.locator("#page-navigation")).to_have_attribute("open", "")
        page.set_viewport_size({"width": 390, "height": 900})
        expect(page.locator("#reference-navigation")).not_to_have_attribute("open", "")
        expect(page.locator("#page-navigation")).not_to_have_attribute("open", "")
        expect(page.locator("#reference-navigation summary")).to_have_text("Browse guides")
        page.locator("#reference-navigation summary").click()
        expect(page.locator("#reference-navigation")).to_have_attribute("open", "")
        page.get_by_role("navigation", name="Documentation sections").get_by_role(
            "link", name="Authentication", exact=True
        ).click()
        expect(page.get_by_role("heading", name="Connect Canvas", exact=True)).to_be_visible()
        page.get_by_role("button", name="Open menu", exact=True).click()
        expect(
            page.get_by_role("navigation", name="Main navigation").get_by_role(
                "link", name="Guide", exact=True
            )
        ).to_have_attribute("aria-current", "location")
        page.get_by_role("button", name="Close menu", exact=True).click()
        for width in (1440, 1024, 900, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 900})
            reference_navigation = page.locator("#reference-navigation")
            page_navigation = page.locator("#page-navigation")
            if width > 900:
                expect(reference_navigation).to_have_attribute("open", "")
            else:
                expect(reference_navigation).not_to_have_attribute("open", "")
            if width > 1200:
                expect(page_navigation).to_have_attribute("open", "")
            else:
                expect(page_navigation).not_to_have_attribute("open", "")
            set_theme(page, "dark")
            check_header(page)
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(ORIGIN + "docs/getting-started/")
        page.get_by_role("navigation", name="On this page", exact=True).get_by_role(
            "link", name="Codex", exact=True
        ).click()
        assert page.url.endswith("#codex")
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
            theme.focus()
            page.keyboard.press("Space")
            check_theme(page, "light")
            page.keyboard.press("Enter")
            check_theme(page, "dark")
        page.goto(ORIGIN)
        page.emulate_media(reduced_motion="reduce")
        for selector in (".hero-ink", ".hero-pencil"):
            assert (
                page.locator(selector).evaluate(
                    "element => getComputedStyle(element).animationName"
                )
                == "none"
            )
        assert (
            page.locator(".hero-ink").evaluate(
                "element => getComputedStyle(element).strokeDashoffset"
            )
            == "0px"
        )
        expect(page.locator(".hero-annotation")).to_have_attribute("aria-hidden", "true")
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
        for selector in (".hero-ink", ".hero-pencil"):
            assert (
                page.locator(selector).evaluate(
                    "element => getComputedStyle(element).animationIterationCount"
                )
                == "1"
            )
            assert (
                page.locator(selector).evaluate(
                    "element => getComputedStyle(element).animationDuration"
                )
                == "3.8s"
            )
        stroke = page.locator(".hero-annotation").evaluate(
            """element => {
              const animations = element.getAnimations({subtree: true});
              const ink = element.querySelector('.hero-ink');
              const pencil = element.querySelector('.hero-pencil');
              animations.forEach(animation => { animation.currentTime = 0; });
              const start = parseFloat(getComputedStyle(ink).strokeDashoffset);
              animations.forEach(animation => { animation.currentTime = 1900; });
              const middle = parseFloat(getComputedStyle(ink).strokeDashoffset);
              const moving = new DOMMatrix(getComputedStyle(pencil).transform);
              const movingOpacity = getComputedStyle(pencil).opacity;
              animations.forEach(animation => { animation.currentTime = 3800; });
              const resting = new DOMMatrix(getComputedStyle(pencil).transform);
              return {start, middle, movingX: moving.e, movingOpacity,
                end: parseFloat(getComputedStyle(ink).strokeDashoffset),
                restingX: resting.e, restingY: resting.f,
                restingOpacity: getComputedStyle(pencil).opacity};
            }"""
        )
        assert stroke["start"] == 100 and 0 < stroke["middle"] < 100 and stroke["end"] == 0
        assert 10 < stroke["movingX"] < stroke["restingX"] == 282
        assert stroke["movingOpacity"] == "1"
        assert (
            int(
                page.locator(".hero-annotation").evaluate(
                    "element => getComputedStyle(element).zIndex"
                )
            )
            > 0
        )
        assert stroke["restingY"] == 58 and stroke["restingOpacity"] == "0"
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
        blocked = browser.new_context(
            color_scheme="dark",
            viewport={"width": 320, "height": 900},
            is_mobile=True,
            has_touch=True,
        )
        blocked.route(ORIGIN + "**", serve)
        blocked.add_init_script("""Object.defineProperty(window, 'localStorage', {
          get() { throw new DOMException('Storage is blocked', 'SecurityError'); }
        });""")
        blocked_page = blocked.new_page()
        blocked_page.on("pageerror", lambda error: errors.append(str(error)))
        blocked_page.goto(ORIGIN)
        check_theme(blocked_page, "dark")
        assert blocked_page.evaluate("window.themeAtInit") == {"theme": "dark", "body": False}
        blocked_page.get_by_role("button", name="Switch to light theme").tap()
        check_theme(blocked_page, "light")
        blocked_page.reload()
        check_theme(blocked_page, "dark")
        blocked_page.emulate_media(color_scheme="light")
        check_theme(blocked_page, "light")
        blocked_page.get_by_role("button", name="Open menu", exact=True).tap()
        expect(blocked_page.locator("#site-navigation")).to_be_visible()
        check_header(blocked_page)
        blocked_page.get_by_role("navigation", name="Main navigation").get_by_role(
            "link", name="Guide", exact=True
        ).tap()
        expect(
            blocked_page.get_by_role("heading", name="Getting started", exact=True)
        ).to_be_visible()
        expect(blocked_page.locator("#site-navigation")).to_be_hidden()
        blocked.close()
        # Hold the first index fetch to observe loading, then mock a failure and retry.
        retry_context = browser.new_context()
        retry_context.route(ORIGIN + "**", serve)
        retry_context.add_init_script(
            """(() => {
              const nativeFetch = window.fetch.bind(window);
              let held = false;
              window.fetch = (input, init) => {
                if (!held && String(input).includes('search-index.json')) {
                  held = true;
                  return new Promise((resolve, reject) => {
                    window.releaseSearchIndex = () =>
                      nativeFetch(input, init).then(resolve, reject);
                  });
                }
                return nativeFetch(input, init);
              };
            })();"""
        )
        retry_attempts = {"index": 0}

        def fail_first_search_index(route):
            retry_attempts["index"] += 1
            if retry_attempts["index"] == 1:
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body='{"error":"temporary outage"}',
                )
            else:
                route.fulfill(
                    content_type="application/json",
                    body=(site / "search-index.json").read_text(encoding="utf-8"),
                )

        retry_context.route(re.compile(r"/search-index\.json(?:\?|$)"), fail_first_search_index)
        retry_page = retry_context.new_page()
        retry_page.on("pageerror", lambda error: errors.append(str(error)))
        retry_page.goto(ORIGIN)
        check_search_shell(retry_page)
        open_search(retry_page)
        expect(retry_page.locator("#site-search-state")).to_contain_text("Loading")
        retry_page.evaluate("window.releaseSearchIndex()")
        expect(retry_page.locator("#site-search-state")).to_contain_text("could not load")
        retry_button = retry_page.get_by_role("button", name="Retry search", exact=True)
        expect(retry_button).to_be_visible()
        retry_button.click()
        expect(search_options(retry_page).first).to_be_visible()
        assert retry_attempts["index"] == 2
        retry_context.close()
        # CSS alone gives a usable reading surface when scripting is unavailable.
        no_script = browser.new_context(java_script_enabled=False, color_scheme="dark")
        no_script.route(ORIGIN + "**", serve)
        no_script_page = no_script.new_page()
        no_script_page.set_viewport_size({"width": 320, "height": 900})
        no_script_page.goto(ORIGIN)
        expect(no_script_page.get_by_role("heading", level=1)).to_be_visible()
        expect(no_script_page.locator(".theme-toggle")).to_be_hidden()
        expect(no_script_page.locator("#site-search-open")).to_be_hidden()
        expect(no_script_page.locator("#site-menu-toggle")).to_be_hidden()
        expect(no_script_page.locator("#site-navigation")).to_be_visible()
        no_script_page.get_by_text("View full prompt", exact=True).click()
        expect(no_script_page.locator("#setup-prompt")).to_be_visible()
        assert (
            no_script_page.locator("html").evaluate(
                "element => getComputedStyle(element).colorScheme"
            )
            == "dark"
        )
        no_script_page.goto(ORIGIN + "catalog/")
        expect(no_script_page.get_by_role("searchbox", name="Filter operations")).to_be_hidden()
        expect(no_script_page.get_by_text("All operations are shown.", exact=False)).to_be_visible()
        no_script_page.locator("[data-operation]").first.locator("summary").click()
        expect(no_script_page.locator("[data-operation][open]")).to_be_visible()
        no_script.close()
        page.keyboard.press("Tab")
        assert page.locator("main#main").count() == 1
        assert not errors, errors
        browser.close()
    print(
        "Browser checks passed: tabs/keyboard, global search/load/retry, "
        "clipboard success/failure, catalog/groups, docs/navigation, "
        "320–1440px layout/touch targets, hamburger/keyboard/touch/resize, "
        "sun/moon toggle/keyboard/touch, "
        "theme persistence/system changes/cross-tab sync, "
        "pre-paint initialization, blocked storage, no-JS fallback, contrast, reduced motion."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=ROOT / "_site")
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    check(args.site, args.screenshots)
