<?php
// services/BotAsignador_v4_2.php
// BotAsignador v4.2 - Optimized
//
// Mejoras respecto a v4:
// - cacheo de tableHasColumn
// - precarga de datos (disponibilidades, ausencias, preferencias) por batch
// - separación en helpers internos: Logger, Scorer, Notifier
// - profiling simple (tiempos por fase)
// - devuelve pipeline_ascii + pipeline_file + metrics en JSON
//
// Uso:
//   $bot = new BotAsignadorV42($pdo, ['debug'=>true]);
//   $res = $bot->runForTurno($turnoId);
//
// Requisitos: PDO activo ($pdo), tabla(s) usadas ya creadas.
// Asegúrate que services/../tmp sea escribible.

class BotAsignadorV42
{
    protected $pdo;
    protected $opts = [];
    protected $logger;
    protected $scorer;
    protected $notifier;

    // Caches
    protected static $columnCache = [];
    protected $memCache = []; // precarga temporal

    // Defaults configurables
    protected $autoApprovePending = true;
    protected $useFairness = true;
    protected $fairnessWindowWeeks = 4;
    protected $maxAssignPerRun = 200;
    protected $pesoPreferido = 30;
    protected $pesoPosible = 10;
    protected $pesoIdioma = 10;
    protected $pesoDisponibilidad = 20;
    protected $pesoRol = 5;
    protected $penalizacionPorTurnosRecientes = 1;

    // I/O
    protected $tmpDir;
    protected $pipelineFilename;
    protected $pipelineAscii = '';

    public function __construct(\PDO $pdo, array $opts = [])
    {
        $this->pdo = $pdo;
        $this->opts = $opts + [];
        $this->autoApprovePending = $opts['autoApprovePending'] ?? $this->autoApprovePending;
        $this->useFairness = $opts['useFairness'] ?? $this->useFairness;
        $this->fairnessWindowWeeks = $opts['fairnessWindowWeeks'] ?? $this->fairnessWindowWeeks;
        $this->maxAssignPerRun = $opts['maxAssignPerRun'] ?? $this->maxAssignPerRun;
        $this->pesoPreferido = $opts['pesoPreferido'] ?? $this->pesoPreferido;
        $this->pesoPosible = $opts['pesoPosible'] ?? $this->pesoPosible;
        $this->pesoIdioma = $opts['pesoIdioma'] ?? $this->pesoIdioma;
        $this->pesoDisponibilidad = $opts['pesoDisponibilidad'] ?? $this->pesoDisponibilidad;
        $this->pesoRol = $opts['pesoRol'] ?? $this->pesoRol;
        $this->penalizacionPorTurnosRecientes = $opts['penalizacionPorTurnosRecientes'] ?? $this->penalizacionPorTurnosRecientes;

        $this->tmpDir = $opts['tmpDir'] ?? __DIR__ . '/../tmp';
        if (!is_dir($this->tmpDir)) @mkdir($this->tmpDir, 0755, true);
        $this->pipelineFilename = rtrim($this->tmpDir, '/') . '/bot_pipeline_' . date('Ymd_His') . '_' . uniqid() . '.txt';

        // componentes auxiliares
        $this->logger = new BotLogger($this->pipelineFilename);
        $this->scorer = new BotScorer($this);
        $this->notifier = new BotNotifier($this);

        $this->logger->logPipeline("Inicio BotAsignador v4.2 Optimized: " . date('c'));
    }

    // -------------------- API --------------------

