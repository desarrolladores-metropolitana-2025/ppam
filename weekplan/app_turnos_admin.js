// app_turnos_admin.js — Sistema PPAM (Administrador) — Creación de turnos desde calendario
const AppTurnosAdmin = (() => {
  const apiBase = "../api/turnos_admin.php";
  const modal = document.getElementById("modalCrearTurno");
  const form = document.getElementById("formCrearTurno");
  const selectPunto = document.getElementById("puntoSelect");
  const validacionInfo = document.getElementById("validacionInfo");

  let currentMonth = (new Date()).getMonth();
  let currentYear = (new Date()).getFullYear();

  async function fetchJSON(url, options = {}) {
    const r = await fetch(url, options);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  // --- render calendario ---
  async function render() {
    const calendar = document.getElementById("calendarRoot");
    const monthLabel = document.getElementById("monthLabel");
    const months = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Sept.","Oct.","Nov.","Dic."];

    monthLabel.textContent = `${months[currentMonth]} ${currentYear}`;
    calendar.innerHTML = '';

    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const totalDays = lastDay.getDate();
    const start = firstDay.getDay();

    // días vacíos
    for (let i = 0; i < start; i++) {
      const empty = document.createElement("div");
      empty.className = "day day-empty";
      calendar.appendChild(empty);
    }

    // obtener turnos del mes
    let turnos = {};
    try {
      const desde = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-01`;
      const hasta = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-31`;
      turnos = await fetchJSON(`${apiBase}?accion=listar_por_rango&desde=${desde}&hasta=${hasta}`);
    } catch(e){ console.warn(e); }

    for (let d = 1; d <= totalDays; d++) {
      const fecha = `${currentYear}-${String(currentMonth + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const dayDiv = document.createElement("div");
      dayDiv.className = "day";
      dayDiv.innerHTML = `<div style="font-weight:800">${d}</div>`;

      const info = turnos[fecha] || [];

      if (info.some(t => t.estado === 'creado')) dayDiv.classList.add('day-green');
      else if (info.some(t => t.estado === 'abierto')) dayDiv.classList.add('day-yellow');
      else if (info.length > 0) dayDiv.classList.add('day-orange');

      dayDiv.addEventListener("click", () => abrirModal(fecha));
      calendar.appendChild(dayDiv);
    }
  }

  // --- navegación de meses ---
  function changeMonth(delta) {
    currentMonth += delta;
    if (currentMonth < 0) { currentMonth = 11; currentYear--; }
    if (currentMonth > 11) { currentMonth = 0; currentYear++; }
    render();
  }

  // --- abrir modal ---
  async function abrirModal(fecha) {
    modal.classList.add("open");
    form.reset();
    document.getElementById("fechaTurno").value = fecha;
    validacionInfo.innerHTML = "<div class='loader'>Cargando puntos...</div>";

    try {
      const puntos = await fetchJSON(`${apiBase}?accion=puntos_disponibles&fecha=${fecha}`);
      selectPunto.innerHTML = "";
      puntos.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = p.nombre;
        selectPunto.appendChild(opt);
      });
      validacionInfo.innerHTML = "";
    } catch(err) {
      validacionInfo.innerHTML = `<div class='alert-warning'>Error: ${err.message}</div>`;
    }
  }

  document.getElementById("cerrarModal").addEventListener("click", () => modal.classList.remove("open"));

  // --- crear turno ---
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const data = new FormData(form);
    try {
      const res = await fetch(`${apiBase}?accion=crear`, { method: "POST", body: data });
      const json = await res.json();
      if (json.ok) {
        alert("Turno creado correctamente");
        modal.classList.remove("open");
        render();
      } else {
        alert(json.error || "Error al crear");
      }
    } catch(err) {
      alert("Error: " + err.message);
    }
  });

  return {
    initCalendar() {
      document.getElementById("prevM").addEventListener("click", () => changeMonth(-1));
      document.getElementById("nextM").addEventListener("click", () => changeMonth(1));
      render();
    }
  };
})();


// --- Exponer al ámbito global ---
if (typeof window !== "undefined" && typeof AppTurnosAdmin !== "undefined") {
  window.AppTurnosAdmin = AppTurnosAdmin;
}



