"""Scrape the public Assen meldingen API and save a daily GeoJSON snapshot.

Usage:
    python scraper.py                    # Fetch today's data
    python scraper.py --categories       # Refresh categories + icons
    python scraper.py --refresh-areas    # Re-fetch area boundaries
"""

import json
import hashlib
from datetime import date, datetime
from pathlib import Path

import requests

API_GEOGRAPHY = (
    "https://api.meldingen.assen.nl/signals/v1/public/signals/geography"
    "?bbox=6.483948,52.932515,6.632644,53.061921"
)
API_CATEGORIES = "https://api.meldingen.assen.nl/signals/v1/public/terms/categories"
API_AREAS = "https://api.meldingen.assen.nl/signals/v1/public/areas/"

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ICONS_DIR = BASE_DIR / "public" / "icons"
CATEGORIES_FILE = BASE_DIR / "categories.json"
AREAS_FILE = BASE_DIR / "areas.json"
RESOLVED_FILE = DATA_DIR / "resolved.json"
OPEN_IDS_FILE = DATA_DIR / "open_ids.json"

HEADERS = {
    "User-Agent": "AssenMeldingenBot/1.0 (https://github.com/GraafG/assen-meldingen)"
}


def feature_id(feat):
    """Generate a stable ID from coordinates + created_at + category slug."""
    coords = feat["geometry"]["coordinates"]
    cat = feat["properties"]["category"]
    key = f"{coords[0]:.8f},{coords[1]:.8f},{cat['slug']},{feat['properties']['created_at']}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def fetch_geography():
    resp = requests.get(API_GEOGRAPHY, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Area / neighbourhood enrichment
# ---------------------------------------------------------------------------

def fetch_and_save_areas():
    """Fetch all named wijken and districts with bounding boxes; save to areas.json."""
    all_areas = []
    url = API_AREAS
    while url:
        resp = requests.get(url, params={"page_size": 200}, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_areas.extend(data["results"])
        next_link = data["_links"].get("next") or {}
        url = next_link.get("href")

    # Keep only wijken (21) and districts (10) — skip 124 tiny buurten
    areas = [a for a in all_areas if a["type"]["code"] in ("gm0106-wijk", "district")]

    # Sort by bbox area ascending so the most specific (smallest) match wins first
    def bbox_area(a):
        b = a["bbox"]
        return (b[2] - b[0]) * (b[3] - b[1])

    areas.sort(key=bbox_area)
    AREAS_FILE.write_text(json.dumps(areas, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(areas)} areas to {AREAS_FILE}")
    return areas


def load_areas():
    if not AREAS_FILE.exists():
        return []
    return json.loads(AREAS_FILE.read_text(encoding="utf-8"))


def find_wijk(lat, lng, areas):
    """Return the most specific area name containing (lat, lng) via bbox lookup."""
    for area in areas:  # sorted smallest-bbox first
        b = area["bbox"]  # [min_lng, min_lat, max_lng, max_lat]
        if b[0] <= lng <= b[2] and b[1] <= lat <= b[3]:
            return area["name"]
    return None


def backfill_wijk(areas):
    """Add missing wijk field to all existing snapshot files."""
    manifest = DATA_DIR / "index.json"
    if not manifest.exists():
        return
    dates = json.loads(manifest.read_text(encoding="utf-8"))
    updated_files = updated_count = 0
    for date_str in dates:
        year, month, day = date_str.split("-")
        path = DATA_DIR / year / month / f"{day}.json"
        if not path.exists():
            continue
        meldingen = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for m in meldingen:
            if "wijk" not in m:
                m["wijk"] = find_wijk(m["lat"], m["lng"], areas)
                changed = True
                updated_count += 1
        if changed:
            path.write_text(json.dumps(meldingen, ensure_ascii=False), encoding="utf-8")
            updated_files += 1
    print(f"Backfilled wijk in {updated_count} meldingen across {updated_files} files")


# ---------------------------------------------------------------------------
# Feature normalisation
# ---------------------------------------------------------------------------

def normalize_features(geojson, areas=None):
    """Add stable IDs, flatten category info, and enrich with neighbourhood."""
    features = []
    seen = set()
    for feat in geojson.get("features", []):
        fid = feature_id(feat)
        if fid in seen:
            continue
        seen.add(fid)
        cat = feat["properties"]["category"]
        lng = feat["geometry"]["coordinates"][0]
        lat = feat["geometry"]["coordinates"][1]
        features.append({
            "id": fid,
            "lng": lng,
            "lat": lat,
            "category": cat["parent"]["name"],
            "category_slug": cat["parent"]["slug"],
            "subcategory": cat["name"],
            "subcategory_slug": cat["slug"],
            "created_at": feat["properties"]["created_at"],
            "wijk": find_wijk(lat, lng, areas) if areas else None,
        })
    return features


# ---------------------------------------------------------------------------
# Resolution tracking
# ---------------------------------------------------------------------------

def track_resolutions(current_features, scrape_date=None):
    """
    Compare today's meldingen against previously known open set.
    Meldingen that vanished from the API are marked resolved.
    Updates data/open_ids.json and appends to data/resolved.json.
    """
    if scrape_date is None:
        scrape_date = date.today().isoformat()

    current = {f["id"]: f for f in current_features}

    open_ids = {}
    if OPEN_IDS_FILE.exists():
        open_ids = json.loads(OPEN_IDS_FILE.read_text(encoding="utf-8"))

    resolved = []
    if RESOLVED_FILE.exists():
        resolved = json.loads(RESOLVED_FILE.read_text(encoding="utf-8"))
    resolved_ids = {r["id"] for r in resolved}

    scrape_dt = datetime.fromisoformat(scrape_date + "T00:00:00+00:00")
    newly_resolved = []
    for rid, melding in open_ids.items():
        if rid not in current and rid not in resolved_ids:
            created = datetime.fromisoformat(melding["created_at"].replace("Z", "+00:00"))
            days_open = max(0, (scrape_dt - created).days)
            newly_resolved.append({**melding, "resolved_date": scrape_date, "days_open": days_open})

    if newly_resolved:
        resolved.extend(newly_resolved)
        RESOLVED_FILE.write_text(json.dumps(resolved, ensure_ascii=False), encoding="utf-8")
        print(f"Marked {len(newly_resolved)} meldingen as resolved")
    else:
        print("No newly resolved meldingen")

    OPEN_IDS_FILE.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    return newly_resolved


# ---------------------------------------------------------------------------
# Snapshot persistence
# ---------------------------------------------------------------------------

def save_snapshot(features, date_str=None):
    if date_str is None:
        date_str = date.today().isoformat()

    year, month, day = date_str.split("-")
    out_dir = DATA_DIR / year / month
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{day}.json"

    existing = []
    if out_file.exists():
        existing = json.loads(out_file.read_text(encoding="utf-8"))
    existing_ids = {f["id"] for f in existing}

    new_count = 0
    for feat in features:
        if feat["id"] not in existing_ids:
            existing.append(feat)
            existing_ids.add(feat["id"])
            new_count += 1

    existing.sort(key=lambda f: f["created_at"], reverse=True)
    out_file.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    update_manifest(date_str)
    print(f"Saved {len(existing)} meldingen to {out_file} ({new_count} new)")
    return out_file


def update_manifest(date_str):
    manifest = DATA_DIR / "index.json"
    dates = []
    if manifest.exists():
        dates = json.loads(manifest.read_text(encoding="utf-8"))
    if date_str not in dates:
        dates.append(date_str)
    dates.sort(reverse=True)
    manifest.write_text(json.dumps(dates, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Categories + icons
# ---------------------------------------------------------------------------

def fetch_and_save_categories():
    """Fetch full category tree (with handling_message) and download SVG icons."""
    resp = requests.get(API_CATEGORIES, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    categories = {}
    for parent in data.get("results", []):
        parent_slug = parent["slug"]
        parent_icon_url = parent.get("_links", {}).get("sia:icon", {}).get("href")
        if parent_icon_url:
            download_icon(parent_icon_url, parent_slug, parent_slug)

        for sub in parent.get("sub_categories", []):
            slug = sub["slug"]
            icon_url = sub.get("_links", {}).get("sia:icon", {}).get("href")
            icon_path = download_icon(icon_url, parent_slug, slug) if icon_url else None
            categories[slug] = {
                "name": sub["name"],
                "parent": parent["name"],
                "parent_slug": parent_slug,
                "description": sub.get("description", ""),
                "handling_message": sub.get("handling_message", ""),
                "icon_path": icon_path,
            }

    CATEGORIES_FILE.write_text(json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(categories)} subcategories to {CATEGORIES_FILE}")
    return categories


def download_icon(url, parent_slug, slug):
    out_dir = ICONS_DIR / parent_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{slug}.svg"
    if out_file.exists():
        return f"/icons/{parent_slug}/{slug}.svg"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        out_file.write_bytes(resp.content)
    except Exception as e:
        print(f"  ⚠️ Failed to download icon {slug}: {e}")
        return None
    return f"/icons/{parent_slug}/{slug}.svg"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import sys

    # Load (or fetch) area boundaries for neighbourhood enrichment
    had_areas = AREAS_FILE.exists()
    areas = load_areas()
    if not areas or "--refresh-areas" in sys.argv:
        print("Fetching area boundaries...")
        areas = fetch_and_save_areas()
        if not had_areas:
            backfill_wijk(areas)

    print("Fetching meldingen from Assen API...")
    geojson = fetch_geography()
    features = normalize_features(geojson, areas=areas)
    print(f"Fetched {len(features)} unique meldingen")

    track_resolutions(features)
    save_snapshot(features)

    if not CATEGORIES_FILE.exists() or "--refresh-categories" in sys.argv:
        print("Fetching categories and icons...")
        fetch_and_save_categories()
    elif "--categories" in sys.argv:
        fetch_and_save_categories()

    print("Done!")


if __name__ == "__main__":
    main()