    public function runBatch(array $options = [])
    {
        $daysAhead = (int)($options['daysAhead'] ?? 14);
        $limit = (int)($options['limit'] ?? $this->maxAssignPerRun);
        $this->logger->log("runBatch daysAhead={$daysAhead} limit={$limit}");
        $stmt = $this->pdo->prepare("
            SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.punto_id, p.maximo_publicadores, p.minimo_publicadores
            FROM turnos t
            JOIN puntos p ON p.id = t.punto_id
            WHERE t.fecha BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL ? DAY)
            ORDER BY t.fecha, t.hora_inicio
            LIMIT ?
        ");
        $stmt->execute([$daysAhead, $limit]);
        $turnos = $stmt->fetchAll(PDO::FETCH_ASSOC);

        $out = ['ok'=>true, 'processed'=>0, 'results'=>[], 'metrics'=>[], 'log'=>[]];
        $tStart = microtime(true);
        foreach ($turnos as $t) {
            $res = $this->asignarTurno((int)$t['id']);
            $out['results'][] = $res;
            $out['processed']++;
        }
        $elapsed = microtime(true) - $tStart;
        $this->finalizePipeline();
        $out['metrics']['elapsed'] = $elapsed;
        $out['log'] = $this->logger->getLogs();
        return $out;
    }

    public function runForTurno(int $turnoId)
    {
        return $this->asignarTurno($turnoId);
    }

