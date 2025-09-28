<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

$page_title = 'Turnos';
 ob_start();
require_once __DIR__ . '/../exp_config.php';
require_once __DIR__ . '/../settings/cfgpanel/load_config.php';

function log_problema($tipo, $mensaje) {
    echo "<div class='alert $tipo'>$mensaje</div>";
}

try {
    // Obtener puntos sin planificar (ejemplo: estado 'pendiente')
    $puntos = $pdo->query("
    SELECT 
        p.id,
        p.nombre,
        p.fecha,
        p.minimo_publicadores,
        p.maximo_publicadores,
        p.idiomas_id,
        COUNT(t.id) AS turnos_creados
    FROM puntos p
    LEFT JOIN turnos t ON t.punto_id = p.id
    WHERE t.id IS NULL OR t.estado = 'pendiente'
    GROUP BY p.id, p.nombre, p.fecha, p.minimo_publicadores, p.maximo_publicadores, p.idiomas_id
")->fetchAll(PDO::FETCH_ASSOC);


    foreach ($puntos as $punto) {
        echo "<h3>Planificando punto: {$punto['nombre']}</h3>";

        // Buscar solicitudes para este punto
        $stmt = $pdo->prepare("
            SELECT s.*, u.id as usuario_id, u.full_name, u.capitan, u.experience, u.genero, u.tiene_vehiculo, u.idiomas_id
            FROM solicitudes s
            JOIN users u ON u.id = s.usuario_id
            WHERE s.estado = 'aprobada' AND s.punto_id = ?
        ");
        $stmt->execute([$punto['id']]);
        $candidatos = $stmt->fetchAll(PDO::FETCH_ASSOC);

        // Filtrar por disponibilidad
        $candidatos = array_filter($candidatos, function($c) use ($pdo, $punto) {
            $dia = strtolower(date('l', strtotime($punto['fecha'] ?? 'now')));
            $stmt = $pdo->prepare("SELECT 1 FROM disponibilidad WHERE usuario_id = ? AND dia = ?");
            $stmt->execute([$c['usuario_id'], $dia]);
            return $stmt->fetch();
        });

        // Filtrar por ausencias
        $candidatos = array_filter($candidatos, function($c) use ($pdo, $punto) {
            $fecha = $punto['fecha'] ?? date('Y-m-d');
            $stmt = $pdo->prepare("SELECT 1 FROM ausencias WHERE usuario_id = ? AND ? BETWEEN fecha_inicio AND fecha_fin");
            $stmt->execute([$c['usuario_id'], $fecha]);
            return !$stmt->fetch();
        });

        // Priorizar capitanes
        $capitanes = array_filter($candidatos, fn($c) => $c['capitan'] == 1);
        if (count($capitanes) === 0) {
            $check = $GLOBALS['config']['planificacion']['check_multicapitan'] ?? 'error';
            if ($check === 'error') {
                log_problema('error', "Falta capitán en {$punto['nombre']} (bloqueado)");
                continue;
            } elseif ($check === 'advertencia') {
                log_problema('warning', "Falta capitán en {$punto['nombre']}");
            }
        }

        // Validar mínimos y máximos
        if (count($candidatos) < $punto['minimo_publicadores']) {
            log_problema('error', "No hay suficientes publicadores en {$punto['nombre']}");
            continue;
        }
        if (count($candidatos) > $punto['maximo_publicadores']) {
            log_problema('error', "Demasiados publicadores en {$punto['nombre']}");
            continue;
        }

        // Verificar idioma
        $habla_idioma = array_filter($candidatos, fn($c) => $c['idiomas_id'] == $punto['idiomas_id']);
        if (empty($habla_idioma)) {
            $check = $GLOBALS['config']['planificacion']['check_idioma'] ?? 'error';
            if ($check === 'error') {
                log_problema('error', "Nadie habla el idioma del punto {$punto['nombre']}");
                continue;
            }
        }

        // TODO: agregar las demás validaciones (mentores, vehículos, turnos consecutivos...)

        // Crear turno
        $stmt = $pdo->prepare("
            INSERT INTO turnos (fecha, hora_inicio, hora_fin, punto_id, estado)
            VALUES (CURDATE(), '09:00:00', '11:00:00', ?, 'planificado')
        ");
        $stmt->execute([$punto['id']]);
        $turno_id = $pdo->lastInsertId();

        // Insertar participantes (ejemplo simple: todos los candidatos hasta máximo)
        $candidatos = array_slice($candidatos, 0, $punto['maximo_publicadores']);
        foreach ($candidatos as $c) {
            $rol = $c['capitan'] ? 'capitan' : 'publicador';
            $stmt = $pdo->prepare("INSERT INTO turno_participantes (turno_id, usuario_id, rol, asistio) VALUES (?, ?, ?, 0)");
            $stmt->execute([$turno_id, $c['usuario_id'], $rol]);
        }

        echo "<div class='success'>Turno creado en {$punto['nombre']} con " . count($candidatos) . " participantes.</div>";
    }

} catch (Exception $e) {
    echo "<div class='error'>Error: " . $e->getMessage() . "</div>";
}

 $content = ob_get_clean();
include __DIR__ . '/../turnos_layout.php';