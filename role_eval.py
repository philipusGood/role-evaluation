#!/usr/bin/env python3
"""
role_eval.py — Quebec Municipal Rôle d'Évaluation Lookup Tool

Supported platforms:
  • Geocentralis  — MRC des Pays-d'en-Haut (10 municipalities)
  • Geocentriq    — MRC Vallée-de-la-Gatineau (14+ municipalities)
  • PG Municipal  — Rigaud and others (opens browser; has CAPTCHA)

Usage:
  python role_eval.py "saint-sauveur" "125 chemin des Coureurs"
  python role_eval.py "gracefield" "123 rue Principale"
  python role_eval.py "morin-heights" "5283-91-2643" --type matricule
  python role_eval.py "saint-sauveur" "2313704"       --type lot

Output:
  Matricule      : 5283-91-2643
  Numéro de lot  : 2313704
  Registre Foncier: https://www.registrefoncier.gouv.qc.ca/...
"""

import requests
import re
import sys
import time
import json
import webbrowser
import argparse
from bs4 import BeautifulSoup


# ─────────────────────────────────────────────────────────────────────────────
# Municipality registry
# ─────────────────────────────────────────────────────────────────────────────

MUNICIPALITIES = {
    # ── Geocentralis — MRC des Pays-d'en-Haut ────────────────────────────────
    "esterel":                         {"platform": "geocentralis", "muni_id": "77011", "mrc_slug": "mrc-pays-d-en-haut"},
    "lac-des-seize-iles":              {"platform": "geocentralis", "muni_id": "77055", "mrc_slug": "mrc-pays-d-en-haut"},
    "morin-heights":                   {"platform": "geocentralis", "muni_id": "77050", "mrc_slug": "mrc-pays-d-en-haut"},
    "piedmont":                        {"platform": "geocentralis", "muni_id": "77030", "mrc_slug": "mrc-pays-d-en-haut"},
    "saint-adolphe-dhoward":           {"platform": "geocentralis", "muni_id": "77065", "mrc_slug": "mrc-pays-d-en-haut"},
    "saint-sauveur":                   {"platform": "geocentralis", "muni_id": "77043", "mrc_slug": "mrc-pays-d-en-haut"},
    "sainte-adele":                    {"platform": "geocentralis", "muni_id": "77022", "mrc_slug": "mrc-pays-d-en-haut"},
    "sainte-anne-des-lacs":            {"platform": "geocentralis", "muni_id": "77035", "mrc_slug": "mrc-pays-d-en-haut"},
    "sainte-marguerite-du-lac-masson": {"platform": "geocentralis", "muni_id": "77012", "mrc_slug": "mrc-pays-d-en-haut"},
    "wentworth-nord":                  {"platform": "geocentralis", "muni_id": "77060", "mrc_slug": "mrc-pays-d-en-haut"},

    # ── Geocentriq — MRC Vallée-de-la-Gatineau ───────────────────────────────
    "gracefield":       {"platform": "geocentriq", "muni_slug": "gracefield",       "mrc_slug": "vallee-de-la-gatineau"},
    "maniwaki":         {"platform": "geocentriq", "muni_slug": "maniwaki",         "mrc_slug": "vallee-de-la-gatineau"},
    "aumond":           {"platform": "geocentriq", "muni_slug": "aumond",           "mrc_slug": "vallee-de-la-gatineau"},
    "blue-sea":         {"platform": "geocentriq", "muni_slug": "blue-sea",         "mrc_slug": "vallee-de-la-gatineau"},
    "bois-franc":       {"platform": "geocentriq", "muni_slug": "bois-franc",       "mrc_slug": "vallee-de-la-gatineau"},
    "bouchette":        {"platform": "geocentriq", "muni_slug": "bouchette",        "mrc_slug": "vallee-de-la-gatineau"},
    "cayamant":         {"platform": "geocentriq", "muni_slug": "cayamant",         "mrc_slug": "vallee-de-la-gatineau"},
    "egan-sud":         {"platform": "geocentriq", "muni_slug": "egan-sud",         "mrc_slug": "vallee-de-la-gatineau"},
    "grand-remous":     {"platform": "geocentriq", "muni_slug": "grand-remous",     "mrc_slug": "vallee-de-la-gatineau"},
    "kazabazua":        {"platform": "geocentriq", "muni_slug": "kazabazua",        "mrc_slug": "vallee-de-la-gatineau"},
    "lac-sainte-marie": {"platform": "geocentriq", "muni_slug": "lac-sainte-marie", "mrc_slug": "vallee-de-la-gatineau"},
    "low":              {"platform": "geocentriq", "muni_slug": "low",              "mrc_slug": "vallee-de-la-gatineau"},
    "messines":         {"platform": "geocentriq", "muni_slug": "messines",         "mrc_slug": "vallee-de-la-gatineau"},
    "montcerf-lytton":  {"platform": "geocentriq", "muni_slug": "montcerf-lytton",  "mrc_slug": "vallee-de-la-gatineau"},

    # ── PG Municipal / ACCEO ─────────────────────────────────────────────────
    "rigaud": {"platform": "pg_municipal", "muni_code": "U4051", "fourn_seq": "344"},
}

