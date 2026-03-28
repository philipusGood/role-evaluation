#!/usr/bin/env python3
"""
app.py — Flask web interface for role_eval.py
Serves a browser UI + JSON API endpoint for DealEval integration.
"""

from flask import Flask, request, jsonify, render_template_string
from role_eval import lookup, MUNICIPALITIES, normalize_muni

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# HTML UI (single-file, no external build step)
# ─────────────────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rôle d'Évaluation</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f0f2f5;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      min-height: 100vh;
      padding: 40px 16px;
    }
    .card {
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.08);
      width: 100%;
      max-width: 560px;
      padding: 36px;
    }
    h1 {
      font-size: 1.4rem;
      font-weight: 700;
      color: #1a1a2e;
      margin-bottom: 4px;
    }
    .sub {
      color: #666;
      font-size: 0.875rem;
      margin-bottom: 28px;
    }
    label {
      display: block;
      font-size: 0.82rem;
      font-weight: 600;
      color: #444;
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    select, input[type="text"] {
      width: 100%;
      padding: 10px 14px;
      border: 1.5px solid #ddd;
      border-radius: 8px;
      font-size: 0.95rem;
      color: #222;
      background: #fafafa;
      margin-bottom: 18px;
      transition: border-color 0.15s;
      appearance: none;
    }
    select:focus, input[type="text"]:focus {
      outline: none;
      border-color: #4f46e5;
      background: white;
    }
    button {
      width: 100%;
      padding: 12px;
      background: #4f46e5;
      color: white;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    button:hover { background: #4338ca; }
    button:disabled { background: #a5b4fc; cursor: not-allowed; }

    #result {
      margin-top: 28px;
      display: none;
    }
    .result-box {
      background: #f8f9ff;
      border: 1.5px solid #e0e3ff;
      border-radius: 10px;
      padding: 20px 22px;
    }
    .result-box.error {
      background: #fff5f5;
      border-color: #fecaca;
    }
    .field { margin-bottom: 14px; }
    .field:last-child { margin-bottom: 0; }
    .field-label {
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #888;
      margin-bottom: 3px;
    }
    .field-value {
      font-size: 1rem;
      color: #1a1a2e;
      font-weight: 500;
      word-break: break-all;
    }
    .field-value a {
      color: #4f46e5;
      text-decoration: none;
      font-weight: 600;
    }
    .field-value a:hover { text-decoration: underline; }
    .badge {
      display: inline-block;
      font-size: 0.72rem;
      padding: 2px 8px;
      border-radius: 99px;
      background: #e0e7ff;
      color: #4338ca;
      font-weight: 700;
      vertical-align: middle;
      margin-left: 6px;
      text-transform: uppercase;
    }
    .spinner {
      display: inline-block;
      width: 18px; height: 18px;
      border: 3px solid rgba(255,255,255,0.4);
      border-top-color: white;
      border-radius: 50%;
      animation: spin 0.7s linear infinite;
      vertical-align: middle;
      margin-right: 8px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .multiple-notice {
      font-size: 0.82rem;
      color: #666;
      margin-bottom: 12px;
      font-style: italic;
    }
    .result-item {
      border: 1px solid #e0e3ff;
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 10px;
      background: white;
      cursor: pointer;
      transition: border-color 0.15s;
    }
    .result-item:hover { border-color: #4f46e5; }
  </style>
</head>
<body>
<div class="card">
  <h1>🏡 Rôle d'Évaluation</h1>
  <p class="sub">Matricule · Numéro de lot · Registre Foncier</p>

  <form id="searchForm">
    <label for="municipality">Municipalité</label>
    <select id="municipality" name="municipality" required>
      <option value="">Choisir une municipalité...</option>
      <optgroup label="Geocentralis — MRC des Pays-d'en-Haut">
        <option value="saint-sauveur">Saint-Sauveur</option>
        <option value="sainte-adele">Sainte-Adèle</option>
        <option value="morin-heights">Morin-Heights</option>
        <option value="piedmont">Piedmont</option>
        <option value="sainte-anne-des-lacs">Sainte-Anne-des-Lacs</option>
        <option value="sainte-marguerite-du-lac-masson">Sainte-Marguerite-du-Lac-Masson</option>
        <option value="wentworth-nord">Wentworth-Nord</option>
        <option value="saint-adolphe-dhoward">Saint-Adolphe-d'Howard</option>
        <option value="lac-des-seize-iles">Lac-des-Seize-Îles</option>
        <option value="esterel">Estérel</option>
      </optgroup>
      <optgroup label="Geocentriq — MRC Vallée-de-la-Gatineau">
        <option value="gracefield">Gracefield</option>
        <option value="maniwaki">Maniwaki</option>
        <option value="aumond">Aumond</option>
        <option value="blue-sea">Blue-Sea</option>
        <option value="bois-franc">Bois-Franc</option>
        <option value="bouchette">Bouchette</option>
        <option value="cayamant">Cayamant</option>
        <option value="egan-sud">Egan-Sud</option>
        <option value="grand-remous">Grand-Remous</option>
        <option value="kazabazua">Kazabazua</option>
        <option value="lac-sainte-marie">Lac-Sainte-Marie</option>
        <option value="low">Low</option>
        <option value="messines">Messines</option>
        <option value="montcerf-lytton">Montcerf-Lytton</option>
      </optgroup>
      <optgroup label="PG Municipal">
        <option value="rigaud">Rigaud (opens browser)</option>
      </optgroup>
    </select>

    <label for="query">Adresse, matricule ou numéro de lot</label>
    <input type="text" id="query" name="query"
           placeholder="ex: 125 chemin des Coureurs"
           required autocomplete="off">

    <button type="submit" id="searchBtn">Rechercher</button>
  </form>

  <div id="result"></div>
</div>

<script>
const form = document.getElementById('searchForm');
const btn  = document.getElementById('searchBtn');
const out  = document.getElementById('result');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const muni  = document.getElementById('municipality').value;
  const query = document.getElementById('query').value.trim();
  if (!muni || !query) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Recherche en cours...';
  out.style.display = 'none';

  try {
    const resp = await fetch(`/api/lookup?municipality=${encodeURIComponent(muni)}&query=${encodeURIComponent(query)}`);
    const data = await resp.json();
    out.style.display = 'block';
    out.innerHTML = renderResult(data);
  } catch (err) {
    out.style.display = 'block';
    out.innerHTML = `<div class="result-box error"><div class="field-value">Erreur réseau: ${err.message}</div></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Rechercher';
  }
});

function renderResult(data) {
  if (data.error) {
    return `<div class="result-box error">
      <div class="field-label">Erreur</div>
      <div class="field-value">${data.error}</div>
    </div>`;
  }

  if (data.multiple_results) {
    const items = data.results.map(r => renderFields(r)).join('');
    return `<div class="multiple-notice">${data.count} résultats trouvés :</div>${items}`;
  }

  return `<div class="result-box">${renderFields(data)}</div>`;
}

function renderFields(r) {
  const platformBadge = r.platform ? `<span class="badge">${r.platform}</span>` : '';
  const rfLink = r.registre_foncier_url
    ? `<a href="${r.registre_foncier_url}" target="_blank">Ouvrir dans le Registre Foncier →</a>`
    : '—';

  return `
    <div class="field">
      <div class="field-label">Matricule ${platformBadge}</div>
      <div class="field-value">${r.matricule || '—'}</div>
    </div>
    <div class="field">
      <div class="field-label">Matricule complet</div>
      <div class="field-value" style="font-size:0.85rem; color:#666">${r.matricule_complet || r.matricule || '—'}</div>
    </div>
    <div class="field">
      <div class="field-label">Numéro de lot</div>
      <div class="field-value">${r.lot || '—'}</div>
    </div>
    <div class="field">
      <div class="field-label">Registre Foncier</div>
      <div class="field-value">${rfLink}</div>
    </div>
  `;
}
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/lookup")
def api_lookup():
    """
    GET /api/lookup?municipality=saint-sauveur&query=125+chemin+des+Coureurs

    Returns JSON:
    {
      "matricule":         "5283-91-2643",
      "matricule_complet": "5283-91-2643-0-000-0000",
      "lot":               "2313704",
      "registre_foncier_url": "https://www.registrefoncier.gouv.qc.ca/..."
    }
    """
    municipality = request.args.get("municipality", "").strip()
    query        = request.args.get("query", "").strip()

    if not municipality:
        return jsonify({"error": "Missing parameter: municipality"}), 400
    if not query:
        return jsonify({"error": "Missing parameter: query"}), 400

    result = lookup(municipality, query)

    # Strip raw API data before sending to client
    result.pop("raw", None)

    return jsonify(result)


@app.route("/api/municipalities")
def api_municipalities():
    """List all supported municipalities."""
    munis = {k: v["platform"] for k, v in MUNICIPALITIES.items()}
    return jsonify(munis)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=False)
