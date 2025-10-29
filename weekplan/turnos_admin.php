<?php
ini_set('display_errors', 1);
error_reporting(E_ALL);
//require_once __DIR__ . '/../includes/auth.php';
//require_login();
require_once __DIR__ . '/../includes/exp_config.php'; // tu conexión PDO $pdo

$accion = $_GET['accion'] ?? '';

if ($accion === 'listar_por_rango') {
  $desde = $_GET['desde'];
  $hasta = $_GET['hasta'];

  // Traemos todos los datos necesarios para mostrar los turnos en la grilla
  $sql = "SELECT 
            t.id,
            t.fecha,
            t.hora_inicio,
            t.hora_fin,
            t.estado,
            p.nombre AS punto
          FROM turnos t
          LEFT JOIN puntos p ON p.id = t.punto_id
          WHERE t.fecha BETWEEN ? AND ?
          ORDER BY t.fecha, t.hora_inicio";

  $stmt = $pdo->prepare($sql);
  $stmt->execute([$desde, $hasta]);

  $data = [];

  while ($r = $stmt->fetch(PDO::FETCH_ASSOC)) {
    // Buscar participantes si existen
    $sub = $pdo->prepare("SELECT tp.usuario_id, u.full_name AS nombre 
                          FROM turno_participantes tp 
                          LEFT JOIN users u ON u.id = tp.usuario_id
                          WHERE tp.turno_id = ?");
    $sub->execute([$r['id']]);
    $r['participantes'] = $sub->fetchAll(PDO::FETCH_ASSOC);

    // Agrupar por fecha
    $data[$r['fecha']][] = $r;
  }

  header('Content-Type: application/json; charset=utf-8');
  echo json_encode($data, JSON_UNESCAPED_UNICODE);
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
  // $uid = $_SESSION['user_id'];
  $uid =1;

  $sql = "INSERT INTO turnos (fecha,hora_inicio,hora_fin,punto_id,estado,created_by)
          VALUES (?,?,?,?, 'creado', ?)";
  $stmt = $pdo->prepare($sql);
  $ok = $stmt->execute([$fecha, $inicio, $fin, $punto, $uid]);
  echo json_encode(['ok'=>$ok]);
  exit;
}

if ($accion === 'asignar_manual') {

    // espera JSON { turno_id, usuario_id, rol }
    $payload = json_decode(file_get_contents('php://input'), true);
    $turno_id = intval($payload['turno_id'] ?? 0);
    $usuario_id = intval($payload['usuario_id'] ?? 0);
    $rol = $payload['rol'] ?? 'publicador';

    if (!$turno_id || !$usuario_id) {
      echo json_encode(['error'=>'turno_id/usuario_id faltante']);
      exit;
    }

    // evitar duplicados
    $chk = $pdo->prepare("SELECT COUNT(*) FROM turno_participantes WHERE turno_id=? AND usuario_id=?");
    $chk->execute([$turno_id, $usuario_id]);
    if ($chk->fetchColumn() > 0) {
      echo json_encode(['ok'=>false,'error'=>'Usuario ya asignado']);
      exit;
    }

    $ins = $pdo->prepare("INSERT INTO turno_participantes (turno_id, usuario_id, rol, asignado_por, asignado_en) VALUES (?, ?, ?, ?, NOW())");
    $ins->execute([$turno_id, $usuario_id, $rol, $_SESSION['user_id'] ?? null]);

    // opcional: notificar, actualizar estado del turno si completo...
    echo json_encode(['ok'=>true,'message'=>'Asignado manualmente']);
    exit;
}


echo json_encode(['error'=>'Acción no válida']);
