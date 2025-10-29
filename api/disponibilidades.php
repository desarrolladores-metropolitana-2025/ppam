<?php
require_once __DIR__ . '/../includes/config.php';

header('Content-Type: application/json');
$input = json_decode(file_get_contents('php://input'), true);

if (!$input || !isset($input['usuario_id'], $input['dia_semana'], $input['hora_inicio'], $input['hora_fin'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Parámetros inválidos']);
    exit;
}

$stmt = $pdo->prepare("
    INSERT INTO disponibilidades (usuario_id, dia_semana, hora_inicio, hora_fin, frecuencia, cada)
    VALUES (?, ?, ?, ?, ?, ?)
");
$stmt->execute([
    $input['usuario_id'],
    $input['dia_semana'],
    $input['hora_inicio'],
    $input['hora_fin'],
    $input['frecuencia'] ?? 'semanal',
    $input['cada'] ?? 1
]);

echo json_encode(['status' => 'registrada']);
