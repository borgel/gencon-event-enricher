"""End-to-end webpage smoke test using Playwright + a tiny on-disk events.json."""
import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

TINY_BLOB = {
    "groups": [
        {
            "key": "BGM-wingspan-asia-tournament-abc",
            "title": "Wingspan: Asia Tournament",
            "event_type": "BGM",
            "event_type_label": "BGM - Board Game",
            "game_system": "Wingspan: Asia",
            "short_description": "Compete!",
            "long_description": "Long Wingspan description.",
            "tournament": True, "min_players": 1, "max_players": 4,
            "age_required": "Teen (13+)", "experience_required": "Some",
            "duration_minutes": 240, "cost": 8.0,
            "bgg": {
                "id": 266192, "name": "Wingspan: Asia", "year_published": 2022,
                "rank": 142, "bayesaverage": 7.84, "average": 8.05,
                "users_rated": 14238, "is_expansion": True,
                "category_ranks": {"strategygames": 44}, "match_source": "exact",
            },
            "sessions": [{
                "gencon_id": "BGM26ND000001",
                "start": "2026-07-30T09:00:00", "end": "2026-07-30T13:00:00",
                "duration_minutes": 240, "location": "ICC", "room": "Hall A",
                "table": "27", "gm": "Jane Doe", "tickets_available": 8,
                "round_number": 1, "total_rounds": 3, "cost_override": 8.0,
            }],
        },
        {
            "key": "SEM-cosplay-101-abc",
            "title": "Cosplay 101", "event_type": "SEM",
            "event_type_label": "SEM - Seminar", "game_system": "",
            "short_description": "Foam.", "long_description": "Foam armor.",
            "tournament": False, "min_players": 1, "max_players": 50,
            "age_required": "Everyone (6+)", "experience_required": "None",
            "duration_minutes": 60, "cost": 2.0,
            "sessions": [{
                "gencon_id": "SEM26ND000005",
                "start": "2026-07-31T10:00:00", "end": "2026-07-31T11:00:00",
                "duration_minutes": 60, "location": "ICC", "room": "Room 200",
                "table": "", "gm": "Cos Player", "tickets_available": 12,
                "round_number": 1, "total_rounds": 1, "cost_override": 2.0,
            }],
        },
    ],
    "meta": {
        "generated_at": "2026-05-04T00:00:00Z",
        "gencon_source": "x.xlsx", "bgg_source": "y.csv",
        "stats": {"groups": 2, "sessions": 2, "matched": 1, "unmatched": 1},
    },
}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    docs_root = ROOT / "docs"
    data_dir = docs_root / "data"
    data_dir.mkdir(exist_ok=True)
    events_path = data_dir / "events.json"
    backup = events_path.read_text() if events_path.exists() else None
    events_path.write_text(json.dumps(TINY_BLOB))

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(docs_root), **k)
        def log_message(self, *_): pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        httpd.shutdown()
        if backup is not None:
            events_path.write_text(backup)


