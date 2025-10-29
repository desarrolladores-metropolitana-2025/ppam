<?php
/**
 * Valida un turno según las reglas de planificación configuradas.
 * Devuelve un array con errores y advertencias.
 */
function validarTurnoAntesDePlanificar(PDO $pdo, int $turno_id): array {
    $result = [
        'errores' => [],
        'advertencias' => []
    ];

    // Traer datos del turno y sus participantes
    $stmt = $pdo->prepare("
        SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.punto_id,
               p.nombre AS punto, p.maximo_publicadores, p.minimo_publicadores
        FROM turnos t
        JOIN puntos p ON p.id = t.punto_id
        WHERE t.id = ?
    ");
    $stmt->execute([$turno_id]);
    $turno = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$turno) {
        $result['errores'][] = "El turno no existe.";
        return $result;
    }

    // Participantes actuales
    $stmt = $pdo->prepare("
        SELECT u.id, u.full_name, tp.rol, tp.asistio
        FROM turno_participantes tp
        JOIN users u ON u.id = tp.usuario_id
        WHERE tp.turno_id = ?
    ");
    $stmt->execute([$turno_id]);
    $participantes = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $numCapitanes = count(array_filter($participantes, fn($p) => $p['rol'] === 'capitan'));
    $numPublis    = count(array_filter($participantes, fn($p) => $p['rol'] === 'publicador'));

    // === EJEMPLOS de reglas (de las 14 que mencionaste) ===

    // 1. Múltiples capitanes asignados al mismo punto
    if ($numCapitanes > 1) {
        $result['errores'][] = "Hay más de un capitán asignado.";
    } elseif ($numCapitanes === 0) {
        $result['advertencias'][] = "Falta asignar un capitán.";
    }

    // 2. Demasiados publicadores
    if ($turno['maximo_publicadores'] > 0 && $numPublis > $turno['maximo_publicadores']) {
        $result['errores'][] = "Se superó el máximo de publicadores permitido.";
    }

    // 3. No suficientes publicadores
    if ($numPublis < $turno['minimo_publicadores']) {
        $result['advertencias'][] = "Faltan publicadores para este turno.";
    }

    // 4. Ejemplo de regla con idiomas (simulada)
    // Podrías cruzar `turno_idioma` con los idiomas de usuarios
    // y verificar compatibilidad

    // Aquí irían las demás validaciones (hasta las 14)

    return $result;
}
