<?php
// config.php — conexión PDO
$DB_HOST = getenv('DB_HOST') ?: 'localhost';
$DB_NAME = getenv('DB_NAME') ?: 'u962788881_Metropoliplan';
$DB_USER = getenv('DB_USER') ?: 'u962788881_metropolitana';
$DB_PASS = getenv('DB_PASS') ?: 'Beto.2058yut';
$DB_CHARSET = 'utf8mb4';

$dsn = "mysql:host=$DB_HOST;dbname=$DB_NAME;charset=$DB_CHARSET";
$options = [
  PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
  PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
  PDO::ATTR_EMULATE_PREPARES => false,
];

try {
  $pdo = new PDO($dsn, $DB_USER, $DB_PASS, $options);
} catch (Throwable $e) {
  http_response_code(500);
  echo "Error de conexión a la base de datos.";
  exit;
}
?>
