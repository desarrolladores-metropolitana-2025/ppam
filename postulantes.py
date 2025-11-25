# postulantes.py
from flask import Blueprint, request, jsonify
from extensiones import db
from modelos import Publicador, SolicitudTurno, Ausencia, Turno
from datetime import datetime

bp_post = Blueprint("postulantes", __name__, url_prefix="/api")

def parse_time(s):
    if not s: return None
    try:
        return datetime.strptime(s, "%H:%M").time()
    except:
        try:
            return datetime.strptime(s, "%H:%M:%S").time()
        except:
            return None

@bp_post.route("/publicador")
def api_publicador():
    pub_id = request.args.get("id", type=int)
    if not pub_id:
        return jsonify({"error": "id requerido"}), 400

    p = Publicador.query.get(pub_id)
    if not p:
        return jsonify({"error": "no encontrado"}), 404

    return jsonify({
        "id": p.id,
        "nombre": p.nombre,
        "apellido": p.apellido
    })


@bp_post.route("/postulantes", methods=["GET","POST"])
def api_postulantes():
    accion = request.args.get("accion") or (request.get_json(silent=True) or {}).get("accion")

    # ----------------------------------------------------------------
    # listar_disponibles -> devuelve lista de publicadores (simple)
    # opcionalmente acepta filtros: punto_id, fecha, hora_inicio, hora_fin
    # ----------------------------------------------------------------
    if accion == "listar_disponibles":
        punto_id = request.args.get("punto_id", type=int)
        fecha = request.args.get("fecha")
        hora_inicio = request.args.get("hora_inicio")
        hora_fin = request.args.get("hora_fin")

        hi = parse_time(hora_inicio) if hora_inicio else None
        hf = parse_time(hora_fin) if hora_fin else None
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else None
        except:
            fecha_obj = None

        pubs = Publicador.query.order_by(Publicador.nombre, Publicador.apellido).all()
        out = []
        for p in pubs:
            ok = True
            motivo = None

            # 1) Ausencias
            if fecha_obj:
                aus = Ausencia.query.filter(Ausencia.publicador_id == p.id).all()
                for a in aus:
                    if a.fecha_inicio <= fecha_obj <= a.fecha_fin:
                        ok = False
                        motivo = "ausente"
                        break
                if not ok:
                    continue

            # 2) Ya asignado a otro turno que solape
            if fecha_obj and hi and hf:
                solapantes = Turno.query.filter(
                    Turno.fecha == fecha_obj,
                    ((Turno.publicador1_id == p.id) |
                     (Turno.publicador2_id == p.id) |
                     (Turno.publicador3_id == p.id) |
                     (Turno.publicador4_id == p.id) |
                     (Turno.capitan_id == p.id))
                ).all()
                conflict = False
                for s in solapantes:
                    if (s.hora_inicio <= hi < s.hora_fin) or (hi <= s.hora_inicio < hf):
                        conflict = True
                        break
                if conflict:
                    ok = False
                    motivo = "ya asignado"
                    continue

            # 3) Verificar que exista una SolicitudTurno que cubra ese horario (si se pide filtro por punto/horario)
            if punto_id and fecha_obj and hi and hf:
                solicitudes = SolicitudTurno.query.filter(
                    SolicitudTurno.publicador_id == p.id,
                    SolicitudTurno.punto_id == punto_id
                ).all()
                match = False
                for sol in solicitudes:
                    # verificar rango de fechas si están definidas
                    if sol.fecha_inicio and fecha_obj < sol.fecha_inicio:
                        continue
                    if sol.fecha_fin and fecha_obj > sol.fecha_fin:
                        continue
                    if sol.hora_inicio <= hi and sol.hora_fin >= hf:
                        match = True
                        break
                if not match:
                    ok = False
                    motivo = "no solicita ese horario"
                    continue

            # si llegó hasta acá, incluir
            out.append({
                "id": p.id,
                "nombre": p.nombre,
                "apellido": p.apellido,
                "usuario": p.usuario,
                "mail": p.mail,
                "motivo_exclusion": motivo
            })
        return jsonify(out)
    # ---------------------
    # LISTAR DISPONIBLES PARA UN TURNO (nuevo de acuerdo al punto 3 de los desarrolladores PPAM)
    # GET /api/postulantes?accion=disponibles&fecha=YYYY-MM-DD&hora_inicio=HH:MM&hora_fin=HH:MM&punto_id=#
    # ---------------------
    if accion == "disponibles":
        punto_id = request.args.get("punto_id", type=int) or request.args.get("punto", type=int)
        fecha = request.args.get("fecha")
        hora_inicio = request.args.get("hora_inicio")
        hora_fin = request.args.get("hora_fin")

        # parse fecha y horas
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else None
        except Exception:
            fecha_obj = None

        def parse_time_safe(s):
            if not s:
                return None
            for fmt in ("%H:%M", "%H:%M:%S"):
                try:
                    return datetime.strptime(s, fmt).time()
                except:
                    continue
            return None

        hi = parse_time_safe(hora_inicio)
        hf = parse_time_safe(hora_fin)

        pubs = Publicador.query.order_by(Publicador.nombre, Publicador.apellido).all()
        out = []
        for p in pubs:
            ok = True

            # 1) Ausencias que cubran la fecha
            if fecha_obj:
                aus = Ausencia.query.filter(Ausencia.publicador_id == p.id).all()
                for a in aus:
                    if a.fecha_inicio <= fecha_obj <= a.fecha_fin:
                        ok = False
                        break
                if not ok:
                    continue

            # 2) Ya asignado a otro turno que solape (mismo día)
            if fecha_obj and hi and hf:
                solapantes = Turno.query.filter(
                    Turno.fecha == fecha_obj,
                    ((Turno.publicador1_id == p.id) |
                    (Turno.publicador2_id == p.id) |
                    (Turno.publicador3_id == p.id) |
                    (Turno.publicador4_id == p.id) |
                    (Turno.capitan_id == p.id))
                ).all()
                conflict = False
                for s in solapantes:
                    # conviene convertir a minutos para comparar
                    def t2m(t):
                        return (t.hour * 60 + t.minute) if t else None
                    s_hi = t2m(s.hora_inicio)
                    s_hf = t2m(s.hora_fin)
                    q_hi = t2m(hi)
                    q_hf = t2m(hf)
                    if s_hi is None or s_hf is None:
                        continue
                    # overlap test
                    if max(s_hi, q_hi) < min(s_hf, q_hf):
                        conflict = True
                        break
                if conflict:
                    ok = False
                    continue

            # 3) Verificar que exista una SolicitudTurno que cubra ese horario para el punto (si punto_id y horas dadas)
            if punto_id and fecha_obj and hi and hf:
                solicitudes = SolicitudTurno.query.filter(
                    SolicitudTurno.publicador_id == p.id,
                    SolicitudTurno.punto_id == punto_id
                ).all()
                match = False
                for sol in solicitudes:
                    if sol.fecha_inicio and fecha_obj < sol.fecha_inicio:
                        continue
                    if sol.fecha_fin and fecha_obj > sol.fecha_fin:
                        continue
                    # sol.hora_inicio <= hi and sol.hora_fin >= hf
                    if sol.hora_inicio and sol.hora_fin:
                        # aceptar si la solicitud cubre todo el intervalo
                        if (sol.hora_inicio <= hi) and (sol.hora_fin >= hf):
                            match = True
                            break
                if not match:
                    ok = False
                    continue

            # 4) Si pasó todo, incluir en salida (campos mínimos)
            out.append({
                "id": p.id,
                "nombre": p.nombre,
                "apellido": p.apellido,
                "usuario": p.usuario,
                "mail": p.mail
            })

        return jsonify(out)
    # --------------------------------------------------------------------
