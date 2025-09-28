<?php
ini_set('display_errors', 1);
error_reporting(E_ALL);

require_once __DIR__ . '/../exp_config.php';
require_once __DIR__ . '/validaciones_turnos.php';

// 1) Obtener todos los turnos
$stmt = $pdo->query("
    SELECT t.id, t.fecha, t.hora_inicio, t.hora_fin, p.nombre as punto
    FROM turnos t
    JOIN puntos p ON t.punto_id = p.id
    ORDER BY t.fecha, t.hora_inicio
");
$turnos = $stmt->fetchAll(PDO::FETCH_ASSOC);

$page_title = "Test de Validaciones de Turnos";
ob_start();
?>

<h2>Validaciones de Turnos</h2>

<?php if (!$turnos): ?>
  <p><em>No hay turnos en la base de datos.</em></p>
<?php else: ?>
  <table class="report-table" border="1" cellpadding="5" cellspacing="0" style="width:100%; border-collapse:collapse;">
    <thead>
      <tr style="background:#f0f0f0;">
        <th>ID</th>
        <th>Fecha</th>
        <th>Hora</th>
        <th>Punto</th>
        <th>Problemas</th>
      </tr>
    </thead>
    <tbody>
      <?php foreach ($turnos as $t): ?>
        <?php 
          $problemas = validarTurnoAntesDePlanificar($pdo, (int)$t['id']); 
        ?>
        <tr>
          <td><?= $t['id'] ?></td>
          <td><?= htmlspecialchars($t['fecha']) ?></td>
          <td><?= htmlspecialchars($t['hora_inicio'] . ' - ' . $t['hora_fin']) ?></td>
          <td><?= htmlspecialchars($t['punto']) ?></td>
          <td>
            <?php if (!$problemas): ?>
              <span style="color:green;">✓ Sin problemas</span>
            <?php else: ?>
              <ul style="margin:0; padding-left:15px;">
                <?php foreach ($problemas as $p): ?>
                  <li>
                    <strong>[<?= $p['nivel'] ?>]</strong>
                    <?= htmlspecialchars($p['descripcion']) ?>
                  </li>
                <?php endforeach; ?>
              </ul>
            <?php endif; ?>
          </td>
        </tr>
      <?php endforeach; ?>
    </tbody>
  </table>
<?php endif; ?>

<?php
$content = ob_get_clean();
include __DIR__ . '/../config_layout.php';
