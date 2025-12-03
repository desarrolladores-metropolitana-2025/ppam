# apiapp.py
"""
PPAM system -  30/11/2025
API App - PythonAnywhere + PRO utilities (Based on PythonAnywhere API)
Blueprint mounted at /apiapp
Equipo de desarrolladores PPAM (c) 2025

Features:
- Cards UI (single-file templates) for many PythonAnywhere API endpoints:
  - webapps (list, details, create*, delete*, reload, update)
  - consoles (list, create, close)
  - scheduled tasks (list, create, run, delete)
  - files via API where supported
  - workers (list, create, delete)
- Extra PRO server-side features (not through PA API):
  - File manager (list, view, edit, delete, upload, download, backup zip)
  - View server logs (error.log, server.log)
  - Deploy (git pull) and run local scripts
  - Reload webapp (via PA API)
- Uses environment variables: PA_API_TOKEN, PA_USERNAME
- Configurable FILEBROWSER_ROOT via app.config['FILEBROWSER_ROOT']
"""

import os
import io
import json
import shutil
import zipfile
import time
import subprocess
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask_login import login_required, current_user


import requests
from flask import (
    Blueprint, current_app, request, jsonify,
    render_template_string, send_file, abort, url_for
)
from werkzeug.utils import secure_filename

# -----------------------------------------------------------------------------
# Blueprint & basic config
# -----------------------------------------------------------------------------
apiapp_bp = Blueprint("apiapp", __name__, url_prefix="/apiapp")

PA_API_TOKEN = os.getenv("PA_API_TOKEN")
PA_USERNAME = os.getenv("PA_USERNAME")
PA_API_BASE = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}" if PA_USERNAME else None

REQUEST_TIMEOUT = 12
CACHE = {"webapps": {"ts": 0, "data": None}, "last_response": None}
CACHE_TTL = 60  # seconds for some caches
# ---------- LOGIN REQUIRED ----------------------
def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login", next=request.url))

        if getattr(current_user, "rol", None) != "Admin":
            abort(403, description="No tenés permisos para acceder a esta sección.")

        return func(*args, **kwargs)
    return wrapper
@apiapp_bp.before_request
@login_required
@admin_required
def protect_apiapp_routes():
    pass
# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def require_pa_token(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not PA_API_TOKEN or not PA_USERNAME:
            return jsonify({"ok": False, "error": "PA_API_TOKEN or PA_USERNAME not configured in env"}), 500
        return func(*args, **kwargs)
    return wrapper

def _pa_headers():
    return {"Authorization": f"Token {PA_API_TOKEN}"} if PA_API_TOKEN else {}

def _call_pa(path, method="GET", **kwargs):
    """Call PythonAnywhere API safely. path is relative to /api/v0/user/<username>/"""
    if not PA_API_BASE:
        return None, "PA_USERNAME not set"
    url = f"{PA_API_BASE}/{path.lstrip('/')}"
    try:
        resp = requests.request(method, url, headers=_pa_headers(), timeout=REQUEST_TIMEOUT, **kwargs)
        # store last response for debugging
        CACHE["last_response"] = {"url": url, "status": resp.status_code, "headers": dict(resp.headers), "text": resp.text[:2000]}
        return resp, None
    except Exception as e:
        current_app.logger.exception("PA API call error")
        return None, str(e)

def _get_webapps(force=False):
    now = time.time()
    cached = CACHE["webapps"]
    if not force and cached["data"] and (now - cached["ts"] < CACHE_TTL):
        return cached["data"]
    resp, err = _call_pa("webapps/")
    if err:
        return {"error": err}
    if resp.status_code != 200:
        try:
            return {"error": f"PA returned {resp.status_code}: {resp.text}"}
        except Exception:
            return {"error": f"PA returned {resp.status_code}"}
    try:
        data = resp.json()
    except Exception:
        return {"error": "Invalid JSON from PA"}
    cached["data"] = data
    cached["ts"] = now
    return data

