"""Drive docs/app/filters.js inside a real browser via Playwright.

We use a tiny HTML harness that imports the module and exposes assert helpers
on `window`. Test functions evaluate JS and read structured results back.
"""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

HARNESS_HTML = """\
<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as F from '/docs/app/filters.js';
window.F = F;
</script>
</body></html>
"""


def _serve(route):
    url = route.request.url
    if "/docs/app/filters.js" in url:
        body = (ROOT / "docs" / "app" / "filters.js").read_text()
        route.fulfill(body=body, content_type="application/javascript")
    elif "/harness" in url:
        route.fulfill(body=HARNESS_HTML, content_type="text/html")
    else:
        route.fulfill(status=404, body="not found")


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    # Serve docs/ via Playwright's built-in route handler.
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        ctx.route("**/*", lambda route: _serve(route))
        pg = ctx.new_page()
        # Navigate to a URL so module imports go through the route handler.
        pg.goto("http://localhost/harness", wait_until="networkidle")
        # Wait for window.F to be set by the ES module.
        pg.wait_for_function("typeof window.F !== 'undefined'")
        yield pg
        browser.close()


def _eval(page, code: str):
    return page.evaluate(f"(() => {{ {code} }})()")


def test_default_state(page):
    s = _eval(page, "return JSON.stringify({...F.defaultState(), days: [...F.defaultState().days]})")
    obj = json.loads(s)
    assert obj["search"] == ""
    assert obj["ticketsOnly"] is True
    assert obj["tournament"] == "either"
    assert obj["days"] == []


def test_state_to_hash_empty(page):
    h = _eval(page, "return F.stateToHash(F.defaultState())")
    assert h == ""


def test_roundtrip_with_filters(page):
    js = """
    const s = F.defaultState();
    s.days = new Set(['thu', 'fri']);
    s.types = new Set(['BGM']);
    s.bggMin = 7.5;
    s.search = 'wingspan asia';
    s.ticketsOnly = false;
    const h = F.stateToHash(s);
    const back = F.hashToState(h);
    return JSON.stringify({
      h,
      back: { ...back,
        days: [...back.days].sort(),
        types: [...back.types],
        durationBands: [...back.durationBands],
        locations: [...back.locations],
      }
    });
    """
    obj = json.loads(_eval(page, js))
    h = obj["h"]
    assert "days=thu,fri" in h or "days=fri,thu" in h
    assert "types=BGM" in h
    assert "bgg=7.5" in h
    assert "q=wingspan%20asia" in h or "q=wingspan+asia" in h or "q=wingspan%2520asia" in h
    assert "tix=0" in h
    assert obj["back"]["days"] == ["fri", "thu"] or obj["back"]["days"] == ["thu", "fri"]
    assert obj["back"]["types"] == ["BGM"]
    assert obj["back"]["bggMin"] == 7.5
    assert obj["back"]["search"] == "wingspan asia"
    assert obj["back"]["ticketsOnly"] is False


def test_predicate_filters_by_type(page):
    js = """
    const s = F.defaultState();
    s.types = new Set(['BGM']);
    const p = F.buildPredicate(s, new Set());
    return JSON.stringify({
      bgm: p({ event_type: 'BGM', sessions: [{ start: '2026-07-30T09:00', tickets_available: 8 }] }),
      rpg: p({ event_type: 'RPG', sessions: [{ start: '2026-07-30T09:00', tickets_available: 8 }] }),
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["bgm"] is True
    assert obj["rpg"] is False
