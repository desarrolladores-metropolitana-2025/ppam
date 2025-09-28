<?php
// turnos_debug_protected.php (temporal - diagnóstico)
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

$page_title = 'Turnos - DEBUG';
ob_start();

// includear archivos **solo si existen**
$exp = __DIR__ . '/../exp_config.php';
$loadcfg = __DIR__ . '/../settings/cfgpanel/load_config.php';
$layout = __DIR__ . '/../turnos_layout.php';

echo "<h2>Turnos - DEBUG protegido</h2>";
if (file_exists($exp) && is_readable($exp)) {
    require_once $exp;
    echo "<p style='color:green'>incluido exp_config.php</p>";
} else {
    echo "<p style='color:red'>NO se incluyó exp_config.php - revisar ruta/permisos: $exp</p>";
}

// load_config (opcional)
if (file_exists($loadcfg) && is_readable($loadcfg)) {
    try { require_once $loadcfg; echo "<p style='color:green'>incluido load_config.php</p>"; }
    catch(Throwable $e) { echo "<p style='color:red'>Error load_config: " . htmlspecialchars($e->getMessage()) . "</p>"; }
} else {
    echo "<p style='color:orange'>No existe load_config.php (no crítico a menos que tu script dependa de \$GLOBALS['config'])</p>";
}

// Verificar $pdo
if (!isset($pdo) || !($pdo instanceof PDO)) {
    echo "<p style='color:red'>ATENCIÓN: \$pdo no está disponible. Si exp_config.php debería crear \$pdo, revisalo.</p>";
    // no continuamos a ejecutar queries que fallen
    $content = ob_get_clean();
    echo $content;
    exit;
}

// Query segura (no SELECT p.* con GROUP BY)
try {
    $sql = "
        SELECT 
            p.id,
            p.nombre,
            COALESCE(p.fecha, CURDATE()) AS fecha,
            COALESCE(p.minimo_publicadores,0) AS minimo_publicadores,
            COALESCE(p.maximo_publicadores,0) AS maximo_publicadores,
            COALESCE(p.idiomas_id, NULL) AS idiomas_id,
            COUNT(t.id) AS turnos_creados
        FROM puntos p
        LEFT JOIN turnos t ON t.punto_id = p.id AND (t.estado = 'pendiente' OR t.estado IS NULL)
        GROUP BY p.id, p.nombre, p.fecha, p.minimo_publicadores, p.maximo_publicadores, p.idiomas_id
        LIMIT 100
    ";
    $stmt = $pdo->query($sql);
    $puntos = $stmt->fetchAll(PDO::FETCH_ASSOC);
    echo "<p style='color:green'>Query ejecutada OK. Puntos obtenidos: " . count($puntos) . "</p>";
} catch (Throwable $e) {
    echo "<p style='color:red'>Error ejecutando la query: " . htmlspecialchars($e->getMessage()) . "</p>";
    $content = ob_get_clean();
    echo $content;
    exit;
}

// Mostrar algunos datos para inspección
foreach ($puntos as $punto) {
    echo "<div style='border:1px solid #ddd;padding:10px;margin:10px 0;'>";
    echo "<h4>" . htmlspecialchars($punto['nombre'] ?? 'N/A') . " (id: " . htmlspecialchars($punto['id']) . ")</h4>";
    echo "<ul>";
    echo "<li>fecha: " . htmlspecialchars($punto['fecha']) . "</li>";
    echo "<li>min: " . htmlspecialchars($punto['minimo_publicadores']) . "</li>";
    echo "<li>max: " . htmlspecialchars($punto['maximo_publicadores']) . "</li>";
    echo "<li>idiomas_id: " . htmlspecialchars($punto['idiomas_id']) . "</li>";
    echo "<li>turnos_creados: " . htmlspecialchars($punto['turnos_creados']) . "</li>";
    echo "</ul>";
    echo "</div>";
}

$content = ob_get_clean();
echo $content;
