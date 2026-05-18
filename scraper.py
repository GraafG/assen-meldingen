"""Scrape the public Assen meldingen API and save a daily GeoJSON snapshot.

Usage:
    python scraper.py              # Fetch today's data
    python scraper.py --backfill   # Fetch and save (API only returns current window)
"""

import json
import hashlib
from datetime import date, timezone, datetime
from pathlib import Path

import requests

API_GEOGRAPHY = (
    "https://api.meldingen.assen.nl/signals/v1/public/signals/geography"
    "?bbox=6.483948,52.932515,6.632644,53.061921"
)
API_CATEGORIES = "https://api.meldingen.assen.nl/signals/v1/public/terms/categories"

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ICONS_DIR = BASE_DIR / "public" / "icons"
CATEGORIES_FILE = BASE_DIR / "categories.json"

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
    """Fetch all public meldingen as GeoJSON from the API."""
    resp = requests.get(API_GEOGRAPHY, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize_features(geojson):
    """Add stable IDs and flatten category info for simpler consumption."""
    features = []
    seen = set()
    for feat in geojson.get("features", []):
        fid = feature_id(feat)
        if fid in seen:
            continue
        seen.add(fid)
        cat = feat["properties"]["category"]
        features.append({
            "id": fid,
            "lng": feat["geometry"]["coordinates"][0],
            "lat": feat["geometry"]["coordinates"][1],
            "category": cat["parent"]["name"],
            "category_slug": cat["parent"]["slug"],
            "subcategory": cat["name"],
            "subcategory_slug": cat["slug"],
            "created_at": feat["properties"]["created_at"],
        })
    return features


def save_snapshot(features, date_str=None):
    """Save features to data/YYYY/MM/DD.json datalake layout."""
    if date_str is None:
        date_str = date.today().isoformat()

    year, month, day = date_str.split("-")
    out_dir = DATA_DIR / year / month
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{day}.json"

    # Merge with existing snapshot if present (API window may overlap)
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

    # Update manifest
    update_manifest(date_str)

    print(f"Saved {len(existing)} meldingen to {out_file} ({new_count} new)")
    return out_file


def update_manifest(date_str):
    """Add date to data/index.json manifest (newest first, deduplicated)."""
    manifest = DATA_DIR / "index.json"
    dates = []
    if manifest.exists():
        dates = json.loads(manifest.read_text(encoding="utf-8"))
    if date_str not in dates:
        dates.append(date_str)
    dates.sort(reverse=True)
    manifest.write_text(json.dumps(dates, ensure_ascii=False), encoding="utf-8")


def fetch_and_save_categories():
    """Fetch category tree and download SVG icons."""
    resp = requests.get(API_CATEGORIES, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    categories = {}
    for parent in data.get("results", []):
        parent_slug = parent["slug"]
        parent_icon_url = parent.get("_links", {}).get("sia:icon", {}).get("href")

        # Download parent icon
        if parent_icon_url:
            download_icon(parent_icon_url, parent_slug, parent_slug)

        for sub in parent.get("sub_categories", []):
            slug = sub["slug"]
            icon_url = sub.get("_links", {}).get("sia:icon", {}).get("href")
            icon_path = None
            if icon_url:
                icon_path = download_icon(icon_url, parent_slug, slug)

            categories[slug] = {
                "name": sub["name"],
                "parent": parent["name"],
                "parent_slug": parent_slug,
                "description": sub.get("description", ""),
                "icon_path": icon_path,
            }

    CATEGORIES_FILE.write_text(
        json.dumps(categories, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved {len(categories)} subcategories to {CATEGORIES_FILE}")
    return categories


def download_icon(url, parent_slug, slug):
    """Download an SVG icon and return relative path."""
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


def main():
    import sys

    print("Fetching meldingen from Assen API...")
    geojson = fetch_geography()
    features = normalize_features(geojson)
    print(f"Fetched {len(features)} unique meldingen")

    save_snapshot(features)

    # Refresh categories + icons periodically
    if not CATEGORIES_FILE.exists() or "--refresh-categories" in sys.argv:
        print("Fetching categories and icons...")
        fetch_and_save_categories()
    elif "--categories" in sys.argv:
        fetch_and_save_categories()

    print("Done!")


if __name__ == "__main__":
    main()
