# turnos.py
from flask import Blueprint, request, jsonify
from extensiones import db
from modelos import Turno, PuntoPredicacion, Publicador, SolicitudTurno
from datetime import datetime, date, time

bp_turnos = Blueprint("turnos", __name__, url_prefix="/api")

def time_to_str(t):
    return t.strftime("%H:%M") if t else ""

def date_to_iso(d):
    return d.isoformat() if d else None

def turno_to_dict(t: Turno):
    return {
        "id": t.id,
        "punto_id": t.punto_id,
        "punto": t.punto.punto_nombre if getattr(t, "punto", None) else None,
        "fecha": date_to_iso(t.fecha),
        "dia": t.dia,
        "hora_inicio": time_to_str(t.hora_inicio),
        "hora_fin": time_to_str(t.hora_fin),
        "publicador1": t.publicador1_id,
        "publicador2": t.publicador2_id,
        "publicador3": t.publicador3_id,
        "publicador4": t.publicador4_id,
        "capitan": t.capitan_id,
        "is_public": bool(t.is_public)
    }

@bp_turnos.route("/turnos", methods=["GET", "POST"])
def api_turnos():
    accion = request.args.get("accion") or request.form.get("accion") or (request.get_json(silent=True) or {}).get("accion")
    # LISTAR simple (array)
    if accion == "listar":
        turnos = Turno.query.order_by(Turno.fecha, Turno.hora_inicio).all()
        data = [turno_to_dict(t) for t in turnos]
        return jsonify(data)

    # LISTAR POR RANGO -> devuelve objeto agrupado por fecha (igual al PHP)
    if accion == "listar_por_rango":
        desde = request.args.get("desde")
        hasta = request.args.get("hasta")
        try:
            fecha_desde = datetime.strptime(desde, "%Y-%m-%d").date() if desde else None
            fecha_hasta = datetime.strptime(hasta, "%Y-%m-%d").date() if hasta else None
        except Exception:
            return jsonify({"error":"Formato de fecha inválido. Use YYYY-MM-DD"}), 400

        q = Turno.query
        if fecha_desde:
            q = q.filter(Turno.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.filter(Turno.fecha <= fecha_hasta)
        q = q.order_by(Turno.fecha, Turno.hora_inicio)
        turnos = q.all()

        out = {}
        for t in turnos:
            key = date_to_iso(t.fecha)
            out.setdefault(key, []).append(turno_to_dict(t))
        return jsonify(out)

    # CREAR MANUAL (POST JSON) - crear turno puntual
    if accion == "crear_manual" and request.method == "POST":
        data = request.get_json(force=True)
        fecha = data.get("fecha")
        hora_inicio = data.get("hora_inicio")
        hora_fin = data.get("hora_fin")
        punto_id = data.get("punto_id") or data.get("punto")  # aceptar id o nombre
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else None
            hi = datetime.strptime(hora_inicio, "%H:%M").time() if hora_inicio else None
            hf = datetime.strptime(hora_fin, "%H:%M").time() if hora_fin else None
        except Exception as e:
            return jsonify({"ok": False, "error": f"Formato fecha/hora inválido: {e}"}), 400

        # si punto_id no es int, intentar buscar por nombre
        if punto_id and not isinstance(punto_id, int):
            p = PuntoPredicacion.query.filter(PuntoPredicacion.punto_nombre == str(punto_id)).first()
            punto_id = p.id if p else None

        # calcular dia de semana (string)
        dia = fecha_obj.strftime("%A").lower() if fecha_obj else None
        mapping = {
            "monday":"lunes","tuesday":"martes","wednesday":"miercoles","thursday":"jueves",
            "friday":"viernes","saturday":"sabado","sunday":"domingo"
        }
        dia_es = mapping.get(dia, "lunes") if dia else "lunes"

        nuevo = Turno(
            punto_id=punto_id,
            fecha=fecha_obj,
            dia=dia_es,
            hora_inicio=hi,
            hora_fin=hf,
            is_public=False
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({"ok": True, "id": nuevo.id, "turno": turno_to_dict(nuevo)})

    # ASIGNAR MANUAL (POST JSON) - asigna usuario al primer slot libre
    if accion == "asignar_manual" and request.method == "POST":
        data = request.get_json(force=True)
        turno_id = data.get("turno_id")
        usuario_id = data.get("usuario_id")
        if not turno_id or not usuario_id:
            return jsonify({"ok": False, "error": "falta turno_id o usuario_id"}), 400
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"ok": False, "error": "Turno no encontrado"}), 404

        # evitar duplicados (ya asignado)
        current_ids = {t.publicador1_id, t.publicador2_id, t.publicador3_id, t.publicador4_id}
        if usuario_id in current_ids:
            return jsonify({"ok": False, "error": "Usuario ya asignado en este turno"}), 400

        # buscar primer slot libre
        for slot in ("publicador1_id","publicador2_id","publicador3_id","publicador4_id"):
            if getattr(t, slot) is None:
                setattr(t, slot, int(usuario_id))
                db.session.commit()
                return jsonify({"ok": True, "turno": turno_to_dict(t)})
        return jsonify({"ok": False, "error": "No hay slots libres"}), 400

    # PUNTOS DISPONIBLES para una fecha (filtrar por horario del día)
    if accion == "puntos_disponibles":
        fecha = request.args.get("fecha")
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else date.today()
        except Exception:
            fecha_obj = date.today()

        weekday = fecha_obj.weekday()  # 0 lunes ... 6 domingo? (Python: 0 lunes)
        # Map weekday -> attribute names
        dias = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]
        attr_inicio = f"{dias[weekday]}_inicio"
        attr_fin = f"{dias[weekday]}_fin"

        puntos = PuntoPredicacion.query.all()
        out = []
        for p in puntos:
            inicio = getattr(p, attr_inicio)
            fin = getattr(p, attr_fin)
            # verificar rango de fechas del punto
            if p.fecha_inicio and fecha_obj < p.fecha_inicio: 
                continue
            if p.fecha_fin and fecha_obj > p.fecha_fin:
                continue
            if inicio and fin:
                out.append({
                    "id": p.id,
                    "nombre": p.punto_nombre,
                    "inicio": time_to_str(inicio),
                    "fin": time_to_str(fin)
                })
        return jsonify(out)

    return jsonify({"error": "accion no reconocida"}), 400
