# ppamtools.py
# PPAM equpo de desarrolladores 
# 30/11/2025
import os
import json
import time 
import threading
import random
import re
import difflib
import psutil
from collections import deque, defaultdict
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


# Carpeta para datos simples (notificaciones, chat, logs)
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "ppamtools_data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

NOTIF_FILE = os.path.join(DATA_DIR, "notificaciones.json")
CHAT_FILE = os.path.join(DATA_DIR, "chat.json")
LOG_FILE = os.path.join(DATA_DIR, "ppamtools.log")
# --- Lock para escrituras seguras en CHAT_FILE ---
# Configurables
BOT_NAME = "PPAM-BOT"
MAX_CONTEXT = 6                   # mensajes previos a guardar por usuario
MIN_REPLY_DELAY = 0.6             # mínimo "typing" delay
MAX_REPLY_DELAY = 2.2             # máximo "typing" delay
USER_THROTTLE_SECONDS = 1.0       # evitar respuestas muy seguidas por usuario
CHAT_LOCK = threading.Lock()      # usar el mismo lock que ya tenías

# Memoria en RAM (no persistente): contexto y último reply time
BOT_CONTEXT = defaultdict(lambda: deque(maxlen=MAX_CONTEXT))
LAST_REPLY_AT = defaultdict(lambda: 0.0)

# Sinónimos y pequeñas plantillas
COMMANDS = {
    "/ayuda": "Comandos: /ayuda, /hoy, /publicadores, /pendientes, /actividad, /estado, /notif, /info <usuario>",
}

SYNONYMS = {
    "turno": ["turno", "turnos", "asignacion", "asignaciones", "asignar"],
    "actividad": ["actividad", "actividad semanal", "actividad semana", "semana", "hoy"],
    "publicadores": ["publicador", "publicadores", "usuarios", "cuantos publicadores"],
    "pendientes": ["pendiente", "pendientes", "solicitudes", "por resolver"],
    "estado": ["estado", "cpu", "memoria", "uptime", "servidor"],
    "notificaciones": ["notif", "notificacion", "notificaciones", "mensaje"],
    "saludo": ["hola", "buenas", "buen día", "buenas tardes", "buenas noches", "hey"],
    "agradecer": ["gracias", "grx", "muchas gracias"],
}


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

APP_OBJECT = {}   # será un contenedor mutado desde afuera
# se asignará cuando se registre el blueprint

# ----------------------- PPAM-BOT v4 -----------------------
# Bot humano, reglas + parsing simple, fuzzy, contexto pequeño,
# seguro para usar con threads (usa current_app.app_context()).
# --------------------- Bot V2 --------------------
# small helper functions
def _normalize(text):
    # lower, remove accents lightly, strip punctuation edges
    t = text.lower().strip()
    # remove repeated spaces
    t = re.sub(r'\s+', ' ', t)
    # remove accents (very simple)
    t = (t.replace('á','a').replace('é','e').replace('í','i')
           .replace('ó','o').replace('ú','u').replace('ñ','n'))
    return t

def _contains_keyword(text, keylist):
    t = _normalize(text)
    for k in keylist:
        if k in t:
            return True
    return False

def _fuzzy_match_word(word, candidates, cutoff=0.75):
    # devuelve True si `word` está cercano a alguno de candidates
    m = difflib.get_close_matches(word, candidates, n=1, cutoff=cutoff)
    return bool(m)

def _find_intent_by_keywords(text):
    t = _normalize(text)
    # direct command: exact match first
    if t in COMMANDS:
        return ("command", t)
    # check synonyms
    for intent, kws in SYNONYMS.items():
        if _contains_keyword(t, kws):
            return (intent, None)
    # try token fuzzy match
    words = [w for w in re.split(r'\W+', t) if w]
    for w in words:
        for intent, kws in SYNONYMS.items():
            if _fuzzy_match_word(w, kws, cutoff=0.8):
                return (intent, None)
    return (None, None)

