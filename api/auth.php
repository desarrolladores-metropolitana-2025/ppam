<?php
// inicio común para todos los scripts de PPAM
session_save_path('/opt/alt/php73/var/lib/php/session');
// Esto debe ir antes de session_start()
session_set_cookie_params([
    'lifetime' => 0,  // sesión expira al cerrar navegador
    'path' => '/',
    'domain' => '.appwebterritorios.com', // <-- el punto inicial permite todos los subdominios
    'secure' => true,   // usa HTTPS
    'httponly' => true, // más seguro contra JS
    'samesite' => 'None' // necesario para compartir entre subdominios con HTTPS
]);

session_start();


// Si quieres, puedes hacer debug:
/*
if (!isset($_SESSION['user_id'])) {
    error_log("⚠️ No hay sesión activa en PPAM");
} else {
    error_log("✅ Sesión detectada desde PPAM: user_id=" . $_SESSION['user_id']);
}
*/
?>
