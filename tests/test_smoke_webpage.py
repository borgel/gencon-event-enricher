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

        # Type filter to BGM only -> 1 row.
        # Strict-types semantics: defaults to all selected, so we Clear all
        # first, then click BGM to narrow to BGM only.
        page.click("#f-types-none")
        page.click('span.chip[data-val="BGM"]')
        page.wait_for_function("document.querySelectorAll('.row').length === 1")

        # Clicking a row opens the detail panel
        page.click(".row")
        panel = page.query_selector("#detail-panel")
        assert "hidden" not in panel.get_attribute("class").split()
        assert "Wingspan: Asia" in page.inner_text("#detail-panel")

        # Session card's GenCon link uses the direct /events/<num> URL pattern,
        # not the legacy /events?search=<id> form.
        href = page.eval_on_selector(
            "#detail-panel .session-card a[href*='gencon.com/events']",
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

        # Each session row also has a Google Calendar link with prefilled
        # title/dates/details/location and the GenCon timezone.
        cal_href = page.eval_on_selector(
            "#detail-panel .session-card a[href*='google.com/calendar']",
            "e => e.href",
        )
        assert cal_href.startswith("https://www.google.com/calendar/event?")
        assert "action=TEMPLATE" in cal_href
        # Wall-clock dates from fixture (no timezone math; ctz handles it):
        # 2026-07-30T09:00 -> 20260730T090000, end 13:00 -> 20260730T130000
        assert "dates=20260730T090000%2F20260730T130000" in cal_href
        assert "ctz=America%2FIndiana%2FIndianapolis" in cal_href
        # Title contains the event title and gencon_id
        assert "Wingspan" in cal_href
        assert "BGM26ND000001" in cal_href
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
        # Click Saved button -> active, filter applies in the list.
        page.click("#s-saved")
        page.wait_for_function(
            "document.querySelector('#s-saved').classList.contains('active')"
        )
        # The saved row remains visible; the unsaved row is filtered out.
        page.wait_for_function("document.querySelectorAll('.row').length === 1")
        # Click Saved again -> inactive, all rows back.
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


def test_type_chips_all_active_by_default(server):
    """Page loads with every type chip active (strict-types default)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector('#f-types .chip')
        all_count = page.eval_on_selector_all("#f-types .chip", "els => els.length")
        active_count = page.eval_on_selector_all(
            "#f-types .chip.active", "els => els.length"
        )
        assert all_count == active_count and all_count > 0
        ctx.close()
        browser.close()


def test_type_clear_all_then_select_all(server):
    """Clear all -> 0 rows visible. Select all -> rows back."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        before_rows = page.eval_on_selector_all(".row", "els => els.length")
        assert before_rows >= 1
        page.click("#f-types-none")
        page.wait_for_function("document.querySelectorAll('.row').length === 0")
        # Every chip is now inactive.
        active = page.eval_on_selector_all("#f-types .chip.active", "els => els.length")
        assert active == 0
        page.click("#f-types-all")
        page.wait_for_function(
            f"document.querySelectorAll('.row').length === {before_rows}"
        )
        ctx.close()
        browser.close()


def test_schedule_export_downloads_csv(server):
    """The Export schedule button triggers a CSV download with marked sessions."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Save the BGM (Wingspan) session.
        page.click(".row")
        page.click("#detail-panel .save-toggle")
        # Trigger export and capture the download.
        with page.expect_download() as info:
            page.click("#f-export")
        dl = info.value
        path = dl.path()
        body = Path(path).read_text()
        lines = body.strip().split("\n")
        # Header + 1 data row for the saved session.
        assert lines[0] == "event_id,gencon_id,title,when,saved,purchased"
        assert any("BGM26ND000001" in ln and "1,0" in ln for ln in lines[1:])
        ctx.close()
        browser.close()


def test_schedule_import_replaces_state(tmp_path, server):
    """Picking a CSV via the Import button replaces saved/purchased after confirm."""
    # Build a CSV that marks the SEM session as purchased only.
    csv_path = tmp_path / "schedule.csv"
    csv_path.write_text(
        "event_id,gencon_id,title,when,saved,purchased\n"
        "000005,SEM26ND000005,Cosplay 101,2026-07-31T10:00:00,0,1\n"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#f-import", state="attached")
        # Auto-accept the confirm dialog.
        page.on("dialog", lambda d: d.accept())
        # Upload the file via the hidden file input.
        page.set_input_files("#f-import", str(csv_path))
        # After import: toolbar count = 0 saved, but ★ Saved button updates to 0.
        page.wait_for_function(
            "document.querySelector('#s-saved').textContent.includes('(0)')"
        )
        # The SEM row now has the 🎟 mark; the BGM row has none.
        sem_row_marks = page.eval_on_selector_all(
            ".row .marks", "els => els.map(e => e.textContent)"
        )
        joined = "|".join(sem_row_marks)
        assert "🎟" in joined  # purchased SEM row shows the ticket glyph
        assert "★" not in joined  # nothing saved
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
        # Set non-default state: clear all, then activate BGM.
        page.click("#f-types-none")
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
        # And every chip should be active (default = all selected after popstate
        # with empty hash).
        all_count = page.eval_on_selector_all("#f-types .chip", "els => els.length")
        active = page.eval_on_selector_all("#f-types .chip.active", "els => els.length")
        assert active == all_count and all_count > 0
        browser.close()


def test_clear_filters_resets_filters_preserves_sort(server):
    """Clear button: reset filters, untick ticketsOnly, preserve sort."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Set non-default state: clear types, activate BGM only, switch sort.
        page.click("#f-types-none")
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
        # ticketsOnly is now unchecked (clear flips it off, even though
        # it defaults to true on first load).
        tix = page.eval_on_selector("#f-tix", "e => e.checked")
        assert tix is False
        # All type chips active again (clear restores the all-selected default).
        all_count = page.eval_on_selector_all("#f-types .chip", "els => els.length")
        active_types = page.eval_on_selector_all(
            "#f-types .chip.active", "els => els.length"
        )
        assert active_types == all_count and all_count > 0
        # Hash carries sort but not the narrowed types filter.
        h2 = page.evaluate("() => window.location.hash")
        assert "types=BGM" not in h2
        assert "tix=0" in h2  # because ticketsOnly is now false
        assert "sort=bgg" in h2  # sort preserved
        browser.close()


def test_detail_view_fires_on_show_and_on_close(server):
    """Verify createDetailView's onShow/onClose callbacks fire correctly."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Construct a fresh detail view against an isolated panel; exercise
        # show() and the close-button click path.
        result = page.evaluate("""
        async () => {
          const mod = await import('/app/view-detail.js');
          const panel = document.createElement('aside');
          document.body.appendChild(panel);
          const events = [];
          const view = mod.createDetailView({
            panel,
            onShow: (g) => events.push(['show', g.title]),
            onClose: () => events.push(['close']),
          });
          view.show({
            key: 'TEST', title: 'Probe Group',
            event_type: 'BGM', event_type_label: 'BGM - Board Game',
            min_players: 1, max_players: 4, age_required: 'Teen',
            experience_required: 'Some',
            duration_minutes: 60, cost: 0,
            sessions: [{ gencon_id: 'X', start: '2026-07-30T09:00:00', end: '2026-07-30T10:00:00' }],
          });
          panel.querySelector('.close').click();
          return events;
        }
        """)
        assert result == [["show", "Probe Group"], ["close"]]
        ctx.close()
        browser.close()


def test_session_card_fit_line_renders(server):
    """The session card always shows a fit-status line (✓ or ⚠️)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        page.click(".row")
        page.wait_for_selector("#detail-panel .session-card .session-fit")
        text = page.eval_on_selector(
            "#detail-panel .session-card .session-fit", "e => e.textContent"
        )
        assert "Fits" in text or "Conflicts" in text
        ctx.close()
        browser.close()


def test_row_marker_no_conflict_by_default(server):
    """Default state: no rows have the conflict marker (fixture has no overlaps)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        marks = page.eval_on_selector_all(
            ".row .marks", "els => els.map(e => e.textContent).join('|')"
        )
        assert "⚠" not in marks
        n = page.eval_on_selector_all(".row.conflict", "els => els.length")
        assert n == 0
        ctx.close()
        browser.close()


def test_timeline_renders_saved_and_purchased(server):
    """Construct timeline view and verify it draws blocks for saved/purchased."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        result = page.evaluate("""
        async () => {
          const mod = await import('/app/view-timeline.js');
          const container = document.createElement('div');
          container.style.height = '700px';
          document.body.appendChild(container);
          const view = mod.createTimelineView({
            container,
            onEventClick: () => {},
          });
          const groups = [
            { key: 'G1', title: 'Wingspan',
              sessions: [{ gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T13:00:00' }] },
            { key: 'G2', title: 'Cosplay',
              sessions: [{ gencon_id: 'B', start: '2026-07-31T10:00:00', end: '2026-07-31T11:00:00' }] },
          ];
          view.render(groups, new Set(['A']), new Set(['B']), null, null);
          return {
            saved: container.querySelectorAll('.tl-saved').length,
            purchased: container.querySelectorAll('.tl-purchased').length,
            days: container.querySelectorAll('.tl-day').length,
          };
        }
        """)
        assert result["saved"] == 1
        assert result["purchased"] == 1
        assert result["days"] == 2
        ctx.close()
        browser.close()


def test_timeline_lanes_for_conflict(server):
    """Two overlapping sessions on the same day render in separate tracks
    and the day column widens to fit them."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        result = page.evaluate("""
        async () => {
          const mod = await import('/app/view-timeline.js');
          const container = document.createElement('div');
          document.body.appendChild(container);
          const view = mod.createTimelineView({ container, onEventClick: () => {} });
          const groups = [
            { key: 'G1', title: 'Pathfinder',
              sessions: [{ gencon_id: 'A', start: '2026-07-30T10:00:00', end: '2026-07-30T13:00:00' }] },
            { key: 'G2', title: 'Catan',
              sessions: [{ gencon_id: 'B', start: '2026-07-30T11:00:00', end: '2026-07-30T13:00:00' }] },
          ];
          view.render(groups, new Set(['A', 'B']), new Set(),
                      new Set(['A', 'B']), null);
          const blocks = [...container.querySelectorAll('.tl-event')]
            .map(e => e.style.width);
          const dayWidth = container.querySelector('.tl-day').style.width;
          const conflictBlocks = container.querySelectorAll('.tl-event.tl-conflict').length;
          return { blocks, dayWidth, conflictBlocks };
        }
        """)
        assert result["conflictBlocks"] == 2
        assert "calc(50% - 2px)" in result["blocks"][0]
        # Column width = 2 tracks × 140px = 280px
        assert result["dayWidth"] == "280px"
        ctx.close()
        browser.close()


def test_timeline_shows_out_of_window_indicators(server):
    """Sessions starting before 8a or ending after midnight render with ←/→."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        result = page.evaluate("""
        async () => {
          const mod = await import('/app/view-timeline.js');
          const container = document.createElement('div');
          document.body.appendChild(container);
          const view = mod.createTimelineView({ container, onEventClick: () => {} });
          const groups = [
            { key: 'EARLY', title: 'Pre-dawn Tournament',
              sessions: [{ gencon_id: 'A', start: '2026-07-30T06:00:00', end: '2026-07-30T10:00:00' }] },
            { key: 'LATE', title: 'Midnight Madness',
              sessions: [{ gencon_id: 'B', start: '2026-07-30T22:00:00', end: '2026-07-31T02:00:00' }] },
          ];
          view.render(groups, new Set(['A', 'B']), new Set(), null, null);
          return {
            beforeMarkers: container.querySelectorAll('.tl-out.before').length,
            afterMarkers: container.querySelectorAll('.tl-out.after').length,
          };
        }
        """)
        assert result["beforeMarkers"] == 1
        assert result["afterMarkers"] == 1
        ctx.close()
        browser.close()


def test_timeline_preview_blocks_unit(server):
    """Pass a previewGroup to render() — its sessions appear as preview blocks."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        result = page.evaluate("""
        async () => {
          const mod = await import('/app/view-timeline.js');
          const container = document.createElement('div');
          document.body.appendChild(container);
          const view = mod.createTimelineView({ container, onEventClick: () => {} });
          const groups = [
            { key: 'BROWSING', title: 'Dixit',
              sessions: [
                { gencon_id: 'D1', start: '2026-07-30T14:00:00', end: '2026-07-30T17:00:00' },
                { gencon_id: 'D2', start: '2026-07-31T15:00:00', end: '2026-07-31T17:00:00' },
              ] },
          ];
          view.render(groups, new Set(), new Set(), null, groups[0]);
          return {
            previews: container.querySelectorAll('.tl-preview').length,
            saved: container.querySelectorAll('.tl-saved').length,
          };
        }
        """)
        assert result["previews"] == 2
        assert result["saved"] == 0
        ctx.close()
        browser.close()


def test_toolbar_timeline_toggle(server):
    """Clicking the 🗓️ Timeline button shows/hides the timeline panel
    alongside the (always-visible) list view."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#s-timeline")
        # Initially: list visible, timeline hidden.
        assert "hidden" in page.eval_on_selector("#results-timeline", "e => e.className")
        assert "hidden" not in page.eval_on_selector("#results-list", "e => e.className")
        # Click the timeline toggle.
        page.click("#s-timeline")
        page.wait_for_function(
            "!document.querySelector('#results-timeline').classList.contains('hidden')"
        )
        # Timeline now visible; list stays visible (side-by-side).
        assert "hidden" not in page.eval_on_selector("#results-timeline", "e => e.className")
        assert page.eval_on_selector(
            "#results-list", "e => getComputedStyle(e).display"
        ) != "none"
        # Hash records the mode.
        h = page.evaluate("() => window.location.hash")
        assert "view=timeline" in h
        # Toggle back.
        page.click("#s-timeline")
        page.wait_for_function(
            "document.querySelector('#results-timeline').classList.contains('hidden')"
        )
        h2 = page.evaluate("() => window.location.hash")
        assert "view=timeline" not in h2
        ctx.close()
        browser.close()


def test_list_stays_visible_in_timeline_mode(server):
    """Side-by-side semantics: enabling timeline mode keeps the list visible
    AND in-sync with the predicate. Both panels render together."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Save the BGM session so we have something to filter to.
        page.click(".row")
        page.click("#detail-panel .save-toggle")
        page.click("#detail-panel .close")
        # Enable timeline.
        page.click("#s-timeline")
        page.wait_for_function(
            "!document.querySelector('#results-timeline').classList.contains('hidden')"
        )
        # The list must remain visible (not display:none).
        list_display = page.eval_on_selector(
            "#results-list", "e => getComputedStyle(e).display"
        )
        assert list_display != "none", f"list shouldn't be hidden, got {list_display!r}"
        # And the list must still reflect the current filter state. Toggle
        # Saved-only to confirm setRows is being called in timeline mode.
        n_before = page.eval_on_selector_all(".row", "els => els.length")
        page.click("#s-saved")
        page.wait_for_function(
            "document.querySelector('#s-saved').classList.contains('active')"
        )
        page.wait_for_function("document.querySelectorAll('.row').length === 1")
        n_after = page.eval_on_selector_all(".row", "els => els.length")
        assert n_after == 1, f"list didn't update: was {n_before}, now {n_after}"
        ctx.close()
        browser.close()


def test_saved_button_keeps_list_view(server):
    """Toggling Saved-only filters the list in place; it does NOT switch to timeline."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#s-saved")
        # Initially: list view.
        assert "hidden" in page.eval_on_selector("#results-timeline", "e => e.className")
        page.click("#s-saved")
        page.wait_for_function(
            "document.querySelector('#s-saved').classList.contains('active')"
        )
        # List view stays visible; timeline stays hidden.
        assert "hidden" in page.eval_on_selector("#results-timeline", "e => e.className")
        assert "hidden" not in page.eval_on_selector("#results-list", "e => e.className")
        ctx.close()
        browser.close()


def test_list_has_column_header_row(server):
    """The list area has a header row above #results-list with column labels."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#results-header")
        labels = page.eval_on_selector_all(
            "#results-header .row-cell",
            "els => els.map(e => e.textContent.trim()).filter(Boolean)",
        )
        # Header labels in order (the leading empty marks cell is filtered out).
        assert labels == ["Title", "Type", "When", "Tix", "BGG"]
        browser.close()


def test_row_columns_b_aligned(server):
    """Row uses the new grid template — marks · title · type · when · tix · bgg."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        cell_classes = page.eval_on_selector(
            ".row",
            "e => [...e.children].map(c => c.className.split(' ')[0])",
        )
        assert cell_classes == ["marks", "title", "type", "when", "tix", "bgg"]
        browser.close()


def test_phone_hamburger_toggles_drawer(server):
    """At phone width: hamburger button visible; clicking toggles drawer."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 375, "height": 700})
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")

        # Hamburger is visible on phone (display != 'none').
        ham_display = page.eval_on_selector(
            "#hamburger", "e => getComputedStyle(e).display"
        )
        assert ham_display != "none"

        # Drawer closed initially.
        body_classes_before = page.eval_on_selector("body", "e => e.className")
        assert "drawer-open" not in body_classes_before

        # Click hamburger → drawer opens.
        page.click("#hamburger")
        page.wait_for_function(
            "document.body.classList.contains('drawer-open')"
        )

        # Click the backdrop → drawer closes.
        page.click("#drawer-backdrop")
        page.wait_for_function(
            "!document.body.classList.contains('drawer-open')"
        )

        ctx.close()
        browser.close()


def test_desktop_hamburger_hidden(server):
    """At desktop width: hamburger is display: none."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#hamburger", state="attached")
        ham_display = page.eval_on_selector(
            "#hamburger", "e => getComputedStyle(e).display"
        )
        assert ham_display == "none"
        ctx.close()
        browser.close()