ALIASES = {
    "st-sauveur":       "saint-sauveur",
    "ste-adele":        "sainte-adele",
    "ste-anne-des-lacs":"sainte-anne-des-lacs",
    "wentworth":        "wentworth-nord",
    "lac-masson":       "sainte-marguerite-du-lac-masson",
    "st-adolphe":       "saint-adolphe-dhoward",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def normalize_muni(name: str) -> str:
    key = name.lower().strip()
    for src, rep in [('à','a'),('â','a'),('é','e'),('è','e'),('ê','e'),
                     ('î','i'),('ô','o'),('ù','u'),('û','u'),('ç','c')]:
        key = key.replace(src, rep)
    key = re.sub(r"\s+", "-", key)
    key = re.sub(r"[^a-z0-9\-]", "", key)
    return ALIASES.get(key, key)


def build_registre_foncier_url(lot_number: str) -> str:
    lot_clean = re.sub(r"\s+", "", str(lot_number))
    return (
        "https://www.registrefoncier.gouv.qc.ca/Pivots/Recherche/"
        f"RechercheParNumeroDeLot?numeroLot={lot_clean}"
    )


def _make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
    })
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Geocentralis adapter
#
# API flow:
#   1. GET /public/sig-web/{mrc_slug}/{muni_id}/   → establishes public session
#   2. GET /georole_web_2/recherche-rapide/{muni_id}/?term={q}
#      → JSON: [{id, matricule, matricule_court, id_municipalite, text}, ...]
#   3. Parse lot from text HTML: Lot(s):</span> 2 313 704
#
# ─────────────────────────────────────────────────────────────────────────────

