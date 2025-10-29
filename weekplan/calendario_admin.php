<?php
// Sistema PPAM 
// 17/10/2025
// calendario_admin.php - Crear turnos (vista calendario)
//require_once __DIR__ . '/../includes/auth.php';
//require_login();
?>
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Calendario de Turnos (Admin)</title>

  <link rel="stylesheet" href="../css/app_turnos.css">
  <link rel="stylesheet" href="../css/app_turnos_admin.css"> 
  <style>
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.5);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 2000;
    }
    .modal.open { display: flex; }
    .modal-content {
      background: #fff;
      border-radius: 12px;
      padding: 20px;
      max-width: 400px;
      width: 90%;
      box-shadow: 0 8px 20px rgba(0,0,0,0.25);
      animation: fadeIn .3s ease;
    }
    @keyframes fadeIn { from {opacity:0;transform:translateY(-10px);} to {opacity:1;transform:translateY(0);} }
    .modal h3 { margin-top:0; color:#0a3a5d; }
    .modal label { font-weight:600; display:block; margin-top:10px; }
    .modal input, .modal select {
      width:100%; padding:8px; margin-top:4px; border:1px solid #ccc;
      border-radius:6px; font-size:14px;
    }
    .modal button { margin-top:12px; padding:8px 14px; border:none; border-radius:8px; cursor:pointer; }
    .btn-primary { background:#1d76c6; color:white; }
    .btn-cancel { background:#ddd; color:#333; }
    .alert-warning { margin-top:8px; background:#fff3cd; color:#856404; padding:6px 8px; border-radius:6px; font-size:13px; }
  </style>
</head>
<body>

<div class="calendar-card">
  <div class="calendar-controls">
    <button id="prevM" class="ctrl">←</button>
    <div id="monthLabel" class="month-label">Mes</div>
    <button id="nextM" class="ctrl">→</button>
  </div>
  <div id="calendarRoot" class="calendar-root"></div>
</div>

<div class="calendar-legend">
  <div><span class="dot" style="background:#55c373"></span> Creado</div>
  <div><span class="dot" style="background:#f7dc6f"></span> Abierto</div>
  <div><span class="dot" style="background:#f4a261"></span> Otros</div>
</div>

<!-- Modal creación -->
<div id="modalCrearTurno" class="modal">
  <div class="modal-content">
    <h3>Crear turno</h3>
    <form id="formCrearTurno">
      <label>Fecha</label>
      <input type="date" id="fechaTurno" name="fecha" readonly>

      <label>Hora inicio</label>
      <input type="time" id="horaInicio" name="hora_inicio" required>

      <label>Hora fin</label>
      <input type="time" id="horaFin" name="hora_fin" required>

      <label>Punto</label>
      <select id="puntoSelect" name="punto_id" required></select>

      <div id="validacionInfo"></div>

      <div style="display:flex;justify-content:end;gap:8px;margin-top:12px;">
        <button type="button" class="btn-cancel" id="cerrarModal">Cancelar</button>
        <button type="submit" class="btn-primary">Crear turno</button>
      </div>
    </form>
  </div>
</div>

<script src="../js/app_turnos_admin.js"></script>
<script>
  document.addEventListener('DOMContentLoaded', () => {
    AppTurnosAdmin.initCalendar();
  });
</script>
</body>
</html>
