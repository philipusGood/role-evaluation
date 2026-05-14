#!/usr/bin/env python3
"""
ingest.py — Download and parse Quebec Rôle d'Évaluation foncière into SQLite.

On first run: downloads the provincial ZIP (~224 MB), parses 1140 XML files,
loads ~3.5 M property records into /data/role_eval.db.

On subsequent runs: checks last_modified against the stored manifest and exits
immediately if the data is already current.

Usage:
    python ingest.py              # Skip if up to date
    python ingest.py --force      # Re-ingest regardless
    python ingest.py --check      # Print status and exit
"""

import argparse
import io
import json
import os
import re
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR      = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH       = DATA_DIR / "role_eval.db"
MANIFEST_PATH = DATA_DIR / "manifest.json"

DATASET_API   = (
    "https://www.donneesquebec.ca/recherche/api/3/action/package_show"
    "?id=roles-d-evaluation-fonciere-du-quebec"
)
INDEX_URL_TPL = "https://donneesouvertes.affmunqc.net/role/indexRole{year}.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def normalize_text(s: str) -> str:
    """Uppercase + strip accents for consistent string matching."""
    if not s:
        return ""
    s = s.upper()
    for src, rep in [
        ("À", "A"), ("Â", "A"), ("Ä", "A"),
        ("É", "E"), ("È", "E"), ("Ê", "E"), ("Ë", "E"),
        ("Î", "I"), ("Ï", "I"),
        ("Ô", "O"), ("Ö", "O"),
        ("Ù", "U"), ("Û", "U"), ("Ü", "U"),
        ("Ç", "C"),
        ("'", " "), ("’", " "),
    ]:
        s = s.replace(src, rep)
    return re.sub(r"\s+", " ", s).strip()


def fmt_matricule(a, b, c) -> str | None:
    """Build 'XXXX-XX-XXXX' matricule from XML fields RL0104A/B/C."""
    if not (a and b and c):
        return None
    try:
        return f"{int(a):04d}-{int(b):02d}-{int(c):04d}"
    except (ValueError, TypeError):
        return f"{a}-{b}-{c}"


