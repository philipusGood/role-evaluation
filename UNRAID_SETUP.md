# Deploying on Unraid

## Architecture overview

```
Unraid server
├── /mnt/user/appdata/role-evaluation/   ← source code (git repo)
├── /mnt/user/appdata/role-eval-data/    ← persistent volume (SQLite DB, ~300 MB)
└── Docker container: role-evaluation
      port 7860 → Flask app + API
```

On first start the container downloads ~224 MB of Quebec property data and
builds the SQLite DB (≈15 minutes). Subsequent starts check for updates and
exit ingest in seconds if the data is current. The DB is rebuilt automatically
each April when the provincial rôle refreshes.

---

## Step 1 — Push code to GitHub (from Mac)

```bash
cd ~/Desktop/Cowork/role_evaluation
git add -A
git commit -m "new provincial DB architecture"
git push
```

GitHub Actions will build the Docker image and push it to `ghcr.io/philipusgood/role-evaluation:latest`.

---

## Step 2 — Create the data directory on Unraid

SSH into Unraid, then:

```bash
mkdir -p /mnt/user/appdata/role-eval-data
```

This directory persists across container restarts. It will hold `role_eval.db`
and `manifest.json` after the first ingest.

---

## Step 3 — Add the container in Unraid

In the Unraid web UI go to **Docker → Add Container** and fill in:

| Field | Value |
|-------|-------|
| Name | `role-evaluation` |
| Repository | `ghcr.io/philipusgood/role-evaluation:latest` |
| Network Type | `bridge` |
| Port — Host Port | `7860` |
| Port — Container Port | `7860` |
| Path — Container Path | `/data` |
| Path — Host Path | `/mnt/user/appdata/role-eval-data` |
| Variable — Key | `DATA_DIR` |
| Variable — Value | `/data` |

Click **Apply**.

---

## Step 4 — Watch the first-run ingest

In Unraid, click the container name → **Logs**. You'll see output like:

```
[10:02:01] Checking dataset metadata...
[10:02:03] Fetching municipality index for 2026...
[10:02:04]   1140 municipalities listed.
[10:02:04] Downloading https://donneesouvertes.affmunqc.net/role/Roles_Donnees_Ouvertes_2026.zip ...
[10:02:14]   Download: 22 MB / 224 MB (10%)
...
[10:14:30] Ingest complete.
[10:14:30]   Properties     : 3,521,847
[10:14:30]   DB size        : 287.4 MB
 * Running on http://0.0.0.0:7860
```

The app starts automatically once ingest finishes.

---

## Step 5 — Use it

**Browser UI:**
```
http://10.0.1.73:7860
```

**JSON API (for DealEval / Levitas integration):**

Search by address:
```
GET http://10.0.1.73:7860/api/lookup?query=125+chemin+des+Coureurs&muni_name=Saint-Sauveur
```

Search by matricule (no municipality needed):
```
GET http://10.0.1.73:7860/api/lookup?query=5283-91-2643
```

Search by lot number:
```
GET http://10.0.1.73:7860/api/lookup?query=2313704
```

Example response:
```json
{
  "muni_code": "77043",
  "muni_name": "Saint-Sauveur",
  "matricule": "5283-91-2643",
  "lot_number": "2313704",
  "address": "125 Chemin Des Coureurs",
  "total_value": 485000,
  "land_value": 120000,
  "building_value": 365000,
  "taxable_value": 485000,
  "ref_date": "2023-07-01",
  "role_year": 2026,
  "usage_code": "1000",
  "usage_label": "Résidentiel — 1 logement",
  "year_built": 1998,
  "living_area_m2": 148.5,
  "lot_area_m2": 3200.0,
  "registre_foncier_url": "https://www.registrefoncier.gouv.qc.ca/..."
}
```

**DB status check:**
```
GET http://10.0.1.73:7860/api/status
```

---

## Updating the data (annual, ~April)

The container checks for new data every time it starts. To force a refresh:

Option A — restart the container (it will detect the new `last_modified` and re-ingest).

Option B — SSH into Unraid and run:
```bash
docker exec role-evaluation python ingest.py --force
```

---

## Updating the code

Edit on Mac → push to GitHub → Force Update the container in Unraid Docker UI.
The data volume is untouched by code updates.

---

## CLI usage (debugging)

SSH into Unraid, then:

```bash
# Lookup by address
docker exec role-evaluation python role_eval.py "125 chemin des Coureurs" --muni "Saint-Sauveur"

# Lookup by matricule
docker exec role-evaluation python role_eval.py "5283-91-2643"

# Check DB status
docker exec role-evaluation python role_eval.py --status

# Force re-ingest
docker exec role-evaluation python ingest.py --force
```
