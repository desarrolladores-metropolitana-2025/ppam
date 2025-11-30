# apiapp.py
"""
ApiApp: pequeño panel en un solo archivo para usar la API de PythonAnywhere.
- PPAM 2025
- 29/11/2025
- Montar como Blueprint en tu Flask_app: app.register_blueprint(apiapp_bp)
- Configurar PA_API_TOKEN y PA_USERNAME en variables de entorno.
"""
import os
import requests
import time
from flask import Blueprint, current_app, request, jsonify, render_template_string

apiapp_bp = Blueprint("apiapp", __name__, url_prefix="/apiapp")

# Config desde env (seguro)
PA_API_TOKEN = os.getenv("PA_API_TOKEN")
PA_USERNAME = os.getenv("PA_USERNAME")
PA_API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}"

# Timeouts / cache
REQUEST_TIMEOUT = 12
_WEBAPPS_CACHE = {"ts": 0, "data": None}
_CACHE_TTL = 60  # 1 minuto


# ---- Helpers ----
def _pa_headers():
    return {"Authorization": f"Token {PA_API_TOKEN}"} if PA_API_TOKEN else {}


def _call_pa(path, method="GET", **kwargs):
    """Llamada segura a la API de PythonAnywhere. path sin prefijo '/api/v0/user/<username>/'"""
    url = f"{PA_API_BASE}/{path.lstrip('/')}"
    try:
        resp = requests.request(method, url, headers=_pa_headers(), timeout=REQUEST_TIMEOUT, **kwargs)
    except Exception as e:
        current_app.logger.exception("Error al contactar la API de PythonAnywhere")
        return None, f"Error de conexión: {e}"
    try:
        # Intentamos parsear JSON, si no es JSON devolvemos el text
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type or resp.text.strip().startswith(("{", "[")):
            return resp, None
    except Exception:
        pass
    return resp, None


def get_webapps(force=False):
    """Lista webapps (cache simple)."""
    now = time.time()
    if not force and _WEBAPPS_CACHE["data"] and (now - _WEBAPPS_CACHE["ts"] < _CACHE_TTL):
        return _WEBAPPS_CACHE["data"]
    resp, err = _call_pa("webapps/")
    if err:
        return {"error": err}
    if resp.status_code != 200:
        return {"error": f"PA returned {resp.status_code}: {resp.text}"}
    try:
        data = resp.json()
    except Exception as e:
        return {"error": f"Error parseando JSON: {e}"}
    # Cacheamos
    _WEBAPPS_CACHE["data"] = data
    _WEBAPPS_CACHE["ts"] = now
    return data


# ---- Backend API para frontend ----
@apiapp_bp.route("/api/webapps", methods=["GET"])
def api_webapps():
    """Devuelve la lista de webapps (JSON)."""
    if not PA_API_TOKEN or not PA_USERNAME:
        return jsonify({"error": "PA_API_TOKEN o PA_USERNAME no configurados en variables de entorno."}), 500
    data = get_webapps(force=request.args.get("force", "0") == "1")
    return jsonify({"ok": True, "data": data})


@apiapp_bp.route("/api/webapp/<webapp_name>/reload", methods=["POST"])
def api_reload_webapp(webapp_name):
    """Recarga la webapp indicada. webapp_name debe ser el 'name' interno o domain."""
    if not PA_API_TOKEN or not PA_USERNAME:
        return jsonify({"ok": False, "error": "Token o username no configurados."}), 500

    # Soportar que el usuario pase el domain_name (ej. ppamappcaba.pythonanywhere.com)
    path = f"webapps/{webapp_name}/reload/"
    resp, err = _call_pa(path, method="POST")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code == 200:
        return jsonify({"ok": True, "message": "Webapp reloaded"})
    else:
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500


