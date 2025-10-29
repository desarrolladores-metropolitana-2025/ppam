<?php
require_once __DIR__ . '/../vendor/autoload.php';
require_once __DIR__ . '/../includes/exp_config.php'; // $pdo conectado

header('Content-Type: application/json');

$accion = $_GET['accion'] ?? null;

switch ($accion) {
    case 'listar':
        $stmt = $pdo->query("SELECT id, nombre, lugar_encuentro FROM puntos ORDER BY nombre");
        $puntos = $stmt->fetchAll(PDO::FETCH_ASSOC);
        echo json_encode($puntos);
        break;

    case 'detalle':
        $id = (int) $_GET['id'];
        $stmt = $pdo->prepare("SELECT * FROM puntos WHERE id=?");
        $stmt->execute([$id]);
        echo json_encode($stmt->fetch(PDO::FETCH_ASSOC));
        break;

    case 'crear':
        $nombre = $_POST['nombre'] ?? null;
        $lugar = $_POST['lugar_encuentro'] ?? null;

        if (!$nombre) {
            echo json_encode(['error' => 'Nombre del punto requerido']);
            exit;
        }

        $stmt = $pdo->prepare("INSERT INTO puntos (nombre, lugar_encuentro) VALUES (?, ?)");
        $ok = $stmt->execute([$nombre, $lugar]);

        echo json_encode(['ok' => $ok, 'id' => $pdo->lastInsertId()]);
        break;

    case 'modificar':
        $id     = (int) $_POST['id'];
        $nombre = $_POST['nombre'] ?? null;
        $lugar  = $_POST['lugar_encuentro'] ?? null;

        if (!$id || !$nombre) {
            echo json_encode(['error' => 'Datos incompletos']);
            exit;
        }

        $stmt = $pdo->prepare("UPDATE puntos SET nombre=?, lugar_encuentro=? WHERE id=?");
        $ok   = $stmt->execute([$nombre, $lugar, $id]);

        echo json_encode(['ok' => $ok]);
        break;

    case 'eliminar':
        $id = (int) $_POST['id'];
        if (!$id) {
            echo json_encode(['error' => 'ID inválido']);
            exit;
        }

        $stmt = $pdo->prepare("DELETE FROM puntos WHERE id=?");
        $ok   = $stmt->execute([$id]);

        echo json_encode(['ok' => $ok]);
        break;

    default:
        echo json_encode(['error' => 'Acción no soportada']);
}
