<?php
require_once __DIR__ . '/../vendor/autoload.php';
require_once __DIR__ . '/../fsm/TurnosFSM.php'; 
require_once __DIR__ . '/../services/BotAsignador.php';
require_once __DIR__ . '/../entities/TurnoEntity.php';
require_once __DIR__ . '/../api/dispatcher.php'; // Dispatcher central
require_once __DIR__ . '/../includes/exp_config.php'; // $pdo

header('Content-Type: application/json');

$accion = $_GET['accion'] ?? null;

switch ($accion) {
    case 'listar':
         $sql = "SELECT t.*, p.nombre AS punto 
            FROM turnos t
             JOIN puntos p ON t.punto_id = p.id
            ORDER BY t.fecha, t.hora_inicio";
    $stmt = $pdo->query($sql);
    echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));    
    break;

    case 'detalle':
        $id = (int) $_GET['id'];
        $stmt = $pdo->prepare("SELECT * FROM turnos WHERE id = ?");
        $stmt->execute([$id]);
        echo json_encode($stmt->fetch(PDO::FETCH_ASSOC));
        break;

    case 'crear':
    $fecha       = $_POST['fecha'] ?? null;
    $hora_inicio = $_POST['hora_inicio'] ?? null;
    $hora_fin    = $_POST['hora_fin'] ?? null;
    $punto_id    = (int) ($_POST['punto_id'] ?? 0);

    if (!$fecha || !$hora_inicio || !$hora_fin || !$punto_id) {
        echo json_encode(['error' => 'Faltan datos']);
        exit;
    }

    $stmt = $pdo->prepare("INSERT INTO turnos (fecha, hora_inicio, hora_fin, punto_id, estado) 
                           VALUES (?, ?, ?, ?, 'pendiente')");
    $stmt->execute([$fecha, $hora_inicio, $hora_fin, $punto_id]);

    echo json_encode(['ok' => true, 'id' => $pdo->lastInsertId()]);
    break;

    case 'modificar':
        $id   = (int) $_POST['turno_id'];
        $data = json_decode(file_get_contents('php://input'), true);

        $stmt = $pdo->prepare("
            UPDATE turnos
            SET fecha = ?, hora_inicio = ?, hora_fin = ?, punto_id = ?, tipo = ?
            WHERE id = ?
        ");
        $stmt->execute([
            $data['fecha'],
            $data['hora_inicio'],
            $data['hora_fin'],
            $data['punto_id'],
            $data['tipo'] ?? 'fijo',
            $id
        ]);
        echo json_encode(['ok' => true]);
        break;

    case 'eliminar':
        $id = (int) $_POST['turno_id'];
        $pdo->prepare("DELETE FROM turnos WHERE id = ?")->execute([$id]);
        echo json_encode(['ok' => true]);
        break;

    case 'asignar':
        $id = (int) $_POST['turno_id'];
        $stmt = $pdo->prepare("SELECT * FROM turnos WHERE id = ?");
        $stmt->execute([$id]);
        $turnoData = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$turnoData) {
            echo json_encode(['error' => 'Turno no encontrado']);
            exit;
        }

        $turno = new TurnoEntity($turnoData);
        $fsm   = new TurnosFSM($turno);

        try {
            if ($fsm->can('planificar')) {
                $fsm->apply('planificar');
                // Actualizar BD
                $pdo->prepare("UPDATE turnos SET estado=? WHERE id=?")
                    ->execute([$fsm->getCurrentState(), $id]);

                // Disparar evento → Bot + Notificaciones
                \Api\Dispatcher::dispatch('turno.planificado', $turnoData);

                echo json_encode(['ok' => true, 'estado' => $fsm->getCurrentState()]);
            } else {
                echo json_encode(['error' => 'No se puede planificar en el estado actual']);
            }
        } catch (Exception $e) {
            echo json_encode(['error' => $e->getMessage()]);
        }
        break;

    case 'cancelar':
        $id = (int) $_POST['turno_id'];
        $stmt = $pdo->prepare("SELECT * FROM turnos WHERE id = ?");
        $stmt->execute([$id]);
        $turnoData = $stmt->fetch(PDO::FETCH_ASSOC);

        if (!$turnoData) {
            echo json_encode(['error' => 'Turno no encontrado']);
            exit;
        }

        $turno = new TurnoEntity($turnoData);
        $fsm   = new TurnosFSM($turno);

        if ($fsm->can('cancelar')) {
            $fsm->apply('cancelar');
            $pdo->prepare("UPDATE turnos SET estado=? WHERE id=?")
                ->execute([$fsm->getCurrentState(), $id]);

            // Disparar evento
            \Api\Dispatcher::dispatch('turno.cancelado', $turnoData);

            echo json_encode(['ok' => true, 'estado' => $fsm->getCurrentState()]);
        } else {
            echo json_encode(['error' => 'No se puede cancelar este turno']);
        }
        break;

    default:
        echo json_encode(['error' => 'Acción no soportada']);
}
