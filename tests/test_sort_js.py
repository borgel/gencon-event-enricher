"""Drive docs/app/sort.js inside a real browser via Playwright.

Mirrors test_filters_js.py — a tiny HTML harness imports the module and
exposes it on window.S so tests can call functions and read structured results.
"""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

HARNESS_HTML = """\
<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as S from '/docs/app/sort.js';
window.S = S;
</script>
</body></html>
"""


def _serve(route):
    url = route.request.url
    if "/docs/app/sort.js" in url:
        body = (ROOT / "docs" / "app" / "sort.js").read_text()
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


def test_default_sort_state(page):
    s = _eval(page, "return JSON.stringify(S.defaultSortState())")
    assert json.loads(s) == {"key": "start", "dir": "asc"}


def test_sort_hash_default_is_empty(page):
    h = _eval(page, "return S.sortStateToHash(S.defaultSortState())")
    assert h == ""


def test_sort_hash_roundtrip_non_default(page):
    js = """
    const s = { key: 'bgg', dir: 'desc' };
    const h = S.sortStateToHash(s);
    const back = { ...S.defaultSortState() };
    S.applyHashPair(back, 'sort', 'bgg');
    S.applyHashPair(back, 'dir', 'desc');
    return JSON.stringify({ h, back });
    """
    obj = json.loads(_eval(page, js))
    assert obj["h"] == "sort=bgg&dir=desc"
    assert obj["back"] == {"key": "bgg", "dir": "desc"}


def test_labels_have_all_combinations(page):
    js = """
    const out = {};
    for (const k of ['start', 'type', 'bgg']) {
      for (const d of ['asc', 'desc']) {
        out[k + '/' + d] = S.LABELS[k][d];
      }
    }
    return JSON.stringify(out);
    """
    labels = json.loads(_eval(page, js))
    for combo in ["start/asc", "start/desc", "type/asc", "type/desc", "bgg/asc", "bgg/desc"]:
        assert isinstance(labels[combo], str) and len(labels[combo]) > 0


def test_key_options_shape(page):
    opts = json.loads(_eval(page, "return JSON.stringify(S.KEY_OPTIONS)"))
    assert opts == [["start", "Start time"], ["type", "Event type"], ["bgg", "BGG rating"]]


def _fixture_groups():
    """Four groups for comparator tests. Two have BGG, two don't."""
    return [
        {
            "key": "a",
            "event_type_label": "Board Game",
            "sessions": [{"start": "2026-07-31T10:00:00"}],
            "bgg": {"bayesaverage": 7.5},
        },
        {
            "key": "b",
            "event_type_label": "RPG",
            "sessions": [{"start": "2026-07-30T09:00:00"}],
            "bgg": None,
        },
        {
            "key": "c",
            "event_type_label": "Board Game",
            "sessions": [{"start": "2026-07-30T15:00:00"}],
            "bgg": {"bayesaverage": 8.2},
        },
        {
            "key": "d",
            "event_type_label": "Seminar",
            "sessions": [{"start": "2026-08-01T12:00:00"}],
            "bgg": None,
        },
    ]


def _sorted_keys(page, groups, state):
    js = f"""
    const groups = {json.dumps(groups)};
    const cmp = S.compareGroups({json.dumps(state)});
    const sorted = [...groups].sort(cmp);
    return JSON.stringify(sorted.map(g => g.key));
    """
    return json.loads(_eval(page, js))


def test_sort_by_start_asc(page):
    keys = _sorted_keys(page, _fixture_groups(), {"key": "start", "dir": "asc"})
    assert keys == ["b", "c", "a", "d"]


def test_sort_by_start_desc(page):
    keys = _sorted_keys(page, _fixture_groups(), {"key": "start", "dir": "desc"})
    assert keys == ["d", "a", "c", "b"]


def test_sort_by_type_uses_label_not_code(page):
    """Regression: sort by 'type' must compare event_type_label, not event_type."""
    groups = [
        {"key": "x", "event_type_label": "Zoo (last alphabetically)",
         "event_type": "AAA", "sessions": [{"start": "2026-07-30T09:00:00"}], "bgg": None},
        {"key": "y", "event_type_label": "Acrobatics (first alphabetically)",
         "event_type": "ZZZ", "sessions": [{"start": "2026-07-30T09:00:00"}], "bgg": None},
    ]
    keys = _sorted_keys(page, groups, {"key": "type", "dir": "asc"})
    assert keys == ["y", "x"]


def test_sort_by_type_tiebreak_is_start_asc(page):
    """Two groups with the same label fall back to start-time ascending."""
    keys = _sorted_keys(page, _fixture_groups(), {"key": "type", "dir": "asc"})
    # Board Game appears twice (a, c). c starts earlier than a. RPG (b), Seminar (d).
    assert keys == ["c", "a", "b", "d"]


def test_sort_by_bgg_desc_nulls_last(page):
    keys = _sorted_keys(page, _fixture_groups(), {"key": "bgg", "dir": "desc"})
    # c=8.2, a=7.5, then null-bgg rows by start-asc tiebreak: b (07-30) before d (08-01).
    assert keys == ["c", "a", "b", "d"]


def test_sort_by_bgg_asc_nulls_still_last(page):
    """Per spec Q3: nulls always go to the bottom regardless of direction."""
    keys = _sorted_keys(page, _fixture_groups(), {"key": "bgg", "dir": "asc"})
    # a=7.5, c=8.2, then nulls: b, d.
    assert keys == ["a", "c", "b", "d"]
