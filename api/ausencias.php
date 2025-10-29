<?php
require_once __DIR__ . '/../includes/exp_config.php';

header('Content-Type: application/json');
$input = json_decode(file_get_contents('php://input'), true);

if (!$input || !isset($input['usuario_id'], $input['turno_id'], $input['motivo'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Parámetros inválidos']);
    exit;
}

$stmt = $pdo->prepare("
    INSERT INTO ausencias (usuario_id, turno_id, motivo, fecha_aviso)
    VALUES (?, ?, ?, NOW())
");
$stmt->execute([$input['usuario_id'], $input['turno_id'], $input['motivo']]);

echo json_encode(['status' => 'registrada']);
