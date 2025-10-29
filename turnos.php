<?php
 ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../vendor/autoload.php';
require_once __DIR__ . '/../fsm/TurnosFSM.php'; 
require_once __DIR__ . '/../services/BotAsignador.php';
require_once __DIR__ . '/../entities/TurnoEntity.php';
require_once __DIR__ . '/../api/dispatcher.php'; // Dispatcher central
require_once __DIR__ . '/../includes/exp_config.php'; // $pdo

use Entities\TurnoEntity;
use FSM\TurnosFSM;   // si TurnosFSM.php también tiene namespace FSM
use Api\Dispatcher;  // si dispatcher.php tiene namespace Api


header('Content-Type: application/json');

$accion = $_GET['accion'] ?? null;

switch ($accion) {
   case 'listar':
    $params = [];
   $sql = "SELECT t.*, p.nombre AS punto 
            FROM turnos t
             JOIN puntos p ON t.punto_id = p.id";

    if (!empty($_GET['punto'])) {
        $sql .= " AND t.punto_id = :punto";
        $params[':punto'] = intval($_GET['punto']);
    }

    if (!empty($_GET['fecha'])) {
        $sql .= " AND t.fecha = :fecha";
        $params[':fecha'] = $_GET['fecha'];
    }

    $sql .= " ORDER BY t.fecha, t.hora_inicio";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
    break;
// *---------------------------------Listar por rango---------------------------------------*

case 'listar_por_rango':
    header("Content-Type: application/json; charset=utf-8");

    $params = [];
    $where = [];

    if (!empty($_GET['punto'])) {
        $where[] = "t.punto_id = :punto";
        $params[':punto'] = intval($_GET['punto']);
    }
    if (!empty($_GET['desde'])) {
        $where[] = "t.fecha >= :desde";
        $params[':desde'] = $_GET['desde'];
    }
    if (!empty($_GET['hasta'])) {
        $where[] = "t.fecha <= :hasta";
        $params[':hasta'] = $_GET['hasta'];
    }

    $sql = "SELECT t.fecha, t.estado, COUNT(*) AS cantidad
            FROM turnos t";

    if (count($where)) {
        $sql .= " WHERE " . implode(" AND ", $where);
    }

    $sql .= " GROUP BY t.fecha, t.estado ORDER BY t.fecha";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // Reorganizamos por fecha, con todos los estados presentes ese día
    $result = [];
    foreach ($rows as $r) {
        $fecha = $r['fecha'];
        if (!isset($result[$fecha])) {
            $result[$fecha] = [];
        }
        $result[$fecha][] = [
            'estado' => $r['estado'],
            'cantidad' => (int)$r['cantidad']
        ];
    }

    echo json_encode($result);
    break;

  
// *---------------------------------Detalle------------------------------------------------*
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
	case 'solicitar':
            // Usuario se solicita para un turno
            $turno_id = $_GET['id'] ?? null;
            
			if (isset($_SESSION['user_id']) && is_numeric($_SESSION['user_id'])) {
    $usuario_id = intval($_SESSION['user_id']);
} else {
    //  Para modo seguro:
   // http_response_code(401);
   // echo json_encode(['ok' => false, 'error' => 'Sesión no iniciada o inválida']);
   $usuario_id = 1; // TODO: aquí deberíamos tomar de sesión/login  
}
            $rol = $_POST['rol'] ?? 'publicador';
            if (!$turno_id) throw new Exception("Turno ID faltante");
			
			 // Verificar si ya existe una solicitud igual
    $check = $pdo->prepare("SELECT COUNT(*) FROM solicitudes WHERE usuario_id=? AND turno_id=?");
    $check->execute([$usuario_id, $turno_id]);
   
    // $lineadb = $check->fetch(PDO::FETCH_ASSOC);
	   $lineadb = $check->fetchColumn();

   if ($lineadb > 0) {
      echo json_encode(['error' => 'Ya enviaste una solicitud para este turno']);
      exit;
    } 
	
	// Verificar la fecha de turnos que no sea anterior a hoy...
	
	    $stmt = $pdo->prepare("SELECT * FROM turnos WHERE id = ?");
        $stmt->execute([$turno_id]);
        $lineaTurno = $stmt->fetch(PDO::FETCH_ASSOC);
		
		if (!$lineaTurno) {
    // No se encontró el turno con ese ID
    echo json_encode(['error' => 'Turno no encontrado']);
    exit;
     }
		
		$fecha_turno = $lineaTurno['fecha'];
        $hora_turno = $lineaTurno['hora_inicio'];
		try {
    $fecha_hora_turno = new DateTime($fecha_turno . ' ' . $hora_turno);
        } catch (Exception $e) {
    // Manejar el error si el formato es inválido
    // die("Error al crear el objeto DateTime: " . $e->getMessage());
	echo json_encode(['error' => 'Error al crear objeto de fecha' ]);
	exit;
}
        $fecha_hora_actual = new DateTime();
		$fecha_hoy = $fecha_hora_actual->format('Y-m-d H:i:s');

	    if ($fecha_hora_turno < $fecha_hora_actual) {
    // La fecha y hora de del turno es anterior a la fecha y hora actual
    // echo "El registro es anterior a hoy (" . $fecha_hora_db->format('Y-m-d H:i:s') . ").";
	     echo json_encode(['error' => 'El turno es anterior a hoy (' . $fecha_hora_turno->format('d-m-Y H:i')  . ').' ]);
		 //  echo json_encode(['error' => 'El turno es anterior a hoy ' ]);
        exit;
        }
	

            $stmt = $pdo->prepare("INSERT INTO solicitudes (usuario_id, turno_id, rol, estado, processed_by, processed_at)
                                   VALUES (?, ?, ?, 'pendiente', ?, ?)");
            $stmt->execute([$usuario_id, $turno_id, $rol, $usuario_id, $fecha_hoy ]);
            $response = ['status' => 'ok', 'message' => 'Solicitud registrada'];
			echo json_encode(['success' => 'Solicitud enviada correctamente' ]);
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
	 case 'abrir':
	 $id = (int) $_POST['turno_id'];
	 $stmt = $pdo->prepare("UPDATE turnos SET estado=? WHERE id=?");
	 $stmt->execute(['abierto', $id]);
	 echo json_encode(['ok' => true]);
	 echo json_encode(['success' => 'Turno abierto']);
     break;		

   case 'planificar':
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
            
            // 🔹 Actualizar estado del turno
            $pdo->prepare("UPDATE turnos SET estado=? WHERE id=?")
                ->execute([$fsm->getState(), $id]);

            // 🔹 Disparar evento → Bot + Notificaciones
            $resp = Api\Dispatcher::dispatch('turno.planificado', $turnoData);

            // 🔹 Guardar log completo del Bot en /tmp (para diagnóstico o pipeline)
            $timestamp = date('Ymd_His');
            $pipelineFile = __DIR__ . "/../tmp/bot_pipeline_{$timestamp}.txt";
            if (!empty($resp['pipeline_ascii'])) {
    file_put_contents($pipelineFile, $resp['pipeline_ascii']); // guarda el contenido real
    $resp['pipeline_url'] = "/tmp/" . basename($pipelineFile);
} elseif (!empty($resp['pipeline_file'])) {
    // fallback: si solo vino ruta, intentar copiarla o exponerla
    $resp['pipeline_url'] = "/tmp/" . basename($resp['pipeline_file']);
}
            // 🔹 Registrar respuesta completa en JSON para auditoría
            file_put_contents(__DIR__ . '/../tmp/bot_log.json', json_encode($resp, JSON_PRETTY_PRINT));
			if (!empty($resp['pipeline_file']) && file_exists($resp['pipeline_file'])) {
			$resp['pipeline_text'] = file_get_contents($resp['pipeline_file']);
			}


            // 🔹 Responder al frontend
            echo json_encode([
                'ok' => true,
                'estado' => $fsm->getState(),
                'pipeline_url' => $resp['pipeline_url'] ?? null,
				'pipeline_text' => $resp['pipeline_text'] ?? null,
                'log_file' => '/tmp/bot_log.json'
            ]);
        } else {
            echo json_encode(['error' => 'No se puede planificar en el estado actual']);
        }
    } catch (Exception $e) {
        echo json_encode(['error' => $e->getMessage()]);
    }
    break;
		
		case 'editar':
    $id          = (int)($_GET['id'] ?? 0);
    $fecha       = $_POST['fecha'] ?? null;
    $hora_inicio = $_POST['hora_inicio'] ?? null;
    $hora_fin    = $_POST['hora_fin'] ?? null;
    $punto_id    = (int)($_POST['punto_id'] ?? 0);

    if (!$id || !$fecha || !$hora_inicio || !$hora_fin || !$punto_id) {
        echo json_encode(['error' => 'Faltan datos']);
        exit;
    }

    $stmt = $pdo->prepare("UPDATE turnos 
                           SET fecha=?, hora_inicio=?, hora_fin=?, punto_id=? 
                           WHERE id=?");
    $stmt->execute([$fecha, $hora_inicio, $hora_fin, $punto_id, $id]);

    echo json_encode(['ok' => true]);
    break;
    
	case 'asignar_auto':
    
    $bot = new BotAsignador($pdo);

    try {
        // Ejecutar el bot en modo batch (por ejemplo próximos 30 días)
        $resultado = $bot->runBatch(['daysAhead' => 30]);
        echo json_encode([
            'ok' => true,
            'procesados' => $resultado['processed'],
            'log' => $resultado['log'],
            'pipeline_file' => $bot->pipelineFilename ?? null,
        ]);
    } catch (Exception $e) {
        echo json_encode([
            'ok' => false,
            'error' => $e->getMessage(),
        ]);
    }
    break;

    case 'cancelar':
	       echo json_encode([
  'debug' => 'ENTRO',
  'ok' => true
]);
	   
        $id = (int) $_POST['turno_id'];
		
        if ($id <= 0) {
            echo json_encode(['error' => 'turno_id no recibido']);
            exit;
        }
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
                ->execute([$fsm->getState(), $id]);

            // Disparar evento
            \Api\Dispatcher::dispatch('turno.cancelado', $turnoData);

            echo json_encode(['ok' => true, 'estado' => $fsm->getState()]);
        } else {
            echo json_encode(['error' => 'No se puede cancelar este turno']);
        }
        break;


    default:
        echo json_encode(['error' => 'Acción no soportada']);
}
