<?php
// services/BotAsignador.php
// BotAsignador — versión final combinada
// - Comportamiento: solicitudes aprobadas -> pendientes -> fairness -> disponibilidad -> preferencias
// - Genera pipeline ASCII y lo escribe en /tmp/bot_pipeline_{ts}.txt
// - Registra en bot_logs si existe la tabla
// - Compatible con las tablas: turnos, turno_participantes, disponibilidades, solicitudes, notificaciones, user_point_preferences, ausencias, puntos, users
// - Uso: $b = new BotAsignador($pdo); $b->runForTurno($turnoId) OR $b->runBatch($options)

// Requisitos:
// - $pdo: instancia PDO con atributos apropiados.
// - PHP con permiso de escritura en /tmp (confirmado por el usuario).
// - Tablas: turnos, turno_participantes, solicitudes, disponibilidades, notificaciones, user_point_preferences, ausencias, bot_logs (opcional).

class BotAsignador
{
    private \PDO $pdo;
    private array $logs = [];
    private array $pipelineSteps = []; // guarda el pipeline ASCII lines
    private string $pipelineFilename = '';
	private string $pipelineAscii = '';

    // Configurables
    public bool $autoApprovePending = true;
    public bool $useFairness = true;
    public int  $fairnessWindowWeeks = 4;
    public int  $maxAssignPerRun = 200; // proteção para batch
    // Pesos (puedes ajustar)
    public int $pesoPreferido = 30;
    public int $pesoPosible = 10;
    public int $pesoIdioma = 10;
    public int $pesoDisponibilidad = 20;
    public int $pesoRol = 5;
    public int $penalizacionPorTurnosRecientes = 1;
	
    public function __construct(\PDO $pdo, array $opts = [])
    {
        $this->pdo = $pdo;
        foreach ($opts as $k => $v) if (property_exists($this, $k)) $this->$k = $v;
        // $this->pipelineFilename = __DIR__ . '/../tmp/bot_pipeline_' . date('Ymd_His') . '.txt';
		$this->pipelineFilename = __DIR__ . '/../tmp/bot_pipeline_' . date('Ymd_His') . '_' . uniqid() . '.txt';

		// $this->pipelineFilename = sys_get_temp_dir() . '/bot_pipeline_' . date('Ymd_His') . '.txt';
        $this->logPipeline("Inicio BotAsignador V->4.1.2: " . date('c'));
    }

    /* ---------------------- API principal ---------------------- */

    // Ejecuta el pipeline completo en modo batch: busca turnos con vacantes en próximos X días
    // opciones: ['daysAhead' => 14]
    public function runBatch(array $options = []): array
    {
        $daysAhead = (int)($options['daysAhead'] ?? 14);
        $this->log("Modo batch: buscando turnos con vacantes en próximos {$daysAhead} días");

        $stmt = $this->pdo->prepare("
            SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.punto_id, p.maximo_publicadores, p.minimo_publicadores
            FROM turnos t
            JOIN puntos p ON p.id = t.punto_id
            WHERE t.fecha BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL ? DAY)
            ORDER BY t.fecha, t.hora_inicio
            LIMIT ?
        ");
        $stmt->execute([$daysAhead, $this->maxAssignPerRun]);
        $turnos = $stmt->fetchAll(\PDO::FETCH_ASSOC);

        $out = ['ok'=>true, 'processed'=>0, 'results'=>[], 'log'=>[]];
        foreach ($turnos as $t) {
            $res = $this->asignarTurno((int)$t['id']);
            $out['results'][] = $res;
            $out['processed']++;
        }

        $this->finalizePipeline();
        $out['log'] = $this->logs;
        return $out;
    }

    // Ejecuta asignación para un turno (ID) — protecciones internas
    public function runForTurno(int $turnoId): array
    {
        return $this->asignarTurno($turnoId);
    }

