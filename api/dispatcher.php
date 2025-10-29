<?php
// api/dispatcher.php
namespace Api;

require_once __DIR__ . '/../includes/exp_config.php'; // $pdo
require_once __DIR__ . '/../services/BotAsignador.php';

class Dispatcher
{
    public static function dispatch(string $evento, $turno)
    {
        global $pdo;
        $bot = new \BotAsignador($pdo);

        switch ($evento) {
            case 'turno.planificado':
                // Asignación automática
                $res = $bot->asignarTurno($turno);
                return $res;

            case 'turno.cancelado':
                // Crear notificación de cancelación
                $turnoId = (int)($turno['id'] ?? $turno->id);
                $stmt = $pdo->prepare("INSERT INTO notificaciones (turno_id, usuario_id, tipo, mensaje) VALUES (?, NULL, 'cancelado', ?)");
                $stmt->execute([$turnoId, "Turno #$turnoId cancelado"]);
                return ['ok'=>true];

            case 'turno.vacante':
                // Notifica a usuarios disponibles
                $turnoId = (int)($turno['id'] ?? $turno->id);
                // busca usuarios con disponibilidad en esa franja
                $stmt = $pdo->prepare("SELECT d.usuario_id FROM disponibilidades d
                    JOIN turnos t ON t.punto_id = ? -- optional
                    WHERE d.dia_semana = ? AND NOT (d.hora_fin <= ? OR d.hora_inicio >= ?)");
                // Could be improved: pass fecha -> weekday
                $fecha = $turno['fecha'] ?? null;
                $weekday = $fecha ? (int)date('N', strtotime($fecha)) : null;
                $horaInicio = $turno['hora_inicio'] ?? null;
                $horaFin = $turno['hora_fin'] ?? null;
                if ($weekday) {
                    $stmt->execute([$turno['punto_id'] ?? 0, $weekday, $horaInicio, $horaFin]);
                    $uids = $stmt->fetchAll(PDO::FETCH_COLUMN);
                    foreach ($uids as $u) {
                        $pdo->prepare("INSERT INTO notificaciones (turno_id, usuario_id, tipo, mensaje) VALUES (?, ?, 'vacante', ?)")
                            ->execute([$turnoId, $u, "Vacante disponible para turno #$turnoId"]);
                    }
                }
                return ['ok'=>true];
        }
        return ['error'=>'Evento desconocido'];
    }
}
