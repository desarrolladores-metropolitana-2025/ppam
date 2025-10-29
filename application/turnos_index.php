<?php
// /application/turnos_index.php
require_once __DIR__ . '/../includes/auth.php';
include_once(__DIR__ . "/../includes/app_layout.php"); // diferente layout por si queremos diferenciar...
?>

<div class="ppam-shell app-shell">
  <header class="app-header">
    <a href="https://metropoliplan.appwebterritorios.com"><img src="/imagenes/logo_ppam.png" alt="PPAM" class="app-logo"></a>
    <div class="app-title">PREDICACIÓN PÚBLICA<br><span>EN ÁREAS METROPOLITANAS</span></div>
  </header>

  <main class="app-main">
    <h2 class="section-title">Seleccionar Punto</h2>
    <div id="puntosGrid" class="puntos-grid">
      <!-- puntos cargados por JS -->
      <div class="loader">Cargando puntos...</div>
    </div>
  </main>
</div>

<script src="../js/app_turnos.js" defer></script>
<script>
  // inicializa al cargar
  document.addEventListener('DOMContentLoaded', ()=> {
    AppTurnos.loadPuntos();
  });
</script>
<?php include_once(__DIR__ . "/../includes/app_footer.php"); ?>
