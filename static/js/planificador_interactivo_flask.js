/* planificador_interactivo_flask.js
   PlanificadorInteractivo con init(), grid semanal y asignación de turnos
   - Filtrado por semana y por Punto de Predicación
   - Fechas parseadas como locales para evitar desfase
*/

(function () {
  if (window.PlanificadorInteractivo && window.PlanificadorInteractivo._initialized) return;

  // Normaliza texto eliminando tildes y pasando a minúsculas
  function normalizarTexto(str) {
    if (!str) return "";
    return str
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  // Parse YYYY-MM-DD como fecha local (no UTC)
  function parseDateLocal(dateStr) {
    const [y,m,d] = dateStr.split('-').map(Number);
    return new Date(y, m-1, d);
  }

  // Convertir Date local a string YYYY-MM-DD
  function formatDateLocalFromDate(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth()+1).padStart(2,'0');
    const d = String(dateObj.getDate()).padStart(2,'0');
    return `${y}-${m}-${d}`;
  }

  const PI = {
    _initialized: false,

    init: async function (opts = {}) {
      if (this._initialized) {
        console.log("PlanificadorInteractivo: ya inicializado");
        return;
      }
      this._initialized = true;

      const root = document.getElementById("planificador_turnos");
      if (!root) {
        console.warn("PlanificadorInteractivo: no existe #planificador_turnos en el DOM");
        return;
      }

      if (!root.dataset.piBuilt) {
        root.innerHTML = this._buildLayoutHTML();
        root.dataset.piBuilt = "1";
      }

      this.el = {
        root,
        sidebarUsers: root.querySelector("#pi_sidebar_users"),
        gridWrap: root.querySelector("#gridSemana"),
        btnReload: root.querySelector("#pi_reload_btn"),
        btnAutoAssign: document.getElementById("asignarTurno"),
        pipelineArea: document.getElementById("pipelineOutput"),
      };

      this.el.btnReload?.addEventListener("click", async () => {
        await this.reloadAll();
      });

      if (this.el.btnAutoAssign) {
        this._oldAutoAssign = this.el.btnAutoAssign.onclick;
        this.el.btnAutoAssign.onclick = async () => {
          if (!confirm("¿Ejecutar asignación automática de turnos?")) return;
          await this.ejecutarAsignador();
        };
      }

      await Promise.all([
        this.renderUsersList(),
        this.loadPuntosFiltro(),
        this.renderGridSemana(),
        typeof cargarSelectPuntos === "function" ? cargarSelectPuntos() : Promise.resolve(),
      ]);

      if (typeof cargarTurnos === "function") {
        try { await cargarTurnos(); } catch (e) { console.warn("cargarTurnos() falló:", e); }
      }
      if (typeof cargarSolicitudes === "function") {
        try { await cargarSolicitudes(); } catch (e) { console.warn("cargarSolicitudes() falló:", e); }
      }

      console.log("PlanificadorInteractivo: inicializado correctamente");
    },

    _buildLayoutHTML: function () {
      return `
      <div class="w-full flex gap-4">
        <aside id="pi_sidebar" class="w-80 bg-white p-3 rounded shadow overflow-auto" style="max-height: 70vh;">
          <div class="flex justify-between items-center mb-3">
            <h3 class="font-semibold">Publicadores</h3>
            <button id="pi_reload_btn" class="px-2 py-1 bg-gray-100 rounded text-sm">Recargar</button>
          </div>
          <div id="pi_sidebar_users" class="space-y-2">
            <div class="text-sm text-gray-500">Cargando usuarios...</div>
          </div>
        </aside>

        <section id="pi_grid_container" class="flex-1 bg-white p-3 rounded shadow overflow-auto">
          <div class="flex justify-between items-center mb-3">
            <h3 class="font-semibold">Semana</h3>
            <div class="flex gap-2 items-center">
              <input id="pi_fecha_input" type="date" class="border p-1 rounded"/>
              <select id="pi_filtro_punto" class="border p-1 rounded">
                <option value="">Todos los puntos</option>
              </select>
              <button id="pi_apply_date" class="px-3 py-1 bg-blue-500 text-white rounded">Ir</button>
            </div>
          </div>

          <div id="gridSemana" class="overflow-x-auto" style="min-width:700px;">
            <div id="pi_grid_inner" style="min-width:900px;">
              <div class="text-sm text-gray-500">Calendario vacío (presione "Recargar" o seleccione fecha)</div>
            </div>
          </div>
        </section>
      </div>
      `;
    },

    renderUsersList: async function () {
      const container = document.getElementById("pi_sidebar_users");
      if (!container) return;
      container.innerHTML = `<div class="text-sm text-gray-500">Cargando publicadores...</div>`;

      try {
        let res;
        try { res = await fetch('/api/postulantes?accion=listar_disponibles'); } catch { res = null; }
        let users = res && res.ok ? await res.json() : [];

        if (!users || users.length === 0) {
          container.innerHTML = `<div class="text-sm text-gray-500">No hay publicadores disponibles.</div>`;
          return;
        }

        container.innerHTML = "";
        users.forEach(u => {
          const el = document.createElement("div");
          el.className = "p-2 border rounded hover:bg-gray-50 flex justify-between items-center";
          el.innerHTML = `<div><div class="font-medium">${u.nombre || u.usuario || ("Usuario " + (u.id||''))} ${u.apellido || ""}</div>
                          <div class="text-xs text-gray-500">${u.rol || ''} ${u.congregacion ? ' - ' + u.congregacion : ''}</div></div>
                          <div class="text-xs text-gray-400">${u.id || ''}</div>`;
          container.appendChild(el);
        });
      } catch (err) {
        console.warn("renderUsersList error:", err);
        container.innerHTML = `<div class="text-sm text-red-500">Error cargando publicadores</div>`;
      }
    },

    // Cargar puntos para el select de filtro
    loadPuntosFiltro: async function(fechaISO) {
      const select = document.getElementById("pi_filtro_punto");
      if (!select) return;
      select.innerHTML = `<option value="">Todos los puntos</option>`;
      const fecha = fechaISO || document.getElementById("pi_fecha_input")?.value;
      if (!fecha) return;

      try {
        const res = await fetch(`/api/turnos?accion=puntos_disponibles&fecha=${fecha}`);
        if (!res.ok) return;
        const puntos = await res.json();
        puntos.forEach(p => {
          const opt = document.createElement("option");
          opt.value = p.id;
          opt.textContent = p.nombre;
          select.appendChild(opt);
        });
      } catch (e) {
        console.warn("Error cargando puntos para filtro:", e);
      }

      // onchange para filtrar grid
      select.onchange = async () => {
        await this.renderGridSemana(fecha);
      };
    },

    renderGridSemana: async function (fechaISO) {
      const wrapper = document.getElementById("pi_grid_inner");
      if (!wrapper) return;

      let fecha = fechaISO || document.getElementById("pi_fecha_input")?.value;
      if (!fecha) {
        const d = new Date();
        fecha = formatDateLocalFromDate(d);
        document.getElementById("pi_fecha_input").value = fecha;
      }

      // Calcular semana (lunes a domingo)
      const base = parseDateLocal(fecha);
      const dow = base.getDay();
      const diff = (dow === 0 ? -6 : 1 - dow);
      const start = new Date(base);
      start.setDate(base.getDate() + diff);

      const days = [];
      for (let i=0; i<7; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        days.push(d);
      }

      // Construir columnas
      const colsHtml = days.map(d => {
        const iso = formatDateLocalFromDate(d);
        const dayName = d.toLocaleDateString('es-ES', { weekday: 'long' });
        const dayShort = d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
        return `<div class="pi-day-column border-l p-2" data-fecha="${iso}" style="min-width:140px;">
                  <div class="font-semibold">${dayName}</div>
                  <div class="text-xs text-gray-500">${dayShort}</div>
                  <div class="pi-day-body mt-2"></div>
                </div>`;
      }).join("");

      wrapper.innerHTML = `<div class="grid grid-cols-7 gap-2">${colsHtml}</div>`;

      // Fetch turnos para la semana
      try {
        const startISO = formatDateLocalFromDate(days[0]);
        const endISO = formatDateLocalFromDate(days[6]);
        const res = await fetch(`/api/turnos?accion=listar_por_rango&desde=${startISO}&hasta=${endISO}`);
        if (!res.ok) return;
        const turnosObj = await res.json();
        const turnos = Object.values(turnosObj).flat();

        const filtroPunto = document.getElementById("pi_filtro_punto")?.value;

        const mapCols = {};
        const colNodes = wrapper.querySelectorAll(".pi-day-column");
        colNodes.forEach(n => {
          const fechaCol = n.dataset.fecha;
          const fechaObj = parseDateLocal(fechaCol);
          const diaNombre = fechaObj.toLocaleDateString("es-ES", { weekday: 'long' }).toLowerCase();
          const diaNombreNorm = normalizarTexto(diaNombre);
          const body = n.querySelector(".pi-day-body");
          if (body) {
            mapCols[fechaCol] = body;
            mapCols[diaNombre] = body;
            mapCols[diaNombreNorm] = body;
          }
        });

        (turnos || []).forEach(t => {
          if (filtroPunto && t.punto_id != filtroPunto) return; // FILTRO

          const fechaTurnoISO = t.fecha || null;
          const diaTurno = (t.dia || "").toLowerCase();
          const diaTurnoNorm = normalizarTexto(diaTurno);
          let targetBody = null;

          if (fechaTurnoISO && mapCols[fechaTurnoISO]) targetBody = mapCols[fechaTurnoISO];
          else if (diaTurno && mapCols[diaTurno]) targetBody = mapCols[diaTurno];
          else if (diaTurnoNorm && mapCols[diaTurnoNorm]) targetBody = mapCols[diaTurnoNorm];
          else if (t.fecha) {
            const isoShort = formatDateLocalFromDate(parseDateLocal(t.fecha));
            if (mapCols[isoShort]) targetBody = mapCols[isoShort];
          }

          const dest = targetBody || (colNodes[0]?.querySelector(".pi-day-body"));
          if (!dest) return;

          const nodo = document.createElement("div");
          nodo.className = "p-2 mb-2 border rounded bg-slate-50";
          const puntoText = (t.punto && typeof t.punto === "string") ? t.punto : ('Punto ' + (t.punto_id||''));
          nodo.innerHTML = `<div class="font-medium">${puntoText}</div>
                            <div class="text-xs text-gray-600">${t.hora_inicio || ''} - ${t.hora_fin || ''}</div>`;
          dest.appendChild(nodo);
        });

      } catch (e) {
        console.warn("No se pudieron cargar turnos para el grid:", e);
      }

      // Botón 'Ir' cambia fecha y recarga select y grid
      const btn = document.getElementById("pi_apply_date");
      if (btn) {
        btn.onclick = async () => {
          const newDate = document.getElementById("pi_fecha_input").value;
          await this.loadPuntosFiltro(newDate);
          await this.renderGridSemana(newDate);
        };
      }
    },

    ejecutarAsignador: async function (fecha) {
      try {
        const body = fecha ? { fecha } : {};
        const res = await fetch('/api/bot_asignador', {
          method: "POST",
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const data = await (async () => {
          const text = await res.text();
          try { return JSON.parse(text); } catch { return { error: text }; }
        })();

        if (!res.ok) {
          console.error("Error bot_asignador:", data);
          alert("Error ejecutando asignador: " + (data.msg || data.error || res.status));
          return data;
        }

        if (data.assigned) alert(`Asignaciones realizadas: ${data.assigned.length}`);
        else if (data.procesados !== undefined) alert(`Procesados: ${data.procesados}`);
        else alert("Asignador ejecutado.");

        if (typeof cargarTurnos === "function") await cargarTurnos();
        if (typeof actualizarPipeline === "function") actualizarPipeline();
        return data;
      } catch (err) {
        console.error("ejecutarAsignador error:", err);
        alert("Error al ejecutar el asignador: " + (err.message || err));
        return { error: err.message || String(err) };
      }
    },

    reloadAll: async function () {
      await Promise.all([
        this.renderUsersList(),
        this.loadPuntosFiltro(),
        this.renderGridSemana(),
        typeof cargarTurnos === "function" ? cargarTurnos() : Promise.resolve(),
        typeof cargarSolicitudes === "function" ? cargarSolicitudes() : Promise.resolve(),
      ]);
      if (typeof actualizarPipeline === "function") actualizarPipeline();
    }
  };

  window.PlanificadorInteractivo = PI;
})();
