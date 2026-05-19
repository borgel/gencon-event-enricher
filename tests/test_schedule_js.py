"""Drive docs/app/schedule.js inside a real browser via Playwright.

Mirrors the harness pattern used in test_filters_js.py / test_sort_js.py.
"""
import json
import re
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


def test_export_includes_name_metadata_when_provided(page):
    """exportSchedule({name:'Alice', ...}) puts '# name=Alice' as line 1."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const saved = new Set(['BGM26ND313243']);
    const purchased = new Set();
    return S.exportSchedule(groups, saved, purchased, {{name: 'Alice'}});
    """
    csv = _eval(page, js)
    lines = csv.strip().split("\n")
    assert lines[0] == "# name=Alice"
    assert lines[1] == "event_id,gencon_id,title,when,saved,purchased"


def test_export_omits_metadata_when_name_empty(page):
    """No metadata row when name is empty / not provided."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const saved = new Set(['BGM26ND313243']);
    return S.exportSchedule(groups, saved, new Set(), {{name: ''}});
    """
    csv = _eval(page, js)
    lines = csv.strip().split("\n")
    assert lines[0] == "event_id,gencon_id,title,when,saved,purchased"


def test_import_parses_name_metadata(page):
    """parseScheduleCSV returns the imported name from a '# name=' row."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv =
      '# name=Bob\\n' +
      'event_id,gencon_id,title,when,saved,purchased\\n' +
      '313243,BGM26ND313243,Foo,2026-07-31T19:00,1,0\\n';
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{
      name: result.name, saved: [...result.saved], matched: result.matched,
    }});
    """
    obj = json.loads(_eval(page, js))
    assert obj["name"] == "Bob"
    assert obj["saved"] == ["BGM26ND313243"]
    assert obj["matched"] == 1


def test_import_without_metadata_still_works(page):
    """Backwards-compat: name is empty string when no metadata row exists."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv =
      'event_id,gencon_id,title,when,saved,purchased\\n' +
      '313243,BGM26ND313243,Foo,2026-07-31T19:00,1,0\\n';
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{name: result.name, matched: result.matched}});
    """
    obj = json.loads(_eval(page, js))
    assert obj["name"] == ""
    assert obj["matched"] == 1


def test_import_ignores_unknown_metadata(page):
    """Future-proofing: extra metadata keys are ignored, not errors."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv =
      '# exporter_version=2\\n' +
      '# name=Carol\\n' +
      '# unknown_key=nonsense\\n' +
      'event_id,gencon_id,title,when,saved,purchased\\n' +
      '313243,BGM26ND313243,Foo,2026-07-31T19:00,1,0\\n';
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{name: result.name, matched: result.matched}});
    """
    obj = json.loads(_eval(page, js))
    assert obj["name"] == "Carol"
    assert obj["matched"] == 1


def test_roundtrip_preserves_name(page):
    """Export with name=Dave, import it back → result.name === 'Dave'."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv = S.exportSchedule(groups, new Set(['BGM26ND313243']), new Set(), {{name: 'Dave'}});
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{name: result.name}});
    """
    obj = json.loads(_eval(page, js))
    assert obj["name"] == "Dave"


def test_roundtrip_name_with_comma_survives(page):
    """A collection name containing a comma must round-trip cleanly."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv = S.exportSchedule(groups, new Set(['BGM26ND313243']), new Set(), {{name: 'Smith, Alice'}});
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{name: result.name, matched: result.matched}});
    """
    obj = json.loads(_eval(page, js))
    assert obj["name"] == "Smith, Alice"
    assert obj["matched"] == 1


def test_export_strips_newlines_from_name(page):
    """An accidental newline in a name must not corrupt the file."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv = S.exportSchedule(
      groups, new Set(['BGM26ND313243']), new Set(),
      {{name: 'Alice\\nBob'}}
    );
    const result = S.parseScheduleCSV(csv, groups);
    return JSON.stringify({{
      firstLine: csv.split('\\n')[0],
      name: result.name,
      matched: result.matched,
    }});
    """
    obj = json.loads(_eval(page, js))
    # Newline must be collapsed; metadata stays on one line.
    assert obj["firstLine"] == "# name=Alice Bob"
    assert obj["name"] == "Alice Bob"
    assert obj["matched"] == 1