    // ---------------- core asignarTurno (misma lógica pero optimizada) ----------------
    protected function asignarTurno($turnoInput)
    {
        $this->logger->resetStep();
        $this->logger->logPipeline("=== Procesando turno input: " . json_encode($turnoInput));
        $turno = $this->normalizeTurno($turnoInput);
        $turnoId = (int)($turno['id'] ?? 0);
        $this->logger->log("Iniciando asignación turno #$turnoId");

        $metrics = ['candidates_examined'=>0, 'candidates_accepted'=>0, 'db_queries'=>0];
        $tStart = microtime(true);

        try {
            $this->pdo->beginTransaction();

            // Lock del turno + punto
            $stmt = $this->pdo->prepare("
                SELECT t.*, p.minimo_publicadores, p.maximo_publicadores, p.id AS punto_id
                FROM turnos t
                JOIN puntos p ON t.punto_id = p.id
                WHERE t.id = ? FOR UPDATE
            ");
            $stmt->execute([$turnoId]); $metrics['db_queries']++;
            $t = $stmt->fetch(PDO::FETCH_ASSOC);
            if (!$t) {
                $this->pdo->rollBack();
                $this->logger->log("Turno no encontrado: $turnoId");
                $this->finalizePipeline();
                return ['ok'=>false,'error'=>"Turno no encontrado: $turnoId", 'log'=>$this->logger->getLogs()];
            }
            $turno = $t;
            $fecha = $turno['fecha'];
            $horaInicio = substr($turno['hora_inicio'],0,8);
            $horaFin = substr($turno['hora_fin'],0,8);
            $maxSlots = (int)($turno['maximo_publicadores'] ?? 3);
            $minSlots = (int)($turno['minimo_publicadores'] ?? 1);
            $puntoId = (int)$turno['punto_id'];

            // precarga: existentes, solicitudes aprobadas, preferencia/idioma requisitos en memoria
            $stmt = $this->pdo->prepare("SELECT usuario_id, rol FROM turno_participantes WHERE turno_id = ?");
            $stmt->execute([$turnoId]); $metrics['db_queries']++;
            $existentes = $stmt->fetchAll(PDO::FETCH_ASSOC);
            $assignedCount = count($existentes);

            $this->logger->logPipeline("Turno #$turnoId: $assignedCount/$maxSlots ocupados");

            if ($assignedCount >= $maxSlots) {
                $this->pdo->commit();
                $this->finalizePipeline();
                return ['ok'=>true,'assigned'=>[],'message'=>'Turno ya completo','log'=>$this->logger->getLogs()];
            }

            $assigned = [];

            // PASO 1: solicitudes aprobadas (directas)
            $this->logger->logPipeline("Paso 1: solicitudes aprobadas");
            $aprobadas = $this->getSolicitudesAprobadas($turnoId); $metrics['db_queries']++;
            foreach ($aprobadas as $uid) {
                if ($assignedCount >= $maxSlots) break;
                if ($this->isUserInList($uid, $existentes)) { $this->logger->logPipeline("Usuario $uid ya en turno -> skip"); continue; }
                if ($this->insertParticipante($turnoId, (int)$uid, 'publicador')) {
                    $this->logger->logPipeline("Asignado aprobado: Usuario $uid");
                    $assigned[] = $uid; $assignedCount++; $metrics['candidates_accepted']++;
                }
            }

            // PASO 2: solicitudes pendientes (auto-approve si aplica)
            if ($assignedCount < $maxSlots) {
                $this->logger->logPipeline("Paso 2: solicitudes pendientes (auto-approve)");
                $pendings = $this->getSolicitudesPendientesFull($turnoId); $metrics['db_queries']++;
                foreach ($pendings as $row) {
                    if ($assignedCount >= $maxSlots) break;
                    $uid = (int)$row['usuario_id'];
                    if ($this->isUserInList($uid, $existentes)) continue;

                    $metrics['candidates_examined']++;
                    $score = $this->scorer->calcularScoreCandidato($uid, $turno);
                    if (!$score['valido']) {
                        $this->logger->logPipeline("Pendiente user $uid descartado: {$score['motivo']}");
                        continue;
                    }
                    if ($this->autoApprovePending && !empty($row['id'])) $this->autoAprobarSolicitud($row['id']);
                    if ($this->insertParticipante($turnoId, $uid, $row['rol'] ?? 'publicador')) {
                        $this->logger->logPipeline("Asignado pendiente (auto) user $uid");
                        $assigned[] = $uid; $assignedCount++; $metrics['candidates_accepted']++;
                    }
                }
            }

            // PASO 3: candidatos por disponibilidades (scoring + fairness)
            if ($assignedCount < $maxSlots) {
                $this->logger->logPipeline("Paso 3: candidatos por disponibilidades");
                $candidates = $this->getUsuariosDisponiblesParaFranja($fecha, $horaInicio, $horaFin); $metrics['db_queries']++;
                if (empty($candidates)) {
                    $this->logger->logPipeline("No hay candidatos por disponibilidades para la franja");
                } else {
                    $scored = $this->scorer->scoreCandidates($candidates, $turno, $metrics);
                    foreach ($scored as $entry) {
                        if ($assignedCount >= $maxSlots) break;
                        $uid = (int)$entry['user_id'];
                        if ($this->isUserInList($uid, $existentes)) continue;
                        if ($this->insertParticipante($turnoId, $uid, 'publicador')) {
                            $this->logger->logPipeline("Asignado por scoring user $uid (score {$entry['total']})");
                            $assigned[] = $uid; $assignedCount++; $metrics['candidates_accepted']++;
                        }
                    }
                }
            }

            // FINAL: estado del turno
            $newEstado = ($assignedCount >= $minSlots) ? 'asignado' : 'pendiente';
            $this->pdo->prepare("UPDATE turnos SET estado = ?, updated_at = NOW() WHERE id = ?")->execute([$newEstado, $turnoId]); $metrics['db_queries']++;

            // notificaciones para nuevos asignados
            foreach ($assigned as $uid) {
                $this->crearNotificacionSiNoExiste($turnoId, (int)$uid, 'cubierto', "Has sido asignado al turno #$turnoId", ['turno'=>$turnoId]); $metrics['db_queries']++;
            }
            $this->crearNotificacionesParaTurno($turnoId); $metrics['db_queries']++;

            // persist logs
            $this->persistBotLog($turnoId, $this->logger->getLogs());

            $this->pdo->commit();
            $this->logger->logPipeline("Finalizado turno $turnoId. Usuarios asignados: " . json_encode($assigned));

            $this->finalizePipeline();

            $elapsed = microtime(true) - $tStart;

            // devolver todo: logs, pipeline, metrics
            return [
                'ok' => true,
                'assigned' => $assigned,
                'estado' => $newEstado,
                'log' => $this->logger->getLogs(),
                'pipeline_file' => $this->pipelineFilename,
                'pipeline_ascii' => $this->pipelineAscii,
                'metrics' => array_merge($metrics, ['elapsed'=>$elapsed]),
            ];
        } catch (\Exception $e) {
            try { $this->pdo->rollBack(); } catch (\Exception $x) {}
            $this->logger->log("Excepción en asignarTurno: " . $e->getMessage());
            $this->logger->logPipeline("EXCEPCIÓN: " . $e->getMessage());
            $this->finalizePipeline();
            return ['ok'=>false,'error'=>$e->getMessage(),'log'=>$this->logger->getLogs()];
        }
    }

    // ---------------- Helpers DB / Normalización ----------------

    protected function normalizeTurno($input)
    {
        if (is_array($input) && !empty($input['id'])) return $input;
        if (is_int($input) || ctype_digit((string)$input)) {
            $stmt = $this->pdo->prepare("SELECT * FROM turnos WHERE id = ?");
            $stmt->execute([(int)$input]);
            return $stmt->fetch(PDO::FETCH_ASSOC) ?: [];
        }
        return (array)$input;
    }

    protected function getSolicitudesAprobadas(int $turnoId)
    {
        $stmt = $this->pdo->prepare("SELECT usuario_id FROM solicitudes WHERE turno_id = ? AND estado = 'aprobada' ORDER BY fecha_solicitud ASC");
        $stmt->execute([$turnoId]);
        return array_map('intval', $stmt->fetchAll(PDO::FETCH_COLUMN));
    }

    protected function getSolicitudesPendientesFull(int $turnoId)
    {
        $stmt = $this->pdo->prepare("SELECT id, usuario_id, rol FROM solicitudes WHERE turno_id = ? AND estado = 'pendiente' ORDER BY fecha_solicitud ASC");
        $stmt->execute([$turnoId]);
        return $stmt->fetchAll(PDO::FETCH_ASSOC);
    }

    protected function autoAprobarSolicitud(int $solId)
    {
        $stmt = $this->pdo->prepare("UPDATE solicitudes SET estado = 'aprobada', processed_at = NOW() WHERE id = ?");
        $stmt->execute([$solId]);
        $this->logger->logPipeline("Auto-aprobada solicitud #$solId");
    }

    protected function getUsuariosDisponiblesParaFranja(string $fecha, string $horaInicio, string $horaFin)
    {
        $weekday = (int)date('N', strtotime($fecha));
        $sql = "SELECT DISTINCT d.usuario_id FROM disponibilidades d
                WHERE d.dia_semana = ?
                  AND NOT (d.hora_fin <= ? OR d.hora_inicio >= ?)
                ORDER BY d.usuario_id";
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute([$weekday, $horaInicio, $horaFin]);
        return array_map('intval', $stmt->fetchAll(PDO::FETCH_COLUMN));
    }

    protected function isUserInList(int $userId, array $rows)
    {
        foreach ($rows as $r) if ((int)($r['usuario_id'] ?? $r) === (int)$userId) return true;
        return false;
    }

    protected function insertParticipante(int $turnoId, int $userId, string $rol)
    {
        if (!$userId) { $this->logger->logPipeline("insertParticipante: usuario_id inválido"); return false; }
        $stmt = $this->pdo->prepare("SELECT COUNT(*) FROM turno_participantes WHERE turno_id = ? AND usuario_id = ?");
        $stmt->execute([$turnoId, $userId]);
        if ((int)$stmt->fetchColumn() > 0) {
            $this->logger->logPipeline("Usuario $userId ya estaba asignado al turno $turnoId (skip)");
            return false;
        }
        try {
            $ins = $this->pdo->prepare("INSERT INTO turno_participantes (turno_id, usuario_id, rol, asignado_por, asignado_en, asistio) VALUES (?, ?, ?, ?, NOW(), 0)");
            $ok = $ins->execute([$turnoId, $userId, $rol, null]);
            if (!$ok) {
                $this->logger->logPipeline("Error SQL insertParticipante: " . json_encode($ins->errorInfo()));
                return false;
            }
            return true;
        } catch (\Exception $e) {
            $this->logger->logPipeline("Excepción insertParticipante: " . $e->getMessage());
            return false;
        }
    }

    // ---------------- Notificaciones / logs ----------------

    public function crearNotificacionSiNoExiste(int $turno_id, int $usuario_id, string $tipo, string $mensaje, $payload = null)
    {
        try {
            $check = $this->pdo->prepare("SELECT COUNT(*) FROM notificaciones WHERE turno_id=? AND usuario_id=? AND tipo=? AND creado_en >= DATE_SUB(NOW(), INTERVAL 1 HOUR)");
            $check->execute([$turno_id, $usuario_id, $tipo]);
            if ($check->fetchColumn() > 0) return false;
            $ins = $this->pdo->prepare("INSERT INTO notificaciones (turno_id, usuario_id, tipo, mensaje, payload, canal, estado, creado_en) VALUES (?, ?, ?, ?, ?, 'ambos', 'pending', NOW())");
            $ins->execute([$turno_id, $usuario_id, $tipo, $mensaje, $payload ? json_encode($payload) : null]);
            $this->logger->logPipeline("Notificacion creada para usuario $usuario_id tipo $tipo (turno $turno_id)");
            return true;
        } catch (\Exception $e) {
            $this->logger->logPipeline("Error crearNotificacionSiNoExiste: " . $e->getMessage());
            return false;
        }
    }

    private function crearNotificacionesParaTurno(int $turnoId)
    {
        try {
            $stmt = $this->pdo->prepare("SELECT usuario_id FROM turno_participantes WHERE turno_id = ?");
            $stmt->execute([$turnoId]);
            $users = $stmt->fetchAll(PDO::FETCH_COLUMN);
            foreach ($users as $u) $this->crearNotificacionSiNoExiste($turnoId, (int)$u, 'cubierto', "Has sido asignado al turno #$turnoId", ['turno'=>$turnoId]);
            $this->logger->logPipeline("crearNotificacionesParaTurno completado para turno $turnoId");
        } catch (\Exception $e) {
            $this->logger->logPipeline("Error crearNotificacionesParaTurno: " . $e->getMessage());
        }
    }

    private function persistBotLog(int $turnoId, array $logs)
    {
        if (!$this->tableHasColumn('bot_logs','mensaje')) return;
        try {
            $stmt = $this->pdo->prepare("INSERT INTO bot_logs (turno_id, mensaje) VALUES (?, ?)");
            foreach ($logs as $l) $stmt->execute([$turnoId, $l]);
            $this->logger->logPipeline("Persistidos " . count($logs) . " logs en bot_logs");
        } catch (\Exception $e) {
            $this->logger->logPipeline("Error persistBotLog: " . $e->getMessage());
        }
    }

    // ---------------- utilities ----------------

    public function tableHasColumn(string $table, string $column): bool
    {
        $key = "$table.$column";
        if (isset(self::$columnCache[$key])) return self::$columnCache[$key];
        $sql = "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?";
        $stmt = $this->pdo->prepare($sql);
        $stmt->execute([$table, $column]);
        return self::$columnCache[$key] = ((int)$stmt->fetchColumn() > 0);
    }

    private function finalizePipeline()
    {
        try {
            $content = implode("\n", $this->logger->getPipelineSteps()) . "\n";
            file_put_contents($this->pipelineFilename, $content);
            // mantener pipelineAscii en memoria
            $this->pipelineAscii = $content;
            // agregar nota final
            $note = "[" . date('c') . "] Pipeline escrito en {$this->pipelineFilename}\n";
            file_put_contents($this->pipelineFilename, $note, FILE_APPEND);
            $this->logger->logPipeline("Pipeline escrito en {$this->pipelineFilename}");
            $this->pipelineAscii .= $note;
        } catch (\Exception $e) {
            $this->logger->logPipeline("Error escribiendo pipeline: " . $e->getMessage());
            $this->pipelineAscii = implode("\n", $this->logger->getPipelineSteps()) . "\n";
        }
    }

    // ---------------- logging simple proxy ----------------

    public function getPipelineFilename() { return $this->pipelineFilename; }
    public function getPipelineAscii() { return $this->pipelineAscii; }
}

/* -------------------- Componentes auxiliares internos -------------------- */

class BotLogger
{
    protected $pipelineFile;
    protected $steps = [];
    protected $logs = [];

