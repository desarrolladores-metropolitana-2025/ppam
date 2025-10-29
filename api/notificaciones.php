<?php
require_once __DIR__ . '/../includes/config.php';

header('Content-Type: application/json');

$input = json_decode(file_get_contents('php://input'), true);

if (!$input || !isset($input['usuario_id'], $input['mensaje'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Parámetros inválidos']);
    exit;
}

// Aquí se decide cómo enviar: email, WhatsApp API, etc.
// De momento guardamos en una tabla log_notificaciones.

$stmt = $pdo->prepare("
    INSERT INTO log_notificaciones (usuario_id, mensaje, enviado_en)
    VALUES (?, ?, NOW())
");
$stmt->execute([$input['usuario_id'], $input['mensaje']]);

echo json_encode(['status' => 'ok']);
