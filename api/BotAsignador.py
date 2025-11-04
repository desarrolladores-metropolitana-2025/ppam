# BotAsignador.py
# Versión Python del BotAsignador.php
# Requisitos: pip install mysql-connector-python
# Uso: from BotAsignador import BotAsignador

import mysql.connector
from mysql.connector import MySQLConnection, Error
from typing import Any, Dict, List, Optional
import json
import os
import datetime
import time
import uuid
import traceback


class BotAsignador:
    def __init__(self, conn: MySQLConnection, opts: Optional[Dict[str, Any]] = None):
        self.conn = conn
        self.logs: List[str] = []
        self.pipelineSteps: List[str] = []
        self.pipelineFilename: str = ''
        self.pipelineAscii: str = ''
        # Configurables (por defecto iguales al PHP)
        self.autoApprovePending: bool = True
        self.useFairness: bool = True
        self.fairnessWindowWeeks: int = 4
        self.maxAssignPerRun: int = 200
        # Pesos
        self.pesoPreferido: int = 30
        self.pesoPosible: int = 10
        self.pesoIdioma: int = 10
        self.pesoDisponibilidad: int = 20
        self.pesoRol: int = 5
        self.penalizacionPorTurnosRecientes: int = 1

        if opts:
            for k, v in opts.items():
                if hasattr(self, k):
                    setattr(self, k, v)

        # pipeline filename in /tmp (unique)
        ts = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        uniq = uuid.uuid4().hex[:8]
        self.pipelineFilename = os.path.join('/tmp', f'bot_pipeline_{ts}_{uniq}.txt')
        self.logPipeline(f"Inicio BotAsignador V->py: {datetime.datetime.utcnow().isoformat()}")

    # ---------------------- API principal ----------------------
    def runBatch(self, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        daysAhead = int(options.get('daysAhead', 14))
        self.log(f"Modo batch: buscando turnos con vacantes en próximos {daysAhead} días")

        sql = """
            SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.punto_id, p.maximo_publicadores, p.minimo_publicadores
            FROM turnos t
            JOIN puntos p ON p.id = t.punto_id
            WHERE t.fecha BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL %s DAY)
            ORDER BY t.fecha, t.hora_inicio
            LIMIT %s
        """
        cur = self.conn.cursor(dictionary=True)
        cur.execute(sql, (daysAhead, self.maxAssignPerRun))
        turnos = cur.fetchall()
        cur.close()

        out = {'ok': True, 'processed': 0, 'results': [], 'log': []}
        for t in turnos:
            res = self.asignarTurno(int(t['id']))
            out['results'].append(res)
            out['processed'] += 1

        self.finalizePipeline()
        out['log'] = self.logs
        return out

    def run_for_turno(self, turnoId: int) -> Dict[str, Any]:
        return self.asignarTurno(turnoId)

    # -------------------- Core: asignarTurno -------------------
    def asignarTurno(self, turnoInput: Any) -> Dict[str, Any]:
        self.logs = []
        self.logPipeline(f"=== Procesando turno input: {json.dumps(turnoInput, default=str)}")
        turno = self.normalizeTurno(turnoInput)
        if not turno or 'id' not in turno:
            self.finalizePipeline()
            return {'ok': False, 'error': 'Turno no encontrado o invalido', 'log': self.logs}

        turnoId = int(turno['id'])
        self.log(f"Iniciando asignación turno #{turnoId}")

        try:
            # iniciar transacción
            self.conn.start_transaction()

            # Lock del turno + punto FOR UPDATE
            sql_lock = """
                SELECT t.*, p.minimo_publicadores, p.maximo_publicadores, p.id AS punto_id
                FROM turnos t
                JOIN puntos p ON t.punto_id = p.id
                WHERE t.id = %s FOR UPDATE
            """
            cur = self.conn.cursor(dictionary=True)
            cur.execute(sql_lock, (turnoId,))
            t = cur.fetchone()
            if not t:
                self.log(f"Turno no encontrado: {turnoId}")
                self.conn.rollback()
                cur.close()
                self.finalizePipeline()
                return {'ok': False, 'error': f'Turno no encontrado: {turnoId}', 'log': self.logs}
            turno = t
            fecha = turno['fecha']
            horaInicio = (turno['hora_inicio'][:8] if isinstance(turno['hora_inicio'], str) else str(turno['hora_inicio']))[:8]
            horaFin = (turno['hora_fin'][:8] if isinstance(turno['hora_fin'], str) else str(turno['hora_fin']))[:8]
            maxSlots = int(turno.get('maximo_publicadores') or 3)
            minSlots = int(turno.get('minimo_publicadores') or 1)
            puntoId = int(turno.get('punto_id'))

            # participantes ya presentes
            cur2 = self.conn.cursor(dictionary=True)
            cur2.execute("SELECT usuario_id, rol FROM turno_participantes WHERE turno_id = %s", (turnoId,))
            existentes = cur2.fetchall()
            assignedCount = len(existentes)
            self.logPipeline(f"Turno #{turnoId}: {assignedCount}/{maxSlots} ocupados")

            if assignedCount >= maxSlots:
                self.log(f"Turno ya completo: {assignedCount}/{maxSlots}")
                self.conn.commit()
                cur.close()
                cur2.close()
                self.finalizePipeline()
                return {'ok': True, 'assigned': [], 'message': 'Turno ya completo', 'log': self.logs}

            assigned: List[int] = []

            # 1) solicitudes aprobadas
            self.logPipeline("Paso 1: solicitudes aprobadas")
            aprobadas = self.getSolicitudesAprobadas(turnoId)
            for uid in aprobadas:
                if assignedCount >= maxSlots:
                    break
                if self.isUserInList(uid, existentes):
                    self.logPipeline(f"Usuario {uid} ya en turno -> skip")
                    continue
                if self.insertParticipante(turnoId, int(uid), 'publicador'):
                    self.logPipeline(f"Asignado aprobado: Usuario {uid}")
                    assigned.append(uid)
                    assignedCount += 1

            # 2) solicitudes pendientes
            if assignedCount < maxSlots:
                self.logPipeline("Paso 2: procesando solicitudes pendientes (auto-approve si aplica)")
                pendings = self.getSolicitudesPendientesFull(turnoId)
                for row in pendings:
                    if assignedCount >= maxSlots:
                        break
                    uid = int(row['usuario_id'])
                    if self.isUserInList(uid, existentes):
                        continue
                    score = self.calcularScoreCandidato(uid, turno)
                    if not score['valido']:
                        self.logPipeline(f"Pendiente usuario nro. {uid} descartado: {score['motivo']}")
                        continue
                    if self.autoApprovePending and row.get('id'):
                        self.autoAprobarSolicitud(int(row['id']))
                    if self.insertParticipante(turnoId, uid, row.get('rol') or 'publicador'):
                        self.logPipeline(f"Asignado pendiente (auto) user {uid}")
                        assigned.append(uid)
                        assignedCount += 1

            # 3) fairness + scoring: candidatos por disponibilidad
            if assignedCount < maxSlots:
                self.logPipeline("Paso 3: habilitados + puntaje de candidatos por disponibilidad")
                candidates = self.getUsuariosDisponiblesParaFranja(str(fecha), horaInicio, horaFin)
                if not candidates:
                    self.logPipeline("No hay candidatos por disponibilidades para la franja")
                else:
                    scored = self.scoreCandidates(candidates, turno)
                    for entry in scored:
                        if assignedCount >= maxSlots:
                            break
                        uid = int(entry['user_id'])
                        if self.isUserInList(uid, existentes):
                            continue
                        if self.insertParticipante(turnoId, uid, 'publicador'):
                            self.logPipeline(f"Asignado por scoring user {uid} (score {entry.get('total')})")
                            assigned.append(uid)
                            assignedCount += 1

            # 4) fallback -> estado
            newEstado = 'asignado' if assignedCount >= minSlots else 'pendiente'
            u = self.conn.cursor()
            u.execute("UPDATE turnos SET estado = %s, updated_at = NOW() WHERE id = %s", (newEstado, turnoId))
            u.close()

            # Crear notificaciones sólo para los que se insertaron ahora
            for uid in assigned:
                self.crearNotificacionSiNoExiste(turnoId, int(uid), 'cubierto', f"Has sido asignado al turno #{turnoId}", {'turno': turnoId})

            # Notificaciones generales para el turno
            self.crearNotificacionesParaTurno(turnoId)

            # persist logs en DB si está la tabla
            self.persistBotLog(turnoId, self.logs)

            self.conn.commit()
            self.logPipeline(f"Finalizado turno {turnoId}. Usuarios asignados (ID de cada uno): {json.dumps(assigned)}")

            cur.close()
            cur2.close()
            # finalizePipeline already called below
            self.finalizePipeline()

            pipeline_file = self.pipelineFilename
            pipeline_ascii = self.pipelineAscii or (("\n".join(self.pipelineSteps) + "\n") if self.pipelineSteps else "")

            return {
                'ok': True,
                'assigned': assigned,
                'estado': newEstado,
                'log': self.logs,
                'pipeline_file': pipeline_file,
                'pipeline_ascii': pipeline_ascii
            }

        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            tb = traceback.format_exc()
            self.log(f"Excepción en asignarTurno: {str(e)}")
            self.logPipeline(f"EXCEPCIÓN: {str(e)}")
            self.logPipeline(tb)
            self.finalizePipeline()
            return {'ok': False, 'error': str(e), 'log': self.logs}

    # ---------------- Helper: normalizar/obtener turno ----------------
    def normalizeTurno(self, input_data: Any) -> Dict[str, Any]:
        if isinstance(input_data, dict) and input_data.get('id'):
            return input_data
        if isinstance(input_data, int) or (isinstance(input_data, str) and input_data.isdigit()):
            cur = self.conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM turnos WHERE id = %s", (int(input_data),))
            row = cur.fetchone()
            cur.close()
            return row or {}
        return dict(input_data) if isinstance(input_data, dict) else {}

    # ---------------- Solicitudes helpers ----------------
    def getSolicitudesAprobadas(self, turnoId: int) -> List[int]:
        cur = self.conn.cursor()
        cur.execute("SELECT usuario_id FROM solicitudes WHERE turno_id = %s AND estado = 'aprobada' ORDER BY fecha_solicitud ASC", (turnoId,))
        rows = cur.fetchall()
        cur.close()
        return [int(r[0]) for r in rows]

    def getSolicitudesPendientesFull(self, turnoId: int) -> List[Dict[str, Any]]:
        cur = self.conn.cursor(dictionary=True)
        cur.execute("SELECT id, usuario_id, rol FROM solicitudes WHERE turno_id = %s AND estado = 'pendiente' ORDER BY fecha_solicitud ASC", (turnoId,))
        rows = cur.fetchall()
        cur.close()
        return rows

    def autoAprobarSolicitud(self, solId: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE solicitudes SET estado = 'aprobada', processed_at = NOW() WHERE id = %s", (solId,))
        cur.close()
        self.logPipeline(f"Auto-aprobada solicitud #{solId}")

    # ----------------- Scoring / Fairness / Candidates -----------------
    def getUsuariosDisponiblesParaFranja(self, fecha: str, horaInicio: str, horaFin: str) -> List[int]:
        # weekday 1..7
        wd = datetime.date.fromisoformat(str(fecha)).isoweekday() if isinstance(fecha, (str,)) else datetime.date.fromordinal(fecha).isoweekday()
        sql = """
            SELECT DISTINCT d.usuario_id FROM disponibilidades d
            WHERE d.dia_semana = %s
              AND NOT (d.hora_fin <= %s OR d.hora_inicio >= %s)
            ORDER BY d.usuario_id
        """
        cur = self.conn.cursor()
        cur.execute(sql, (wd, horaInicio, horaFin))
        rows = cur.fetchall()
        cur.close()
        return [int(r[0]) for r in rows]

    def scoreCandidates(self, candidates: List[int], turno: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for uid in candidates:
            s = self.calcularScoreCandidato(int(uid), turno)
            if s.get('valido'):
                out.append(s)
            else:
                self.logPipeline(f"Candidato nro {uid} descartado: {s.get('motivo')}")
        out.sort(key=lambda x: x.get('total', 0), reverse=True)
        # fairness handled in calcularScoreCandidato via penalizacion por turnos recientes
        return out

    def calcularScoreCandidato(self, userId: int, turno: Dict[str, Any]) -> Dict[str, Any]:
        total = 0
        puntoId = int(turno.get('punto_id') or 0)
        fecha = str(turno.get('fecha'))
        horaInicio = str(turno.get('hora_inicio'))[:5]
        horaFin = str(turno.get('hora_fin'))[:5]

        # 1) Preferencia de punto
        pref = self.getPreferenciaPunto(userId, puntoId)
        if pref == 'no_posible':
            return {'valido': False, 'motivo': 'Punto marcado no_posible', 'user_id': userId}
        if pref == 'preferido':
            total += self.pesoPreferido
        if pref == 'posible':
            total += self.pesoPosible

        # 2) Idioma
        if self.idiomaCompatible(userId, puntoId):
            total += self.pesoIdioma

        # 3) Disponibilidad (requerida)
        if self.tieneDisponibilidad(userId, fecha, horaInicio, horaFin):
            total += self.pesoDisponibilidad
        else:
            return {'valido': False, 'motivo': 'No disponible', 'user_id': userId}

        # 4) Ausencia
        if self.tieneAusencia(userId, fecha):
            return {'valido': False, 'motivo': 'Ausente', 'user_id': userId}

        # 5) Conflicto de turnos
        if self.tieneConflictoTurnos(userId, fecha, horaInicio, horaFin):
            return {'valido': False, 'motivo': 'Conflicto horario', 'user_id': userId}

        # 6) Fairness penaliza
        cntRecent = self.countTurnosRecientes(userId, self.fairnessWindowWeeks)
        total -= cntRecent * self.penalizacionPorTurnosRecientes

        # 7) rol solicitado previamente
        solRole = self.hasRequestRole(userId, int(turno.get('id')))
        if solRole:
            total += self.pesoRol

        return {'valido': True, 'total': total, 'user_id': userId, 'motivo': 'OK'}

    # ---------------- DB checks / utilitarios ----------------
    def getPreferenciaPunto(self, userId: int, puntoId: int) -> Optional[str]:
        if not self.tableHasColumn('user_point_preferences', 'nivel'):
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT nivel FROM user_point_preferences WHERE usuario_id = %s AND punto_id = %s LIMIT 1", (userId, puntoId))
        row = cur.fetchone()
        cur.close()
        return row[0] if row and row[0] is not None else None

    def idiomaCompatible(self, userId: int, puntoId: int) -> bool:
        if self.tableHasColumn('puntos', 'idiomas_id') and self.tableHasColumn('users', 'idiomas_id'):
            sql = """
                SELECT CASE WHEN u.idiomas_id IS NULL OR p.idiomas_id IS NULL OR u.idiomas_id = p.idiomas_id THEN 1 ELSE 0 END
                FROM users u JOIN puntos p ON p.id = %s WHERE u.id = %s
            """
            cur = self.conn.cursor()
            cur.execute(sql, (puntoId, userId))
            row = cur.fetchone()
            cur.close()
            return bool(row and row[0] == 1)
        return True

    def tieneDisponibilidad(self, userId: int, fecha: str, horaInicio: str, horaFin: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM disponibilidades WHERE usuario_id = %s", (userId,))
        has_any = int(cur.fetchone()[0])
        if not (has_any > 0):
            cur.close()
            return True  # treat as available if no records
        wd = datetime.date.fromisoformat(fecha).isoweekday()
        cur.execute(
            "SELECT COUNT(*) FROM disponibilidades WHERE usuario_id = %s AND dia_semana = %s AND NOT (hora_fin <= %s OR hora_inicio >= %s)",
            (userId, wd, horaInicio, horaFin)
        )
        cnt = int(cur.fetchone()[0])
        cur.close()
        return cnt > 0

    def tieneAusencia(self, userId: int, fecha: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ausencias WHERE usuario_id = %s AND fecha_inicio <= %s AND fecha_fin >= %s", (userId, fecha, fecha))
        cnt = int(cur.fetchone()[0])
        cur.close()
        return cnt > 0

    def tieneConflictoTurnos(self, userId: int, fecha: str, horaInicio: str, horaFin: str) -> bool:
        sql = """
            SELECT COUNT(*) FROM turno_participantes tp JOIN turnos t ON tp.turno_id = t.id
            WHERE tp.usuario_id = %s AND t.fecha = %s AND NOT (t.hora_fin <= %s OR t.hora_inicio >= %s) AND t.estado IN ('asignado','planificado','pendiente')
        """
        cur = self.conn.cursor()
        cur.execute(sql, (userId, fecha, horaInicio, horaFin))
        cnt = int(cur.fetchone()[0])
        cur.close()
        return cnt > 0

    def countTurnosRecientes(self, userId: int, weeks: int = 4) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM turno_participantes tp JOIN turnos t ON tp.turno_id = t.id WHERE tp.usuario_id = %s AND t.fecha >= DATE_SUB(CURDATE(), INTERVAL %s WEEK)", (userId, weeks))
        cnt = int(cur.fetchone()[0])
        cur.close()
        return cnt

    def hasRequestRole(self, userId: int, turnoId: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM solicitudes WHERE usuario_id = %s AND turno_id = %s", (userId, turnoId))
        cnt = int(cur.fetchone()[0])
        cur.close()
        return cnt > 0

    # ---------------- DB insert participante (defensivo) ----------------
    def isUserInList(self, userId: int, rows: List[Dict[str, Any]]) -> bool:
        for r in rows:
            val = r.get('usuario_id') if isinstance(r, dict) else r
            if int(val) == int(userId):
                return True
        return False

    def insertParticipante(self, turnoId: int, userId: int, rol: str) -> bool:
        if not userId:
            self.logPipeline("insertParticipante: usuario_id inválido")
            return False
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM turno_participantes WHERE turno_id = %s AND usuario_id = %s", (turnoId, userId))
        if int(cur.fetchone()[0]) > 0:
            cur.close()
            self.logPipeline(f"Usuario {userId} ya estaba asignado al turno {turnoId} (skip)")
            return False
        try:
            ins = self.conn.cursor()
            ins.execute(
                "INSERT INTO turno_participantes (turno_id, usuario_id, rol, asignado_por, asignado_en, asistio) VALUES (%s, %s, %s, %s, NOW(), 0)",
                (turnoId, userId, rol, None)
            )
            ins.close()
            self.logPipeline(f"insertParticipante: insert OK user {userId} turno {turnoId}")
            return True
        except Exception as e:
            self.logPipeline(f"Excepción insertParticipante: {str(e)}")
            return False

    # ---------------- Notificaciones ----------------
    def crearNotificacionSiNoExiste(self, turno_id: int, usuario_id: int, tipo: str, mensaje: str, payload: Any = None) -> bool:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM notificaciones WHERE turno_id=%s AND usuario_id=%s AND tipo=%s AND creado_en >= DATE_SUB(NOW(), INTERVAL 1 HOUR)", (turno_id, usuario_id, tipo))
            if int(cur.fetchone()[0]) > 0:
                cur.close()
                return False
            ins = self.conn.cursor()
            ins.execute("INSERT INTO notificaciones (turno_id, usuario_id, tipo, mensaje, payload, canal, estado, creado_en) VALUES (%s, %s, %s, %s, %s, 'ambos', 'pending', NOW())",
                        (turno_id, usuario_id, tipo, mensaje, json.dumps(payload) if payload is not None else None))
            ins.close()
            cur.close()
            self.logPipeline(f"Notificacion creada para usuario {usuario_id} tipo {tipo} (turno {turno_id})")
            return True
        except Exception as e:
            self.logPipeline(f"Error crearNotificacionSiNoExiste: {str(e)}")
            return False

    def crearNotificacionesParaTurno(self, turnoId: int):
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT usuario_id FROM turno_participantes WHERE turno_id = %s", (turnoId,))
            users = [r[0] for r in cur.fetchall()]
            cur.close()
            for u in users:
                self.crearNotificacionSiNoExiste(turnoId, int(u), 'cubierto', f"Has sido asignado al turno #{turnoId}", {'turno': turnoId})
            self.logPipeline(f"crearNotificacionesParaTurno completado para turno {turnoId}")
        except Exception as e:
            self.logPipeline(f"Error crearNotificacionesParaTurno: {str(e)}")

    # -------------- Persistir logs en bot_logs --------------
    def persistBotLog(self, turnoId: int, logs: List[str]):
        if not self.tableHasColumn('bot_logs', 'mensaje'):
            return
        try:
            stmt = self.conn.cursor()
            for l in logs:
                stmt.execute("INSERT INTO bot_logs (turno_id, mensaje) VALUES (%s, %s)", (turnoId, l))
            stmt.close()
            self.logPipeline(f"Agregados {len(logs)} logs en bot_logs")
        except Exception as e:
            self.logPipeline(f"Error persistBotLog: {str(e)}")

    # ---------------- Utility / tabla existencia ----------------
    def tableHasColumn(self, table: str, column: str) -> bool:
        cur = self.conn.cursor()
        sql = "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s"
        cur.execute(sql, (table, column))
        cnt = int(cur.fetchone()[0])
        cur.close()
        return cnt > 0

    # ---------------- Logging / pipeline ASCII ----------------
    def log(self, txt: str):
        self.logs.append(f"{datetime.datetime.utcnow().isoformat()} {txt}")

    def logPipeline(self, line: str):
        ts = datetime.datetime.utcnow().isoformat()
        self.pipelineSteps.append(f"[{ts}] {line}")
        self.log(line)

    def finalizePipeline(self):
        try:
            if self.pipelineSteps:
                content = "\n".join(self.pipelineSteps) + "\n"
                # write full content
                with open(self.pipelineFilename, 'w', encoding='utf-8') as f:
                    f.write(content)
                finalLine = f"[{datetime.datetime.utcnow().isoformat()}] Pipeline escrito en {self.pipelineFilename}"
                self.pipelineSteps.append(finalLine)
                self.logs.append(finalLine)
                # append final to file
                with open(self.pipelineFilename, 'a', encoding='utf-8') as f:
                    f.write(finalLine + "\n")
                self.pipelineAscii = "\n".join(self.pipelineSteps) + "\n"
                # logPipeline appends, but avoid infinite recursion; append minimal log
                self.logs.append(f"Pipeline escrito en {self.pipelineFilename}")
            else:
                self.pipelineAscii = ""
        except Exception as e:
            self.logPipeline(f"Error escribiendo pipeline en archivo: {str(e)}")
            self.pipelineAscii = "\n".join(self.pipelineSteps) + "\n"

    # ---------------- Métodos auxiliares reutilizables ----------------
    def getSolicitudesAprobadasByRole(self, turnoId: int, rol: str = 'publicador') -> List[int]:
        cur = self.conn.cursor()
        cur.execute("SELECT usuario_id FROM solicitudes WHERE turno_id = %s AND estado = 'aprobada' AND rol = %s ORDER BY fecha_solicitud ASC", (turnoId, rol))
        rows = cur.fetchall()
        cur.close()
        return [int(r[0]) for r in rows]

    def isUserAssignedInTurn(self, turnoId: int, userId: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM turno_participantes WHERE turno_id = %s AND usuario_id = %s", (turnoId, userId))
        cnt = int(cur.fetchone()[0])
        cur.close()
        return cnt > 0

    def crearNotificacion(self, turnoId: int, userId: int, tipo: str, mensaje: str):
        try:
            cur = self.conn.cursor()
            cur.execute("INSERT INTO notificaciones (turno_id, usuario_id, tipo, mensaje, canal, estado, creado_en) VALUES (%s, %s, %s, %s, 'ambos', 'pending', NOW())",
                        (turnoId, userId, tipo, mensaje))
            cur.close()
        except Exception as e:
            self.logPipeline(f"Error crearNotificacion: {str(e)}")