@apiapp_bp.route("/api/webapp/<webapp_name>", methods=["GET"])
def api_webapp_details(webapp_name):
    """Detalles de una webapp (intenta webapps/<name>/ or busca por domain)"""
    if not PA_API_TOKEN or not PA_USERNAME:
        return jsonify({"ok": False, "error": "Token no configurado"}), 500

    # Primero intentamos GET /webapps/<webapp_name> (si existe)
    resp, err = _call_pa(f"webapps/{webapp_name}/")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code == 200:
        try:
            return jsonify({"ok": True, "data": resp.json()})
        except Exception:
            return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

    # Si no, listamos y buscamos por domain_name
    webapps = get_webapps()
    if isinstance(webapps, dict) and webapps.get("error"):
        return jsonify({"ok": False, "error": webapps["error"]}), 500

    for w in webapps:
        if w.get("domain_name") == webapp_name or w.get("name") == webapp_name:
            return jsonify({"ok": True, "data": w})
    return jsonify({"ok": False, "error": "No encontrado"}), 404


@apiapp_bp.route("/api/consoles", methods=["GET", "POST"])
def api_consoles():
    """GET -> listar consolas, POST -> crear una consola bash interactiva."""
    if not PA_API_TOKEN or not PA_USERNAME:
        return jsonify({"ok": False, "error": "Token o username no configurados"}), 500

    if request.method == "GET":
        resp, err = _call_pa("consoles/")
        if err:
            return jsonify({"ok": False, "error": err}), 500
        if resp.status_code == 200:
            try:
                return jsonify({"ok": True, "data": resp.json()})
            except Exception:
                return jsonify({"ok": False, "body": resp.text}), 500
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

    # POST: crear consola
    # body form: {"console_type": "bash", "command": "ls -la"}
    body = {}
    if request.form:
        body = request.form.to_dict()
    else:
        try:
            body = request.get_json() or {}
        except Exception:
            body = {}

    # Default: console_type=bash
    if "console_type" not in body:
        body["console_type"] = "bash"

    resp, err = _call_pa("consoles/", method="POST", json=body)
    if err:
        return jsonify({"ok": False, "error": err}), 500
    try:
        if resp.status_code in (200, 201):
            return jsonify({"ok": True, "data": resp.json()})
        else:
            return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500
    except Exception:
        return jsonify({"ok": False, "body": resp.text}), 500


