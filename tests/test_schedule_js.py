"""Drive docs/app/schedule.js inside a real browser via Playwright.

Mirrors the harness pattern used in test_filters_js.py / test_sort_js.py.
"""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

HARNESS_HTML = """\
<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as S from '/docs/app/schedule.js';
window.S = S;
</script>
</body></html>
"""


def _serve(route):
    url = route.request.url
    if "/docs/app/schedule.js" in url:
        body = (ROOT / "docs" / "app" / "schedule.js").read_text()
        route.fulfill(body=body, content_type="application/javascript")
    elif "/harness" in url:
        route.fulfill(body=HARNESS_HTML, content_type="text/html")
    else:
        route.fulfill(status=404, body="not found")


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        ctx.route("**/*", lambda route: _serve(route))
        pg = ctx.new_page()
        pg.goto("http://localhost/harness", wait_until="networkidle")
        pg.wait_for_function("typeof window.S !== 'undefined'")
        yield pg
        browser.close()


def _eval(page, code: str):
    return page.evaluate(f"(() => {{ {code} }})()")


_GROUPS = [
    {
        "key": "BGM-foo",
        "title": "Foo, the Game",  # comma-in-title to exercise CSV escaping
        "sessions": [
            {"gencon_id": "BGM26ND313243", "start": "2026-07-31T19:00:00"},
            {"gencon_id": "BGM26ND313244", "start": "2026-08-01T10:00:00"},
        ],
    },
    {
        "key": "RPG-bar",
        "title": "Bar Quest",
        "sessions": [
            {"gencon_id": "RPG26ND400500", "start": "2026-07-30T09:00:00"},
        ],
    },
]


def test_export_only_includes_marked_sessions(page):
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const saved = new Set(['BGM26ND313243']);
    const purchased = new Set(['RPG26ND400500']);
    return S.exportSchedule(groups, saved, purchased);
    """
    csv = _eval(page, js)
    lines = csv.strip().split("\n")
    # Header + 2 data rows (BGM saved, RPG purchased; BGM-313244 omitted).
    assert len(lines) == 3
    assert lines[0] == "event_id,gencon_id,title,when,saved,purchased"
    # Comma-in-title is quoted in the CSV
    assert '"Foo, the Game"' in csv
    # Numeric event_id is the trailing digits, in the first column of a row
    assert lines[1].startswith("313243,") or lines[2].startswith("313243,")
    assert lines[1].startswith("400500,") or lines[2].startswith("400500,")


def test_export_then_import_roundtrip(page):
    """Export some state, parse it back; matched IDs and flags must round-trip."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const saved = new Set(['BGM26ND313243']);
    const purchased = new Set(['BGM26ND313243', 'RPG26ND400500']);
    const csv = S.exportSchedule(groups, saved, purchased);
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{
      saved: [...result.saved].sort(),
      purchased: [...result.purchased].sort(),
      matched: result.matched,
      missed: result.missed,
    }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["saved"] == ["BGM26ND313243"]
    assert obj["purchased"] == ["BGM26ND313243", "RPG26ND400500"]
    assert obj["matched"] == 2  # 2 unique session rows in CSV
    assert obj["missed"] == 0


def test_import_matches_by_numeric_id(page):
    """Even with the gencon_id column scrambled, numeric event_id matches."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv =
      'event_id,gencon_id,title,when,saved,purchased\\n' +
      '313243,IGNORED,foo,2026-07-31T19:00,1,0\\n' +
      '400500,WRONG-PREFIX,bar,2026-07-30T09:00,0,1\\n';
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{
      saved: [...result.saved].sort(),
      purchased: [...result.purchased].sort(),
      matched: result.matched, missed: result.missed,
    }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["saved"] == ["BGM26ND313243"]
    assert obj["purchased"] == ["RPG26ND400500"]
    assert obj["matched"] == 2 and obj["missed"] == 0


def test_import_reports_misses_for_unknown_ids(page):
    """Rows whose IDs aren't in the loaded dataset are counted as missed."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv =
      'event_id,gencon_id,title,when,saved,purchased\\n' +
      '313243,BGM26ND313243,foo,2026,1,0\\n' +
      '999999,XXX26ND999999,gone,2026,1,1\\n';
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{ matched: result.matched, missed: result.missed }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["matched"] == 1
    assert obj["missed"] == 1


def test_import_handles_quoted_commas_in_title(page):
    """A CSV row whose title contains a quoted comma still parses cleanly."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv =
      'event_id,gencon_id,title,when,saved,purchased\\n' +
      '313243,BGM26ND313243,"Foo, the Game",2026-07-31T19:00,1,0\\n';
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{
      saved: [...result.saved], matched: result.matched,
    }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["saved"] == ["BGM26ND313243"]
    assert obj["matched"] == 1


def test_import_truthy_variations(page):
    """saved/purchased columns accept 1/true/yes (case-insensitive)."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv =
      'event_id,saved,purchased\\n' +
      '313243,TRUE,no\\n' +
      '400500,yes,1\\n';
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{
      saved: [...result.saved].sort(),
      purchased: [...result.purchased].sort(),
    }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["saved"] == ["BGM26ND313243", "RPG26ND400500"]
    assert obj["purchased"] == ["RPG26ND400500"]
