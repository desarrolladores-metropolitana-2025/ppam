<?php
ini_set('display_errors', 1);
error_reporting(E_ALL);
require_once __DIR__ . '/../includes/exp_config.php';
header('Content-Type: application/json; charset=utf-8');
date_default_timezone_set('America/Argentina/Buenos_Aires');

$accion = $_GET['accion'] ?? 'listar';

switch ($accion) {

  /* =========================================================
     1️⃣ LISTAR USUARIOS BÁSICO
  ========================================================== */
  case 'listar':
    $stmt = $pdo->query("SELECT id, full_name, last_name, email FROM users ORDER BY last_name");
    echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
    break;


  /* =========================================================
     2️⃣ LISTAR USUARIOS DISPONIBLES (rango)
  ========================================================== */
  case 'listar_disponibles':
    $desde = $_GET['desde'] ?? date('Y-m-d');
    $hasta = $_GET['hasta'] ?? date('Y-m-d', strtotime('+7 days'));
    $puntoId = (int)($_GET['punto'] ?? 0);

    $stmt = $pdo->query("SELECT id, full_name, last_name, email FROM users WHERE bloqueado = 0 ORDER BY last_name");
    $usuarios = $stmt->fetchAll(PDO::FETCH_ASSOC);

    foreach ($usuarios as &$u) {
      $uid = $u['id'];

      // 🔹 Disponibilidad
      $sql = "SELECT dia_semana, hora_inicio, hora_fin, frecuencia 
              FROM disponibilidades
              WHERE usuario_id = ? AND (end_date IS NULL OR end_date >= ?)";
      $st = $pdo->prepare($sql);
      $st->execute([$uid, $desde]);
      $u['disponibilidad'] = $st->fetchAll(PDO::FETCH_ASSOC);

      // 🔹 Ausencias
      $sql = "SELECT fecha_inicio, fecha_fin, motivo
              FROM ausencias
              WHERE usuario_id = ? AND fecha_fin >= ? AND fecha_inicio <= ?";
      $st = $pdo->prepare($sql);
      $st->execute([$uid, $desde, $hasta]);
      $u['ausencias'] = $st->fetchAll(PDO::FETCH_ASSOC);

      // 🔹 Preferencias
      $sql = "SELECT punto_id, nivel, prioridad
              FROM user_point_preferences
              WHERE usuario_id = ?";
      $st = $pdo->prepare($sql);
      $st->execute([$uid]);
      $u['preferencias'] = $st->fetchAll(PDO::FETCH_ASSOC);

      // 🔹 Carga semanal
      $sql = "SELECT COUNT(*) FROM turno_participantes tp
              JOIN turnos t ON tp.turno_id = t.id
              WHERE tp.usuario_id = ?
              AND t.fecha >= DATE_SUB(CURDATE(), INTERVAL 4 WEEK)";
      $st = $pdo->prepare($sql);
      $st->execute([$uid]);
      $u['carga_ultimas_4_semanas'] = (int)$st->fetchColumn();

      // 🔹 Idiomas
      if (tableHasColumn($pdo, 'users', 'idiomas_id')) {
        $st = $pdo->prepare("SELECT idiomas_id FROM users WHERE id = ?");
        $st->execute([$uid]);
        $u['idiomas_id'] = (int)$st->fetchColumn();
      }
    }

    echo json_encode($usuarios);
    break;


  /* =========================================================
     VALIDAR DISPONIBILIDAD / ASIGNABILIDAD DE UN USUARIO
  ========================================================== */
  case 'validar_disponibilidad':
    $usuario_id = (int)($_GET['usuario_id'] ?? 0);
    $fecha = $_GET['fecha'] ?? null;
    $hora_inicio = $_GET['hora_inicio'] ?? null;
    $hora_fin = $_GET['hora_fin'] ?? null;
    $punto_id = (int)($_GET['punto_id'] ?? 0);
    $rol = $_GET['rol'] ?? 'publicador';

    $hora_inicio = substr($hora_inicio, 0, 5) . ':00';
    $hora_fin = substr($hora_fin, 0, 5) . ':00';

    if (!$usuario_id || !$fecha || !$hora_inicio || !$hora_fin) {
      echo json_encode(['ok' => false, 'motivo' => 'Parámetros incompletos']);
      exit;
    }

    //  PATCH: Verificar si tiene solicitud para ese turno (ya lo solicitó)
    $st = $pdo->prepare("
      SELECT COUNT(*) FROM solicitudes s
      JOIN turnos t ON s.turno_id = t.id
      WHERE s.usuario_id = ?
        AND (s.estado = 'pendiente' OR s.estado = 'aprobada')
        AND t.fecha = ?
        AND NOT (t.hora_fin <= ? OR t.hora_inicio >= ?)
    ");
    $st->execute([$usuario_id, $fecha, $hora_inicio, $hora_fin]);
    if ($st->fetchColumn() > 0) {
      echo json_encode(['ok' => true, 'motivo' => 'Solicitud previa encontrada (apta)']);
      exit;
    }

    // Ausencia
    $st = $pdo->prepare("SELECT COUNT(*) FROM ausencias WHERE usuario_id=? AND fecha_inicio<=? AND fecha_fin>=?");
    $st->execute([$usuario_id, $fecha, $fecha]);
    if ($st->fetchColumn() > 0) {
      echo json_encode(['ok' => false, 'motivo' => 'Ausente en esa fecha']);
      exit;
    }

    // Disponibilidad
    $st = $pdo->prepare("SELECT * FROM disponibilidades WHERE usuario_id=?");
    $st->execute([$usuario_id]);
    if ($st->fetchColumn() > 0) {
      $weekday = date('N', strtotime($fecha));
      $stmt = $pdo->prepare("SELECT COUNT(*) FROM disponibilidades
                             WHERE usuario_id=? AND dia_semana=? 
                             AND hora_inicio<=? AND hora_fin>=?");
      $stmt->execute([$usuario_id, $weekday, $hora_inicio, $hora_fin]);
      if ($stmt->fetchColumn() == 0) {
        echo json_encode(['ok' => false, 'motivo' => 'Fuera de horario disponible']);
        exit;
      }
    }

    // BIS - evitar solapamiento
    $st = $pdo->prepare("
      SELECT COUNT(*) 
      FROM turno_participantes tp
      JOIN turnos t ON tp.turno_id = t.id
      WHERE tp.usuario_id = ?
      AND t.fecha = ?
      AND NOT (t.hora_fin <= ? OR t.hora_inicio >= ?)
    ");
    $st->execute([$usuario_id, $fecha, $hora_inicio, $hora_fin]);
    if ($st->fetchColumn() > 0) {
      echo json_encode(['ok' => false, 'motivo' => 'Ya tiene otro turno en ese horario']);
      exit;
    }

    // Preferencia de punto
    if ($punto_id) {
      $st = $pdo->prepare("SELECT nivel FROM user_point_preferences WHERE usuario_id=? AND punto_id=?");
      $st->execute([$usuario_id, $punto_id]);
      $nivel = $st->fetchColumn();
      if ($nivel === 'no_posible') {
        echo json_encode(['ok' => false, 'motivo' => 'Punto marcado como no posible']);
        exit;
      }
    }

    // Idioma compatible
    if (tableHasColumn($pdo, 'puntos', 'idiomas_id') && tableHasColumn($pdo, 'users', 'idiomas_id') && $punto_id != 0) {
      $sql = "SELECT COUNT(*) FROM users u 
              JOIN puntos p ON p.id = ?
              WHERE u.id = ? AND (u.idiomas_id IS NULL OR p.idiomas_id IS NULL OR u.idiomas_id = p.idiomas_id)";
      $st = $pdo->prepare($sql);
      $st->execute([$punto_id, $usuario_id]);
      if ($st->fetchColumn() == 0) {
        echo json_encode(['ok' => false, 'motivo' => 'Idioma no compatible']);
        exit;
      }
    }

    // Límite mensual
    $max_turnos_mes = 5;
    $st = $pdo->prepare("SELECT COUNT(*) FROM turno_participantes tp
                         JOIN turnos t ON tp.turno_id = t.id
                         WHERE tp.usuario_id = ?
                         AND MONTH(t.fecha) = MONTH(?)
                         AND YEAR(t.fecha) = YEAR(?)");
    $st->execute([$usuario_id, $fecha, $fecha]);
    if ((int)$st->fetchColumn() >= $max_turnos_mes) {
      echo json_encode(['ok' => false, 'motivo' => 'Límite mensual alcanzado']);
      exit;
    }

    // Rol
    if ($rol === 'capitan') {
      $st = $pdo->prepare("SELECT rol FROM users WHERE id = ?");
      $st->execute([$usuario_id]);
      $rol_user = $st->fetchColumn();
      if ($rol_user !== 'capitan' && $rol_user !== 'admin') {
        echo json_encode(['ok' => false, 'motivo' => 'No tiene rol de capitán']);
        exit;
      }
    }

    echo json_encode(['ok' => true]);
    break;

  default:
    echo json_encode(['error' => 'Acción no soportada']);
    break;
}

/* =========================================================
   🔧 FUNCIONES AUXILIARES
========================================================= */
function tableHasColumn(PDO $pdo, string $table, string $column): bool {
  $sql = "SELECT COUNT(*) FROM information_schema.columns
          WHERE table_schema = DATABASE() AND table_name = ? AND column_name = ?";
  $st = $pdo->prepare($sql);
  $st->execute([$table, $column]);
  return (int)$st->fetchColumn() > 0;
};