#   ACCIÓN: disponibles_bulk  (ULTRA OPTIMIZADO)
# --------------------------------------------------------------------
    if accion == "disponibles_bulk":
        """
        POST:
        {
            "punto_id": 3,
            "turnos": [
                {"id":91,"fecha":"2025-11-17","hora_inicio":"08:00","hora_fin":"09:00"},
                {"id":92,"fecha":"2025-11-17","hora_inicio":"09:00","hora_fin":"10:00"}
            ]
        }

        Respuesta:
        { "91":[{pub},{pub}], "92":[...] }
        """

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "JSON inválido"}), 400
    
        punto_id = data.get("punto_id")
        turnos_in = data.get("turnos", [])

        # -----------------------------------------------
        # Parseamos turnos + convertimos hora/fecha
        # -----------------------------------------------
        turnos = []
        for t in turnos_in:
            try:
                fecha_obj = datetime.strptime(t["fecha"], "%Y-%m-%d").date()
            except:
                fecha_obj = None
    
            def parse_hora(x):
                if not x:
                    return None
                for fmt in ("%H:%M", "%H:%M:%S"):
                    try:
                        return datetime.strptime(x, fmt).time()
                    except:
                        pass
                return None

            hi = parse_hora(t.get("hora_inicio"))
            hf = parse_hora(t.get("hora_fin"))

            turnos.append({
                "id": str(t["id"]),
                "fecha": fecha_obj,
                "hi": hi,
                "hf": hf
            })

        # -----------------------------------------------
        # 1) CARGAR TODOS LOS PUBLICADORES UNA SOLA VEZ
        # -----------------------------------------------
        pubs = Publicador.query.all()

        # -----------------------------------------------
        # 2) CARGAR AUSENCIAS Y TURNOS EXISTENTES EN BLOQUE
        # -----------------------------------------------
        pub_ids = [p.id for p in pubs]
        fechas = [t["fecha"] for t in turnos if t["fecha"]]

        ausencias = {}
        for a in Ausencia.query.filter(Ausencia.publicador_id.in_(pub_ids)).all():
            ausencias.setdefault(a.publicador_id, []).append(a)
    
        # todos los turnos del mismo día para detectar solapes
        turnos_existentes = {}
        if fechas:
            t_exist = Turno.query.filter(Turno.fecha.in_(fechas)).all()
            for tx in t_exist:
                turnos_existentes.setdefault(tx.fecha, []).append(tx)

        # solicitudes por publicador+punto
        solicitudes = {}
        if punto_id:
            sols = SolicitudTurno.query.filter(
                SolicitudTurno.punto_id == punto_id
            ).all()
            for s in sols:
                solicitudes.setdefault(s.publicador_id, []).append(s)

        # -----------------------------------------------
        # FUNCIÓN AUXILIAR - chequeo rápido de solape
        # -----------------------------------------------
        def t2m(t):
            return t.hour * 60 + t.minute if t else None

        # -----------------------------------------------
        # 3) EVALUAR DISPONIBILIDAD
        # -----------------------------------------------
        respuesta = {t["id"]: [] for t in turnos}

        for t in turnos:
            fecha = t["fecha"]
            hi = t["hi"]
            hf = t["hf"]

            for p in pubs:
                ok = True

                # AUSENCIAS
                if fecha:
                    for a in ausencias.get(p.id, []):
                        if a.fecha_inicio <= fecha <= a.fecha_fin:
                            ok = False
                            break
                    if not ok:
                        continue

                # SOLAPES
                if fecha and hi and hf:
                    q_hi = t2m(hi)
                    q_hf = t2m(hf)

                    for tx in turnos_existentes.get(fecha, []):
                        if p.id not in (
                            tx.publicador1_id, tx.publicador2_id,
                            tx.publicador3_id, tx.publicador4_id,
                            tx.capitan_id
                        ):
                            continue

                        s_hi = t2m(tx.hora_inicio)
                        s_hf = t2m(tx.hora_fin)
                        if max(s_hi, q_hi) < min(s_hf, q_hf):
                            ok = False
                            break
                    if not ok:
                        continue

                # SOLICITUDES
                if fecha and hi and hf:
                    match = False
                    for s in solicitudes.get(p.id, []):
                        if s.fecha_inicio and fecha < s.fecha_inicio:
                            continue
                        if s.fecha_fin and fecha > s.fecha_fin:
                            continue
                        if s.hora_inicio <= hi and s.hora_fin >= hf:
                            match = True
                            break
                    if not match:
                        ok = False
                        continue

                # APROBADO
                respuesta[t["id"]].append({
                    "id": p.id,
                    "nombre": p.nombre,
                    "apellido": p.apellido
                })

        return jsonify(respuesta)


    # ----------------------------------------------------------------
    # validar_disponibilidad?usuario_id=...&fecha=YYYY-MM-DD&hora_inicio=HH:MM&hora_fin=HH:MM&punto_id=...
    # ----------------------------------------------------------------
    if accion == "validar_disponibilidad":
        usuario_id = request.args.get("usuario_id", type=int)
        fecha = request.args.get("fecha")
        hora_inicio = request.args.get("hora_inicio")
        hora_fin = request.args.get("hora_fin")
        punto_id = request.args.get("punto_id", type=int)

        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else None
        except:
            return jsonify({"ok": False, "motivo": "fecha inválida"}), 400

        hi = parse_time(hora_inicio)
        hf = parse_time(hora_fin)
        if not usuario_id:
            return jsonify({"ok": False, "motivo": "usuario_id faltante"}), 400

        # 1) Ausencias
        aus = Ausencia.query.filter(Ausencia.publicador_id == usuario_id).all()
        for a in aus:
            if a.fecha_inicio <= fecha_obj <= a.fecha_fin:
                return jsonify({"ok": False, "motivo": "ausente en esas fechas"})

        # 2) Ya asignado a otro turno que solape en la misma fecha
        solapantes = Turno.query.filter(
            Turno.fecha == fecha_obj,
            ((Turno.publicador1_id == usuario_id) |
             (Turno.publicador2_id == usuario_id) |
             (Turno.publicador3_id == usuario_id) |
             (Turno.publicador4_id == usuario_id) |
             (Turno.capitan_id == usuario_id))
        ).all()
        for s in solapantes:
            if (s.hora_inicio <= hi < s.hora_fin) or (hi <= s.hora_inicio < hf):
                return jsonify({"ok": False, "motivo": "ya asignado a otro turno ese horario"})

        # 3) Existe una solicitud que cubra ese horario?
        solicitudes = SolicitudTurno.query.filter(
            SolicitudTurno.publicador_id == usuario_id,
            SolicitudTurno.punto_id == punto_id
        ).all()

        match = False
        for sol in solicitudes:
            if sol.fecha_inicio and fecha_obj < sol.fecha_inicio:
                continue
            if sol.fecha_fin and fecha_obj > sol.fecha_fin:
                continue
            if sol.hora_inicio <= hi and sol.hora_fin >= hf:
                match = True
                break

        if not match:
            return jsonify({"ok": False, "motivo": "no tiene solicitud que cubra este horario"})

        return jsonify({"ok": True})

    # listar todos (sin filtros)
    if accion == "listar_todos":
        pubs = Publicador.query.order_by(Publicador.nombre, Publicador.apellido).all()
        out = [{"id": p.id, "nombre": p.nombre, "apellido": p.apellido, "usuario": p.usuario, "mail": p.mail} for p in pubs]
        return jsonify(out)

    return jsonify({"error":"accion no reconocida"}), 400
