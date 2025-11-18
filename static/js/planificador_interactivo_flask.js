/**
 * planificador_interactivo_flask.js
 * Versión modernizada + migración completa del planificador original.
 * - Usa endpoints Flask: /api/turnos (accion=listar_por_rango, crear_manual, asignar_manual, puntos_disponibles)
 *                        /api/postulantes (accion=listar_disponibles, validar_disponibilidad)
 * - Interfaz moderna (clases compatibles con Bootstrap)
 * - Limpia código redundante y centraliza helpers
 *
 * Reemplazar el archivo actual por este. No requiere librerías externas aparte de Bootstrap (opcional).
 */

(function () {
  if (window.PlanificadorInteractivo && window.PlanificadorInteractivo._initialized) return;

  const apiBaseTurnos = "/api/turnos";
  const apiBasePost = "/api/postulantes";

  // ------------------------
  // Helpers
  // ------------------------
  function safeFetch(url, opts = {}) {
    return fetch(url, opts).then(async res => {
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status} - ${text || res.statusText}`);
      }
      return res.json().catch(() => ({}));
    });
  }

  function formatISOlocal(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function parseDateLocal(iso) {
    if (!iso) return null;
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  function timeToHHMM(t) {
    if (!t) return "";
    // t can be "8:00" or "08:00:00"
    const parts = t.split(":");
    return `${String(parts[0]||"0").padStart(2,"0")}:${String(parts[1]||"00").padStart(2,"0")}`;
  }

  // centralizar mensajes pequeños (overlay en celda)
  function mostrarAvisoCelda(celda, mensaje, tipo = "info") {
    if (!celda) return;
    const aviso = document.createElement("div");
    aviso.className = `position-absolute small text-white px-2 py-1 rounded ${tipo === "ok" ? "bg-success" : tipo === "error" ? "bg-danger" : "bg-secondary"}`;
    aviso.style.top = "6px";
    aviso.style.left = "6px";
    aviso.style.zIndex = 6000;
    aviso.textContent = mensaje;
    celda.appendChild(aviso);
    setTimeout(() => {
      aviso.style.opacity = "0";
      setTimeout(() => aviso.remove(), 350);
    }, 1400);
  }

  // ------------------------
  // Estado interno
  // ------------------------
  let turnos = [];      // array plano de turnos con { fecha, hora_inicio, hora_fin, punto, ... }
  let usuarios = [];    // lista de publicadores (para arrastrar)
  let semanaInicial = null; // Date (lunes)
  let offsetSemanas = 0;

  // ------------------------
  // UI builder (bootstrap-friendly)
  // ------------------------
  function buildLayout(root) {
    root.innerHTML = `
      <div class="d-flex gap-3">
        <aside id="pi_sidebar" class="bg-white border rounded p-3" style="width:320px; max-height:80vh; overflow:auto;">
          <div class="d-flex justify-content-between align-items-center mb-3">
            <h5 class="mb-0">Publicadores</h5>
            <div>
              <button id="pi_reload_btn" class="btn btn-sm btn-outline-secondary">Recargar</button>
            </div>
          </div>
          <div id="pi_sidebar_users" class="list-group list-group-flush"></div>
        </aside>

        <main class="flex-fill">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <div>
              <button id="btnVistaSemanal" class="btn btn-primary btn-sm me-2">📆 Vista semanal</button>
              <button id="btnVistaDiaria" class="btn btn-outline-primary btn-sm d-none">← Volver</button>
            </div>
            <div class="d-flex align-items-center gap-2">
              <input id="pi_fecha_input" type="date" class="form-control form-control-sm" />
              <select id="pi_filtro_punto" class="form-select form-select-sm ms-2" style="width:240px;">
                <option value="">Todos los puntos</option>
              </select>
            </div>
          </div>

          <div id="pi_contenedor_diario" class="mb-3">
            <div class="card">
              <div class="card-body p-2" id="lista_diaria_area">
                <!-- Vista diaria: lista de turnos y drag zone -->
                <div id="turnosListPlanif" class="row gx-2 gy-2"></div>
              </div>
            </div>
          </div>

          <div id="pi_contenedor_semanal" class="d-none">
            <div id="tituloSemana" class="mb-2 fw-bold"></div>
            <div class="d-flex mb-2 gap-2">
              <button id="btnPrevSemana" class="btn btn-outline-secondary btn-sm">◀</button>
              <button id="btnNextSemana" class="btn btn-outline-secondary btn-sm">▶</button>
            </div>
            <div id="gridSemana" class="position-relative border rounded p-2 bg-white" style="min-height:320px; overflow:auto;"></div>
          </div>
        </main>

        <aside id="pi_resumen" class="bg-light border rounded p-3" style="width:260px;">
          <h6>Resumen</h6>
          <div id="panelResumen" class="small"></div>
        </aside>
      </div>
    `;
  }

  // ------------------------
  // Cargas iniciales (usuarios + puntos + turnos)
  // ------------------------
  async function cargarUsuarios() {
    // llamamos a listar_disponibles para mostrar publicadores disponibles (sin filtros)
    try {
      const url = `${apiBasePost}?accion=listar_disponibles`;
      const data = await safeFetch(url);
      // Si endpoint devuelve array
      usuarios = Array.isArray(data) ? data : (data.pubs || []);
    } catch (err) {
      console.warn("cargarUsuarios:", err);
      usuarios = [];
    }
  }

  async function cargarTurnosPorRango(desdeISO, hastaISO) {
    try {
      const url = `${apiBaseTurnos}?accion=listar_por_rango&desde=${desdeISO}&hasta=${hastaISO}`;
      const data = await safeFetch(url);
      // El backend devuelve objeto { "YYYY-MM-DD": [turnos...] }
      // Lo convertimos a array plano con campo fecha
      const flat = [];
      Object.entries(data || {}).forEach(([fecha, arr]) => {
        (arr || []).forEach(t => flat.push({ ...t, fecha }));
      });
      turnos = flat;
      return turnos;
    } catch (err) {
      console.error("cargarTurnosPorRango:", err);
      turnos = [];
      return [];
    }
  }

  async function cargarPuntosDisponibles(fechaISO) {
    try {
      const url = `${apiBaseTurnos}?accion=puntos_disponibles&fecha=${fechaISO}`;
      return await safeFetch(url);
    } catch (err) {
      console.warn("cargarPuntosDisponibles:", err);
      return [];
    }
  }

  // ------------------------
  // Render listado diario (cards)
  // ------------------------
  function renderUsuariosList(container) {
    container.innerHTML = "";
    if (!usuarios || usuarios.length === 0) {
      container.innerHTML = `<div class="text-muted small">No hay publicadores disponibles</div>`;
      return;
    }
    usuarios.forEach(u => {
      const item = document.createElement("div");
      item.className = "list-group-item d-flex justify-content-between align-items-center draggable-user";
      item.style.cursor = "grab";
      item.draggable = true;
      item.dataset.userId = u.id;
      item.innerHTML = `<div>${u.nombre || u.full_name || u.usuario || "Usuario"}</div><small class="text-muted">${u.apellido || ""}</small>`;
      item.addEventListener("dragstart", e => {
        e.dataTransfer.setData("userId", u.id);
        e.dataTransfer.effectAllowed = "move";
      });
      container.appendChild(item);
    });
  }

  function renderTurnosList(container) {
    container.innerHTML = "";
    if (!turnos || turnos.length === 0) {
      container.innerHTML = `<div class="text-muted small">No hay turnos programados</div>`;
      return;
    }
    // Agrupar por fecha
    const grupos = {};
    turnos.forEach(t => {
      grupos[t.fecha] = grupos[t.fecha] || [];
      grupos[t.fecha].push(t);
    });
    const fechas = Object.keys(grupos).sort();

    fechas.forEach(fecha => {
      const col = document.createElement("div");
      col.className = "mb-3";
      const fechaH = parseDateLocal(fecha);
      col.innerHTML = `<div class="fw-semibold mb-1">${fechaH ? fechaH.toLocaleDateString() : fecha}</div>`;
      const inner = document.createElement("div");
      inner.className = "d-grid gap-2";
      grupos[fecha].forEach(t => {
        const card = document.createElement("div");
        card.className = "p-2 border rounded drop-turno position-relative bg-white";
        card.dataset.turnoId = t.id;
        card.dataset.fecha = t.fecha;
        card.dataset.horaInicio = t.hora_inicio;
        card.dataset.horaFin = t.hora_fin;
        card.dataset.puntoId = t.punto_id || "";
        card.innerHTML = `
          <div class="fw-medium">${timeToHHMM(t.hora_inicio)} - ${timeToHHMM(t.hora_fin)}</div>
          <div class="text-muted small">${t.punto || t.punto_id || ""}</div>
          <div class="text-success small mt-1 asignados">${t.asignados ? `${t.asignados} asignados` : '0 asignados'}</div>
        `;
        // allow drop
        card.addEventListener("dragover", e => e.preventDefault());
        card.addEventListener("drop", onDropUsuarioSimple);
        inner.appendChild(card);
      });
      col.appendChild(inner);
      container.appendChild(col);
    });
  }

  // ------------------------
  // Drop handler (list/card view)
  // ------------------------
  async function onDropUsuarioSimple(e) {
    e.preventDefault();
    const turnoId = e.currentTarget.dataset.turnoId;
    const userId = e.dataTransfer.getData("userId");
    if (!turnoId || !userId) {
      mostrarAvisoCelda(e.currentTarget, "Datos incompletos", "error");
      return;
    }
    // find turno object
    const turno = turnos.find(t => t.id == turnoId);
    if (!turno) {
      mostrarAvisoCelda(e.currentTarget, "Turno no encontrado", "error");
      return;
    }

    // 1) validar disponibilidad con backend
    const params = new URLSearchParams({
      accion: "validar_disponibilidad",
      usuario_id: userId,
      fecha: turno.fecha,
      hora_inicio: timeToHHMM(turno.hora_inicio),
      hora_fin: timeToHHMM(turno.hora_fin),
      punto_id: turno.punto_id || ""
    });
    try {
      const valid = await safeFetch(`${apiBasePost}?${params.toString()}`);
      if (!valid.ok) {
        mostrarAvisoCelda(e.currentTarget, `✗ ${valid.motivo || 'no disponible'}`, "error");
        return;
      }
    } catch (err) {
      mostrarAvisoCelda(e.currentTarget, "Error validando", "error");
      return;
    }

    // 2) asignar via API
    try {
      const body = { turno_id: Number(turnoId), usuario_id: Number(userId), rol: "publicador" };
      const res = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (res.ok) {
        mostrarAvisoCelda(e.currentTarget, "✓ Asignado", "ok");
        // actualizar UI local: incrementar asignados, cambiar barra/label
        const asignLabel = e.currentTarget.querySelector(".asignados");
        if (asignLabel) {
          const prev = turno.asignados || 0;
          turno.asignados = prev + 1;
          asignLabel.textContent = `${turno.asignados} asignados`;
        }
      } else {
        mostrarAvisoCelda(e.currentTarget, `Error: ${res.error || "no se asignó"}`, "error");
      }
    } catch (err) {
      console.error("Error asignar_manual:", err);
      mostrarAvisoCelda(e.currentTarget, "Error asignando", "error");
    }
  }

  // ------------------------
  // Semana: crear grid y permitir arrastrar en celdas vacías (creación de turnos)
  // ------------------------
  function ensureSemanaInicial() {
    if (!semanaInicial) {
      const hoy = new Date();
      const d = hoy.getDay();
      const diff = (d === 0 ? -6 : 1 - d);
      const lunes = new Date(hoy);
      lunes.setDate(hoy.getDate() + diff);
      lunes.setHours(0,0,0,0);
      semanaInicial = lunes;
    }
  }

  function getRangoSemana(baseDate) {
    const base = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate());
    const day = base.getDay();
    const diff = (day === 0 ? -6 : 1 - day);
    const lunes = new Date(base);
    lunes.setDate(base.getDate() + diff);
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    return {
      desde: formatISOlocal(lunes),
      hasta: formatISOlocal(domingo),
      lunes,
      domingo
    };
  }

  async function cambiarSemana(delta = 0) {
    ensureSemanaInicial();
    offsetSemanas += delta;
    const base = new Date(semanaInicial);
    base.setDate(semanaInicial.getDate() + offsetSemanas * 7);
    const { desde, hasta, lunes } = getRangoSemana(base);
    document.getElementById("tituloSemana").textContent = `Semana: ${desde} → ${hasta}`;

    // mostrar spinner
    const grid = document.getElementById("gridSemana");
    grid.innerHTML = `<div class="text-center py-4 text-muted">Cargando semana...</div>`;

    await cargarTurnosPorRango(desde, hasta);
    renderSemanaGrid(lunes);
  }

  function crearCeldaHora(hora, diaIndex) {
    const celda = document.createElement("div");
    celda.className = "border position-relative drop-turno-cell p-1";
    celda.dataset.dia = diaIndex + 1; // 1..7
    celda.dataset.hora = hora;
    celda.style.minHeight = "48px";
    celda.style.cursor = "pointer";

    celda.addEventListener("dragover", e => {
      e.preventDefault();
      celda.classList.add("border-primary");
    });
    celda.addEventListener("dragleave", () => celda.classList.remove("border-primary"));
    celda.addEventListener("drop", async (e) => {
      celda.classList.remove("border-primary");
      await onDropUsuarioEnCelda(e, celda);
    });
	// click en celda vacía = crear turno manualmente
	celda.addEventListener("click", async (e) => {
    e.stopPropagation();

    // obtener fecha real según semana
    ensureSemanaInicial();
    const dayIndex = Number(celda.dataset.dia); // 1..7
    const fecha = new Date(semanaInicial);
    fecha.setDate(semanaInicial.getDate() + offsetSemanas*7 + (dayIndex - 1));
    const fechaISO = formatISOlocal(fecha);
    const horaInicio = celda.dataset.hora;
    const horaFin = sumarHorasHora(horaInicio, 1);

    // cargar puntos disponibles
    const puntos = await cargarPuntosDisponibles(fechaISO);

    // abrir popup de creación
    const result = await mostrarPopupCreacionTurno(
        fechaISO,
        horaInicio,
        horaFin,
        puntos,
        celda
    );

    if (!result || !result.ok) {
        mostrarAvisoCelda(celda, "Cancelado", "error");
        return;
    }

    // recargar la semana para que aparezca el turno creado
    await cambiarSemana(0);
});


    return celda;
  }

  function renderSemanaGrid(lunesDate) {
    const cont = document.getElementById("gridSemana");
    cont.innerHTML = "";
    // encabezado dias
    const dias = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"];
    const horas = Array.from({length: 12}, (_,i) => `${String(8 + i).padStart(2,"0")}:00`);

    const tabla = document.createElement("div");
    tabla.className = "table-responsive";
    // build simple grid using CSS grid
    const grid = document.createElement("div");
    grid.style.display = "grid";
    grid.style.gridTemplateColumns = `100px repeat(7, 1fr)`;
    grid.style.gap = "0";

    // primera celda vacía (esquina)
    const corner = document.createElement("div");
    corner.className = "p-1";
    grid.appendChild(corner);

    // headers dias con fecha
    for (let d=0; d<7; d++) {
      const fecha = new Date(lunesDate);
      fecha.setDate(lunesDate.getDate() + d);
      const h = document.createElement("div");
      h.className = "p-2 text-center fw-medium bg-light border";
      h.innerHTML = `<div>${dias[d]}</div><div class="small text-muted">${formatISOlocal(fecha)}</div>`;
      grid.appendChild(h);
    }

    // filas por hora
    for (let hi=0; hi<horas.length; hi++) {
      const hora = horas[hi];
      // label hora
      const label = document.createElement("div");
      label.className = "p-2 text-end small border bg-white";
      label.textContent = hora;
      grid.appendChild(label);

      for (let d=0; d<7; d++) {
        const celda = crearCeldaHora(hora, d);
        grid.appendChild(celda);
      }
    }

    tabla.appendChild(grid);
    cont.appendChild(tabla);

    // pintar bloques de turnos existentes
    turnos.forEach(t => {
      if (!t.fecha) return;
      const fechaObj = parseDateLocal(t.fecha);
      if (!fechaObj) return;
      // calcular dia index en la semana (0..6)
      const dayIdx = (fechaObj.getDay() + 6) % 7; // Monday=0
      const startHour = Number((t.hora_inicio || "08:00").split(":")[0]);
      const endHour = Number((t.hora_fin || "09:00").split(":")[0]) || (startHour + 1);
      const dur = Math.max(1, endHour - startHour);
      // find the corresponding starting cell
      // grid children index math: 1 corner + 7 headers + (rowIndex * 8) + (dayIndex + 1)
      const rowStart = startHour - 8;
      if (rowStart < 0 || rowStart >= 12) return;
      const idx = 1 + 7 + (rowStart * 8) + (dayIdx + 1);
      const cell = grid.children[idx];
      if (!cell) return;

      // create block
      const bloque = document.createElement("div");
      bloque.className = "position-absolute text-white small rounded p-1";
      // color by coverage
      const pct = Math.round(((t.asignados || 0) / (t.maximo_publicadores || 3)) * 100);
      bloque.style.background = pct >= 80 ? "#16a34a" : pct >= 40 ? "#eab308" : "#ef4444";
      bloque.style.top = "0";
      bloque.style.left = "0";
      bloque.style.right = "0";
      bloque.style.zIndex = 50;
      bloque.style.height = `calc(${dur} * 100%)`; // cover the selected hours
      bloque.textContent = `${timeToHHMM(t.hora_inicio)}-${timeToHHMM(t.hora_fin)} ${t.punto || ""}`;
      bloque.title = `${t.asignados || 0}/${t.maximo_publicadores || 3}`;

      // set cell background to indicate coverage for the range
      for (let i=0;i<dur;i++) {
        const idxCell = 1 + 7 + ((rowStart + i) * 8) + (dayIdx + 1);
        const c = grid.children[idxCell];
        if (c) c.classList.add("bg-light");
      }
      // place on start cell
      cell.appendChild(bloque);

      // also enable dropping on the bloque to allow assignment to that turno directly
      bloque.addEventListener("dragover", e => e.preventDefault());
      bloque.addEventListener("drop", async (e) => {
        e.preventDefault();
        // if the bloque corresponds to an existing turno, prefer assigning to that turno via its id
        // we don't have t.id stamped on bloque, so fallback to fetch turnos by fecha/hora
        await onDropUsuarioEnBloque(e, t);
      });
    });
  }

  // ------------------------
  // Drop on empty cell: try to create a turno or match existing
  // ------------------------
  async function onDropUsuarioEnCelda(e, celda) {
    const userId = e.dataTransfer.getData("userId");
    if (!userId) {
      mostrarAvisoCelda(celda, "Usuario inválido", "error");
      return;
    }
    // Deduce date from cell's header: we stored date on header elements earlier in renderSemanaGrid
    // easier: find the date from the col header position by measuring index of the cell inside grid
    // We will compute the date from semanaInitial + offset + celda.dataset.dia - 1
    ensureSemanaInicial();
    const dayIndex = Number(celda.dataset.dia); // 1..7
    const fecha = new Date(semanaInicial);
    fecha.setDate(semanaInicial.getDate() + offsetSemanas*7 + (dayIndex - 1));
    const fechaISO = formatISOlocal(fecha);
    const hora = celda.dataset.hora;

    // 1) fetch turnos that overlap that fecha/hora
    try {
      const resp = await safeFetch(`${apiBaseTurnos}?accion=listar_por_rango&desde=${fechaISO}&hasta=${fechaISO}`);
      const diaTurnos = resp[fechaISO] || [];
      // find overlaps by comparing numeric hours
      const posibles = (diaTurnos || []).filter(t => {
        const hI = Number((t.hora_inicio || "00:00").split(":")[0]) + Number((t.hora_inicio || "00:00").split(":")[1]||0)/60;
        const hF = Number((t.hora_fin || "00:00").split(":")[0]) + Number((t.hora_fin || "00:00").split(":")[1]||0)/60;
        const [hSelH, hSelM] = hora.split(":").map(Number);
        const hSel = hSelH + (hSelM || 0)/60;
        return hSel >= hI && hSel < hF;
      });

      // if there are multiple, show selection modal
      let turnoElegido = null;
      if (posibles.length === 1) turnoElegido = posibles[0];
      else if (posibles.length > 1) turnoElegido = await mostrarSelectorTurnoModal(posibles);
      // if elegido -> validate + assign
      if (turnoElegido) {
        // validate disponibilidad
        const params = new URLSearchParams({
          accion: "validar_disponibilidad",
          usuario_id: userId,
          fecha: turnoElegido.fecha,
          hora_inicio: timeToHHMM(turnoElegido.hora_inicio),
          hora_fin: timeToHHMM(turnoElegido.hora_fin),
          punto_id: turnoElegido.punto_id || ""
        });
        const valid = await safeFetch(`${apiBasePost}?${params.toString()}`);
        if (!valid.ok) {
          mostrarAvisoCelda(celda, valid.motivo || "No disponible", "error");
          return;
        }
        // asignar
        const res = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ turno_id: turnoElegido.id, usuario_id: Number(userId), rol: "publicador" })
        });
        if (res.ok) {
          mostrarAvisoCelda(celda, "✓ Asignado", "ok");
          // actualizar localmente recargando la semana
          await cambiarSemana(0);
        } else {
          mostrarAvisoCelda(celda, "Error asignando", "error");
        }
        return;
      }

      // Si no hay turno posible, abrir popup de creación de turno (selección de punto)
      const puntos = await cargarPuntosDisponibles(fechaISO);
      const result = await mostrarPopupCreacionTurno(fechaISO, hora, sumarHorasHora(hora,1), puntos, celda);
      if (!result || !result.ok) {
        mostrarAvisoCelda(celda, "Creación cancelada", "error");
        return;
      }
      // buscar el turno recién creado en backend (re-cargar rango)
      await cambiarSemana(0);
      // encontrar turno creado y asignar al usuario
      const resp2 = await safeFetch(`${apiBaseTurnos}?accion=listar_por_rango&desde=${fechaISO}&hasta=${fechaISO}`);
      const listaDia = resp2[fechaISO] || [];
      const match = listaDia.find(t => t.hora_inicio === result.hora_inicio && t.hora_fin === result.hora_fin && (t.punto_id == result.punto_id || t.punto == result.punto));
      if (!match) {
        mostrarAvisoCelda(celda, "No se encontró el turno creado", "error");
        return;
      }
      // asignar usuario al turno creado
      const asignRes = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ turno_id: match.id, usuario_id: Number(userId), rol: "publicador" })
      });
      if (asignRes.ok) {
        mostrarAvisoCelda(celda, "✓ Creado y asignado", "ok");
        await cambiarSemana(0);
      } else {
        mostrarAvisoCelda(celda, "Error asignando nuevo turno", "error");
      }

    } catch (err) {
      console.error("onDropUsuarioEnCelda error:", err);
      mostrarAvisoCelda(celda, "Error procesando", "error");
    }
  }

  // Drop directly on a visual bloque (existing turno object passed)
  async function onDropUsuarioEnBloque(e, turnoObj) {
    const userId = e.dataTransfer.getData("userId");
    if (!userId) {
      mostrarAvisoCelda(e.currentTarget, "Usuario inválido", "error");
      return;
    }
    try {
      const params = new URLSearchParams({
        accion: "validar_disponibilidad",
        usuario_id: userId,
        fecha: turnoObj.fecha,
        hora_inicio: timeToHHMM(turnoObj.hora_inicio),
        hora_fin: timeToHHMM(turnoObj.hora_fin),
        punto_id: turnoObj.punto_id || ""
      });
      const valid = await safeFetch(`${apiBasePost}?${params.toString()}`);
      if (!valid.ok) {
        mostrarAvisoCelda(e.currentTarget, valid.motivo || "No disponible", "error");
        return;
      }
      const res = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ turno_id: turnoObj.id, usuario_id: Number(userId), rol: "publicador" })
      });
      if (res.ok) {
        mostrarAvisoCelda(e.currentTarget, "✓ Asignado", "ok");
        await cambiarSemana(0);
      } else {
        mostrarAvisoCelda(e.currentTarget, "Error asignando", "error");
      }
    } catch (err) {
      console.error("onDropUsuarioEnBloque:", err);
      mostrarAvisoCelda(e.currentTarget, "Error", "error");
    }
  }

  // ------------------------
  // UI modals: selector turno, crear turno
  // ------------------------
  function mostrarSelectorTurnoModal(turnosList) {
    return new Promise(resolve => {
      const backdrop = document.createElement("div");
      backdrop.className = "position-fixed top-0 start-0 w-100 h-100 bg-dark bg-opacity-50 d-flex justify-content-center align-items-center";
      backdrop.style.zIndex = 7000;
      const box = document.createElement("div");
      box.className = "bg-white rounded p-3 shadow";
      box.style.width = "360px";
      box.innerHTML = `<h6 class="mb-2">Seleccioná el turno</h6><div class="list-group mb-2"></div><div class="text-end"><button class="btn btn-sm btn-secondary btn-cancel">Cancelar</button></div>`;
      const list = box.querySelector(".list-group");
      (turnosList || []).forEach(t => {
        const it = document.createElement("button");
        it.className = "list-group-item list-group-item-action text-start";
        it.textContent = `${timeToHHMM(t.hora_inicio)} - ${timeToHHMM(t.hora_fin)} • ${t.punto || ""}`;
        it.addEventListener("click", () => { backdrop.remove(); resolve(t); });
        list.appendChild(it);
      });
      box.querySelector(".btn-cancel").addEventListener("click", () => { backdrop.remove(); resolve(null); });
      backdrop.appendChild(box);
      document.body.appendChild(backdrop);
    });
  }

  function sumarHorasHora(horaStr, horas) {
    const [h,m] = (horaStr||"08:00").split(":").map(Number);
    const d = new Date();
    d.setHours(h + horas, m || 0, 0, 0);
    return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
  }

  async function mostrarPopupCreacionTurno(fechaISO, horaInicio, horaFin, puntosArray = [], celdaRef = null) {
    return new Promise(resolve => {
      const backdrop = document.createElement("div");
      backdrop.className = "position-fixed top-0 start-0 w-100 h-100 bg-dark bg-opacity-50 d-flex justify-content-center align-items-center";
      backdrop.style.zIndex = 7000;

      const box = document.createElement("div");
      box.className = "bg-white rounded p-3 shadow";
      box.style.width = "360px";
      box.innerHTML = `
        <h6 class="mb-2">Crear turno ${fechaISO} ${horaInicio}-${horaFin}</h6>
        <div class="mb-2">
          <label class="form-label small">Punto</label>
          <select id="selPuntoNuevo" class="form-select form-select-sm"></select>
        </div>
        <div class="d-flex justify-content-end gap-2">
          <button class="btn btn-sm btn-secondary btn-cancel">Cancelar</button>
          <button class="btn btn-sm btn-primary btn-create">Crear</button>
        </div>
      `;
      const sel = box.querySelector("#selPuntoNuevo");
      sel.innerHTML = (puntosArray && puntosArray.length) ? puntosArray.map(p => `<option value="${p.id}" data-name="${p.nombre}">${p.nombre}</option>`).join("") : `<option value="">(Sin puntos disponibles)</option>`;

      box.querySelector(".btn-cancel").addEventListener("click", () => { backdrop.remove(); resolve(null); });
      box.querySelector(".btn-create").addEventListener("click", async () => {
        const pid = sel.value;
        const pname = sel.selectedOptions[0]?.dataset?.name || sel.selectedOptions[0]?.textContent || "";
        if (!pid) { alert("Seleccioná un punto"); return; }
        // enviar crear_manual
        try {
          const payload = { fecha: fechaISO, hora_inicio: horaInicio, hora_fin: horaFin, punto_id: Number(pid), punto: pname, maximo_publicadores: 3 };
          const res = await safeFetch(`${apiBaseTurnos}?accion=crear_manual`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          backdrop.remove();
          resolve({ ok: res.ok !== false, ...payload }); // devolver payload para posteriores búsquedas
        } catch (err) {
          console.error("crear_manual error:", err);
          alert("Error creando turno: " + err.message);
          backdrop.remove();
          resolve({ ok: false, error: err.message });
        }
      });

      backdrop.appendChild(box);
      document.body.appendChild(backdrop);
    });
  }

  // ------------------------
  // init
  // ------------------------
  async function init(opts = {}) {
    if (window.PlanificadorInteractivo && window.PlanificadorInteractivo._initialized) return;
    window.PlanificadorInteractivo = window.PlanificadorInteractivo || {};
    window.PlanificadorInteractivo._initialized = true;

    const root = document.getElementById("planificador_turnos");
    if (!root) return console.warn("No existe #planificador_turnos");

    buildLayout(root);

    // bind buttons
    document.getElementById("pi_reload_btn").addEventListener("click", async () => {
      await reloadAll();
    });
    document.getElementById("btnVistaSemanal").addEventListener("click", async () => {
      document.getElementById("pi_contenedor_semanal").classList.remove("d-none");
      document.getElementById("pi_contenedor_diario").classList.add("d-none");
      document.getElementById("btnVistaDiaria").classList.remove("d-none");
      document.getElementById("btnVistaSemanal").classList.add("d-none");
      await cambiarSemana(0);
    });
    document.getElementById("btnVistaDiaria").addEventListener("click", () => {
      document.getElementById("pi_contenedor_semanal").classList.add("d-none");
      document.getElementById("pi_contenedor_diario").classList.remove("d-none");
      document.getElementById("btnVistaDiaria").classList.add("d-none");
      document.getElementById("btnVistaSemanal").classList.remove("d-none");
    });

    document.getElementById("btnPrevSemana").addEventListener("click", () => cambiarSemana(-1));
    document.getElementById("btnNextSemana").addEventListener("click", () => cambiarSemana(1));

    // initial loads
    await Promise.all([cargarUsuarios(), cambiarSemana(0)]);
    // render initial lists
    renderUsuariosList(document.getElementById("pi_sidebar_users"));
    renderTurnosList(document.getElementById("turnosListPlanif"));

    // filter puntos on date change
    const fechaInput = document.getElementById("pi_fecha_input");
    fechaInput.value = formatISOlocal(new Date());
    fechaInput.addEventListener("change", async () => {
      const fecha = fechaInput.value;
      if (!fecha) return;
      try {
        const puntos = await cargarPuntosDisponibles(fecha);
        const sel = document.getElementById("pi_filtro_punto");
        sel.innerHTML = `<option value="">Todos los puntos</option>`;
        (puntos || []).forEach(p => {
          const opt = document.createElement("option");
          opt.value = p.id;
          opt.textContent = p.nombre || p.nombre;
          sel.appendChild(opt);
        });
      } catch (err) { console.warn("error cargar puntos:", err); }
      // update daily list when changing date
      await reloadAll();
    });

    // when reload, refresh sidebar users and daily turnos
    async function reloadAll() {
      await cargarUsuarios();
      renderUsuariosList(document.getElementById("pi_sidebar_users"));
      // reload current week/day view
      await cambiarSemana(0);
      renderTurnosList(document.getElementById("turnosListPlanif"));
    }

    // expose some methods for debugging
    window.PlanificadorInteractivo.reloadAll = reloadAll;
    window.PlanificadorInteractivo.init = init;
    console.log("PlanificadorInteractivo inicializado (Flask modernizado)");
  }

  // expose public
  window.PlanificadorInteractivo = window.PlanificadorInteractivo || {};
  window.PlanificadorInteractivo.init = init;
  window.PlanificadorInteractivo._initialized = false;

})();
