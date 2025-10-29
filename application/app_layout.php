<?php
/* app_layout.php - Cabecera común para todas las pantallas - Sistema PPAM */
?>
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title><?= isset($title) ? htmlspecialchars($title) : "Turnos - Predicación" ?></title>

  <!-- CSS global -->
  <link rel="stylesheet" href="../css/comunes.css">
  <link rel="stylesheet" href="../css/sec_turnos.css">
  <link rel="stylesheet" href="/css/app_turnos.css">

  <!-- CSS específico de página -->
  <?php if (isset($extra_css)): ?>
    <link rel="stylesheet" href="<?= htmlspecialchars($extra_css) ?>">
  <?php endif; ?>

  <script>
    // pequeño helper global para mobile/desktop detecting (opcional)
    function isMobile() {
      return window.matchMedia("(max-width: 900px)").matches;
    }
  </script>
</head>
<body>
  <header class="ppam-topbar">
    <div class="ppam-topbar-inner">
      <div class="logo-wrap">
        <a href="https://metropoliplan.appwebterritorios.com"><img src="../imagenes/logo_ppam.png" alt="PPAM logo" class="ppam-logo"></a>
        <div class="ppam-title">
          <h2>PPAM</h2>&nbsp;&nbsp;&nbsp;<span>CABA</span>
        </div>
      </div>

      <div class="top-actions">
        <!-- Botón fijo grande (como en tus imágenes) -->
        <a href="../application/turnos_disponibles.php" class="btn-turno-fijo">Turno<br><span>Fijo</span></a>
      </div>
    </div>
  </header>

  <main class="ppam-main">
    <div class="ppam-shell">
      <!-- Aquí inyecta contenido de cada página -->
