#!/usr/bin/env python3
"""
role_eval.py — Query module for Quebec Rôle d'Évaluation SQLite database.

Accepts an address or matricule, returns evaluated value, land/building split,
property details, and Registre Foncier URL.

Usage:
    python role_eval.py "5283-91-2643"
    python role_eval.py "125 chemin des Coureurs" --muni "saint-sauveur"
    python role_eval.py "125 chemin des Coureurs" --muni-code 77043
    python role_eval.py "125 chemin des Coureurs" --muni "saint-sauveur" --json
    python role_eval.py --status
"""

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH  = DATA_DIR / "role_eval.db"

# ─────────────────────────────────────────────────────────────────────────────
# Usage code labels (MAMH classification)
# ─────────────────────────────────────────────────────────────────────────────

USAGE_LABELS = {
    "1000": "Résidentiel — 1 logement",
    "1001": "Résidentiel — 2 logements",
    "1002": "Résidentiel — 3 logements",
    "1003": "Résidentiel — 4 logements",
    "1004": "Résidentiel — 5 logements",
    "1005": "Résidentiel — 6 logements",
    "1010": "Résidentiel — 7 logements et plus",
    "1040": "Résidentiel — maison mobile",
    "1090": "Résidentiel — autre",
    "2000": "Villégiature (chalet / résidence secondaire)",
    "3000": "Commercial",
    "3100": "Bureau / professionnel",
    "3200": "Hôtel / hébergement",
    "3400": "Commercial — grande surface",
    "4000": "Industriel",
    "4100": "Industriel léger",
    "4200": "Industriel lourd",
    "5000": "Institutionnel / gouvernemental",
    "5100": "École / établissement d'enseignement",
    "5200": "Hôpital / établissement de santé",
    "5300": "Lieu de culte",
    "6000": "Récréatif",
    "6100": "Terrain de golf",
    "7000": "Forêt",
    "7100": "Forêt productive",
    "8000": "Agriculture",
    "8100": "Ferme / exploitation agricole",
    "9000": "Terrain vacant",
    "9100": "Terrain vacant non bâti",
    "9200": "Stationnement",
}

STREET_TYPE_LABELS = {
    "AV":    "Avenue",
    "AVE":   "Avenue",
    "BD":    "Boulevard",
    "BOUL":  "Boulevard",
    "CARR":  "Carré",
    "CH":    "Chemin",
    "COTE":  "Côte",
    "CRES":  "Croissant",
    "IMP":   "Impasse",
    "MONT":  "Montée",
    "MTL":   "Montée",
    "PL":    "Place",
    "PLACE": "Place",
    "PRIV":  "Privé",
    "RANG":  "Rang",
    "RT":    "Route",
    "ROUTE": "Route",
    "RU":    "Rue",
    "RUE":   "Rue",
    "SENT":  "Sentier",
    "SQ":    "Square",
    "TERR":  "Terrasse",
    "VOIE":  "Voie",
}

DIRECTION_LABELS = {
    "E":  "Est",
    "N":  "Nord",
    "O":  "Ouest",
    "S":  "Sud",
    "NE": "Nord-Est",
    "NO": "Nord-Ouest",
    "SE": "Sud-Est",
    "SO": "Sud-Ouest",
}

MATRICULE_RE = re.compile(r"^\d{1,4}-\d{1,2}-\d{1,4}$")

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def normalize_text(s: str) -> str:
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
        ("'", " "), ("’", " "), ("-", " "),
    ]:
        s = s.replace(src, rep)
    return re.sub(r"\s+", " ", s).strip()


def build_rf_url(lot_number: str) -> Optional[str]:
    if not lot_number:
        return None
    lot_clean = re.sub(r"\s+", "", str(lot_number))
    return (
        "https://www.registrefoncier.gouv.qc.ca/Pivots/Recherche/"
        f"RechercheParNumeroDeLot?numeroLot={lot_clean}"
    )


