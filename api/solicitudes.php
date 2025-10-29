<?php
require_once __DIR__ . '/../includes/exp_config.php'; // $pdo
header('Content-Type: application/json');

$accion = $_GET['accion'] ?? null;

// TODO: autenticación real (admin / publicador)
$usuario_id = $_SESSION['user_id'] ?? 1; 
$rol_usuario = $_SESSION['rol'] ?? 'admin';

switch ($accion) {

  // 🧾 1. Listar solicitudes
  case 'listar':
    if ($rol_usuario === 'admin') {
      $stmt = $pdo->query("SELECT s.*, u.full_name as usuario, t.fecha, t.hora_inicio, t.hora_fin, p.nombre as punto
                           FROM solicitudes s
                           JOIN users u ON s.usuario_id = u.id
                           JOIN turnos t ON s.turno_id = t.id
                           JOIN puntos p ON t.punto_id = p.id
                           ORDER BY t.fecha DESC");
    } else {
      $stmt = $pdo->prepare("SELECT s.*, t.fecha, t.hora_inicio, t.hora_fin, p.nombre as punto
                             FROM solicitudes s
                             JOIN turnos t ON s.turno_id = t.id
                             JOIN puntos p ON t.punto_id = p.id
                             WHERE s.usuario_id = ?");
      $stmt->execute([$usuario_id]);
    }
    echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
    break;

  // 📨 2. Crear solicitud (usuario común)
  case 'crear':
    $turno_id = (int) $_POST['turno_id'];
    $rol = $_POST['rol'] ?? 'publicador';

    // Verificar si ya existe una solicitud igual
    $check = $pdo->prepare("SELECT COUNT(*) FROM solicitudes WHERE usuario_id=? AND turno_id=?");
    $check->execute([$usuario_id, $turno_id]);
    if ($check->fetchColumn() > 0) {
      echo json_encode(['error' => 'Ya enviaste una solicitud para este turno']);
      exit;
    }

    $stmt = $pdo->prepare("INSERT INTO solicitudes (usuario_id, turno_id, rol) VALUES (?,?,?)");
    $stmt->execute([$usuario_id, $turno_id, $rol]);

    echo json_encode(['ok' => true, 'mensaje' => 'Solicitud enviada correctamente']);
    break;

  // ✅ 3. Aprobar solicitud (solo admin)
  case 'aprobar':
    if ($rol_usuario !== 'admin') {
      echo json_encode(['error' => 'Permiso denegado']);
      exit;
    }
    $id = (int) $_POST['id'];
    $stmt = $pdo->prepare("UPDATE solicitudes SET estado='aprobada' WHERE id=?");
    $stmt->execute([$id]);
    echo json_encode(['ok' => true]);
    break;

  // ❌ 4. Rechazar solicitud (solo admin)
  case 'rechazar':
    if ($rol_usuario !== 'admin') {
      echo json_encode(['error' => 'Permiso denegado']);
      exit;
    }
    $id = (int) $_POST['id'];
    $stmt = $pdo->prepare("UPDATE solicitudes SET estado='rechazada' WHERE id=?");
    $stmt->execute([$id]);
    echo json_encode(['ok' => true]);
    break;

  // 🗑️ 5. Eliminar solicitud (usuario)
  case 'eliminar':
    $id = (int) $_POST['id'];
    $stmt = $pdo->prepare("DELETE FROM solicitudes WHERE id=? AND usuario_id=?");
    $stmt->execute([$id, $usuario_id]);
    echo json_encode(['ok' => true]);
    break;

  default:
    echo json_encode(['error' => 'Acción no soportada']);
}
?>
