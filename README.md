# assen-meldingen

Dagelijks overzicht van openbare ruimte meldingen in Assen — kaart, tabel en trends.

🔗 **Live:** https://graafg.github.io/assen-meldingen/  
📡 **Bron:** [meldingen.assen.nl](https://meldingen.assen.nl/meldingenkaart) (Signalen API)

---

## Wat doet het?

Elke ochtend haalt een GitHub Actions workflow de meest recente openstaande meldingen op via de publieke Signalen API van Assen. Per melding worden de coördinaten, categorie, subcategorie en aanmaakdatum opgeslagen. Adressen worden opgezocht via de PDOK Locatieserver (reverse geocoding). De data wordt weergegeven als een interactieve kaart (Leaflet) met statistieken, trends en een gefilterde tabel — gebouwd als statische site met Astro, gehost via GitHub Pages.

---

## Project structuur

```
assen-meldingen/
├── scraper.py            # Haalt meldingen op, verrijkt met adressen, slaat op per dag
├── build_history.py      # Aggregeert alle dagelijkse snapshots → data/history.json
├── data/
│   ├── index.json        # Lijst van beschikbare datum-snapshots
│   ├── history.json      # Geaggregeerde data voor de frontend
│   ├── open_ids.json     # Huidige open melding-ID's (voor resolutie-tracking)
│   ├── resolved.json     # Meldingen die ooit open waren maar nu gesloten zijn
│   ├── total_counts.json # Dagelijks totaal open meldingen (voor trendgrafiek)
│   ├── address_cache.json# PDOK reverse geocoding cache
│   └── 2026/05/18.json  # Voorbeeld dagelijks snapshot
├── areas.json            # Assen wijken (GeoJSON)
├── categories.json       # Signalen categorieën inclusief afdelingen
├── public/
│   ├── icons/            # SVG iconen per categorie (afkomstig van Amsterdam/signals)
│   └── data/            # Kopie van data/ voor de Astro build
├── src/
│   ├── pages/index.astro # Volledige frontend (kaart, tabel, filters, statistieken)
│   ├── layouts/          # Astro layout
│   └── styles/global.css # Globale stijlen
├── scripts/copy-data.mjs # Kopieert data/ → public/data/ voor de build
└── .github/workflows/
    └── scrape.yml        # CI: scrape → commit data → build → deploy
```

---

## Data pipeline

```
Signalen API (publiek, GeoJSON)
        ↓
  scraper.py
        ├── fetch_geography()     — haalt alle open meldingen op (paginering)
        ├── enrich_addresses()    — PDOK reverse geocoding per coördinaat
        ├── fetch_and_save_areas()— Assen wijkgrenzen
        ├── fetch_and_save_categories() — categorieën + afdelingen
        ├── save_snapshot()       — schrijft data/YYYY/MM/DD.json
        ├── update_resolved()     — vergelijkt IDs met vorige dag
        └── log_total_count()     — logt dagelijks totaal open meldingen
        ↓
  build_history.py
        └── aggregeert snapshots → data/history.json
        ↓
  Astro build (npm run build)
        └── statische site → dist/
        ↓
  GitHub Pages
```

### Publieke API velden

De Signalen API van Assen is een instantie van het open source [Amsterdam/signals](https://github.com/Amsterdam/signals) platform. Het publieke geography endpoint geeft alleen:

| Veld | Beschrijving |
|------|-------------|
| `geometry.coordinates` | `[lng, lat]` coördinaten |
| `properties.category.name` | Subcategorienaam |
| `properties.category.slug` | Subcategorie slug |
| `properties.category.parent.name` | Hoofdcategorienaam |
| `properties.category.parent.slug` | Hoofdcategorie slug |
| `properties.created_at` | Aanmaakdatum |

Signal-ID's zijn bewust niet opgenomen in de publieke API (privacyontwerp). Adressen worden verrijkt via [PDOK Locatieserver](https://api.pdok.nl).

---

## Lokaal draaien

### Vereisten

- Python 3.12+
- Node.js 22+

### Installatie

```bash
git clone https://github.com/GraafG/assen-meldingen.git
cd assen-meldingen

pip install -r requirements.txt
npm install
```

### Data ophalen

```bash
# Nieuwe meldingen scrapen + adressen verrijken
python scraper.py

# Alle adressen opnieuw ophalen (backfill)
python scraper.py --refresh-addresses

# History aggregeren
python build_history.py
```

### Site bouwen en previeuwen

```bash
npm run build    # bouwt naar dist/
npm run dev      # development server op http://localhost:4321
npm run preview  # preview van de build
```

---

## CI/CD

De GitHub Actions workflow (`.github/workflows/scrape.yml`) draait elke dag om **09:30 CET**:

1. **scrape** — voert `scraper.py` + `build_history.py` uit, commit eventuele datawijzigingen
2. **deploy** — checkout van main (met nieuwe data), `npm run build`, deploy naar GitHub Pages

Handmatig triggeren kan via de GitHub Actions UI of:

```bash
gh workflow run scrape.yml
```

---

## Categorieën & kleuren

| Categorie | Kleur |
|-----------|-------|
| Afval | 🟠 Amber |
| Wegen, verkeer & straatmeubilair | 🔵 Blauw |
| Openbaar groen & water | 🟢 Groen |
| Overlast openbare ruimte | 🟣 Violet |
| Overlast dier | 🔴 Rood |
| Schoon | 🩵 Cyaan |
| Civiele constructies | 🟤 Steen |
| Riolering | 🩵 Teal |
| Overig | ⬜ Slate |

---

## Iconen

De SVG-iconen in `public/icons/` zijn afkomstig van [Amsterdam/signals](https://github.com/Amsterdam/signals) en vallen onder de licentie van dat project.

---

## Technische stack

| | |
|---|---|
| **Scraper** | Python + requests |
| **Geocoding** | PDOK Locatieserver v3.1 |
| **Frontend** | [Astro](https://astro.build) (statisch) |
| **Kaart** | [Leaflet](https://leafletjs.com) + MarkerCluster |
| **Hosting** | GitHub Pages |
| **CI/CD** | GitHub Actions |
