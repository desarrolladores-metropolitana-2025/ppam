<?php
// api/load_config_json.php
require_once __DIR__ . '/../includes/exp_config.php'; // conexión PDO existente

function load_configurations(PDO $pdo) {
    $stmt = $pdo->query("SELECT id, seccion, clave, valor, tipo FROM configuraciones ORDER BY seccion, clave");
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $config = [];
    foreach ($rows as $row) {
        $valor = $row['valor'];
        switch ($row['tipo']) {
            case 'bool':
                $valor = (bool)$valor;
                break;
            case 'number':
                $valor = is_numeric($valor) ? (float)$valor : 0;
                break;
        }
        $config[] = [
            'id'       => (int)$row['id'],
            'seccion'  => $row['seccion'],
            'clave'    => $row['clave'],
            'valor'    => $valor,
            'tipo'     => $row['tipo']
        ];
    }
    return $config;
}

// → salida JSON limpia
header('Content-Type: application/json; charset=utf-8');
try {
    $data = load_configurations($pdo);
    echo json_encode(['ok' => true, 'configuraciones' => $data], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => $e->getMessage()]);
}
// Guardar en $GLOBALS
$GLOBALS['config'] = $data;