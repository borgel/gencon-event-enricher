"""One-off generator for tests/fixtures/tiny_gencon.xlsx.

Keeps the binary fixture reproducible from a readable script. Re-run only when
fixture rows change.

Usage: uv run python tests/fixtures/_make_tiny_gencon.py
"""
from pathlib import Path
from openpyxl import Workbook

HEADERS = [
    "Game ID", "Group", "Title", "Short Description", "Long Description",
    "Event Type", "Game System", "Rules Edition", "Minimum Players",
    "Maximum Players", "Age Required", "Experience Required",
    "Materials Required", "Materials Required Details",
    "Start Date & Time", "Duration", "End Date & Time", "GM Names",
    "Website", "Email", "Tournament?", "Round Number", "Total Rounds",
    "Minimum Play Time", "Attendee Registration?", "Cost $",
    "Location", "Room Name", "Table Number", "Special Category",
    "Tickets Available", "Last Modified",
]

ROWS = [
    # Session 1: Wingspan: Asia tournament round 1
    ["BGM26ND000001", "Thursday Games", "Wingspan: Asia Tournament", "Compete!", "Long desc here.",
     "BGM - Board Game", "Wingspan: Asia", "1st", 1, 4, "Teen (13+)", "Some",
     "No", "", "07/30/2026 09:00 AM", 4, "07/30/2026 01:00 PM", "Jane Doe",
     "", "", "Yes", 1, 3, 240, "Yes", 8.0, "ICC", "Hall A", "27", "none", 8, 46104.5],
    # Session 2: Wingspan: Asia tournament round 2 — same event group
    ["BGM26ND000002", "Thursday Games", "Wingspan: Asia Tournament", "Compete!", "Long desc here.",
     "BGM - Board Game", "Wingspan: Asia", "1st", 1, 4, "Teen (13+)", "Some",
     "No", "", "07/30/2026 02:00 PM", 4, "07/30/2026 06:00 PM", "Jane Doe",
     "", "", "Yes", 2, 3, 240, "Yes", 8.0, "ICC", "Hall A", "27", "none", 4, 46104.5],
    # Session 3: Brass: Birmingham learn & play (single session) — exact match
    ["BGM26ND000003", "Friday Games", "Brass Birmingham — Learn & Play", "Learn this!", "Description.",
     "BGM - Board Game", "Brass: Birmingham", "1st", 2, 4, "Teen (13+)", "None",
     "No", "", "07/31/2026 10:00 AM", 2, "07/31/2026 12:00 PM", "John Smith",
     "", "", "No", 1, 1, 120, "Yes", 0.0, "ICC", "Hall A", "10", "none", 0, 46105.5],
    # Session 4: Hellfire RPG — should NOT match BGG (Marvel Super Heroes RPG isn't in tiny CSV)
    ["RPG26ND000004", "Sunday Night Games", "Hellfire in the Heartland, 1938",
     "RPG.", "Long RPG description.", "RPG - Roleplaying Game",
     "Marvel Super Heroes", "Basic", 3, 8, "Teen (13+)", "None",
     "No", "", "08/02/2026 09:00 AM", 5, "08/02/2026 02:00 PM", "Robert Ogdon",
     "", "", "No", 1, 1, 300, "Yes", 6.0, "Hyatt", "Concept A", "2", "none", 8, 46108.5],
    # Session 5: Cosplay seminar — should be left to the agent (not a board game at all)
    ["SEM26ND000005", "Friday Seminars", "Cosplay 101: Foam & Form",
     "Seminar.", "Seminar description.", "SEM - Seminar",
     "", "", 1, 50, "Everyone (6+)", "None",
     "No", "", "07/31/2026 10:00 AM", 1, "07/31/2026 11:00 AM", "Cos Player",
     "", "", "No", 1, 1, 60, "Yes", 2.0, "ICC", "Room 200", "", "none", 12, 46105.5],
]


def main():
    wb = Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in ROWS:
        ws.append(row)
    out = Path(__file__).parent / "tiny_gencon.xlsx"
    wb.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