    /* -------------------- Core: asignarTurno ------------------- */
    // pipeline híbrido que implementa la lógica descrita.
    public function asignarTurno($turnoInput): array
    {
        $this->logs = [];
        $this->logPipeline("=== Procesando turno input: " . json_encode($turnoInput));
        $turno = $this->normalizeTurno($turnoInput);
        $turnoId = (int)$turno['id'];
        $this->log("Iniciando asignación turno #$turnoId");

        try {
            $this->pdo->beginTransaction();

            // Lock del turno + punto para evitar races
            $stmt = $this->pdo->prepare("
                SELECT t.*, p.minimo_publicadores, p.maximo_publicadores, p.id AS punto_id
                FROM turnos t
                JOIN puntos p ON t.punto_id = p.id
                WHERE t.id = ? FOR UPDATE
            ");
            $stmt->execute([$turnoId]);
            $t = $stmt->fetch(\PDO::FETCH_ASSOC);
            if (!$t) {
                $this->log("Turno no encontrado: $turnoId");
                $this->pdo->rollBack();
                $this->finalizePipeline();
                return ['ok'=>false,'error'=>"Turno no encontrado: $turnoId", 'log'=>$this->logs];
            }
            $turno = $t;
            $fecha = $turno['fecha'];
            $horaInicio = substr($turno['hora_inicio'],0,8);
            $horaFin = substr($turno['hora_fin'],0,8);
            // $maxSlots = (int)($turno['maximo_publicadores'] ?? $turno['maximo_publicadores'] ?? 3);
			$maxSlots = (int)($turno['maximo_publicadores'] ?? 3);

            $minSlots = (int)($turno['minimo_publicadores'] ?? 1);
            $puntoId = (int)$turno['punto_id'];

            // participantes ya presentes
            $stmt = $this->pdo->prepare("SELECT usuario_id, rol FROM turno_participantes WHERE turno_id = ?");
            $stmt->execute([$turnoId]);
            $existentes = $stmt->fetchAll(\PDO::FETCH_ASSOC);
            $assignedCount = count($existentes);

            $this->logPipeline("Turno #$turnoId: $assignedCount/$maxSlots ocupados");

            if ($assignedCount >= $maxSlots) {
                $this->log("Turno ya completo: $assignedCount/$maxSlots");
                $this->pdo->commit();
                $this->finalizePipeline();
                return ['ok'=>true,'assigned'=>[],'message'=>'Turno ya completo','log'=>$this->logs];
            }

            $assigned = [];

            // 1) solicitudes aprobadas (capitanes y publicadores)
            $this->logPipeline("Paso 1: solicitudes aprobadas");
            $aprobadas = $this->getSolicitudesAprobadas($turnoId);
            foreach ($aprobadas as $uid) {
                if ($assignedCount >= $maxSlots) break;
                if ($this->isUserInList($uid, $existentes)) { $this->logPipeline("Usuario $uid ya en turno -> skip"); continue; }
                if ($this->insertParticipante($turnoId, (int)$uid, 'publicador')) {
                    $this->logPipeline("Asignado aprobado: Usuario $uid");
                    $assigned[] = $uid;
                    $assignedCount++;
                }
            }

            // 2) solicitudes pendientes (orden por fecha_solicitud)
            if ($assignedCount < $maxSlots) {
                $this->logPipeline("Paso 2: procesando solicitudes pendientes (auto-approve si aplica)");
                $pendings = $this->getSolicitudesPendientesFull($turnoId);
                foreach ($pendings as $row) {
                    if ($assignedCount >= $maxSlots) break;
                    $uid = (int)$row['usuario_id'];
                    if ($this->isUserInList($uid, $existentes)) continue;
                    // validar candidato rápidamente con scoring (valido/no)
                    $score = $this->calcularScoreCandidato($uid, $turno);
                    if (!$score['valido']) {
                        $this->logPipeline("Pendiente usuario nro. $uid descartado: {$score['motivo']}");
                        continue;
                    }
                    if ($this->autoApprovePending && !empty($row['id'])) $this->autoAprobarSolicitud($row['id']);
                    if ($this->insertParticipante($turnoId, $uid, $row['rol'] ?? 'publicador')) {
                        $this->logPipeline("Asignado pendiente (auto) user $uid");
                        $assigned[] = $uid;
                        $assignedCount++;
                    }
                }
            }

            // 3) fairness + scoring: candidatos por disponibilidad (solo si quedan plazas)
            if ($assignedCount < $maxSlots) {
                $this->logPipeline("Paso 3: habilitados + puntaje de candidatos por disponibilidad");
                $candidates = $this->getUsuariosDisponiblesParaFranja($fecha, $horaInicio, $horaFin);
                if (empty($candidates)) {
                    $this->logPipeline("No hay candidatos por disponibilidades para la franja");
                } else {
                    // score & order
                    $scored = $this->scoreCandidates($candidates, $turno);
                    foreach ($scored as $entry) {
                        if ($assignedCount >= $maxSlots) break;
                        $uid = (int)$entry['user_id'];
                        if ($this->isUserInList($uid, $existentes)) continue;
                        if ($this->insertParticipante($turnoId, $uid, 'publicador')) {
                            $this->logPipeline("Asignado por scoring user $uid (score {$entry['total']})");
                            $assigned[] = $uid;
                            $assignedCount++;
                        }
                    }
                }
            }

            // 4) fallback: si aún hay plazas y no hay candidatos, podemos dejar vacante o notificar admin (no forzamos)
            $newEstado = ($assignedCount >= $minSlots) ? 'asignado' : 'pendiente';
            $this->pdo->prepare("UPDATE turnos SET estado = ?, updated_at = NOW() WHERE id = ?")->execute([$newEstado, $turnoId]);

            // Crear notificaciones sólo para los que se insertaron ahora
            foreach ($assigned as $uid) {
                $this->crearNotificacionSiNoExiste($turnoId, (int)$uid, 'cubierto', "Has sido asignado al turno #$turnoId", ['turno'=>$turnoId]);
            }

            // También crear notificaciones generales para el turno (simple)
            $this->crearNotificacionesParaTurno($turnoId);

            // persist logs en DB si está la tabla
            $this->persistBotLog($turnoId, $this->logs);

            $this->pdo->commit();
            $this->logPipeline("Finalizado turno $turnoId. Usuarios asignados (ID de cada uno): " . json_encode($assigned));

            $this->finalizePipeline();

            // Asegurarnos que finalizePipeline() ya llenó pipelineAscii
$pipeline_file = $this->pipelineFilename;
$pipeline_ascii = $this->pipelineAscii ?? ( !empty($this->pipelineSteps) ? implode("\n", $this->pipelineSteps) . "\n" : "" );

// devolver ambos: ruta y contenido (pipeline_ascii) para que el frontend lo use primero
return [
    'ok' => true,
    'assigned' => $assigned,
    'estado' => $newEstado,
    'log' => $this->logs,
    'pipeline_file' => $pipeline_file,
    'pipeline_ascii' => $pipeline_ascii
];

			
			//return ['ok'=>true,'assigned'=>$assigned,'estado'=>$newEstado,'log'=>$this->logs, 'pipeline_file'=>$this->pipelineFilename];
        } catch (\Exception $e) {
            try { $this->pdo->rollBack(); } catch (\Exception $ignored) {}
            $this->log("Excepción en asignarTurno: " . $e->getMessage());
            $this->logPipeline("EXCEPCIÓN: " . $e->getMessage());
            $this->finalizePipeline();
            return ['ok'=>false,'error'=>$e->getMessage(),'log'=>$this->logs];
        }
    }

    /* ---------------- Helper: normalizar/obtener turno ---------------- */
    private function normalizeTurno($input): array
    {
        if (is_array($input) && !empty($input['id'])) return $input;
        if (is_int($input) || ctype_digit((string)$input)) {
            $stmt = $this->pdo->prepare("SELECT * FROM turnos WHERE id = ?");
            $stmt->execute([(int)$input]);
            $row = $stmt->fetch(PDO::FETCH_ASSOC);
            return $row ?: [];
        }
        return (array)$input;
    }

    /* ---------------- Solicitudes helpers ---------------- */

    private function getSolicitudesAprobadas(int $turnoId): array
    {
        $stmt = $this->pdo->prepare("SELECT usuario_id FROM solicitudes WHERE turno_id = ? AND estado = 'aprobada' ORDER BY fecha_solicitud ASC");
        $stmt->execute([$turnoId]);
        return array_map('intval', $stmt->fetchAll(PDO::FETCH_COLUMN));
    }

    private function getSolicitudesPendientesFull(int $turnoId): array
    {
        $stmt = $this->pdo->prepare("SELECT id, usuario_id, rol FROM solicitudes WHERE turno_id = ? AND estado = 'pendiente' ORDER BY fecha_solicitud ASC");
        $stmt->execute([$turnoId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    private function autoAprobarSolicitud(int $solId)
    {
        $stmt = $this->pdo->prepare("UPDATE solicitudes SET estado = 'aprobada', processed_at = NOW() WHERE id = ?");
        $stmt->execute([$solId]);
        $this->logPipeline("Auto-aprobada solicitud #$solId");
    }

    /* ----------------- Scoring / Fairness / Candidates ----------------- */

    private function getUsuariosDisponiblesParaFranja(string $fecha, string $horaInicio, string $horaFin): array
    {
        $weekday = (int)date('N', strtotime($fecha)); // 1..7
        $sql = "SELECT DISTINCT d.usuario_id FROM disponibilidades d
                WHERE d.dia_semana = ?
                  AND NOT (d.hora_fin <= ? OR d.hora_inicio >= ?)
                ORDER BY d.usuario_id";
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute([$weekday, $horaInicio, $horaFin]);
        return array_map('intval', $stmt->fetchAll(PDO::FETCH_COLUMN));
    }

    private function scoreCandidates(array $candidates, array $turno): array
    {
        $out = [];
        foreach ($candidates as $uid) {
            $s = $this->calcularScoreCandidato((int)$uid, $turno);
            if ($s['valido']) $out[] = $s;
            else $this->logPipeline("Candidato nro {$uid} descartado: {$s['motivo']}");
        }
        usort($out, fn($a,$b)=> $b['total'] <=> $a['total']);
        // aplicar fairness ranking secundario si se solicitó
        if ($this->useFairness) {
            // fair ordering already penaliza por turnos recientes en calcularScoreCandidato
        }
        return $out;
    }

    // calcularScoreCandidato: retorna ['valido'=>bool,'total'=>int,'user_id'=>int,'motivo'=>string]
    private function calcularScoreCandidato(int $userId, array $turno): array
    {
        $total = 0;
        $puntoId = (int)$turno['punto_id'];
        $fecha = $turno['fecha'];
        $horaInicio = substr($turno['hora_inicio'],0,5);
        $horaFin = substr($turno['hora_fin'],0,5);

        // 1) Preferencia de punto
        $pref = $this->getPreferenciaPunto($userId, $puntoId);
        if ($pref === 'no_posible') return ['valido'=>false,'motivo'=>'Punto marcado no_posible','user_id'=>$userId];
        if ($pref === 'preferido') $total += $this->pesoPreferido;
        if ($pref === 'posible') $total += $this->pesoPosible;

        // 2) Idioma
        if ($this->idiomaCompatible($userId, $puntoId)) $total += $this->pesoIdioma;

        // 3) Disponibilidad (requerida)
        if ($this->tieneDisponibilidad($userId, $fecha, $horaInicio, $horaFin)) $total += $this->pesoDisponibilidad;
        else return ['valido'=>false,'motivo'=>'No disponible','user_id'=>$userId];

        // 4) Ausencia
        if ($this->tieneAusencia($userId, $fecha)) return ['valido'=>false,'motivo'=>'Ausente','user_id'=>$userId];

        // 5) Conflicto de turnos
        if ($this->tieneConflictoTurnos($userId, $fecha, $horaInicio, $horaFin)) return ['valido'=>false,'motivo'=>'Conflicto horario','user_id'=>$userId];

        // 6) Fairness penaliza
        $cntRecent = $this->countTurnosRecientes($userId, $this->fairnessWindowWeeks);
        $total -= $cntRecent * $this->penalizacionPorTurnosRecientes;

        // 7) rol solicitado previamente (si existe)
        $solRole = $this->hasRequestRole($userId, (int)$turno['id']);
        if ($solRole) $total += $this->pesoRol;

        return ['valido'=>true,'total'=>$total,'user_id'=>$userId,'motivo'=>'OK'];
    }

    /* ---------------- DB checks / utilitarios ---------------- */

    private function getPreferenciaPunto(int $userId, int $puntoId): ?string
    {
        if (!$this->tableHasColumn('user_point_preferences','nivel')) return null;
        $stmt = $this->pdo->prepare("SELECT nivel FROM user_point_preferences WHERE usuario_id = ? AND punto_id = ? LIMIT 1");
        $stmt->execute([$userId, $puntoId]);
        $v = $stmt->fetchColumn();
        return $v ?: null;
    }

    private function idiomaCompatible(int $userId, int $puntoId): bool
    {
        if ($this->tableHasColumn('puntos','idiomas_id') && $this->tableHasColumn('users','idiomas_id')) {
            $stmt = $this->pdo->prepare("SELECT CASE WHEN u.idiomas_id IS NULL OR p.idiomas_id IS NULL OR u.idiomas_id = p.idiomas_id THEN 1 ELSE 0 END
                                         FROM users u JOIN puntos p ON p.id = ? WHERE u.id = ?");
            $stmt->execute([$puntoId, $userId]);
            return (bool)$stmt->fetchColumn();
        }
        return true;
    }

    private function tieneDisponibilidad(int $userId, string $fecha, string $horaInicio, string $horaFin): bool
    {
        // 1) si no expresó disponibilidades, tratamos como disponible
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM disponibilidades WHERE usuario_id = ?");
        $stmt->execute([$userId]);
        if (!($stmt->fetchColumn() > 0)) return true;

        $weekday = (int)date('N', strtotime($fecha));
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM disponibilidades WHERE usuario_id = ? AND dia_semana = ? AND NOT (hora_fin <= ? OR hora_inicio >= ?)");
        $stmt->execute([$userId, $weekday, $horaInicio, $horaFin]);
        return (int)$stmt->fetchColumn() > 0;
    }

    private function tieneAusencia(int $userId, string $fecha): bool
    {
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM ausencias WHERE usuario_id = ? AND fecha_inicio <= ? AND fecha_fin >= ?");
        $stmt->execute([$userId, $fecha, $fecha]);
        return (int)$stmt->fetchColumn() > 0;
    }

    private function tieneConflictoTurnos(int $userId, string $fecha, string $horaInicio, string $horaFin): bool
    {
        $sql = "SELECT COUNT(*) FROM turno_participantes tp JOIN turnos t ON tp.turno_id = t.id
                WHERE tp.usuario_id = ? AND t.fecha = ? AND NOT (t.hora_fin <= ? OR t.hora_inicio >= ?) AND t.estado IN ('asignado','planificado','pendiente')";
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute([$userId, $fecha, $horaInicio, $horaFin]);
        return (int)$stmt->fetchColumn() > 0;
    }

    private function countTurnosRecientes(int $userId, int $weeks = 4): int
    {
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM turno_participantes tp JOIN turnos t ON tp.turno_id = t.id WHERE tp.usuario_id = ? AND t.fecha >= DATE_SUB(CURDATE(), INTERVAL ? WEEK)");
        $stmt->execute([$userId, $weeks]);
        return (int)$stmt->fetchColumn();
    }

    private function hasRequestRole(int $userId, int $turnoId): bool
    {
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM solicitudes WHERE usuario_id = ? AND turno_id = ?");
        $stmt->execute([$userId, $turnoId]);
        return ((int)$stmt->fetchColumn()) > 0;
    }

    /* ---------------- DB insert participante (defensivo) ---------------- */
    private function isUserInList(int $userId, array $rows): bool
    {
        foreach ($rows as $r) if ((int)($r['usuario_id'] ?? $r) === (int)$userId) return true;
        return false;
    }

    private function insertParticipante(int $turnoId, int $userId, string $rol): bool
    {
        if (!$userId) { $this->logPipeline("insertParticipante: usuario_id inválido"); return false; }
        // evita duplicados
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM turno_participantes WHERE turno_id = ? AND usuario_id = ?");
        $stmt->execute([$turnoId, $userId]);
        if ((int)$stmt->fetchColumn() > 0) {
            $this->logPipeline("Usuario $userId ya estaba asignado al turno $turnoId (skip)");
            return false;
        }
        try {
            $ins = $this->pdo->prepare("INSERT INTO turno_participantes (turno_id, usuario_id, rol, asignado_por, asignado_en, asistio) VALUES (?, ?, ?, ?, NOW(), 0)");
            $ok = $ins->execute([$turnoId, $userId, $rol, null]);
            if (!$ok) {
                $this->logPipeline("Error SQL insertParticipante: " . json_encode($ins->errorInfo()));
                return false;
            }
            return true;
        } catch (\Exception $e) {
            $this->logPipeline("Excepción insertParticipante: " . $e->getMessage());
            return false;
        }
    }

    /* ---------------- Notificaciones ---------------- */

    // Inserta notificación si no existe similar en ventana corta
    public function crearNotificacionSiNoExiste(int $turno_id, int $usuario_id, string $tipo, string $mensaje, $payload = null): bool
    {
        try {
            $check = $this->pdo->prepare("SELECT COUNT(*) FROM notificaciones WHERE turno_id=? AND usuario_id=? AND tipo=? AND creado_en >= DATE_SUB(NOW(), INTERVAL 1 HOUR)");
            $check->execute([$turno_id, $usuario_id, $tipo]);
            if ($check->fetchColumn() > 0) return false;

            $ins = $this->pdo->prepare("INSERT INTO notificaciones (turno_id, usuario_id, tipo, mensaje, payload, canal, estado, creado_en) VALUES (?, ?, ?, ?, ?, 'ambos', 'pending', NOW())");
            $ins->execute([$turno_id, $usuario_id, $tipo, $mensaje, $payload ? json_encode($payload) : null]);
            $this->logPipeline("Notificacion creada para usuario $usuario_id tipo $tipo (turno $turno_id)");
            return true;
        } catch (\Exception $e) {
            $this->logPipeline("Error crearNotificacionSiNoExiste: " . $e->getMessage());
            return false;
        }
    }

    // Notifica a todos los participantes (puede duplicar si ya existían; usar crearNotificacionSiNoExiste si quieres evitar duplicados)
    private function crearNotificacionesParaTurno(int $turnoId)
    {
        try {
            $stmt = $this->pdo->prepare("SELECT usuario_id FROM turno_participantes WHERE turno_id = ?");
            $stmt->execute([$turnoId]);
            $users = $stmt->fetchAll(PDO::FETCH_COLUMN);
            foreach ($users as $u) {
                $this->crearNotificacionSiNoExiste($turnoId, (int)$u, 'cubierto', "Has sido asignado al turno #$turnoId", ['turno'=>$turnoId]);
            }
            $this->logPipeline("crearNotificacionesParaTurno completado para turno $turnoId");
        } catch (\Exception $e) {
            $this->logPipeline("Error crearNotificacionesParaTurno: " . $e->getMessage());
        }
    }

    /* -------------- Persistir logs en bot_logs -------------- */
    private function persistBotLog(int $turnoId, array $logs)
    {
        if (!$this->tableHasColumn('bot_logs','mensaje')) return;
        try {
            $stmt = $this->pdo->prepare("INSERT INTO bot_logs (turno_id, mensaje) VALUES (?, ?)");
            foreach ($logs as $l) {
                $stmt->execute([$turnoId, $l]);
            }
            $this->logPipeline("Agregados " . count($logs) . " logs en bot_logs");
        } catch (\Exception $e) {
            // no romper el flujo
            $this->logPipeline("Error persistBotLog: " . $e->getMessage());
        }
    }

    /* ---------------- Utility / tabla existencia ---------------- */
    private function tableHasColumn(string $table, string $column): bool
    {
        $sql = "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?";
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute([$table, $column]);
        return (int)$stmt->fetchColumn() > 0;
    }

    /* ---------------- Logging / pipeline ASCII ---------------- */
    private function log(string $txt) { $this->logs[] = date('c') . ' ' . $txt; }
    private function logPipeline(string $line)
    {
        $ts = date('c');
        $this->pipelineSteps[] = "[$ts] $line";
        $this->log($line);
    }

    // Al finalizar, escribe pipeline en archivo /tmp y resume
      // Al finalizar, escribe pipeline en archivo /tmp y resume
    private function finalizePipeline()
    {
        try {
            if (!empty($this->pipelineSteps)) {
                // preparar contenido final (incluye todo lo que hay hasta ahora)
                $content = implode("\n", $this->pipelineSteps) . "\n";
                // escribir contenido completo por primera vez
                file_put_contents($this->pipelineFilename, $content);

                // añadir una línea final en memoria y en archivo indicando la ruta (timestamp ya incluido en filename)
                $finalLine = "[" . date('c') . "] Pipeline escrito en {$this->pipelineFilename}";
                // agregar a arrays
                $this->pipelineSteps[] = $finalLine;
                $this->logs[] = $finalLine;
                // añadir también al archivo (append) para que el archivo contenga la línea final
                file_put_contents($this->pipelineFilename, $finalLine . "\n", FILE_APPEND);

                // almacenar ASCII en memoria para devolverlo en la respuesta
                $this->pipelineAscii = implode("\n", $this->pipelineSteps) . "\n";

                $this->logPipeline("Pipeline escrito en {$this->pipelineFilename}"); // opcional, quedará en logs
            } else {
                // si no hay steps, aseguramos que pipelineAscii sea string vacío
                $this->pipelineAscii = "";
            }
        } catch (\Exception $e) {
            $this->logPipeline("Error escribiendo pipeline en archivo: " . $e->getMessage());
            // intentar dejar pipelineAscii con lo que hay
            $this->pipelineAscii = implode("\n", $this->pipelineSteps) . "\n";
        }
    }


    /* ---------------- Métodos auxiliares reutilizables (posiblemente viejos) ---------------- */

    private function getSolicitudesAprobadasByRole(int $turnoId, string $rol = 'publicador'): array
    {
        $stmt = $this->pdo->prepare("SELECT usuario_id FROM solicitudes WHERE turno_id = ? AND estado = 'aprobada' AND rol = ? ORDER BY fecha_solicitud ASC");
        $stmt->execute([$turnoId, $rol]);
        return array_map('intval', $stmt->fetchAll(PDO::FETCH_COLUMN));
    }

    private function isUserAssignedInTurn(int $turnoId, int $userId): bool
    {
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM turno_participantes WHERE turno_id = ? AND usuario_id = ?");
        $stmt->execute([$turnoId, $userId]);
        return (int)$stmt->fetchColumn() > 0;
    }

    // Para compatibilidad: crearNotificacion simple (no usado fuera)
    private function crearNotificacion(int $turnoId, $userId, string $tipo, string $mensaje)
    {
        try {
            $stmt = $this->pdo->prepare("INSERT INTO notificaciones (turno_id, usuario_id, tipo, mensaje, canal, estado, creado_en) VALUES (?, ?, ?, ?, 'ambos', 'pending', NOW())");
            $stmt->execute([$turnoId, $userId, $tipo, $mensaje]);
        } catch (\Exception $e) {
            $this->logPipeline("Error crearNotificacion: " . $e->getMessage());
        }
    }
}
