# turnos.py
from flask import Blueprint, request, jsonify, render_template, session
from extensiones import db
from modelos import Turno, PuntoPredicacion, Publicador, SolicitudTurno
from datetime import datetime, date, time
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

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
@login_required
def api_turnos():
    accion = request.args.get("accion") or request.form.get("accion") or (request.get_json(silent=True) or {}).get("accion")

    # ---------------------
    # LISTAR simple (array)
    # ---------------------
    if accion == "listar":
        punto_id = request.args.get("punto", type=int)
        fecha = request.args.get("fecha")

        q = Turno.query

        if punto_id:
            q = q.filter(Turno.punto_id == punto_id)

        if fecha:
            try:
                fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
                q = q.filter(Turno.fecha == fecha_obj)
            except:
                pass

        turnos = q.order_by(Turno.fecha, Turno.hora_inicio).all()
        data = [turno_to_dict(t) for t in turnos]
        return jsonify(data)
    if accion == "solicitar":
        data = request.get_json() or {}
        turno_id = data.get("turno_id")

        if not turno_id:
            return jsonify({"ok": False, "error": "turno_id requerido"}), 400

        # Buscar turno
        turno = Turno.query.get(turno_id)
        if not turno:
            return jsonify({"ok": False, "error": "Turno inexistente"}), 404

        # Evitar duplicados: si ya existe solicitud del mismo usuario para ese turno
        existe = SolicitudTurno.query.filter_by(
            publicador_id=current_user.id,
            punto_id=turno.punto_id,
            hora_inicio=turno.hora_inicio,
            hora_fin=turno.hora_fin,
            dia=turno.dia,
            fecha_inicio=turno.fecha
        ).first()

        if existe:
            return jsonify({"ok": False, "error": "Ya existe tu solicitud para este turno"}), 400

        try:
            # Crear solicitud
            sol = SolicitudTurno(
                publicador_id=current_user.id,
                punto_id=turno.punto_id,
                hora_inicio=turno.hora_inicio,
                hora_fin=turno.hora_fin,
                dia=turno.dia,
                fecha_inicio=turno.fecha,
                fecha_fin=turno.fecha,
                prioridad=1,
                frecuencia=None
            )
            db.session.add(sol)
            db.session.commit()
            return jsonify({"ok": True, "message": "Solicitud creada", "solicitud_id": sol.id})
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error creando solicitud")
            return jsonify({"ok": False, "error": str(e)}), 500




    # ---------------------
    # LISTAR POR RANGO -> objeto agrupado por fecha (igual al PHP)
    # ---------------------
    if accion == "listar_por_rango":
        desde = request.args.get("desde")
        hasta = request.args.get("hasta")
        punto_id = request.args.get("punto", type=int)

        try:
            fecha_desde = datetime.strptime(desde, "%Y-%m-%d").date() if desde else None
            fecha_hasta = datetime.strptime(hasta, "%Y-%m-%d").date() if hasta else None
        except Exception:
            return jsonify({"error":"Formato de fecha inválido. Use YYYY-MM-DD"}), 400

        q = Turno.query

        # Filtros
        if fecha_desde:
            q = q.filter(Turno.fecha >= fecha_desde)
        if fecha_hasta:
            q = q.filter(Turno.fecha <= fecha_hasta)
        if punto_id:
            q = q.filter(Turno.punto_id == punto_id)

        q = q.order_by(Turno.fecha, Turno.hora_inicio)
        turnos = q.all()

        out = {}
        for t in turnos:
            key = date_to_iso(t.fecha)
            out.setdefault(key, []).append(turno_to_dict(t))
        return jsonify(out)
    # ---------------------
    # GET por id
    # ---------------------
    if accion == "get":
        turno_id = request.args.get("id", type=int)
        if not turno_id:
            return jsonify({"error":"id faltante"}), 400
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"error":"turno no encontrado"}), 404
        return jsonify(turno_to_dict(t))

    # ---------------------
    # CREAR MANUAL (POST JSON) - crear turno puntual
    # ---------------------
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

        # calcular dia de semana (string en español)
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

    # ---------------------
    # ASIGNAR MANUAL (POST JSON) - asigna usuario al primer slot libre
    # ---------------------
    if accion == "asignar_manual" and request.method == "POST":
        data = request.get_json(force=True)
        turno_id = data.get("turno_id")
        usuario_id = data.get("usuario_id")
        rol = data.get("rol")  # opcional
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

    # ---------------------
    # DESASIGNAR (POST JSON) - quitar usuario de un slot concreto
    # body: { turno_id, usuario_id }
    # ---------------------
    if accion == "desasignar" and request.method == "POST":
        data = request.get_json(force=True)
        turno_id = data.get("turno_id")
        usuario_id = data.get("usuario_id")
        if not turno_id or not usuario_id:
            return jsonify({"ok": False, "error": "falta turno_id o usuario_id"}), 400
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"ok": False, "error": "Turno no encontrado"}), 404

        changed = False
        for slot in ("publicador1_id","publicador2_id","publicador3_id","publicador4_id"):
            if getattr(t, slot) == int(usuario_id):
                setattr(t, slot, None)
                changed = True
        if changed:
            db.session.commit()
            return jsonify({"ok": True, "turno": turno_to_dict(t)})
        return jsonify({"ok": False, "error": "Usuario no encontrado en ese turno"}), 400

    # ---------------------
    # SET CAPITAN (POST JSON): { turno_id, capitan_id }
    # ---------------------
    if accion == "set_capitan" and request.method == "POST":
        data = request.get_json(force=True)
        turno_id = data.get("turno_id")
        capitan_id = data.get("capitan_id")
        if not turno_id:
            return jsonify({"ok": False, "error": "falta turno_id"}), 400
        t = Turno.query.get(turno_id)
        if not t:
            return jsonify({"ok": False, "error": "Turno no encontrado"}), 404
        t.capitan_id = int(capitan_id) if capitan_id else None
        db.session.commit()
        return jsonify({"ok": True, "turno": turno_to_dict(t)})

    # ---------------------
    # ELIMINAR TURNO (POST/GET)
    # ---------------------
    if accion == "eliminar" and request.method in ("POST","GET"):
        turno_id = request.args.get("id") or (request.get_json(silent=True) or {}).get("turno_id")
        if not turno_id:
            return jsonify({"ok": False, "error": "falta id"}), 400
        t = Turno.query.get(int(turno_id))
        if not t:
            return jsonify({"ok": False, "error": "Turno no encontrado"}), 404
        db.session.delete(t)
        db.session.commit()
        return jsonify({"ok": True})

    # ---------------------
    # PUNTOS DISPONIBLES para una fecha (filtrar por horario del día)
    # ---------------------
    if accion == "puntos_disponibles":
        fecha = request.args.get("fecha")
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else date.today()
        except Exception:
            fecha_obj = date.today()

        weekday = fecha_obj.weekday()  # 0 lunes ... 6 domingo (Python)
        dias = ["lunes","martes","miercoles","jueves","viernes","sabado","domingo"]
        attr_inicio = f"{dias[weekday]}_inicio"
        attr_fin = f"{dias[weekday]}_fin"

        puntos = PuntoPredicacion.query.all()
        out = []
        for p in puntos:
            inicio = getattr(p, attr_inicio)
            fin = getattr(p, attr_fin)
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
@bp_turnos.route('/calendario')
@login_required
def calendario_publico():
    p = request.args.get('p', type=int, default=1)
    punto = PuntoPredicacion.query.get(p)
    nombre = punto.punto_nombre if punto else request.args.get('nomb', f'Punto {p}')
    return render_template('calendario_ppam.html', punto_id=p, punto_name=nombre)

