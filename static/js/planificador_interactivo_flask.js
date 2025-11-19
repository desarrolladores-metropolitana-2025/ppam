/* planificador_interactivo_flask_full_v2.js
   Versión migrada y completada para Flask (oct 2025)
   - Usa endpoints:
       /api/turnos?accion=...
       /api/postulantes?accion=...
   - Opción C: usa los nombres cargados en memoria (usuarios[]) al asignar
*/

(function () {
  if (window.PlanificadorInteractivo && window.PlanificadorInteractivo._initialized) return;

  // --- API bases (Flask)
  const apiBaseTurnos = "/api/turnos";
  const apiBasePost = "/api/postulantes";

  // Estado
  let usuarios = [];
  let turnos = [];
  let semanaInicial = null;
  let offsetSemanas = 0;
  let resumen = {
    totalAsignados: 0,
    turnosCompletos: 0,
    turnosVacantes: 0,
    conflictos: []
  };

  // ---------------- utility ----------------
  function padTimeToHHMM(t) {
    if (!t) return t;
    const parts = t.split(':');
    const hh = String(parts[0] || '0').padStart(2,'0');
    const mm = String(parts[1] || '00').padStart(2,'0');
    return `${hh}:${mm}`;
  }

  function sumarHoras(horaStr, horasASumar) {
    const [horas, minutos] = horaStr.split(':').map(Number);
    const fechaTemp = new Date();
    fechaTemp.setHours(horas + horasASumar, minutos || 0, 0);
    return `${String(fechaTemp.getHours()).padStart(2,'0')}:${String(fechaTemp.getMinutes()).padStart(2,'0')}`;
  }

  function formatISOlocal(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function getRangoSemana(baseDate) {
    const base = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate());
    base.setHours(12, 0, 0, 0);
    const day = base.getDay(); // 0=domingo
    const diff = (day === 0 ? -6 : 1 - day);
    const lunes = new Date(base);
    lunes.setDate(base.getDate() + diff);
    lunes.setHours(0,0,0,0);
    const domingo = new Date(lunes);
    domingo.setDate(lunes.getDate() + 6);
    domingo.setHours(23,59,59,999);
    return { desde: formatISOlocal(lunes), hasta: formatISOlocal(domingo), lunes, domingo };
  }

  // safeFetch: trabaja con JSON o texto; devuelve { ok, status, data, error }
  async function safeFetch(url, opts = {}) {
    try {
      const r = await fetch(url, opts);
      const text = await r.text();
      // intentar parsear JSON
      let data;
      try { data = JSON.parse(text); }
      catch { data = text; }
      return { ok: r.ok, status: r.status, data, url };
    } catch (err) {
      return { ok: false, status: 0, error: err.message || String(err), url };
    }
  }

  // ---------------- UI helpers ----------------
  function mostrarAvisoCelda(celda, mensaje, tipo = "info") {
    if (!celda) return;
    const aviso = document.createElement("div");
    aviso.className = `absolute z-50 px-3 py-1 rounded text-xs font-medium text-white shadow-lg transition-opacity duration-500 ${
      tipo === "ok" ? "bg-green-500" : tipo === "error" ? "bg-red-500" : "bg-gray-700"
    }`;
    aviso.textContent = mensaje;
    aviso.style.top = "6px";
    aviso.style.left = "6px";
    aviso.style.pointerEvents = "none";
    celda.appendChild(aviso);
    setTimeout(() => (aviso.style.opacity = "0"), 1200);
    setTimeout(() => aviso.remove(), 1800);
  }

  function nombreFromUser(u) {
    if (!u) return "Usuario";
    return [u.nombre, u.apellido].filter(Boolean).join(" ") || u.usuario || `Usuario ${u.id}`;
  }

  // ---------------- CARGA DATOS ----------------
  async function cargarUsuarios(params = {}) {
    // params possible: punto_id, fecha, hora_inicio, hora_fin
    const q = new URLSearchParams({ accion: "listar_disponibles" });
    Object.keys(params).forEach(k => { if (params[k] !== undefined && params[k] !== null) q.set(k, String(params[k])); });
    const url = `${apiBasePost}?${q.toString()}`;
    const r = await safeFetch(url);
    if (!r.ok) { console.warn("Error cargarUsuarios:", r); usuarios = []; return usuarios; }
    usuarios = Array.isArray(r.data) ? r.data : [];
    return usuarios;
  }

  async function cargarTurnos(desde, hasta) {
    // si no se pasan, usa semana actual (calcula)
    if (!desde || !hasta) {
      const hoy = new Date();
      const { desde: d, hasta: h } = getRangoSemana(hoy);
      desde = d; hasta = h;
    }
    const url = `${apiBaseTurnos}?accion=listar_por_rango&desde=${desde}&hasta=${hasta}`;
    const r = await safeFetch(url);
    if (!r.ok) { console.warn("Error cargarTurnos:", r); turnos = []; return turnos; }
    const obj = r.data || {};
    // convertir a array plano con fecha field
    turnos = Object.entries(obj).flatMap(([fecha, arr]) => (arr || []).map(t => ({ ...t, fecha })));
    return turnos;
  }

  // ---------------- RENDER LISTA USUARIOS (barra lateral) ----------------
  async function renderUsersList(containerId = "pi_sidebar_users") {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = `<div class="text-sm text-gray-500">Cargando publicadores...</div>`;
    try {
      if (!usuarios || usuarios.length === 0) await cargarUsuarios();
      if (!usuarios || usuarios.length === 0) {
        container.innerHTML = `<div class="text-sm text-gray-500">No hay publicadores disponibles.</div>`;
        return;
      }
      container.innerHTML = "";
      usuarios.forEach(u => {
        const el = document.createElement("div");
        el.className = "p-2 border rounded hover:bg-gray-50 flex justify-between items-center draggable-user cursor-move";
        el.draggable = true;
        el.dataset.userId = u.id;
        el.innerHTML = `<div><div class="font-medium">${nombreFromUser(u)}</div>
                        <div class="text-xs text-gray-500">${u.usuario || ''}</div></div>
                        <div class="text-xs text-gray-400">${u.id || ''}</div>`;
        el.addEventListener("dragstart", onDragStart);
        container.appendChild(el);
      });
    } catch (err) {
      container.innerHTML = `<div class="text-sm text-red-500">Error cargando publicadores</div>`;
      console.warn("renderUsersList error:", err);
    }
  }

  // ---------------- RENDER GRID SEMANA (simplificado y robusto) ----------------
  async function renderGridSemana(fechaISO) {
    // wrapper required: #pi_grid_inner in your earlier layout; fallback to #gridSemana
    const wrapper = document.getElementById("pi_grid_inner") || document.getElementById("gridSemana");
    if (!wrapper) return;

    let fecha = fechaISO || document.getElementById("pi_fecha_input")?.value;
    if (!fecha) {
      const d = new Date();
      fecha = formatISOlocal(d);
      const inp = document.getElementById("pi_fecha_input");
      if (inp) inp.value = fecha;
    }

    const base = (fecha) ? new Date(fecha.split('-').map((n,i)=> i===1 ? Number(n)-1 : Number(n)).reverse().reverse()) : new Date();
    // compute monday as in getRangoSemana
    const { lunes } = getRangoSemana(new Date(base.getFullYear(), base.getMonth(), base.getDate()));
    const days = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(lunes);
      d.setDate(lunes.getDate() + i);
      days.push(d);
    }

    const colsHtml = days.map(d => {
      const iso = formatISOlocal(d);
      const dayName = d.toLocaleDateString('es-ES', { weekday: 'long' });
      const dayShort = d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
      return `<div class="pi-day-column border-l p-2" data-fecha="${iso}" style="min-width:140px;position:relative;">
                <div class="font-semibold">${dayName}</div>
                <div class="text-xs text-gray-500">${dayShort}</div>
                <div class="pi-day-body mt-2"></div>
              </div>`;
    }).join("");
    wrapper.innerHTML = `<div class="grid grid-cols-7 gap-2">${colsHtml}</div>`;

    // cargar turnos para el rango
    const desde = formatISOlocal(days[0]);
    const hasta = formatISOlocal(days[6]);
    await cargarTurnos(desde, hasta);

    // Build map date -> column body
    const colNodes = wrapper.querySelectorAll(".pi-day-column");
    const mapCols = {};
    colNodes.forEach(n => {
      mapCols[n.dataset.fecha] = n.querySelector(".pi-day-body");
    });

    // filter by punto (if select exists)
    const filtroPunto = document.getElementById("pi_filtro_punto")?.value || "";

    // append turnos to columns
    (turnos || []).forEach(t => {
      if (filtroPunto && String(t.punto_id) !== String(filtroPunto)) return;
      const target = mapCols[t.fecha] || Object.values(mapCols)[0];
      if (!target) return;
      const nodo = document.createElement("div");
      nodo.className = "p-2 mb-2 border rounded bg-slate-50 drop-turno";
      nodo.dataset.turnoId = t.id;
      nodo.dataset.fecha = t.fecha;
      nodo.dataset.horaInicio = t.hora_inicio;
      nodo.dataset.horaFin = t.hora_fin;
      nodo.dataset.puntoId = t.punto_id;
      nodo.innerHTML = `<div class="font-medium">${t.punto || ('Punto ' + (t.punto_id||''))}</div>
                        <div class="text-xs text-gray-600">${t.hora_inicio || ''} - ${t.hora_fin || ''}</div>
                        <div class="asignados text-xs text-gray-700 mt-1"></div>`;
      nodo.addEventListener("dragover", e => e.preventDefault());
      nodo.addEventListener("drop", onDropUsuario);
      target.appendChild(nodo);

      // render assigned names from backend fields if present (we expect nulls normally)
      const asignBox = nodo.querySelector(".asignados");
      const assignedNames = [];
      ["publicador1","publicador2","publicador3","publicador4"].forEach(slot => {
        const val = t[slot];
        if (val) assignedNames.push(String(val)); // backend might eventually send "Name" or id
      });
      if (assignedNames.length) asignBox.innerHTML = assignedNames.map(n => `<div>${n}</div>`).join("");
    });

    // attach "Ir" button behavior if present
    const btn = document.getElementById("pi_apply_date");
    if (btn) btn.onclick = async () => {
      const newDate = document.getElementById("pi_fecha_input").value;
      await loadPuntosFiltro(newDate);
      await renderGridSemana(newDate);
    };
  }

  // load puntos into select
  async function loadPuntosFiltro(fechaISO) {
    const sel = document.getElementById("pi_filtro_punto");
    if (!sel) return;
    sel.innerHTML = `<option value="">Todos los puntos</option>`;
    const fecha = fechaISO || document.getElementById("pi_fecha_input")?.value;
    if (!fecha) return;
    const url = `${apiBaseTurnos}?accion=puntos_disponibles&fecha=${fecha}`;
    const r = await safeFetch(url);
    if (!r.ok) return;
    const puntos = Array.isArray(r.data) ? r.data : [];
    puntos.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.nombre;
      sel.appendChild(opt);
    });
    sel.onchange = async () => { await renderGridSemana(fecha); };
  }

  // ---------------- Drag & Drop core (diario y semanal unified) ----------------
  function onDragStart(e) {
    const id = e.target.dataset.userId;
    if (!id) return;
    e.dataTransfer.setData("userId", id);
    e.dataTransfer.effectAllowed = "move";
  }

  // onDropUsuario: maneja muchos escenarios (turno existente, seleccionar, crear nuevo, asignar)
  async function onDropUsuario(e) {
    e.preventDefault();
    const box = e.currentTarget;
    if (!box) return;
    const userId = e.dataTransfer.getData("userId");
    if (!userId) { console.warn("drop sin userId"); return; }

    // Si la caja tiene data-turno-id (tarjeta de turno) -> asignar directamente a ese turno
    const turnoId = box.dataset.turnoId || box.dataset.turnoid || null;

    // Asegurar caja '.asignados'
    let asignadosBox = box.querySelector(".asignados");
    if (!asignadosBox) {
      asignadosBox = document.createElement("div");
      asignadosBox.className = "asignados text-xs text-gray-600 italic";
      box.appendChild(asignadosBox);
    }

    // Si no existe turnoId pero estamos en grilla semanal (celda con data-dia) => tratar de buscar/crear turno
    if (!turnoId && box.dataset.dia) {
      const dia = parseInt(box.dataset.dia);
      const hora = box.dataset.hora;
      const fecha = calcularFechaPorDia(dia);
      // normalizar fecha ISO
      const fechaISO = fecha && fecha.includes("/") ? fecha.split("/").reverse().join("-") : fecha;

      mostrarAvisoCelda(box, `Intentando asignar ${userId} → ${fechaISO} ${hora}`, "info");

      // pedir turnos del día
      const resp = await safeFetch(`${apiBaseTurnos}?accion=listar_por_rango&desde=${fechaISO}&hasta=${fechaISO}`);
      if (!resp.ok) {
        mostrarAvisoCelda(box, "Error cargando turnos", "error");
        return;
      }
      const datos = resp.data || {};
      const posibles = (datos[fechaISO] || []).filter(t => {
        const hI = Number(t.hora_inicio.split(":")[0]) + Number(t.hora_inicio.split(":")[1] || 0)/60;
        const hF = Number(t.hora_fin.split(":")[0]) + Number(t.hora_fin.split(":")[1] || 0)/60;
        const [hSelH, hSelM] = (hora || "00:00").split(":").map(Number);
        const hSel = hSelH + (hSelM || 0)/60;
        return hSel >= hI && hSel < hF;
      });

      if (posibles.length > 0) {
        // seleccionar si hay varios
        let elegido = posibles[0];
        if (posibles.length > 1) {
          elegido = await mostrarSelectorTurno(posibles);
          if (!elegido) { mostrarAvisoCelda(box, "Cancelado", "error"); return; }
        }

        // validar disponibilidad contra backend
        const params = new URLSearchParams({
          accion: "validar_disponibilidad",
          usuario_id: userId,
          fecha: elegido.fecha,
          hora_inicio: padTimeToHHMM(elegido.hora_inicio),
          hora_fin: padTimeToHHMM(elegido.hora_fin),
          punto_id: elegido.punto_id || ""
        });
        const v = await safeFetch(`${apiBasePost}?${params.toString()}`);
        const vdata = v.data || {};
        if (!v.ok || vdata.ok === false) {
          mostrarAvisoCelda(box, `No disponible: ${vdata.motivo || v.error || '?'}`, "error");
          return;
        }

        // asignar mediante API
        const post = { turno_id: elegido.id, usuario_id: Number(userId), rol: "publicador" };
        const r = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(post)
        });
        if (!r.ok || r.data?.ok === false) {
          mostrarAvisoCelda(box, `Error: ${r.data?.error || r.error || r.status}`, "error");
          return;
        }

        // Visual: usar nombre desde usuarios[] (Opción C)
        const userObj = usuarios.find(u => String(u.id) === String(userId));
        const nombre = nombreFromUser(userObj);
        const overlay = document.createElement("div");
        overlay.className = "absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow";
        overlay.textContent = "✓ " + nombre.split(' ')[0];
        box.appendChild(overlay);
        resumen.totalAsignados++;
        actualizarPanelResumen();
        mostrarAvisoCelda(box, "✓ Asignado", "ok");
        return;
      }

      // No hay turnos: crear uno nuevo (popup)
      mostrarAvisoCelda(box, "No existe turno → crear", "info");
      const result = await mostrarPopupCreacionTurno(fechaISO, hora, sumarHoras(hora,1), box);
      if (!result || !result.ok) { mostrarAvisoCelda(box, "Creación cancelada", "error"); return; }

      // buscar turno nuevo en backend y asignar
      const resp2 = await safeFetch(`${apiBaseTurnos}?accion=listar_por_rango&desde=${fechaISO}&hasta=${fechaISO}`);
      if (!resp2.ok) { mostrarAvisoCelda(box, "Error reload turnos", "error"); return; }
      const nuevos = resp2.data || {};
      const fechaKey = fechaISO;
      const turnoNuevo = (nuevos[fechaKey] || []).find(t => t.hora_inicio === result.hora_inicio && t.hora_fin === result.hora_fin);
      if (!turnoNuevo) { mostrarAvisoCelda(box, "No se encontró el turno creado", "error"); return; }

      // asignar al turno nuevo
      const post2 = { turno_id: turnoNuevo.id, usuario_id: Number(userId), rol: "publicador" };
      const r2 = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(post2)
      });
      if (!r2.ok || r2.data?.ok === false) { mostrarAvisoCelda(box, `Error asignando: ${r2.data?.error||r2.error}`, "error"); return; }

      const userObj2 = usuarios.find(u => String(u.id) === String(userId));
      const nombre2 = nombreFromUser(userObj2);
      const overlay2 = document.createElement("div");
      overlay2.className = "absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow";
      overlay2.textContent = "✓ " + nombre2.split(' ')[0];
      box.appendChild(overlay2);
      resumen.totalAsignados++;
      actualizarPanelResumen();
      mostrarAvisoCelda(box, "✓ Creado + asignado", "ok");
      return;
    }

    // Si tenemos un turnoId directo — comportamiento normal: validar + asignar
    if (turnoId) {
      const turno = turnos.find(t => String(t.id) === String(turnoId));
      const userObj = usuarios.find(u => String(u.id) === String(userId));
      if (!turno) { mostrarAvisoCelda(box, "Turno no encontrado localmente", "error"); return; }
      if (!userObj) { mostrarAvisoCelda(box, "Usuario no encontrado localmente", "error"); return; }

      // Validar disponibilidad
      const params = new URLSearchParams({
        accion: "validar_disponibilidad",
        usuario_id: userId,
        fecha: turno.fecha,
        hora_inicio: padTimeToHHMM(turno.hora_inicio),
        hora_fin: padTimeToHHMM(turno.hora_fin),
        punto_id: turno.punto_id || ""
      });
      const v = await safeFetch(`${apiBasePost}?${params.toString()}`);
      const vdata = v.data || {};
      if (!v.ok || vdata.ok === false) {
        mostrarAvisoCelda(box, `No disponible: ${vdata.motivo || v.error || '?'}`, "error");
        resumen.conflictos.push(`${nombreFromUser(userObj)} → ${turno.fecha} (${vdata.motivo || 'conflicto'})`);
        actualizarPanelResumen();
        return;
      }

      // Asignar
      const post = { turno_id: Number(turnoId), usuario_id: Number(userId), rol: "publicador" };
      const r = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(post)
      });
      if (!r.ok || r.data?.ok === false) {
        mostrarAvisoCelda(box, `Error: ${r.data?.error || r.error || r.status}`, "error");
        return;
      }

      // Pintar UI (usar nombre local)
      const nombre = nombreFromUser(userObj);
      asignadosBox.innerHTML += `<div class="text-green-700">✓ ${nombre} asignado</div>`;
      if (box.closest("#gridSemana")) {
        const overlay = document.createElement("div");
        overlay.className = "absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow";
        overlay.textContent = `${nombre.split(' ')[0]}`;
        box.appendChild(overlay);
      }
      resumen.totalAsignados++;
      actualizarPanelResumen();
      actualizarBarraProgreso(turnoId);
    }
  }

  // ----------------- actualizar barra progreso local -----------------
  function actualizarBarraProgreso(turnoId) {
    const turno = turnos.find(t => String(t.id) === String(turnoId));
    if (!turno) return;
    // actualizar contador localmente (no exhaustivo)
    turno.asignados = (turno.asignados || 0) + 1;
    const asignados = turno.asignados;
    const max = turno.maximo_publicadores || 3;
    const pct = Math.round((asignados / max) * 100);
    const box = document.querySelector(`.drop-turno[data-turno-id="${turnoId}"]`);
    if (!box) return;
    const bar = box.querySelector(".h-3 > div");
    const label = box.querySelector(".text-xs");
    if (bar) {
      bar.className = `${pct >= 80 ? "bg-green-500" : pct >= 40 ? "bg-yellow-400" : "bg-red-400"} h-full transition-all duration-300`;
      bar.style.width = `${pct}%`;
    }
    if (label) label.textContent = `${asignados}/${max} cubiertos (${pct}%)`;
  }

  // ---------------- Mostrar selector de turnos si hay varios ----------------
  async function mostrarSelectorTurno(turnosArr) {
    return new Promise(resolve => {
      const popup = document.createElement("div");
      popup.className = "fixed inset-0 bg-black/50 flex justify-center items-center z-[9999]";
      popup.innerHTML = `
        <div class="bg-white rounded-lg shadow-xl p-4 w-[340px]">
          <h3 class="font-semibold text-lg mb-2 text-indigo-700">📍 Seleccioná el turno</h3>
          <div class="max-h-[200px] overflow-y-auto mb-3">
            ${turnosArr.map(t => `
              <div class="turno-opcion border rounded p-2 mb-1 cursor-pointer hover:bg-indigo-50"
                   data-id="${t.id}">
                <b>${t.punto}</b><br>
                <span class="text-sm text-gray-600">${t.hora_inicio} - ${t.hora_fin}</span>
              </div>
            `).join("")}
          </div>
          <div class="flex justify-end">
            <button id="btnCancelarSelTurno" class="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 text-sm">Cancelar</button>
          </div>
        </div>
      `;
      document.body.appendChild(popup);
      popup.querySelectorAll(".turno-opcion").forEach(el => {
        el.addEventListener("click", () => {
          const id = el.dataset.id;
          const elegido = turnosArr.find(t => String(t.id) === String(id));
          popup.remove();
          resolve(elegido);
        });
      });
      popup.querySelector("#btnCancelarSelTurno").onclick = () => { popup.remove(); resolve(null); };
    });
  }

  // ---------------- Popup crear turno (arrastrable) ----------------
  async function mostrarPopupCreacionTurno(fecha, horaInicio, horaFin, celda) {
    return new Promise(async (resolve, reject) => {
      const anterior = document.getElementById("popupTurnoNuevo");
      if (anterior) anterior.remove();

      if (horaInicio === horaFin) {
        const [h,m] = horaInicio.split(":").map(Number);
        horaFin = `${String(h+1).padStart(2,'0')}:${String(m||0).padStart(2,'0')}`;
      }

      const popup = document.createElement("div");
      popup.id = "popupTurnoNuevo";
      popup.className = `fixed z-[9999] bg-white border border-gray-300 shadow-2xl rounded-lg p-4 w-72 animate-fadeIn text-sm`;
      popup.innerHTML = `
        <div class="font-semibold text-gray-800 mb-2">📅 ${fecha}<br>🕒 ${horaInicio} - ${horaFin}</div>
        <label class="block text-sm text-gray-600 mb-1">Seleccioná el punto:</label>
        <select id="selPuntoNuevo" class="w-full border rounded p-1 mb-3 text-sm"><option value="">Cargando puntos...</option></select>
        <div class="flex justify-end gap-2">
          <button id="btnCancelarPopup" class="text-sm px-2 py-1 bg-gray-200 rounded hover:bg-gray-300">Cancelar</button>
          <button id="btnCrearPopup" class="text-sm px-3 py-1 bg-indigo-500 text-white rounded hover:bg-indigo-600">Crear</button>
        </div>
      `;
      document.body.appendChild(popup);

      // position near celda (best effort)
      try {
        const rect = celda.getBoundingClientRect();
        const viewportHeight = window.innerHeight;
        const popupHeight = 220;
        let topPosition = rect.top + window.scrollY + 15;
        let leftPosition = rect.left + window.scrollX + 15;
        if (rect.bottom + popupHeight > viewportHeight) topPosition = Math.max(rect.top + window.scrollY - popupHeight - 30, 5);
        popup.style.top = `${topPosition}px`; popup.style.left = `${leftPosition}px`; popup.style.position = "fixed";
      } catch (e) { /* ignore position errors */ }

      // draggable behavior (simple)
      let isDragging = false, initialX=0, initialY=0, xOffset=0, yOffset=0;
      popup.addEventListener("mousedown", (ev) => {
        if (ev.button !== 0) return;
        const tag = ev.target.tagName.toLowerCase();
        if (["select","option","button","input","label"].includes(tag)) return;
        isDragging = true; initialX = ev.clientX - xOffset; initialY = ev.clientY - yOffset;
        popup.style.cursor = "grabbing";
      });
      document.addEventListener("mouseup", () => { isDragging = false; popup.style.cursor = "default"; });
      document.addEventListener("mousemove", (ev) => {
        if (!isDragging) return;
        xOffset = ev.clientX - initialX; yOffset = ev.clientY - initialY;
        popup.style.transform = `translate3d(${xOffset}px, ${yOffset}px, 0)`;
      });

      // cargar puntos disponibles
      const r = await safeFetch(`${apiBaseTurnos}?accion=puntos_disponibles&fecha=${fecha}`);
      const puntos = (r.ok && Array.isArray(r.data)) ? r.data : [];
      const sel = popup.querySelector("#selPuntoNuevo");
      sel.innerHTML = puntos.length ? puntos.map(p => `<option value="${p.id}">${p.nombre}</option>`).join("") : `<option value="">(Sin puntos disponibles)</option>`;

      const handleEscape = (ev) => { if (ev.key === "Escape") { popup.remove(); document.removeEventListener("keydown", handleEscape); resolve({ cancelled: true }); } };
      document.addEventListener("keydown", handleEscape);

      popup.querySelector("#btnCancelarPopup").addEventListener("click", () => { popup.remove(); document.removeEventListener("keydown", handleEscape); resolve({ cancelled: true }); });

      popup.querySelector("#btnCrearPopup").addEventListener("click", async () => {
        const puntoId = sel.value;
        const puntoNombre = sel.selectedOptions[0]?.text || "";
        if (!puntoId) { alert("Seleccioná un punto"); return; }
        const postData = { fecha, hora_inicio: horaInicio, hora_fin: horaFin, punto: puntoNombre, punto_id: Number(puntoId), maximo_publicadores: 3 };
        const resp = await safeFetch(`${apiBaseTurnos}?accion=crear_manual`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(postData)
        });
        if (!resp.ok || resp.data?.ok === false) {
          popup.remove();
          resolve({ ok: false, error: resp.data?.error || resp.error });
          return;
        }
        popup.remove();
        document.removeEventListener("keydown", handleEscape);
        resolve({ ok: true, ...postData });
      });
    });
  }

  // ---------------- Semanal: render y creación de grid grande (vista tipo PHP) ----------------
  async function renderSemanaFull() {
    const cont = document.getElementById("gridSemana");
    if (!cont) return;
    cont.innerHTML = "";

    const dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"];
    const horas = Array.from({length: 12}, (_,i) => `${String(8 + i).padStart(2,'0')}:00`);
    // establecer semanaBase si no
    if (!semanaInicial) {
      const hoy = new Date(); semanaInicial = getRangoSemana(hoy).lunes;
    }
    const grid = document.createElement("div");
    grid.className = "grid border-t border-l";
    grid.style.gridTemplateColumns = `100px repeat(7, 1fr)`;
    // corner
    grid.appendChild(document.createElement("div"));
    dias.forEach(d => { const h = document.createElement("div"); h.textContent = d; h.className = "font-semibold text-center border-r border-b bg-indigo-50"; grid.appendChild(h); });

    horas.forEach(hora => {
      const label = document.createElement("div"); label.textContent = hora; label.className = "text-right pr-2 text-sm border-r border-b bg-gray-50"; grid.appendChild(label);
      for (let d = 0; d < 7; d++) {
        const celda = document.createElement("div");
        celda.className = "relative border-r border-b h-16 hover:bg-indigo-50 transition drop-turno empty-slot";
        celda.dataset.dia = d + 1;
        celda.dataset.hora = hora;
        celda.addEventListener("dragover", e => { e.preventDefault(); celda.classList.add("ring","ring-indigo-300"); });
        celda.addEventListener("dragleave", () => celda.classList.remove("ring","ring-indigo-300"));
        celda.addEventListener("drop", e => { celda.classList.remove("ring","ring-indigo-300"); onDropUsuario(e); });
        grid.appendChild(celda);
      }
    });

    cont.appendChild(grid);

    // Insertar turnos visualmente (usar turnos[] local — asegúrate de cargar semana antes)
    // Compute semanaBase if needed (already above)
    const primera = turnos[0];
    if (primera && primera.fecha) {
      // set semanaInicial such that monday maps
      const [yy,mm,dd] = primera.fecha.split("-").map(Number);
      const primeraFecha = new Date(yy, mm-1, dd);
      const diaSemana = (primeraFecha.getDay() + 6) % 7;
      semanaInicial = new Date(primeraFecha);
      semanaInicial.setDate(primeraFecha.getDate() - diaSemana);
    }

    // Put turns into grid
    turnos.forEach(t => {
      if (!t.fecha) return;
      const [yy,mm,dd] = t.fecha.split("-").map(Number);
      const fechaObj = new Date(yy, mm-1, dd);
      const dia = (fechaObj.getDay() + 6) % 7; // lunes = 0
      const horaInicio = parseInt((t.hora_inicio || "08:00").split(":")[0], 10);
      const horaFin = parseInt((t.hora_fin || "09:00").split(":")[0], 10);
      const duracion = Math.max(1, horaFin - horaInicio);
      const fila = horaInicio - 8;
      if (fila < 0) return;
      // compute index in grid children
      // grid children layout: 1 corner + 7 headers + (for each hour: 1 label + 7 cells) => top offset = 1 + 7
      const topOffset = 1 + 7;
      const idx = topOffset + (fila * (1 + 7)) + (dia + 1);
      const celdaInicio = grid.children[idx];
      if (!celdaInicio) return;

      const asignados = t.asignados || 0;
      const max = t.maximo_publicadores || 3;
      const pct = Math.round((asignados / max) * 100);
      const color = pct >= 80 ? "bg-green-500" : pct >= 40 ? "bg-yellow-400" : "bg-red-400";

      const bloque = document.createElement("div");
      bloque.className = `absolute inset-0 rounded text-xs text-white p-1 shadow ${color} overflow-hidden`;
      bloque.textContent = `${t.hora_inicio}-${t.hora_fin} ${t.punto || ''}`;
      bloque.title = `${asignados}/${max} (${pct}%)`;
      bloque.style.height = `calc(${duracion} * 100%)`; bloque.style.top = "0"; bloque.style.left = "0"; bloque.style.right = "0"; bloque.style.zIndex = "5";

      // color background for covered celdas
      for (let i = 0; i < duracion; i++) {
        const idxCelda = topOffset + ((fila + i) * (1 + 7)) + (dia + 1);
        const celda = grid.children[idxCelda];
        if (celda) celda.classList.add("bg-green-100");
      }

      celdaInicio.appendChild(bloque);
    });

    // Add markers/tooltips per cell
    const celdas = cont.querySelectorAll(".drop-turno");
    celdas.forEach(celda => {
      const dia = parseInt(celda.dataset.dia);
      const hora = celda.dataset.hora;
      const fecha = calcularFechaPorDia(dia);
      const lista = (turnos || []).filter(t => {
        if (!t.fecha) return false;
        if (t.fecha !== fecha) return false;
        const hI = Number(t.hora_inicio.split(":")[0]) + Number(t.hora_inicio.split(":")[1]||0)/60;
        const hF = Number(t.hora_fin.split(":")[0]) + Number(t.hora_fin.split(":")[1]||0)/60;
        const [hSelH, hSelM] = hora.split(":").map(Number);
        const hSel = hSelH + (hSelM || 0)/60;
        return hSel >= hI && hSel < hF;
      });
      if (lista.length > 0) {
        const marker = document.createElement("div");
        marker.className = "absolute bottom-1 right-1 text-[10px] text-gray-500 bg-yellow-50 px-1 rounded border border-yellow-300";
        marker.textContent = `${lista.length} turno${lista.length>1 ? "s" : ""}`;
        celda.appendChild(marker);
        celda.title = lista.map(t => `${t.hora_inicio}-${t.hora_fin} ${t.punto}`).join("\n");
      }
    });

    activarCreacionTurnoGrid(); // enable select-to-create behavior
  }

  // ---------------- Activar creación por selección en grilla semanal ----------------
  let creandoTurno = null;
  function activarCreacionTurnoGrid() {
    const grid = document.getElementById("gridSemana");
    if (!grid) return;

    grid.addEventListener("mousedown", e => {
      if (!e.target.classList.contains("drop-turno")) return;
      e.preventDefault();
      creandoTurno = { dia: e.target.dataset.dia, celdaInicio: e.target, celdasSeleccionadas: [e.target] };
      e.target.classList.add("bg-blue-100","ring","ring-blue-300");
    });

    grid.addEventListener("mouseover", e => {
      if (!creandoTurno) return;
      const celda = e.target.closest(".drop-turno");
      if (!celda || celda.dataset.dia !== creandoTurno.dia) return;
      const todas = [...grid.querySelectorAll(`.drop-turno[data-dia="${creandoTurno.dia}"]`)];
      const iInicio = todas.indexOf(creandoTurno.celdaInicio);
      const iActual = todas.indexOf(celda);
      creandoTurno.celdasSeleccionadas.forEach(c => c.classList.remove("bg-blue-200"));
      const rango = todas.slice(Math.min(iInicio,iActual), Math.max(iInicio,iActual)+1);
      rango.forEach(c => c.classList.add("bg-blue-200"));
      creandoTurno.celdasSeleccionadas = rango;
    });

    grid.addEventListener("mouseup", async e => {
      if (!creandoTurno) return;
      const celdaFin = e.target.closest(".drop-turno");
      if (!celdaFin) { // cleanup
        if (creandoTurno && Array.isArray(creandoTurno.celdasSeleccionadas)) crearLimpiezaSeleccion();
        creandoTurno = null; return;
      }
      const dia = parseInt(creandoTurno.dia);
      const horaInicio = creandoTurno.celdaInicio.dataset.hora;
      let horaFin = celdaFin.dataset.hora;
      const [hFin,mFin] = horaFin.split(":").map(Number);
      horaFin = `${String(hFin + 1).padStart(2,"0")}:${String(mFin||0).padStart(2,"0")}`;
      const fechaTurno = calcularFechaPorDia(dia);
      const rangoSeleccionado = [...(creandoTurno.celdasSeleccionadas || [])];
      const result = await mostrarPopupCreacionTurno(fechaTurno, horaInicio, horaFin, celdaFin);
      if (result && result.ok) {
        rangoSeleccionado.forEach(c => { c.classList.remove("bg-blue-100","bg-blue-200","ring","ring-blue-300"); c.classList.add("bg-green-100"); });
        const bloque = document.createElement("div");
        bloque.className = "absolute inset-0 rounded text-xs text-white p-1 shadow bg-green-500 overflow-hidden";
        bloque.textContent = `${horaInicio}-${horaFin} ${result.punto || ""}`;
        const numCeldas = rangoSeleccionado.length;
        bloque.style.height = `calc(${numCeldas} * 100%)`;
        bloque.style.top = "0"; bloque.style.left = "0"; bloque.style.right = "0"; bloque.style.zIndex = "5";
        if (rangoSeleccionado.length) rangoSeleccionado[0].appendChild(bloque);
        mostrarAvisoCelda(celdaFin, "✓ Creado visualmente", "ok");
      }
      crearLimpiezaSeleccion();
      creandoTurno = null;
    });

    document.addEventListener("keydown", e => { if (e.key === "Escape" && creandoTurno) { crearLimpiezaSeleccion(); creandoTurno = null; } });
  }

  function crearLimpiezaSeleccion() {
    if (creandoTurno && Array.isArray(creandoTurno.celdasSeleccionadas)) {
      creandoTurno.celdasSeleccionadas.forEach(c => c.classList.remove("bg-blue-100","bg-blue-200","ring","ring-blue-300"));
    }
  }

  // ---------------- util: calcularFechaPorDia según semanaInicial ----------------
  function calcularFechaPorDia(dia) {
    if (!semanaInicial) {
      const hoy = new Date(); semanaInicial = getRangoSemana(hoy).lunes;
    }
    const fecha = new Date(semanaInicial);
    fecha.setDate(semanaInicial.getDate() + (dia - 1));
    const y = fecha.getFullYear(); const m = String(fecha.getMonth() + 1).padStart(2,'0'); const d = String(fecha.getDate()).padStart(2,'0');
    return `${y}-${m}-${d}`;
  }

  // ---------------- Panel resumen ----------------
  function actualizarPanelResumen() {
    document.getElementById("countAsignados") && (document.getElementById("countAsignados").textContent = resumen.totalAsignados);
    document.getElementById("countConflictos") && (document.getElementById("countConflictos").textContent = resumen.conflictos.length);
    const listaConflictos = document.getElementById("listaConflictos");
    if (listaConflictos) listaConflictos.innerHTML = resumen.conflictos.map(c => `<div>• ${c}</div>`).join("");
    const totalTurnos = turnos.length;
    resumen.turnosCompletos = Math.floor(resumen.totalAsignados / 3);
    resumen.turnosVacantes = Math.max(0, totalTurnos - resumen.turnosCompletos);
    document.getElementById("countCompletos") && (document.getElementById("countCompletos").textContent = resumen.turnosCompletos);
    document.getElementById("countVacantes") && (document.getElementById("countVacantes").textContent = resumen.turnosVacantes);
  }

  // ---------------- Init: render layout minimal + listeners ----------------
  const PI = {
    _initialized: false,
    init: async function (opts = {}) {
      if (this._initialized) { console.log("PlanificadorInteractivo: ya inicializado"); return; }
      this._initialized = true;

      const root = document.getElementById("planificador_turnos");
      if (!root) { console.warn("No existe #planificador_turnos"); return; }

      if (!root.dataset.piBuilt) {
        root.innerHTML = `
          <div class="w-full flex gap-4">
            <aside id="pi_sidebar" class="w-80 bg-white p-3 rounded shadow overflow-auto" style="max-height: 70vh;">
              <div class="flex justify-between items-center mb-3">
                <h3 class="font-semibold">Publicadores</h3>
                <button id="pi_reload_btn" class="px-2 py-1 bg-gray-100 rounded text-sm">Recargar</button>
              </div>
              <div id="pi_sidebar_users" class="space-y-2"><div class="text-sm text-gray-500">Cargando usuarios...</div></div>
            </aside>
            <section id="pi_grid_container" class="flex-1 bg-white p-3 rounded shadow overflow-auto">
              <div class="flex justify-between items-center mb-3">
                <h3 class="font-semibold">Semana</h3>
                <div class="flex gap-2 items-center">
                  <input id="pi_fecha_input" type="date" class="border p-1 rounded"/>
                  <select id="pi_filtro_punto" class="border p-1 rounded"><option value="">Todos los puntos</option></select>
                  <button id="pi_apply_date" class="px-3 py-1 bg-blue-500 text-white rounded">Ir</button>
                </div>
              </div>
              <div id="gridSemana" class="overflow-x-auto" style="min-width:700px;">
                <div id="pi_grid_inner" style="min-width:900px;">
                  <div class="text-sm text-gray-500">Calendario vacío (presione "Recargar" o seleccione fecha)</div>
                </div>
              </div>
            </section>
          </div>`;
        root.dataset.piBuilt = "1";
      }

      // elements
      this.el = {
        root,
        sidebarUsers: root.querySelector("#pi_sidebar_users"),
        gridWrap: root.querySelector("#gridSemana"),
        btnReload: root.querySelector("#pi_reload_btn")
      };

      this.el.btnReload?.addEventListener("click", async () => {
        await Promise.all([cargarUsuarios(), loadPuntosFiltro(), renderGridSemana()]);
        actualizarPanelResumen();
      });

      // initial load
      await Promise.all([cargarUsuarios(), loadPuntosFiltro(), renderGridSemana()]);
      await renderUsersList("pi_sidebar_users");
      actualizarPanelResumen();
      console.log("PlanificadorInteractivo: inicializado correctamente");
    }
  };

  window.PlanificadorInteractivo = PI;
})();