# Simple safe path logic for file manager
def get_root():
    root = current_app.config.get("FILEBROWSER_ROOT", os.path.join("/home", PA_USERNAME or ""))  # default /home/<user>
    return os.path.abspath(root)

def safe_path(relpath):
    # Accept '', '.' or nested; return absolute path within root
    root = get_root()
    rel = (relpath or "").strip("/")
    joined = os.path.normpath(os.path.join(root, rel))
    if not joined.startswith(root):
        abort(403, "Access outside of root not allowed")
    return joined

def rel_from_abs(abs_path):
    root = get_root()
    return os.path.relpath(abs_path, root).replace("\\", "/")

def human_size(n):
    if n is None: return ""
    n = float(n)
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"

def is_text_file(path):
    return Path(path).suffix.lower() in {'.txt','.py','.md','.html','.htm','.css','.js','.json','.csv','.ini','.cfg','.log','.sql','.yml','.yaml'}

# -----------------------------------------------------------------------------
# Backend API routes (these are called from the UI)
# -----------------------------------------------------------------------------

# --- Webapps ---
@apiapp_bp.route("/api/webapps", methods=["GET"])
@require_pa_token
def api_webapps():
    force = request.args.get("force", "0") == "1"
    data = _get_webapps(force=force)
    if isinstance(data, dict) and data.get("error"):
        return jsonify({"ok": False, "error": data["error"]}), 500
    return jsonify({"ok": True, "data": data})

@apiapp_bp.route("/api/webapp/<name>/details", methods=["GET"])
@require_pa_token
def api_webapp_details(name):
    # Try GET /webapps/<name>/ else lookup by domain_name
    resp, err = _call_pa(f"webapps/{name}/")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code == 200:
        try:
            return jsonify({"ok": True, "data": resp.json()})
        except:
            return jsonify({"ok": False, "body": resp.text}), 500
    # fallback: list and search by domain_name or name
    webapps = _get_webapps()
    if isinstance(webapps, dict) and webapps.get("error"):
        return jsonify({"ok": False, "error": webapps["error"]}), 500
    for w in webapps:
        if w.get("domain_name") == name or w.get("name") == name:
            return jsonify({"ok": True, "data": w})
    return jsonify({"ok": False, "error": "Not found"}), 404

@apiapp_bp.route("/api/webapp/<name>/reload", methods=["POST"])
@require_pa_token
def api_webapp_reload(name):
    # name can be domain_name or internal name
    # try both: if name contains '.', assume domain_name; else try internal first
    target = name
    resp, err = _call_pa(f"webapps/{target}/reload/", method="POST")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code in (200, 204):
        return jsonify({"ok": True, "message": "Reload triggered"})
    # try list and match by domain_name
    webapps = _get_webapps()
    if isinstance(webapps, list):
        for w in webapps:
            if w.get("domain_name") == name:
                resp, err = _call_pa(f"webapps/{w.get('name')}/reload/", method="POST")
                if err:
                    return jsonify({"ok": False, "error": err}), 500
                if resp.status_code in (200,204):
                    return jsonify({"ok": True, "message": "Reload triggered"})
    return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

@apiapp_bp.route("/api/webapp/create", methods=["POST"])
@require_pa_token
def api_webapp_create():
    # Creating webapps via API may be restricted to paid accounts.
    # Expected input (JSON or form): domain_name, source_directory, python_version, virtualenv_path(optional)
    payload = request.json or request.form.to_dict()
    if not payload.get("domain_name") or not payload.get("source_directory"):
        return jsonify({"ok": False, "error": "domain_name and source_directory required"}), 400
    resp, err = _call_pa("webapps/", method="POST", json=payload)
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code in (200,201):
        # invalidate cache
        CACHE["webapps"]["data"] = None
        return jsonify({"ok": True, "data": resp.json()})
    return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