# Core generator: devuelve texto (string) o None
def ppam_bot_v4_generate(user, texto):
    """
    Accede a modelos DB (Publicador, Turno, SolicitudTurno) y a NOTIF_FILE.
    Debe ejecutarse DENTRO de app_context si usa DB (threads).
    """
    if not texto:
        return None

    t = _normalize(texto)

    # 1) comandos directos con slash
    if t.startswith("/"):
        parts = t.split()
        cmd = parts[0]
        arg = " ".join(parts[1:]) if len(parts) > 1 else ""
        # comandos simples
        if cmd == "/ayuda" or cmd == "/help":
            return COMMANDS["/ayuda"]
        if cmd == "/hoy":
            try:
                hoy = datetime.now().date()
                n = Turno.query.filter(Turno.fecha == hoy).count()
                return f"Asig. hoy ({hoy}): {n}"
            except Exception as e:
                current_app.logger.exception("bot /hoy error")
                return "No pude obtener las asignaciones del día."
        if cmd == "/publicadores":
            try:
                n = Publicador.query.count()
                return f"Publicadores: {n}"
            except Exception:
                current_app.logger.exception("bot /publicadores error")
                return "No pude leer la cantidad de publicadores."
        if cmd == "/pendientes":
            try:
                ahora = datetime.now().time()
                pendientes = (
                    SolicitudTurno.query
                    .filter(SolicitudTurno.hora_inicio >= ahora)
                    .order_by(SolicitudTurno.hora_inicio)
                    .limit(10)
                    .all()
                )

                if not pendientes:
                    return "No hay solicitudes pendientes para lo que queda del día."

                filas = [
                    f"{p.hora_inicio.strftime('%H:%M')} — ID {p.id}"
                    for p in pendientes
                ]

                return "⏳ Pendientes de hoy:\n" + "\n".join(filas)

            except Exception as e:
                print("ERROR /pendientes:", e)
                return "Error al consultar solicitudes pendientes."
        if cmd == "/actividad":
            try:
                hoy = datetime.now().date()
                partes = []
                for i in range(6, -1, -1):
                    dia = hoy - timedelta(days=i)
                    q = Turno.query.filter(Turno.fecha == dia).count()
                    partes.append(f"{dia.strftime('%d/%m')}: {q}")
                return "Actividad (7d): " + " | ".join(partes)
            except Exception:
                current_app.logger.exception("bot /actividad error")
                return "No pude obtener la actividad semanal."
        if cmd == "/estado":
            try:
                cpu = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory().percent
                uptime_h = round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 1)
                return f"Estado — CPU: {cpu}% | Mem: {mem}% | Uptime: {uptime_h}h"
            except Exception:
                current_app.logger.exception("bot /estado error")
                return "No pude obtener el estado del servidor."
        if cmd == "/notif":
            try:
                notifs = _read_json(NOTIF_FILE)[-5:]
                if not notifs:
                    return "No hay notificaciones recientes."
                return "Últimas: " + " // ".join(n.get("texto","(sin texto)") for n in notifs)
            except Exception:
                current_app.logger.exception("bot /notif error")
                return "No pude leer las notificaciones."
        if cmd == "/info" and arg:
            # ejemplo: /info admin Buscar info de usuario (simple)
            try:
                userq = Publicador.query.filter_by(usuario=arg).first()
                if not userq:
                    return f"No encontré usuario '{arg}'."
                # ajusta campos según tu modelo
                return f"Usuario {userq.usuario} — rol: {getattr(userq,'rol','-')}"
            except Exception:
                current_app.logger.exception("bot /info error")
                return "Error consultando usuario."
        # desconocido
        return "Comando no reconocido. Escribí /ayuda."

    # 2) Intent detection por keywords / fuzzy
    intent, _ = _find_intent_by_keywords(texto)

    # SALUDOS
    if intent == "saludo":
        return random.choice(["Hola 👋", "¡Hola! ¿Cómo puedo ayudar?", "Buenas — ¿qué necesitás?"])

    if intent == "agradecer":
        return random.choice(["¡De nada!", "Con gusto 😊", "A la orden."])

    if intent == "turno":
        # sugerir /hoy o /actividad
        return "¿Querés ver asignaciones? Probá: /hoy o /actividad."

    if intent == "actividad":
        # intentar devolver resumen (misma lógica que /actividad)
        try:
            hoy = datetime.now().date()
            partes = []
            for i in range(6, -1, -1):
                dia = hoy - timedelta(days=i)
                q = Turno.query.filter(Turno.fecha == dia).count()
                partes.append(f"{dia.strftime('%d/%m')}: {q}")
            return "Actividad (7d): " + " | ".join(partes)
        except Exception:
            current_app.logger.exception("bot actividad error")
            return "No pude obtener la actividad semanal."

    if intent == "publicadores":
        try:
            n = Publicador.query.count()
            return f"Ahora hay {n} publicadores."
        except Exception:
            current_app.logger.exception("bot publicadores error")
            return "No pude leer la cantidad de publicadores."

    if intent == "pendientes":
        try:
            n = SolicitudTurno.query.filter_by(estado="Pendiente").count()
            return f"Solicitudes pendientes: {n}"
        except Exception:
            current_app.logger.exception("bot pendientes error")
            return "No pude consultar las solicitudes pendientes."

    if intent == "estado":
        try:
            cpu = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory().percent
            uptime_h = round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 1)
            return f"Servidor — CPU: {cpu}% | Mem: {mem}% | Uptime: {uptime_h}h"
        except Exception:
            current_app.logger.exception("bot estado error")
            return "No pude obtener el estado del servidor."

    if intent == "notificaciones":
        try:
            notifs = _read_json(NOTIF_FILE)[-5:]
            if not notifs:
                return "No hay notificaciones recientes."
            return "Últimas: " + " // ".join(n.get("texto","(sin texto)") for n in notifs)
        except Exception:
            current_app.logger.exception("bot notif error")
            return "No pude leer las notificaciones."

    # 3) fallback humano y sugerencias
    # si el texto parece pregunta corta:
    if len(texto.split()) <= 4 and texto.endswith("?"):
        return "Buena pregunta — probá con /ayuda o escribí más detalles."

    # respuestas amigables por defecto (varias frases humanas)
    fallbacks = [
        "No entendí del todo 🤔 — intentá con /ayuda.",
        "No lo pillé. Podés usar /hoy, /publicadores o /pendientes.",
        "Lo siento, no estoy seguro. Escribí /ayuda para ver comandos."
    ]
    return random.choice(fallbacks)