def get_db() -> Optional[sqlite3.Connection]:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_status() -> dict:
    manifest_path = DATA_DIR / "manifest.json"
    if not DB_PATH.exists():
        return {
            "ready":   False,
            "message": "Database not found. Run: python ingest.py",
        }
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    return {
        "ready":              True,
        "year":               manifest.get("year"),
        "num_properties":     manifest.get("num_properties"),
        "num_municipalities": manifest.get("num_municipalities"),
        "last_modified":      manifest.get("last_modified"),
        "ingested_at":        manifest.get("ingested_at"),
        "db_size_mb":         manifest.get("db_size_mb"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Result formatting
# ─────────────────────────────────────────────────────────────────────────────

def format_result(row: sqlite3.Row) -> dict:
    d = dict(row)

    # Build human-readable address string
    # French Quebec convention: "1328 Rue Sherbrooke Est" (direction after street name)
    parts = []
    if d.get("civic_number"):
        parts.append(d["civic_number"])
    st = d.get("street_type") or ""
    parts.append(STREET_TYPE_LABELS.get(st, st))
    if d.get("street_name"):
        parts.append(d["street_name"].title())
    if d.get("street_direction"):
        parts.append(DIRECTION_LABELS.get(d["street_direction"], d["street_direction"]))
    address_str = " ".join(p for p in parts if p).strip()

    usage_code = d.get("usage_code") or ""

    return {
        "muni_code":    d.get("muni_code"),
        "muni_name":    d.get("muni_name"),
        "seq_id":       d.get("seq_id"),       # unique evaluation unit ID
        "matricule":    d.get("matricule"),
        "unit_id":      d.get("unit_id"),      # condo unit differentiator (RL0104F)
        "lot_number":   d.get("lot_number"),
        "address":      address_str,
        # Evaluation
        "total_value":    d.get("total_value"),
        "land_value":     d.get("land_value"),
        "building_value": d.get("building_value"),
        "taxable_value":  d.get("taxable_value"),
        "ref_date":       d.get("ref_date"),
        "role_year":      d.get("year"),
        # Property details
        "usage_code":     usage_code,
        "usage_label":    USAGE_LABELS.get(usage_code) or (f"Code {usage_code}" if usage_code else None),
        "year_built":     d.get("year_built"),
        "living_area_m2": d.get("living_area_m2"),
        "lot_area_m2":    d.get("lot_area_m2"),
        "frontage_m":     d.get("frontage_m"),
        "num_units":      d.get("num_units"),
        # Links
        "registre_foncier_url": build_rf_url(d.get("lot_number")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Municipality helpers
# ─────────────────────────────────────────────────────────────────────────────

def resolve_muni_code(conn: sqlite3.Connection, name: str) -> Optional[str]:
    norm = normalize_text(name)
    row = conn.execute(
        "SELECT code FROM municipalities WHERE nom_norm = ? LIMIT 1", (norm,)
    ).fetchone()
    if row:
        return row["code"]
    row = conn.execute(
        "SELECT code FROM municipalities WHERE nom_norm LIKE ? ORDER BY LENGTH(nom) ASC LIMIT 1",
        (f"%{norm}%",)
    ).fetchone()
    return row["code"] if row else None


def search_municipalities(name: str, limit: int = 10) -> list:
    conn = get_db()
    if not conn:
        return []
    norm = normalize_text(name)
    try:
        rows = conn.execute(
            "SELECT code, nom FROM municipalities WHERE nom_norm LIKE ? ORDER BY nom ASC LIMIT ?",
            (f"%{norm}%", limit)
        ).fetchall()
        return [{"code": r["code"], "nom": r["nom"]} for r in rows]
    finally:
        conn.close()


def list_municipalities(limit: int = 1200) -> list:
    conn = get_db()
    if not conn:
        return []
    try:
        rows = conn.execute(
            "SELECT code, nom FROM municipalities ORDER BY nom ASC LIMIT ?", (limit,)
        ).fetchall()
        return [{"code": r["code"], "nom": r["nom"]} for r in rows]
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Lookups
# ─────────────────────────────────────────────────────────────────────────────

_BASE_SELECT = """
    SELECT p.*, m.nom AS muni_name
    FROM properties p
    LEFT JOIN municipalities m ON p.muni_code = m.code
"""


def lookup_by_matricule(matricule: str) -> dict:
    conn = get_db()
    if not conn:
        return {"error": "Database not initialized. Run: python ingest.py"}
    clean = matricule.strip()
    try:
        row = conn.execute(
            _BASE_SELECT + "WHERE p.matricule = ? LIMIT 1", (clean,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"error": f"No property found for matricule: {clean}"}
    return format_result(row)


def lookup_by_lot(lot_number: str) -> dict:
    conn = get_db()
    if not conn:
        return {"error": "Database not initialized. Run: python ingest.py"}
    clean = re.sub(r"\s+", "", lot_number.strip())
    try:
        row = conn.execute(
            _BASE_SELECT + "WHERE p.lot_number = ? LIMIT 1", (clean,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"error": f"No property found for lot: {clean}"}
    return format_result(row)


def lookup_by_address(
    query:     str,
    muni_code: Optional[str] = None,
    muni_name: Optional[str] = None,
    limit:     int = 10,
) -> dict:
    conn = get_db()
    if not conn:
        return {"error": "Database not initialized. Run: python ingest.py"}

    try:
        if not muni_code and muni_name:
            muni_code = resolve_muni_code(conn, muni_name)
        if not muni_code:
            return {
                "error": "Municipality required for address search. "
                         "Pass muni_code (5-digit code) or muni_name."
            }

        q_norm = normalize_text(query)
        civic_match  = re.match(r"^(\d+)\s*(.*)", q_norm)
        civic_number = civic_match.group(1) if civic_match else None
        street_part  = civic_match.group(2).strip() if civic_match else q_norm

        # Strip leading street-type abbreviation
        words = street_part.split()
        if words and words[0] in STREET_TYPE_LABELS:
            words = words[1:]

        # Strip trailing cardinal direction (stored separately in street_direction column)
        # e.g. "SHERBROOKE E" → "SHERBROOKE" (direction "E" is in its own DB column)
        DIRECTIONS = {"E", "O", "N", "S", "NE", "NO", "SE", "SO",
                      "EST", "OUEST", "NORD", "SUD"}
        direction_hint = None
        if words and words[-1] in DIRECTIONS:
            direction_hint = words[-1]
            words = words[:-1]

        street_search = " ".join(words).strip()

        if not street_search:
            return {"error": "Could not parse a street name from the query."}

        params: list = [muni_code, f"%{street_search}%"]
        sql = _BASE_SELECT + "WHERE p.muni_code = ? AND p.street_name_norm LIKE ?"
        if civic_number:
            sql += " AND p.civic_number = ?"
            params.append(civic_number)
        sql += f" LIMIT {limit}"

        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"error": f"No properties found matching: {query!r}"}

    results = [format_result(r) for r in rows]
    if len(results) == 1:
        return results[0]
    return {"multiple_results": True, "count": len(results), "results": results}


def lookup(
    query:     str,
    muni_code: Optional[str] = None,
    muni_name: Optional[str] = None,
) -> dict:
    """
    Auto-detects query type:
      XXXX-XX-XXXX  → matricule lookup (province-wide, no muni needed)
      Pure digits   → lot number lookup
      Otherwise     → address lookup (muni_code or muni_name required)
    """
    q = query.strip()
    if MATRICULE_RE.match(q):
        return lookup_by_matricule(q)
    if re.match(r"^\d+$", q):
        return lookup_by_lot(q)
    return lookup_by_address(q, muni_code=muni_code, muni_name=muni_name)


# ─────────────────────────────────────────────────────────────────────────────
# CLI pretty-printer
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_currency(v) -> str:
    if v is None:
        return "—"
    return f"{int(v):,} $".replace(",", " ")


def _print_result(result: dict):
    if "error" in result:
        print(f"\n  ✗  {result['error']}\n")
        return
    if result.get("multiple_results"):
        print(f"\n  {result['count']} results found:\n")
        for r in result["results"]:
            _print_single(r)
            print()
        return
    _print_single(result)


def _print_single(r: dict):
    SEP = ("─" * 24, "─" * 22)
    rows = [
        ("Municipality",   f"{r.get('muni_name') or ''} ({r.get('muni_code') or ''})"),
        ("Address",        r.get("address") or "—"),
        ("Matricule",      r.get("matricule") or "—"),
        ("Lot number",     r.get("lot_number") or "—"),
        ("Usage",          r.get("usage_label") or "—"),
        ("Role year",      str(r.get("role_year") or "—")),
        ("Ref. date",      r.get("ref_date") or "—"),
        SEP,
        ("Total value",    _fmt_currency(r.get("total_value"))),
        ("  Land",         _fmt_currency(r.get("land_value"))),
        ("  Building",     _fmt_currency(r.get("building_value"))),
        ("  Taxable",      _fmt_currency(r.get("taxable_value"))),
        SEP,
        ("Year built",     str(r.get("year_built") or "—")),
        ("Living area",    f"{r.get('living_area_m2')} m²" if r.get("living_area_m2") else "—"),
        ("Lot area",       f"{r.get('lot_area_m2'):,.0f} m²" if r.get("lot_area_m2") else "—"),
        ("Units",          str(r.get("num_units") or "—")),
        ("Registre F.",    r.get("registre_foncier_url") or "—"),
    ]
    print()
    for label, value in rows:
        if label == "─" * 24:
            print(f"  {label}  {value}")
        else:
            print(f"  {label:<24}: {value}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Quebec Rôle d'Évaluation lookup")
    parser.add_argument("query", nargs="?", help="Address, matricule (XXXX-XX-XXXX), or lot number")
    parser.add_argument("--muni",      help="Municipality name (for address search)")
    parser.add_argument("--muni-code", dest="muni_code", help="5-digit municipality geo code")
    parser.add_argument("--status",    action="store_true", help="Show DB status and exit")
    parser.add_argument("--json",      action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.status:
        st = db_status()
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return

    if not args.query:
        parser.print_help()
        return

    result = lookup(args.query, muni_code=args.muni_code, muni_name=args.muni)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_result(result)


if __name__ == "__main__":
    main()
