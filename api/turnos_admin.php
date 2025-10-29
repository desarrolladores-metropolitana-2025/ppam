<?php
ini_set('display_errors', 1);
error_reporting(E_ALL);
//require_once __DIR__ . '/../includes/auth.php';
//require_login();
require_once __DIR__ . '/../includes/exp_config.php'; // tu conexión PDO $pdo

$accion = $_GET['accion'] ?? '';

if ($accion === 'listar') {
  $sql = "SELECT 
            t.id,
            t.fecha,
            t.hora_inicio,
            t.hora_fin,
            p.nombre AS punto,
            t.punto_id,
            (SELECT COUNT(*) FROM turno_participantes tp WHERE tp.turno_id = t.id) AS asignados,
            3 AS maximo_publicadores
          FROM turnos t
          LEFT JOIN puntos p ON p.id = t.punto_id
          ORDER BY t.fecha, t.hora_inicio";
  $stmt = $pdo->query($sql);
  $turnos = $stmt->fetchAll(PDO::FETCH_ASSOC);

  foreach ($turnos as &$r) {
    if (!empty($r['hora_inicio'])) {
      $r['hora_inicio'] = substr($r['hora_inicio'], 0, 5);
    }
    if (!empty($r['hora_fin'])) {
      $r['hora_fin'] = substr($r['hora_fin'], 0, 5);
    }
  }

  echo json_encode($turnos);
  exit;
}


