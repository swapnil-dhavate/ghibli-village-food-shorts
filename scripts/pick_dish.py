"""Pick the next dish in rotation without repeating until the whole catalog is exhausted.

Reads data/dish_catalog.json and data/state/used_dishes.json, picks the first catalog
entry whose id isn't in used_ids, records it, and writes the state back. When the whole
catalog has been used, the cycle resets (used_ids clears, cycle increments) so the
rotation starts over instead of erroring out.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "dish_catalog.json"
STATE_PATH = ROOT / "data" / "state" / "used_dishes.json"


def pick_next_dish():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["dishes"]
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    used_ids = set(state.get("used_ids", []))
    remaining = [d for d in catalog if d["id"] not in used_ids]

    if not remaining:
        state["cycle"] = state.get("cycle", 1) + 1
        state["used_ids"] = []
        used_ids = set()
        remaining = catalog

    chosen = remaining[0]
    state.setdefault("used_ids", [])
    state["used_ids"].append(chosen["id"])
    state.setdefault("history", []).append(
        {
            "id": chosen["id"],
            "name": chosen["name"],
            "cycle": state["cycle"],
            "picked_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return chosen


if __name__ == "__main__":
    dish = pick_next_dish()
    json.dump(dish, sys.stdout, indent=2)
