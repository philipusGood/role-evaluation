#!/usr/bin/env python3
"""
app.py — Flask web interface + JSON API for Quebec Rôle d'Évaluation.

Endpoints:
  GET  /                                        Browser UI
  GET  /api/lookup?query=&muni_code=&muni_name= Main lookup (address / matricule / lot)
  GET  /api/municipalities?q=                   Municipality search / autocomplete
  GET  /api/status                              DB health check
  GET  /health                                  Simple liveness probe
"""

from flask import Flask, jsonify, render_template_string, request

from role_eval import (
    db_status,
    list_municipalities,
    lookup,
    search_municipalities,
)

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# HTML UI
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rôle d'Évaluation — Québec</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      background: #f0f2f5;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding: 40px 16px 80px;
    }

    .card {
      background: #fff;
      border-radius: 14px;
      box-shadow: 0 2px 16px rgba(0,0,0,0.07);
      width: 100%;
      max-width: 600px;
      padding: 36px 40px;
    }

    h1 { font-size: 1.35rem; font-weight: 700; color: #111; }
    .sub { color: #777; font-size: 0.85rem; margin-top: 4px; margin-bottom: 28px; }

    label {
      display: block;
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #555;
      margin-bottom: 6px;
    }

    input[type="text"], input[type="search"] {
      width: 100%;
      padding: 10px 14px;
      border: 1.5px solid #ddd;
      border-radius: 8px;
      font-size: 0.95rem;
      color: #222;
      background: #fafafa;
      margin-bottom: 16px;
      transition: border-color 0.15s, background 0.15s;
    }
    input:focus { outline: none; border-color: #4f46e5; background: #fff; }

    .hint { font-size: 0.78rem; color: #999; margin-top: -12px; margin-bottom: 16px; }

    button[type="submit"] {
      width: 100%;
      padding: 12px;
      background: #4f46e5;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    button[type="submit"]:hover  { background: #4338ca; }
    button[type="submit"]:disabled { background: #a5b4fc; cursor: not-allowed; }

    /* ── Results ── */
    #result { margin-top: 28px; }

    .result-card {
      background: #f8f9ff;
      border: 1.5px solid #e0e3ff;
      border-radius: 10px;
      overflow: hidden;
    }
    .result-card.error {
      background: #fff5f5;
      border-color: #fecaca;
    }

    .result-header {
      padding: 16px 20px 14px;
      border-bottom: 1px solid #e0e3ff;
    }
    .result-header h2 {
      font-size: 1rem;
      font-weight: 700;
      color: #1a1a2e;
    }
    .result-header .subaddr {
      font-size: 0.82rem;
      color: #666;
      margin-top: 2px;
    }
    .badge {
      display: inline-block;
      font-size: 0.7rem;
      padding: 2px 8px;
      border-radius: 99px;
      background: #e0e7ff;
      color: #4338ca;
      font-weight: 700;
      text-transform: uppercase;
      vertical-align: middle;
      margin-left: 8px;
    }

    .eval-block {
      padding: 18px 20px;
      border-bottom: 1px solid #e0e3ff;
    }
    .eval-total {
      font-size: 1.75rem;
      font-weight: 800;
      color: #1a1a2e;
      letter-spacing: -0.5px;
    }
    .eval-label {
      font-size: 0.75rem;
      color: #888;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 4px;
    }
    .eval-sub {
      display: flex;
      gap: 24px;
      margin-top: 10px;
      flex-wrap: wrap;
    }
    .eval-sub-item .sl { font-size: 0.72rem; color: #aaa; text-transform: uppercase; letter-spacing: 0.04em; }
    .eval-sub-item .sv { font-size: 0.92rem; font-weight: 600; color: #444; }

    .detail-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      padding: 14px 20px;
      gap: 12px 24px;
    }
    .detail-item .dl { font-size: 0.72rem; color: #aaa; text-transform: uppercase; letter-spacing: 0.04em; }
    .detail-item .dv { font-size: 0.88rem; color: #333; font-weight: 500; margin-top: 2px; }

    .result-footer {
      padding: 12px 20px;
      border-top: 1px solid #e0e3ff;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }
    .result-footer a {
      font-size: 0.82rem;
      color: #4f46e5;
      text-decoration: none;
      font-weight: 600;
    }
    .result-footer a:hover { text-decoration: underline; }
    .result-footer .meta {
      font-size: 0.78rem;
      color: #aaa;
      margin-left: auto;
      align-self: center;
    }

    /* Multiple results */
    .multi-notice { font-size: 0.82rem; color: #777; margin-bottom: 12px; font-style: italic; }
    .result-item {
      background: #fff;
      border: 1.5px solid #e0e3ff;
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 10px;
      cursor: pointer;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .result-item:hover { border-color: #4f46e5; box-shadow: 0 2px 8px rgba(79,70,229,0.1); }
    .result-item .ri-addr { font-size: 0.88rem; font-weight: 600; color: #222; }
    .result-item .ri-val  { font-size: 1rem; font-weight: 700; color: #4f46e5; margin-top: 4px; }
    .result-item .ri-meta { font-size: 0.75rem; color: #999; margin-top: 2px; }

    /* Error */
    .error-msg { padding: 20px; color: #991b1b; font-size: 0.92rem; }

    /* Spinner */
    .spinner {
      display: inline-block;
      width: 16px; height: 16px;
      border: 3px solid rgba(255,255,255,0.4);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin 0.65s linear infinite;
      vertical-align: middle;
      margin-right: 8px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* DB not ready banner */
    .banner {
      background: #fef3c7;
      border: 1px solid #fcd34d;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 0.85rem;
      color: #92400e;
      margin-bottom: 20px;
    }
  </style>
</head>
<body>
<div class="card">
  <h1>🏡 Rôle d'Évaluation — Québec</h1>
  <p class="sub">Valeur municipale · Terrain &amp; bâtiment · Registre Foncier</p>

  <div id="banner" style="display:none" class="banner">
    ⏳ La base de données est en cours de chargement. Revenez dans quelques minutes.
  </div>

  <form id="searchForm" autocomplete="off">
    <label for="muni">Municipalité</label>
    <input type="search" id="muni" name="muni" placeholder="ex: Saint-Sauveur" list="muni-list">
    <datalist id="muni-list"></datalist>

    <label for="query">Adresse, matricule ou numéro de lot</label>
    <input type="text" id="query" name="query"
           placeholder="ex: 125 chemin des Coureurs  ou  5283-91-2643"
           required>
    <p class="hint">Pour une recherche par matricule ou lot, la municipalité est optionnelle.</p>

    <button type="submit" id="btn">Rechercher</button>
  </form>

  <div id="result"></div>
</div>

<script>
// ── Municipality autocomplete ─────────────────────────────────────────────
let allMunis = [];

async function loadMunis() {
  try {
    const res = await fetch('/api/municipalities');
    allMunis = await res.json();
    const dl = document.getElementById('muni-list');
    dl.innerHTML = allMunis.map(m =>
      `<option value="${m.nom}" data-code="${m.code}">`
    ).join('');
  } catch(e) {}
}
loadMunis();

async function checkStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (!data.ready) {
      document.getElementById('banner').style.display = 'block';
    }
  } catch(e) {}
}
checkStatus();

// ── Search ────────────────────────────────────────────────────────────────
const form = document.getElementById('searchForm');
const btn  = document.getElementById('btn');
const out  = document.getElementById('result');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const muni  = document.getElementById('muni').value.trim();
  const query = document.getElementById('query').value.trim();
  if (!query) return;

  // Resolve muni code from datalist if possible
  const opt = document.querySelector(`#muni-list option[value="${CSS.escape(muni)}"]`);
  const muniCode = opt ? opt.getAttribute('data-code') : '';

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Recherche en cours…';
  out.innerHTML = '';

  try {
    const params = new URLSearchParams({ query });
    if (muniCode) params.set('muni_code', muniCode);
    else if (muni) params.set('muni_name', muni);

    const res  = await fetch(`/api/lookup?${params}`);
    const data = await res.json();
    out.innerHTML = renderResult(data);
  } catch(err) {
    out.innerHTML = `<div class="result-card error"><div class="error-msg">Erreur réseau: ${err.message}</div></div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Rechercher';
  }
});

// ── Rendering ─────────────────────────────────────────────────────────────
function fmt(v) {
  if (v == null) return '—';
  return new Intl.NumberFormat('fr-CA', {style:'currency', currency:'CAD', maximumFractionDigits:0}).format(v);
}

function renderResult(data) {
  if (data.error) {
    return `<div class="result-card error"><div class="error-msg">✗ ${data.error}</div></div>`;
  }
  if (data.multiple_results) {
    const items = data.results.map(r => renderItem(r)).join('');
    return `<div class="multi-notice">${data.count} résultats — cliquez pour sélectionner :</div>${items}`;
  }
  return renderCard(data);
}

function renderItem(r) {
  return `
  <div class="result-item" onclick="this.closest('#result').innerHTML = renderCard(${JSON.stringify(r).replace(/"/g,'&quot;')})">
    <div class="ri-addr">${r.address || '(adresse inconnue)'}</div>
    <div class="ri-val">${fmt(r.total_value)}</div>
    <div class="ri-meta">${r.usage_label || ''} · Matricule ${r.matricule || '—'}</div>
  </div>`;
}

function renderCard(r) {
  const rfLink = r.registre_foncier_url
    ? `<a href="${r.registre_foncier_url}" target="_blank">Ouvrir dans le Registre Foncier →</a>`
    : '';

  const details = [
    ['Type d\'immeuble', r.usage_label],
    ['Année de construction', r.year_built],
    ['Superficie habitable', r.living_area_m2 ? `${r.living_area_m2} m²` : null],
    ['Superficie du terrain', r.lot_area_m2 ? `${new Intl.NumberFormat('fr-CA').format(Math.round(r.lot_area_m2))} m²` : null],
    ['Façade', r.frontage_m ? `${r.frontage_m} m` : null],
    ['Logements', r.num_units],
  ].filter(([,v]) => v != null).map(([l,v]) => `
    <div class="detail-item">
      <div class="dl">${l}</div>
      <div class="dv">${v}</div>
    </div>`).join('');

  return `
  <div class="result-card">
    <div class="result-header">
      <h2>${r.address || '(adresse non disponible)'}
        ${r.muni_name ? `<span class="badge">${r.muni_name}</span>` : ''}
      </h2>
      <div class="subaddr">Matricule ${r.matricule || '—'} · Lot ${r.lot_number || '—'}</div>
    </div>

    <div class="eval-block">
      <div class="eval-label">Valeur totale (rôle ${r.role_year || ''})</div>
      <div class="eval-total">${fmt(r.total_value)}</div>
      <div class="eval-sub">
        <div class="eval-sub-item">
          <div class="sl">Terrain</div>
          <div class="sv">${fmt(r.land_value)}</div>
        </div>
        <div class="eval-sub-item">
          <div class="sl">Bâtiment</div>
          <div class="sv">${fmt(r.building_value)}</div>
        </div>
        <div class="eval-sub-item">
          <div class="sl">Valeur imposable</div>
          <div class="sv">${fmt(r.taxable_value)}</div>
        </div>
      </div>
    </div>

    ${details ? `<div class="detail-grid">${details}</div>` : ''}

    <div class="result-footer">
      ${rfLink}
      <span class="meta">Réf. ${r.ref_date || '—'}</span>
    </div>
  </div>`;
}

// Allow clicking multiple-result items inline
document.addEventListener('click', (e) => {
  const item = e.target.closest('.result-item');
  if (!item) return;
  const onclick = item.getAttribute('onclick');
  if (onclick) {
    // handled inline — just call renderCard with the data
    try { eval(onclick); } catch(err) {}
  }
});
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
    GET /api/lookup?query=125+chemin+des+Coureurs&muni_name=saint-sauveur
    GET /api/lookup?query=5283-91-2643
    GET /api/lookup?query=2313704

    Returns JSON with evaluation data. Suitable for DealEval integration.
    """
    query     = request.args.get("query", "").strip()
    muni_code = request.args.get("muni_code", "").strip() or None
    muni_name = request.args.get("muni_name", "").strip() or None

    if not query:
        return jsonify({"error": "Missing parameter: query"}), 400

    result = lookup(query, muni_code=muni_code, muni_name=muni_name)
    return jsonify(result)


@app.route("/api/municipalities")
def api_municipalities():
    """
    GET /api/municipalities          → all municipalities (for autocomplete datalist)
    GET /api/municipalities?q=saint  → filtered subset
    """
    q = request.args.get("q", "").strip()
    if q:
        munis = search_municipalities(q, limit=20)
    else:
        munis = list_municipalities()
    return jsonify(munis)


@app.route("/api/status")
def api_status():
    return jsonify(db_status())


@app.route("/health")
def health():
    st = db_status()
    code = 200 if st.get("ready") else 503
    return jsonify({"status": "ok" if st.get("ready") else "initializing", **st}), code


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=False)