# ---- Frontend (single-file templates + JS) ----
INDEX_TEMPLATE = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>API App · PythonAnywhere</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    /* Minimal modern UI - cards */
    :root{
      --bg:#f7fafc; --card:#ffffff; --accent:#0b74da; --muted:#6b7280; --glass: rgba(255,255,255,0.7);
      --success:#16a34a; --danger:#ef4444;
    }
    body{font-family:Inter,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);margin:0;color:#0b1220}
    .wrap{max-width:1100px;margin:28px auto;padding:12px}
    header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:18px}
    header h1{margin:0;font-size:20px}
    .controls{display:flex;gap:8px;align-items:center}
    .btn{background:var(--accent);color:#fff;padding:8px 12px;border-radius:10px;border:none;cursor:pointer}
    .btn.light{background:#e6eefc;color:var(--accent);border:1px solid #dbeafe}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
    .card{background:var(--card);padding:14px;border-radius:12px;box-shadow:0 6px 18px rgba(11,20,34,0.06);border:1px solid rgba(11,20,34,0.03)}
    .card h3{margin:0 0 8px 0;font-size:16px}
    .muted{color:var(--muted);font-size:13px}
    .small{font-size:13px}
    .kv{font-size:13px;color:var(--muted);margin-top:8px}
    .list{margin-top:10px;max-height:240px;overflow:auto;border-radius:8px;padding:8px;background:linear-gradient(180deg,#fff, #fbfdff)}
    pre {white-space:pre-wrap;font-size:13px}
    footer{margin-top:18px;text-align:center;color:var(--muted)}
    .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    input[type=text], select {padding:8px;border-radius:8px;border:1px solid #e6eef5;width:100%}
    .ok{color:var(--success)}
    .err{color:var(--danger)}
    .spinner{display:inline-block;width:16px;height:16px;border-radius:50%;border:2px solid rgba(0,0,0,0.1);border-top-color:var(--accent);animation:spin 1s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    @media (max-width:640px){ header{flex-direction:column;align-items:flex-start} }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div>
        <h1>API App — PythonAnywhere</h1>
        <div class="muted">Interfaz rápida para los endpoints de la API de PythonAnywhere</div>
      </div>
      <div class="controls">
        <button id="btn-refresh-webapps" class="btn light">Actualizar lista</button>
        <button id="btn-clear-log" class="btn light">Limpiar log</button>
      </div>
    </header>

    <div class="grid">
      <!-- Card: List webapps -->
      <div class="card">
        <h3>Mis Webapps</h3>
        <div class="muted">Listado de webapps desde la API</div>
        <div style="margin-top:10px">
          <button id="btn-list-webapps" class="btn">Listar webapps</button>
          <span id="webapps-spinner" style="display:none" class="spinner"></span>
        </div>
        <div class="list" id="webapps-list" style="margin-top:10px">Haz click en "Listar webapps"</div>
      </div>

      <!-- Card: Webapp details & reload -->
      <div class="card">
        <h3>Detalles / Reload</h3>
        <div class="muted">Seleccioná una webapp y recargala</div>
        <div style="margin-top:10px" class="row">
          <input id="sel-webapp" placeholder="ej: ppamappcaba.pythonanywhere.com" />
          <button id="btn-get-details" class="btn light">Ver detalles</button>
          <button id="btn-reload-webapp" class="btn">Reload</button>
          <span id="reload-spinner" style="display:none" class="spinner"></span>
        </div>
        <div class="kv" id="webapp-detail-area" style="margin-top:10px"></div>
      </div>

      <!-- Card: Consoles -->
      <div class="card">
        <h3>Consoles</h3>
        <div class="muted">Lista consolas y creación de una nueva consola (bash)</div>
        <div style="margin-top:10px" class="row">
          <button id="btn-list-consoles" class="btn">Listar consolas</button>
          <button id="btn-create-console" class="btn light">Crear consola bash</button>
        </div>
        <div class="list" id="consoles-list" style="margin-top:10px">Sin datos</div>
      </div>

      <!-- Card: Logs / respuesta -->
      <div class="card">
        <h3>Feedback / Debug</h3>
        <div class="muted">Respuestas crudas y mensajes de la API</div>
        <div style="margin-top:10px">
          <button id="btn-show-raw" class="btn light">Mostrar última respuesta</button>
          <button id="btn-copy-raw" class="btn light">Copiar</button>
        </div>
        <pre id="raw-output" class="small" style="margin-top:10px;height:220px;overflow:auto">Nada por ahora</pre>
      </div>
    </div>

    <footer>Equipo de desarrollo PPAM 2025 · ©</footer>
  </div>

<script>
const el = id => document.getElementById(id);
let lastResponse = null;

async function callApi(path, opts){
  const res = await fetch("/apiapp" + path, opts);
  let text = await res.text();
  try {
    const json = JSON.parse(text);
    lastResponse = json;
    return { ok: res.ok, status: res.status, json };
  } catch (e){
    // no JSON
    lastResponse = { status: res.status, text };
    return { ok: res.ok, status: res.status, json: null, text };
  }
}

async function listWebapps(){
  el("webapps-spinner").style.display = "inline-block";
  const r = await callApi("/api/webapps");
  el("webapps-spinner").style.display = "none";
  if(!r.ok){ el("webapps-list").innerText = "Error: " + JSON.stringify(r.json || r.text); return; }
  const data = r.json.data || r.json;
  if(!data || data.length === 0){ el("webapps-list").innerText = "No hay webapps"; return; }
  const lines = data.map(w => {
    const name = w.domain_name || w.name;
    return `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${name}</b><div class="muted small">python: ${w.python_version || '-'} • enabled: ${w.enabled}</div></div>`;
  });
  el("webapps-list").innerHTML = lines.join("");
}

async function getDetails(){
  const name = el("sel-webapp").value.trim();
  if(!name){ alert("Ingresá el domain o name de la webapp"); return; }
  el("reload-spinner").style.display = "inline-block";
  const r = await callApi("/api/webapp/" + encodeURIComponent(name));
  el("reload-spinner").style.display = "none";
  if(!r.ok){ el("webapp-detail-area").innerText = "Error: " + JSON.stringify(r.json || r.text); return; }
  const d = r.json.data;
  el("webapp-detail-area").innerHTML = `<pre>${JSON.stringify(d, null, 2)}</pre>`;
}

async function reloadWebapp(){
  const name = el("sel-webapp").value.trim();
  if(!name){ alert("Ingresá el domain o name de la webapp"); return; }
  el("reload-spinner").style.display = "inline-block";
  const r = await callApi("/api/webapp/" + encodeURIComponent(name) + "/reload", { method: "POST" });
  el("reload-spinner").style.display = "none";
  if(!r.ok){ el("raw-output").innerText = "Error: " + JSON.stringify(r.json || r.text); return; }
  el("raw-output").innerText = JSON.stringify(r.json, null, 2);
  alert("Reload solicitado. Revisá el panel Web en PythonAnywhere para confirmar.");
}

async function listConsoles(){
  el("consoles-list").innerText = "Cargando...";
  const r = await callApi("/api/consoles");
  if(!r.ok){ el("consoles-list").innerText = "Error: " + JSON.stringify(r.json || r.text); return; }
  const data = r.json.data || r.json;
  if(!data || data.length === 0){ el("consoles-list").innerText = "No hay consolas"; return; }
  el("consoles-list").innerHTML = data.map(c => `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${c.console_type}</b> • ${c.state || ''} <div class="muted small">${c.url || c.hostname || ''}</div></div>`).join("");
}

async function createConsole(){
  el("consoles-list").innerText = "Creando consola...";
  const r = await callApi("/api/consoles", { method: "POST", body: new URLSearchParams({console_type: "bash"}) });
  if(!r.ok){ el("consoles-list").innerText = "Error: " + JSON.stringify(r.json || r.text); return; }
  el("consoles-list").innerText = "Consola creada: " + JSON.stringify(r.json.data || r.json, null, 2);
}

function showLast(){
  el("raw-output").innerText = JSON.stringify(lastResponse, null, 2);
}

function copyRaw(){
  navigator.clipboard.writeText(JSON.stringify(lastResponse, null, 2));
  alert("Copiado al portapapeles");
}

el("btn-list-webapps").onclick = listWebapps;
el("btn-refresh-webapps").onclick = ()=>listWebapps();
el("btn-get-details").onclick = getDetails;
el("btn-reload-webapp").onclick = reloadWebapp;
el("btn-list-consoles").onclick = listConsoles;
el("btn-create-console").onclick = createConsole;
el("btn-show-raw").onclick = showLast;
el("btn-copy-raw").onclick = copyRaw;
el("btn-clear-log").onclick = ()=>{ el("raw-output").innerText = ""; lastResponse = null; }

</script>
</body>
</html>
"""

# ---- Index route ----
@apiapp_bp.route("/", methods=["GET"])
def index():
    # simple check
    if not PA_API_TOKEN or not PA_USERNAME:
        msg = ("PA_API_TOKEN and PA_USERNAME must be set as environment variables. "
               "This UI proxies requests through the server to keep your token secret.")
        # render template but with warning inside
        return render_template_string(INDEX_TEMPLATE.replace("Nada por ahora", "⚠️ " + msg))
    return render_template_string(INDEX_TEMPLATE)


# End of file