def test_page_loads_and_lists_groups(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        rows = page.query_selector_all(".row")
        assert len(rows) >= 2

        # Type filter to BGM only -> 1 row
        page.click('span.chip[data-val="BGM"]')
        page.wait_for_function("document.querySelectorAll('.row').length === 1")

        # Clicking a row opens the detail panel
        page.click(".row")
        panel = page.query_selector("#detail-panel")
        assert "hidden" not in panel.get_attribute("class").split()
        assert "Wingspan: Asia" in page.inner_text("#detail-panel")

        # Session row's GenCon link uses the direct /events/<num> URL pattern,
        # not the legacy /events?search=<id> form.
        href = page.eval_on_selector(
            "#detail-panel table.sessions a[href*='gencon.com/events']",
            "e => e.href",
        )
        # Fixture's gencon_id is BGM26ND000001 → trailing digits 000001
        assert href == "https://www.gencon.com/events/000001"

        # Prominent sign-up button row near the top of the panel: one button
        # per session, each labeled with day/time and pointing at the same
        # direct event URL.
        btns = page.eval_on_selector_all(
            "#detail-panel .signup-row .signup-btn",
            "els => els.map(e => ({text: e.textContent.trim(), href: e.href}))",
        )
        assert len(btns) == 1
        assert "Thu" in btns[0]["text"]  # fixture session starts 2026-07-30 (Thu)
        assert btns[0]["href"] == "https://www.gencon.com/events/000001"
        browser.close()


def test_results_toolbar_renders_with_sort_controls(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#results-toolbar")
        assert page.query_selector("#results-toolbar #s-key") is not None
        assert page.query_selector("#results-toolbar #s-dir") is not None
        # Sort key options
        keys = page.eval_on_selector_all(
            "#s-key option", "els => els.map(e => e.value)"
        )
        assert keys == ["start", "type", "bgg"]
        browser.close()


def test_sort_changes_row_order(server):
    """Switching to BGG-desc puts the BGG-rated row first."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        page.select_option("#s-key", "bgg")
        # Direction button defaults to bgg's default (desc), so no toggle needed.
        page.wait_for_function("document.querySelectorAll('.row')[0].textContent.includes('Wingspan')")
        first_text = page.eval_on_selector(".row", "e => e.textContent")
        assert "Wingspan" in first_text
        browser.close()


def test_view_table_scroll_to_key_exists(server):
    """Construct a tableView via the page and verify scrollToKey is callable."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        result = page.evaluate("""
        async () => {
          const mod = await import('/app/view-table.js');
          const container = document.createElement('div');
          container.style.height = '100px';
          document.body.appendChild(container);
          const v = mod.createTableView({ container, rowHeightPx: 30, onRowClick: () => {} });
          v.setRows([{ key: 'a', title: 'a', sessions: [{}] }, { key: 'b', title: 'b', sessions: [{}] }]);
          return typeof v.scrollToKey === 'function';
        }
        """)
        assert result is True
        browser.close()


def test_popstate_resyncs_toolbar(server):
    """Navigating back/forward must update the toolbar to reflect the URL hash."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#s-key")
        # Change sort to bgg -> toolbar and hash update via the select handler
        page.select_option("#s-key", "bgg")
        page.wait_for_function("window.location.hash.includes('sort=bgg')")
        # Simulate popstate back to default (no sort params in hash) by
        # resetting the hash and firing popstate — mirrors what the browser
        # does when the user hits Back after a pushState-based navigation.
        page.evaluate("history.replaceState(null, '', '#'); window.dispatchEvent(new PopStateEvent('popstate', {state: null}))")
        page.wait_for_function("document.querySelector('#s-key').value === 'start'")
        # Direction button label must also re-render to the start-asc default
        dir_text = page.eval_on_selector("#s-dir", "e => e.textContent")
        assert "Earliest" in dir_text
        browser.close()


def test_bggmatch_chip_group_renders(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#f-bggmatch")
        chips = page.eval_on_selector_all(
            "#f-bggmatch .chip", "els => els.map(e => e.dataset.bgg)"
        )
        assert chips == ["either", "yes", "no"]
        # Default is 'either' -> first chip active
        active = page.eval_on_selector("#f-bggmatch .chip.active", "e => e.dataset.bgg")
        assert active == "either"
        # Old checkbox is gone
        assert page.query_selector("#f-bggonly") is None
        browser.close()


def test_bggmatch_no_filters_to_unmatched(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Tickets-only is on by default, so only the SEM unmatched row + BGM
        # matched row are present in the fixture (both have tix > 0).
        page.click('#f-bggmatch .chip[data-bgg="no"]')
        page.wait_for_function("document.querySelectorAll('.row').length === 1")
        text = page.eval_on_selector(".row", "e => e.textContent")
        assert "Cosplay" in text  # The unmatched fixture row.
        browser.close()


def test_duration_range_inputs_render(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#f-durmin")
        page.wait_for_selector("#f-durmax")
        # Old chip group is gone
        assert page.query_selector("#f-durations") is None
        # Slider attributes
        attrs = page.eval_on_selector(
            "#f-durmin",
            "e => ({min: e.min, max: e.max, step: e.step, val: e.value})",
        )
        assert attrs["min"] == "0" and attrs["max"] == "12" and attrs["step"] == "0.5"
        browser.close()


def test_type_chip_shows_label_and_abbrev(server):
    """Type chips display 'Full Label (CODE)', not just the code."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector('#f-types .chip[data-val="BGM"]')
        text = page.eval_on_selector(
            '#f-types .chip[data-val="BGM"]', "e => e.textContent.trim()"
        )
        # Fixture's event_type_label for BGM is "BGM - Board Game"; we strip the
        # "CODE - " prefix to derive the human label.
        assert "Board Game" in text
        assert "(BGM)" in text
        # data-val (used by the predicate) remains the bare code
        assert page.eval_on_selector(
            '#f-types .chip[data-val="BGM"]', "e => e.dataset.val"
        ) == "BGM"
        browser.close()


def test_lucky_button_opens_detail_panel(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#s-lucky")
        # Sanity: panel is hidden initially
        panel_class = page.eval_on_selector("#detail-panel", "e => e.className")
        assert "hidden" in panel_class
        # Click lucky -> panel opens with one of the fixture groups
        page.click("#s-lucky")
        page.wait_for_function(
            "!document.querySelector('#detail-panel').classList.contains('hidden')"
        )
        text = page.inner_text("#detail-panel")
        assert "Wingspan" in text or "Cosplay" in text
        browser.close()


def test_lucky_button_disabled_when_empty(server):
    """Filter to nothing, lucky button should be disabled."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Toggling Saved-only with nothing saved drops every row.
        page.click("#s-saved")
        page.wait_for_function("document.querySelectorAll('.row').length === 0")
        disabled = page.eval_on_selector("#s-lucky", "e => e.disabled")
        assert disabled is True
        browser.close()


def test_saved_toolbar_button_count_and_active_state(server):
    """The toolbar saved button shows a live count and toggles the filter."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Fresh context — clean localStorage.
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#s-saved")
        # Initially: count 0, not active.
        text = page.eval_on_selector("#s-saved", "e => e.textContent")
        assert "(0)" in text
        active = page.eval_on_selector("#s-saved", "e => e.classList.contains('active')")
        assert active is False
        # Save an event from the detail panel.
        page.click(".row")
        page.click("#detail-panel .save-toggle")
        # Count updates live.
        page.wait_for_function(
            "document.querySelector('#s-saved').textContent.includes('(1)')"
        )
        # Click Saved button -> active, filter applies.
        page.click("#s-saved")
        page.wait_for_function(
            "document.querySelector('#s-saved').classList.contains('active')"
        )
        # The saved row remains visible; the unsaved row is filtered out.
        page.wait_for_function("document.querySelectorAll('.row').length === 1")
        # Click again -> inactive, all rows back.
        page.click("#s-saved")
        page.wait_for_function("document.querySelectorAll('.row').length === 2")
        # Old rail checkbox is gone.
        assert page.query_selector("#f-saved") is None
        ctx.close()
        browser.close()


def test_purchased_toggle_persists(server):
    """Tickets purchased state survives a page reload (localStorage-backed)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Open detail, tick "Tickets purchased".
        page.click(".row")
        page.click("#detail-panel .purchased-cb")
        # Reload, reopen detail for the same row.
        page.reload(wait_until="networkidle")
        page.wait_for_selector(".row")
        page.click(".row")
        checked = page.eval_on_selector("#detail-panel .purchased-cb", "e => e.checked")
        assert checked is True
        ctx.close()
        browser.close()


def test_row_marks_show_saved_and_purchased(server):
    """Rows display ★ for saved and 🎟️ for purchased events."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Initially: no marks anywhere.
        marks_text = page.eval_on_selector_all(
            ".row .marks", "els => els.map(e => e.textContent).join('|')"
        )
        assert marks_text == "|"  # 2 rows in fixture, both empty
        # Save the first row (Wingspan), tick its purchased.
        page.click(".row")
        page.click("#detail-panel .save-toggle")
        page.click("#detail-panel .purchased-cb")
        # Row now shows both marks.
        page.wait_for_function(
            "[...document.querySelectorAll('.row .marks')].some(e => e.textContent.includes('★'))"
        )
        first_marks = page.eval_on_selector(".row:first-child .marks", "e => e.textContent")
        assert "★" in first_marks
        assert "🎟" in first_marks  # match either 🎟️ (with VS-16) or 🎟 alone
        ctx.close()
        browser.close()


def test_purchased_orthogonal_to_saved(server):
    """Purchased and Saved are independent flags (Q1=A)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Tick Purchased; do NOT tick Saved.
        page.click(".row")
        page.click("#detail-panel .purchased-cb")
        # The Save toggle must remain in its initial (unsaved) state.
        save_label = page.eval_on_selector(
            "#detail-panel .save-toggle", "e => e.textContent.trim()"
        )
        assert save_label.startswith("☆")  # ☆ Save (not ★ Saved)
        # And the toolbar saved-count is still 0.
        text = page.eval_on_selector("#s-saved", "e => e.textContent")
        assert "(0)" in text
        ctx.close()
        browser.close()


def test_detail_open_does_not_shift_toolbar(server):
    """Opening the detail panel must not push the results toolbar inward.

    Layout regression guard: the detail panel is nested inside #results, so
    only #results-list shares horizontal space with it; the toolbar (and the
    Lucky button) stay put.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_viewport_size({"width": 1400, "height": 800})
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")

        before = page.eval_on_selector(
            "#results-toolbar",
            "e => { const r = e.getBoundingClientRect(); return {x: r.x, w: r.width}; }",
        )
        # Open detail panel
        page.click(".row")
        page.wait_for_function(
            "!document.querySelector('#detail-panel').classList.contains('hidden')"
        )
        after = page.eval_on_selector(
            "#results-toolbar",
            "e => { const r = e.getBoundingClientRect(); return {x: r.x, w: r.width}; }",
        )
        assert before == after, f"Toolbar shifted: {before} -> {after}"
        # And the detail panel must be a descendant of #results, not a sibling
        is_nested = page.evaluate(
            "() => document.querySelector('#results').contains(document.querySelector('#detail-panel'))"
        )
        assert is_nested is True
        browser.close()


def test_popstate_repopulates_type_chips(server):
    """Regression: type/location chip groups must survive Back/Forward navigation.

    Pre-existing bug (I-2 from prior review): renderFilterRail wipes #f-types
    on popstate, but populateMultiselect wasn't re-called, leaving an empty
    div until hard reload. The renderAllFilterUI helper fixes this.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector('#f-types .chip[data-val="BGM"]')
        # Toggle a type to push hash state.
        page.click('#f-types .chip[data-val="BGM"]')
        page.wait_for_function("window.location.hash.includes('types=BGM')")
        # Simulate Back navigation: clear hash, fire popstate.
        page.evaluate("""
        () => {
          history.replaceState(null, '', '#');
          window.dispatchEvent(new PopStateEvent('popstate'));
        }
        """)
        # After popstate, the type chips must still be present (not just an
        # empty container).
        page.wait_for_function(
            "document.querySelectorAll('#f-types .chip').length > 0"
        )
        # And no chip should be active (since hash is empty).
        active = page.eval_on_selector_all(
            "#f-types .chip.active", "els => els.length"
        )
        assert active == 0
        browser.close()


def test_clear_filters_resets_filters_preserves_sort(server):
    """Clear button: reset filters, untick ticketsOnly, preserve sort."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Set non-default state: pick a type, switch sort to BGG-desc.
        page.click('#f-types .chip[data-val="BGM"]')
        page.wait_for_function("document.querySelectorAll('.row').length === 1")
        page.select_option("#s-key", "bgg")
        page.wait_for_function("window.location.hash.includes('sort=bgg')")
        # Sanity: hash currently has both filter and sort fragments.
        h = page.evaluate("() => window.location.hash")
        assert "types=BGM" in h and "sort=bgg" in h

        # Click clear.
        page.click("#f-clear")

        # Both fixture rows visible again.
        page.wait_for_function("document.querySelectorAll('.row').length === 2")
        # ticketsOnly is now unchecked (Q1=C — clear flips it off, even though
        # it defaults to true on first load).
        tix = page.eval_on_selector("#f-tix", "e => e.checked")
        assert tix is False
        # Type chip no longer active.
        active_types = page.eval_on_selector_all(
            "#f-types .chip.active", "els => els.length"
        )
        assert active_types == 0
        # Hash no longer carries filter keys, but sort is preserved.
        h2 = page.evaluate("() => window.location.hash")
        assert "types=" not in h2
        assert "tix=0" in h2  # because ticketsOnly is now false
        assert "sort=bgg" in h2  # sort preserved
        browser.close()