@apiapp_bp.route("/api/webapp/<name>/delete", methods=["POST"])
@require_pa_token
def api_webapp_delete(name):
    resp, err = _call_pa(f"webapps/{name}/", method="DELETE")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code in (200,204):
        CACHE["webapps"]["data"] = None
        return jsonify({"ok": True, "message": "Deleted"})
    return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

# --- Consoles ---
@apiapp_bp.route("/api/consoles", methods=["GET", "POST"])
@require_pa_token
def api_consoles():
    if request.method == "GET":
        resp, err = _call_pa("consoles/")
        if err:
            return jsonify({"ok": False, "error": err}), 500
        if resp.status_code == 200:
            return jsonify({"ok": True, "data": resp.json()})
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500
    else:
        # create console
        body = request.json or request.form.to_dict() or {"console_type": "bash"}
        resp, err = _call_pa("consoles/", method="POST", json=body)
        if err:
            return jsonify({"ok": False, "error": err}), 500
        if resp.status_code in (200,201):
            return jsonify({"ok": True, "data": resp.json()})
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

@apiapp_bp.route("/api/consoles/<console_id>/close", methods=["POST"])
@require_pa_token
def api_console_close(console_id):
    resp, err = _call_pa(f"consoles/{console_id}/", method="DELETE")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code in (200,204):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

# --- Scheduled tasks ---
@apiapp_bp.route("/api/tasks", methods=["GET", "POST"])
@require_pa_token
def api_tasks():
    if request.method == "GET":
        resp, err = _call_pa("scheduled_tasks/")
        if err:
            return jsonify({"ok": False, "error": err}), 500
        if resp.status_code == 200:
            return jsonify({"ok": True, "data": resp.json()})
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500
    else:
        payload = request.json or request.form.to_dict()
        resp, err = _call_pa("scheduled_tasks/", method="POST", json=payload)
        if err:
            return jsonify({"ok": False, "error": err}), 500
        if resp.status_code in (200,201):
            return jsonify({"ok": True, "data": resp.json()})
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

@apiapp_bp.route("/api/tasks/<task_id>/run", methods=["POST"])
@require_pa_token
def api_task_run(task_id):
    resp, err = _call_pa(f"scheduled_tasks/{task_id}/run/", method="POST")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code in (200,201,204):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

@apiapp_bp.route("/api/tasks/<task_id>/delete", methods=["POST"])
@require_pa_token
def api_task_delete(task_id):
    resp, err = _call_pa(f"scheduled_tasks/{task_id}/", method="DELETE")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code in (200,204):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

# --- Workers ---
@apiapp_bp.route("/api/workers", methods=["GET", "POST"])
@require_pa_token
def api_workers():
    if request.method == "GET":
        resp, err = _call_pa("workers/")
        if err:
            return jsonify({"ok": False, "error": err}), 500
        if resp.status_code == 200:
            return jsonify({"ok": True, "data": resp.json()})
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500
    else:
        payload = request.json or request.form.to_dict()
        resp, err = _call_pa("workers/", method="POST", json=payload)
        if err:
            return jsonify({"ok": False, "error": err}), 500
        if resp.status_code in (200,201):
            return jsonify({"ok": True, "data": resp.json()})
        return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

@apiapp_bp.route("/api/workers/<worker_name>/delete", methods=["POST"])
@require_pa_token
def api_worker_delete(worker_name):
    resp, err = _call_pa(f"workers/{worker_name}/", method="DELETE")
    if err:
        return jsonify({"ok": False, "error": err}), 500
    if resp.status_code in (200,204):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "status": resp.status_code, "body": resp.text}), 500

# -----------------------------------------------------------------------------
# PRO - File manager & other local operations (runs on the server)
# -----------------------------------------------------------------------------
@apiapp_bp.route("/api/fs/list", methods=["GET"])
def api_fs_list():
    p = request.args.get("p", "").strip("/")
    abs_path = safe_path(p)
    items = []
    try:
        names = sorted(os.listdir(abs_path), key=lambda s: s.lower())
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "Not found"}), 404
    for name in names:
        full = os.path.join(abs_path, name)
        try:
            st = os.stat(full)
            items.append({
                "name": name,
                "is_dir": os.path.isdir(full),
                "size": st.st_size if os.path.isfile(full) else None,
                "mtime": int(st.st_mtime),
                "relpath": rel_from_abs(full)
            })
        except Exception:
            continue
    return jsonify({"ok": True, "items": items})

