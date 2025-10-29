case 'asignar_manual':
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
  break;
