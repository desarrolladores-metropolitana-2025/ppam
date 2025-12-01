# ppamtools.py
# PPAM equpo de desarrolladores 
# 30/11/2025
import os
import json
import time
import threading
import random
import difflib
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
# --- Lock para escrituras seguras en CHAT_FILE ---
CHAT_LOCK = threading.Lock()

# --- Pequeña memoria en memoria (contexto por usuario), no persistente ---
BOT_CONTEXT = {}  # clave: usuario -> {"last_messages": [...], "last_reply": ts}

# --- Diccionarios de sinónimos / patrones simples ---
INTENTS = {
    "greeting": ["hola", "buenos", "buenas", "saludos", "hey", "holaa"],
    "thanks": ["gracias", "graciass", "muchas gracias", "grx"],
    "help": ["ayuda", "help", "soporte", "cómo hago", "como hago", "qué hago"],
    "turno": ["turno", "turnos", "asignación", "asignaciones"],
    "publicadores": ["publicadores", "punlicadores", "publicador", "usuarios"],
    "pendientes": ["pendiente", "pendientes", "solicitudes", "pendencias"],
    "actividad": ["actividad", "hoy", "semana"],
    "estado": ["cpu", "memoria", "uptime", "estado", "servidor"],
    "notificaciones": ["notifix", "notifica", "notificaciones", "notif", "notif."],
}

# respuestas tipo "humanas" con variaciones
TEMPLATES = {
    "greeting": ["¡Hola! ¿Qué tal?", "Hola 👋, ¿en qué puedo ayudarte?", "¡Buenas! ¿Cómo te va?"],
    "thanks": ["¡De nada!", "Con gusto 😊", "A la orden."],
    "no_understand": [
        "Perdón, no entendí bien. Podés escribir /ayuda para los comandos.",
        "Mmm, no estoy seguro — probá con /ayuda.",
        "No lo pillé. Si querés, escribí /ayuda."
    ],
    "help": [
        "Puedo darte información rápida del sistema. Escribí /ayuda para ver los comandos.",
        "Si necesitás algo, intentá con: /hoy, /publicadores, /pendientes, /estado, /notif."
    ],
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
# --------------------- Bot V2 --------------------
# --- Función util: buscar intención por token fuzzy/simple ---
def detect_intent(text):
    t = text.lower()
    tokens = [tok for tok in difflib.SequenceMatcher().get_matching_blocks()]  # placeholder no usado
    # simple check: look for keywords
    scores = {}
    for intent, keywords in INTENTS.items():
        for kw in keywords:
            if kw in t:
                scores[intent] = scores.get(intent, 0) + 1
    # fallback: fuzzy match words
    if not scores:
        words = [w for w in t.split() if len(w) > 2]
        for w in words:
            for intent, keywords in INTENTS.items():
                m = difflib.get_close_matches(w, keywords, n=1, cutoff=0.8)
                if m:
                    scores[intent] = scores.get(intent, 0) + 0.5
    if not scores:
        return None
    # return intent with highest score
    return max(scores.items(), key=lambda x: x[1])[0]

# --- Bot "cerebro" que genera texto (usa DB/models) ---
def ppam_bot_v2_generate(user, texto):
    """
    Devuelve una respuesta string o None.
    Accede a modelos: Publicador, Turno, SolicitudTurno, NOTIF_FILE y psutil.
    """
    if not texto:
        return None

    intent = detect_intent(texto)

    # respuestas por intent (prioridad)
    try:
        if intent == "greeting":
            return random.choice(TEMPLATES["greeting"])

        if intent == "thanks":
            return random.choice(TEMPLATES["thanks"])

        if intent == "help":
            return random.choice(TEMPLATES["help"])

        if intent == "publicadores":
            try:
                n = Publicador.query.count()
                return random.choice([
                    f"Ahora mismo hay {n} publicadores registrados.",
                    f"Tenemos {n} publicadores en el sistema."
                ])
            except Exception:
                return "No pude leer la cantidad de publicadores."

        if intent == "pendientes":
            try:
                n = SolicitudTurno.query.filter_by(estado="Pendiente").count()
                return f"Hay {n} solicitudes pendientes."
            except Exception:
                return "No pude leer las solicitudes pendientes."

        if intent == "turno":
            try:
                hoy = datetime.now().date()
                n = Turno.query.filter(Turno.fecha == hoy).count()
                return f"Asignaciones para hoy ({hoy}): {n}."
            except Exception:
                return "Error consultando asignaciones del día."

        if intent == "actividad":
            try:
                hoy = datetime.now().date()
                partes = []
                for i in range(6, -1, -1):  # últimos 7 días
                    dia = hoy - timedelta(days=i)
                    q = Turno.query.filter(Turno.fecha == dia).count()
                    partes.append(f"{dia.strftime('%d/%m')}: {q}")
                return "Actividad (7d): " + " | ".join(partes)
            except Exception:
                return "No pude obtener la actividad semanal."

        if intent == "estado":
            try:
                cpu = psutil.cpu_percent(interval=0.5)
                mem = psutil.virtual_memory().percent
                uptime_h = round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 1)
                return f"Servidor — CPU: {cpu}% | Mem: {mem}% | Uptime: {uptime_h}h"
            except Exception:
                return "No pude obtener el estado del servidor."

        if intent == "notificaciones":
            try:
                n = _read_json(NOTIF_FILE)[-5:]
                if not n:
                    return "No hay notificaciones recientes."
                return "Últimas: " + " // ".join(x.get("texto","(sin texto)") for x in n)
            except Exception:
                return "No pude leer las notificaciones."
    except Exception as e:
        # no queremos que el bot cause 500s
        current_app.logger.exception("Error en ppam_bot_v2_generate")
        return None

    # Si no hay intención clara, realizar respuestas por keyword o fallback
    t = texto.lower()
    if "hola" in t:
        return random.choice(TEMPLATES["greeting"])
    if "gracias" in t:
        return random.choice(TEMPLATES["thanks"])

    # fallback: 20% chance to give a helpful hint
    if random.random() < 0.2:
        return "Lo siento, no entendí bien — probá escribir /ayuda para ver comandos."

    return None
