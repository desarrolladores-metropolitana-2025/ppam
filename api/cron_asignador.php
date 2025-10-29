<?php
// cron/cron_asignador.php
// Ejecutar por crontab. Usa services/BotAsignador_Hibrido.php
// Asegurarse de ajustar rutas a exp_config.php y a vendor/autoload.php (PHPMailer).

ini_set('display_errors', 1);
error_reporting(E_ALL);
date_default_timezone_set('America/Argentina/Buenos_Aires');

require_once __DIR__ . '/../includes/exp_config.php'; // debe setear $pdo
require_once __DIR__ . '/../services/BotAsignador_Hibrido.php';
require_once __DIR__ . '/../vendor/autoload.php'; // PHPMailer

use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

function cron_log($t) {
    $f = __DIR__ . '/../tmp/cron_asignador_log.txt';
    file_put_contents($f, "[".date('Y-m-d H:i:s')."] $t\n", FILE_APPEND);
}

// Instanciar bot
$bot = new BotAsignador_Hibrido($pdo);

// 1) Ejecutar reemplazos para turnos próximos con vacantes (opcional, comentar sino se necesita)
try {
    $daysAhead = 14;
    $stmt = $pdo->prepare("SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, t.punto_id, COALESCE(p.maximo_publicadores, t.maximo_publicadores, 3) AS maximo_publicadores FROM turnos t JOIN puntos p ON p.id = t.punto_id WHERE t.fecha BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL ? DAY)");
    $stmt->execute([$daysAhead]);
    $turnos = $stmt->fetchAll(PDO::FETCH_ASSOC);
    foreach ($turnos as $t) {
        $turnoId = (int)$t['id'];
        $c = $pdo->prepare("SELECT COUNT(*) FROM turno_participantes WHERE turno_id = ?");
        $c->execute([$turnoId]);
        $cnt = (int)$c->fetchColumn();
        $max = (int)$t['maximo_publicadores'];
        if ($cnt < $max) {
            cron_log("Turno $turnoId vacantes $cnt/$max -> intentando reemplazos");
            $res = $bot->asignarReemplazos($turnoId);
            cron_log("Resultado reemplazos turno $turnoId: ".json_encode($res));
        }
    }
} catch (Exception $e) {
    cron_log("Error reemplazos: ".$e->getMessage());
}

// 2) Procesar notificaciones pendientes
try {
    // AJUSTAR SMTP / gateway aquí o importarlos desde exp_config.php
    $smtpHost = 'smtp.hostinger.com';
    $smtpUser = 'metropolitana@ppam.appwebterritorios.com';
    $smtpPass = 'xxxxxxxx';
    $smtpPort = 465;

    $gupshupApiUrl = 'https://api.gupshup.io/wa/api/...'; // placeholder
    $gupshupApiKey = 'sk_xxxxx'; // placeholder

    $notifStmt = $pdo->prepare("SELECT n.*, u.email, u.phone, u.full_name FROM notificaciones n JOIN users u ON u.id = n.usuario_id WHERE n.estado = 'pending' ORDER BY n.id ASC LIMIT 200");
    $notifStmt->execute();
    $notifs = $notifStmt->fetchAll(PDO::FETCH_ASSOC);

    if (!$notifs) {
        cron_log("No hay notificaciones pendientes.");
    } else {
        cron_log("Procesando ".count($notifs)." notificaciones pendientes.");
    }

    foreach ($notifs as $n) {
        $id = (int)$n['id'];
        $ok = false;
        $errors = [];

        // Preparar datos
        $canal = $n['canal'] ?? 'ambos';
        $email = $n['email'] ?? null;
        $phone = $n['phone'] ?? null;
        $msg = $n['mensaje'];
        $payload = $n['payload'] ? json_decode($n['payload'], true) : null;

        // EMAIL
        if (($canal === 'email' || $canal === 'ambos') && !empty($email)) {
            try {
                $mail = new PHPMailer(true);
                $mail->isSMTP();
                $mail->Host = $smtpHost;
                $mail->SMTPAuth = true;
                $mail->Username = $smtpUser;
                $mail->Password = $smtpPass;
                $mail->SMTPSecure = PHPMailer::ENCRYPTION_SMTPS;
                $mail->Port = $smtpPort;
                $mail->CharSet = 'UTF-8';
                $mail->setFrom($smtpUser, 'PPAM');
                $mail->addAddress($email, $n['full_name'] ?? '');
                $mail->isHTML(false);
                $mail->Subject = 'Notificación PPAM';
                $mail->Body = $msg;
                $mail->send();
                $ok = true;
                cron_log("Email enviado notif $id -> $email");
            } catch (Exception $e) {
                $errors[] = "PHPMailer: ".$e->getMessage();
                cron_log("Error email notif $id: ".$e->getMessage());
            }
        }

        // PUSH/WHATSAPP (placeholder): intentar si canal es 'ambos' o 'whatsapp' y existe phone
        if ((!$ok && ($canal === 'whatsapp' || $canal === 'ambos')) && !empty($phone)) {
            try {
                // Ejemplo básico: POST a gateway (reemplazar con proveedor real)
                $post = [
                    'to' => $phone,
                    'message' => $msg,
                    'payload' => $payload,
                ];
                // Usar file_get_contents o cURL
                $opts = ['http' => [
                    'method'  => 'POST',
                    'header'  => "Content-Type: application/json\r\n" . "apikey: $gupshupApiKey\r\n",
                    'content' => json_encode($post),
                    'timeout' => 10
                ]];
                $context = stream_context_create($opts);
                $resp = @file_get_contents($gupshupApiUrl, false, $context);
                if ($resp === false) throw new Exception("Gateway error");
                $ok = true;
                cron_log("WhatsApp/Push enviado notif $id -> $phone resp: ".substr((string)$resp,0,250));
            } catch (Exception $e) {
                $errors[] = "Push/GW: ".$e->getMessage();
                cron_log("Error push notif $id: ".$e->getMessage());
            }
        }

        // Actualizar fila notificaciones: intentos++, estado, enviado, sent_at
        try {
            $pdo->beginTransaction();
            $upd = $pdo->prepare("UPDATE notificaciones SET intentos = intentos + 1, sent_at = CASE WHEN ? THEN NOW() ELSE sent_at END, enviado = CASE WHEN ? THEN 1 ELSE enviado END, estado = ?, updated_at = NOW() WHERE id = ?");
            $newEstado = $ok ? 'sent' : 'failed';
            $upd->execute([$ok, $ok, $newEstado, $id]);

            // Si falló y superó reintentos => marcar failed (política: si intentos >= 3)
            if (!$ok) {
                $chk = $pdo->prepare("SELECT intentos FROM notificaciones WHERE id = ?");
                $chk->execute([$id]);
                $intentos = (int)$chk->fetchColumn();
                if ($intentos >= 3) {
                    $pdo->prepare("UPDATE notificaciones SET estado='failed' WHERE id = ?")->execute([$id]);
                    cron_log("Notif $id marcado failed tras $intentos intentos");
                }
            }
            $pdo->commit();
        } catch (Exception $e) {
            try { $pdo->rollBack(); } catch (\Exception $ignored) {}
            cron_log("Error actualizando notificacion $id: ".$e->getMessage());
        }
    }

} catch (Exception $e) {
    cron_log("Error en procesamiento notificaciones: ".$e->getMessage());
}

echo json_encode(['ok'=>true,'msj'=>'cron ejecutado']);
exit;
