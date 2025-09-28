function cambiarEstadoTurno(PDO $pdo, int $turnoId, string $nuevoEstado, int $usuarioId) {
    // Obtener datos del turno y punto
    $stmt = $pdo->prepare("
        SELECT t.estado, t.fecha, t.punto_id, 
               p.minimo_publicadores, p.maximo_publicadores
        FROM turnos t
        JOIN puntos p ON t.punto_id = p.id
        WHERE t.id = ?
    ");
    $stmt->execute([$turnoId]);
    $turno = $stmt->fetch();

    if (!$turno) {
        throw new Exception("Turno no encontrado");
    }

    $estadoActual = $turno['estado'];
    $fechaTurno   = $turno['fecha'];

    // Definir transiciones válidas
    $transiciones = [
        'pendiente'  => ['abierto','cancelado'],
        'abierto'    => ['planificado','cancelado'],
        'planificado'=> ['publicado','cancelado'],
        'publicado'  => ['completado','cancelado'],
        'completado' => [],
        'cancelado'  => []
    ];

    if (!in_array($nuevoEstado, $transiciones[$estadoActual])) {
        throw new Exception("Transición inválida: $estadoActual → $nuevoEstado");
    }

    // Validación automática: si turno ya pasó, forzar a completado
    if ($estadoActual === 'publicado' && new DateTime($fechaTurno) < new DateTime()) {
        $nuevoEstado = 'completado';
    }

    // Validaciones de reglas SOLO si pasa a planificado
    if ($nuevoEstado === 'planificado') {
        // Contar publicadores asignados
        $stmt = $pdo->prepare("
            SELECT COUNT(*) FROM turno_participantes 
            WHERE turno_id = ?
        ");
        $stmt->execute([$turnoId]);
        $total = (int)$stmt->fetchColumn();

        // Validar mínimo y máximo
        if ($total < $turno['minimo_publicadores']) {
            throw new Exception("No se puede planificar: faltan publicadores (mínimo {$turno['minimo_publicadores']})");
        }
        if (!empty($turno['maximo_publicadores']) && $total > $turno['maximo_publicadores']) {
            throw new Exception("No se puede planificar: excede el máximo ({$turno['maximo_publicadores']})");
        }

        // Validar que haya al menos un capitán
        $stmt = $pdo->prepare("
            SELECT COUNT(*) FROM turno_participantes 
            WHERE turno_id = ? AND rol = 'capitan'
        ");
        $stmt->execute([$turnoId]);
        $capitanes = (int)$stmt->fetchColumn();

        if ($capitanes === 0) {
            throw new Exception("No se puede planificar: falta capitán asignado");
        }
    }

    // Ejecutar transición
    $pdo->beginTransaction();
    try {
        $stmt = $pdo->prepare("UPDATE turnos SET estado = ? WHERE id = ?");
        $stmt->execute([$nuevoEstado, $turnoId]);

        // Log para auditoría
        $stmt = $pdo->prepare("
            INSERT INTO turnos_log (turno_id, estado_anterior, estado_nuevo, cambiado_por, fecha_cambio)
            VALUES (?, ?, ?, ?, NOW())
        ");
        $stmt->execute([$turnoId, $estadoActual, $nuevoEstado, $usuarioId]);

        $pdo->commit();
    } catch (Exception $e) {
        $pdo->rollBack();
        throw $e;
    }

    return $nuevoEstado;
}