# ─────────────────────────────────────────────────────────────────────────────
# Dataset metadata
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_zip_resource() -> dict:
    """Return the most recent 'Tous les fichiers' ZIP resource from the API."""
    resp = requests.get(DATASET_API, timeout=30)
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]

    zips = [
        r for r in resources
        if r["format"] == "ZIP" and "Tous les fichiers" in r.get("name", "")
    ]
    if not zips:
        raise RuntimeError("No ZIP resource found on donneesquebec.ca")

    zips.sort(key=lambda r: r.get("last_modified", ""), reverse=True)
    return zips[0]


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def save_manifest(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ─────────────────────────────────────────────────────────────────────────────
# SQLite schema
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS municipalities (
    code     TEXT PRIMARY KEY,
    nom      TEXT,
    nom_norm TEXT,
    xml_url  TEXT
);

CREATE TABLE IF NOT EXISTS properties (
    id               INTEGER PRIMARY KEY,
    muni_code        TEXT    NOT NULL,
    year             INTEGER NOT NULL,
    seq_id           TEXT,            -- RL0106A  unique per unit (use for deduplication)
    matricule        TEXT,            -- "XXXX-XX-XXXX"  (RL0104A-B-C) — NOT unique for condos
    unit_id          TEXT,            -- RL0104F  condo unit differentiator (NULL for non-condos)
    lot_number       TEXT,            -- RL0103Ax  (cadastre lot #)
    civic_number     TEXT,            -- RL0101Ax
    street_type      TEXT,            -- RL0101Ex  (CH, RUE, BOUL …)
    street_direction TEXT,            -- RL0101Fx
    street_name      TEXT,            -- RL0101Gx  (original case from XML)
    street_name_norm TEXT,            -- normalized for LIKE searches
    usage_code       TEXT,            -- RL0105A
    land_value       INTEGER,         -- RL0402A  valeur du terrain
    building_value   INTEGER,         -- RL0403A  valeur du bâtiment
    total_value      INTEGER,         -- RL0404A  valeur totale ← key field
    taxable_value    INTEGER,         -- RL0405A  valeur imposable
    year_built       INTEGER,         -- RL0307A
    lot_area_m2      REAL,            -- RL0302A
    frontage_m       REAL,            -- RL0301A
    num_units        INTEGER,         -- RL0306A
    living_area_m2   REAL,            -- RL0308A
    ref_date         TEXT             -- RL0401A  date de référence de l'évaluation
);

CREATE INDEX IF NOT EXISTS idx_seq_id    ON properties(seq_id);
CREATE INDEX IF NOT EXISTS idx_matricule ON properties(matricule);
CREATE INDEX IF NOT EXISTS idx_muni_addr ON properties(muni_code, street_name_norm, civic_number);
CREATE INDEX IF NOT EXISTS idx_muni_code ON properties(muni_code);
CREATE INDEX IF NOT EXISTS idx_lot       ON properties(lot_number);
"""


def create_schema(conn: sqlite3.Connection):
    for stmt in SCHEMA.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# XML parsing
# ─────────────────────────────────────────────────────────────────────────────

def _text(unit, tag: str) -> str | None:
    el = unit.find(".//" + tag)
    return el.text.strip() if el is not None and el.text else None


def _int(unit, tag: str) -> int | None:
    v = _text(unit, tag)
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _float(unit, tag: str) -> float | None:
    v = _text(unit, tag)
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def parse_xml(xml_bytes: bytes, muni_code: str, year: int) -> list[dict]:
    """Parse one municipality XML and return a list of property dicts.

    Note: year is a fallback — the XML's own RLM02A field is used if present.
    Condos share RL0104A-B-C (matricule base); RL0104F is the unit differentiator
    and RL0106A is the unique sequential ID per evaluation unit.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log(f"  [warn] XML parse error in {muni_code}: {e}")
        return []

    # Use the year declared in the XML itself (more accurate than the URL year)
    xml_year = root.findtext("RLM02A")
    if xml_year:
        try:
            year = int(xml_year)
        except (ValueError, TypeError):
            pass

    records = []
    for unit in root.findall("RLUEx"):
        a = _text(unit, "RL0104A")
        b = _text(unit, "RL0104B")
        c = _text(unit, "RL0104C")
        street_name = _text(unit, "RL0101Gx")

        records.append({
            "muni_code":        muni_code,
            "year":             year,
            "seq_id":           _text(unit, "RL0106A"),   # unique per unit
            "matricule":        fmt_matricule(a, b, c),   # may not be unique (condos)
            "unit_id":          _text(unit, "RL0104F"),   # condo differentiator
            "lot_number":       _text(unit, "RL0103Ax"),
            "civic_number":     _text(unit, "RL0101Ax"),
            "street_type":      _text(unit, "RL0101Ex"),
            "street_direction": _text(unit, "RL0101Fx"),
            "street_name":      street_name,
            "street_name_norm": normalize_text(street_name) if street_name else None,
            "usage_code":       _text(unit, "RL0105A"),
            "land_value":       _int(unit,  "RL0402A"),
            "building_value":   _int(unit,  "RL0403A"),
            "total_value":      _int(unit,  "RL0404A"),
            "taxable_value":    _int(unit,  "RL0405A"),
            "year_built":       _int(unit,  "RL0307A"),
            "lot_area_m2":      _float(unit,"RL0302A"),
            "frontage_m":       _float(unit,"RL0301A"),
            "num_units":        _int(unit,  "RL0306A"),
            "living_area_m2":   _float(unit,"RL0308A"),
            "ref_date":         _text(unit, "RL0401A"),
        })
    return records


INSERT_SQL = """
    INSERT INTO properties (
        muni_code, year, seq_id, matricule, unit_id, lot_number,
        civic_number, street_type, street_direction, street_name, street_name_norm,
        usage_code, land_value, building_value, total_value, taxable_value,
        year_built, lot_area_m2, frontage_m, num_units, living_area_m2, ref_date
    ) VALUES (
        :muni_code, :year, :seq_id, :matricule, :unit_id, :lot_number,
        :civic_number, :street_type, :street_direction, :street_name, :street_name_norm,
        :usage_code, :land_value, :building_value, :total_value, :taxable_value,
        :year_built, :lot_area_m2, :frontage_m, :num_units, :living_area_m2, :ref_date
    )
"""


# ─────────────────────────────────────────────────────────────────────────────
# Index CSV — municipality list
# ─────────────────────────────────────────────────────────────────────────────

def fetch_index_csv(year: int) -> list[dict]:
    """Return list of {code, nom, url} from the annual index CSV."""
    url = INDEX_URL_TPL.format(year=year)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    rows = []
    for line in resp.text.splitlines()[1:]:   # skip header
        parts = line.strip().split(",", 2)
        if len(parts) == 3:
            code, nom, xml_url = parts
            rows.append({
                "code":     code.strip(),
                "nom":      nom.strip(),
                "nom_norm": normalize_text(nom.strip()),
                "xml_url":  xml_url.strip(),
            })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Main ingest
# ─────────────────────────────────────────────────────────────────────────────

def ingest(force: bool = False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()

    # ── Fast path: skip the API call if manifest is less than 24 hours old ───
    # The provincial data updates once a year (April). Checking the remote API
    # on every container restart is unnecessary — once per day is plenty.
    if not force and DB_PATH.exists() and manifest.get("last_modified"):
        ingested_at_str = manifest.get("ingested_at", "")
        try:
            ingested_at = datetime.fromisoformat(ingested_at_str.rstrip("Z"))
            age_hours = (datetime.utcnow() - ingested_at).total_seconds() / 3600
            if age_hours < 24:
                log(f"Database is current (checked {age_hours:.1f}h ago, skipping remote check).")
                log(f"  Year: {manifest.get('year')}  Properties: {manifest.get('num_properties', 0):,}")
                return
        except (ValueError, TypeError):
            pass  # malformed date — fall through to normal check

    # ── Check remote metadata ─────────────────────────────────────────────────
    log("Checking dataset metadata...")
    resource      = get_latest_zip_resource()
    zip_url       = resource["url"]
    last_modified = resource.get("last_modified", "")

    year_match = re.search(r"(\d{4})", zip_url)
    year = int(year_match.group(1)) if year_match else datetime.now().year

    if not force and manifest.get("last_modified") == last_modified and DB_PATH.exists():
        log(f"Database is current (year={year}, last_modified={last_modified}).")
        log(f"  Properties: {manifest.get('num_properties', 0):,}")
        # Refresh ingested_at so the 24h fast-path kicks in next time
        manifest["ingested_at"] = datetime.utcnow().isoformat() + "Z"
        save_manifest(manifest)
        return

    # ── Fetch municipality index ──────────────────────────────────────────────
    log(f"Fetching municipality index for {year}...")
    municipalities = fetch_index_csv(year)
    log(f"  {len(municipalities)} municipalities listed.")

    # ── Download ZIP ─────────────────────────────────────────────────────────
    log(f"Downloading {zip_url} ...")
    resp = requests.get(zip_url, stream=True, timeout=600)
    resp.raise_for_status()
    total_bytes = int(resp.headers.get("content-length", 0))

    buf = bytearray()
    downloaded = 0
    last_reported = 0
    for chunk in resp.iter_content(chunk_size=2 * 1024 * 1024):  # 2 MB chunks
        buf.extend(chunk)
        downloaded += len(chunk)
        pct = (downloaded / total_bytes * 100) if total_bytes else 0
        if pct - last_reported >= 10:
            log(f"  Download: {downloaded / 1024 / 1024:.0f} MB"
                f"{f' / {total_bytes/1024/1024:.0f} MB ({pct:.0f}%)' if total_bytes else ''}")
            last_reported = pct

    log(f"  Download complete: {len(buf) / 1024 / 1024:.1f} MB")

    # ── Prepare DB ───────────────────────────────────────────────────────────
    log("Preparing database...")
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")   # 64 MB cache
    create_schema(conn)

    # ── Insert municipalities ─────────────────────────────────────────────────
    conn.executemany(
        "INSERT OR REPLACE INTO municipalities (code, nom, nom_norm, xml_url) "
        "VALUES (:code, :nom, :nom_norm, :xml_url)",
        municipalities
    )
    conn.commit()
    log(f"  Inserted {len(municipalities)} municipalities.")

    # ── Parse XML files from ZIP ─────────────────────────────────────────────
    log("Parsing XML files...")
    total_properties = 0
    errors = 0

    with zipfile.ZipFile(io.BytesIO(bytes(buf))) as zf:
        xml_files = sorted(n for n in zf.namelist() if n.lower().endswith(".xml"))
        log(f"  ZIP contains {len(xml_files)} XML files.")

        for i, fname in enumerate(xml_files):
            # Derive muni_code from filename: RL01023_2026.xml → 01023
            m = re.search(r"RL0*(\d+)_", fname)
            if m:
                # Re-pad to original length (codes are 5 digits, e.g. 01023)
                raw = m.group(0)[2:].rstrip("_")   # "01023"
                muni_code = raw.zfill(5)
            else:
                muni_code = Path(fname).stem

            with zf.open(fname) as f:
                raw_bytes = f.read()

            try:
                records = parse_xml(raw_bytes, muni_code, year)
            except Exception as e:
                log(f"  [warn] {fname}: {e}")
                errors += 1
                continue

            if records:
                conn.executemany(INSERT_SQL, records)
                total_properties += len(records)

            # Commit and report every 100 files
            if (i + 1) % 100 == 0:
                conn.commit()
                log(f"  Progress: {i+1}/{len(xml_files)} files | "
                    f"{total_properties:,} properties")

    conn.commit()

    # ── Build FTS-style index hint (vacuum to shrink file) ────────────────────
    log("Finalizing database (ANALYZE + VACUUM)...")
    conn.execute("ANALYZE")
    conn.execute("VACUUM")
    conn.close()

    db_size_mb = DB_PATH.stat().st_size / 1024 / 1024

    # ── Save manifest ─────────────────────────────────────────────────────────
    manifest = {
        "year":           year,
        "zip_url":        zip_url,
        "last_modified":  last_modified,
        "ingested_at":    datetime.utcnow().isoformat() + "Z",
        "num_properties": total_properties,
        "num_municipalities": len(municipalities),
        "errors":         errors,
        "db_size_mb":     round(db_size_mb, 1),
    }
    save_manifest(manifest)

    log("─" * 60)
    log(f"Ingest complete.")
    log(f"  Year           : {year}")
    log(f"  Municipalities : {len(municipalities):,}")
    log(f"  Properties     : {total_properties:,}")
    log(f"  Parse errors   : {errors}")
    log(f"  DB size        : {db_size_mb:.1f} MB")
    log("─" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ingest Quebec Rôle d'Évaluation into SQLite")
    parser.add_argument("--force", action="store_true", help="Re-ingest even if up to date")
    parser.add_argument("--check", action="store_true", help="Print status and exit (no download)")
    args = parser.parse_args()

    if args.check:
        manifest = load_manifest()
        if not manifest:
            log("No manifest found — database has not been ingested yet.")
        else:
            log(f"Year          : {manifest.get('year')}")
            log(f"Last modified : {manifest.get('last_modified')}")
            log(f"Ingested at   : {manifest.get('ingested_at')}")
            log(f"Properties    : {manifest.get('num_properties', 0):,}")
            log(f"DB size       : {manifest.get('db_size_mb')} MB")
        sys.exit(0)

    ingest(force=args.force)


if __name__ == "__main__":
    main()
