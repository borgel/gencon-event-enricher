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
    if "/docs/app/sort.js" in url:
        body = (ROOT / "docs" / "app" / "sort.js").read_text()
        route.fulfill(body=body, content_type="application/javascript")
    elif "/docs/app/filters.js" in url:
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


def test_hash_roundtrip_includes_sort(page):
    """Sort state must round-trip through filters.stateToHash/hashToState."""
    js = """
    const s = F.defaultState();
    s.sortKey = 'bgg';
    s.sortDir = 'desc';
    const h = F.stateToHash(s);
    const back = F.hashToState(h);
    return JSON.stringify({ h, sortKey: back.sortKey, sortDir: back.sortDir });
    """
    obj = json.loads(_eval(page, js))
    assert "sort=bgg" in obj["h"]
    assert "dir=desc" in obj["h"]
    assert obj["sortKey"] == "bgg"
    assert obj["sortDir"] == "desc"


def test_hash_omits_default_sort(page):
    """Defaults are never written to the hash."""
    js = """
    const s = F.defaultState();
    return F.stateToHash(s);
    """
    h = _eval(page, js)
    assert "sort=" not in h
    assert "dir=" not in h


def test_bggmatch_yes_keeps_only_matched(page):
    js = """
    const s = F.defaultState();
    s.bggMatch = 'yes';
    s.ticketsOnly = false;
    const p = F.buildPredicate(s, new Set());
    return JSON.stringify({
      hasBgg: p({ event_type: 'BGM', bgg: { bayesaverage: 7 },
                  sessions: [{ start: '2026-07-30T09:00' }] }),
      noBgg:  p({ event_type: 'BGM', bgg: null,
                  sessions: [{ start: '2026-07-30T09:00' }] }),
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["hasBgg"] is True
    assert obj["noBgg"] is False


def test_bggmatch_no_keeps_only_unmatched(page):
    js = """
    const s = F.defaultState();
    s.bggMatch = 'no';
    s.ticketsOnly = false;
    const p = F.buildPredicate(s, new Set());
    return JSON.stringify({
      hasBgg: p({ event_type: 'BGM', bgg: { bayesaverage: 7 },
                  sessions: [{ start: '2026-07-30T09:00' }] }),
      noBgg:  p({ event_type: 'BGM', bgg: null,
                  sessions: [{ start: '2026-07-30T09:00' }] }),
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["hasBgg"] is False
    assert obj["noBgg"] is True


def test_bggmatch_either_is_no_op(page):
    js = """
    const s = F.defaultState();
    s.bggMatch = 'either';
    s.ticketsOnly = false;
    const p = F.buildPredicate(s, new Set());
    return JSON.stringify({
      hasBgg: p({ event_type: 'BGM', bgg: { bayesaverage: 7 },
                  sessions: [{ start: '2026-07-30T09:00' }] }),
      noBgg:  p({ event_type: 'BGM', bgg: null,
                  sessions: [{ start: '2026-07-30T09:00' }] }),
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["hasBgg"] is True
    assert obj["noBgg"] is True


def test_bggmatch_hash_roundtrip(page):
    js = """
    const s = F.defaultState();
    s.bggMatch = 'no';
    const h = F.stateToHash(s);
    const back = F.hashToState(h);
    return JSON.stringify({ h, bggMatch: back.bggMatch });
    """
    obj = json.loads(_eval(page, js))
    assert "bggMatch=no" in obj["h"]
    assert obj["bggMatch"] == "no"


def test_duration_range_keeps_in_band(page):
    js = """
    const s = F.defaultState();
    s.durMinH = 2;
    s.durMaxH = 4;
    s.ticketsOnly = false;
    const p = F.buildPredicate(s, new Set());
    return JSON.stringify({
      shortG:  p({ event_type: 'BGM', duration_minutes: 60,
                   sessions: [{ start: '2026-07-30T09:00' }] }),
      midG:    p({ event_type: 'BGM', duration_minutes: 180,
                   sessions: [{ start: '2026-07-30T09:00' }] }),
      longG:   p({ event_type: 'BGM', duration_minutes: 360,
                   sessions: [{ start: '2026-07-30T09:00' }] }),
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["shortG"] is False
    assert obj["midG"] is True
    assert obj["longG"] is False


def test_duration_max_12_means_unbounded(page):
    """A durMaxH of 12 is the sentinel meaning 'no upper bound'."""
    js = """
    const s = F.defaultState();
    s.durMinH = 0;
    s.durMaxH = 12;
    s.ticketsOnly = false;
    const p = F.buildPredicate(s, new Set());
    return p({ event_type: 'BGM', duration_minutes: 1080,
               sessions: [{ start: '2026-07-30T09:00' }] });
    """
    assert _eval(page, js) is True


def test_duration_hash_roundtrip(page):
    js = """
    const s = F.defaultState();
    s.durMinH = 1.5;
    s.durMaxH = 4;
    const h = F.stateToHash(s);
    const back = F.hashToState(h);
    return JSON.stringify({ h, durMinH: back.durMinH, durMaxH: back.durMaxH });
    """
    obj = json.loads(_eval(page, js))
    assert "durMin=1.5" in obj["h"]
    assert "durMax=4" in obj["h"]
    assert obj["durMinH"] == 1.5
    assert obj["durMaxH"] == 4


def test_duration_default_omitted_from_hash(page):
    js = """
    const s = F.defaultState();
    return F.stateToHash(s);
    """
    h = _eval(page, js)
    assert "durMin=" not in h
    assert "durMax=" not in h


def test_hash_roundtrip_kitchen_sink(page):
    """Round-trip a URL hash that exercises every new key plus a few existing ones."""
    js = """
    const s = F.defaultState();
    s.search = 'wingspan asia';
    s.days = new Set(['thu', 'fri']);
    s.types = new Set(['BGM', 'RPG']);
    s.bggMin = 7.5;
    s.bggMatch = 'yes';
    s.durMinH = 1.5;
    s.durMaxH = 4;
    s.sortKey = 'bgg';
    s.sortDir = 'desc';
    s.ticketsOnly = false;
    const h = F.stateToHash(s);
    const back = F.hashToState(h);
    return JSON.stringify({
      h,
      back: { ...back,
        days: [...back.days].sort(),
        types: [...back.types].sort(),
        locations: [...back.locations],
      },
    });
    """
    obj = json.loads(_eval(page, js))
    h = obj["h"]
    # Every new fragment present
    assert "sort=bgg" in h
    assert "dir=desc" in h
    assert "bggMatch=yes" in h
    assert "durMin=1.5" in h
    assert "durMax=4" in h
    # Pre-existing fragments still present
    assert "bgg=7.5" in h
    assert "tix=0" in h
    assert "types=" in h
    assert "days=" in h
    # Round-trip correctness
    back = obj["back"]
    assert back["search"] == "wingspan asia"
    assert back["days"] == ["fri", "thu"]
    assert back["types"] == ["BGM", "RPG"]
    assert back["bggMin"] == 7.5
    assert back["bggMatch"] == "yes"
    assert back["durMinH"] == 1.5
    assert back["durMaxH"] == 4
    assert back["sortKey"] == "bgg"
    assert back["sortDir"] == "desc"
    assert back["ticketsOnly"] is False