@apiapp_bp.route("/api/fs/view", methods=["GET"])
def api_fs_view():
    path = request.args.get("path", "")
    abs_p = safe_path(path)
    if not os.path.exists(abs_p):
        return jsonify({"ok": False, "error": "Not found"}), 404
    if os.path.isdir(abs_p):
        return jsonify({"ok": False, "error": "Is a directory"}), 400
    if not is_text_file(abs_p):
        # send as file
        return send_file(abs_p)
    try:
        with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@apiapp_bp.route("/api/fs/edit", methods=["POST"])
def api_fs_edit():
    path = request.form.get("path", "")
    txt = request.form.get("content", "")
    abs_p = safe_path(path)
    if os.path.isdir(abs_p):
        return jsonify({"ok": False, "error": "Is a directory"}), 400
    try:
        with open(abs_p, "w", encoding="utf-8") as f:
            f.write(txt or "")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@apiapp_bp.route("/api/fs/delete", methods=["POST"])
def api_fs_delete():
    path = request.form.get("path", "") or request.get_data(as_text=True)
    abs_p = safe_path(path)
    try:
        if os.path.isdir(abs_p):
            shutil.rmtree(abs_p)
        else:
            os.remove(abs_p)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@apiapp_bp.route("/api/fs/upload", methods=["POST"])
def api_fs_upload():
    p = request.form.get("p", "").strip("/")
    abs_dir = safe_path(p)
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    f = request.files.get('file')
    filename = secure_filename(f.filename)
    dest = os.path.join(abs_dir, filename)
    try:
        f.save(dest)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@apiapp_bp.route("/api/fs/download", methods=["GET"])
def api_fs_download():
    path = request.args.get("path", "")
    abs_p = safe_path(path)
    if not os.path.exists(abs_p):
        return jsonify({"ok": False, "error": "Not found"}), 404
    if os.path.isdir(abs_p):
        # zip and send
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(abs_p):
                for f in files:
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, abs_p)
                    zf.write(full, arcname)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"{Path(abs_p).name}.zip", mimetype="application/zip")
    else:
        return send_file(abs_p, as_attachment=True)

@apiapp_bp.route("/api/fs/backup", methods=["POST"])
def api_fs_backup():
    # create zip of a path
    p = request.form.get("p", "").strip("/")
    abs_base = safe_path(p)
    name = f"backup_{Path(abs_base).name}_{int(time.time())}.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(abs_base):
            for f in files:
                full = os.path.join(root, f)
                arcname = os.path.relpath(full, safe_path(p))
                zf.write(full, arcname)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")

