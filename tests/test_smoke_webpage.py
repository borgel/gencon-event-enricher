"""End-to-end webpage smoke test using Playwright + a tiny on-disk events.json."""
import json
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent.parent

TINY_BLOB = {
    "groups": [
        {
            "key": "BGM-wingspan-asia-tournament-abc",
            "title": "Wingspan: Asia Tournament",
            "event_type": "BGM",
            "event_type_label": "BGM - Board Game",
            "game_system": "Wingspan: Asia",
            "short_description": "Compete!",
            "long_description": "Long Wingspan description.",
            "tournament": True, "min_players": 1, "max_players": 4,
            "age_required": "Teen (13+)", "experience_required": "Some",
            "duration_minutes": 240, "cost": 8.0,
            "bgg": {
                "id": 266192, "name": "Wingspan: Asia", "year_published": 2022,
                "rank": 142, "bayesaverage": 7.84, "average": 8.05,
                "users_rated": 14238, "is_expansion": True,
                "category_ranks": {"strategygames": 44}, "match_source": "exact",
            },
            "sessions": [{
                "gencon_id": "BGM26ND000001",
                "start": "2026-07-30T09:00:00", "end": "2026-07-30T13:00:00",
                "duration_minutes": 240, "location": "ICC", "room": "Hall A",
                "table": "27", "gm": "Jane Doe", "tickets_available": 8,
                "round_number": 1, "total_rounds": 3, "cost_override": 8.0,
            }],
        },
        {
            "key": "SEM-cosplay-101-abc",
            "title": "Cosplay 101", "event_type": "SEM",
            "event_type_label": "SEM - Seminar", "game_system": "",
            "short_description": "Foam.", "long_description": "Foam armor.",
            "tournament": False, "min_players": 1, "max_players": 50,
            "age_required": "Everyone (6+)", "experience_required": "None",
            "duration_minutes": 60, "cost": 2.0,
            "sessions": [{
                "gencon_id": "SEM26ND000005",
                "start": "2026-07-31T10:00:00", "end": "2026-07-31T11:00:00",
                "duration_minutes": 60, "location": "ICC", "room": "Room 200",
                "table": "", "gm": "Cos Player", "tickets_available": 12,
                "round_number": 1, "total_rounds": 1, "cost_override": 2.0,
            }],
        },
    ],
    "meta": {
        "generated_at": "2026-05-04T00:00:00Z",
        "gencon_source": "x.xlsx", "bgg_source": "y.csv",
        "stats": {"groups": 2, "sessions": 2, "matched": 1, "unmatched": 1},
    },
}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    docs_root = ROOT / "docs"
    data_dir = docs_root / "data"
    data_dir.mkdir(exist_ok=True)
    events_path = data_dir / "events.json"
    backup = events_path.read_text() if events_path.exists() else None
    events_path.write_text(json.dumps(TINY_BLOB))

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(docs_root), **k)
        def log_message(self, *_): pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        httpd.shutdown()
        if backup is not None:
            events_path.write_text(backup)


def test_page_loads_and_lists_groups(server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(server, wait_until="networkidle")
        page.wait_for_selector(".row")
        rows = page.query_selector_all(".row")
        assert len(rows) >= 2

        # Type filter to BGM only -> 1 row
        page.click('span.chip[data-val="BGM"]')
        page.wait_for_function("document.querySelectorAll('.row').length === 1")

        # Clicking a row opens the detail panel
        page.click(".row")
        panel = page.query_selector("#detail-panel")
        assert "hidden" not in panel.get_attribute("class").split()
        assert "Wingspan: Asia" in page.inner_text("#detail-panel")
        browser.close()
