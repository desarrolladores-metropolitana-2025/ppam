# PPAM
# mysite/planificacion.py
# 25/11/2025
#
import hashlib
from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta, date
from flask_login import login_required, current_user

from extensiones import db
from modelos import PuntoPredicacion, Turno

planificacion_bp = Blueprint("planificacion", __name__, url_prefix="/api/planificacion")


# -----------------------------------------------------------
# 🔵 Utilidad para normalizar el inicio de semana (lunes)
# -----------------------------------------------------------
def get_week_range(start_str=None):
    if start_str:
        try:
            week_start = datetime.strptime(start_str, "%Y-%m-%d").date()
        except:
            week_start = date.today()
    else:
        week_start = date.today()

    # asegurar lunes
    week_start = week_start - timedelta(days=week_start.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


# -----------------------------------------------------------
# 🟦 RUTA PRINCIPAL DE PLANIFICACIÓN
# -----------------------------------------------------------
@planificacion_bp.route("/")
@login_required
def index():
    start_str = request.args.get("week_start")
    week_start, week_end = get_week_range(start_str)

    # cargar puntos
    puntos = PuntoPredicacion.query.order_by(PuntoPredicacion.id.asc()).all()

    # cargar turnos de la semana
    turnos_raw = (
        Turno.query.filter(
            Turno.fecha >= week_start,
            Turno.fecha <= week_end
        )
        .order_by(Turno.fecha.asc(), Turno.hora_inicio.asc())
        .all()
    )

    # -------------------------------------------
    #  Organizar turnos => { punto_id: { dia: [turnos] } }
    # -------------------------------------------
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    turnos = {p.id: {d: [] for d in dias} for p in puntos}

    for t in turnos_raw:
        dia_str = dias[t.fecha.weekday()]  # weekday: lunes=0
        turnos[t.punto_id][dia_str].append({
            "id": t.id,
            "fecha": t.fecha,
            "hora_inicio": t.hora_inicio,
            "hora_fin": t.hora_fin,
            "capitan_nombre": t.capitan.nombre if t.capitan else "",
            "publicador1_nombre": t.publicador1.nombre if t.publicador1 else "",
            "publicador2_nombre": t.publicador2.nombre if t.publicador2 else "",
            "publicador3_nombre": t.publicador3.nombre if t.publicador3 else "",
            "publicador4_nombre": t.publicador4.nombre if t.publicador4 else "",
            "is_public": t.is_public
        })

    # -------------------------------------------
    # Pasamos todo al template planificación.html
    # -------------------------------------------
    return render_template(
        "planificacion.html",
        puntos=puntos,
        turnos=turnos,
        week_start=week_start,
        week_end=week_end,
        prev_week=week_start - timedelta(days=7),
        next_week=week_start + timedelta(days=7)
    )

@planificacion_bp.route("/changes", methods=["GET"])
@login_required
def api_planificacion_changes():
    if current_user.rol != "Admin":
        return jsonify({"ok": False, "error": "No autorizado"}), 403

    punto_id = request.args.get("punto_id", type=int)
    last_version = request.args.get("version", "")
    week_start_str = request.args.get("week_start")

    try:
        week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
    except Exception:
        week_start = date.today() - timedelta(days=date.today().weekday())

    week_end = week_start + timedelta(days=6)

    turnos = Turno.query.filter(
        Turno.punto_id == punto_id,
        Turno.fecha >= week_start,
        Turno.fecha <= week_end
    ).all()

    # hash
    serial = [
        f"{t.id}:{int(t.is_public)}:{t.publicador1_id or 0}:{t.publicador2_id or 0}:{t.publicador3_id or 0}:{t.publicador4_id or 0}:{t.capitan_id or 0}"
        for t in sorted(turnos, key=lambda x: x.id)
    ]
    version = hashlib.sha1("|".join(serial).encode()).hexdigest()

    changed = (version != last_version)

    return jsonify({
        "ok": True,
        "changed": changed,
        "version": version,
        "sample": {
            "total_turnos": len(turnos)
        }
    })
    
@planificacion_bp.route("/stats", methods=["GET"])
@login_required
def api_planificacion_stats():
    if current_user.rol != "Admin":
        return jsonify({"ok": False, "error": "No autorizado"}), 403

    punto_id = request.args.get("punto_id", type=int)
    week_start_str = request.args.get("week_start")

    try:
        week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
    except Exception:
        week_start = date.today() - timedelta(days=date.today().weekday())

    week_end = week_start + timedelta(days=6)

    turnos = Turno.query.filter(
        Turno.punto_id == punto_id,
        Turno.fecha >= week_start,
        Turno.fecha <= week_end
    ).all()

    # estadísticas
    publicos = sum(1 for t in turnos if t.is_public)
    borradores = len(turnos) - publicos

    dias = {}
    for t in turnos:
        dias.setdefault(t.fecha.isoformat(), []).append(t)

    dias_completos = sum(1 for d in dias.values() if any(t.is_public for t in d))
    dias_incompletos = len(dias) - dias_completos

    # hash versión
    serial = [
        f"{t.id}:{int(t.is_public)}:{t.publicador1_id or 0}:{t.publicador2_id or 0}:{t.publicador3_id or 0}:{t.publicador4_id or 0}:{t.capitan_id or 0}"
        for t in sorted(turnos, key=lambda x: x.id)
    ]
    version = hashlib.sha1("|".join(serial).encode()).hexdigest()

    return jsonify({
        "ok": True,
        "publicos": publicos,
        "borradores": borradores,
        "dias_completos": dias_completos,
        "dias_incompletos": dias_incompletos,
        "version": version
    })
    
@planificacion_bp.route("/publish", methods=["POST"])
@login_required
def api_planificacion_publish():
    if current_user.rol != "Admin":
        return jsonify({"ok": False, "error": "No autorizado"}), 403

    data = request.get_json(silent=True) or {}
    ids = data.get("turno_ids", [])
    accion = data.get("action", "publicar")

    if not ids:
        return jsonify({"ok": False, "error": "Lista vacía"}), 400

    updated = []
    try:
        turnos = Turno.query.filter(Turno.id.in_(ids)).all()
        for t in turnos:
            if accion == "publicar":
                if not t.is_public:
                    t.is_public = True
                    updated.append(t.id)
            else:
                if t.is_public:
                    t.is_public = False
                    updated.append(t.id)
            db.session.add(t)

        db.session.commit()

        return jsonify({"ok": True, "updated": updated})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