@bp_turnos.route('/api/events')
@login_required
def api_events():
    """
    Devuelve turnos en formato JSON para FullCalendar.
    Parámetros: punto_id, start, end (ISO dates)
    """
    punto_id = request.args.get('punto_id', type=int)
    start = request.args.get('start')
    end = request.args.get('end')
    try:
        start_dt = datetime.date.fromisoformat(start.split('T')[0]) if start else None
        end_dt = datetime.date.fromisoformat(end.split('T')[0]) if end else None
    except Exception:
        return jsonify({"ok": False, "error": "Fechas inválidas"}), 400

    q = Turno.query
    if punto_id:
        q = q.filter(Turno.punto_id == punto_id)
    if start_dt:
        q = q.filter(Turno.fecha >= start_dt)
    if end_dt:
        q = q.filter(Turno.fecha <= end_dt)
    turnos = q.order_by(Turno.fecha, Turno.hora_inicio).all()

    out = []
    for t in turnos:
        out.append({
            "id": t.id,
            "fecha": t.fecha.isoformat(),
            "hora_inicio": t.hora_inicio.strftime("%H:%M") if t.hora_inicio else None,
            "hora_fin": t.hora_fin.strftime("%H:%M") if t.hora_fin else None,
            "punto_id": t.punto_id,
            "punto_nombre": getattr(t.punto, "nombre", None) if hasattr(t, "punto") else None,
            "title": getattr(t, "titulo", None) or f"Turno #{t.id}",
            "estado": getattr(t, "estado", None)
        })
    return jsonify({"ok": True, "turnos": out})

@bp_turnos.route('/api/solicitar', methods=['POST'])
@login_required
def api_solicitar_turno():
    """
    JSON body: { "turno_id": 123 }
    Crea una SolicitudTurno para el current_user sobre ese turno (estado 'pendiente').
    """
    data = request.get_json(silent=True) or {}
    turno_id = data.get('turno_id')
    if not turno_id:
        return jsonify({"ok": False, "error": "turno_id requerido"}), 400

    turno = Turno.query.get(int(turno_id))
    if not turno:
        return jsonify({"ok": False, "error": "Turno no encontrado"}), 404

    # Evitar duplicados: si ya hay solicitud del mismo user para ese turno
    existe = SolicitudTurno.query.filter_by(turno_id=turno.id, publicador_id=current_user.id).first()
    if existe:
        return jsonify({"ok": False, "error": "Ya existe tu solicitud para este turno"}), 400

    try:
        s = SolicitudTurno(
            turno_id=turno.id,
            publicador_id=current_user.id,
            punto_id=turno.punto_id if hasattr(turno, 'punto_id') else None,
            estado='pendiente',
            created_at=datetime.datetime.utcnow()
        )
        db.session.add(s)
        db.session.commit()
        return jsonify({"ok": True, "message": "Solicitud creada", "solicitud_id": s.id})
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error creando solicitud")
        return jsonify({"ok": False, "error": str(e)}), 500
