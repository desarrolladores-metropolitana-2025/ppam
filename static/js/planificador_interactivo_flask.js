// planificador_interactivo_flask_jquery.js
// Versión jQuery adaptada al backend Flask (/api/turnos, /api/postulantes)
// Clon 1:1 del comportamiento del planificador_interactivo.js original (PHP)
// Opción A: mismo flujo de llamadas, mismos nombres de variables y safeFetch

(function (window, $) {
  "use strict";

  // API bases solicitadas
  const apiBaseTurnos = "/api/turnos";
  const apiBasePost   = "/api/postulantes";

  // safeFetch: wrapper que usa jQuery.ajax y devuelve Promise que resuelve JSON (o lanza error)
  function safeFetch(url, opts = {}) {
    // opts can include method, headers, body (object or string)
    const method = (opts.method || "GET").toUpperCase();
    const contentType = (opts.headers && opts.headers["Content-Type"]) || opts.contentType || "application/json";
    let data = opts.body;

    // if body is object and content-type json, stringify
    if (data && contentType.indexOf("application/json") !== -1 && typeof data !== "string") {
      data = JSON.stringify(data);
    }

    return new Promise((resolve, reject) => {
      $.ajax({
        url,
        method,
        data: data,
        contentType: contentType,
        processData: false, // we'll send stringified JSON or FormData; let jQuery not process by default
        dataType: "json",
        success: function (resp) {
          resolve(resp);
        },
        error: function (jqXHR, textStatus, errorThrown) {
          // try parse JSON error body if possible
          let parsed = null;
          try { parsed = jqXHR.responseJSON || JSON.parse(jqXHR.responseText); } catch (e) {}
          const err = {
            status: jqXHR.status,
            statusText: jqXHR.statusText || textStatus,
            body: parsed || jqXHR.responseText || errorThrown
          };
          reject(err);
        }
      });
    });
  }

  // Utilities
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
    fechaTemp.setHours(horas + horasASumar, minutos, 0);
    const nuevasHoras = fechaTemp.getHours().toString().padStart(2, '0');
    const nuevosMinutos = fechaTemp.getMinutes().toString().padStart(2, '0');
    return `${nuevasHoras}:${nuevosMinutos}`;
  }

  // Module object
  const PlanificadorInteractivo = (function () {
    let semanaInicial = null;
    let offsetSemanas = 0;
    let semanaBase = null; // usado en renderSemana
    let usuarios = [];
    let turnos = [];
    let resumen = {
      totalAsignados: 0,
      turnosCompletos: 0,
      turnosVacantes: 0,
      conflictos: []
    };

    /* ------------------- INIT ------------------- */
    async function init() {
      const contenedor = document.getElementById("planificador_turnos");
      if (!contenedor) return console.error("Falta div #planificador_turnos");

      // Render HTML como en el original
      contenedor.innerHTML = `
        <div class="flex gap-4 p-4">
          <div class="flex-1 flex flex-col gap-4">
            <div id="encabezadoDiario" class="flex justify-between items-center mb-3">
              <h2 class="font-bold text-xl text-indigo-700">🧩 Planificador Interactivo</h2>
              <p class="text-gray-600 text-sm mb-4">Arrastrá un usuario sobre un turno para planificarlo manualmente.</p>
              <button id="btnPlanificarTurnos" class="px-3 py-1 bg-indigo-500 text-white rounded hover:bg-indigo-600">
                📅 Ver semanal
              </button>
            </div>

            <div id="listaPlanificarTurnos" class="grid grid-cols-[260px_1fr_260px] gap-4">
              <div id="titUsuarios">
                <h3 class="font-semibold mb-2">Usuarios disponibles</h3>
                <div id="usuariosList" class="bg-white rounded shadow p-2 h-[420px] overflow-y-auto"></div>
              </div>

              <div id="titTurnos">
                <h3 class="font-semibold mb-2">Turnos</h3>
                <div id="turnosListPlanif" class="bg-white rounded shadow p-2 h-[420px] overflow-y-auto"></div>
              </div>

              <div id="listaResumenes" class="bg-gray-50 border border-gray-200 rounded p-3 flex flex-col gap-3 shadow-sm">
                <h3 class="font-semibold text-lg mb-2">Resumen</h3>
                <div class="text-sm space-y-1">
                  <div>✅ <b id="countAsignados">0</b> asignaciones</div>
                  <div>🟢 <b id="countCompletos">0</b> turnos completos</div>
                  <div>🟡 <b id="countVacantes">0</b> turnos con vacantes</div>
                  <div>🔴 <b id="countConflictos">0</b> conflictos</div>
                </div>
                <div class="mt-3">
                  <h4 class="font-semibold mb-1 text-sm text-gray-700">Conflictos detectados:</h4>
                  <div id="listaConflictos" class="text-xs text-red-600 max-h-[200px] overflow-y-auto"></div>
                </div>
              </div>
            </div>

            <div id="planificadorSemanal" class="hidden">
              <div class="flex justify-between items-center mb-3">
                <h2 class="font-bold text-xl text-indigo-700">📆 Planificador Semanal</h2>
                <button id="btnVolverLista" class="px-3 py-1 bg-indigo-500 text-white rounded hover:bg-indigo-600">← Volver a vista diaria</button>
              </div>
              <div class="flex justify-between items-center mb-3">
                <button id="btnPrevSemana" class="flex items-center justify-center w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 hover:bg-indigo-200 shadow">&#8592;</button>
                <h2 id="tituloSemana" class="font-bold text-xl text-indigo-700">📆 Semana</h2>
                <button id="btnNextSemana" class="flex items-center justify-center w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 hover:bg-indigo-200 shadow">&#8594;</button>
              </div>

              <div class="flex gap-4">
                <div id="usuariosListSemana" class="w-64 bg-white rounded shadow p-2 overflow-y-auto h-[600px]">
                  <h4 class="font-semibold mb-2">Usuarios</h4>
                  <div id="usuariosSemana"></div>
                </div>
                <div id="gridSemana" class="flex-1 relative border rounded overflow-x-auto bg-white shadow-inner"></div>
              </div>
            </div>

          </div>
        </div>
      `;

      // Bind buttons
      $("#btnPrevSemana").on("click", () => cambiarSemana(-1));
      $("#btnNextSemana").on("click", () => cambiarSemana(1));

      $("#btnPlanificarTurnos").on("click", async () => {
        $("#listaResumenes").addClass("hidden");
        $("#listaConflictos").addClass("hidden");
        $("#titUsuarios").addClass("hidden");
        $("#titTurnos").addClass("hidden");
        $("#turnosListPlanif").addClass("hidden");
        $("#encabezadoDiario").addClass("hidden");
        $("#usuariosList").addClass("hidden");

        $("#planificadorSemanal").removeClass("hidden");
        await cambiarSemana(0);
        renderUsuariosSemana();
      });

      $("#btnVolverLista").on("click", () => {
        $("#planificadorSemanal").addClass("hidden");
        $("#encabezadoDiario").removeClass("hidden");
        $("#turnosListPlanif").removeClass("hidden");
        $("#listaResumenes").removeClass("hidden");
        $("#listaConflictos").removeClass("hidden");
        $("#usuariosList").removeClass("hidden");
        $("#titUsuarios").removeClass("hidden");
        $("#titTurnos").removeClass("hidden");
      });

      // Cargar datos
      await Promise.all([cargarUsuarios(), cargarTurnos()]);
      renderUsuarios();
      renderTurnos();
      actualizarPanelResumen();
    }

    /* ------------------- CARGA DATOS ------------------- */

    async function cargarUsuarios() {
      try {
        const url = `${apiBasePost}?accion=listar_disponibles`;
        const data = await safeFetch(url);
        usuarios = Array.isArray(data) ? data : [];
      } catch (err) {
        console.error("Error cargarUsuarios:", err);
        usuarios = [];
      }
    }

    async function cargarTurnos() {
      try {
        const url = `${apiBaseTurnos}?accion=listar`;
        const data = await safeFetch(url);
        turnos = Array.isArray(data) ? data : [];
      } catch (err) {
        console.error("Error cargarTurnos:", err);
        turnos = [];
      }
    }

    /* ------------------- RENDERIZACION DIARIA ------------------- */

    function renderUsuarios() {
      const $list = $("#usuariosList").empty();
      usuarios.forEach(u => {
        const text = u.full_name || u.nombre || u.usuario || (u.usuario ? u.usuario : `Usuario ${u.id || ''}`);
        const $el = $(`<div class="draggable-user bg-blue-50 border border-blue-200 rounded p-2 mb-1 cursor-move"></div>`);
        $el.attr("draggable", true);
        $el.data("userId", u.id);
        $el.text(text);
        // native drag events
        $el.on("dragstart", function (ev) {
          ev.originalEvent.dataTransfer.setData("userId", $(this).data("userId"));
          ev.originalEvent.dataTransfer.effectAllowed = "move";
        });
        $list.append($el);
      });

      if (usuarios.length === 0) {
        $list.html('<div class="text-sm text-gray-500">No hay publicadores disponibles.</div>');
      }
    }

    function renderTurnos() {
      const $list = $("#turnosListPlanif").empty();
      // agrupar por fecha
      const grupos = {};
      turnos.forEach(t => {
        if (!grupos[t.fecha]) grupos[t.fecha] = [];
        grupos[t.fecha].push(t);
      });
      const fechasOrdenadas = Object.keys(grupos).sort((a, b) => new Date(a) - new Date(b));
      fechasOrdenadas.forEach(fecha => {
        const dayContainer = $("<div class='mb-6'></div>");
        const [yy, mm, dd] = (fecha || "").split("-").map(Number);
        const d = new Date(yy, (mm || 1) - 1, dd || 1);
        const diasArr = ["Domingo","Lunes","Martes","Miércoles","Jueves","Viernes","Sábado"];
        const nombreDia = diasArr[d.getDay()] || fecha;
        const encabezado = $(`<div class="font-bold text-lg mb-2 text-indigo-700 flex items-center gap-2"><span>🗓️</span> ${nombreDia} ${dd}/${mm}</div>`);
        dayContainer.append(encabezado);

        const inner = $('<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"></div>');
        grupos[fecha].forEach(t => {
          const el = $(`
            <div class="drop-turno bg-gray-50 border border-gray-300 rounded p-3 shadow-sm hover:shadow-md transition cursor-pointer">
              <div class="font-semibold">${t.hora_inicio} - ${t.hora_fin}</div>
              <div class="text-sm text-gray-500 mb-1">${t.punto || ''}</div>
              <div class="h-3 bg-gray-200 rounded overflow-hidden mb-2">
                <div class="h-full transition-all duration-300" style="width:0%"></div>
              </div>
              <div class="text-xs text-gray-700 mb-1">${(t.asignados||0)}/${t.maximo_publicadores||3} cubiertos (0%)</div>
              <div class="asignados text-sm text-gray-700 italic"></div>
            </div>
          `);
          el.data("turno", t);
          el.attr("data-turno-id", t.id);
          el.attr("data-fecha", t.fecha);
          el.attr("data-hora-inicio", t.hora_inicio);
          el.attr("data-hora-fin", t.hora_fin);
          el.attr("data-punto-id", t.punto_id);

          const asignados = t.asignados || 0;
          const max = t.maximo_publicadores || 3;
          const pct = Math.round((Math.min(asignados / max, 1)) * 100);
          let color = "bg-red-400";
          if (pct >= 80) color = "bg-green-500";
          else if (pct >= 40) color = "bg-yellow-400";
          el.find(".h-3 > div").addClass(color).css("width", pct + "%");
          el.find(".text-xs").text(`${asignados}/${max} cubiertos (${pct}%)`);

          // allow drop
          el.on("dragover", function (ev) { ev.preventDefault(); });
          el.on("drop", function (ev) { ev.preventDefault(); onDropUsuario(ev.originalEvent, this); });

          inner.append(el);
        });

        dayContainer.append(inner);
        $list.append(dayContainer);
      });

      if (fechasOrdenadas.length === 0) {
        $list.html('<div class="text-sm text-gray-500">No hay turnos para mostrar.</div>');
      }
    }

    /* ------------------- DRAG & DROP / ASIGNACION ------------------- */

    function onDropUsuario(ev, element) {
      // ev: native event, element: DOM node (target .drop-turno)
      try {
        ev.preventDefault();
        const dt = ev.dataTransfer;
        const userId = dt.getData("userId");
        const $box = $(element);
        const turnoId = $box.data("turno-id");

        if (!$box || !userId) {
          console.error("drop sin box o userId");
          return;
        }

        // si no hay turnoId pero es la vista semanal con bloques (buscamos)
        const bloqueExistente = $box.find(".has-turno, .turno-bloque, .bg-green-500, .bg-yellow-400, .bg-red-400");
        if (!turnoId && bloqueExistente.length) {
          const hora = $box.data("hora");
          const dia = $box.data("dia");
          const fecha = calcularFechaPorDia(parseInt(dia));
          const turnoMatch = turnos.find(t => t.fecha === fecha && t.hora_inicio === hora);
          if (turnoMatch) {
            $box.data("turno-id", turnoMatch.id);
          }
        }

        let $asignadosBox = $box.find(".asignados");
        if ($asignadosBox.length === 0) {
          $asignadosBox = $('<div class="asignados text-xs text-gray-600 italic"></div>');
          $box.append($asignadosBox);
        }

        // Si la celda es de la vista timeline sin turno_id, procesamos para crear/usar turno según hora/dia
        if (!$box.data("turno-id") && $box.data("dia")) {
          const dia = parseInt($box.data("dia"));
          const hora = $box.data("hora");
          let fecha = calcularFechaPorDia(dia);

          // normalizar a ISO
          let fechaISO = fecha && fecha.indexOf("/") !== -1 ? fecha.split("/").reverse().join("-") : fecha;

          mostrarAvisoCelda($box, `Intentando asignar usuario ${userId} en ${fechaISO} ${hora}`, "ok");
          // Pedimos turnos para ese día via API listar_por_rango
          const url = `${apiBaseTurnos}?accion=listar_por_rango&desde=${fechaISO}&hasta=${fechaISO}`;
          safeFetch(url).then(turnosDia => {
            // turnosDia es objeto por fecha
            const posibles = (turnosDia[fechaISO] || []).filter(t => {
              const hI = Number(t.hora_inicio.split(":")[0]) + Number(t.hora_inicio.split(":")[1]) / 60;
              const hF = Number(t.hora_fin.split(":")[0]) + Number(t.hora_fin.split(":")[1]) / 60;
              const [hSelH, hSelM] = (hora || "00:00").split(":").map(Number);
              const hSel = hSelH + (hSelM || 0) / 60;
              return hSel >= hI && hSel < hF;
            });

            (async () => {
              if ((posibles || []).length > 0) {
                // si hay varios, mostrar selector
                let turnoElegido = posibles[0];
                if (posibles.length > 1) {
                  turnoElegido = await mostrarSelectorTurno(posibles);
                  if (!turnoElegido) {
                    console.log("Usuario canceló selección de turno existente");
                    return;
                  }
                }

                // validar disponibilidad
                const params = new URLSearchParams({
                  accion: "validar_disponibilidad",
                  usuario_id: userId,
                  fecha: turnoElegido.fecha,
                  hora_inicio: padTimeToHHMM(turnoElegido.hora_inicio),
                  hora_fin: padTimeToHHMM(turnoElegido.hora_fin),
                  punto_id: turnoElegido.punto_id || ""
                });
                try {
                  const valid = await safeFetch(`${apiBasePost}?${params.toString()}`);
                  if (!valid.ok) {
                    $box.addClass("bg-red-100");
                    mostrarAvisoCelda($box, `❌ Usuario no disponible: ${valid.motivo}`, "error");
                    return;
                  }

                  // asignar manual
                  const asignResp = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: { turno_id: turnoElegido.id, usuario_id: userId, rol: "publicador" }
                  });

                  if (asignResp.ok) {
                    const overlay = $('<div class="absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow"></div>');
                    const nombreCorto = (usuarios.find(u => u.id == userId) || {}).nombre || ((usuarios.find(u => u.id == userId)||{}).full_name||"Usuario");
                    overlay.text(`✓ ${ (typeof nombreCorto === "string" ? nombreCorto.split(' ')[0] : nombreCorto) }`);
                    $box.append(overlay);
                    resumen.totalAsignados++;
                    actualizarPanelResumen();
                    mostrarAvisoCelda($box, "✓ Asignado", "ok");
                  } else {
                    console.error("Error asignando usuario:", asignResp);
                    mostrarAvisoCelda($box, "✗ Error al asignar", "error");
                  }
                } catch (err) {
                  console.error("Error validación/asignación:", err);
                  mostrarAvisoCelda($box, "✗ Error al validar/asignar", "error");
                }
                return;
              }

              // Si no hay turnos existentes -> crear uno nuevo mediante popup
              mostrarAvisoCelda($box, "✗ No existe turno en esta ubicación", "error");
              const horaFin = sumarHoras(hora, 1);
              const result = await mostrarPopupCreacionTurno(fechaISO, hora, horaFin, $box);
              if (!result || !result.ok) {
                mostrarAvisoCelda($box, "✗ turno cancelado", "error");
                return;
              }

              // luego, buscamos el turno recién creado
              try {
                const resp2 = await safeFetch(`${apiBaseTurnos}?accion=listar_por_rango&desde=${fechaISO}&hasta=${fechaISO}`);
                const turnosDia2 = resp2 || {};
                const turnoNuevo = (turnosDia2[fechaISO] || []).find(t => t.hora_inicio === result.hora_inicio && t.hora_fin === result.hora_fin);
                if (!turnoNuevo) {
                  console.error("No se encontró el turno recién creado.");
                  mostrarAvisoCelda($box, "✗ No se encontró turno creado", "error");
                  return;
                }

                // asignar al usuario al turno nuevo
                const respAsign = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: { turno_id: turnoNuevo.id, usuario_id: userId, rol: "publicador" }
                });

                if (respAsign.ok) {
                  const overlay = $('<div class="absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow"></div>');
                  overlay.text("✓ " + ((usuarios.find(u => u.id == userId) || {}).nombre || "Usuario").split(' ')[0]);
                  $box.append(overlay);
                  resumen.totalAsignados++;
                  actualizarPanelResumen();
                  mostrarAvisoCelda($box, "✓ Creado visualmente", "ok");
                } else {
                  console.error("Error asignando tras crear turno:", respAsign);
                  mostrarAvisoCelda($box, "✗ Turno: " + (respAsign.error || "error"), "error");
                }
              } catch (err) {
                console.error("Error buscando turno nuevo:", err);
                mostrarAvisoCelda($box, "✗ Error buscando turno", "error");
              }
            })();

          }).catch(err => {
            console.error("Error cargando turnosDia:", err);
            mostrarAvisoCelda($box, "✗ Error leyendo turnos día", "error");
          });

          return;
        }

        // Si llegamos hasta acá -> tenemos turnoId (asignación en la lista diaria)
        const turno = turnos.find(t => t.id == $box.data("turno-id"));
        const user = usuarios.find(u => u.id == userId);
        if (!turno || !user) {
          console.warn("turno o usuario no encontrados localmente, re-cargando semana/lista.");
        }

        if ($box && turno) {
          $box.addClass("opacity-50");
          $box.attr("title", "Validando disponibilidad...");
        }

        // validación previa
        const params = new URLSearchParams({
          accion: "validar_disponibilidad",
          usuario_id: userId,
          fecha: turno.fecha,
          hora_inicio: turno.hora_inicio,
          hora_fin: turno.hora_fin,
          punto_id: turno.punto_id,
          rol: "publicador"
        });

        const urlValid = `${apiBasePost}?${params.toString()}`;
        safeFetch(urlValid).then(async (data) => {
          if ($box) {
            if (data.ok) {
              $box.removeClass("opacity-50");
              $box.addClass("bg-green-100");
              $box.attr("title", "✅ Cumple criterios");
              mostrarAvisoCelda($box, "✓ Cumple criterios", "ok");
            } else {
              $box.addClass("bg-red-100");
              $box.attr("title", "❌ " + (data.motivo || ""));
              mostrarAvisoCelda($box, "✗ Turno: " + (data.motivo || 'no válido'), "error");
            }
          }

          if (!data.ok) {
            $box.addClass("border-red-400");
            resumen.conflictos.push(`${user ? (user.nombre || user.full_name) : userId} → ${turno.fecha} (${data.motivo})`);
            $asignadosBox.html(`<span class="text-red-600">✗ ${user ? (user.nombre || user.full_name) : userId}: ${data.motivo || 'no válido'}</span>`);
            actualizarPanelResumen();
            return;
          }

          // asignar
          try {
            const postData = { turno_id: turno.id, usuario_id: userId, rol: "publicador" };
            const resp = await safeFetch(`${apiBaseTurnos}?accion=asignar_manual`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: postData
            });

            if (resp.ok) {
              $box.removeClass("border-gray-300 border-red-400");
              $box.addClass("border-green-500");
              $asignadosBox.append(`<div class="text-green-700">✓ ${(user && (user.nombre || user.full_name)) || 'Usuario'} asignado</div>`);
              if ($box.closest("#gridSemana").length) {
                const overlay = $(`<div class="absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow"></div>`);
                overlay.text(((user && (user.nombre || user.full_name)) || "Usuario").split(' ')[0]);
                $box.append(overlay);
                mostrarAvisoCelda($box, "✓ "+ (((user && (user.nombre || user.full_name)) || "Usuario").split(' ')[0]) + ": Asignado", "ok");
              }
              resumen.totalAsignados++;
              actualizarPanelResumen();
              actualizarBarraProgreso(turno.id);
            } else {
              $box.addClass("border-red-400");
              $asignadosBox.html(`<span class="text-red-600">✗ Error al asignar</span>`);
              console.error("Error asignar:", resp);
              if ($box.closest("#gridSemana").length) {
                mostrarAvisoCelda($box, `Error : ${resp.error || 'error'} usuario : ${userId} Turno : ${turno.id}`, "error");
              }
            }
          } catch (err) {
            console.error("Error en asignación:", err);
            $box.addClass("border-red-500");
          }
        }).catch(err => {
          console.error("Error validando disponibilidad:", err);
          $box.addClass("border-red-500");
        });

      } catch (err) {
        console.error("onDropUsuario general error:", err);
      }
    } // onDropUsuario

    /* ------------------- actualiza barra de progreso ------------------- */
    function actualizarBarraProgreso(turnoId) {
      const turno = turnos.find(t => t.id == turnoId);
      if (!turno) return;
      // actualizar count local (simple)
      turno.asignados = (turno.asignados || 0) + 1;
      const asignados = turno.asignados;
      const max = turno.maximo_publicadores || 3;
      const pct = Math.round((asignados / max) * 100);
      let color = "bg-red-400";
      if (pct >= 80) color = "bg-green-500";
      else if (pct >= 40) color = "bg-yellow-400";
      const $box = $(`.drop-turno[data-turno-id="${turnoId}"]`);
      const $bar = $box.find(".h-3 > div");
      const $label = $box.find(".text-xs");
      $bar.removeClass("bg-red-400 bg-yellow-400 bg-green-500").addClass(color).css("width", pct + "%");
      $label.text(`${asignados}/${max} cubiertos (${pct}%)`);
    }

    /* ------------------- RENDER SEMANAL ------------------- */
    async function renderSemana() {
      const $cont = $("#gridSemana").empty();
      const dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"];
      const horas = Array.from({length: 12}, (_,i) => `${String(8 + i).padStart(2,'0')}:00`);

      if (turnos.length > 0) {
        const primeraFecha = new Date(turnos[0].fecha);
        const diaSemana = (primeraFecha.getDay() + 6) % 7;
        semanaBase = new Date(primeraFecha);
        semanaBase.setDate(primeraFecha.getDate() - diaSemana);
      }

      const $grid = $('<div class="grid border-t border-l"></div>');
      $grid.css("grid-template-columns", `100px repeat(7, 1fr)`);

      // encabezados
      $grid.append('<div></div>');
      dias.forEach(d => {
        const $h = $(`<div class="font-semibold text-center border-r border-b bg-indigo-50">${d}</div>`);
        $grid.append($h);
      });

      // horas + celdas
      horas.forEach(hora => {
        const $label = $(`<div class="text-right pr-2 text-sm border-r border-b bg-gray-50">${hora}</div>`);
        $grid.append($label);
        for (let d = 0; d < 7; d++) {
          const $celda = $(`<div class="relative border-r border-b h-16 hover:bg-indigo-50 transition drop-turno empty-slot"></div>`);
          $celda.attr("data-dia", d + 1);
          $celda.attr("data-hora", hora);

          $celda.on("dragover", function (ev) {
            ev.preventDefault();
            $(this).addClass("ring ring-indigo-300");
          });
          $celda.on("dragleave", function (ev) { $(this).removeClass("ring ring-indigo-300"); });
          $celda.on("drop", function (ev) {
            ev.preventDefault();
            $(this).removeClass("ring ring-indigo-300");
            // call native event with this element
            onDropUsuario(ev.originalEvent, this);
          });

          $celda.on("click", () => {
            if ($celda.hasClass("has-turno")) return;
            const dia = $celda.data("dia");
            const hora = $celda.data("hora");
            const fecha = calcularFechaDesdeSemana(dia);
            // abrirModalNuevoTurno(fecha, hora);
          });

          $grid.append($celda);
        }
      });

      $cont.append($grid);

      // insertar turnos en la grilla
      turnos.forEach(t => {
        if (!t.fecha) return;
        const parts = (t.hora_inicio || "00:00").split(":");
        const [yy, mm, dd] = (t.fecha || "").split("-").map(Number);
        const fecha = new Date(yy, (mm||1)-1, dd);
        const dia = (fecha.getDay() + 6) % 7; // lunes=0
        const horaInicio = parseInt((t.hora_inicio || "08:00").split(":")[0], 10);
        const horaFin = parseInt((t.hora_fin || "09:00").split(":")[0], 10);
        const duracion = Math.max(1, horaFin - horaInicio);
        const fila = horaInicio - 8;
        if (fila < 0) return;

        // calcular índice en grid children (index calculations depend on grid creation)
        // grid children order: corner(1) + 7 headers (7) = 8 first. Then for each hour: label + 7 celdas => 8 children per hour.
        // index formula: 8 + (fila * 8) + (dia + 1)
        const idx = 8 + (fila * 8) + (dia + 1);
        const $celdaInicio = $grid.children().eq(idx);
        if (!$celdaInicio || $celdaInicio.length === 0) return;

        const asignados = t.asignados || 0;
        const max = t.maximo_publicadores || 3;
        const pct = Math.round((asignados / max) * 100);
        let color = "bg-red-400";
        if (pct >= 80) color = "bg-green-500";
        else if (pct >= 40) color = "bg-yellow-400";

        const $bloque = $(`<div class="absolute inset-0 rounded text-xs text-white p-1 shadow ${color} overflow-hidden"></div>`);
        $bloque.text(`${t.hora_inicio}-${t.hora_fin} ${t.punto || ''}`);
        $bloque.attr("title", `${asignados}/${max} (${pct}%)`);
        $bloque.css({
          height: `calc(${duracion} * 100%)`,
          top: "0",
          left: "0",
          right: "0",
          zIndex: 5
        });

        for (let i = 0; i < duracion; i++) {
          const idxCelda = 8 + ((fila + i) * 8) + (dia + 1);
          const $celda = $grid.children().eq(idxCelda);
          if ($celda && $celda.length) $celda.addClass("bg-green-100");
        }

        $celdaInicio.append($bloque);
      });

      // añadir markers a celdas con turnos
      $cont.find(".drop-turno").each(function () {
        const $celda = $(this);
        const dia = parseInt($celda.data("dia"));
        const hora = $celda.data("hora");
        const fecha = calcularFechaPorDia(dia);
        const lista = (turnos || []).filter(t => {
          if (!t.fecha) return false;
          if (t.fecha !== fecha) return false;
          const hI = Number(t.hora_inicio.split(":")[0]) + Number(t.hora_inicio.split(":")[1]) / 60;
          const hF = Number(t.hora_fin.split(":")[0]) + Number(t.hora_fin.split(":")[1]) / 60;
          const [hSelH, hSelM] = (hora || "00:00").split(":").map(Number);
          const hSel = hSelH + (hSelM || 0) / 60;
          return hSel >= hI && hSel < hF;
        });
        if (lista.length > 0) {
          const marker = $(`<div class="absolute bottom-1 right-1 text-[10px] text-gray-500 bg-yellow-50 px-1 rounded border border-yellow-300">${lista.length} turno${lista.length>1 ? 's' : ''}</div>`);
          $celda.append(marker);
          $celda.attr("title", lista.map(t => `${t.hora_inicio}-${t.hora_fin} ${t.punto}`).join("\n"));
        }
      });

      activarCreacionTurno();
    } // renderSemana

    /* ------------------- creación visual de turnos en vista semanal ------------------- */
    let creandoTurno = null;
    function activarCreacionTurno() {
      const $grid = $("#gridSemana");
      if (!$grid.length) return;

      $grid.on("mousedown", function (e) {
        const $t = $(e.target).closest(".drop-turno");
        if (!$t.length) return;
        e.preventDefault();
        creandoTurno = {
          dia: $t.data("dia"),
          horaInicio: $t.data("hora"),
          celdaInicio: $t,
          celdasSeleccionadas: [$t]
        };
        $t.addClass("bg-blue-100 ring ring-blue-300");
      });

      $grid.on("mouseover", function (e) {
        if (!creandoTurno) return;
        const $celda = $(e.target).closest(".drop-turno");
        if (!$celda.length || $celda.data("dia") !== creandoTurno.dia) return;
        const todas = $grid.find(`.drop-turno[data-dia="${creandoTurno.dia}"]`).toArray();
        const iInicio = todas.indexOf(creandoTurno.celdaInicio[0]);
        const iActual = todas.indexOf($celda[0]);
        creandoTurno.celdasSeleccionadas.forEach(c => $(c).removeClass("bg-blue-200"));
        const rango = todas.slice(Math.min(iInicio, iActual), Math.max(iInicio, iActual) + 1);
        rango.forEach(c => $(c).addClass("bg-blue-200"));
        creandoTurno.celdasSeleccionadas = rango.map(n => $(n));
      });

      $(document).on("mouseup", async function (e) {
        if (!creandoTurno) return;
        const $celdaFin = $(e.target).closest(".drop-turno");
        if (!$celdaFin.length) {
          // limpiar
          if (creandoTurno.celdasSeleccionadas && creatingArray(creandoTurno.celdasSeleccionadas)) {
            creandoTurno.celdasSeleccionadas.forEach(c => $(c).removeClass("bg-blue-100 bg-blue-200 ring ring-blue-300"));
          }
          creandoTurno = null;
          return;
        }

        const dia = parseInt(creandoTurno.dia);
        const horaInicio = creandoTurno.celdaInicio.data("hora");
        const fechaTurno = calcularFechaPorDia(dia);
        let horaFin = $celdaFin.data("hora");
        const [hFin, mFin] = (horaFin || "00:00").split(":").map(Number);
        horaFin = `${String(hFin + 1).padStart(2, "0")}:${String(mFin).padStart(2, "0")}`;

        const rangoSeleccionado = [...(creandoTurno.celdasSeleccionadas || [])];
        const result = await mostrarPopupCreacionTurno(fechaTurno, horaInicio, horaFin, $celdaFin);

        if (result && result.ok) {
          rangoSeleccionado.forEach(c => {
            $(c).removeClass("bg-blue-100 bg-blue-200 ring ring-blue-300");
            $(c).addClass("bg-green-100");
          });

          const bloque = $('<div class="absolute inset-0 rounded text-xs text-white p-1 shadow bg-green-500 overflow-hidden"></div>');
          bloque.text(`${horaInicio}-${horaFin} ${result.punto || ""}`);
          const numCeldas = rangoSeleccionado.length;
          bloque.css({ height: `calc(${numCeldas} * 100%)`, top: 0, left: 0, right: 0, zIndex: 5 });
          if (rangoSeleccionado.length > 0) $(rangoSeleccionado[0]).append(bloque);

          if (typeof mostrarAvisoCelda === "function") mostrarAvisoCelda($celdaFin, "✓ Creado visualmente", "ok");
          alert("Turno creado: " + JSON.stringify(result, null, 2));
        }

        // limpieza visual
        if (creandoTurno && Array.isArray(creandoTurno.celdasSeleccionadas)) {
          creandoTurno.celdasSeleccionadas.forEach(c => $(c).removeClass("bg-blue-100 bg-blue-200 ring ring-blue-300"));
        }
        creandoTurno = null;
      });

      // cancelar con ESC
      $(document).on("keydown", function (e) {
        if (e.key === "Escape" && creandoTurno) {
          if (creandoTurno && Array.isArray(creandoTurno.celdasSeleccionadas)) {
            creandoTurno.celdasSeleccionadas.forEach(c => $(c).removeClass("bg-blue-100 bg-blue-200 ring ring-blue-300"));
          }
          creandoTurno = null;
        }
      });
    }

    /* ------------------- util: calcular fecha por dia (usa semanaInicial) ------------------- */
    function getRangoSemana(baseDate) {
      const base = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate());
      base.setHours(12, 0, 0, 0);
      const day = base.getDay();
      const diff = (day === 0 ? -6 : 1 - day);
      const lunes = new Date(base);
      lunes.setDate(base.getDate() + diff);
      lunes.setHours(0,0,0,0);
      const domingo = new Date(lunes);
      domingo.setDate(lunes.getDate() + 6);
      domingo.setHours(23,59,59,999);
      function formatISOlocal(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, "0");
        const d = String(date.getDate()).padStart(2, "0");
        return `${y}-${m}-${d}`;
      }
      return { desde: formatISOlocal(lunes), hasta: formatISOlocal(domingo), lunes, domingo };
    }

    function calcularFechaPorDia(dia) {
      if (!semanaInicial) {
        const hoy = new Date();
        const { lunes } = getRangoSemana(hoy);
        semanaInicial = lunes;
      }
      const fecha = new Date(semanaInicial);
      fecha.setDate(semanaInicial.getDate() + (dia - 1));
      const y = fecha.getFullYear();
      const m = String(fecha.getMonth() + 1).padStart(2, "0");
      const d = String(fecha.getDate()).padStart(2, "0");
      return `${y}-${m}-${d}`;
    }

    function calcularFechaDesdeSemana(diaIndex) {
      const hoy = new Date();
      const lunes = new Date(hoy);
      const day = hoy.getDay();
      const diff = hoy.getDate() - day + (day === 0 ? -6 : 1);
      lunes.setDate(diff);
      const fecha = new Date(lunes);
      fecha.setDate(lunes.getDate() + (diaIndex - 1));
      return fecha.toISOString().split('T')[0];
    }

    /* ------------------- popup creacion turno (Promise) ------------------- */
    async function mostrarPopupCreacionTurno(fecha, horaInicio, horaFin, $celda) {
      return new Promise(async (resolve, reject) => {
        const anterior = $("#popupTurnoNuevo");
        if (anterior.length) anterior.remove();

        if (horaInicio === horaFin) {
          const [h, m] = horaInicio.split(":").map(Number);
          horaFin = `${String(h + 1).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
        }

        const popup = $(`
          <div id="popupTurnoNuevo" class="fixed z-[9999] bg-white border border-gray-300 shadow-2xl rounded-lg p-4 w-72 animate-fadeIn text-sm">
            <div class="font-semibold text-gray-800 mb-2">📅 ${fecha}<br>🕒 ${horaInicio} - ${horaFin}</div>
            <label class="block text-sm text-gray-600 mb-1">Seleccioná el punto:</label>
            <select id="selPuntoNuevo" class="w-full border rounded p-1 mb-3 text-sm"><option value="">Cargando puntos...</option></select>
            <div class="flex justify-end gap-2">
              <button id="btnCancelarPopup" class="text-sm px-2 py-1 bg-gray-200 rounded hover:bg-gray-300">Cancelar</button>
              <button id="btnCrearPopup" class="text-sm px-3 py-1 bg-indigo-500 text-white rounded hover:bg-indigo-600">Crear</button>
            </div>
          </div>
        `);
        $("body").append(popup);

        // posicion alrededor de la celda si se pasa jQuery element
        try {
          if ($celda && $celda.length) {
            const rect = $celda[0].getBoundingClientRect();
            const viewportHeight = window.innerHeight;
            const popupHeight = 250;
            let topPosition = rect.top + window.scrollY + 15;
            let leftPosition = rect.left + window.scrollX + 15;
            if (rect.bottom + popupHeight > (viewportHeight)) {
              topPosition = rect.top + window.scrollY - popupHeight - 300;
              topPosition = Math.max(topPosition, 5);
            }
            popup.css({ position: "fixed", top: topPosition + "px", left: leftPosition + "px" });
          } else {
            popup.css({ position: "fixed", top: "20%", left: "40%" });
          }
        } catch (err) {
          console.warn("No se pudo posicionar popup:", err);
        }

        // draggable (simple) - usar transform translate
        let isDragging = false, currentX, currentY, initialX, initialY, xOffset = 0, yOffset = 0;
        popup.on("mousedown", function (ev) {
          if (ev.button !== 0) return;
          const tag = ev.target.tagName.toLowerCase();
          if (tag === "select" || tag === "option" || tag === "button" || $(ev.target).closest("#selPuntoNuevo").length) return;
          initialX = ev.clientX - xOffset;
          initialY = ev.clientY - yOffset;
          isDragging = true;
          ev.preventDefault();
          popup.css("cursor","grabbing");
        });
        $(document).on("mouseup.popupdrag", function () {
          isDragging = false;
          popup.css("cursor","default");
        });
        $(document).on("mousemove.popupdrag", function (ev) {
          if (!isDragging) return;
          currentX = ev.clientX - initialX;
          currentY = ev.clientY - initialY;
          xOffset = currentX; yOffset = currentY;
          popup.css("transform", `translate3d(${currentX}px, ${currentY}px, 0)`);
        });

        // cargar puntos disponibles desde API
        try {
          const fechaISO = fecha.indexOf("/") !== -1 ? fecha.split("/").reverse().join("-") : fecha;
          const puntos = await safeFetch(`${apiBaseTurnos}?accion=puntos_disponibles&fecha=${fechaISO}`);
          const sel = popup.find("#selPuntoNuevo");
          sel.empty();
          if (Array.isArray(puntos) && puntos.length) {
            puntos.forEach(p => sel.append($(`<option value="${p.id}">${p.nombre}</option>`)));
          } else {
            sel.append('<option value="">(Sin puntos disponibles)</option>');
          }
        } catch (err) {
          console.warn("Error cargando puntos:", err);
        }

        function cleanup() {
          $(document).off("mouseup.popupdrag mousemove.popupdrag");
        }

        const handleEscape = (e) => {
          if (e.key === "Escape") {
            popup.remove();
            cleanup();
            $(document).off("keydown", handleEscape);
            resolve({ cancelled: true });
          }
        };
        $(document).on("keydown", handleEscape);

        popup.find("#btnCancelarPopup").on("click", () => {
          popup.remove();
          cleanup();
          $(document).off("keydown", handleEscape);
          resolve({ cancelled: true });
        });

        popup.find("#btnCrearPopup").on("click", async () => {
          const puntoId = popup.find("#selPuntoNuevo").val();
          const puntoNombre = popup.find("#selPuntoNuevo option:selected").text() || "(Sin punto)";
          if (!puntoId) {
            alert("Seleccioná un punto antes de crear el turno.");
            return;
          }
          const $btn = popup.find("#btnCrearPopup");
          $btn.prop("disabled", true).text("Creando...");
          const postData = { fecha, hora_inicio: horaInicio, hora_fin: horaFin, punto: puntoNombre, maximo_publicadores: 3 };
          try {
            const resp = await safeFetch(`${apiBaseTurnos}?accion=crear_manual`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: postData
            });
            if (resp.ok) {
              if ($celda && $celda.length) {
                $celda.addClass("bg-green-100");
                const nuevo = $('<div class="absolute inset-1 rounded text-xs text-white p-1 shadow bg-green-500"></div>');
                nuevo.text(`${horaInicio}-${horaFin}`);
                $celda.append(nuevo);
              }
              popup.remove(); cleanup(); $(document).off("keydown", handleEscape);
              resolve({ ok: true, ...postData });
            } else {
              if ($celda && $celda.length) $celda.addClass("bg-red-100");
              popup.remove(); cleanup(); $(document).off("keydown", handleEscape);
              resolve({ ok: false, error: resp.error });
            }
          } catch (err) {
            console.error("Error crear turno:", err);
            popup.remove(); cleanup(); $(document).off("keydown", handleEscape);
            reject(err);
          }
        });

      }); // promise
    } // mostrarPopupCreacionTurno

    /* ------------------- mostrar selector turno (cuando hay varios en la misma celda) ------------------- */
    function mostrarSelectorTurno(turnosArr) {
      return new Promise(resolve => {
        const $popup = $(`
          <div class="fixed inset-0 bg-black/50 flex justify-center items-center z-[9999]">
            <div class="bg-white rounded-lg shadow-xl p-4 w-[340px]">
              <h3 class="font-semibold text-lg mb-2 text-indigo-700">📍 Seleccioná el turno</h3>
              <div class="max-h-[200px] overflow-y-auto mb-3"></div>
              <div class="flex justify-end">
                <button id="btnCancelarSelTurno" class="px-3 py-1 bg-gray-200 rounded hover:bg-gray-300 text-sm">Cancelar</button>
              </div>
            </div>
          </div>
        `);
        $("body").append($popup);
        const $list = $popup.find("div.max-h-[200px]");
        turnosArr.forEach(t => {
          const $opt = $(`<div class="turno-opcion border rounded p-2 mb-1 cursor-pointer hover:bg-indigo-50" data-id="${t.id}">
            <b>${t.punto}</b><br><span class="text-sm text-gray-600">${t.hora_inicio} - ${t.hora_fin}</span>
          </div>`);
          $opt.on("click", function () {
            const id = $(this).data("id");
            const elegido = turnosArr.find(x => x.id == id);
            $popup.remove();
            resolve(elegido);
          });
          $list.append($opt);
        });
        $popup.find("#btnCancelarSelTurno").on("click", () => { $popup.remove(); resolve(null); });
      });
    }

    /* ------------------- render usuarios semana ------------------- */
    function renderUsuariosSemana() {
      const $list = $("#usuariosSemana");
      if (!$list.length) return;
      $list.empty();
      usuarios.forEach(u => {
        const text = u.full_name || u.nombre || u.usuario || `Usuario ${u.id || ''}`;
        const $el = $(`<div class="draggable-user bg-blue-50 border border-blue-200 rounded p-2 mb-1 cursor-move text-sm">${text}</div>`);
        $el.attr("draggable", true);
        $el.data("userId", u.id);
        $el.on("dragstart", function (ev) {
          ev.originalEvent.dataTransfer.setData("userId", $(this).data("userId"));
          ev.originalEvent.dataTransfer.effectAllowed = "move";
        });
        $list.append($el);
      });
    }

    /* ------------------- mostrar aviso corto sobre una celda ------------------- */
    function mostrarAvisoCelda($celda, mensaje, tipo = "info") {
      if (!$celda || !$celda.length) return;
      const $aviso = $(`<div class="absolute z-50 px-3 py-1 rounded text-xs font-medium text-white shadow-lg transition-opacity duration-500"></div>`);
      if (tipo === "ok") $aviso.addClass("bg-green-500"); else if (tipo === "error") $aviso.addClass("bg-red-500"); else $aviso.addClass("bg-gray-700");
      $aviso.text(mensaje);
      $aviso.css({ top: "4px", left: "4px", pointerEvents: "none" });
      $celda.append($aviso);
      setTimeout(() => $aviso.css("opacity", 0), 1200);
      setTimeout(() => $aviso.remove(), 1800);
    }

    /* ------------------- panel resumen ------------------- */
    function actualizarPanelResumen() {
      $("#countAsignados").text(resumen.totalAsignados || 0);
      $("#countConflictos").text((resumen.conflictos || []).length || 0);
      const $listaConf = $("#listaConflictos");
      $listaConf.html((resumen.conflictos || []).map(c => `<div>• ${c}</div>`).join("") || "");
      const totalTurnos = turnos.length || 0;
      resumen.turnosCompletos = Math.floor((resumen.totalAsignados || 0) / 3);
      resumen.turnosVacantes = Math.max(0, totalTurnos - resumen.turnosCompletos);
      $("#countCompletos").text(resumen.turnosCompletos);
      $("#countVacantes").text(resumen.turnosVacantes);
    }

    /* ------------------- cambiar semana (cargar via API) ------------------- */
    async function cambiarSemana(delta = 0) {
      if (!semanaInicial) {
        const hoy = new Date();
        const { lunes } = getRangoSemana(hoy);
        semanaInicial = lunes;
      }
      offsetSemanas += delta;
      const nuevaBase = new Date(semanaInicial);
      nuevaBase.setDate(semanaInicial.getDate() + offsetSemanas * 7);
      const { desde, hasta, lunes } = getRangoSemana(nuevaBase);
      $("#tituloSemana").text(`📆 Semana del ${desde.split('-').reverse().join('/')} al ${hasta.split('-').reverse().join('/')}`);
      const detalle = [
        `Lunes base (semana mostrada): ${lunes.toDateString()}`,
        `Desplazamiento de semanas: ${offsetSemanas}`,
        `Desde: ${desde}`,
        `Hasta: ${hasta}`
      ].join('\n');
      $("#tituloSemana").attr("title", detalle).data("tooltip", detalle);

      const $cont = $("#gridSemana").parent().length ? $("#gridSemana").parent() : $(document.body);
      let $overlay = $("#spinnerSemana");
      if (!$overlay.length) {
        $overlay = $(`<div id="spinnerSemana" class="absolute inset-0 flex items-center justify-center bg-white/70 z-50">
          <div class="text-indigo-600 text-sm flex items-center gap-2"><svg class="animate-spin h-6 w-6 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"/><path fill="currentColor" d="M4 12a8 8 0 018-8v8z" class="opacity-75"/></svg> Cargando...</div>
        </div>`);
        $cont.append($overlay);
      } else {
        $overlay.removeClass("hidden");
      }

      try {
        const res = await safeFetch(`${apiBaseTurnos}?accion=listar_por_rango&desde=${desde}&hasta=${hasta}`);
        turnos = Object.entries(res).flatMap(([fecha, arr]) => arr.map(t => ({ ...t, fecha })));
        console.log(`Semana cargada (${turnos.length} turnos)`);
        await renderSemana();
      } catch (err) {
        console.error("Error cargando semana:", err);
      } finally {
        $overlay.addClass("hidden");
      }
    }

    /* ------------------- exposiciones públicas ------------------- */
    return {
      init,
      // helper for debug
      _internal: { safeFetch, obtenerUsuarios: () => usuarios, obtenerTurnos: () => turnos }
    };
  })();

  // expose globally
  window.PlanificadorInteractivo = PlanificadorInteractivo;

})(window, jQuery);
