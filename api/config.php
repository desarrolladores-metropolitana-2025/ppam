<?php
require_once __DIR__ . '/../fsm/vendor/autoload.php';

$dsn = "mysql:host=localhost;dbname=u962788881_Metropoliplan;charset=utf8mb4";
$user = "u962788881_metropolitana";
$pass = "Beto.2058yut";

try {
    $pdo = new PDO($dsn, $user, $pass, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC
    ]);
} catch (PDOException $e) {
    http_response_code(500);
    echo json_encode(["error" => "DB connection failed", "details" => $e->getMessage()]);
    exit;
}