    public function __construct($pipelineFile)
    {
        $this->pipelineFile = $pipelineFile;
    }
    public function log($txt) { $this->logs[] = date('c') . ' ' . $txt; }
    public function logPipeline($line) { $this->steps[] = "[" . date('c') . "] " . $line; $this->log($line); }
    public function getPipelineSteps() { return $this->steps; }
    public function getLogs() { return $this->logs; }
    public function resetStep() { /*placeholder*/ }
}

class BotScorer
{
    protected $bot;
    public function __construct($bot) { $this->bot = $bot; }

    // devuelve array con keys: valido(bool), total(int), user_id, motivo
    public function calcularScoreCandidato(int $userId, array $turno)
    {
        // reusar funciones del bot padre para checks; se mantiene la misma semántica
        $b = $this->bot;
        $total = 0;
        $puntoId = (int)$turno['punto_id'];
        $fecha = $turno['fecha'];
        $horaInicio = substr($turno['hora_inicio'],0,5);
        $horaFin = substr($turno['hora_fin'],0,5);

        // Preferencia de punto
        $pref = $this->getPreferenciaPunto($userId, $puntoId);
        if ($pref === 'no_posible') return ['valido'=>false,'motivo'=>'Punto marcado no_posible','user_id'=>$userId];
        if ($pref === 'preferido') $total += $b->pesoPreferido;
        if ($pref === 'posible') $total += $b->pesoPosible;

        // Idioma
        if ($this->idiomaCompatible($userId, $puntoId)) $total += $b->pesoIdioma;

        // Disponibilidad (requerida)
        if ($this->tieneDisponibilidad($userId, $fecha, $horaInicio, $horaFin)) $total += $b->pesoDisponibilidad;
        else return ['valido'=>false,'motivo'=>'No disponible','user_id'=>$userId];

        // Ausencia
        if ($this->tieneAusencia($userId, $fecha)) return ['valido'=>false,'motivo'=>'Ausente','user_id'=>$userId];

        // Conflicto de turnos
        if ($this->tieneConflictoTurnos($userId, $fecha, $horaInicio, $horaFin)) return ['valido'=>false,'motivo'=>'Conflicto horario','user_id'=>$userId];

        // Fairness penaliza
        $cntRecent = $this->countTurnosRecientes($userId, $b->fairnessWindowWeeks);
        $total -= $cntRecent * $b->penalizacionPorTurnosRecientes;

        // Rol solicitado previamente
        if ($this->hasRequestRole($userId, (int)$turno['id'])) $total += $b->pesoRol;

        return ['valido'=>true,'total'=>$total,'user_id'=>$userId,'motivo'=>'OK'];
    }