# -----------------------------------------------------------------------------
# PRO: Logs, deploy, run local script
# -----------------------------------------------------------------------------
@apiapp_bp.route("/api/logs", methods=["GET"])
def api_logs():
    # returns tail of server.log and error.log
    root = get_root()
    # try common paths
    logs = {}
    candidates = [
        "/var/log/apache2/error.log",
        "/var/log/apache2/access.log",
        os.path.join(root, "error.log"),
        os.path.join(root, "server.log"),
        os.path.join(root, "webapp_error.log"),
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    logs[p] = "\n".join(f.readlines()[-200:])
        except Exception:
            logs[p] = "error reading"
    return jsonify({"ok": True, "logs": logs})

@apiapp_bp.route("/api/deploy", methods=["POST"])
def api_deploy():
    # simple git pull in a target dir
    repo_dir = request.form.get("dir", "").strip("/")
    abs_dir = safe_path(repo_dir or "")
    branch = request.form.get("branch", "main")
    if not os.path.exists(abs_dir):
        return jsonify({"ok": False, "error": "Dir not found"}), 404
    try:
        # run git pull
        p = subprocess.run(["git", "pull", "origin", branch], cwd=abs_dir, capture_output=True, text=True, timeout=120)
        out = p.stdout + "\n" + p.stderr
        return jsonify({"ok": True, "output": out, "code": p.returncode})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@apiapp_bp.route("/api/run", methods=["POST"])
def api_run():
    # run a local command (be careful). Only allow within root.
    cmd = request.form.get("cmd", "")
    cwd = request.form.get("cwd", "").strip("/")
    abs_cwd = safe_path(cwd or "")
    if not cmd:
        return jsonify({"ok": False, "error": "cmd required"}), 400
    try:
        p = subprocess.run(cmd.split(), cwd=abs_cwd, capture_output=True, text=True, timeout=60)
        return jsonify({"ok": True, "stdout": p.stdout, "stderr": p.stderr, "code": p.returncode})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# -----------------------------------------------------------------------------
# Frontend template (single-file) - INDEX_TEMPLATE
# -----------------------------------------------------------------------------
INDEX_TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>API App · PythonAnywhere · PRO</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#f6f8fb; --card:#fff; --accent:#0b74da; --muted:#6b7280;
  --danger:#ef4444; --success:#16a34a;
}
body{font-family:Inter,Arial,Helvetica,sans-serif;background:var(--bg);margin:0;color:#0b1220}
.app{max-width:1200px;margin:18px auto;padding:12px}
.header{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px}
.brand h1{font-size:18px;margin:0}
.controls{display:flex;gap:8px}
.btn{background:var(--accent);color:#fff;padding:8px 10px;border-radius:8px;border:none;cursor:pointer}
.btn.light{background:#e6eefc;color:var(--accent);border:1px solid #dbeafe}
.card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.card{background:var(--card);padding:14px;border-radius:12px;box-shadow:0 6px 18px rgba(11,20,34,0.04);border:1px solid rgba(11,20,34,0.03)}
.card h3{margin:0 0 8px 0;font-size:16px}
.muted{color:var(--muted);font-size:13px}
.small{font-size:13px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.kv{font-size:13px;color:var(--muted);margin-top:8px}
.list{margin-top:10px;max-height:240px;overflow:auto;border-radius:8px;padding:8px;background:linear-gradient(180deg,#fff, #fbfdff)}
pre{white-space:pre-wrap;font-size:13px}
.footer{margin-top:18px;text-align:center;color:var(--muted)}
input[type=text], textarea, select{padding:8px;border-radius:8px;border:1px solid #e6eef5;width:100%}
.spinner{display:inline-block;width:16px;height:16px;border-radius:50%;border:2px solid rgba(0,0,0,0.08);border-top-color:var(--accent);animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (max-width:640px){ .header{flex-direction:column;align-items:flex-start} }
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="brand">
      <h1>API App — PythonAnywhere · PRO</h1>
      <div class="muted">Interfaz para la API oficial + utilidades del servidor</div>
    </div>
    <div class="controls">
      <button id="btn-refresh" class="btn light">Refresh</button>
      <button id="btn-clear" class="btn light">Clear</button>
       <a href="/ppamtools" class="btn" style="text-decoration:none; display:flex; align-items:center;">
    Panel</a><a href="/logout" class="btn" style="text-decoration:none; display:flex; align-items:center;">
    Salir
  </a>
    </div>
  </div>

  <div class="card-grid">
    <!-- Webapps -->
    <div class="card">
      <h3>Webapps</h3>
      <div class="muted">Listar / Detalles / Crear / Delete / Reload</div>
      <div class="row" style="margin-top:8px">
        <button id="btn-list-webapps" class="btn">List webapps</button>
        <button id="btn-create-webapp" class="btn light">Create</button>
      </div>
      <div class="list" id="webapps-list">Click List webapps</div>
    </div>

    <!-- Webapp actions -->
    <div class="card">
      <h3>Webapp actions</h3>
      <div class="muted">Seleccioná webapp (por domain o name)</div>
      <div style="margin-top:8px" class="row">
        <input id="input-webapp" placeholder="ppamappcaba.pythonanywhere.com" />
        <button id="btn-get-details" class="btn light">Details</button>
        <button id="btn-reload-webapp" class="btn">Reload</button>
        <button id="btn-delete-webapp" class="btn light">Delete</button>
      </div>
      <div id="webapp-detail" class="kv"></div>
    </div>

    <!-- Consoles -->
    <div class="card">
      <h3>Consoles</h3>
      <div class="muted">List / Create / Close</div>
      <div style="margin-top:8px" class="row">
        <button id="btn-list-consoles" class="btn">List</button>
        <button id="btn-create-console" class="btn light">Create bash</button>
      </div>
      <div id="consoles-list" class="list">No data</div>
    </div>

    <!-- Scheduled tasks -->
    <div class="card">
      <h3>Scheduled Tasks</h3>
      <div class="muted">List / Create / Run / Delete</div>
      <div style="margin-top:8px" class="row">
        <button id="btn-list-tasks" class="btn">List</button>
        <button id="btn-create-task" class="btn light">Create</button>
      </div>
      <div id="tasks-list" class="list">No data</div>
    </div>

    <!-- Files (server-side) -->
    <div class="card">
      <h3>File Manager (server)</h3>
      <div class="muted">List / View / Edit / Upload / Download / Delete</div>
      <div style="margin-top:8px" class="row">
        <input id="fm-path" placeholder="relative path (empty = root)" />
        <button id="btn-fm-list" class="btn">List</button>
        <input id="fm-upload" type="file" />
        <button id="btn-fm-upload" class="btn light">Upload</button>
      </div>
      <div id="fm-list" class="list">No data</div>
    </div>

    <!-- Logs & deploy -->
    <div class="card">
      <h3>Logs / Deploy / Run</h3>
      <div class="muted">View logs, git pull, run command</div>
      <div style="margin-top:8px" class="row">
        <button id="btn-logs" class="btn">View logs</button>
        <input id="deploy-dir" placeholder="repo dir (rel to root)" />
        <button id="btn-deploy" class="btn light">Git Pull</button>
      </div>
      <pre id="logs-area" class="list">No logs yet</pre>
    </div>

    <!-- Workers -->
    <div class="card">
      <h3>Workers</h3>
      <div class="muted">List / Create / Delete</div>
      <div style="margin-top:8px" class="row">
        <button id="btn-list-workers" class="btn">List</button>
      </div>
      <div id="workers-list" class="list">No data</div>
    </div>

    <!-- Dev utilities -->
    <div class="card">
      <h3>Utilities</h3>
      <div class="muted">Backup folder / Run script / Last response</div>
      <div style="margin-top:8px" class="row">
        <input id="backup-path" placeholder="path to backup (rel to root)" />
        <button id="btn-backup" class="btn">Backup</button>
        <input id="run-cmd" placeholder="command to run (relative)" />
        <button id="btn-run-cmd" class="btn light">Run</button>
      </div>
      <pre id="last-response" class="list">No response</pre>
    </div>

  </div>

  <footer class="footer">Equipo de desarrollo PPAM 2025 · ©</footer>
</div>

<script>
const el = id => document.getElementById(id);
let lastResponse = null;

async function call(path, opts){
  const res = await fetch("/apiapp" + path, opts);
  const text = await res.text();
  try {
    const j = JSON.parse(text);
    lastResponse = j;
    return {ok: res.ok, status: res.status, json: j};
  } catch (e){
    lastResponse = {status: res.status, text};
    return {ok: res.ok, status: res.status, text};
  }
}

/* Webapps */
el("btn-list-webapps").onclick = async ()=>{
  el("webapps-list").innerText = "Loading...";
  const r = await call("/api/webapps");
  if(!r.ok){ el("webapps-list").innerText = "Error: "+(r.json?r.json.error:r.text); return; }
  const data = r.json.data || r.json;
  el("webapps-list").innerHTML = data.map(w=>`<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${w.domain_name||w.name}</b><div class="muted small">python: ${w.python_version||'-'} • enabled: ${w.enabled}</div></div>`).join("");
};

el("btn-create-webapp").onclick = async ()=>{
  const domain = prompt("Domain name for new webapp (e.g. myapp.pythonanywhere.com)");
  const src = prompt("Source directory (absolute path, e.g. /home/you/mysite)");
  if(!domain || !src) return alert("cancelled");
  const body = {domain_name: domain, source_directory: src, python_version: "3.12"};
  const r = await call("/api/webapp/create", {method:"POST", body: JSON.stringify(body), headers: {'Content-Type':'application/json'}});
  el("webapps-list").innerText = JSON.stringify(r.json||r.text, null, 2);
};

el("btn-get-details").onclick = async ()=>{
  const name = el("input-webapp").value.trim();
  if(!name) return alert("enter webapp name");
  const r = await call("/api/webapp/" + encodeURIComponent(name) + "/details");
  el("webapp-detail").innerText = JSON.stringify(r.json||r.text, null, 2);
};

el("btn-reload-webapp").onclick = async ()=>{
  const name = el("input-webapp").value.trim();
  if(!name) return alert("enter webapp name");
  const r = await call("/api/webapp/" + encodeURIComponent(name) + "/reload", {method:"POST"});
  el("last-response").innerText = JSON.stringify(r.json||r.text, null, 2);
  alert("Reload requested (check PA dashboard)");
};

el("btn-delete-webapp").onclick = async ()=>{
  if(!confirm("Delete webapp? This is irreversible")) return;
  const name = el("input-webapp").value.trim();
  const r = await call("/api/webapp/" + encodeURIComponent(name) + "/delete", {method:"POST"});
  el("last-response").innerText = JSON.stringify(r.json||r.text, null, 2);
};

/* Consoles */
el("btn-list-consoles").onclick = async ()=>{
  const r = await call("/api/consoles");
  el("consoles-list").innerText = JSON.stringify(r.json||r.text, null, 2);
};
el("btn-create-console").onclick = async ()=>{
  const r = await call("/api/consoles", {method:"POST", body: new URLSearchParams({console_type:"bash"})});
  el("consoles-list").innerText = JSON.stringify(r.json||r.text, null, 2);
};

/* Tasks */
el("btn-list-tasks").onclick = async ()=>{
  const r = await call("/api/tasks");
  el("tasks-list").innerText = JSON.stringify(r.json||r.text, null, 2);
};
el("btn-create-task").onclick = async ()=>{
  const command = prompt("Command to run (e.g. python3 /home/.../script.py)");
  const schedule = prompt("Schedule (eg 'daily' or cron expression)","");
  const body = {command: command, schedule: schedule};
  const r = await call("/api/tasks", {method:"POST", body: JSON.stringify(body), headers:{'Content-Type':'application/json'}});
  el("tasks-list").innerText = JSON.stringify(r.json||r.text, null, 2);
};

/* File manager */
el("btn-fm-list").onclick = async ()=>{
  const p = el("fm-path").value.trim();
  const r = await call("/api/fs/list?p=" + encodeURIComponent(p));
  if(!r.ok) return el("fm-list").innerText = "Error: " + JSON.stringify(r.json||r.text);
  el("fm-list").innerHTML = r.json.items.map(i=>`<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${i.name}${i.is_dir?'/':''}</b> <button onclick="viewFile('${i.relpath}')">View</button> <button onclick="editFile('${i.relpath}')">Edit</button> <button onclick="downloadFile('${i.relpath}')">DL</button> <button onclick="deleteFile('${i.relpath}')">Del</button></div>`).join("");
};
async function viewFile(rel){
  const r = await call("/api/fs/view?path=" + encodeURIComponent(rel));
  if(!r.ok) return alert("Error: "+JSON.stringify(r.json||r.text));
  if(r.json.content) alert(r.json.content.substring(0,4000));
  else alert("Non-text file (download with DL)");
}
function editFile(rel){
  const val = prompt("Edit file: " + rel);
  if(val === null) return;
  fetch("/apiapp/api/fs/edit", {method:"POST", body: new URLSearchParams({path:rel, content: val})})
    .then(r=>r.json()).then(j=>{ alert(JSON.stringify(j)); });
}
function downloadFile(rel){
  window.location = "/apiapp/api/fs/download?path=" + encodeURIComponent(rel);
}
function deleteFile(rel){
  if(!confirm("Delete "+rel+"?")) return;
  fetch("/apiapp/api/fs/delete", {method:"POST", body: rel}).then(r=>r.json()).then(j=>{ alert(JSON.stringify(j)); el("btn-fm-list").click(); });
}
el("btn-fm-upload").onclick = async ()=>{
  const p = el("fm-path").value.trim();
  const f = el("fm-upload").files[0];
  if(!f) return alert("Choose file");
  const fd = new FormData();
  fd.append("p", p);
  fd.append("file", f);
  const res = await fetch("/apiapp/api/fs/upload", {method:"POST", body: fd});
  const j = await res.json();
  alert(JSON.stringify(j));
};

/* Logs / deploy / run */
el("btn-logs").onclick = async ()=>{
  const r = await call("/api/logs");
  if(!r.ok) return el("logs-area").innerText = "Error: " + JSON.stringify(r.json||r.text);
  el("logs-area").innerText = JSON.stringify(r.json||r.text, null, 2);
};
el("btn-deploy").onclick = async ()=>{
  const dir = el("deploy-dir").value.trim();
  if(!dir) return alert("dir required");
  const fd = new FormData(); fd.append("dir", dir);
  const r = await fetch("/apiapp/api/deploy", {method:"POST", body: fd});
  const j = await r.json();
  el("logs-area").innerText = JSON.stringify(j, null, 2);
};
el("btn-list-workers").onclick = async ()=>{
  const r = await call("/api/workers");
  el("workers-list").innerText = JSON.stringify(r.json||r.text, null, 2);
};

/* Backup & run */
el("btn-backup").onclick = async ()=>{
  const p = el("backup-path").value.trim();
  if(!p) return alert("path required");
  const fd = new FormData(); fd.append("p", p);
  const res = await fetch("/apiapp/api/fs/backup", {method:"POST", body: fd});
  if(!res.ok) return el("last-response").innerText = "Error";
  // initiate download
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a"); a.href = url; a.download = "backup.zip"; a.click();
  URL.revokeObjectURL(url);
};
el("btn-run-cmd").onclick = async ()=>{
  const cmd = el("run-cmd").value.trim();
  const cwd = "";// optionally add input
  if(!cmd) return alert("cmd required");
  const fd = new FormData(); fd.append("cmd", cmd); fd.append("cwd", cwd);
  const r = await fetch("/apiapp/api/run", {method:"POST", body: fd});
  const j = await r.json();
  el("last-response").innerText = JSON.stringify(j, null, 2);
};

/* utilities */
el("btn-refresh").onclick = ()=>location.reload();
el("btn-clear").onclick = ()=>{ el("webapps-list").innerText = ""; el("fm-list").innerText=""; el("last-response").innerText=""; };

</script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# Index route (renders template)
# -----------------------------------------------------------------------------
@apiapp_bp.route("/", methods=["GET"])
@login_required
@admin_required
def index():
    # warn if env not set
    if not PA_API_TOKEN or not PA_USERNAME:
        return render_template_string(INDEX_TEMPLATE.replace("No logs yet", "⚠️ Set PA_API_TOKEN and PA_USERNAME in environment variables (Dashboard → Account → Environment variables)"))
    return render_template_string(INDEX_TEMPLATE)
# ----- Proteger todo el archivo: --------------------------------
def protect_apiapp(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith("apiapp."):
            view = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = login_required(admin_required(view))
# End of file
