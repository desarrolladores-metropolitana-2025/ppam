<?php
// /application/calendario.php?p=ID
// session_start();
$p = isset($_GET['p']) ? intval($_GET['p']) : 1;
$nomb = isset($_GET['nomb']) ? $_GET['nomb'] : 'no hay punto en URL';
include_once(__DIR__ . "/../includes/app_layout.php");
?> 
<link rel="stylesheet" href="/css/app_turnos.css">
<div class="ppam-shell app-shell">
  <header class="app-header">
    <img src="/imagenes/logo_ppam.png" alt="PPAM" class="app-logo">
    <div class="app-title">PREDICACIÓN PÚBLICA<br><span>EN ÁREAS METROPOLITANAS</span></div>
  </header>

  <main class="app-main">
    <div class="cal-header">
     <!-- <a class="back-link" href="/application/turnos_index.php">← Volver</a> -->
	  
	   <!-- Botón Volver -->
    <a href="../application/turnos_index.php"
       style="display:inline-block; padding:8px 14px; border-radius:20px;
              background:linear-gradient(145deg,#ffffff,#d7d9e2);
              box-shadow:2px 2px 6px rgba(0,0,0,0.25), -2px -2px 6px #fff;
              text-decoration:none; font-weight:700; color:#333;">
      ← Volver
    </a>
	  
	  
      <h2 id="puntoName" class="section-title">Punto</h2>
    </div>

    <div class="calendar-card">
      <div class="calendar-controls">
        <button id="prevM" class="ctrl">◀</button>
        <div id="monthLabel" class="month-label">Mes</div>
        <button id="nextM" class="ctrl">▶</button>
      </div>
     
        <div id="calendarRoot" class="calendar"></div>
     	  
	 
<!-- 🔹 Leyenda de colores -->
<div class="calendar-legend">
  <div><span class="dot day-green"></span> Creado</div>
  <div><span class="dot day-purple"></span> Pendiente</div>
  <div><span class="dot day-yellow"></span> Abierto</div>
  <div><span class="dot day-mustard"></span> Asignado</div>
  <div><span class="dot day-red"></span>Planificado</div>
  <div><span class="dot day-blue"></span> Publicado</div>
  <div><span class="dot day-orange"></span>Completado</div>
  <div><span class="dot day-gray"></span> Cancelado</div>
  <div><span class="dot day-dark"></span> Otro</div>
</div>

	  
    </div>

    <div id="turnosContainer" class="turnos-panel card-hidden">
      <div class="turnos-header">
        <h3 id="turnosForLabel">Turnos</h3>
        <button id="closeTurnos" class="btn-small">Cerrar</button>
      </div>
      <div id="turnosList"></div>
    </div>
  </main>
</div>

<script src="../js/app_turnos.js" defer></script>
<script>
document.addEventListener('DOMContentLoaded', ()=>{
  AppTurnos.initCalendar(<?= $p ?>, "<?= $nomb ?>"  );
});
</script>

<?php include_once(__DIR__ . "/../includes/app_footer.php"); ?>