# --- respond_in_background corregida para V4 ---
def respond_in_background(user, trigger_text, delay=0.8):
    """
    Ejecuta la respuesta del bot en un thread seguro para PythonAnywhere.
    Usa APP_OBJECT en lugar de current_app.
    """
    def worker():
        print("BOT THREAD STARTED", user, trigger_text)
        print(">>> APP_OBJECT asignado:", APP_OBJECT["app"])
        try:
            if "app" not in APP_OBJECT:
                print("BOT: APP_OBJECT sigue sin app")
                return

            # throttle
            now = time.time()
            last = LAST_REPLY_AT.get(user, 0)
            if now - last < USER_THROTTLE_SECONDS:
                return

            # typing delay
            simulated = min(MAX_REPLY_DELAY, MIN_REPLY_DELAY + len(trigger_text) * 0.02)
            time.sleep(simulated)

            # Usamos app.app_context() — NO current_app
            
            flask_app = APP_OBJECT["app"]
            with flask_app.app_context():
            # ... aquí sigue tu código 
            # with APP_OBJECT.app_context():
                respuesta = ppam_bot_v4_generate(user, trigger_text)
                if not respuesta:
                    return

                # escribir mensaje del bot
                with CHAT_LOCK:
                    msgs = _read_json(CHAT_FILE)
                    new_id = (msgs[-1].get("id", 0) if msgs else 0) + 1
                    msgs.append({
                        "id": new_id,
                        "usuario": BOT_NAME,
                        "texto": respuesta,
                        "ts": datetime.now().isoformat()
                    })
                    msgs = msgs[-1000:]
                    _write_json(CHAT_FILE, msgs)
                    _append_log(f"{BOT_NAME} respondió a {user}: {respuesta}")

                LAST_REPLY_AT[user] = time.time()

        except Exception as e:
            print("ERROR en hilo BOT:", e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()


# ---------------------------------------------------------
# Fin PPAM-BOT v4
# ---------------------------------------------------------
# -------------------- Filtros --------------------
@ppamtools_bp.app_template_filter("getattr")
def jinja_getattr(obj, name, default=None):
    return getattr(obj, name, default)
# -------------------- Helpers --------------------
# ---------------  Leer JASON --------------------------------

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
    return jsonify({"error": "SSE deshabilitado en PythonAnywhere. Usar /notificaciones_poll"})

@ppamtools_bp.route("/notificaciones_poll")
@login_required
def notificaciones_poll():
    try:
        notifs = _read_json(NOTIF_FILE)
        if not isinstance(notifs, list):
            notifs = []
    except Exception as e:
        _append_log(f"[WARN] notificaciones_poll error: {e}")
        notifs = []
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
# --- Chat un poco mas constestador :) ----------------
@ppamtools_bp.route("/chat/enviar", methods=["POST"])
@login_required
def chat_enviar():
    data = request.get_json() or {}
    texto = data.get("texto", "").strip()

    if not texto:
        return jsonify({"status": "error", "msg": "Texto vacío"}), 400

    # 1. Guardar mensaje del usuario
    msgs = _read_json(CHAT_FILE)
    nuevo_id = (msgs[-1].get("id", 0) + 1) if msgs else 1
    nuevo = {
        "id": nuevo_id,
        "usuario": current_user.usuario,
        "texto": texto,
        "ts": datetime.now().isoformat()
    }
    msgs.append(nuevo)
    msgs = msgs[-1000:]
    _write_json(CHAT_FILE, msgs)

    # 2. BOT en background
    try:
        respond_in_background(current_user.usuario, texto)
    except Exception:
        current_app.logger.exception("No se pudo lanzar hilo del bot")

    return jsonify({"status": "ok"})
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
# -------------- LOGS LIMPIAR ------------------------
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