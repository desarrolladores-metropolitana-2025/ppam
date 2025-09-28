<?php
/**
 * Validar turno antes de planificar
 *
 * @param PDO $pdo
 * @param int $turnoId
 * @return array Lista de problemas detectados
 */
function validarTurnoAntesDePlanificar(PDO $pdo, int $turnoId): array
{
    // 1) Configuraciones de planificación
    $stmt = $pdo->prepare("
        SELECT clave, valor
        FROM configuraciones
        WHERE seccion = 'planificacion'
    ");
    $stmt->execute();
    $configs = $stmt->fetchAll(PDO::FETCH_KEY_PAIR);

    // 2) Definir todas las reglas
    $reglas = [
        'multiples_capitanes'   => 'Múltiples capitanes asignados al mismo punto',
        'idioma_incorrecto'     => 'Ninguno de los publicadores habla el idioma del punto',
        'sin_publicadores'      => 'Ningún publicador asignado',
        'companeros_separados'  => 'Los compañeros no han sido asignados juntos',
        'ignora_turnos_consec'  => 'No se considera la solicitud para turnos consecutivos',
        'multi_turnos_consec'   => 'Un publicador está asignado en diferentes puntos en turnos consecutivos',
        'sin_capitan_suplente'  => 'No hay capitán sustituto',
        'faltan_publicadores'   => 'No hay suficientes publicadores asignados',
        'sobran_publicadores'   => 'Asignados más publicadores que el máximo permitido',
        'sin_vehiculo'          => 'Ningún publicador tiene vehículo disponible',
        'faltan_varones'        => 'No hay suficientes hermanos varones asignados',
        'mismo_dia_repetido'    => 'Publicador asignado varias veces en el mismo día',
        'sin_mentores'          => 'No hay suficientes mentores asignados',
        'punto_imposible'       => 'Asignado en un punto imposible',
    ];

    $problemas = [];

    // 3) Validación real: múltiples capitanes
    $sql = "
        SELECT COUNT(*) as capitanes
        FROM turno_participantes
        WHERE turno_id = :turnoId AND rol = 'capitan'
    ";
    $stmt = $pdo->prepare($sql);
    $stmt->execute(['turnoId' => $turnoId]);
    $capitanes = $stmt->fetchColumn();

    if ($capitanes > 1 && ($configs['multiples_capitanes'] ?? 'ninguno') !== 'ninguno') {
        $problemas[] = [
            'clave'       => 'multiples_capitanes',
            'nivel'       => ucfirst($configs['multiples_capitanes']),
            'descripcion' => $reglas['multiples_capitanes']
        ];
    }

    // 4) Validación real: sin publicadores
    $sql = "
        SELECT COUNT(*) as publis
        FROM turno_participantes
        WHERE turno_id = :turnoId
    ";
    $stmt = $pdo->prepare($sql);
    $stmt->execute(['turnoId' => $turnoId]);
    $publis = $stmt->fetchColumn();

    if ($publis == 0 && ($configs['sin_publicadores'] ?? 'ninguno') !== 'ninguno') {
        $problemas[] = [
            'clave'       => 'sin_publicadores',
            'nivel'       => ucfirst($configs['sin_publicadores']),
            'descripcion' => $reglas['sin_publicadores']
        ];
    }

    // 5) Validación real: idioma incorrecto
    $sql = "
        SELECT p.idiomas_id, COUNT(u.id) as hablantes
        FROM turnos t
        JOIN puntos p ON t.punto_id = p.id
        LEFT JOIN turno_participantes tp ON tp.turno_id = t.id
        LEFT JOIN users u ON u.id = tp.usuario_id
        WHERE t.id = :turnoId
        GROUP BY p.idiomas_id
    ";
    $stmt = $pdo->prepare($sql);
    $stmt->execute(['turnoId' => $turnoId]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($row && $row['idiomas_id'] && $row['hablantes'] == 0 
        && ($configs['idioma_incorrecto'] ?? 'ninguno') !== 'ninguno') {
        $problemas[] = [
            'clave'       => 'idioma_incorrecto',
            'nivel'       => ucfirst($configs['idioma_incorrecto']),
            'descripcion' => $reglas['idioma_incorrecto']
        ];
    }

    // 6) El resto de reglas: simuladas con base en configuración
    foreach ($reglas as $clave => $descripcion) {
        if (in_array($clave, ['multiples_capitanes','sin_publicadores','idioma_incorrecto'])) {
            continue; // ya validadas arriba
        }
        $nivel = $configs[$clave] ?? 'ninguno';
        if ($nivel !== 'ninguno') {
            $problemas[] = [
                'clave'       => $clave,
                'nivel'       => ucfirst($nivel),
                'descripcion' => $descripcion
            ];
        }
    }

    return $problemas;
}
