<?php
// turnos.php - API skeleton
require_once "db.php";
require_once "fsm.php"; // contiene validarTurnoAntesDePlanificar()

header('Content-Type: application/json');

$pdo = getPDO();
$action = $_GET['action'] ?? '';
$turno_id = intval($_GET['turno_id'] ?? 0);

switch ($action) {
    case 'abrir':
        updateEstado($pdo, $turno_id, 'ABIERTO');
        echo json_encode(["ok"=>true,"estado"=>"ABIERTO"]);
        break;

    case 'planificar':
        $issues = validarTurnoAntesDePlanificar($pdo, $turno_id);
        $hasError = array_filter($issues, fn($i)=>$i['level']=='error');
        if (!empty($hasError)) {
            echo json_encode(["ok"=>false,"estado"=>"ERROR_VALIDACION","issues"=>$issues]);
            exit;
        }
        updateEstado($pdo, $turno_id, 'PLANIFICADO');
        echo json_encode(["ok"=>true,"estado"=>"PLANIFICADO","issues"=>$issues]);
        break;

    case 'publicar':
        if (!estadoActualEs($pdo, $turno_id, 'PLANIFICADO')) {
            echo json_encode(["ok"=>false,"msg"=>"Solo se puede publicar desde PLANIFICADO"]);
            exit;
        }
        updateEstado($pdo, $turno_id, 'PUBLICADO');
        echo json_encode(["ok"=>true,"estado"=>"PUBLICADO"]);
        break;

    case 'cancelar':
        updateEstado($pdo, $turno_id, 'CANCELADO');
        echo json_encode(["ok"=>true,"estado"=>"CANCELADO"]);
        break;

    case 'finalizar':
        if (!estadoActualEs($pdo, $turno_id, 'PUBLICADO')) {
            echo json_encode(["ok"=>false,"msg"=>"Solo se puede finalizar desde PUBLICADO"]);
            exit;
        }
        updateEstado($pdo, $turno_id, 'COMPLETADO');
        echo json_encode(["ok"=>true,"estado"=>"COMPLETADO"]);
        break;

    default:
        echo json_encode(["ok"=>false,"msg"=>"Accion no valida"]);
}

function updateEstado(PDO $pdo, int $turno_id, string $estado) {
    $stmt = $pdo->prepare("UPDATE turnos SET estado=? WHERE id=?");
    $stmt->execute([$estado, $turno_id]);
}
function estadoActualEs(PDO $pdo, int $turno_id, string $estado): bool {
    $stmt = $pdo->prepare("SELECT estado FROM turnos WHERE id=?");
    $stmt->execute([$turno_id]);
    return $stmt->fetchColumn() === $estado;
}
