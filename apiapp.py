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
from flask import (
    Blueprint, request, jsonify, session,
    render_template, send_file
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
        return jsonify({"ok": True, "data": data})

    # POST → Crear consola
    payload = request.get_json() or request.form.to_dict() or {}
    console_type = payload.get("console_type", "bash")
    if console_type not in ("bash", "python"):
        return _json_error("console_type inválido", 400)

    data, err = pa_api("consoles/", method="POST", payload={"console_type": console_type})
    if err:
        return _json_error(err, 500)

    return jsonify({"ok": True, "data": data})
	
@apiapp_bp.route("/api/consoles/<console_id>/close", methods=["POST"])
def consoles_close(console_id):
    endpoint = f"consoles/{console_id}/"
    # pa_api hace POST por defecto al método 'POST'; usaremos DELETE emulado via requests
    url = f"{PA_BASE}/{PA_USERNAME}/{endpoint}"
    headers = {"Authorization": f"Token {PA_TOKEN}"}
    try:
        r = requests.delete(url, headers=headers, timeout=10)
    except Exception as e:
        return _json_error(f"Error conectando a PA: {e}", 500)

    if _detect_free_account(r.text):
        return _json_error("Cuenta FREE: no disponible", 403)

    try:
        j = r.json()
    except:
        j = {"raw_text": r.text[:2000]}

    if r.status_code in (200, 204):
        return jsonify({"ok": True, "data": j})
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

# ------------------------------------------------------------
# FS: listar
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/list", methods=["GET"])
def fs_list():
    p = request.args.get("p", "").strip("/")
    try:
        abs_path = _safe_path_rel(p)
    except ValueError:
        return _json_error("Path inválido", 403)

    if not os.path.exists(abs_path):
        return _json_error("No encontrado", 404)

    items = []
    try:
        for name in sorted(os.listdir(abs_path), key=lambda x: x.lower()):
            full = os.path.join(abs_path, name)
            try:
                st = os.stat(full)
                items.append({
                    "name": name,
                    "is_dir": os.path.isdir(full),
                    "size": st.st_size if os.path.isfile(full) else None,
                    "mtime": int(st.st_mtime),
                    "rel": os.path.relpath(full, BASE_ALLOWED_DIR).replace("\\","/")
                })
            except Exception:
                continue
    except Exception as e:
        return _json_error(f"Error leyendo directorio: {e}", 500)

    return jsonify({"ok": True, "items": items})


# ------------------------------------------------------------
# FS: view (text) / download (binary)
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/view", methods=["GET"])
def fs_view():
    path = request.args.get("path", "")
    try:
        abs_p = _safe_path_rel(path)
    except ValueError:
        return _json_error("Path inválido", 403)

    if not os.path.exists(abs_p):
        return _json_error("No encontrado", 404)

    if os.path.isdir(abs_p):
        return _json_error("Es un directorio", 400)

    if _is_text_file(abs_p):
        content = _read_file(abs_p)
        if content is None:
            return _json_error("No se pudo leer archivo", 500)
        return jsonify({"ok": True, "content": content})
    else:
        # archivo binario → enviar como attachment
        try:
            return send_file(abs_p, as_attachment=True)
        except Exception as e:
            return _json_error(f"Error enviando archivo: {e}", 500)


# ------------------------------------------------------------
# FS: edit (guardar texto)
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/edit", methods=["POST"])
def fs_edit():
    path = request.form.get("path") or request.json.get("path") if request.is_json else request.form.get("path")
    content = request.form.get("content") or (request.json.get("content") if request.is_json else None)
    if not path:
        return _json_error("path requerido", 400)
    try:
        abs_p = _safe_path_rel(path)
    except ValueError:
        return _json_error("Path inválido", 403)

    if os.path.isdir(abs_p):
        return _json_error("Es un directorio", 400)

    try:
        ok = _write_file(abs_p, content or "")
        if not ok:
            return _json_error("Error escribiendo archivo", 500)
    except Exception as e:
        return _json_error(f"Error escribiendo: {e}", 500)

    return jsonify({"ok": True})


# ------------------------------------------------------------
# FS: upload
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/upload", methods=["POST"])
def fs_upload():
    p = request.form.get("p", "").strip("/")
    try:
        abs_dir = _safe_path_rel(p)
    except ValueError:
        return _json_error("Path inválido", 403)

    if 'file' not in request.files:
        return _json_error("No file", 400)

    f = request.files['file']
    filename = secure_filename(f.filename)
    if not filename:
        return _json_error("Filename inválido", 400)

    dest = os.path.join(abs_dir, filename)
    try:
        os.makedirs(abs_dir, exist_ok=True)
        f.save(dest)
    except Exception as e:
        return _json_error(f"Error guardando archivo: {e}", 500)

    return jsonify({"ok": True, "path": os.path.relpath(dest, BASE_ALLOWED_DIR).replace("\\","/")})


# ------------------------------------------------------------
# FS: delete (file o carpeta)
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/delete", methods=["POST"])
def fs_delete():
    # acepta form.path o raw body con path
    path = request.form.get("path") or (request.get_data(as_text=True) or "").strip()
    if not path:
        return _json_error("path requerido", 400)
    try:
        abs_p = _safe_path_rel(path)
    except ValueError:
        return _json_error("Path inválido", 403)

    if not os.path.exists(abs_p):
        return _json_error("No encontrado", 404)

    try:
        if os.path.isdir(abs_p):
            shutil.rmtree(abs_p)
        else:
            os.remove(abs_p)
    except Exception as e:
        return _json_error(f"Error eliminando: {e}", 500)

    return jsonify({"ok": True})


# ------------------------------------------------------------
# FS: mkdir
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/mkdir", methods=["POST"])
def fs_mkdir():
    path = request.form.get("path") or (request.json.get("path") if request.is_json else None)
    if not path:
        return _json_error("path requerido", 400)
    try:
        abs_p = _safe_path_rel(path)
    except ValueError:
        return _json_error("Path inválido", 403)

    try:
        os.makedirs(abs_p, exist_ok=True)
    except Exception as e:
        return _json_error(f"Error creando carpeta: {e}", 500)

    return jsonify({"ok": True})


# ------------------------------------------------------------
# FS: download folder as zip
# ------------------------------------------------------------
@apiapp_bp.route("/api/fs/download", methods=["GET"])
def fs_download():
    path = request.args.get("path", "")
    try:
        abs_p = _safe_path_rel(path)
    except ValueError:
        return _json_error("Path inválido", 403)

    if not os.path.exists(abs_p):
        return _json_error("No encontrado", 404)

    if os.path.isfile(abs_p):
        try:
            return send_file(abs_p, as_attachment=True)
        except Exception as e:
            return _json_error(f"Error enviando archivo: {e}", 500)

    # Si es carpeta -> crear zip streaming en memoria
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(abs_p):
                for f in files:
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, abs_p)
                    zf.write(full, arcname)
        buf.seek(0)
        name = f"{Path(abs_p).name}.zip"
        return send_file(buf, as_attachment=True, download_name=name, mimetype="application/zip")
    except Exception as e:
        return _json_error(f"Error creando zip: {e}", 500)


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
# ============================================================

import subprocess


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

async function callApi(path, opts = {}) {
  try {
    const res = await fetch("/apiapp" + path, opts);
    const text = await res.text();
    // try parse JSON
    try {
      const json = JSON.parse(text);
      lastResp = {ok: res.ok, status: res.status, json};
      // normalized error handling: if PA feature disabled -> show it
      if (json && json.ok === false) {
        return {ok:false, status: res.status, json};
      }
      return {ok: res.ok, status: res.status, json};
    } catch (e) {
      lastResp = {ok: res.ok, status: res.status, text};
      return {ok: res.ok, status: res.status, text};
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
  alert(JSON.stringify(r.json || r.text || r.error, null, 2));
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
  el("consoles-list").innerHTML = items.map(c => `<div style="padding:6px;border-bottom:1px solid #f0f4f8"><b>ID: ${c.id}</b><div class="muted small">${c.console_type} • ${c.created}</div>
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
  if (!r.ok) { el("fm-list").innerText = "Error: " + (r.json?.error || r.text || r.error); showLast(); return; }
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
