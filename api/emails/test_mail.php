<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

echo "<pre>Probando carga de PHPMailer...\n";

require __DIR__ . '/vendor/autoload.php'; // ajusta ruta si está en otra carpeta

use PHPMailer\PHPMailer\PHPMailer;
use PHPMailer\PHPMailer\Exception;

try {
    $mail = new PHPMailer(true);
    echo "✔ PHPMailer cargado correctamente\n";

    // --- Test sin envío ---
    $mail->isSMTP();
    $mail->Host = 'smtp.hostinger.com';
    $mail->SMTPAuth = true;
    $mail->Username = 'metropolitana@ppam.appwebterritorios.com';
    $mail->Password = 'DesarrolloPPAM.2026';
    $mail->SMTPSecure = PHPMailer::ENCRYPTION_SMTPS; // o 'ssl'
    $mail->Port = 465;
    $mail->SMTPDebug = 2; // ver detalle

    $mail->setFrom('metropolitana@ppam.appwebterritorios.com', 'Test PHPMailer');
    $mail->addAddress('avillafane@fi.uba.ar');
    $mail->Subject = 'Prueba PHPMailer desde PPAM';
    $mail->Body    = 'Si recibes esto, el servidor puede enviar correos.';

    echo "\nIntentando conectar al servidor SMTP...\n";
    $mail->send();
    echo "\n✅ Correo enviado correctamente.\n";
} catch (Exception $e) {
    echo "\n❌ Error detectado:\n";
    echo $mail->ErrorInfo;
    echo "\n---\n";
    echo $e->getMessage();
}
