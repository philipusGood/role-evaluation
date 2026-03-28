# role_eval.py — Quebec Rôle d'Évaluation Lookup

Automates the Quebec due-diligence workflow:
**Address / Matricule / Lot → Matricule + Numéro de Lot + Registre Foncier URL**

---

## Setup

```bash
pip install requests beautifulsoup4
```

Python 3.10+ required (uses `str | None` union syntax).

---

## Usage

```bash
# By address
python role_eval.py "saint-sauveur" "125 chemin des Coureurs"
python role_eval.py "gracefield"    "99 rue Principale"

# By matricule (partial is fine for Geocentralis)
python role_eval.py "morin-heights" "5283-91-2643"

# By lot number
python role_eval.py "saint-sauveur" "2313704"

# JSON output
python role_eval.py "saint-sauveur" "125 chemin" --json
```

**Example output:**
```
Looking up: '125 chemin des Coureurs' in 'saint-sauveur' ...

  Platform              : geocentralis
  Matricule (court)     : 5283-91-2643
  Matricule (complet)   : 5283-91-2643-0-000-0000
  Numéro de lot         : 2313704
  Registre Foncier      : https://www.registrefoncier.gouv.qc.ca/...
```

---

## Supported Municipalities

### Geocentralis — MRC des Pays-d'en-Haut
| Key | Municipality |
|-----|-------------|
| `saint-sauveur` | Saint-Sauveur |
| `sainte-adele` | Sainte-Adèle |
| `morin-heights` | Morin-Heights |
| `piedmont` | Piedmont |
| `sainte-anne-des-lacs` | Sainte-Anne-des-Lacs |
| `sainte-marguerite-du-lac-masson` | Sainte-Marguerite-du-Lac-Masson |
| `wentworth-nord` | Wentworth-Nord |
| `saint-adolphe-dhoward` | Saint-Adolphe-d'Howard |
| `lac-des-seize-iles` | Lac-des-Seize-Îles |
| `esterel` | Estérel |

### Geocentriq — MRC Vallée-de-la-Gatineau
`gracefield`, `maniwaki`, `aumond`, `blue-sea`, `bois-franc`, `bouchette`,
`cayamant`, `egan-sud`, `grand-remous`, `kazabazua`, `lac-sainte-marie`,
`low`, `messines`, `montcerf-lytton`

### PG Municipal (browser fallback)
`rigaud` — opens the search page in your browser (Cloudflare CAPTCHA present).

### Common aliases
`st-sauveur` → `saint-sauveur`
`ste-adele` → `sainte-adele`
`wentworth` → `wentworth-nord`
`lac-masson` → `sainte-marguerite-du-lac-masson`

---

## How It Works

### Geocentralis
1. Visits the public portal (`/public/sig-web/mrc-pays-d-en-haut/{muni_id}/`) to get a session cookie
2. Calls `/georole_web_2/recherche-rapide/{muni_id}/?term={query}` — returns JSON with matricule + lot
3. Parses lot number from the embedded HTML snippet

### Geocentriq
Calls the clean REST API: `/api/v1/municipalities/{slug}/evaluations?s={query}`
No session setup required.

### PG Municipal
Opens the PG Municipal search page in your browser — complete the CAPTCHA and search manually.

---

## Adding More Municipalities

Edit the `MUNICIPALITIES` dict in `role_eval.py`.

**Geocentralis** — add the `muni_id` (4–5 digit code from the URL) and `mrc_slug`:
```python
"nouvelle-muni": {"platform": "geocentralis", "muni_id": "XXXXX", "mrc_slug": "mrc-slug-here"},
```

**Geocentriq** — add the `muni_slug` (from `app.geocentriq.com` URL):
```python
"nouvelle-muni": {"platform": "geocentriq", "muni_slug": "nouvelle-muni", "mrc_slug": "vallee-de-la-gatineau"},
```

**PG Municipal** — get `muni_code` and `fourn_seq` from the URL at `pdi.pgmunicipal.com`:
```python
"nouvelle-muni": {"platform": "pg_municipal", "muni_code": "UXXXX", "fourn_seq": "NNN"},
```

---

## Registre Foncier

The output URL goes directly to the property lookup by lot number:
```
https://www.registrefoncier.gouv.qc.ca/Pivots/Recherche/RechercheParNumeroDeLot?numeroLot={lot}
```
Cost: $1 per lookup (standard RF fee, unchanged).

---

## Notes

- Geocentralis search is free-text — partial street name, civic number, or partial matricule all work
- If multiple results are returned, all are shown; the first match is used in `--json` mode
- Geocentriq's `no_lot` field sometimes contains spaces; they are stripped automatically
- Internet connection required; no API keys needed