def test_encode_blob_has_prefix_and_urlsafe_alphabet(page):
    """Encoded blob starts with GENCON1: and only uses [A-Za-z0-9_-]."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv = S.exportSchedule(groups, new Set(['BGM26ND313243']), new Set());
    const blob = await S.encodeBlob(csv);
    return blob;
    """
    blob = page.evaluate(f"(async () => {{ {js} }})()")
    assert blob.startswith("GENCON1:")
    body = blob[len("GENCON1:"):]
    assert re.fullmatch(r"[A-Za-z0-9_-]+", body), f"non-urlsafe chars in {body!r}"


def test_blob_roundtrip_preserves_saved_and_purchased(page):
    """encodeBlob → decodeBlob → parseScheduleCSV yields the original sets."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const saved = new Set(['BGM26ND313243']);
    const purchased = new Set(['RPG26ND400500']);
    const csv = S.exportSchedule(groups, saved, purchased, {{name: 'Alice'}});
    const blob = await S.encodeBlob(csv);
    const recovered = await S.decodeBlob(blob);
    const result = S.parseScheduleCSV(recovered, groups);
    return JSON.stringify({{
      name: result.name,
      saved: [...result.saved].sort(),
      purchased: [...result.purchased].sort(),
      matched: result.matched,
      missed: result.missed,
    }});
    """
    obj = json.loads(page.evaluate(f"(async () => {{ {js} }})()"))
    assert obj["name"] == "Alice"
    assert obj["saved"] == ["BGM26ND313243"]
    assert obj["purchased"] == ["RPG26ND400500"]
    assert obj["matched"] == 2
    assert obj["missed"] == 0


def test_decode_blob_tolerates_surrounding_text(page):
    """A blob embedded in chat-style prose still decodes."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv = S.exportSchedule(groups, new Set(['BGM26ND313243']), new Set());
    const blob = await S.encodeBlob(csv);
    const wrapped = 'hey check this out\\n' + blob + '\\nthanks!';
    const recovered = await S.decodeBlob(wrapped);
    return recovered;
    """
    recovered = page.evaluate(f"(async () => {{ {js} }})()")
    assert recovered is not None
    assert "event_id,gencon_id,title,when,saved,purchased" in recovered


def test_decode_blob_returns_null_for_garbage(page):
    """No GENCON1: token → null (not a throw)."""
    js = "return await S.decodeBlob('hello world, no schedule here');"
    out = page.evaluate(f"(async () => {{ {js} }})()")
    assert out is None


def test_decode_blob_returns_null_for_corrupted_payload(page):
    """A flipped character inside the payload returns null, not a throw."""
    js = f"""
    const groups = {json.dumps(_GROUPS)};
    const csv = S.exportSchedule(groups, new Set(['BGM26ND313243']), new Set());
    const blob = await S.encodeBlob(csv);
    // Flip a char in the middle of the base64 body.
    const head = 'GENCON1:';
    const body = blob.slice(head.length);
    const mid = Math.floor(body.length / 2);
    const flipped = body[mid] === 'A' ? 'B' : 'A';
    const corrupted = head + body.slice(0, mid) + flipped + body.slice(mid + 1);
    return await S.decodeBlob(corrupted);
    """
    out = page.evaluate(f"(async () => {{ {js} }})()")
    assert out is None


def test_encode_blob_stays_compact_for_large_schedule(page):
    """A synthesized 300-session schedule encodes under 8 KB (compression smoke)."""
    js = """
    const groups = [];
    const saved = new Set();
    for (let i = 0; i < 300; i++) {
      const id = 'BGM26ND' + String(500000 + i).padStart(6, '0');
      groups.push({
        key: 'g-' + i,
        title: 'Synthesized Game Title ' + i,
        sessions: [{ gencon_id: id, start: '2026-07-31T10:00:00' }],
      });
      saved.add(id);
    }
    const csv = S.exportSchedule(groups, saved, new Set());
    const blob = await S.encodeBlob(csv);
    return blob.length;
    """
    size = page.evaluate(f"(async () => {{ {js} }})()")
    assert size < 8192, f"blob is {size} bytes; expected < 8 KB"
