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


def _fixture_groups():
    return [
        {
            "key": "G1", "title": "Wingspan",
            "sessions": [
                {"gencon_id": "BGM26ND000001", "start": "2026-07-30T09:00:00", "end": "2026-07-30T13:00:00"},
            ],
        },
        {
            "key": "G2", "title": "Pathfinder Society",
            "sessions": [
                {"gencon_id": "RPG26ND000010", "start": "2026-08-01T10:00:00", "end": "2026-08-01T13:00:00"},
            ],
        },
        {
            "key": "G3", "title": "Catan Tournament",
            "sessions": [
                {"gencon_id": "BGM26ND000020", "start": "2026-08-01T11:00:00", "end": "2026-08-01T13:00:00"},
            ],
        },
    ]


def test_group_overlap_map_empty_when_nothing_saved(page):
    js = f"""
    const groups = {json.dumps(_fixture_groups())};
    const out = C.groupOverlapMap(groups, new Set(), new Set());
    return JSON.stringify({{
      conflictedGroups: [...out.conflictedGroups],
      perSessionSize: out.perSession.size,
    }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["conflictedGroups"] == []
    assert obj["perSessionSize"] == 0


def test_group_overlap_map_saved_pair_conflicts(page):
    """G2 (Pathfinder 10–13) and G3 (Catan 11–13) on Aug 1 → both conflict."""
    js = f"""
    const groups = {json.dumps(_fixture_groups())};
    const saved = new Set(['RPG26ND000010', 'BGM26ND000020']);
    const out = C.groupOverlapMap(groups, saved, new Set());
    const ps = {{}};
    for (const [sid, info] of out.perSession) {{
      ps[sid] = {{
        fits: info.fits,
        conflictsWith: info.conflictsWith.map(c => c.title).sort(),
      }};
    }}
    return JSON.stringify({{
      conflictedGroups: [...out.conflictedGroups].sort(),
      perSession: ps,
    }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["conflictedGroups"] == ["G2", "G3"]
    assert obj["perSession"]["RPG26ND000010"]["fits"] is False
    assert obj["perSession"]["RPG26ND000010"]["conflictsWith"] == ["Catan Tournament"]
    assert obj["perSession"]["BGM26ND000020"]["fits"] is False
    assert obj["perSession"]["BGM26ND000020"]["conflictsWith"] == ["Pathfinder Society"]


def test_group_overlap_map_purchased_counts(page):
    """Purchased sessions count for conflict purposes alongside saved."""
    js = f"""
    const groups = {json.dumps(_fixture_groups())};
    // RPG saved, BGM purchased — they still conflict.
    const out = C.groupOverlapMap(groups, new Set(['RPG26ND000010']), new Set(['BGM26ND000020']));
    return JSON.stringify({{ conflictedGroups: [...out.conflictedGroups].sort() }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["conflictedGroups"] == ["G2", "G3"]


def test_group_overlap_map_saved_session_with_unsaved_sibling(page):
    """If a group has multiple sessions but only one is saved, the unsaved
    sibling is not listed as a conflict (only saved/purchased participate)."""
    js = """
    const groups = [
      {
        key: 'G1', title: 'Wingspan',
        sessions: [
          { gencon_id: 'A', start: '2026-07-30T09:00:00', end: '2026-07-30T11:00:00' },
          { gencon_id: 'B', start: '2026-07-30T10:00:00', end: '2026-07-30T12:00:00' },
        ],
      },
    ];
    // Save only A. B is in the same group but unsaved → no conflict reported.
    const out = C.groupOverlapMap(groups, new Set(['A']), new Set());
    return JSON.stringify({ conflictedGroups: [...out.conflictedGroups] });
    """
    obj = json.loads(_eval(page, js))
    assert obj["conflictedGroups"] == []


def test_group_overlap_map_session_fits_when_no_conflict(page):
    js = f"""
    const groups = {json.dumps(_fixture_groups())};
    // Save only G1 — no conflict with anything else.
    const out = C.groupOverlapMap(groups, new Set(['BGM26ND000001']), new Set());
    const info = out.perSession.get('BGM26ND000001');
    return JSON.stringify({{ fits: info.fits, conflictsWith: info.conflictsWith }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["fits"] is True
    assert obj["conflictsWith"] == []
