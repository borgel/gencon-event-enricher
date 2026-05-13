"""Drive docs/app/collections.js inside a real browser via Playwright.

Tests the collections CRUD + color assignment + my-name memory.
"""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

HARNESS_HTML = """\
<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
import * as C from '/docs/app/collections.js';
window.C = C;
</script>
</body></html>
"""


def _serve(route):
    url = route.request.url
    if "/docs/app/collections.js" in url:
        body = (ROOT / "docs" / "app" / "collections.js").read_text()
        route.fulfill(body=body, content_type="application/javascript")
    elif "/harness" in url:
        route.fulfill(body=HARNESS_HTML, content_type="text/html")
    else:
        route.fulfill(status=404, body="not found")


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()
        ctx.route("**/*", lambda route: _serve(route))
        pg = ctx.new_page()
        pg.goto("http://localhost/harness", wait_until="networkidle")
        pg.wait_for_function("typeof window.C !== 'undefined'")
        pg.evaluate("localStorage.clear()")
        yield pg
        browser.close()


def _eval(page, code: str):
    return page.evaluate(f"(() => {{ {code} }})()")


def test_empty_storage(page):
    assert _eval(page, "return C.listCollections().length") == 0
    assert _eval(page, "return C.getMyName()") == ""


def test_create_and_list(page):
    js = """
    const c = C.createCollection({
      name: 'Alice', saved: ['s1','s2'], purchased: ['s3'],
      originalExportName: 'Alice',
    });
    const all = C.listCollections();
    return JSON.stringify({
      id: c.id, name: c.name, savedLen: c.saved.length,
      purchasedLen: c.purchased.length, allLen: all.length,
      color: c.color, originalExportName: c.originalExportName,
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["name"] == "Alice"
    assert obj["savedLen"] == 2
    assert obj["purchasedLen"] == 1
    assert obj["allLen"] == 1
    assert obj["color"] == "#e76f51"  # first palette slot
    assert obj["id"].startswith("c-")
    assert obj["originalExportName"] == "Alice"


def test_colors_unique_in_palette_order(page):
    js = """
    const a = C.createCollection({name:'A',saved:[],purchased:[],originalExportName:'A'});
    const b = C.createCollection({name:'B',saved:[],purchased:[],originalExportName:'B'});
    const c = C.createCollection({name:'C',saved:[],purchased:[],originalExportName:'C'});
    return JSON.stringify([a.color, b.color, c.color]);
    """
    colors = json.loads(_eval(page, js))
    assert colors == ["#e76f51", "#2a9d8f", "#f4a261"]


def test_delete_frees_slot_for_next(page):
    js = """
    const a = C.createCollection({name:'A',saved:[],purchased:[],originalExportName:'A'});
    const b = C.createCollection({name:'B',saved:[],purchased:[],originalExportName:'B'});
    C.deleteCollection(a.id);
    const c = C.createCollection({name:'C',saved:[],purchased:[],originalExportName:'C'});
    // B keeps its #2a9d8f. C reuses A's freed #e76f51 (first unused).
    return JSON.stringify({bColor: b.color, cColor: c.color});
    """
    obj = json.loads(_eval(page, js))
    assert obj["bColor"] == "#2a9d8f"
    assert obj["cColor"] == "#e76f51"


def test_replace_preserves_id_and_color(page):
    js = """
    const a = C.createCollection({name:'Alice',saved:['s1'],purchased:[],originalExportName:'Alice'});
    const r = C.replaceCollection(a.id, {
      name:'Alice', saved:['s2','s3'], purchased:['s4'], originalExportName:'Alice'
    });
    return JSON.stringify({
      sameId: r.id === a.id,
      sameColor: r.color === a.color,
      newSavedLen: r.saved.length,
      newPurchasedLen: r.purchased.length,
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["sameId"] is True
    assert obj["sameColor"] is True
    assert obj["newSavedLen"] == 2
    assert obj["newPurchasedLen"] == 1


def test_rename_changes_name_keeps_original_export_name(page):
    js = """
    const a = C.createCollection({name:'Alice',saved:[],purchased:[],originalExportName:'Alice'});
    const r = C.renameCollection(a.id, 'Alice K');
    return JSON.stringify({name: r.name, oen: r.originalExportName});
    """
    obj = json.loads(_eval(page, js))
    assert obj["name"] == "Alice K"
    assert obj["oen"] == "Alice"


def test_find_by_name_case_insensitive_matches_name_or_original(page):
    js = """
    const a = C.createCollection({name:'Alice K',saved:[],purchased:[],originalExportName:'Alice'});
    return JSON.stringify({
      byCurrentName: C.findByName('alice k')?.id === a.id,
      byOriginal: C.findByName('ALICE')?.id === a.id,
      nope: C.findByName('Bob') === null,
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj == {"byCurrentName": True, "byOriginal": True, "nope": True}


def test_my_name_round_trip(page):
    js = """
    C.setMyName('Bob');
    const a = C.getMyName();
    C.setMyName('');
    const b = C.getMyName();
    return JSON.stringify({a, b});
    """
    obj = json.loads(_eval(page, js))
    assert obj == {"a": "Bob", "b": ""}


def test_palette_cycles_when_exhausted(page):
    """7th and beyond collections cycle the palette via hash of id."""
    js = """
    const names = ['A','B','C','D','E','F','G','H'];
    const ids = [];
    for (const n of names) {
      const c = C.createCollection({name:n,saved:[],purchased:[],originalExportName:n});
      ids.push(c.color);
    }
    return JSON.stringify(ids);
    """
    colors = json.loads(_eval(page, js))
    # First 6 occupy the palette in order.
    assert colors[:6] == ["#e76f51", "#2a9d8f", "#f4a261", "#9b5de5", "#00bbf9", "#f15bb5"]
    # 7th and 8th must be inside the palette (cycled), not a new color.
    palette = {"#e76f51", "#2a9d8f", "#f4a261", "#9b5de5", "#00bbf9", "#f15bb5"}
    assert colors[6] in palette
    assert colors[7] in palette


def test_invalid_stored_color_is_sanitized_on_read(page):
    """A hand-edited localStorage entry with a non-hex color gets repaired."""
    js = """
    // Seed a collection with a malicious / malformed color directly.
    localStorage.setItem('gencon-enricher.collections.v1', JSON.stringify([{
      id: 'c-bad1', name: 'Tampered', color: 'red; background-image:url(x)',
      saved: [], purchased: [], importedAt: '2026-05-13T00:00:00Z',
      originalExportName: 'Tampered'
    }]));
    // First read sanitizes and rewrites storage.
    const after = C.listCollections();
    const stored = JSON.parse(localStorage.getItem('gencon-enricher.collections.v1'));
    return JSON.stringify({
      readColor: after[0].color,
      storedColor: stored[0].color,
      valid: C.isValidColor(after[0].color),
    });
    """
    obj = json.loads(_eval(page, js))
    assert obj["valid"] is True
    assert obj["readColor"].startswith("#")
    # Sanitization is persisted so subsequent reads are stable.
    assert obj["readColor"] == obj["storedColor"]


def test_valid_color_is_preserved_on_read(page):
    """A correctly-formatted hex color is not mutated."""
    js = """
    localStorage.setItem('gencon-enricher.collections.v1', JSON.stringify([{
      id: 'c-ok', name: 'Fine', color: '#abcdef',
      saved: [], purchased: [], importedAt: '2026-05-13T00:00:00Z',
      originalExportName: 'Fine'
    }]));
    return C.listCollections()[0].color;
    """
    assert _eval(page, js) == "#abcdef"
