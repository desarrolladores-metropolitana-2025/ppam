<?php
/**
 * Valida un turno contra las 14 reglas configuradas dinámicamente.
 * Devuelve un array de problemas con: regla, nivel y mensaje.
 */
function validarTurnoAntesDePlanificar(PDO $pdo, int $turnoId): array {
    $resultados = [];

    // --- Cargar configuraciones de reglas ---
    $stmt = $pdo->prepare("SELECT clave, valor FROM configuraciones WHERE seccion = 'planificacion'");
    $stmt->execute();
    $niveles = $stmt->fetchAll(PDO::FETCH_KEY_PAIR); // [clave => nivel]

    // --- Datos base del turno ---
    $stmt = $pdo->prepare("
        SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin,
               p.nombre AS punto_nombre, 
               p.minimo_publicadores, p.maximo_publicadores, p.minimo_varones,
               p.restriccion_asig
        FROM turnos t
        JOIN puntos p ON t.punto_id = p.id
        WHERE t.id = ?
    ");
    $stmt->execute([$turnoId]);
    $turno = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$turno) {
        return [['regla'=>'Validación','nivel'=>'Error','mensaje'=>'El turno no existe']];
    }

    // Participantes
    $stmt = $pdo->prepare("SELECT usuario_id, rol, asistio FROM turno_participantes WHERE turno_id = ?");
    $stmt->execute([$turnoId]);
    $participantes = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $capitanes    = array_filter($participantes, fn($p) => $p['rol'] === 'capitan');
    $publicadores = array_filter($participantes, fn($p) => $p['rol'] === 'publicador');

    $totalCapitanes = count($capitanes);
    $totalPublis    = count($publicadores);

    // ======================
    // 🔹 Reglas dinámicas
    // ======================

    // 1. Múltiples capitanes
    if ($totalCapitanes == 0 || $totalCapitanes > 1) {
        $resultados[] = [
            'regla'=>'Capitán',
            'nivel'=>$niveles['multiple_capitanes'] ?? 'Error',
            'mensaje'=> $totalCapitanes == 0 
                ? 'No hay capitán asignado.' 
                : 'Hay más de un capitán asignado.'
        ];
    }

    // 2. Idioma incorrecto
    if ($niveles['idioma_incorrecto'] !== 'Ninguno') {
        $resultados[] = [
            'regla'=>'Idioma',
            'nivel'=>$niveles['idioma_incorrecto'],
            'mensaje'=>'Ningún publicador habla el idioma del punto.'
        ];
    }

    // 3. Sin publicadores
    if ($totalPublis == 0) {
        $resultados[] = [
            'regla'=>'Publicadores',
            'nivel'=>$niveles['sin_publicadores'] ?? 'Error',
            'mensaje'=>'No hay publicadores en este turno.'
        ];
    }

    // 4. Compañeros separados
    if ($niveles['companeros_separados'] !== 'Ninguno') {
        $resultados[] = [
            'regla'=>'Compañeros',
            'nivel'=>$niveles['companeros_separados'],
            'mensaje'=>'Los compañeros no están asignados juntos.'
        ];
    }

    // ... (igual con las otras reglas hasta la 14)
    // Ejemplo de una con parámetro del punto:
    if ($turno['restriccion_asig']) {
        $resultados[] = [
            'regla'=>'Restricción',
            'nivel'=>$niveles['punto_imposible'] ?? 'Error',
            'mensaje'=>'El turno fue marcado como no planificable.'
        ];
    }

    return $resultados;
}
