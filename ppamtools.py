# ppamtools.py
# PPAM equpo de desarrolladores 
# 30/11/2025
import os
import json
import time
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    render_template,
    jsonify,
    request,
    Response,
    send_from_directory,
    current_app,
    abort,
)
from flask_login import login_required, current_user
from extensiones import db
from modelos import Publicador, Turno, SolicitudTurno
import psutil

# Carpeta para datos simples (notificaciones, chat, logs)
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "ppamtools_data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

NOTIF_FILE = os.path.join(DATA_DIR, "notificaciones.json")
CHAT_FILE = os.path.join(DATA_DIR, "chat.json")
LOG_FILE = os.path.join(DATA_DIR, "ppamtools.log")

# asegurar archivos
for f, empty in [(NOTIF_FILE, []), (CHAT_FILE, []), (LOG_FILE, "")]:
    if not os.path.exists(f):
        with open(f, "w", encoding="utf-8") as fh:
            if isinstance(empty, list):
                json.dump(empty, fh)
            else:
                fh.write(empty)

ppamtools_bp = Blueprint(
    "ppamtools",
    __name__,
    url_prefix="/ppamtools",
    template_folder="templates/ppamtools",
    static_folder="static/ppamtools",
)
# -------------------- Filtros --------------------
@ppamtools_bp.app_template_filter("getattr")
def jinja_getattr(obj, name, default=None):
    return getattr(obj, name, default)
# -------------------- Helpers --------------------
def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, default=str)


def _append_log(line):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(f"[{ts}] {line}\n")


# -------------------- Rutas UI --------------------
@ppamtools_bp.route("/")
@login_required
def dashboard():
    if current_user.rol != "Admin":
        abort(403)
    # Aseguramos que current_user tenga last_login (si no está en modelo puede ser None)
    return render_template("ppamtools/dashboard.html", current_user=current_user)


# -------------------- APIs: métricas y actividad --------------------
@ppamtools_bp.route("/api/metrics")
@login_required
def metrics():
    try:
        total_publicadores = Publicador.query.count()
    except Exception:
        total_publicadores = 0

    try:
        desde = datetime.now() - timedelta(days=30)
        asignaciones = Turno.query.filter(Turno.fecha >= desde.date()).count()
    except Exception:
        asignaciones = 0

    try:
        solicitudes = SolicitudTurno.query.filter_by(estado="Pendiente").count()
    except Exception:
        solicitudes = 0

    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent
        uptime_seconds = datetime.now().timestamp() - psutil.boot_time()
        uptime_h = round(uptime_seconds / 3600, 1)
    except Exception:
        cpu = mem = 0
        uptime_h = 0

    return jsonify({
        "publicadores": total_publicadores,
        "asignaciones": asignaciones,
        "solicitudes": solicitudes,
        "cpu": cpu,
        "mem": mem,
        "uptime": uptime_h,
    })


@ppamtools_bp.route("/api/activity")
@login_required
def activity():
    hoy = datetime.now().date()
    datos = []
    for i in range(7):
        dia = hoy - timedelta(days=i)
        try:
            count = Turno.query.filter(Turno.fecha == dia).count()
        except Exception:
            count = 0
        datos.append({"dia": dia.strftime("%d/%m"), "valor": count})
    datos.reverse()
    return jsonify(datos)


# -------------------- Notificaciones (SSE + polling fallback) --------------------
@ppamtools_bp.route("/notificaciones_stream")
@login_required
def notificaciones_stream():
    def event_stream(last_id=None):
        last_seen = int(last_id) if last_id else 0
        while True:
            notifs = _read_json(NOTIF_FILE)
            new = [n for n in notifs if n.get("id", 0) > last_seen]
            for n in new:
                last_seen = max(last_seen, n.get("id", 0))
                yield f"data: {json.dumps(n)}\n\n"
            time.sleep(1)

    last_id = request.args.get("last_id")
    return Response(event_stream(last_id), mimetype="text/event-stream")


@ppamtools_bp.route("/notificaciones_poll")
@login_required
def notificaciones_poll():
    notifs = _read_json(NOTIF_FILE)
    return jsonify(notifs[-10:])


# Endpoint para crear notificación (útil para otras partes de la app)
@ppamtools_bp.route("/notificaciones/push", methods=["POST"])
@login_required
def notificaciones_push():
    data = request.get_json() or {}
    texto = data.get("texto")
    if not texto:
        return jsonify({"ok": False, "error": "Falta texto"}), 400
    notifs = _read_json(NOTIF_FILE)
    nid = (notifs[-1]["id"] + 1) if len(notifs) else 1
    nuevo = {"id": nid, "texto": texto, "ts": datetime.now().isoformat(), "user": current_user.usuario}
    notifs.append(nuevo)
    _write_json(NOTIF_FILE, notifs)
    _append_log(f"Notificación añadida: {texto}")
    return jsonify({"ok": True, "notif": nuevo})


# -------------------- CHAT --------------------
@ppamtools_bp.route("/chat/get")
@login_required
def chat_get():
    msgs = _read_json(CHAT_FILE)
    # devolver últimos 200
    return jsonify(msgs[-200:])


@ppamtools_bp.route("/chat/enviar", methods=["POST"])
@login_required
def chat_enviar():
    data = request.get_json() or {}
    texto = (data.get("texto") or "").strip()
    if not texto:
        return jsonify({"ok": False, "error": "vacío"}), 400
    msgs = _read_json(CHAT_FILE)
    nuevo = {"id": (msgs[-1]["id"] + 1) if msgs else 1,
            "usuario": current_user.usuario,
            "texto": texto,
            "ts": datetime.now().isoformat()}
    msgs.append(nuevo)
    # mantener última 1000 entradas
    msgs = msgs[-1000:]
    _write_json(CHAT_FILE, msgs)
    _append_log(f"Chat: {current_user.usuario}: {texto}")
    return jsonify({"ok": True, "msg": nuevo})


# -------------------- LOGS --------------------
@ppamtools_bp.route("/logs")
@login_required
def logs():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as fh:
            txt = fh.read()
    except Exception:
        txt = ""
    return Response(txt, mimetype="text/plain; charset=utf-8")


@ppamtools_bp.route("/logs/limpiar", methods=["POST"])
@login_required
def logs_limpiar():
    try:
        open(LOG_FILE, "w", encoding="utf-8").close()
        _append_log("Logs limpiados por " + current_user.usuario)
    except Exception:
        pass
    return jsonify({"ok": True})


# -------------------- Archivos estáticos (si necesitás servir desde blueprint) --------------------
@ppamtools_bp.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static/ppamtools'), filename)


# FIN