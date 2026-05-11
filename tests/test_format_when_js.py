"""Drive docs/app/view-table.js's formatWhen export via Playwright."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

HARNESS_HTML = """\
<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as V from '/docs/app/view-table.js';
window.V = V;
</script>
</body></html>
"""


def _serve(route):
    url = route.request.url
    if "/docs/app/view-table.js" in url:
        body = (ROOT / "docs" / "app" / "view-table.js").read_text()
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
        pg.wait_for_function("typeof window.V !== 'undefined'")
        yield pg
        browser.close()


def _eval(page, code: str):
    return page.evaluate(f"(() => {{ {code} }})()")


def test_format_when_single_session(page):
    js = """
    const g = { sessions: [{ start: '2026-07-30T09:00:00' }] };
    return V.formatWhen(g);
    """
    # GenCon 2026 Thu = 2026-07-30. 9am → "Thu 9a".
    assert _eval(page, js) == "Thu 9a"


def test_format_when_multi_session_single_day(page):
    js = """
    const g = { sessions: [
      { start: '2026-08-01T09:00:00' },
      { start: '2026-08-01T13:00:00' },
      { start: '2026-08-01T17:00:00' },
    ]};
    return V.formatWhen(g);
    """
    # Sat. 3 sessions same day → "3× Sat".
    assert _eval(page, js) == "3× Sat"


def test_format_when_multi_session_multi_day(page):
    js = """
    const g = { sessions: [
      { start: '2026-07-30T09:00:00' },
      { start: '2026-07-31T09:00:00' },
      { start: '2026-08-01T09:00:00' },
      { start: '2026-08-02T09:00:00' },
    ]};
    return V.formatWhen(g);
    """
    # 4 sessions Thu/Fri/Sat/Sun → "4× Thu–Sun".
    assert _eval(page, js) == "4× Thu–Sun"


def test_format_when_multi_session_non_contiguous(page):
    """Thu and Sat only (no Fri) → first–last bracket."""
    js = """
    const g = { sessions: [
      { start: '2026-07-30T09:00:00' },
      { start: '2026-08-01T09:00:00' },
    ]};
    return V.formatWhen(g);
    """
    assert _eval(page, js) == "2× Thu–Sat"


def test_format_when_empty_sessions(page):
    """Defensive: empty session list returns empty string."""
    js = """
    const g = { sessions: [] };
    return V.formatWhen(g);
    """
    assert _eval(page, js) == ""


def test_format_when_minute_precision_single(page):
    """Single session at 9:30 → 'Thu 9:30a'."""
    js = """
    const g = { sessions: [{ start: '2026-07-30T09:30:00' }] };
    return V.formatWhen(g);
    """
    assert _eval(page, js) == "Thu 9:30a"