def test_phone_detail_panel_full_screen(server):
    """At phone width: opening an event makes #detail-panel a full-screen overlay."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 375, "height": 700})
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        page.click(".row")
        page.wait_for_function(
            "!document.querySelector('#detail-panel').classList.contains('hidden')"
        )
        rect = page.eval_on_selector(
            "#detail-panel",
            "e => { const r = e.getBoundingClientRect(); return {x:r.x, y:r.y, w:r.width, h:r.height}; }",
        )
        # Panel covers the viewport below the 38px-ish header.
        assert rect["x"] == 0
        assert rect["w"] == 375
        # Top must be at or below the app-header (around 38px).
        assert rect["y"] >= 30 and rect["y"] <= 50
        # Bottom extends to/past the viewport.
        assert rect["y"] + rect["h"] >= 700
        ctx.close()
        browser.close()


def test_phone_toolbar_overflows_with_scroll(server):
    """At phone width: toolbar-right has horizontal scroll if its buttons overflow."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 375, "height": 700})
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector("#results-toolbar")
        overflow_x = page.eval_on_selector(
            "#results-toolbar .toolbar-right",
            "e => getComputedStyle(e).overflowX",
        )
        assert overflow_x == "auto"
        ctx.close()
        browser.close()


def test_phone_timeline_hides_list_and_scrolls(server):
    """At phone width: enabling timeline hides the list, timeline takes full width."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 375, "height": 700})
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        # Click timeline toggle.
        page.click("#s-timeline")
        page.wait_for_function(
            "document.body.classList.contains('timeline-on')"
        )
        list_display = page.eval_on_selector(
            "#results-list", "e => getComputedStyle(e).display"
        )
        assert list_display == "none"
        # Timeline panel is visible and has overflow: auto for horizontal scroll.
        tl_overflow = page.eval_on_selector(
            "#results-timeline", "e => getComputedStyle(e).overflowX"
        )
        assert tl_overflow == "auto"
        # Header row is also hidden on phone timeline mode.
        header_display = page.eval_on_selector(
            "#results-header", "e => getComputedStyle(e).display"
        )
        assert header_display == "none"
        ctx.close()
        browser.close()


def test_desktop_timeline_keeps_list_visible(server):
    """At desktop width: enabling timeline keeps the list visible alongside."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        page.click("#s-timeline")
        page.wait_for_function(
            "!document.querySelector('#results-timeline').classList.contains('hidden')"
        )
        list_display = page.eval_on_selector(
            "#results-list", "e => getComputedStyle(e).display"
        )
        assert list_display != "none"
        ctx.close()
        browser.close()
