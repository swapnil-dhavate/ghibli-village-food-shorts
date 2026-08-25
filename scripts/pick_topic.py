"""Pick the next topic in rotation without repeating until the whole catalog is exhausted.

Reads data/topic_catalog.json and data/state/used_topics.json, picks the first catalog
entry whose id isn't in used_ids, records it, and writes the state back. When the whole
catalog has been used, the cycle resets (used_ids clears, cycle increments) so the
rotation starts over instead of erroring out.

Replaces pick_dish.py now that the channel covers any general-interest topic, not just
food -- data/dish_catalog.json and data/state/used_dishes.json are left in place as a
historical record of the videos already published under the old food-only format.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "topic_catalog.json"
STATE_PATH = ROOT / "data" / "state" / "used_topics.json"


def pick_next_topic():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["topics"]
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))

    used_ids = set(state.get("used_ids", []))
    remaining = [t for t in catalog if t["id"] not in used_ids]

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
            "title": chosen["title"],
            "cycle": state["cycle"],
            "picked_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return chosen


if __name__ == "__main__":
    topic = pick_next_topic()
    json.dump(topic, sys.stdout, indent=2)