# ======================================================
# PPAM-BOT v3 — Unificado, humano, con COMANDOS y fuzzy
# ======================================================

COMMANDS = {
    "/ayuda": "Comandos disponibles:\n"
              "• /ayuda – muestra este mensaje\n"
              "• /hoy – asignaciones del día\n"
              "• /pendientes – solicitudes sin resolver\n"
              "• /publicadores – cantidad total\n"
              "• /actividad – actividad semanal\n"
              "• /estado – CPU, RAM y uptime del servidor\n"
              "• /notif – últimas notificaciones",
}

def ppam_bot_v3(user, texto):
    t = texto.lower().strip()

    # -----------------------------
    # COMANDOS DIRECTOS
    # -----------------------------
    if t in COMMANDS:
        return COMMANDS[t]

    if t == "/publicadores":
        try:
            n = Publicador.query.count()
            return f"Actualmente hay {n} publicadores registrados."
        except:
            return "No pude obtener la lista de publicadores."

    if t == "/pendientes":
        try:
            n = SolicitudTurno.query.filter_by(estado="Pendiente").count()
            return f"Solicitudes pendientes: {n}."
        except:
            return "Error al consultar solicitudes pendientes."

    if t == "/hoy":
        try:
            hoy = datetime.now().date()
            n = Turno.query.filter(Turno.fecha == hoy).count()
            return f"Asignaciones del día ({hoy}): {n}"
        except:
            return "No pude obtener las asignaciones del día."

    if t == "/actividad":
        try:
            hoy = datetime.now().date()
            partes = []
            for i in range(6, -1, -1):
                dia = hoy - timedelta(days=i)
                q = Turno.query.filter(Turno.fecha == dia).count()
                partes.append(f"{dia.strftime('%d/%m')}: {q}")
            return "Actividad (7 días):\n" + "\n".join(partes)
        except:
            return "No pude obtener la actividad semanal."

    if t == "/estado":
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            uptime_h = round((datetime.now().timestamp() - psutil.boot_time()) / 3600, 1)
            return f"Estado del servidor:\nCPU: {cpu}%\nMemoria: {mem}%\nUptime: {uptime_h} hs"
        except:
            return "No pude obtener el estado del servidor."

    if t == "/notif":
        try:
            notifs = _read_json(NOTIF_FILE)[-5:]
            if not notifs:
                return "No hay notificaciones recientes."
            return "Últimas notificaciones:\n" + "\n".join(f"- {n['texto']}" for n in notifs)
        except:
            return "No pude leer las notificaciones."

    # -----------------------------
    # RESPUESTAS HUMANAS
    # -----------------------------
    if "hola" in t:
        return random.choice(["Hola 👋", "¡Hola! ¿Qué tal?", "¡Buenas! ¿En qué te ayudo?"])

    if "gracias" in t:
        return random.choice(["¡De nada!", "Cuando quieras 😊", "A la orden."])

    if "ayuda" in t:
        return "Podés escribir /ayuda para ver lo que puedo hacer."

    if "turno" in t:
        return "Para turnos podés usar /hoy o /actividad."

    # -----------------------------
    # Fallback
    # -----------------------------
    return random.choice([
        "No entendí bien 🤔 — probá /ayuda",
        "¿Podés repetirlo? También podés usar /ayuda.",
        "No estoy seguro de eso. Probá /ayuda."
    ])

