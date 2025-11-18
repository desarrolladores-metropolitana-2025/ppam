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
