# ============================================================
#  apiapp.py  —  VERSIÓN PRO (Parte 1 / 6)
#  Sistema integral PythonAnywhere WebApps / Consoles /
#  Workers / Scheduled Tasks / File manager / Deploy / Logs
# ============================================================
import os
import json
import time
import traceback
import requests
import shlex
import sqlite3
import subprocess
from functools import wraps
from flask import current_app
from flask import (
    Blueprint, request, jsonify, session,
    render_template, send_file, current_app
)
from datetime import datetime, timedelta
from pathlib import Path

# ------------------------------------------------------------
# BLUEPRINT PRINCIPAL
# ------------------------------------------------------------
apiapp_bp = Blueprint("apiapp_bp", __name__, url_prefix="/apiapp")

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
PA_BASE = "https://www.pythonanywhere.com/api/v0/user"
PA_USERNAME = os.getenv("PA_USERNAME", "")
PA_TOKEN = os.getenv("PA_API_TOKEN", "")
WSGI_FILE = "/var/www/ppamappcaba_pythonanywhere_com_wsgi.py"

# Para validar paths en FS
BASE_ALLOWED_DIR = os.path.expanduser("~/")

# ------------------------------------------------------------
# UTILIDADES
# ------------------------------------------------------------
# ============================================================
#   PythonAnywhere API — Wrapper PRO
# ============================================================

_LAST_PA_RESPONSE = None

def pa_api(path, method="GET", payload=None, raw=False):
    """
    Wrapper centralizado para consumir la API de PythonAnywhere.
    - Maneja token
    - Captura errores
    - Guarda última respuesta para debug
    """
    global _LAST_PA_RESPONSE

    url = f"{PA_BASE}/{PA_USERNAME}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Token {PA_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, timeout=12)
        elif method.upper() == "POST":
            r = requests.post(url, headers=headers, json=payload, timeout=12)
        elif method.upper() == "DELETE":
            r = requests.delete(url, headers=headers, timeout=12)
        else:
            return None, f"Método HTTP no soportado: {method}"

    except Exception as e:
        _LAST_PA_RESPONSE = str(e)
        return None, f"Error de conexión: {e}"

    _LAST_PA_RESPONSE = {
        "status": r.status_code,
        "text": r.text[:5000],
    }

    # Si PA devuelve HTML → token inválido, cuenta FREE o login requerido
    if r.headers.get("content-type", "").startswith("text/html"):
        return None, "PythonAnywhere devolvió HTML (login/token incorrecto o feature bloqueada)"
    # 🔥 Caso especial: DELETE devuelve 204 sin JSON
    # 🔥 Caso especial: DELETE devuelve 204 sin JSON
    if method.upper() == "DELETE" and r.status_code == 204:
        return {"ok": True, "message": "Eliminado correctamente"}, 200
    # Caso normal: parse JSON
    try:
        data = r.json()
        return data, None
    except Exception:
        return None, "Respuesta JSON inválida desde PythonAnywhere"