# --- Función para responder en background (no bloquear request) ---
def respond_in_background(user, trigger_text, delay=0.8):
    """
    Añade la respuesta del bot tras `delay` segundos en un hilo.
    Usa CHAT_LOCK para evitar concurrencia en el archivo.
    """
    def worker():
        try:
            # breve 'typing' delay proporcional a la longitud
            simulated = min(2.5, delay + len(trigger_text) * 0.02)
            time.sleep(simulated)

            respuesta = ppam_bot_v3(user, trigger_text)
            if not respuesta:
                return

            # Escribir en archivo con lock
            with CHAT_LOCK:
                msgs = _read_json(CHAT_FILE)
                last_id = (msgs[-1].get("id",0) if msgs else 0) + 1
                bot_msg = {
                    "id": last_id,
                    "usuario": "PPAM-BOT",
                    "texto": respuesta,
                    "ts": datetime.now().isoformat()
                }
                msgs.append(bot_msg)
                msgs = msgs[-1000:]
                _write_json(CHAT_FILE, msgs)
                # opcional: también agregar log
                _append_log(f"PPAM-BOT respondió a {user}: {respuesta}")
        except Exception:
            current_app.logger.exception("Error en hilo de respuesta del bot")

    t = threading.Thread(target=worker, daemon=True)
    t.start()
# -------------------- Filtros --------------------
@ppamtools_bp.app_template_filter("getattr")
def jinja_getattr(obj, name, default=None):
    return getattr(obj, name, default)
# -------------------- Helpers --------------------
# -- nace Bot (chatito GPT jajaja ) -----------
def bot_respuesta(texto):
    t = texto.lower().strip()

    # respuestas simples
    if t == "hola":
        return "¡Hola! ¿En qué puedo ayudarte?"

    if "ayuda" in t:
        return "Podés contactarte con soporte, ver documentación o describir el error."

    if "horario" in t:
        return "El horario de atención es de 9 a 18 hs."

    if "turno" in t:
        return "Para gestionar turnos, usá el menú 'Turnos' del panel."

    # comando ejemplo
    if t.startswith("/info"):
        return "PPAMTools — Sistema administrativo versión 1.0"

    # comando secreto /random
    if t.startswith("/random"):
        import random
        return f"Número aleatorio: {random.randint(1,100)}"

    # por defecto: no responder
    return None
#--  Bot version V1.1 ----------------------------------
# ======================================================
# PPAM-BOT v1 — Bot integrado al sistema PPAM
# Soporta comandos, preguntas y datos reales
# ======================================================
def ppam_bot_respuesta(texto):

    if not texto:
        return None

    t = texto.lower().strip()

    # -------------------------------
    # COMANDOS DIRECTOS
    # -------------------------------
    if t == "/ayuda":
        return (
            "Comandos disponibles:\n"
            "• /ayuda – muestra este mensaje\n"
            "• /hoy – asignaciones del día\n"
            "• /pendientes – solicitudes sin resolver\n"
            "• /publicadores – cantidad total\n"
            "• /actividad – actividad semanal\n"
            "• /estado – CPU, RAM y uptime del servidor\n"
            "• /notif – últimas notificaciones"
        )

    if t == "/publicadores":
        try:
            n = Publicador.query.count()
            return f"Actualmente hay {n} publicadores registrados."
        except:
            return "No pude obtener la lista de publicadores."

    if t == "/pendientes":
        try:
            n = SolicitudTurno.query.filter_by(estado="Pendiente").count()
            return f"Solicitudes pendientes: {n}"
        except:
            return "Error al consultar solicitudes pendientes."

    if t == "/hoy":
        try:
            hoy = datetime.now().date()
            n = Turno.query.filter(Turno.fecha == hoy).count()
            return f"Asignaciones del día ({hoy}): {n}"
        except:
            return "No pude obtener las asignaciones del día."

    if t == "/notif":
        try:
            notifs = _read_json(NOTIF_FILE)[-5:]
            if not notifs:
                return "No hay notificaciones recientes."
            return "Últimas notificaciones:\n" + "\n".join(f"- {n['texto']}" for n in notifs)
        except:
            return "No pude leer las notificaciones."

    if t == "/estado":
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            uptime = round(datetime.now().timestamp() - psutil.boot_time()) // 3600
            return f"Estado del servidor:\nCPU: {cpu}%\nMemoria: {mem}%\nUptime: {uptime} hs"
        except:
            return "No pude obtener el estado del servidor."

    if t == "/actividad":
        try:
            hoy = datetime.now().date()
            texto = "Actividad semanal:\n"
            for i in range(7):
                dia = hoy - timedelta(days=i)
                q = Turno.query.filter(Turno.fecha == dia).count()
                texto += f"- {dia.strftime('%d/%m')}: {q}\n"
            return texto
        except:
            return "Error obteniendo actividad semanal."

    # -------------------------------
    # RESPUESTAS NORMALES (palabras clave)
    # -------------------------------
    if "hola" in t:
        return "¡Hola! ¿En qué puedo ayudarte?"

    if "turno" in t:
        return "Si necesitás ver turnos o asignaciones, probá usar: /hoy o /actividad."

    if "gracias" in t:
        return "¡De nada!"

    if "ayuda" in t:
        return "Puedo ayudarte con datos de turnos, notificaciones, actividad o estado del servidor. Escribí /ayuda."

    # -------------------------------
    # Si no entendí
    # -------------------------------
    return None

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