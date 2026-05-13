"""Drive docs/app/view-timeline.js's pure helpers inside a real browser
via Playwright. Mirrors the harness pattern used in test_filters_js.py.

Today only collectDays is exercised here — the full timeline render is
covered by the end-to-end smoke tests."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

HARNESS_HTML = """\
<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as T from '/docs/app/view-timeline.js';
window.T = T;
</script>
</body></html>
"""


def _serve(route):
    url = route.request.url
    if "/docs/app/view-timeline.js" in url:
        body = (ROOT / "docs" / "app" / "view-timeline.js").read_text()
        route.fulfill(body=body, content_type="application/javascript")
    elif "/docs/app/conflict.js" in url:
        body = (ROOT / "docs" / "app" / "conflict.js").read_text()
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
        pg.wait_for_function("typeof window.T !== 'undefined'")
        yield pg
        browser.close()


def _eval(page, code: str):
    return page.evaluate(f"(() => {{ {code} }})()")


def test_collect_days_includes_in_window_dates(page):
    js = """
    const groups = [
      { sessions: [
        { start: '2026-07-30T09:00:00' },  // Thu
        { start: '2026-07-31T14:00:00' },  // Fri
        { start: '2026-08-01T10:00:00' },  // Sat
        { start: '2026-08-02T11:00:00' },  // Sun
      ]},
    ];
    return JSON.stringify(T.collectDays(groups));
    """
    days = json.loads(_eval(page, js))
    assert days == ['2026-07-30', '2026-07-31', '2026-08-01', '2026-08-02']


def test_collect_days_drops_pre_con_setup_day(page):
    """A session starting Wed 7/29 (setup / pre-con) must not produce a column."""
    js = """
    const groups = [
      { sessions: [
        { start: '2026-07-29T09:00:00' },  // Wed (pre-con)
        { start: '2026-07-30T09:00:00' },  // Thu
      ]},
    ];
    return JSON.stringify(T.collectDays(groups));
    """
    days = json.loads(_eval(page, js))
    assert days == ['2026-07-30']


def test_collect_days_drops_post_con_outlier(page):
    """A session starting after Sun 8/2 (e.g. Fri 8/7) must not produce a column."""
    js = """
    const groups = [
      { sessions: [
        { start: '2026-07-30T09:00:00' },  // Thu
        { start: '2026-08-07T09:00:00' },  // Fri after con
      ]},
    ];
    return JSON.stringify(T.collectDays(groups));
    """
    days = json.loads(_eval(page, js))
    assert days == ['2026-07-30']


def test_collect_days_returns_sorted_unique_days(page):
    """Multiple sessions on the same day collapse to one entry; result is sorted."""
    js = """
    const groups = [
      { sessions: [
        { start: '2026-08-02T09:00:00' },
        { start: '2026-07-30T09:00:00' },
        { start: '2026-07-30T14:00:00' },  // dup day
        { start: '2026-08-01T10:00:00' },
      ]},
    ];
    return JSON.stringify(T.collectDays(groups));
    """
    days = json.loads(_eval(page, js))
    assert days == ['2026-07-30', '2026-08-01', '2026-08-02']


def test_collect_days_ignores_sessions_without_start(page):
    js = """
    const groups = [
      { sessions: [
        { start: null },
        { /* no start key */ },
        { start: '2026-07-30T09:00:00' },
      ]},
    ];
    return JSON.stringify(T.collectDays(groups));
    """
    days = json.loads(_eval(page, js))
    assert days == ['2026-07-30']
