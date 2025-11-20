# BotAsignador.py
# Versión Python/Flask/SQLAlchemy adaptada desde BotAsignador.php
# - Usa modelos de modelos.py (Publicador, PuntoPredicacion, SolicitudTurno, Ausencia, Turno, Experiencia)
# - Escribe pipeline ASCII en /home/ppamappcaba/mysite/tmp/bot_pipeline_{ts}.txt
# - Escribe /tmp/bot_log.json con {"pipeline_text": "..."}
# - Expone blueprint `bot_api` con endpoints /api/bot/ejecutar, /estado, /metricas
#
# Requisitos:
# - extensiones.db (SQLAlchemy)
# - modelos.py con las clases entregadas
# - permisos de escritura en /tmp

import datetime
import json
import os
import time
from typing import List, Dict, Any, Optional

from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import or_, and_, func

from extensiones import db
from modelos import Turno, Publicador, SolicitudTurno, Ausencia, PuntoPredicacion, Experiencia

bot_api = Blueprint("bot_api", __name__, url_prefix="/api/bot")


def now_ts_str():
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def write_pipeline_file(content: str) -> str:
    ts = now_ts_str()
    filename = f"/home/ppamappcaba/mysite/tmp/bot_pipeline_{ts}.txt"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return filename
    except Exception:
        # fallback to cwd
        filename = os.path.join(os.getcwd(), f"bot_pipeline_{ts}.txt")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        return filename