if ($accion === 'listar_por_rango') {
  $desde = $_GET['desde'];
  $hasta = $_GET['hasta'];

  $sql = "SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, 
                 p.nombre AS punto, t.estado
          FROM turnos t
          LEFT JOIN puntos p ON t.punto_id = p.id
          WHERE t.fecha BETWEEN ? AND ?
          ORDER BY t.fecha, t.hora_inicio";
  $stmt = $pdo->prepare($sql);
  $stmt->execute([$desde, $hasta]);

  $data = [];
  while ($r = $stmt->fetch(PDO::FETCH_ASSOC)) {
    $r['hora_inicio'] = substr($r['hora_inicio'], 0, 5);
    $r['hora_fin'] = substr($r['hora_fin'], 0, 5);

    $st2 = $pdo->prepare("SELECT u.full_name AS nombre, u.id AS usuario_id
                          FROM turno_participantes tp
                          JOIN users u ON u.id = tp.usuario_id
                          WHERE tp.turno_id = ?");
    $st2->execute([$r['id']]);
    $r['participantes'] = $st2->fetchAll(PDO::FETCH_ASSOC);

    $data[$r['fecha']][] = $r;
  }

  echo json_encode($data);
  exit;
}


if ($accion === 'puntos_disponibles') {
  $fecha = $_GET['fecha'];
  $sql = "SELECT p.id, p.nombre FROM puntos p
          WHERE NOT EXISTS (
            SELECT 1 FROM feriados f WHERE f.fecha = :f AND (f.region IS NULL OR f.region='')
          )";
  $stmt = $pdo->prepare($sql);
  $stmt->execute([':f' => $fecha]);
  echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
  exit;
}


if ($accion === 'crear') {
  $fecha = $_POST['fecha'];
  $inicio = $_POST['hora_inicio'];
  $fin = $_POST['hora_fin'];
  $punto = $_POST['punto_id'];
  $uid = $_SESSION['user_id'];

  $sql = "INSERT INTO turnos (fecha,hora_inicio,hora_fin,punto_id,estado,created_by)
          VALUES (?,?,?,?, 'creado', ?)";
  $stmt = $pdo->prepare($sql);
  $ok = $stmt->execute([$fecha, $inicio, $fin, $punto, $uid]);
  echo json_encode(['ok'=>$ok]);
  exit;
}


if ($accion === 'asignar_manual') {

    // Espera JSON { turno_id, usuario_id, rol }
    $payload = json_decode(file_get_contents('php://input'), true);
    $turno_id = intval($payload['turno_id'] ?? 0);
    $usuario_id = intval($payload['usuario_id'] ?? 0);
    $rol = $payload['rol'] ?? 'publicador';

    if (!$turno_id || !$usuario_id) {
      echo json_encode(['error'=>'turno_id/usuario_id faltante']);
      exit;
    }

    try {
      $pdo->beginTransaction();

      // evitar duplicados
      $chk = $pdo->prepare("SELECT COUNT(*) FROM turno_participantes WHERE turno_id=? AND usuario_id=?");
      $chk->execute([$turno_id, $usuario_id]);
      if ($chk->fetchColumn() > 0) {
        echo json_encode(['ok'=>false,'error'=>'Usuario ya asignado']);
        $pdo->rollBack();
        exit;
      }

      // insertar asignación
      $ins = $pdo->prepare("INSERT INTO turno_participantes (turno_id, usuario_id, rol, asignado_por, asignado_en) 
                            VALUES (?, ?, ?, ?, NOW())");
      $ins->execute([$turno_id, $usuario_id, $rol, $_SESSION['user_id'] ?? null]);

      /*  PATCH: Actualizar solicitud si existe */
      $upd = $pdo->prepare("UPDATE solicitudes 
                            SET estado='aprobada', processed_by=?, processed_at=NOW()
                            WHERE usuario_id=? AND turno_id=? AND estado='pendiente'");
      $upd->execute([$_SESSION['user_id'] ?? null, $usuario_id, $turno_id]);

      /*  PATCH: Insertar notificación */
      $msg = "Tu solicitud para el turno #$turno_id ha sido aprobada. ¡Te esperamos!";
      $not = $pdo->prepare("INSERT INTO notificaciones 
                            (turno_id, usuario_id, tipo, mensaje, canal, estado, creado_en)
                            VALUES (?, ?, 'cubierto', ?, 'email', 'pending', NOW())");
      $not->execute([$turno_id, $usuario_id, $msg]);

      $pdo->commit();
      echo json_encode(['ok'=>true,'message'=>'Asignado manualmente + notificado']);
    } catch (Exception $e) {
      $pdo->rollBack();
      echo json_encode(['ok'=>false,'error'=>$e->getMessage()]);
    }
    exit;
}


if ($accion === 'crear_manual') {
  $payload = json_decode(file_get_contents('php://input'), true);

  $fecha = $payload['fecha'] ?? null;
  $inicio = $payload['hora_inicio'] ?? null;
  $fin = $payload['hora_fin'] ?? null;
  $puntoNombre = trim($payload['punto'] ?? '');
  $maximo = intval($payload['maximo_publicadores'] ?? 3);
  $uid = $_SESSION['user_id'] ?? null;

  if (!$fecha || !$inicio || !$fin || !$puntoNombre) {
    echo json_encode(['ok'=>false, 'error'=>'Faltan campos obligatorios']);
    exit;
  }

  try {
    $stF = $pdo->prepare("SELECT nombre FROM feriados WHERE fecha = ? LIMIT 1");
    $stF->execute([$fecha]);
    $feriado = $stF->fetchColumn();
    if ($feriado) {
      echo json_encode(['ok'=>false, 'error'=>"No se pueden crear turnos en feriado: $feriado"]);
      exit;
    }

    $st = $pdo->prepare("SELECT id FROM puntos WHERE nombre = ?");
    $st->execute([$puntoNombre]);
    $punto = $st->fetchColumn();

    if (!$punto) {
      $insP = $pdo->prepare("INSERT INTO puntos (nombre) VALUES (?)");
      $insP->execute([$puntoNombre]);
      $punto = $pdo->lastInsertId();
    }

    $sqlSolap = "SELECT COUNT(*) 
                 FROM turnos 
                 WHERE punto_id = ? AND fecha = ?
                 AND (
                   (hora_inicio < ? AND hora_fin > ?) OR 
                   (hora_inicio >= ? AND hora_inicio < ?)
                 )";
    $chk = $pdo->prepare($sqlSolap);
    $chk->execute([$punto, $fecha, $fin, $inicio, $inicio, $fin]);
    $existeSolape = $chk->fetchColumn();

    if ($existeSolape > 0) {
      echo json_encode(['ok'=>false, 'error'=>'Ya existe un turno en ese punto con horario superpuesto.']);
      exit;
    }

    $sql = "INSERT INTO turnos (fecha, hora_inicio, hora_fin, punto_id, maximo_publicadores, estado, created_by)
            VALUES (?, ?, ?, ?, ?, 'creado', ?)";
    $stmt = $pdo->prepare($sql);
    $ok = $stmt->execute([$fecha, $inicio, $fin, $punto, $maximo, $uid]);

    echo json_encode([
      'ok' => $ok,
      'turno_id' => $pdo->lastInsertId(),
      'message' => $ok ? 'Turno creado exitosamente' : 'Error al crear turno'
    ]);
  } catch (Exception $e) {
    echo json_encode(['ok'=>false, 'error'=>$e->getMessage()]);
  }
  exit;
}

echo json_encode(['error'=>'Acción no válida']);
