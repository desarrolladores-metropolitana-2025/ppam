<?php
require_once __DIR__ . '/config.php';

/**
 * BotAsignador
 * Lógica para asignar automáticamente publicadores/capitanes a un turno.
 */
class BotAsignador
{
    /**
     * Cuando se crea un turno, intentar asignar participantes automáticamente.
     */
    public function onTurnoCreado(array $turno)
    {
        global $pdo;

        // obtener detalles del turno
        $stmt = $pdo->prepare("SELECT * FROM turnos WHERE id=?");
        $stmt->execute([$turno['id']]);
        $t = $stmt->fetch();

        if (!$t) return;

        // buscar solicitudes pendientes compatibles
        $sql = "SELECT s.*, u.nombre, u.rol_predeterminado
                FROM solicitudes s
                JOIN users u ON u.id = s.usuario_id
                WHERE s.turno_id = ? AND s.estado = 'pendiente'";
        $stmt = $pdo->prepare($sql);
        $stmt->execute([$t['id']]);
        $solicitudes = $stmt->fetchAll();

        if (empty($solicitudes)) {
            error_log("Bot: No hay solicitudes para turno {$t['id']}");
            return;
        }

        // elegir capitan (preferencia rol_capitan)
        $capitan = null;
        foreach ($solicitudes as $s) {
            if ($s['rol'] === 'capitan' || $s['rol_predeterminado'] === 'capitan') {
                $capitan = $s;
                break;
            }
        }
        if ($capitan) {
            $this->asignarParticipante($t['id'], $capitan['usuario_id'], 'capitan');
        }

        // asignar publicadores (máximo definido en puntos)
        $maxPub = $this->getMaxPublicadores($t['punto_id']);
        $asignados = $capitan ? 1 : 0;

        foreach ($solicitudes as $s) {
            if ($asignados >= $maxPub + 1) break; // +1 porque ya hay capitán
            if ($capitan && $s['usuario_id'] == $capitan['usuario_id']) continue;

            $this->asignarParticipante($t['id'], $s['usuario_id'], 'publicador');
            $asignados++;
        }

        // actualizar estado del turno
        $upd = $pdo->prepare("UPDATE turnos SET estado='planificado' WHERE id=?");
        $upd->execute([$t['id']]);

        error_log("Bot: Turno {$t['id']} planificado automáticamente.");
    }

    /**
     * Insertar participante en turno_participantes
     */
    private function asignarParticipante($turnoId, $usuarioId, $rol)
    {
        global $pdo;
        $stmt = $pdo->prepare("INSERT IGNORE INTO turno_participantes (turno_id, usuario_id, rol, asistio) VALUES (?, ?, ?, 0)");
        $stmt->execute([$turnoId, $usuarioId, $rol]);
    }

    /**
     * Obtener máximo de publicadores para el punto.
     */
    private function getMaxPublicadores($puntoId)
    {
        global $pdo;
        $stmt = $pdo->prepare("SELECT maximo_publicadores FROM puntos WHERE id=?");
        $stmt->execute([$puntoId]);
        $row = $stmt->fetch();
        return $row ? (int)$row['maximo_publicadores'] : 2; // por defecto 2
    }
}