class GeocentralisAdapter:
    BASE = "https://portail.geocentralis.com"

    def __init__(self, muni_id: str, mrc_slug: str):
        self.muni_id  = muni_id
        self.mrc_slug = mrc_slug
        self.session  = _make_session()
        self._ready   = False

    # ── session init ──────────────────────────────────────────────────────────

    def _ensure_session(self):
        if self._ready:
            return
        url = f"{self.BASE}/public/sig-web/{self.mrc_slug}/{self.muni_id}/"
        try:
            self.session.get(url, timeout=15)
        except requests.RequestException as e:
            print(f"  [warn] session init failed: {e}", file=sys.stderr)
        self._ready = True

    # ── search ────────────────────────────────────────────────────────────────

    def _recherche_rapide(self, query: str) -> list:
        self._ensure_session()
        url = f"{self.BASE}/georole_web_2/recherche-rapide/{self.muni_id}/"
        params = {"term": query, "_": int(time.time() * 1000)}
        resp = self.session.get(url, params=params, timeout=20,
                                headers={"X-Requested-With": "XMLHttpRequest"})
        resp.raise_for_status()
        return resp.json()

    # ── parsing ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_lot(text_html: str) -> str | None:
        """Extract lot number from the HTML blob returned by recherche-rapide."""
        # Pattern: ...Lot(s):</span> 2 313 704...
        m = re.search(r"Lot\(s\):\s*</span>\s*([\d\s]+)", text_html)
        if m:
            return m.group(1).strip().replace(" ", "").replace("\u00a0", "")
        return None

    def _build_result(self, item: dict) -> dict:
        lot = self._parse_lot(item.get("text", ""))
        result = {
            "platform":           "geocentralis",
            "matricule":          item.get("matricule_court", ""),
            "matricule_complet":  item.get("matricule", ""),
            "lot":                lot,
            "ue_id":              item.get("id"),
        }
        if lot:
            result["registre_foncier_url"] = build_registre_foncier_url(lot)
        return result

    # ── public interface ──────────────────────────────────────────────────────

    def lookup(self, query: str) -> dict:
        try:
            results = self._recherche_rapide(query)
        except Exception as e:
            return {"error": f"recherche-rapide failed: {e}"}

        if not results:
            return {"error": f"No properties found for: {query!r}"}

        if len(results) == 1:
            return self._build_result(results[0])

        # Multiple results — show a numbered list and let the caller pick
        return {
            "multiple_results": True,
            "count": len(results),
            "results": [self._build_result(r) for r in results],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Geocentriq adapter (CIM platform)
#
# API: GET https://app.geocentriq.com/api/v1/municipalities/{slug}/evaluations
#        ?page_size=10&s={query}
# ─────────────────────────────────────────────────────────────────────────────

class GeocentriqAdapter:
    BASE = "https://app.geocentriq.com"

    def __init__(self, muni_slug: str):
        self.muni_slug = muni_slug
        self.session   = _make_session()
        self.session.headers.update({"Accept": "application/json"})

    def lookup(self, query: str) -> dict:
        url = f"{self.BASE}/api/v1/municipalities/{self.muni_slug}/evaluations"
        try:
            resp = self.session.get(url, params={"page_size": 10, "s": query},
                                    timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {"error": f"Geocentriq API failed: {e}"}

        results = data.get("results", [])
        if not results:
            return {"error": f"No results for: {query!r}"}

        prop = results[0]
        lot  = str(prop.get("no_lot") or prop.get("lot") or "").replace(" ", "")
        mat  = str(prop.get("matricule") or "")

        result = {
            "platform":  "geocentriq",
            "matricule": mat,
            "lot":       lot,
            "raw":       prop,
        }
        if lot:
            result["registre_foncier_url"] = build_registre_foncier_url(lot)

        if len(results) > 1:
            result["note"] = f"{len(results)} results found; showing first match."

        return result


# ─────────────────────────────────────────────────────────────────────────────
# PG Municipal / ACCEO adapter
#
# Cloudflare Turnstile CAPTCHA → open browser, let user search manually.
# ─────────────────────────────────────────────────────────────────────────────

class PGMunicipalAdapter:
    PG_BASE = "https://pdi.pgmunicipal.com/immosoft/controller/ImmoNetPub"

    def __init__(self, muni_code: str, fourn_seq: str):
        self.muni_code = muni_code
        self.fourn_seq = fourn_seq

    def lookup(self, query: str) -> dict:
        url = (
            f"{self.PG_BASE}/{self.muni_code}/trouverParAdresse"
            f"?language=fr&fourn_seq={self.fourn_seq}"
        )
        print(f"\n  ⚠  PG Municipal uses Cloudflare CAPTCHA.")
        print(f"  Opening browser → search for: {query!r}")
        print(f"  URL: {url}")
        webbrowser.open(url)
        return {
            "platform":       "pg_municipal",
            "browser_opened": True,
            "url":            url,
            "note":           "Complete the search manually in the browser.",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main lookup
# ─────────────────────────────────────────────────────────────────────────────

def lookup(municipality: str, query: str) -> dict:
    key       = normalize_muni(municipality)
    muni_info = MUNICIPALITIES.get(key)

    if not muni_info:
        return {
            "error": (
                f"Municipality {municipality!r} not found. "
                f"Normalised key: {key!r}. "
                f"Available: {', '.join(sorted(MUNICIPALITIES))}"
            )
        }

    platform = muni_info["platform"]

    if platform == "geocentralis":
        adapter = GeocentralisAdapter(muni_info["muni_id"], muni_info["mrc_slug"])
        return adapter.lookup(query)

    if platform == "geocentriq":
        adapter = GeocentriqAdapter(muni_info["muni_slug"])
        return adapter.lookup(query)

    if platform == "pg_municipal":
        adapter = PGMunicipalAdapter(muni_info["muni_code"], muni_info["fourn_seq"])
        return adapter.lookup(query)

    return {"error": f"Unknown platform: {platform}"}


# ─────────────────────────────────────────────────────────────────────────────
# Pretty-print
# ─────────────────────────────────────────────────────────────────────────────

def print_result(result: dict):
    if "error" in result:
        print(f"\n  ✗  Error: {result['error']}")
        return

    if result.get("multiple_results"):
        print(f"\n  Found {result['count']} results — showing all:\n")
        for i, r in enumerate(result["results"], 1):
            print(f"  [{i}]")
            _print_fields(r)
        return

    print()
    _print_fields(result)


def _print_fields(r: dict):
    rows = [
        ("Platform",          r.get("platform", "")),
        ("Matricule (court)", r.get("matricule", "")),
        ("Matricule (complet)",r.get("matricule_complet", "")),
        ("Numéro de lot",     r.get("lot", "")),
        ("Registre Foncier",  r.get("registre_foncier_url", "")),
    ]
    if "note" in r:
        rows.append(("Note", r["note"]))

    for label, value in rows:
        if value:
            print(f"  {label:<22}: {value}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Quebec Rôle d'Évaluation lookup — returns Matricule, Lot, Registre Foncier URL"
    )
    parser.add_argument("municipality", help='e.g. "saint-sauveur" or "gracefield"')
    parser.add_argument("query",        help='Address, matricule, or lot number')
    parser.add_argument("--json",       action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    print(f"\nLooking up: {args.query!r} in {args.municipality!r} ...")
    result = lookup(args.municipality, args.query)

    if args.json:
        # Remove raw API data before printing
        result.pop("raw", None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_result(result)


if __name__ == "__main__":
    main()
