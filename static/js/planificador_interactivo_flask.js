/* planificador_interactivo_flask.js
   Versión completa del PlanificadorInteractivo con init().
   - Construye el DOM necesario dentro de #planificador_turnos
   - Se integra con las funciones globales existentes (cargarTurnos, cargarPuntos, cargarSolicitudes, actualizarPipeline)
   - Protegido contra múltiples inicializaciones
*/

(function () {
  // Evitar redeclarar si ya existe
  if (window.PlanificadorInteractivo && window.PlanificadorInteractivo._initialized) return;

  // Función de utilidad: normaliza texto eliminando tildes y pasando a minúsculas
  function normalizarTexto(str) {
    if (!str) return "";
    return str
      .normalize("NFD")              // separa letras de sus acentos
      .replace(/[\u0300-\u036f]/g, "") // elimina los acentos
      .toLowerCase();                // homogeneiza el caso
  }

  const PI = {
    _initialized: false,
    init: async function (opts = {}) {
      if (this._initialized) {
        console.log("PlanificadorInteractivo: ya inicializado");
        return;
      }
      this._initialized = true;

      // Elemento contenedor principal (creado por index.html)
      const root = document.getElementById("planificador_turnos");
      if (!root) {
        console.warn("PlanificadorInteractivo: no existe #planificador_turnos en el DOM");
        return;
      }

      // Construir estructura interna si está vacía
      if (!root.dataset.piBuilt) {
        root.innerHTML = this._buildLayoutHTML();
        root.dataset.piBuilt = "1";
      }

      // Referencias rápidas
      this.el = {
        root,
        sidebarUsers: root.querySelector("#pi_sidebar_users"),
        gridWrap: root.querySelector("#gridSemana"),
        btnReload: root.querySelector("#pi_reload_btn"),
        btnAutoAssign: document.getElementById("asignarTurno"),
        pipelineArea: document.getElementById("pipelineOutput"),
      };

      // Hook botones principales
      this.el.btnReload?.addEventListener("click", async () => {
        await this.reloadAll();
      });

      // Si existe el botón "Asignar AUTO" global, sobrescribir su comportamiento para integrar
      if (this.el.btnAutoAssign) {
        this._oldAutoAssign = this.el.btnAutoAssign.onclick;
        this.el.btnAutoAssign.onclick = async (ev) => {
          // Confirmación y ejecución
          if (!confirm("¿Ejecutar asignación automática de turnos?")) return;
          await this.ejecutarAsignador();
        };
      }

      // Inicializar data y vistas
      await Promise.all([
        this.renderUsersList(),
        this.renderGridSemana(),
        typeof cargarSelectPuntos === "function" ? cargarSelectPuntos() : Promise.resolve(),
      ]);

      // cargar datos
      if (typeof cargarTurnos === "function") {
        try { await cargarTurnos(); } catch (e) { console.warn("cargarTurnos() falló:", e); }
      }
      if (typeof cargarSolicitudes === "function") {
        try { await cargarSolicitudes(); } catch (e) { console.warn("cargarSolicitudes() falló:", e); }
      }

      // Marcar inicializado
      console.log("PlanificadorInteractivo: inicializado correctamente");
    },

    // HTML del layout principal (sidebar + grid)
    _buildLayoutHTML: function () {
      return `
      <div class="w-full flex gap-4">
        <!-- Sidebar usuarios -->
        <aside id="pi_sidebar" class="w-80 bg-white p-3 rounded shadow overflow-auto" style="max-height: 70vh;">
          <div class="flex justify-between items-center mb-3">
            <h3 class="font-semibold">Publicadores</h3>
            <button id="pi_reload_btn" class="px-2 py-1 bg-gray-100 rounded text-sm">Recargar</button>
          </div>
          <div id="pi_sidebar_users" class="space-y-2">
            <!-- usuarios se insertan aquí -->
            <div class="text-sm text-gray-500">Cargando usuarios...</div>
          </div>
        </aside>

        <!-- Grid semana -->
        <section id="pi_grid_container" class="flex-1 bg-white p-3 rounded shadow overflow-auto">
          <div class="flex justify-between items-center mb-3">
            <h3 class="font-semibold">Semana</h3>
            <div class="flex gap-2 items-center">
              <input id="pi_fecha_input" type="date" class="border p-1 rounded"/>
              <button id="pi_apply_date" class="px-3 py-1 bg-blue-500 text-white rounded">Ir</button>
            </div>
          </div>

          <div id="gridSemana" class="overflow-x-auto" style="min-width:700px;">
            <!-- grid dinámico -->
            <div id="pi_grid_inner" style="min-width:900px;">
              <div class="text-sm text-gray-500">Calendario vacío (presione "Recargar" o seleccione fecha)</div>
            </div>
          </div>
        </section>
      </div>
      `;
    },

    // Renderiza la lista de usuarios (puede usar la API o dejar vacío si no hay endpoint)
    renderUsersList: async function () {
      const container = document.getElementById("pi_sidebar_users");
      if (!container) return;
      container.innerHTML = `<div class="text-sm text-gray-500">Cargando publicadores...</div>`;

      // Intentamos llamar a /api/publicadores (si existe) o sacar de /api/solicitudes
      try {
        // Preferir endpoint público si existe
        let res;
        try {
          res = await fetch('/api/publicadores?action=listar');
        } catch (e) {
          res = null;
        }

        let users = null;
        if (res && res.ok) {
          users = await res.json();
        } else {
          // fallback: si existe 'Publicador' en el backend, tal vez /api/solicitudes devuelve usuarios
          const alt = await fetch('/api/turnos?action=listar');
          if (alt && alt.ok) {
            // no es ideal, pero vaciamos lista de turnos
            users = [];
          } else {
            users = [];
          }
        }

        // Si la lista viene vacía, mostrar placeholder
        if (!users || users.length === 0) {
          container.innerHTML = `<div class="text-sm text-gray-500">No hay publicadores disponibles.</div>`;
          return;
        }

        // Render simple
        container.innerHTML = "";
        users.forEach(u => {
          const el = document.createElement("div");
          el.className = "p-2 border rounded hover:bg-gray-50 flex justify-between items-center";
          el.innerHTML = `<div><div class="font-medium">${u.nombre || u.usuario || ("Usuario " + (u.id||''))}</div>
                          <div class="text-xs text-gray-500">${u.rol || ''} ${u.congregacion ? ' - ' + u.congregacion : ''}</div></div>
                          <div class="text-xs text-gray-400">${u.id || ''}</div>`;
          container.appendChild(el);
        });

      } catch (err) {
        console.warn("renderUsersList error:", err);
        container.innerHTML = `<div class="text-sm text-red-500">Error cargando publicadores</div>`;
      }
    },

    // Construye la vista simplificada de la semana (headers + columnas)
    renderGridSemana: async function (fechaISO) {
      const wrapper = document.getElementById("pi_grid_inner");
      if (!wrapper) return;

      // Si se pasó fecha, usarla, sino tomar hoy
      let fecha = fechaISO || (document.getElementById("pi_fecha_input") && document.getElementById("pi_fecha_input").value) || null;
      if (!fecha) {
        const d = new Date();
        fecha = d.toISOString().slice(0, 10);
        if (document.getElementById("pi_fecha_input")) document.getElementById("pi_fecha_input").value = fecha;
      }

      // Construir headers de 7 días centrados en fecha
      const base = new Date(fecha);
      // Calcula el lunes de la semana que contiene 'base'
      const start = new Date(base);
      // JS: getDay() devuelve 0 (domingo) .. 6 (sábado). Queremos lunes como inicio.
      const dow = start.getDay();
      const offsetToMonday = (dow === 0) ? -6 : (1 - dow); // si domingo(0) -> retrocede 6 días; si lunes(1)->0; etc.
      start.setDate(base.getDate() + offsetToMonday);

      const days = [];
      for (let i = 0; i < 7; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        days.push(d);
      }

      // Construir markup
      const colsHtml = days.map(d => {
        const iso = d.toISOString().slice(0,10);
        const dayName = d.toLocaleDateString('es-ES', { weekday: 'long' });
        const dayShort = d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
        return `<div class="pi-day-column border-l p-2" data-fecha="${iso}" style="min-width:140px;">
                  <div class="font-semibold">${dayName}</div>
                  <div class="text-xs text-gray-500">${dayShort}</div>
                  <div class="pi-day-body mt-2"></div>
                </div>`;
      }).join("");

      wrapper.innerHTML = `<div class="grid grid-cols-7 gap-2">${colsHtml}</div>`;

      // Poblar eventos/turnos
      try {
        const res = await fetch('/api/turnos?accion=listar'); // ← asegúrate de que este es el endpoint correcto
        if (res.ok) {
          const turnos = await res.json();

          // Construir mapa de columnas por fecha ISO y por nombre de día en minúsculas
          const mapCols = {};
          const colNodes = wrapper.querySelectorAll(".pi-day-column");
          colNodes.forEach(n => {
            const fechaCol = n.dataset.fecha;                   // YYYY-MM-DD
            const fechaObj = new Date(fechaCol);
            const diaNombre = fechaObj.toLocaleDateString("es-ES", { weekday: "long" }).toLowerCase(); // "lunes"
            const diaNombreNorm = normalizarTexto(diaNombre);
			const body = n.querySelector(".pi-day-body");
            if (body) {
              mapCols[fechaCol] = body;
              mapCols[diaNombre] = body;
			  mapCols[diaNombreNorm] = body; // <-- también guardamos sin acento
            }
          });

          (turnos || []).forEach(t => {
            // Prioriza fecha ISO si viene, luego dia string
            const fechaTurnoISO = t.fecha || null; // si el backend devolviera fecha completa
            const diaTurno = (t.dia || "").toString().toLowerCase(); // "lunes"
            // Normalizar sin tildes
			const diaTurnoNorm = normalizarTexto(diaTurno);         
            let targetBody = null;
            if (fechaTurnoISO && mapCols[fechaTurnoISO]) targetBody = mapCols[fechaTurnoISO];
            else if (diaTurno && mapCols[diaTurno]) targetBody = mapCols[diaTurno];
            else if (diaTurnoNorm && mapCols[diaTurnoNorm]) targetBody = mapCols[diaTurnoNorm];
            else {
              // También intentar convertir si t.fecha viene en formato "2025-11-03T..." o similar
              if (t.fecha) {
                try {
                  const isoShort = new Date(t.fecha).toISOString().slice(0,10);
                  if (mapCols[isoShort]) targetBody = mapCols[isoShort];
                } catch {}
              }
            }

            // Si encontramos columna objetivo, append, sino append al primero
            const dest = targetBody || (colNodes[0] && colNodes[0].querySelector(".pi-day-body"));
            if (!dest) return;

            const nodo = document.createElement("div");
            nodo.className = "p-2 mb-2 border rounded bg-slate-50";
            const puntoText = (t.punto && typeof t.punto === "string") ? t.punto : ('Punto ' + (t.punto_id||''));
            nodo.innerHTML = `<div class="font-medium">${puntoText}</div>
                              <div class="text-xs text-gray-600">${t.hora_inicio || ''} - ${t.hora_fin || ''}</div>`;
            dest.appendChild(nodo);
          });
        } else {
          console.warn("renderGridSemana: /api/turnos respondió con status", res.status);
        }
      } catch (e) {
        console.warn("No se pudieron cargar turnos para el grid:", e);
      }

      // Hook del botón 'Ir' para cambiar fecha
      const btn = document.getElementById("pi_apply_date");
      if (btn) {
        btn.onclick = async () => {
          const newDate = document.getElementById("pi_fecha_input").value;
          await this.renderGridSemana(newDate);
        };
      }
    },

    // Ejecuta el asignador automático llamando al endpoint Flask adecuado
    ejecutarAsignador: async function (fecha) {
      try {
        const body = fecha ? { fecha } : { };
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

        // Actualizar UI
        if (data.assigned) {
          alert(`Asignaciones realizadas: ${data.assigned.length}`);
        } else if (data.procesados !== undefined) {
          alert(`Procesados: ${data.procesados}`);
        } else {
          alert("Asignador ejecutado.");
        }

        // actualizar vista y pipeline
        if (typeof cargarTurnos === "function") await cargarTurnos();
        if (typeof actualizarPipeline === "function") actualizarPipeline();

        return data;
      } catch (err) {
        console.error("ejecutarAsignador error:", err);
        alert("Error al ejecutar el asignador: " + (err.message || err));
        return { error: err.message || String(err) };
      }
    },

    // Reload general (users + grid + data)
    reloadAll: async function () {
      await Promise.all([
        this.renderUsersList(),
        this.renderGridSemana(),
        typeof cargarTurnos === "function" ? cargarTurnos() : Promise.resolve(),
        typeof cargarSolicitudes === "function" ? cargarSolicitudes() : Promise.resolve(),
      ]);
      if (typeof actualizarPipeline === "function") actualizarPipeline();
    }
  };

  // Exportar globalmente
  window.PlanificadorInteractivo = PI;
  // marcar inicializado si se llama init
  // (el flag _initialized se gestiona en init())
})();

/* Fin del planificador_interactivo_flask.js */
