"""Drive docs/app/conflict.js inside a real browser via Playwright.

Mirrors test_sort_js.py.
"""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

HARNESS_HTML = """\
<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as C from '/docs/app/conflict.js';
window.C = C;
</script>
</body></html>
"""


def _serve(route):
    url = route.request.url
    if "/docs/app/conflict.js" in url:
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
        pg.wait_for_function("typeof window.C !== 'undefined'")
        yield pg
        browser.close()


def _eval(page, code: str):
    return page.evaluate(f"(() => {{ {code} }})()")


def test_detect_overlaps_empty(page):
    out = _eval(page, "return [...C.detectOverlaps([])]")
    assert out == []


def test_detect_overlaps_no_overlap(page):
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T10:00:00' },
      { gencon_id: 'B', start: '2026-07-30T10:00:00', end: '2026-07-30T11:00:00' },
    ];
    return [...C.detectOverlaps(sessions)];
    """
    # Adjacent intervals (closed-open) do NOT overlap.
    assert _eval(page, js) == []


def test_detect_overlaps_pair(page):
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T11:00:00' },
      { gencon_id: 'B', start: '2026-07-30T10:00:00', end: '2026-07-30T12:00:00' },
    ];
    return [...C.detectOverlaps(sessions)].sort();
    """
    assert _eval(page, js) == ["A", "B"]


def test_detect_overlaps_different_days(page):
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T11:00:00' },
      { gencon_id: 'B', start: '2026-07-31T10:00:00', end: '2026-07-31T12:00:00' },
    ];
    return [...C.detectOverlaps(sessions)];
    """
    assert _eval(page, js) == []


def test_detect_overlaps_three_way(page):
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T11:00:00' },
      { gencon_id: 'B', start: '2026-07-30T10:00:00', end: '2026-07-30T12:00:00' },
      { gencon_id: 'C', start: '2026-07-30T10:30:00', end: '2026-07-30T11:30:00' },
    ];
    return [...C.detectOverlaps(sessions)].sort();
    """
    assert _eval(page, js) == ["A", "B", "C"]


def test_assign_tracks_single(page):
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T10:00:00' },
    ];
    return Object.fromEntries(C.assignTracks(sessions));
    """
    assert _eval(page, js) == {"A": 0}


def test_assign_tracks_non_overlap(page):
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T10:00:00' },
      { gencon_id: 'B', start: '2026-07-30T10:00:00', end: '2026-07-30T11:00:00' },
    ];
    return Object.fromEntries(C.assignTracks(sessions));
    """
    assert _eval(page, js) == {"A": 0, "B": 0}


def test_assign_tracks_overlap_pair(page):
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T11:00:00' },
      { gencon_id: 'B', start: '2026-07-30T10:00:00', end: '2026-07-30T12:00:00' },
    ];
    return Object.fromEntries(C.assignTracks(sessions));
    """
    assert _eval(page, js) == {"A": 0, "B": 1}


def test_assign_tracks_chain_reuse(page):
    """A overlaps B; B overlaps C; A and C don't overlap → A,C share track 0."""
    js = """
    const sessions = [
      { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T10:30:00' },
      { gencon_id: 'B', start: '2026-07-30T10:00:00', end: '2026-07-30T11:30:00' },
      { gencon_id: 'C', start: '2026-07-30T11:00:00', end: '2026-07-30T12:00:00' },
    ];
    return Object.fromEntries(C.assignTracks(sessions));
    """
    obj = _eval(page, js)
    assert obj == {"A": 0, "B": 1, "C": 0}
