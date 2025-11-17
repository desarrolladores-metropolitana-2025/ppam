# turnos.py
from flask import Blueprint, jsonify, request
from extensiones import db
from modelos import Turno, PuntoPredicacion

# Blueprint principal para la API de turnos
bp_turnos = Blueprint("turnos", __name__, url_prefix="/api")

# ----------------------------
# TURNOS API
# ----------------------------
@bp_turnos.route("/turnos", methods=["GET", "POST"])
def api_turnos():
    accion = request.args.get("accion")

    # ✅ LISTAR TURNOS
    if accion == "listar":
        turnos = (
            db.session.query(Turno, PuntoPredicacion)
            .join(PuntoPredicacion, Turno.punto_id == PuntoPredicacion.id, isouter=True)
            .order_by(Turno.hora_inicio)
            .all()
        )
        data = []
        for t, p in turnos:
            data.append({
                "id": t.id,
                "punto": p.punto_nombre if p else None,
                "punto_id": t.punto_id,
                "dia": t.dia,
                "hora_inicio": str(t.hora_inicio),
                "hora_fin": str(t.hora_fin),
            })
        return jsonify(data)

    # ✅ CREAR UN TURNO
    elif accion == "crear" and request.method == "POST":
        try:
            data = request.form or request.get_json(force=True)
            nuevo = Turno(
                punto_id=data.get("punto_id"),
                hora_inicio=data.get("hora_inicio"),
                hora_fin=data.get("hora_fin"),
                dia=data.get("dia", "lunes"),
            )
            db.session.add(nuevo)
            db.session.commit()
            return jsonify({"ok": True, "id": nuevo.id})
        except Exception as e:
            db.session.rollback()
            return jsonify({"ok": False, "error": str(e)}), 500

    # ✅ EDITAR
    elif accion == "editar" and request.method == "POST":
        turno_id = request.args.get("id")
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"ok": False, "error": "Turno no encontrado"}), 404
        try:
            data = request.form or request.get_json(force=True)
            t.hora_inicio = data.get("hora_inicio", t.hora_inicio)
            t.hora_fin = data.get("hora_fin", t.hora_fin)
            t.dia = data.get("dia", t.dia)
            t.punto_id = data.get("punto_id", t.punto_id)
            db.session.commit()
            return jsonify({"ok": True})
        except Exception as e:
            db.session.rollback()
            return jsonify({"ok": False, "error": str(e)}), 500

    # ✅ CANCELAR
    elif accion == "cancelar" and request.method == "POST":
        turno_id = request.form.get("turno_id")
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"ok": False, "error": "No existe el turno"}), 404
        try:
            t.is_public = False
            db.session.commit()
            return jsonify({"ok": True})
        except Exception as e:
            db.session.rollback()
            return jsonify({"ok": False, "error": str(e)}), 500

    # ✅ ABRIR
    elif accion == "abrir" and request.method == "POST":
        turno_id = request.form.get("turno_id")
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"ok": False, "error": "No existe el turno"}), 404
        try:
            t.is_public = True
            db.session.commit()
            return jsonify({"ok": True})
        except Exception as e:
            db.session.rollback()
            return jsonify({"ok": False, "error": str(e)}), 500

    # ✅ PLANIFICAR
    elif accion == "planificar" and request.method == "POST":
        turno_id = request.form.get("turno_id")
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"ok": False, "error": "No existe el turno"}), 404
        try:
            t.is_public = True
            db.session.commit()
            return jsonify({"ok": True, "estado": "planificado"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"ok": False, "error": str(e)}), 500

    # ✅ FALLBACK
    else:
        return jsonify({"error": "Acción no reconocida o método inválido"}), 400
