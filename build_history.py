"""Build aggregated history from daily meldingen snapshots.

Reads data/YYYY/MM/DD.json files and produces data/history.json with:
- Per-category daily counts
- Total counts and trends
- Top locations (repeat meldingen at same coordinates)
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"


def snapshot_path(date_str):
    year, month, day = date_str.split("-")
    return DATA_DIR / year / month / f"{day}.json"


def build_history():
    manifest = DATA_DIR / "index.json"
    if not manifest.exists():
        print("No data/index.json — nothing to do.")
        return

    dates = sorted(json.loads(manifest.read_text(encoding="utf-8")))

    # Track all unique meldingen across all snapshots
    all_meldingen = {}  # id → melding dict
    daily_counts = {}  # date → {category_slug: count}
    category_totals = Counter()
    subcategory_totals = Counter()
    location_counts = Counter()  # "lat,lng" → count

    for date_str in dates:
        path = snapshot_path(date_str)
        if not path.exists():
            continue

        meldingen = json.loads(path.read_text(encoding="utf-8"))
        day_cats = Counter()

        for m in meldingen:
            mid = m["id"]
            if mid not in all_meldingen:
                all_meldingen[mid] = m
                category_totals[m["category_slug"]] += 1
                subcategory_totals[m["subcategory_slug"]] += 1
                loc_key = f"{m['lat']:.5f},{m['lng']:.5f}"
                location_counts[loc_key] += 1

            day_cats[m["category_slug"]] += 1

        daily_counts[date_str] = dict(day_cats)

    # Build category summary
    categories_file = BASE_DIR / "categories.json"
    cat_meta = {}
    if categories_file.exists():
        cat_meta = json.loads(categories_file.read_text(encoding="utf-8"))

    category_summary = {}
    for slug, count in category_totals.most_common():
        meta = cat_meta.get(slug, {})
        parent_slug = meta.get("parent_slug", slug)
        if parent_slug not in category_summary:
            category_summary[parent_slug] = {
                "name": meta.get("parent", parent_slug),
                "total": 0,
                "subcategories": {},
            }
        category_summary[parent_slug]["total"] += count
        category_summary[parent_slug]["subcategories"][slug] = {
            "name": meta.get("name", slug),
            "count": count,
        }

    # Top repeat locations
    hotspots = []
    for loc_key, count in location_counts.most_common(50):
        if count < 2:
            break
        lat, lng = loc_key.split(",")
        hotspots.append({"lat": float(lat), "lng": float(lng), "count": count})

    history = {
        "total_meldingen": len(all_meldingen),
        "total_dates": len(dates),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "daily_counts": daily_counts,
        "categories": category_summary,
        "hotspots": hotspots,
    }

    out = DATA_DIR / "history.json"
    out.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    print(f"Built history: {len(all_meldingen)} meldingen across {len(dates)} dates → {out}")


if __name__ == "__main__":
    build_history()
