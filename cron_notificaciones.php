<?php
// cron/cron.php
// Ejecutar por crontab cada X minutos
// Requiere: includes/exp_config.php que provea $pdo y vendor/autoload.php para PHPMailer si lo usas.
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);
ob_start(); // ðŸ‘ˆ Comienza el buffer para capturar todo output

require_once __DIR__ . '/vendor/autoload.php';
require_once __DIR__ . '/../includes/exp_config.php';
require_once __DIR__ . '/../services/BotAsignador.php';

use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

date_default_timezone_set('America/Argentina/Buenos_Aires');

function cron_log($t) {
    $f = __DIR__ . '/../tmp/cron_log.txt';
    file_put_contents($f, "[".date('Y-m-d H:i:s')."] $t\n", FILE_APPEND);
//	echo json_encode(['ok' => true, 'msj' => $t ]);
}

$bot = new BotAsignador($pdo);

// --- 1) Procesar notificaciones pendientes ---
$notifStmt = $pdo->prepare("SELECT n.*, u.email, u.phone FROM notificaciones n JOIN users u ON u.id = n.usuario_id WHERE n.enviado = 0 ORDER BY n.id ASC LIMIT 200");
$notifStmt->execute();
$notifs = $notifStmt->fetchAll(PDO::FETCH_ASSOC);

if (!$notifs) {
    cron_log("No hay notificaciones pendientes.");
} else {
    cron_log("Procesando ".count($notifs)." notificaciones pendientes.");
}

// ConfiguraciÃ³n de envÃ­o (ajustar)
$smtpHost = 'smtp.hostinger.com';
$smtpUser = 'metropolitana@ppam.appwebterritorios.com';
$smtpPass = 'DesarrolloPPAM.2026';
$smtpPort = 465;
$waGatewayUrl = 'https://api.tu_whatsapp_gateway.com/send'; // placeholder (requiere proveedor real)
// 'https://api.gupshup.io/sm/api/v1/msg';
$apiUrl = 'https://api.gupshup.io/wa/api/metropoliplan/msg';
$appname = 'metropoliplan'; // nombre de tu app en Gupshup
$apikey = 'sk_a7da3e9644a24c489250e311df32ebc2';

foreach ($notifs as $n) {
    $ok = false;
    $error = null;

    // Priorizar el canal guardado en n['canal'] (ambos/email/whatsapp)
    $canal = $n['canal'] ?? 'ambos';
    $email = $n['email'] ?? null;
    $phone = $n['phone'] ?? null;
    $msg = $n['mensaje'];

   
    // 1) Email con PHPMailer
    if (($canal === 'email' || $canal === 'ambos') && !empty($email)) {
        try {
            $mail = new PHPMailer(true);
            $mail->isSMTP();
            $mail->Host = $smtpHost;
            $mail->SMTPAuth = true;
            $mail->Username = $smtpUser;
            $mail->Password = $smtpPass;
            $mail->SMTPSecure = PHPMailer::ENCRYPTION_SMTPS; // o 'ssl'
            $mail->Port = $smtpPort;
			$mail->CharSet = 'UTF-8';
			$mail->Encoding = 'base64';
			$mail->SMTPDebug = 2;
            $mail->setFrom($smtpUser, 'PPAM');
            $mail->addAddress($email);
            $mail->isHTML(false);
            $mail->Subject = 'NotificaciÃ³n PPAM';
            $mail->Body = $msg;
            $mail->send();
            $ok = true;
            cron_log("Email enviado a $email (notif {$n['id']})");
        } catch (Exception $e) {
            $error = "PHPMailer error: ".$e->getMessage();
            cron_log($error);
        }
    }
 
    // 2) WhatsApp (gateway HTTP) - placeholder: adaptar al proveedor elegido (Twilio, Gupshup, etc.)
   // 2) WhatsApp con Gupshup API
if (($canal === 'whatsapp' || $canal === 'ambos') && !empty($phone)) {
    try {
       
        $data = [
            'channel' => 'whatsapp',
            'source' => 'whatsapp:+917834811114', // n¨²mero asignado por Gupshup
            'destination' => "whatsapp:+{$phone}",
            'message' => json_encode(['type' => 'text', 'text' => $msg]),
        ];

        $options = [
            'http' => [
                'header'  => [
                    "Content-Type: application/x-www-form-urlencoded",
                    "apikey: $apikey",
                ],
                'method'  => 'POST',
                'content' => http_build_query($data),
                'timeout' => 15,
            ]
        ];

        $context = stream_context_create($options);
        $resp = @file_get_contents($apiUrl, false, $context);

        if ($resp === false) {
            $err = error_get_last();
            throw new Exception("Error Gupshup: " . ($err['message'] ?? 'unknown'));
        }

        $ok = true;
        cron_log("WhatsApp Gupshup enviado a $phone (notif {$n['id']}) resp: $resp");
    } catch (Exception $e) {
        $error = "Gupshup error: " . $e->getMessage();
        cron_log($error);
    }
  }
}

// --- 2) Buscar turnos con vacantes (turnos recientes o proximos) y lanzar reemplazos ---
cron_log("Buscando turnos con vacantes para intentar reemplazos automaticos.");

// criterios: turnos en los proximos X di­as (ajustar), con participantes < maximo
$daysAhead = 14;
$stmt = $pdo->prepare("
    SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.punto_id, p.maximo_publicadores
    FROM turnos t
    JOIN puntos p ON p.id = t.punto_id
    WHERE t.fecha BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL ? DAY)
");
$stmt->execute([$daysAhead]);
$turnos = $stmt->fetchAll(PDO::FETCH_ASSOC);

foreach ($turnos as $t) {
    $turnoId = (int)$t['id'];
    // contar participantes
    $c = $pdo->prepare("SELECT COUNT(*) FROM turno_participantes WHERE turno_id = ?");
    $c->execute([$turnoId]);
    $cnt = (int)$c->fetchColumn();
    $max = (int)($t['maximo_publicadores'] ?? 3);
    if ($cnt < $max) {
        cron_log("Turno $turnoId tiene vacantes $cnt/$max -> intentando reemplazos");
        $res = $bot->asignarReemplazos($turnoId);
        cron_log("Resultado reemplazos turno $turnoId: ".json_encode($res));
    }
}
// cron_log("proceso de notificaciones terminado.");
$output = trim(ob_get_clean()); // captura cualquier salida anterior
if ($output !== '') {
    file_put_contents( __DIR__ . '/../tmp/cron_log.txt', $output,  FILE_APPEND);
}
echo json_encode(['ok' => true, 'msj' => 'Proceso de notificaciones completado.']);
exit;