def write_bot_log_json(payload: Dict[str, Any]) -> str:
    """Write /tmp/bot_log.json (frontend reads this). Returns path."""
    path = "/home/ppamappcaba/mysite/tmp/bot_log.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        # fallback to cwd
        path = os.path.join(os.getcwd(), "bot_log.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def time_overlap(start1, end1, start2, end2):
    """True if [start1, end1) overlaps [start2, end2). Works with datetime.time."""
    if not (start1 and end1 and start2 and end2):
        return False
    # times are datetime.time -> convert to minutes
    def to_min(t):
        return t.hour * 60 + t.minute + (t.second / 60.0)
    a0, a1 = to_min(start1), to_min(end1)
    b0, b1 = to_min(start2), to_min(end2)
    return not (a1 <= b0 or b1 <= a0)


class BotAsignador:
    def __init__(self, session=None, opts: Optional[Dict[str, Any]] = None):
        self.session = session or db.session
        self.logs: List[str] = []
        self.pipeline_lines: List[str] = []
        self.pipeline_filename: Optional[str] = None
        self.pipeline_text: str = ""

        # Configurables (valores por defecto tomados del PHP)
        self.auto_approve_pending = True
        self.use_fairness = True
        self.fairness_window_weeks = 4
        self.max_assign_per_run = 200
        self.peso_preferido = 30
        self.peso_posible = 10
        self.peso_idioma = 10
        self.peso_disponibilidad = 20
        self.peso_rol = 5
        self.penalizacion_por_turnos_recientes = 1

        if opts:
            for k, v in opts.items():
                if hasattr(self, k):
                    setattr(self, k, v)

        self.log_pipeline(f"Inicio BotAsignador Python: {datetime.datetime.utcnow().isoformat()}")

    # ---------- Logging ----------
    def log(self, txt: str):
        self.logs.append(f"{datetime.datetime.utcnow().isoformat()} {txt}")

    def log_pipeline(self, line: str):
        ts = datetime.datetime.utcnow().isoformat()
        self.pipeline_lines.append(f"[{ts}] {line}")
        self.log(line)

    def finalize_pipeline(self):
        """Escribe pipeline file y bot_log.json con pipeline_text"""
        try:
            content = "\n".join(self.pipeline_lines) + "\n"
            self.pipeline_filename = write_pipeline_file(content)
            # add final line
            final_line = f"[{datetime.datetime.utcnow().isoformat()}] Pipeline escrito en {self.pipeline_filename}"
            self.pipeline_lines.append(final_line)
            self.logs.append(final_line)
            # pipeline text
            self.pipeline_text = "\n".join(self.pipeline_lines) + "\n"
            # write bot_log.json with pipeline_text (frontend reads this)
            write_bot_log_json({"pipeline_text": self.pipeline_text, "pipeline_file": self.pipeline_filename})
        except Exception as e:
            self.log_pipeline(f"Error en finalize_pipeline: {e}")
            self.pipeline_text = "\n".join(self.pipeline_lines) + "\n"
            write_bot_log_json({"pipeline_text": self.pipeline_text})

    # ---------- API public ----------
    def run_batch(self, days_ahead: int = 14) -> Dict[str, Any]:
        t0 = time.time()
        self.pipeline_lines = []
        self.log_pipeline(f"Modo batch: buscando turnos con vacantes en próximos {days_ahead} días")

        today = datetime.date.today()
        end = today + datetime.timedelta(days=days_ahead)

        # obtener turnos dentro del rango
        turnos = (
            self.session.query(Turno)
            .filter(Turno.fecha >= today, Turno.fecha <= end)
            .order_by(Turno.fecha, Turno.hora_inicio)
            .limit(self.max_assign_per_run)
            .all()
        )

        results = []
        processed = 0
        for t in turnos:
            processed += 1
            res = self.run_for_turno(t.id, commit=True)
            results.append(res)

        duration_ms = round((time.time() - t0) * 1000, 2)
        self.log_pipeline(f"Batch finalizado. Procesados: {processed} - Duracion ms: {duration_ms}")
        self.finalize_pipeline()
        return {
            "ok": True,
            "processed": processed,
            "results": results,
            "pipeline_file": self.pipeline_filename,
            "pipeline_text": self.pipeline_text,
            "duracion_ms": duration_ms,
        }

    def run_for_turno(self, turno_input, commit: bool = True) -> Dict[str, Any]:
        """
        turno_input: id int or Turno instance or dict-like from DB
        """
        self.logs = []
        self.pipeline_lines = []
        try:
            turno = self._normalize_turno(turno_input)
            if not turno:
                return {"ok": False, "error": "Turno no encontrado"}

            turno_id = turno.id if isinstance(turno, Turno) else int(turno.get("id"))
            self.log_pipeline(f"=== Procesando turno input: {turno_id}")
            # comenzamos transacción
            with self.session.begin_nested():
                # refrescar turno
                t = self.session.query(Turno).get(turno_id)
                if not t:
                    return {"ok": False, "error": "Turno no encontrado"}

                # obtener maxSlots si punto define (si no, usar 4)
                try:
                    punto = t.punto
                    max_slots = getattr(punto, "maximo_publicadores", None) or 4
                    min_slots = getattr(punto, "minimo_publicadores", None) or 1
                except Exception:
                    max_slots = 4
                    min_slots = 1

                # contar asignados actuales
                existing_ids = [i for i in (
                    t.publicador1_id, t.publicador2_id, t.publicador3_id, t.publicador4_id
                ) if i is not None]
                assigned_count = len(existing_ids)
                self.log_pipeline(f"Turno #{t.id}: {assigned_count}/{max_slots} ocupados")

                if assigned_count >= max_slots:
                    self.log_pipeline("Turno ya completo.")
                    # commit transaction context automatically
                    self.finalize_pipeline()
                    return {"ok": True, "assigned": [], "message": "Turno ya completo", "pipeline_text": self.pipeline_text}

                assigned = []

                # ---- Paso 1: solicitudes "aprobadas" (en este modelo, tomamos solicitudes_turno con publicador_id != None) ----
                self.log_pipeline("Paso 1: solicitudes aprobadas (publicador_id presente en solicitudes_turno)")
                aprobadas = (
                    self.session.query(SolicitudTurno)
                    .filter(SolicitudTurno.punto_id == t.punto_id)
                    .filter(SolicitudTurno.publicador_id.isnot(None))
                    .order_by(SolicitudTurno.prioridad.desc(), SolicitudTurno.id.asc())
                    .all()
                )
                for s in aprobadas:
                    if assigned_count >= max_slots:
                        break
                    uid = int(s.publicador_id)
                    if uid in existing_ids or uid in assigned:
                        self.log_pipeline(f"Usuario {uid} ya en turno -> skip")
                        continue
                    ok_insert = self._insert_participante_in_turn(t, uid)
                    if ok_insert:
                        self.log_pipeline(f"Asignado aprobado: Usuario {uid}")
                        assigned.append(uid)
                        assigned_count += 1

                # ---- Paso 2: solicitudes "pendientes" (aquí consideramos solicitudes sin publicador_id) ----
                if assigned_count < max_slots:
                    self.log_pipeline("Paso 2: procesando solicitudes pendientes (solicitudes sin publicador_id)")
                    pendings = (
                        self.session.query(SolicitudTurno)
                        .filter(SolicitudTurno.punto_id == t.punto_id)
                        .filter(SolicitudTurno.publicador_id.is_(None))
                        .order_by(SolicitudTurno.prioridad.desc(), SolicitudTurno.id.asc())
                        .all()
                    )
                    for row in pendings:
                        if assigned_count >= max_slots:
                            break
                        # validar candidato: en este modelo no hay usuario en la fila, así que skip (no aplicable)
                        # (Se podría implementar: si hay una columna de usuario solicitante, procesar aquí)
                        # Por ahora interpretamos que pendings no contienen usuario -> no asignamos.
                        continue

                # ---- Paso 3: candidatos por disponibilidad y scoring ----
                if assigned_count < max_slots:
                    self.log_pipeline("Paso 3: habilitados por disponibilidad y scoring")
                    candidates = self._get_usuarios_disponibles_para_franja(t.fecha, t.hora_inicio, t.hora_fin)
                    if not candidates:
                        self.log_pipeline("No hay candidatos por disponibilidades para la franja")
                    else:
                        scored = self._score_candidates(candidates, t)
                        for entry in scored:
                            if assigned_count >= max_slots:
                                break
                            uid = int(entry["user_id"])
                            if uid in existing_ids or uid in assigned:
                                continue
                            ok_insert = self._insert_participante_in_turn(t, uid)
                            if ok_insert:
                                self.log_pipeline(f"Asignado por scoring user {uid} (score {entry.get('total')})")
                                assigned.append(uid)
                                assigned_count += 1

                # ---- Paso 4: fallback (no forzamos asignación si no hay candidatos) ----
                new_estado = "asignado" if assigned_count >= min_slots else "pendiente"
                # Intentar setear campo estado si existe en la tabla (no existe en modelo entregado)
                try:
                    if hasattr(t, "estado"):
                        setattr(t, "estado", new_estado)
                        self.session.add(t)
                except Exception:
                    # si no existe la columna, lo ignoramos
                    pass

                # crear notificaciones (en este esquema solo hacemos log) para cada asignado
                for uid in assigned:
                    self.log_pipeline(f"Crear notificacion para user {uid} (simulada)")

                # persist logs en archivo (no en DB, salvo que tengas tabla bot_logs)
                self.session.flush()  # asegurar que t esté actualizado
                # commit happen on exit of begin_nested / outer context if commit True

                if commit:
                    # commit outer transaction
                    self.session.commit()

                self.log_pipeline(f"Finalizado turno {t.id}. Usuarios asignados: {assigned}")
                self.finalize_pipeline()

                return {
                    "ok": True,
                    "assigned": assigned,
                    "estado": new_estado,
                    "pipeline_file": self.pipeline_filename,
                    "pipeline_text": self.pipeline_text,
                }

        except Exception as e:
            # rollback any pending transaction
            try:
                self.session.rollback()
            except Exception:
                pass
            self.log_pipeline(f"EXCEPCIÓN: {e}")
            self.finalize_pipeline()
            return {"ok": False, "error": str(e), "pipeline_text": self.pipeline_text}

    # ---------- Helpers ----------
    def _normalize_turno(self, input_val):
        if isinstance(input_val, Turno):
            return input_val
        if isinstance(input_val, int):
            return self.session.query(Turno).get(input_val)
        if isinstance(input_val, dict):
            tid = input_val.get("id")
            if tid:
                return self.session.query(Turno).get(int(tid))
        return None

    def _get_solicitudes_aprobadas(self, turno_id: int) -> List[int]:
        # En este modelo, entendemos solicitudes con publicador_id como "aprobadas"
        rows = (
            self.session.query(SolicitudTurno)
            .filter(SolicitudTurno.punto_id == self.session.query(Turno.punto_id).filter(Turno.id == turno_id).scalar_subquery())
            .filter(SolicitudTurno.publicador_id.isnot(None))
            .order_by(SolicitudTurno.prioridad.desc(), SolicitudTurno.id.asc())
            .all()
        )
        return [int(r.publicador_id) for r in rows if r.publicador_id]

    def _get_usuarios_disponibles_para_franja(self, fecha: datetime.date, hora_inicio: datetime.time, hora_fin: datetime.time) -> List[int]:
        """
        Buscamos publicadores que:
         - no estén en ausencia ese día
         - no tengan conflicto de turnos solapados
         - preferiblemente tengan una SolicitudTurno que cubra la franja (si existen)
         - si no hay solicitudes, devolvemos todos los publicadores que no estén ausentes ni con conflicto
        """
        weekday = fecha.isoweekday()  # 1..7
        # Primero: buscar publicadores que tienen SolicitudTurno cuya franja cubre este turno
        candidates = []
        sol_q = (
            self.session.query(SolicitudTurno)
            .filter(SolicitudTurno.hora_inicio <= hora_inicio)
            .filter(SolicitudTurno.hora_fin >= hora_fin)
            .filter(SolicitudTurno.dia == self._weekday_to_dia(weekday))
        ).all()
        for s in sol_q:
            if s.publicador_id:
                candidates.append(int(s.publicador_id))

        # Si no hay candidatos por solicitudes, buscar todos los publicadores y filtrar por ausencias / conflictos
        if not candidates:
            all_pubs = self.session.query(Publicador).all()
            for p in all_pubs:
                if self._user_has_ausencia(p.id, fecha):
                    continue
                if self._user_has_conflict(p.id, fecha, hora_inicio, hora_fin):
                    continue
                candidates.append(p.id)

        # remover duplicados y ordenar por menos asignaciones ese día (fairness)
        uniq = list(dict.fromkeys(candidates))
        uniq.sort(key=lambda uid: self._count_assignments_for_date(uid, fecha))
        return uniq

    def _weekday_to_dia(self, weekday: int) -> str:
        mapping = {1: "lunes", 2: "martes", 3: "miercoles", 4: "jueves", 5: "viernes", 6: "sabado", 7: "domingo"}
        return mapping.get(weekday, "lunes")

    def _tiene_disponibilidad(self, user_id: int, fecha: datetime.date, hora_inicio: datetime.time, hora_fin: datetime.time) -> bool:
        # En este modelo usamos SolicitudTurno como "disponibilidad explícita"
        count = (
            self.session.query(SolicitudTurno)
            .filter(SolicitudTurno.publicador_id == user_id)
            .filter(SolicitudTurno.dia == self._weekday_to_dia(fecha.isoweekday()))
            .filter(SolicitudTurno.hora_inicio <= hora_inicio)
            .filter(SolicitudTurno.hora_fin >= hora_fin)
            .count()
        )
        # si no hay filas para ese usuario en disponibilidades, asumimos disponible
        total_rows_user = (
            self.session.query(SolicitudTurno).filter(SolicitudTurno.publicador_id == user_id).count()
        )
        if total_rows_user == 0:
            return True
        return count > 0

    def _user_has_ausencia(self, user_id: int, fecha: datetime.date) -> bool:
        c = (
            self.session.query(Ausencia)
            .filter(Ausencia.publicador_id == user_id)
            .filter(Ausencia.fecha_inicio <= fecha, Ausencia.fecha_fin >= fecha)
            .count()
        )
        return c > 0

    def _user_has_conflict(self, user_id: int, fecha: datetime.date, hora_inicio: datetime.time, hora_fin: datetime.time) -> bool:
        # Revisar turnos del mismo día donde el usuario ya esté asignado
        q = (
            self.session.query(Turno)
            .filter(Turno.fecha == fecha)
            .filter(or_(
                Turno.publicador1_id == user_id,
                Turno.publicador2_id == user_id,
                Turno.publicador3_id == user_id,
                Turno.publicador4_id == user_id,
            ))
            .all()
        )
        for t in q:
            if time_overlap(t.hora_inicio, t.hora_fin, hora_inicio, hora_fin):
                return True
        return False

    def _count_assignments_for_date(self, user_id: int, fecha: datetime.date) -> int:
        return (
            self.session.query(Turno)
            .filter(Turno.fecha == fecha)
            .filter(or_(
                Turno.publicador1_id == user_id,
                Turno.publicador2_id == user_id,
                Turno.publicador3_id == user_id,
                Turno.publicador4_id == user_id,
            ))
            .count()
        )

    def _score_candidates(self, candidates: List[int], turno: Turno) -> List[Dict[str, Any]]:
        out = []
        for uid in candidates:
            sc = self._calcular_score_candidato(uid, turno)
            if sc.get("valido"):
                out.append(sc)
            else:
                self.log_pipeline(f"Candidato {uid} descartado: {sc.get('motivo')}")
        # order descending by total
        out.sort(key=lambda x: x.get("total", 0), reverse=True)
        return out

    def _calcular_score_candidato(self, user_id: int, turno: Turno) -> Dict[str, Any]:
        total = 0
        punto_id = turno.punto_id
        fecha = turno.fecha
        hora_inicio = turno.hora_inicio
        hora_fin = turno.hora_fin

        # 1) preferencia de punto (si existe user_point_preferences -> no model definido aquí; se omite)
        # 2) idioma compat (no modelizado) -> asumimos True
        total += 0

        # 3) disponibilidad requerida
        if self._tiene_disponibilidad(user_id, fecha, hora_inicio, hora_fin):
            total += self.peso_disponibilidad
        else:
            return {"valido": False, "motivo": "No disponible", "user_id": user_id}

        # 4) ausencia
        if self._user_has_ausencia(user_id, fecha):
            return {"valido": False, "motivo": "Ausente", "user_id": user_id}

        # 5) conflicto de turnos
        if self._user_has_conflict(user_id, fecha, hora_inicio, hora_fin):
            return {"valido": False, "motivo": "Conflicto horario", "user_id": user_id}

        # 6) fairness (penaliza por turnos recientes)
        cnt_recent = self._count_turnos_recientes(user_id, self.fairness_window_weeks)
        total -= cnt_recent * self.penalizacion_por_turnos_recientes

        # 7) rol solicitado previamente
        has_req_role = self._has_request_role(user_id, turno.id)
        if has_req_role:
            total += self.peso_rol

        return {"valido": True, "total": total, "user_id": user_id, "motivo": "OK"}

    def _count_turnos_recientes(self, user_id: int, weeks: int) -> int:
        cutoff = datetime.date.today() - datetime.timedelta(weeks=weeks)
        return (
            self.session.query(Turno)
            .filter(Turno.fecha >= cutoff)
            .filter(or_(
                Turno.publicador1_id == user_id,
                Turno.publicador2_id == user_id,
                Turno.publicador3_id == user_id,
                Turno.publicador4_id == user_id,
            ))
            .count()
        )

    def _has_request_role(self, user_id: int, turno_id: int) -> bool:
        c = (
            self.session.query(SolicitudTurno)
            .filter(SolicitudTurno.publicador_id == user_id)
            .filter(SolicitudTurno.punto_id == self.session.query(Turno.punto_id).filter(Turno.id == turno_id).scalar_subquery())
            .count()
        )
        return c > 0

    def _insert_participante_in_turn(self, turno_obj: Turno, user_id: int) -> bool:
        """Inserta el user_id en el primer slot libre del Turno (publicador1..4)."""
        try:
            if self._is_user_in_turn(turno_obj, user_id):
                self.log_pipeline(f"Usuario {user_id} ya estaba en el turno {turno_obj.id} -> skip")
                return False
            for slot in ("publicador1_id", "publicador2_id", "publicador3_id", "publicador4_id"):
                if getattr(turno_obj, slot) is None:
                    setattr(turno_obj, slot, int(user_id))
                    self.session.add(turno_obj)
                    # flush only (commit handled by caller)
                    try:
                        self.session.flush()
                    except Exception:
                        # ignore flush errors until commit
                        pass
                    return True
            return False
        except Exception as e:
            self.log_pipeline(f"Error insert_participante: {e}")
            return False

    def _is_user_in_turn(self, turno_obj: Turno, user_id: int) -> bool:
        return user_id in (
            x
            for x in (
                turno_obj.publicador1_id,
                turno_obj.publicador2_id,
                turno_obj.publicador3_id,
                turno_obj.publicador4_id,
            )
            if x is not None
        )


# ------------------- Flask endpoints -------------------
@bot_api.route("/ejecutar", methods=["POST"])
def api_ejecutar():
    """
    POST body (json) options:
      { "mode": "batch", "days_ahead": 30 }  -> run_batch
      { "mode": "turno", "turno_id": 123 }   -> run_for_turno
    """
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "batch")
    bot = BotAsignador(session=db.session)

    try:
        if mode == "rango":
            f1 = datetime.datetime.strptime(data.get("fecha_desde"), "%Y-%m-%d").date()
            f2 = datetime.datetime.strptime(data.get("fecha_hasta"), "%Y-%m-%d").date()


            bot.log(f"=== Asignación por rango {f1} → {f2} ===")

            q = Turno.query.filter(Turno.fecha >= f1, Turno.fecha <= f2).order_by(Turno.fecha, Turno.hora_inicio)
            turnos = q.all()

            asignados = []

            for t in turnos:
                incompleto = not all([
                    t.publicador1_id,
                    t.publicador2_id,
                    t.publicador3_id,
                    t.publicador4_id
                ])
                if not incompleto:
                    bot.log(f"Turno #{t.id} completo → saltando")
                    continue

                bot.log(f"Procesando turno #{t.id} {t.fecha} {t.hora_inicio}-{t.hora_fin}")
                asignados_turno = bot.asignar_turno(t)
                asignados.extend(asignados_turno)

            # guardar log + pipeline
            bot.finalize_pipeline()
            return {
                "ok": True,
                "asignados": asignados,
                "pipeline_text": bot.pipeline_text
            }
        if mode == "turno":
            turno_id = data.get("turno_id")
            if not turno_id:
                return jsonify({"ok": False, "error": "turno_id requerido para modo 'turno'"}), 400
            resp = bot.run_for_turno(int(turno_id))
            return jsonify(resp)
        else:
            days = int(data.get("days_ahead", 14))
            resp = bot.run_batch(days_ahead=days)
            return jsonify(resp)
    except Exception as e:
        current_app.logger.exception("Error en /api/bot/ejecutar")
        return jsonify({"ok": False, "error": str(e)}), 500

        

@bot_api.route("/estado", methods=["GET"])
def api_estado():
    return jsonify({"ok": True, "estado": "módulo bot operativo"})


@bot_api.route("/metricas", methods=["GET"])
def api_metricas():
    # Placeholder: podrías exponer métricas desde DB o logs guardados
    return jsonify({"ok": True, "info": "Métricas no implementadas (placeholder)"})


# Helper to call from code
def run_batch_from_code(days_ahead: int = 14):
    b = BotAsignador(session=db.session)
    return b.run_batch(days_ahead=days_ahead)