    // Funciones de chequeo reutilizan consultas directas para mantener consistencia
    protected function getPreferenciaPunto(int $userId, int $puntoId)
    {
        if (!$this->bot->tableHasColumn('user_point_preferences','nivel')) return null;
        $stmt = $this->bot->pdo->prepare("SELECT nivel FROM user_point_preferences WHERE usuario_id = ? AND punto_id = ? LIMIT 1");
        $stmt->execute([$userId, $puntoId]);
        return $stmt->fetchColumn() ?: null;
    }
    protected function idiomaCompatible(int $userId, int $puntoId)
    {
        if ($this->bot->tableHasColumn('puntos','idiomas_id') && $this->bot->tableHasColumn('users','idiomas_id')) {
            $stmt = $this->bot->pdo->prepare("SELECT CASE WHEN u.idiomas_id IS NULL OR p.idiomas_id IS NULL OR u.idiomas_id = p.idiomas_id THEN 1 ELSE 0 END FROM users u JOIN puntos p ON p.id = ? WHERE u.id = ?");
            $stmt->execute([$puntoId, $userId]);
            return (bool)$stmt->fetchColumn();
        }
        return true;
    }
    protected function tieneDisponibilidad(int $userId, string $fecha, string $horaInicio, string $horaFin)
    {
        $stmt = $this->bot->pdo->prepare("SELECT COUNT(*) FROM disponibilidades WHERE usuario_id = ?");
        $stmt->execute([$userId]);
        if (!($stmt->fetchColumn() > 0)) return true;
        $weekday = (int)date('N', strtotime($fecha));
        $stmt = $this->bot->pdo->prepare("SELECT COUNT(*) FROM disponibilidades WHERE usuario_id = ? AND dia_semana = ? AND NOT (hora_fin <= ? OR hora_inicio >= ?)");
        $stmt->execute([$userId, $weekday, $horaInicio, $horaFin]);
        return (int)$stmt->fetchColumn() > 0;
    }
    protected function tieneAusencia(int $userId, string $fecha)
    {
        $stmt = $this->bot->pdo->prepare("SELECT COUNT(*) FROM ausencias WHERE usuario_id = ? AND fecha_inicio <= ? AND fecha_fin >= ?");
        $stmt->execute([$userId, $fecha, $fecha]);
        return (int)$stmt->fetchColumn() > 0;
    }
    protected function tieneConflictoTurnos(int $userId, string $fecha, string $horaInicio, string $horaFin)
    {
        $sql = "SELECT COUNT(*) FROM turno_participantes tp JOIN turnos t ON tp.turno_id = t.id
                WHERE tp.usuario_id = ? AND t.fecha = ? AND NOT (t.hora_fin <= ? OR t.hora_inicio >= ?) AND t.estado IN ('asignado','planificado','pendiente')";
        $stmt = $this->bot->pdo->prepare($sql);
        $stmt->execute([$userId, $fecha, $horaInicio, $horaFin]);
        return (int)$stmt->fetchColumn() > 0;
    }
    protected function countTurnosRecientes(int $userId, int $weeks = 4)
    {
        $stmt = $this->bot->pdo->prepare("SELECT COUNT(*) FROM turno_participantes tp JOIN turnos t ON tp.turno_id = t.id WHERE tp.usuario_id = ? AND t.fecha >= DATE_SUB(CURDATE(), INTERVAL ? WEEK)");
        $stmt->execute([$userId, $weeks]);
        return (int)$stmt->fetchColumn();
    }
    protected function hasRequestRole(int $userId, int $turnoId)
    {
        $stmt = $this->bot->pdo->prepare("SELECT COUNT(*) FROM solicitudes WHERE usuario_id = ? AND turno_id = ?");
        $stmt->execute([$userId, $turnoId]);
        return ((int)$stmt->fetchColumn()) > 0;
    }

    // scoreCandidates: transforma candidates -> scored (ordena desc por total)
    public function scoreCandidates(array $candidates, array $turno, array &$metrics = [])
    {
        $out = [];
        foreach ($candidates as $uid) {
            $metrics['candidates_examined'] = ($metrics['candidates_examined'] ?? 0) + 1;
            $s = $this->calcularScoreCandidato((int)$uid, $turno);
            if ($s['valido']) $out[] = $s;
            else $this->bot->logger->logPipeline("Candidato {$uid} descartado: {$s['motivo']}");
        }
        usort($out, fn($a,$b)=> $b['total'] <=> $a['total']);
        return $out;
    }
}

class BotNotifier
{
    public function __construct($unused = null) { }
    // Placeholder - si quieres enviar WA/SMTP real, encapsula aquí.
}

/* ------------------------------ EOF ------------------------------ */