def _json_error(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code


def _safe_join(base, *paths):
    """Join seguro: evita escaparse del home."""
    new_path = os.path.abspath(os.path.join(base, *paths))
    if not new_path.startswith(base):
        raise ValueEr
# ============================================================
#  apiapp.py  —  VERSIÓN PRO (Parte 2 / 6)
#  Continúa: Consoles (POST/close), Webapps (list/details/reload/create/delete)
# ============================================================

# ------------------------------------------------------------
# Consoles - create (POST) and close
# ------------------------------------------------------------
@apiapp_bp.route("/api/consoles", methods=["GET", "POST"])
def api_consoles():
    if request.method == "GET":
        # Listar consolas
        data, err = pa_api("consoles/", method="GET")
        if err:
            return _json_error(err, 500)

        # PythonAnywhere devuelve:
        # - a veces {"consoles": [...]}
        # - a veces [...]
        if isinstance(data, dict):
            consoles = data.get("consoles", [])
        elif isinstance(data, list):
            consoles = data
        else:
            consoles = []

        return jsonify({"ok": True, "data": consoles})

    # POST → Crear consola
    payload = request.get_json() or request.form.to_dict() or {}
    console_type = payload.get("console_type", "bash")
    if console_type not in ("bash", "python"):
        return _json_error("console_type inválido", 400)

    data, err = pa_api("consoles/", method="POST", payload={"console_type": console_type})
    if err:
        return _json_error(err, 500)

    return jsonify({"ok": True, "data": data})
# -- Cerrar de una vez una de las benditas dos consolas que te permite PA ...
@apiapp_bp.route("/api/consoles/<console_id>/close", methods=["POST"])
def consoles_close(console_id):
    endpoint = f"consoles/{console_id}/"
    url = f"{PA_BASE}/{PA_USERNAME}/{endpoint}"
    headers = {"Authorization": f"Token {PA_TOKEN}"}
    
    try:
        r = requests.delete(url, headers=headers, timeout=10)
    except Exception as e:
        return _json_error(f"Error conectando a PA: {e}", 500)

    if r.status_code in (200, 204):
        # 🔹 Devuelve siempre JSON claro
        return jsonify({"ok": True, "message": "Consola cerrada correctamente"})

    # Intentar parsear JSON si no fue 200/204
    try:
        j = r.json()
    except:
        j = {"raw_text": r.text[:2000]}

    return _json_error(j.get("error", f"PA HTTP {r.status_code}"), 500)

# ------------------------------------------------------------
# Webapps - list, details, reload, create, delete
# ------------------------------------------------------------
_CACHE = {"webapps": {"ts": 0, "data": None}}
_CACHE_TTL = 45  # segundos

def _cached_webapps(force=False):
    now = time.time()
    if not force:
        it = _CACHE.get("webapps", {})
        if it.get("data") and (now - it.get("ts", 0) < _CACHE_TTL):
            return it["data"], None
    data, err = pa_api("webapps/")
    if err:
        return None, err
    _CACHE["webapps"]["data"] = data
    _CACHE["webapps"]["ts"] = now
    return data, None

@apiapp_bp.route("/api/webapps", methods=["GET"])
def webapps_list():
    force = request.args.get("force") == "1"
    data, err = _cached_webapps(force=force)
    if err:
        return _json_error(err, 403)
    # PA devuelve lista de webapps
    return jsonify({"ok": True, "data": data})

@apiapp_bp.route("/api/webapp/<name>/details", methods=["GET"])
def webapp_details(name):
    # intentar endpoint directo
    endpoint = f"webapps/{name}/"
    data, err = pa_api(endpoint)
    if err:
        # fallback: listar y buscar por domain_name o name
        all_data, all_err = _cached_webapps()
        if all_err:
            return _json_error(all_err, 403)
        for w in (all_data or []):
            if w.get("domain_name") == name or w.get("name") == name:
                return jsonify({"ok": True, "data": w})
        return _json_error("Webapp no encontrada", 404)
    return jsonify({"ok": True, "data": data})

@apiapp_bp.route("/api/webapp/<name>/reload", methods=["POST"])
def webapp_reload(name):
    # acepta domain o internal name
    # intento directo
    data, err = pa_api(f"webapps/{name}/reload/", method="POST")
    if err:
        # intento matching por domain_name
        all_data, all_err = _cached_webapps()
        if all_err:
            return _json_error(all_err, 403)
        for w in (all_data or []):
            if w.get("domain_name") == name:
                data2, err2 = pa_api(f"webapps/{w.get('name')}/reload/", method="POST")
                if err2:
                    return _json_error(err2, 500)
                return jsonify({"ok": True, "message": "Reload solicitado", "data": data2})
        return _json_error(err, 500)
    return jsonify({"ok": True, "message": "Reload solicitado", "data": data})

@apiapp_bp.route("/api/webapp/create", methods=["POST"])
def webapp_create():
    payload = request.get_json() or request.form.to_dict() or {}
    required = ("domain_name", "source_directory")
    if not all(payload.get(k) for k in required):
        return _json_error("domain_name y source_directory requeridos", 400)
    data, err = pa_api("webapps/", method="POST", data=payload)
    if err:
        return _json_error(err, 403)
    # invalidar cache
    _CACHE["webapps"]["data"] = None
    return jsonify({"ok": True, "data": data})

@apiapp_bp.route("/api/webapp/<name>/delete", methods=["POST"])
def webapp_delete(name):
    # DELETE emulado
    url = f"{PA_BASE}/{PA_USERNAME}/webapps/{name}/"
    headers = {"Authorization": f"Token {PA_TOKEN}"}
    try:
        r = requests.delete(url, headers=headers, timeout=10)
    except Exception as e:
        return _json_error(f"Error conectando a PA: {e}", 500)

    if _detect_free_account(r.text):
        return _json_error("Cuenta FREE: no disponible", 403)

    if r.status_code in (200, 204):
        _CACHE["webapps"]["data"] = None
        return jsonify({"ok": True})
    try:
        j = r.json()
        return _json_error(j.get("error", f"HTTP {r.status_code}"), 500)
    except:
        return _json_error(f"HTTP {r.status_code}: {r.text[:1000]}", 500)
# ============================================================
#  apiapp.py — VERSIÓN PRO (Parte 3 / 6)
#  Scheduled Tasks + Workers (corregido y estable)
# ============================================================

# ------------------------------------------------------------
# SCHEDULED TASKS
# ------------------------------------------------------------

@apiapp_bp.route("/api/tasks", methods=["GET"])
def tasks_list():
    data, err = pa_api("scheduled_tasks/")
    if err:
        return _json_error(err, 403)
    return jsonify({"ok": True, "data": data.get("tasks", [])})


@apiapp_bp.route("/api/tasks/<task_id>/run", methods=["POST"])
def tasks_run(task_id):
    endpoint = f"scheduled_tasks/{task_id}/run/"
    data, err = pa_api(endpoint, method="POST")
    if err:
        return _json_error(err, 403)
    return jsonify({"ok": True, "message": "Tarea ejecutada", "data": data})


@apiapp_bp.route("/api/tasks/<task_id>/delete", methods=["POST"])
def tasks_delete(task_id):
    # PythonAnywhere API para eliminar task requiere DELETE
    url = f"{PA_BASE}/{PA_USERNAME}/scheduled_tasks/{task_id}/"
    headers = {"Authorization": f"Token {PA_TOKEN}"}

    try:
        r = requests.delete(url, headers=headers, timeout=10)
    except Exception as e:
        return _json_error(f"Error conectando: {e}", 500)

    if _detect_free_account(r.text):
        return _json_error("Cuenta FREE: no disponible", 403)

    if r.status_code in (200, 204):
        return jsonify({"ok": True, "message": "Task eliminada"})

    try:
        j = r.json()
        return _json_error(j.get("error", f"HTTP {r.status_code}"), 500)
    except:
        return _json_error(f"HTTP {r.status_code}: {r.text[:500]}", 500)


# ------------------------------------------------------------
# WORKERS
# ------------------------------------------------------------
@apiapp_bp.route("/api/workers", methods=["GET"])
def workers_list():
    data, err = pa_api("workers/")
    if err:
        return _json_error(err, 403)
    return jsonify({"ok": True, "data": data.get("workers", [])})


@apiapp_bp.route("/api/workers/<name>/delete", methods=["POST"])
def workers_delete(name):
    # DELETE emulado manual
    url = f"{PA_BASE}/{PA_USERNAME}/workers/{name}/"
    headers = {"Authorization": f"Token {PA_TOKEN}"}

    try:
        r = requests.delete(url, headers=headers, timeout=10)
    except Exception as e:
        return _json_error(f"Error conectando: {e}", 500)

    if _detect_free_account(r.text):
        return _json_error("Cuenta FREE: no disponible", 403)

    if r.status_code in (200, 204):
        return jsonify({"ok": True, "message": f"Worker {name} eliminado"})

    try:
        j = r.json()
        return _json_error(j.get("error", f"HTTP {r.status_code}"), 500)
    except:
        return _json_error(f"HTTP {r.status_code}: {r.text[:500]}", 500)
# ============================================================
#  apiapp.py — VERSIÓN PRO (Parte 4 / 6)
#  FILE MANAGER (LIST / VIEW / EDIT / UPLOAD / DOWNLOAD / DELETE / MKDIR / MOVE)
# ============================================================

import io
import shutil
import zipfile
import mimetypes
from werkzeug.utils import secure_filename

# ---------- helpers de archivo ----------
TEXT_SUFFIXES = {'.txt', '.py', '.md', '.html', '.htm', '.css', '.js', '.json', '.csv', '.ini', '.cfg', '.log', '.sql', '.yml', '.yaml', '.env'}

def _is_text_file(path):
    return Path(path).suffix.lower() in TEXT_SUFFIXES

def _safe_path_rel(rel):
    """
    Devuelve ruta absoluta segura dentro de BASE_ALLOWED_DIR
    Acepta '' o '.' para root.
    """
    rel = (rel or "").lstrip("/").strip()
    try:
        return _safe_join(BASE_ALLOWED_DIR, rel)
    except ValueError as e:
        raise
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

#def is_text_file(path):
    #return Path(path).suffix.lower() in {'.txt','.py','.md','.html','.htm','.css','.js','.json','.csv','.ini','.cfg','.log','.sql','.yml','.yaml'}
# ------------------------------------------------------------
# FS: listar
# ------------------------------------------------------------
# ----------------------------------------------------------------------
# File Manager & local operations (PRO)
# ----------------------------------------------------------------------
# Lista archivos y carpetas
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/list", methods=["GET"])
def api_fs_list():
    p = request.args.get("p", "").strip("/")
    abs_path = safe_path(p)
    if not os.path.exists(abs_path):
        return jsonify({"ok": False, "error": "Not found"}), 404

    items = []
    try:
        names = sorted(os.listdir(abs_path), key=lambda s: s.lower())
        for name in names:
            full = os.path.join(abs_path, name)
            try:
                st = os.stat(full)
                items.append({
                    "name": name,
                    "is_dir": os.path.isdir(full),
                    "size": st.st_size if os.path.isfile(full) else None,
                    "mtime": int(st.st_mtime),
                    "relpath": os.path.relpath(full, BASE_ALLOWED_DIR).replace("\\","/")
                })
            except Exception:
                continue
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error leyendo directorio: {e}"}), 500

    return jsonify({"ok": True, "items": items})

# ------------------------------------------------------------
# Ver contenido de archivo de texto
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/view", methods=["GET"])
def api_fs_view():
    path = request.args.get("path", "")
    abs_p = safe_path(path)
    if not os.path.exists(abs_p):
        return jsonify({"ok": False, "error": "Not found"}), 404
    if os.path.isdir(abs_p):
        return jsonify({"ok": False, "error": "Is a directory"}), 400

    if not is_text_file(abs_p):
        return send_file(abs_p, as_attachment=True)

    try:
        with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"ok": True, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------------------------------------
# Editar archivo de texto
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/edit", methods=["POST"])
def api_fs_edit():
    path = request.form.get("path") or (request.json.get("path") if request.is_json else "")
    content = request.form.get("content") or (request.json.get("content") if request.is_json else "")
    abs_p = safe_path(path)
    if os.path.isdir(abs_p):
        return jsonify({"ok": False, "error": "Is a directory"}), 400

    try:
        with open(abs_p, "w", encoding="utf-8") as f:
            f.write(content or "")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------------------------------------
# Borrar archivo o carpeta
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/delete", methods=["POST"])
def api_fs_delete():
    path = request.form.get("path") or request.get_data(as_text=True).strip()
    if not path:
        return jsonify({"ok": False, "error": "path requerido"}), 400
    abs_p = safe_path(path)

    if not os.path.exists(abs_p):
        return jsonify({"ok": False, "error": "Not found"}), 404

    try:
        if os.path.isdir(abs_p):
            shutil.rmtree(abs_p)
        else:
            os.remove(abs_p)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------------------------------------
# Subir archivo
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/upload", methods=["POST"])
def api_fs_upload():
    p = request.form.get("p", "").strip("/")
    abs_dir = safe_path(p)
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400

    f = request.files['file']
    filename = secure_filename(f.filename)
    if not filename:
        return jsonify({"ok": False, "error": "Filename inválido"}), 400

    dest = os.path.join(abs_dir, filename)
    try:
        os.makedirs(abs_dir, exist_ok=True)
        f.save(dest)
        return jsonify({"ok": True, "relpath": os.path.relpath(dest, BASE_ALLOWED_DIR).replace("\\","/")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------------------------------------
# Descargar archivo o carpeta (zip si es carpeta)
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/download", methods=["GET"])
def api_fs_download():
    path = request.args.get("path", "")
    abs_p = safe_path(path)
    if not os.path.exists(abs_p):
        return jsonify({"ok": False, "error": "Not found"}), 404

    if os.path.isdir(abs_p):
        buf = io.BytesIO()
        try:
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(abs_p):
                    for f in files:
                        full = os.path.join(root, f)
                        arcname = os.path.relpath(full, abs_p).replace("\\","/")
                        zf.write(full, arcname)
            buf.seek(0)
            name = f"{Path(abs_p).name}.zip"
            return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")
        except Exception as e:
            return jsonify({"ok": False, "error": f"Error creando zip: {e}"}), 500
    else:
        return send_file(abs_p, as_attachment=True)

# ------------------------------------------------------------
# Crear backup (zip de carpeta)
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/backup", methods=["POST"])
def api_fs_backup():
    p = request.form.get("p", "").strip("/")
    abs_base = safe_path(p)
    name = f"backup_{Path(abs_base).name}_{int(time.time())}.zip"
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(abs_base):
                for f in files:
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, abs_base).replace("\\","/")
                    zf.write(full, arcname)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error creando backup: {e}"}), 500

# ------------------------------------------------------------
# FS: move / rename
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/move", methods=["POST"])
def fs_move():
    src = request.form.get("src") or (request.json.get("src") if request.is_json else None)
    dst = request.form.get("dst") or (request.json.get("dst") if request.is_json else None)
    if not src or not dst:
        return _json_error("src y dst requeridos", 400)
    try:
        abs_src = _safe_path_rel(src)
        abs_dst = _safe_path_rel(dst)
    except ValueError:
        return _json_error("Path inválido", 403)

    if not os.path.exists(abs_src):
        return _json_error("src no encontrado", 404)

    try:
        os.makedirs(os.path.dirname(abs_dst), exist_ok=True)
        shutil.move(abs_src, abs_dst)
    except Exception as e:
        return _json_error(f"Error moviendo: {e}", 500)

    return jsonify({"ok": True, "dst": os.path.relpath(abs_dst, BASE_ALLOWED_DIR).replace("\\","/")})
# ============================================================
#  apiapp.py — VERSIÓN PRO (Parte 5 / 6)
#  LOGS · DEPLOY · RUN COMMAND · BACKUP · DEBUG
# ===========================================================

# ============================================================
# LOGS
# ============================================================

LOG_CANDIDATES = [
    # Apache global PA (a veces accesible, a veces no)
    "/var/log/apache2/error.log",
    "/var/log/apache2/access.log",

    # Logs típicos de webapps en PythonAnywhere
    "/var/log/user.log",
    "/var/log/webapp_error.log",

    # Logs locales del proyecto
    "error.log",
    "server.log",
    "webapp_error.log",
]


@apiapp_bp.route("/api/logs", methods=["GET"])
def logs_get():
    """
    Devuelve los últimos ~200–300 lines de cada log disponible.
    """
    results = {}
    for p in LOG_CANDIDATES:
        try:
            abs_p = p
            if not os.path.isabs(p):
                abs_p = os.path.join(BASE_ALLOWED_DIR, p)

            if os.path.exists(abs_p):
                with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                results[p] = "".join(lines[-300:])
        except Exception:
            results[p] = "⚠ Error leyendo log"

    return jsonify({"ok": True, "logs": results})


# ============================================================
# DEPLOY (GIT PULL)
# ============================================================

@apiapp_bp.route("/api/deploy", methods=["POST"])
def deploy():
    """
    Ejecuta git pull dentro de un directorio seguro.
    """
    repo_dir = request.form.get("dir", "").strip("/")
    branch = request.form.get("branch", "main")

    try:
        abs_dir = _safe_path_rel(repo_dir)
    except ValueError:
        return _json_error("Directorio inválido", 403)

    if not os.path.exists(abs_dir):
        return _json_error("Directorio no encontrado", 404)

    try:
        p = subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=abs_dir,
            capture_output=True,
            text=True,
            timeout=120
        )
    except Exception as e:
        return _json_error(f"Error ejecutando git pull: {e}", 500)

    output = p.stdout + "\n" + p.stderr
    return jsonify({"ok": True, "returncode": p.returncode, "output": output})


# ============================================================
# RUN LOCAL COMMAND (limitado)
# ============================================================

ALLOWED_CMDS = {"python3", "pip", "ls", "git", "cat", "echo"}

@apiapp_bp.route("/api/run", methods=["POST"])
def run_command():
    """
    Ejecuta un comando limitado dentro del proyecto.
    Protección básica: solo comandos en ALLOWED_CMDS.
    """
    cmd = request.form.get("cmd", "").strip()
    cwd = request.form.get("cwd", "").strip("/")

    if not cmd:
        return _json_error("cmd requerido", 400)

    # seguridad: evitar comandos peligrosos
    exec_name = cmd.split()[0]
    if exec_name not in ALLOWED_CMDS:
        return _json_error(f"Comando '{exec_name}' no permitido", 403)

    try:
        abs_cwd = _safe_path_rel(cwd) if cwd else BASE_ALLOWED_DIR
    except ValueError:
        return _json_error("cwd inválido", 403)

    try:
        p = subprocess.run(
            cmd.split(),
            cwd=abs_cwd,
            capture_output=True,
            text=True,
            timeout=60
        )
    except Exception as e:
        return _json_error(f"Error ejecutando comando: {e}", 500)

    return jsonify({
        "ok": True,
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr
    })


# ============================================================
# BACKUP (ZIP)
# ============================================================

@apiapp_bp.route("/api/fs/backup", methods=["POST"])
def fs_backup():
    """
    Genera un ZIP de una carpeta completa.
    """
    rel = request.form.get("p", "").strip("/")
    if not rel:
        return _json_error("path requerido", 400)

    try:
        abs_base = _safe_path_rel(rel)
    except ValueError:
        return _json_error("Path inválido", 403)

    if not os.path.exists(abs_base):
        return _json_error("No encontrado", 404)

    buf = io.BytesIO()
    name = f"backup_{Path(abs_base).name}_{int(time.time())}.zip"

    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(abs_base):
                for f in files:
                    full = os.path.join(root, f)
                    arc = os.path.relpath(full, abs_base)
                    zf.write(full, arc)
        buf.seek(0)
    except Exception as e:
        return _json_error(f"Error creando ZIP: {e}", 500)

    return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")


# ============================================================
# DEBUG: última respuesta real obtenida desde PythonAnywhere API
# ============================================================

@apiapp_bp.route("/_debug/last_pa_response", methods=["GET"])
def debug_last_pa_response():
    """
    Devuelve la última respuesta real del request a PA API, útil
    cuando PA devuelve HTML diciendo “you must login”.
    """
    return jsonify({
        "ok": True,
        "last": _LAST_PA_RESPONSE,
        "username": PA_USERNAME,
        "token_present": bool(PA_TOKEN),
        "base_url": PA_BASE,
    })
# ----------------- Helpers para Databases & Domains (pegar en apiapp.py) -----------------
def require_pa_token(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not PA_TOKEN or not PA_USERNAME:
            return jsonify({"ok": False, "error": "PA_API_TOKEN or PA_USERNAME not configured in env"}), 500
        return func(*args, **kwargs)
    return wrapper
def api_response(data=None, message=None, status=200):
    body = {"ok": True}
    if data is not None:
        body["data"] = data
    if message:
        body["message"] = message
    return jsonify(body), status

def api_error(msg, status=400):
    return jsonify({"ok": False, "error": str(msg)}), status

def run_cmd(args, timeout=10):
    """Run command safely (args list). Return (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 255, "", str(e)

def sqlite_exec(db_path, query, fetch=True):
    """Execute SQL on sqlite DB safely. Returns rows or message."""
    try:
        con = sqlite3.connect(db_path, timeout=10)
        cur = con.cursor()
        cur.execute(query)
        if fetch:
            rows = cur.fetchall()
        else:
            rows = []
        con.commit()
        cur.close()
        con.close()
        return True, rows
    except Exception as e:
        return False, str(e)

# Paths helper: base dir for DBs under your safe root (so no surprises)
def get_db_base():
    # colocamos bases sqlite/mysql/postgres dentro del get_root() por seguridad
    base = os.path.join(get_root(), "databases")
    os.makedirs(base, exist_ok=True)
    return base

# ----------------- Endpoints: Databases -----------------
@apiapp_bp.route("/api/databases", methods=["GET"])
@require_pa_token
def api_databases_list():
    base = get_db_base()
    items = []

    # SQLite files (search in base/sqlite)
    sqlite_dir = os.path.join(base, "sqlite")
    if os.path.isdir(sqlite_dir):
        for f in sorted(os.listdir(sqlite_dir)):
            if f.endswith(".db"):
                items.append({"name": f, "type": "sqlite", "relpath": os.path.join("sqlite", f)})

    # MySQL & Postgres: these are best-effort entries (PA-managed DBs may not be filesystem-visible)
    # list MySQL databases by running `mysql -e 'SHOW DATABASES'` if mysql client exists
    code, out, err = run_cmd(["which", "mysql"], timeout=3)
    if code == 0:
        # try to list databases (uses no-password, will only work if client can auth)
        # NOTE: this may fail on PA free accounts; we return best-effort
        code2, out2, err2 = run_cmd(["mysql", "-e", "SHOW DATABASES;"], timeout=5)
        if code2 == 0:
            for line in out2.splitlines()[1:]:
                line = line.strip()
                if line:
                    items.append({"name": line, "type": "mysql"})
    # Postgres: similar attempt
    code, out, err = run_cmd(["which", "psql"], timeout=3)
    if code == 0:
        code2, out2, err2 = run_cmd(["psql", "-c", "\\l"], timeout=5)
        if code2 == 0:
            # best-effort: include raw output
            items.append({"name": "postgres_list (raw)", "type": "postgres", "raw": out2.splitlines()[:10]})

    return api_response(data=items)

@apiapp_bp.route("/api/databases", methods=["POST"])
@require_pa_token
def api_database_create():
    body = request.get_json() or request.form.to_dict() or {}
    name = (body.get("name") or "").strip()
    dbtype = (body.get("type") or "").strip().lower()
    if not name or not dbtype:
        return api_error("name and type required", 400)

    base = get_db_base()
    if dbtype == "sqlite":
        sqlite_dir = os.path.join(base, "sqlite")
        os.makedirs(sqlite_dir, exist_ok=True)
        path = os.path.join(sqlite_dir, f"{name}.db")
        if os.path.exists(path):
            return api_error("SQLite DB already exists", 409)
        open(path, "wb").close()
        return api_response(message="SQLite DB creada", data={"relpath": os.path.relpath(path, get_root()).replace("\\","/")})

    if dbtype == "mysql":
        # attempt to create database via mysql client (safer than os.system with formatted string)
        # This requires the mysql client to be authenticated; this may fail on PA free accounts.
        rc, out, err = run_cmd(["mysql", "-e", f"CREATE DATABASE `{name}`;"])
        if rc == 0:
            return api_response(message="MySQL DB creada")
        return api_error(f"MySQL error: {err or out}", 500)

    if dbtype == "postgres":
        rc, out, err = run_cmd(["createdb", name])
        if rc == 0:
            return api_response(message="Postgres DB creada")
        return api_error(f"Postgres error: {err or out}", 500)

    return api_error("Tipo no soportado", 400)

@apiapp_bp.route("/api/databases/delete", methods=["POST"])
@require_pa_token
def api_database_delete():
    body = request.get_json() or {}
    name = (body.get("name") or "").strip()
    if not name:
        return api_error("name required", 400)

    base = get_db_base()
    sqlite_path = os.path.join(base, "sqlite", f"{name}.db")
    if os.path.exists(sqlite_path):
        try:
            os.remove(sqlite_path)
            return api_response(message="SQLite DB eliminada")
        except Exception as e:
            return api_error(f"Error eliminando sqlite: {e}", 500)

    # try drop in MySQL
    rc, out, err = run_cmd(["mysql", "-e", f"DROP DATABASE IF EXISTS `{name}`;"])
    if rc == 0:
        return api_response(message="MySQL DB eliminada (si existía)")
    # fallback
    return api_error("No se encontró la DB o no se pudo eliminar", 404)

@apiapp_bp.route("/api/databases/sql", methods=["POST"])
@require_pa_token
def api_database_sql():
    body = request.get_json() or {}
    db = (body.get("db") or "").strip()
    query = (body.get("query") or "").strip()
    if not db or not query:
        return api_error("db and query required", 400)

    base = get_db_base()
    # SQLite
    sqlite_path = os.path.join(base, "sqlite", db if db.endswith(".db") else f"{db}.db")
    if os.path.exists(sqlite_path):
        ok, result = sqlite_exec(sqlite_path, query, fetch=True)
        if ok:
            return api_response(data=result)
        return api_error(result, 500)

    # MySQL: use mysql client to run query (best-effort)
    rc, out, err = run_cmd(["mysql", db, "-e", query], timeout=10)
    if rc == 0:
        # parse output into lines
        return api_response(data=out.splitlines())
    return api_error(err or out, 500)
# ----------------- Endpoints: Domains / WSGI / Static -----------------
@apiapp_bp.route("/api/domains", methods=["GET"])
@require_pa_token
def api_domains_list():
    # Best-effort: try PythonAnywhere API (if available) or fallback to local file
    try:
        resp, err = pa_api("domains/")
        if err:
            # fallback to local file or empty
            local = os.path.join(get_root(), "domains.json")
            if os.path.exists(local):
                with open(local, "r", encoding="utf-8") as f:
                    return api_response(data=json.load(f))
            return api_response(data=[])
        if resp.status_code == 200:
            try:
                return api_response(data=resp.json())
            except Exception:
                return api_error("Invalid JSON from PA", 502)
        return api_error(f"PA HTTP {resp.status_code}: {resp.text}", 502)
    except Exception as e:
        return api_error(str(e), 500)
# ---- WSGI FILES ----------------------
# ---- WSGI ----------------------------
@apiapp_bp.route("/api/webapp/<name>/wsgi", methods=["GET"])
def api_webapp_wsgi(name):
    """
    Obtiene el archivo WSGI real de PythonAnywhere SIN usar la API,
    porque la API de webapps está bloqueada en planes FREE.
    """
    filename = f"/var/www/{name}_pythonanywhere_com_wsgi.py"

    if not os.path.exists(filename):
        return api_error(f"WSGI file not found at {filename}", 404)

    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()

        return api_response(data={
            "wsgi_file": filename,
            "content": content
        })

    except Exception as e:
        return api_error(f"Could not read WSGI file: {e}", 500)

# --- STATIC FILES -------------
@apiapp_bp.route("/api/webapp/<name>/static", methods=["GET"])
@require_pa_token
def api_webapp_static(name):   

    # Ruta ABSOLUTA al static en PythonAnywhere
    STATIC_FOLDER = "/home/ppamappcaba/mysite/static"

    # Primero intentamos la API de PA
    try:
        data, err = pa_api(f"webapps/{name}/")
        if data and not err:
            static_maps = (
                data.get("static_files", []) or
                data.get("static_mappings", []) or
                []
            )
            if static_maps:
                # IMPORTANTE: formateamos la respuesta más bonito
                return api_response(data=static_maps)
    except Exception:
        pass

    # Fallback manual → recorremos el directorio estático real
    if os.path.isdir(STATIC_FOLDER):
        files = []
        for root, _, fs in os.walk(STATIC_FOLDER):
            for f in fs:
                relpath = os.path.relpath(
                    os.path.join(root, f),
                    STATIC_FOLDER
                ).replace("\\", "/")
                files.append(relpath)

        return api_response(data=files)

    # Si esto falla, realmente no existe
    return api_error("Static folder not found", 404)
# -------------------- GET ---------------------------------
@apiapp_bp.route("/api/webapp/<name>/wsgi", methods=["GET"])
def api_webapp_wsgi_get(name):
    """
    Lee y devuelve el archivo WSGI real de PythonAnywhere.
    """
    filename = f"/var/www/{name}_pythonanywhere_com_wsgi.py"

    if not os.path.exists(filename):
        return api_error(f"WSGI file not found at {filename}", 404)

    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()

        return api_response(data={
            "wsgi_file": filename,
            "content": content
        })

    except Exception as e:
        return api_error(f"Could not read WSGI file: {e}", 500)
# -------  GUARDAR ---------
@apiapp_bp.route("/api/webapp/<name>/wsgi", methods=["POST"])
def api_webapp_wsgi_save(name):
    """
    Guarda (sobrescribe) el archivo WSGI real.
    """
    filename = f"/var/www/{name}_pythonanywhere_com_wsgi.py"

    data = request.get_json(silent=True) or {}
    new_content = data.get("content")

    if not new_content:
        return api_error("Falta 'content' para guardar el WSGI", 400)

    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(new_content)

        return api_response(data={
            "saved": True,
            "wsgi_file": filename,
            "size": len(new_content)
        })

    except Exception as e:
        return api_error(f"No se pudo guardar el WSGI: {e}", 500)

# ============================================================
#  apiapp.py — VERSIÓN PRO (Parte 6 / 6)
#  Plantilla HTML integrada (index) + JS PRO + utilidades finales
# ============================================================

from flask import render_template_string

# ------------------------------------------------------------
# Aseguramos que exista la variable de debug (puede no haber sido llenada)
# ------------------------------------------------------------
if "_LAST_PA_RESPONSE" not in globals():
    _LAST_PA_RESPONSE = None

# ------------------------------------------------------------
# Plantilla HTML (inline) - UI ligera y JS PRO
# ------------------------------------------------------------
INDEX_HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>API App · PythonAnywhere · PRO</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"></script>
<style>
body{font-family:Arial,Helvetica,sans-serif;background:#f6f8fb;margin:0;color:#0b1220}
.app{max-width:1100px;margin:18px auto;padding:14px}
.header{display:flex;justify-content:space-between;align-items:center}
.btn{background:#0b74da;color:#fff;padding:8px 10px;border-radius:8px;border:none;cursor:pointer}
.btn.light{background:#e6eefc;color:#0b74da;border:1px solid #dbeafe}
.card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:14px}
.card{background:#fff;padding:12px;border-radius:10px;box-shadow:0 6px 18px rgba(11,20,34,0.04)}
.list{max-height:260px;overflow:auto;padding:8px;border-radius:8px;background:#fbfdff}
.muted{color:#6b7280;font-size:13px}
pre{white-space:pre-wrap;font-size:13px}
.small{font-size:13px}
.footer{margin-top:18px;color:#6b7280;text-align:center}
input, select, textarea{padding:8px;border-radius:8px;border:1px solid #e6eef5;width:100%}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div><h2 style="margin:0">API App — PythonAnywhere · PRO</h2><div class="muted">Usuario: {{ username }}</div></div>
    <div style="display:flex;gap:8px">
      <button id="btn-refresh" class="btn light">Refresh</button>
      <button id="btn-debug" class="btn">PA Debug</button>
    </div>
  </div>

  <div class="card-grid">

    <div class="card">
      <h3>Webapps</h3>
      <div class="muted small">List / Details / Reload / Create / Delete</div>
      <div style="margin-top:8px;display:flex;gap:8px">
        <button id="btn-list-webapps" class="btn">List webapps</button>
        <button id="btn-create-webapp" class="btn light">Create</button>
      </div>
      <div id="webapps-list" class="list">--</div>
    </div>

    <div class="card">
      <h3>Scheduled Tasks</h3>
      <div class="muted small">List / Create / Run / Delete</div>
      <div style="margin-top:8px;display:flex;gap:8px">
        <button id="btn-list-tasks" class="btn">List</button>
        <button id="btn-create-task" class="btn light">Create</button>
      </div>
      <div id="tasks-list" class="list">--</div>
    </div>

    <div class="card">
      <h3>Workers</h3>
      <div class="muted small">List / Delete</div>
      <div style="margin-top:8px">
        <button id="btn-list-workers" class="btn">List</button>
      </div>
      <div id="workers-list" class="list">--</div>
    </div>

    <div class="card">
      <h3>Consoles</h3>
      <div class="muted small">List / Create / Close</div>
      <div style="margin-top:8px">
        <button id="btn-list-consoles" class="btn">List</button>
        <button id="btn-create-console" class="btn light">Create bash</button>
      </div>
      <div id="consoles-list" class="list">--</div>
    </div>

    <div class="card">
      <h3>File Manager</h3>
      <div class="muted small">List / View / Edit / Upload / Download / Delete / Move</div>
      <div style="margin-top:8px;display:flex;gap:8px">
        <input id="fm-path" placeholder="relative path (empty = root)">
        <button id="btn-fm-list" class="btn">List</button>
      </div>
      <div class="list" id="fm-list">--</div>
    </div>

    <div class="card">
      <h3>Utilities</h3>
      <div class="muted small">Logs / Deploy / Run / Backup</div>
      <div style="margin-top:8px;display:flex;gap:8px">
        <button id="btn-logs" class="btn">View logs</button>
      </div>
      <pre id="logs-area" class="list">--</pre>
    </div>
<div class="card">
    <h2>Databases</h2>
    <p>Gestiona tus bases MySQL, Postgres y SQLite.</p>

    <button onclick="load_databases()">Listar Bases</button>
    <pre id="db_list"></pre>

    <h3>Crear Base</h3>
    <input id="new_db_name" placeholder="Nombre de la base">
    <select id="new_db_type">
      <option value="mysql">MySQL</option>
      <option value="postgres">Postgres</option>
      <option value="sqlite">SQLite</option>
    </select>
    <button onclick="create_database()">Crear</button>

    <h3>Eliminar Base</h3>
    <input id="del_db_name" placeholder="Nombre de la base">
    <button onclick="delete_database()">Eliminar</button>

    <h3>Ejecutar SQL</h3>
    <input id="sql_db_name" placeholder="Base">
    <textarea id="sql_query" placeholder="Ej: SELECT * FROM tabla"></textarea>
    <button onclick="exec_sql()">Ejecutar</button>
    <pre id="sql_result"></pre>
</div>

<div class="card">
    <h2>Domains / Static / WSGI</h2>
    <p>Herramientas avanzadas de webapps.</p>

    <button onclick="load_domains()">Listar Dominios</button>
    <pre id="domains_list"></pre>

    <h3>WSGI Config</h3>
    <input id="wsgi_app_name" placeholder="Nombre webapp">
    <button onclick="load_wsgi()">Ver WSGI</button>&nbsp;
    <button onclick="loadWSGI()">Cargar WSGI</button>
    <div id="wsgi-box" style="display:none;">
    <textarea id="wsgi-editor" style="width:100%;height:300px"></textarea>
    <br><button onclick="saveWSGI()">Guardar WSGI</button>
    </div>
    
    
    <pre id="wsgi_result"></pre>

    <h3>Static Files</h3>
    <input id="static_app_name" placeholder="Nombre webapp">
    <button onclick="load_static()">Ver Static Files</button>
    <pre id="static_result"></pre>
</div>
  </div>

  <div style="margin-top:12px">
    <h4>Last response (debug)</h4>
    <pre id="last-response" class="list"></pre>
  </div>

  <div class="footer">PPAM · API App PRO · 2025</div>
</div>

<script>
const el = id => document.getElementById(id);
let lastResp = null;
const api = axios.create({
    baseURL: '/apiapp/api',
    headers: {
        'Content-Type': 'application/json'
    }
});
async function callApi(path, opts = {}) {
  try {
    const res = await fetch("/apiapp" + path, opts);
    const text = await res.text();
    
    // Intentamos parsear JSON
    try {
      const json = JSON.parse(text);
      lastResp = {ok: res.ok, status: res.status, json};
      if (json && json.ok === false) return {ok:false, status: res.status, json};
      return {ok: res.ok, status: res.status, json};
    } catch (e) {
      // No es JSON → revisamos si es HTML de error de PA free
      let msg = text.match(/<h1>(.*?)<\/h1>/)?.[1] || "Error de servidor";
      let code = text.match(/Error code:\s*(.*?)<\/p>/)?.[1] || res.status;
      lastResp = {ok: false, status: res.status, text};
      return {ok: false, status: res.status, error: `Servidor respondió HTML: ${msg} (code: ${code})`, text};
    }

  } catch (e) {
    lastResp = {ok:false, error: e.toString()};
    return {ok:false, error: e.toString()};
  }
}


function showLast() {
  el("last-response").innerText = JSON.stringify(lastResp, null, 2);
}

// ---------------- Webapps ----------------
el("btn-list-webapps").onclick = async () => {
  el("webapps-list").innerText = "Loading...";
  const r = await callApi("/api/webapps");
  if (!r.ok) {
    el("webapps-list").innerText = "Error: " + (r.json?.error || r.text || r.error || "unknown");
    showLast();
    return;
  }
  const items = r.json.data || r.json || [];
  if (!items.length) {
    el("webapps-list").innerText = "(no webapps)";
    return;
  }
  el("webapps-list").innerHTML = items.map(w => {
    const name = w.domain_name || w.name || "";
    return `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${name}</b><div class="muted small">python:${w.python_version||'-'} enabled:${w.enabled}</div>
      <div style="margin-top:6px"><button class="btn light" onclick="showWebapp('${name}')">Details</button> <button class="btn" onclick="reloadWebapp('${name}')">Reload</button> <button class="btn light" onclick="deleteWebapp('${name}')">Delete</button></div></div>`;
  }).join("");
};

window.showWebapp = async (name) => {
  const r = await callApi("/api/webapp/" + encodeURIComponent(name) + "/details");
  if (!r.ok) return alert("Error: " + (r.json?.error || r.text));
  alert(JSON.stringify(r.json.data || r.json, null, 2));
};

window.reloadWebapp = async (name) => {
  const r = await callApi("/api/webapp/" + encodeURIComponent(name) + "/reload", { method: "POST" });
  if (!r.ok) return alert(r.error);
  alert(JSON.stringify(r.json || r.text, null, 2));
  el("btn-list-webapps").click();
};

window.deleteWebapp = async (name) => {
  if (!confirm("Delete webapp " + name + "?")) return;
  const r = await callApi("/api/webapp/" + encodeURIComponent(name) + "/delete", { method: "POST" });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-webapps").click();
};

el("btn-create-webapp").onclick = async () => {
  const domain = prompt("Domain (e.g. myapp.pythonanywhere.com)");
  const src = prompt("Source directory (e.g. /home/you/mysite)");
  if (!domain || !src) return;
  const body = { domain_name: domain, source_directory: src, python_version: "3.12" };
  const r = await callApi("/api/webapp/create", { method: "POST", headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-webapps").click();
};

// ---------------- Tasks ----------------
el("btn-list-tasks").onclick = async () => {
  el("tasks-list").innerText = "Loading...";
  const r = await callApi("/api/tasks");
  if (!r.ok) {
    el("tasks-list").innerText = "Error: " + (r.json?.error || r.text || r.error);
    showLast();
    return;
  }
  const items = r.json.data || [];
  if (!items.length) { el("tasks-list").innerText = "(no scheduled tasks)"; return; }
  el("tasks-list").innerHTML = items.map(t => `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${t.id}</b><div class="muted small">${t.command} • ${t.schedule}</div>
    <div style="margin-top:6px"><button class="btn" onclick="runTask('${t.id}')">Run</button> <button class="btn light" onclick="deleteTask('${t.id}')">Delete</button></div></div>`).join("");
};

window.runTask = async (id) => {
  const r = await callApi("/api/tasks/" + id + "/run", { method: "POST" });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-tasks").click();
};

window.deleteTask = async (id) => {
  if (!confirm("Delete task?")) return;
  const r = await callApi("/api/tasks/" + id + "/delete", { method: "POST" });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-tasks").click();
};

el("btn-create-task").onclick = async () => {
  const cmd = prompt("Command to run (e.g. python3 /home/.../script.py)");
  const schedule = prompt("Schedule (eg 'daily' or cron expression)", "");
  if (!cmd) return;
  const body = { command: cmd, schedule };
  const r = await callApi("/api/tasks", { method: "POST", headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-tasks").click();
};

// ---------------- Workers ----------------
el("btn-list-workers").onclick = async () => {
  el("workers-list").innerText = "Loading...";
  const r = await callApi("/api/workers");
  if (!r.ok) {
    el("workers-list").innerText = "Error: " + (r.json?.error || r.text || r.error);
    showLast();
    return;
  }
  const items = r.json.data || [];
  if (!items.length) { el("workers-list").innerText = "(no workers)"; return; }
  el("workers-list").innerHTML = items.map(w => `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${w.name}</b><div class="muted small">running:${w.running}</div>
    <div style="margin-top:6px"><button class="btn light" onclick="deleteWorker('${w.name}')">Delete</button></div></div>`).join("");
};

window.deleteWorker = async (name) => {
  if (!confirm("Delete worker "+ name +"?")) return;
  const r = await callApi("/api/workers/" + encodeURIComponent(name) + "/delete", { method: "POST" });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-workers").click();
};

// ---------------- Consoles ----------------
el("btn-list-consoles").onclick = async () => {
  el("consoles-list").innerText = "Loading...";
  const r = await callApi("/api/consoles");
  if (!r.ok) {
    el("consoles-list").innerText = "Error: " + (r.json?.error || r.text || r.error);
    showLast();
    return;
  }
  const items = r.json.data || [];
  if (!items.length) { el("consoles-list").innerText = "(no consoles)"; return; }
  el("consoles-list").innerHTML = items.map(c => `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>ID: ${c.id}</b><div class="muted small">${c.webapp || "(no informan tipo)"} • ${c.url || ""}</div>
    <div style="margin-top:6px"><button class="btn light" onclick="closeConsole('${c.id}')">Close</button></div></div>`).join("");
};

el("btn-create-console").onclick = async () => {
  const r = await callApi("/api/consoles", { method: "POST", headers: {'Content-Type':'application/json'}, body: JSON.stringify({console_type: "bash"}) });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-consoles").click();
};

window.closeConsole = async (id) => {
  const r = await callApi("/api/consoles/" + encodeURIComponent(id) + "/close", { method: "POST" });
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
  el("btn-list-consoles").click();
};

// ---------------- File Manager ----------------
el("btn-fm-list").onclick = async () => {
  el("fm-list").innerText = "Loading...";
  const p = el("fm-path").value.trim();
  const r = await callApi("/api/fs/list?p=" + encodeURIComponent(p));
  if (!r.ok) {
    // si es HTML (error de PA FREE o backend) mostramos mensaje reducido
    if (r.text && r.text.includes("<body>")) {
      const msg = r.text.match(/<h1>(.*?)<\/h1>/)?.[1] || "Error al listar";
      el("fm-list").innerText = `Error: ${msg}`;
    } else {
      el("fm-list").innerText = "Error: " + (r.json?.error || r.text || r.error);
    }
    showLast();
    return;
  }

  const items = r.json.items || [];
  if (!items.length) { el("fm-list").innerText = "(empty)"; return; }
  el("fm-list").innerHTML = items.map(i => `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>${i.name}${i.is_dir?'/':''}</b> <div class="muted small">size:${i.size||'-'} mtime:${new Date(i.mtime*1000).toLocaleString()}</div>
    <div style="margin-top:6px"><button class="btn light" onclick="viewFile('${i.rel}')">View</button> <button class="btn" onclick="downloadFile('${i.rel}')">DL</button> <button class="btn light" onclick="deleteFile('${i.rel}')">Del</button></div></div>`).join("");
};


window.viewFile = async (rel) => {
  const r = await callApi("/api/fs/view?path=" + encodeURIComponent(rel));
  if (!r.ok) return alert("Error: " + (r.json?.error || r.text || r.error));
  if (r.json.content) {
    const ok = confirm("Show file content? (OK = show, Cancel = copy to console)");
    if (ok) alert(r.json.content.substring(0, 10000));
  } else {
    alert("Binary file — use download");
  }
};

window.downloadFile = (rel) => {
  window.location = "/apiapp/api/fs/download?path=" + encodeURIComponent(rel);
};

window.deleteFile = async (rel) => {
  if (!confirm("Delete " + rel + "?")) return;
  const r = await fetch("/apiapp/api/fs/delete", { method: "POST", body: rel });
  const j = await r.json();
  alert(JSON.stringify(j, null, 2));
  el("btn-fm-list").click();
};

// ---------------- Logs / Deploy / Run / Backup ----------------
el("btn-logs").onclick = async () => {
  el("logs-area").innerText = "Loading...";
  const r = await callApi("/api/logs");
  if (!r.ok) { el("logs-area").innerText = "Error: " + (r.json?.error || r.text); showLast(); return; }
  el("logs-area").innerText = JSON.stringify(r.json, null, 2);
};

// ---------------- Misc ----------------
el("btn-refresh").onclick = () => location.reload();
el("btn-debug").onclick = async () => {
  const r = await callApi("/apiapp/_debug/last_pa_response");
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
};

window.addEventListener("beforeunload", () => {
  // nothing heavy; keep
});
// ----  DB ------------------------------------------------
async function load_databases() {
    const r = await api('/databases');
    document.getElementById('db_list').textContent = JSON.stringify(r, null, 2);
}
async function create_database() {
    const name = document.getElementById('new_db_name').value;
    const type = document.getElementById('new_db_type').value;
    const r = await api('/databases', {name, type});
    alert(JSON.stringify(r, null, 2));
    load_databases();
}
async function delete_database() {
    const name = document.getElementById('del_db_name').value;
    const r = await api('/databases/delete', {name});
    alert(JSON.stringify(r, null, 2));
    load_databases();
}
async function exec_sql() {
    const db = document.getElementById('sql_db_name').value;
    const query = document.getElementById('sql_query').value;
    const r = await api('/databases/sql', {db, query});
    document.getElementById('sql_result').textContent = JSON.stringify(r, null, 2);
}

async function load_domains() {
    const r = await api('/domains');
    document.getElementById('domains_list').innerHTML = `
  <pre style="
      background:#f7f7f9;
      padding:10px;
      border-radius:8px;
      white-space:pre-wrap;
  ">${JSON.stringify(r.data.data, null, 2)}</pre>
`;

}
function decodeEscapes(str) {
    try {
        // Convierte secuencias como \n, \t, \" en caracteres reales
        return JSON.parse(`"${str.replace(/"/g, '\\"')}"`);
    } catch {
        return str;
    }
}
function escapeHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

async function load_wsgi() {
    const app = document.getElementById('wsgi_app_name').value;
    const r = await api(`/webapp/${app}/wsgi`);
    
   // El contenido viene en "content"
    let content = r.json?.content || r.data?.content || r.data?.data;
    if (!content) {
        alert("Error: el backend no envió el contenido WSGI");
        console.error("WSGI JSON:", r.json);
        return;
    }
    if (typeof content !== "string") {
        console.warn("WSGI: content NO ES STRING:", content);
        content = JSON.stringify(content, null, 2);
    }

    // ✔ escapado HTML
    content = content
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    if (typeof content === "string") {
    content = decodeEscapes(content);
     }   
  document.getElementById('wsgi_result').innerHTML = `
  <pre style="
      background:#f7f7f9;
      padding:10px;
      border-radius:8px;
      white-space:pre-wrap;
  ">${content}</pre>
  
`;
el("wsgi-box").style.display = "none";
    el("wsgi_result").style.display = "block";
}

async function load_static() {
    const app = document.getElementById('static_app_name').value;
    const r = await api(`/webapp/${app}/static`);
  document.getElementById('static_result').innerHTML = `
  <pre style="
    background:#f7f7f9;
    padding:10px;
    border-radius:8px;
    white-space:pre-wrap;
  ">${JSON.stringify(r.data, null, 2)}</pre>
`;
}
async function loadWSGI() {
    const r = await callApi("/api/webapp/ppamappcaba/wsgi");
    if (!r.ok) return alert("Error: " + (r.json?.error || r.text));
    el("wsgi-editor").value = r.json.data.content;
    // mostrar el textarea recién ahora
    el("wsgi-box").style.display = "block";
    el("wsgi_result").style.display = "none";
}
async function saveWSGI() {
    const content = el("wsgi-editor").value;

    const r = await callApi("/api/webapp/ppamappcaba/wsgi", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content })
    });

    alert(JSON.stringify(r.json || r.error, null, 2));
}
</script>
</body>
</html>
"""

# ------------------------------------------------------------
# Re-definimos index para garantizar que la plantilla inline se use
# (si por alguna razón hubo una definición anterior esta la reemplaza)
# ------------------------------------------------------------
@apiapp_bp.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML, username=PA_USERNAME or "")

# ============================================================
# FIN del archivo apiapp.py — VERSIÓN PRO (Partes 1..6)
# ============================================================
