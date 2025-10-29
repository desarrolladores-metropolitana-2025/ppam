// PPAM - Sistema de predicación Metropolitana
// 21/10/2025  -  Equipo de desarrolladores PPAM
// planificador_interactivo.js — Versión 3: con panel lateral resumen
// Depende de postulantes.php (validar_disponibilidad) y turnos_admin.php (asignar_manual)

const PlanificadorInteractivo = (() => {

  const apiBase = "/api";
  let semanaBase = null;
  let usuarios = [];
  let turnos = [];
  let resumen = {
    totalAsignados: 0,
    turnosCompletos: 0,
    turnosVacantes: 0,
    conflictos: []
  };
  /* ----- Normalizar tiempos ----------------------*/
  function padTimeToHHMM(t) {
  if (!t) return t;
  // admite "8:00" o "08:00:00" o "08:00"
  const parts = t.split(':');
  const hh = String(parts[0] || '0').padStart(2,'0');
  const mm = String(parts[1] || '00').padStart(2,'0');
  return `${hh}:${mm}`;
}

/**
 * Suma una cantidad de horas a una cadena de tiempo "HH:MM".
 * @param {string} horaStr - La hora inicial en formato "HH:MM" (ej: "08:00").
 * @param {number} horasASumar - El número de horas a sumar (ej: 1).
 * @returns {string} La nueva hora en formato "HH:MM" (ej: "09:00").
 */
function sumarHoras(horaStr, horasASumar) {
    // 1. Descomponer la hora en horas y minutos
    const [horas, minutos] = horaStr.split(':').map(Number);

    // 2. Crear un objeto Date temporal
    // Se usa una fecha arbitraria (ej: hoy) para que el objeto Date pueda funcionar, 
    // ya que solo estamos manipulando las horas y minutos.
    const fechaTemp = new Date();
    fechaTemp.setHours(horas + horasASumar, minutos, 0); // Suma las horas

    // 3. Formatear la nueva hora a "HH:MM"
    // .getHours() y .getMinutes() devuelven números.
    const nuevasHoras = fechaTemp.getHours().toString().padStart(2, '0');
    const nuevosMinutos = fechaTemp.getMinutes().toString().padStart(2, '0');

    return `${nuevasHoras}:${nuevosMinutos}`;
}


  /* ==========================================================
     🔹 Inicialización
  ========================================================== */
  async function init() {
  const contenedor = document.getElementById("planificador_turnos");
  if (!contenedor) return console.error("Falta div #planificador_turnos");

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
		  <!-- 🔹 Columna 1: Usuarios -->
  <div id="titUsuarios">
    <h3 class="font-semibold mb-2">Usuarios disponibles</h3>
    <div id="usuariosList" class="bg-white rounded shadow p-2 h-[420px] overflow-y-auto"></div>
  </div>

  <!-- 🔹 Columna 2: Turnos -->
  <div id="titTurnos" >
    <h3 class="font-semibold mb-2">Turnos</h3>
    <div id="turnosListPlanif" class="bg-white rounded shadow p-2 h-[420px] overflow-y-auto"></div>
  </div>

  <!-- 🔹 Columna 3: Panel lateral resumen -->
  <div id="listaResumenes"class="bg-gray-50 border border-gray-200 rounded p-3 flex flex-col gap-3 shadow-sm">
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

        <!-- Vista semanal -->
       <div id="planificadorSemanal" class="hidden">
  <div class="flex justify-between items-center mb-3">
    <h2 class="font-bold text-xl text-indigo-700">📆 Planificador Semanal</h2>
    <button id="btnVolverLista" class="px-3 py-1 bg-indigo-500 text-white rounded hover:bg-indigo-600">
      ← Volver a vista diaria
    </button>
  </div>
<div class="flex justify-between items-center mb-3">  
    <button id="btnPrevSemana" class="flex items-center justify-center w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 hover:bg-indigo-200 shadow">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="w-5 h-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5 8.25 12l7.5-7.5" />
        </svg>
    </button>  
    <h2 id="tituloSemana" class="font-bold text-xl text-indigo-700">📆 Semana del 13 al 19 oct 2025</h2>  
    <button id="btnNextSemana" class="flex items-center justify-center w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 hover:bg-indigo-200 shadow">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="w-5 h-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
        </svg>
    </button>
</div>
  <!-- Nueva estructura horizontal -->
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

document.getElementById("btnPrevSemana").addEventListener("click", () => cambiarSemana(-1));
document.getElementById("btnNextSemana").addEventListener("click", () => cambiarSemana(1));

  // 🔹 Agregar listeners después de renderizar el HTML -  encabezadoDiario
  document.getElementById("btnPlanificarTurnos").addEventListener("click", async () => {
    document.getElementById("listaResumenes").classList.add("hidden");
	document.getElementById("listaConflictos").classList.add("hidden");
	document.getElementById("titUsuarios").classList.add("hidden");
	document.getElementById("titTurnos").classList.add("hidden");
	document.getElementById("turnosListPlanif").classList.add("hidden");
	document.getElementById("encabezadoDiario").classList.add("hidden");
	document.getElementById("usuariosList").classList.add("hidden");
    document.getElementById("planificadorSemanal").classList.remove("hidden");
    await cambiarSemana(0);
	renderUsuariosSemana();

  });

  document.getElementById("btnVolverLista").addEventListener("click", () => {
    document.getElementById("planificadorSemanal").classList.add("hidden");
	 document.getElementById("encabezadoDiario").classList.remove("hidden");
    document.getElementById("turnosListPlanif").classList.remove("hidden");
	document.getElementById("listaResumenes").classList.remove("hidden");
	document.getElementById("listaConflictos").classList.remove("hidden");
	document.getElementById("usuariosList").classList.remove("hidden");
	document.getElementById("titUsuarios").classList.remove("hidden");
	document.getElementById("titTurnos").classList.remove("hidden");
  });

  // 🔹 Cargar datos
  await Promise.all([cargarUsuarios(), cargarTurnos()]);
  renderUsuarios();
  renderTurnos();
  actualizarPanelResumen();
}

  /* ==========================================================
     🔹 Cargar datos
  ========================================================== */
  async function cargarUsuarios() {
    const res = await fetch(`${apiBase}/postulantes.php?accion=listar_disponibles`);
    usuarios = await res.json();
  }

  async function cargarTurnos() {
    const res = await fetch(`${apiBase}/turnos_admin.php?accion=listar`);
    turnos = await res.json();
  }

  /* ==========================================================
     🔹 Renderización
  ========================================================== */
  function renderUsuarios() {
    const list = document.getElementById("usuariosList");
    list.innerHTML = "";

    usuarios.forEach(u => {
      const el = document.createElement("div");
      el.className = "draggable-user bg-blue-50 border border-blue-200 rounded p-2 mb-1 cursor-move";
      el.draggable = true;
      el.dataset.userId = u.id;
      el.textContent = u.full_name || u.last_name || u.name || u.email || 'Usuario sin nombre';
      el.addEventListener("dragstart", onDragStart);
      list.appendChild(el);
    });
  }

 function renderTurnos() {
  const list = document.getElementById("turnosListPlanif");
  list.innerHTML = "";

  // Agrupar turnos por fecha
  const grupos = {};
  turnos.forEach(t => {
    if (!grupos[t.fecha]) grupos[t.fecha] = [];
    grupos[t.fecha].push(t);
  });

  // Ordenar fechas cronológicamente
  const fechasOrdenadas = Object.keys(grupos).sort((a,b)=> new Date(a) - new Date(b));

  // Mostrar cada grupo (día)
  fechasOrdenadas.forEach(fecha => {
    const dayContainer = document.createElement("div");
    dayContainer.className = "mb-6";

    // Encabezado con nombre del día
    let [yy, mm, dd] = fecha.split('-').map(Number);
    const d = new Date(yy, mm - 1, dd);  // <-- forzado en zona local
    const dias = ["Domingo","Lunes","Martes","Miércoles","Jueves","Viernes","Sábado"];
    const nombreDia = dias[d.getDay()];
	// console.log("Dia->"+d.getDay()+'Fecha: '+ fecha);
    const encabezado = document.createElement("div");
    encabezado.className = "font-bold text-lg mb-2 text-indigo-700 flex items-center gap-2";
    // encabezado.innerHTML = `<span>🗓️</span> ${nombreDia} ${d.getDate()}/${d.getMonth()+1}`;
	encabezado.innerHTML = `<span>🗓️</span> ${nombreDia} ${dd}/${mm}`;
    dayContainer.appendChild(encabezado);

    // Contenedor de tarjetas
    const inner = document.createElement("div");
    inner.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3";

    grupos[fecha].forEach(t => {
      const el = document.createElement("div");
      el.className = "drop-turno bg-gray-50 border border-gray-300 rounded p-3 shadow-sm hover:shadow-md transition cursor-pointer";
      el.dataset.turnoId = t.id;
      el.dataset.fecha = t.fecha;
      el.dataset.horaInicio = t.hora_inicio;
      el.dataset.horaFin = t.hora_fin;
      el.dataset.puntoId = t.punto_id;

      const asignados = t.asignados || 0;
      const max = t.maximo_publicadores || 3;
      const ratio = Math.min(asignados / max, 1);
      const pct = Math.round(ratio * 100);

      let color = "bg-red-400";
      if (pct >= 80) color = "bg-green-500";
      else if (pct >= 40) color = "bg-yellow-400";

      el.innerHTML = `
        <div class="font-semibold">${t.hora_inicio} - ${t.hora_fin}</div>
        <div class="text-sm text-gray-500 mb-1">${t.punto}</div>

        <!-- Barra de progreso -->
        <div class="h-3 bg-gray-200 rounded overflow-hidden mb-2">
          <div class="${color} h-full transition-all duration-300" style="width:${pct}%"></div>
        </div>

        <div class="text-xs text-gray-700 mb-1">${asignados}/${max} cubiertos (${pct}%)</div>
        <div class="asignados text-sm text-gray-700 italic"></div>
      `;

      el.addEventListener("dragover", e => e.preventDefault());
      el.addEventListener("drop", onDropUsuario);
      inner.appendChild(el);
    });

    dayContainer.appendChild(inner);
    list.appendChild(dayContainer);
  });
}


  /* ==========================================================
     🔹 Drag & Drop + Validación + Asignación + Resumen
  ========================================================== */
  function onDragStart(e) {
    e.dataTransfer.setData("userId", e.target.dataset.userId);
    e.dataTransfer.effectAllowed = "move";
  }


  async function onDropUsuario(e) {
    e.preventDefault();
	const box = e.currentTarget;
	const userId = e.dataTransfer.getData("userId");
    const turnoId = e.currentTarget.dataset.turnoId;
    if (!box) { console.error('No se detectó elemento destino en drop'); return; }

// 🔍 Detectar si está en vista semanal con bloque de turno
    const bloqueExistente = box.querySelector(".has-turno, .turno-bloque, .bg-green-500, .bg-yellow-400, .bg-red-400");
    if (!turnoId && bloqueExistente) {
  // intentar deducir el turno según las horas y fecha
  const hora = box.dataset.hora;
  const dia = box.dataset.dia;
  const fecha = calcularFechaPorDia(parseInt(dia));
  const turnoMatch = turnos.find(t => t.fecha === fecha && t.hora_inicio === hora);
  if (turnoMatch) {
    e.currentTarget.dataset.turnoId = turnoMatch.id;
  }
}

	 //  Si no existe .asignados, lo creamos temporalmente (vista semanal)
  let asignadosBox = box.querySelector(".asignados");
  if (!asignadosBox) {
    asignadosBox = document.createElement("div");
    asignadosBox.className = "asignados text-xs text-gray-600 italic";
    box.appendChild(asignadosBox);
  }	
       
 // Si está en modo timeline (sin turno_id directo)
 if (!turnoId && box.dataset.dia) {
  const dia = parseInt(box.dataset.dia);
  const hora = box.dataset.hora;
  const fecha = calcularFechaPorDia(dia);
  
  //  Normalizamos la fecha a formato ISO (YYYY-MM-DD)
let fechaISO = null;

if (typeof fecha === "string" && fecha.trim() !== "") {
  fechaISO = fecha.includes("/")
    ? fecha.split("/").reverse().join("-")
    : fecha;
	mostrarAvisoCelda(box, `Intentando asignar usuario ${userId} en ${fecha} ${hora}`, "ok");
	console.log(` Intentando asignar usuario ${userId} en ${fecha} ${hora}`);
} else {
  console.warn("⚠️ Fecha no válida o indefinida en onDropUsuario:", fecha);
  mostrarAvisoCelda(box, `Intentando asignar usuario ${userId} en ${fecha} ${hora}`, "error");
  // como fallback, intentamos calcularla desde box.dataset.dia
  const dia = parseInt(box.dataset.dia);
  fechaISO = calcularFechaPorDia(dia);
}


  //console.log(` Intentando asignar usuario ${userId} en ${fecha} ${hora}`);
  // mostrarAvisoCelda(box, `Intentando asignar usuario ${userId} en ${fecha} ${hora}`, "ok");

  //  Buscar turnos existentes en ese día y rango horario
  const respTurnos = await fetch(`${apiBase}/turnos_admin.php?accion=listar_por_rango&desde=${fecha}&hasta=${fecha}`);
  const turnosDia = await respTurnos.json();
  console.log("📅 Turnos recibidos para", fecha, "→", Object.keys(turnosDia));
// 🔧 Normalizamos la fecha a formato ISO (YYYY-MM-DD)
// const fechaISO = fecha.includes("/") ? fecha.split("/").reverse().join("-") : fecha;

const posibles = (turnosDia[fechaISO] || []).filter(t => {
  const hI = Number(t.hora_inicio.split(":")[0]) + Number(t.hora_inicio.split(":")[1]) / 60;
  const hF = Number(t.hora_fin.split(":")[0]) + Number(t.hora_fin.split(":")[1]) / 60;
  const [hSelH, hSelM] = hora.split(":").map(Number);
  const hSel = hSelH + (hSelM || 0) / 60;

  return hSel >= hI && hSel < hF;
});


  if (posibles.length > 0) {
    // 🔹 2️⃣ Si hay varios turnos en esa hora, mostrar selección
    let turnoElegido = posibles[0];
    if (posibles.length > 1) {
      turnoElegido = await mostrarSelectorTurno(posibles);
      if (!turnoElegido) {
        console.log("🚫 Usuario canceló selección de turno existente");
        return;
      }
    }

    console.log("✅ Turno elegido:", turnoElegido);

    //  Validar disponibilidad antes de asignar
    const params = new URLSearchParams({
      accion: "validar_disponibilidad",
      usuario_id: userId,
      fecha: turnoElegido.fecha,
      hora_inicio: turnoElegido.hora_inicio,
      hora_fin: turnoElegido.hora_fin,
      punto_id: turnoElegido.punto_id,
      rol: "publicador"
    });

    const validResp = await fetch(`${apiBase}/postulantes.php?${params}`);
    const validData = await validResp.json();

    if (!validData.ok) {
      box.classList.add("bg-red-100");
      console.warn(`❌ Usuario no disponible: ${validData.motivo}`);
	  mostrarAvisoCelda(box,`❌ Usuario no disponible: ${validData.motivo}`, "error");

      return;
    }

    //  Asignar al usuario en turno_participantes
    const asignar = await fetch(`${apiBase}/turnos_admin.php?accion=asignar_manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        turno_id: turnoElegido.id,
        usuario_id: userId,
        rol: "publicador"
      })
    });

    const rjson = await asignar.json();
    if (rjson.ok) {
      const overlay = document.createElement("div");
      overlay.className = "absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow";
      overlay.textContent = "✓ " + (usuarios.find(u => u.id == userId)?.full_name?.split(' ')[0] || "Usuario");
      box.appendChild(overlay);
      resumen.totalAsignados++;
      actualizarPanelResumen();
      console.log("✅ Usuario asignado correctamente al turno existente");
	  mostrarAvisoCelda(box, "✓ Asignado", "ok");
    } else {
      console.error("❌ Error asignando usuario:", rjson.error);
    }
    return;
  }

  //  Si no hay turnos existentes, crear uno nuevo (comportamiento anterior)
  console.log("🧩 No hay turnos existentes → crear nuevo turno");
  mostrarAvisoCelda(box, "✗ No existe turno en esta ubicación", "error");

  const result = await mostrarPopupCreacionTurno(fecha, hora, sumarHoras(hora, 1), box);
  if (!result || !result.ok) {
	  console.log("❌ Creación de turno cancelada o fallida");
	  mostrarAvisoCelda(box, "✗ turno cancelado", "error");

	  return;
      } 

/*--------------------------------------------------------------------------------*/
  // Buscar el turno recién creado en el backend (por fecha, hora y punto)
  respTurnos = await fetch(`${apiBase}/turnos_admin.php?accion=listar_por_rango&desde=${fecha}&hasta=${fecha}`);
  turnosDia = await respTurnos.json();
  console.log("📅 Turnos recibidos para", fecha, "→", Object.keys(turnosDia));
  fechaISO = fecha.includes("/") 
  ? fecha.split("/").reverse().join("-") 
  : fecha;
  const turnoNuevo = (turnosDia[fechaISO] || []).find(t =>
  t.hora_inicio === result.hora_inicio && t.hora_fin === result.hora_fin
);


  if (!turnoNuevo) {
    console.error("No se encontró el turno recién creado.");
    return;
  }

  // ⚡ Asignar al usuario recién soltado
  const asignar = await fetch(`${apiBase}/turnos_admin.php?accion=asignar_manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      turno_id: turnoNuevo.id,
      usuario_id: userId,
      rol: "publicador"
    })
  });

  const rjson = await asignar.json();
  if (rjson.ok) {
    const overlay = document.createElement("div");
    overlay.className = "absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow";
    overlay.textContent = "✓ " + (usuarios.find(u => u.id == userId)?.full_name?.split(' ')[0] || "Usuario");
    box.appendChild(overlay);
    resumen.totalAsignados++;
    actualizarPanelResumen();
    console.log("✅ Usuario asignado manualmente al turno nuevo");
	mostrarAvisoCelda(box, "✓ Creado visualmente", "ok");
  } else {
    console.error("❌ Error asignando tras crear turno:", rjson.error);
	mostrarAvisoCelda(box, "✗ Turno: " + rjson.error , "error");
  }

  return;
}


  // Validación con el backend
  // const resp = await fetch(`${apiBase}/postulantes.php?accion=validar_disponibilidad&usuario_id=${userId}&turno_id=${turnoId}`);
  //  const data = await resp.json();
    const turno = turnos.find(t => t.id == turnoId);
    const user = usuarios.find(u => u.id == userId);
    if (!turno || !user) return;
  
	
    if( box ) { 
	// const asignadosBox = box.querySelector(".asignados");
	box.classList.add("opacity-50"); 
    box.title = "Validando disponibilidad...";
	}
	else { console.log(`Error e.currentTarget es NULL en Box: ` + data.motivo); }

   

    // Validación previa
    const params = new URLSearchParams({
      accion: "validar_disponibilidad",
      usuario_id: userId,
      fecha: turno.fecha,
      hora_inicio: turno.hora_inicio,
      hora_fin: turno.hora_fin,
      punto_id: turno.punto_id,
      rol: "publicador"
    });
	
	// Construye la URL completa
const urlCompleta = `${apiBase}/postulantes.php?${params.toString()}`;

// Esto Imprime la URL completa en la consola
// console.log("URL de la llamada:", urlCompleta);


    try {
      const res = await fetch(`${apiBase}/postulantes.php?${params}`);
      const data = await res.json();
     if(box) { 
	 if (data.ok) {
	box.classList.remove("opacity-50");	 
    box.classList.add("bg-green-100");
    box.title = "✅ Cumple criterios";
	mostrarAvisoCelda(box, "✓ Cumple criterios", "ok");
  } else {    
  console.log(`Error e.currentTarget es Null: ` + data.motivo);
  box.classList.add("bg-red-100");
  box.title = "❌ " + data.motivo;
  mostrarAvisoCelda(box, "✗ Turno: " + data.motivo , "error");
  }	 
	 	 }
	 else { console.log(`Error e.currentTarget es NULL en Box: ` + data.motivo); }

      if (!data.ok) {
        box.classList.add("border-red-400");
        resumen.conflictos.push(`${user.full_name} → ${turno.fecha} (${data.motivo})`);
        asignadosBox.innerHTML = `<span class="text-red-600">✗ ${user.full_name}: ${data.motivo || 'no válido'}</span>`;
        actualizarPanelResumen();
        return;
      }
      
	  // ✅ Asignar realmente al turno  (versión JSON)
const postData = {
  turno_id: turnoId,
  usuario_id: userId,
  rol: "publicador"
};

     console.log("📤 Enviando asignación manual:", postData);

const resp = await fetch(`${apiBase}/turnos_admin.php?accion=asignar_manual`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify(postData)
});

const rjson = await resp.json();
console.log("📥 Respuesta del backend:", rjson);

      if (rjson.ok) {
        box.classList.remove("border-gray-300", "border-red-400");
        box.classList.add("border-green-500");
        asignadosBox.innerHTML += `<div class="text-green-700">✓ ${user.full_name} asignado</div>`;
          //  Si la asignación se hizo en la vista semanal, pintar un bloque visual sobre la celda
    if (box.closest("#gridSemana")) {
    const overlay = document.createElement("div");
    overlay.className = "absolute inset-0 flex items-center justify-center text-[10px] bg-green-400/80 text-white rounded shadow";
    overlay.textContent = `${user.full_name.split(' ')[0] || user.full_name}`;
    box.appendChild(overlay);
	mostrarAvisoCelda(box, "✓ "+ `${user.full_name.split(' ')[0] || user.full_name}` + ": Asignado", "ok");
  }

        resumen.totalAsignados++;
        actualizarPanelResumen();
        actualizarBarraProgreso(turnoId);

      } else {
        box.classList.add("border-red-400");
        asignadosBox.innerHTML = `<span class="text-red-600">✗ Error al asignar</span>`;
		 console.log(`Error : ` + rjson.error + ` usuario : ` + userId + ` Turno : ` + turnoId);
		 if (box.closest("#gridSemana")) { mostrarAvisoCelda(box, `Error : ` + rjson.error + ` usuario : ` + userId + ` Turno : ` + turnoId, "error"); }
      }

    } catch (err) {
      console.error("Error general:", err);
      box.classList.add("border-red-500");
    }
  }

/* ==========================================================
     🔹 Actualización de la Barra de progreso
  ========================================================== */


function actualizarBarraProgreso(turnoId) {
  const turno = turnos.find(t => t.id == turnoId);
  if (!turno) return;

  const box = document.querySelector(`.drop-turno[data-turno-id="${turnoId}"]`);
  if (!box) return;

  const asignados = (turno.asignados = (turno.asignados || 0) + 1);
  const max = turno.maximo_publicadores || 3;
  const pct = Math.round((asignados / max) * 100);

  let color = "bg-red-400";
  if (pct >= 80) color = "bg-green-500";
  else if (pct >= 40) color = "bg-yellow-400";

  const bar = box.querySelector(".h-3 > div");
  const label = box.querySelector(".text-xs");

  bar.className = `${color} h-full transition-all duration-300`;
  bar.style.width = `${pct}%`;
  label.textContent = `${asignados}/${max} cubiertos (${pct}%)`;
}

/* ==========================================================
     🔹 Planificar Turnos
  ========================================================== */

// Renderizado semanal
async function renderSemana() {
  const cont = document.getElementById("gridSemana");
  cont.innerHTML = "";

  // Asumimos que turnos[] está cargado con todos los turnos de la semana
  const dias = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"];
  // const horas = Array.from({length: 12}, (_,i)=> `${8+i}:00`); // 8h–20h ajustable
  const horas = Array.from({length: 12}, (_,i) => `${String(8 + i).padStart(2,'0')}:00`); // "08:00","09:00"...

  if (turnos.length > 0) {
  const primeraFecha = new Date(turnos[0].fecha);
  const diaSemana = (primeraFecha.getDay() + 6) % 7; // lunes=0
  semanaBase = new Date(primeraFecha);
  semanaBase.setDate(primeraFecha.getDate() - diaSemana);
}



  const grid = document.createElement("div");
  grid.className = "grid border-t border-l";
  grid.style.gridTemplateColumns = `100px repeat(7, 1fr)`;

  // Encabezados
  grid.appendChild(document.createElement("div")); // espacio vacío esquina
  dias.forEach(d => {
    const h = document.createElement("div");
    h.textContent = d;
    h.className = "font-semibold text-center border-r border-b bg-indigo-50";
    grid.appendChild(h);
  });

  // Horas + celdas
  horas.forEach(hora => {
    const label = document.createElement("div");
    label.textContent = hora;
    label.className = "text-right pr-2 text-sm border-r border-b bg-gray-50";
    grid.appendChild(label);

    for (let d = 0; d < 7; d++) {
      const celda = document.createElement("div");
     // celda.className = "relative border-r border-b h-16 hover:bg-indigo-50 transition drop-turno";
	  // dentro del loop que genera cada celda (dentro de for let d=0...):
      celda.className = "relative border-r border-b h-16 hover:bg-indigo-50 transition drop-turno empty-slot";

      celda.dataset.dia = d + 1;
      celda.dataset.hora = hora;
      // celda.addEventListener("dragover", e => e.preventDefault());
      // celda.addEventListener("drop", onDropUsuario);
	  celda.addEventListener("dragover", e => {
      e.preventDefault();
      celda.classList.add("ring", "ring-indigo-300");
      });
      celda.addEventListener("dragleave", () => celda.classList.remove("ring", "ring-indigo-300"));
      celda.addEventListener("drop", e => {
      celda.classList.remove("ring", "ring-indigo-300");
      onDropUsuario(e);
     });

	  celda.addEventListener("click", (ev) => {
  if (celda.classList.contains("has-turno")) return; // ya ocupado

  const dia = celda.dataset.dia;
  const hora = celda.dataset.hora;
  const fecha = calcularFechaDesdeSemana(dia);
  
  // abrirModalNuevoTurno(fecha, hora);
});

      grid.appendChild(celda);
    }
  });

  cont.appendChild(grid);

  // Insertar turnos visualmente
  // Insertar turnos visualmente en la grilla semanal
turnos.forEach(t => {
  if (!t.fecha) return;

  // ✅ Convertir correctamente la fecha (sin desfases UTC)
  const [yy, mm, dd] = t.fecha.split("-").map(Number);
  const fecha = new Date(yy, mm - 1, dd);
  const dia = (fecha.getDay() + 6) % 7; // lunes=0
  const horaInicio = parseInt(t.hora_inicio.split(":")[0]);
  const horaFin = parseInt(t.hora_fin.split(":")[0]);
  const duracion = Math.max(1, horaFin - horaInicio); // horas cubiertas

  // 🧭 Posición dentro del grid
  const fila = horaInicio - 8; // base 8:00
  if (fila < 0) return;

  // Calcular índice correcto en la grilla
  const idx = (8) + (fila * 8) + (dia + 1);
  const celdaInicio = grid.children[idx];
  if (!celdaInicio) return;

  // 📊 Determinar color según porcentaje de cobertura
  const asignados = t.asignados || 0;
  const max = t.maximo_publicadores || 3;
  const pct = Math.round((asignados / max) * 100);

  let color = "bg-red-400";
  if (pct >= 80) color = "bg-green-500";
  else if (pct >= 40) color = "bg-yellow-400";

  // 📦 Crear bloque visual que cubra todas las horas del turno
  const bloque = document.createElement("div");
  bloque.className = `absolute inset-0 rounded text-xs text-white p-1 shadow ${color} overflow-hidden`;
  bloque.textContent = `${t.hora_inicio}-${t.hora_fin} ${t.punto}`;
  bloque.title = `${asignados}/${max} (${pct}%)`;

  // Ajustar altura para cubrir todas las celdas del rango horario
  bloque.style.height = `calc(${duracion} * 100%)`;
  bloque.style.top = "0";
  bloque.style.left = "0";
  bloque.style.right = "0";
  bloque.style.zIndex = "5";

  // Aplicar color base verde claro al fondo de las celdas cubiertas
  for (let i = 0; i < duracion; i++) {
    const idxCelda = (8) + ((fila + i) * 8) + (dia + 1);
    const celda = grid.children[idxCelda];
    if (celda) celda.classList.add("bg-green-100");
  }

  celdaInicio.appendChild(bloque);
});

/* ==========================================================
  Muestra tooltip o log visual de turnos existentes por celda
========================================================== */
const celdas = cont.querySelectorAll(".drop-turno");
celdas.forEach(celda => {
  const dia = parseInt(celda.dataset.dia);
  const hora = celda.dataset.hora;
  const fecha = calcularFechaPorDia(dia);
  const lista = (turnos || []).filter(t => {
    if (!t.fecha) return false;
    if (t.fecha !== fecha) return false;
    const hI = Number(t.hora_inicio.split(":")[0]) + Number(t.hora_inicio.split(":")[1]) / 60;
    const hF = Number(t.hora_fin.split(":")[0]) + Number(t.hora_fin.split(":")[1]) / 60;
    const [hSelH, hSelM] = hora.split(":").map(Number);
    const hSel = hSelH + (hSelM || 0) / 60;
    return hSel >= hI && hSel < hF;
  });

  if (lista.length > 0) {
    // 🔹 Muestra un pequeño punto o texto con cantidad
    const marker = document.createElement("div");
    marker.className = "absolute bottom-1 right-1 text-[10px] text-gray-500 bg-yellow-50 px-1 rounded border border-yellow-300";
    marker.textContent = `${lista.length} turno${lista.length > 1 ? 's' : ''}`;
    celda.appendChild(marker);

    // Tooltip completo con nombres y horas
    celda.title = lista.map(t => `${t.hora_inicio}-${t.hora_fin} ${t.punto}`).join("\n");
  }
});

  activarCreacionTurno();  
 }

/* ==========================================================
   🔹 Activar creación visual de turnos en vista semanal
   ========================================================== */
let creandoTurno = null;

function activarCreacionTurno() {
  const grid = document.getElementById("gridSemana");
  if (!grid) return;

  // 🖱️ Al presionar mouse, comenzar selección
  grid.addEventListener("mousedown", e => {
    if (!e.target.classList.contains("drop-turno")) return;
    e.preventDefault();

    creandoTurno = {
      dia: e.target.dataset.dia,
      horaInicio: e.target.dataset.hora,
      celdaInicio: e.target,
      celdasSeleccionadas: [e.target]
    };

    e.target.classList.add("bg-blue-100", "ring", "ring-blue-300");
  });

  // 🖱️ Al mover el mouse, sombrear el rango
  grid.addEventListener("mouseover", e => {
    if (!creandoTurno) return;
    const celda = e.target.closest(".drop-turno");
    if (!celda || celda.dataset.dia !== creandoTurno.dia) return; // solo mismo día

    const celdaInicio = creandoTurno.celdaInicio;
    const todas = [...grid.querySelectorAll(`.drop-turno[data-dia="${creandoTurno.dia}"]`)];
    const iInicio = todas.indexOf(celdaInicio);
    const iActual = todas.indexOf(celda);

    creandoTurno.celdasSeleccionadas.forEach(c => c.classList.remove("bg-blue-200"));
    const rango = todas.slice(Math.min(iInicio, iActual), Math.max(iInicio, iActual) + 1);
    rango.forEach(c => c.classList.add("bg-blue-200"));
    creandoTurno.celdasSeleccionadas = rango;
  });

  // 🖱️ Al soltar mouse, finalizar y abrir popup
 grid.addEventListener("mouseup", async e => {
  if (!creandoTurno) return;
  const celdaFin = e.target.closest(".drop-turno");
  if (!celdaFin) return;

  const dia = parseInt(creandoTurno.dia);
  const horaInicio = creandoTurno.celdaInicio.dataset.hora;
  // const horaFin = celdaFin.dataset.hora;
  const fechaTurno = calcularFechaPorDia(dia);
  
  //  Ajustar horaFin sumando +1h al final del bloque
let horaFin = celdaFin.dataset.hora;
const [hFin, mFin] = horaFin.split(":").map(Number);
horaFin = `${String(hFin + 1).padStart(2, "0")}:${String(mFin).padStart(2, "0")}`;


  // ✅ Tomamos copia del rango ANTES de limpiar
  const rangoSeleccionado = [...(creandoTurno.celdasSeleccionadas || [])];

  // 🔹 Mostrar popup y esperar resultado
  const result = await mostrarPopupCreacionTurno(fechaTurno, horaInicio, horaFin, celdaFin);

  // ⚠️ Solo continuar si se confirma la creación
  if (result && result.ok) {
    // 🌿 Marca todas las celdas del rango en verde
    rangoSeleccionado.forEach(c => {
      c.classList.remove("bg-blue-100", "bg-blue-200", "ring", "ring-blue-300");
      c.classList.add("bg-green-100");
    });

    // 📦 Crear bloque visual del turno
    const bloque = document.createElement("div");
    bloque.className = "absolute inset-0 rounded text-xs text-white p-1 shadow bg-green-500 overflow-hidden";
    bloque.textContent = `${horaInicio}-${horaFin} ${result.punto || ""}`;

    // Calcula altura proporcional al número de celdas seleccionadas
    const numCeldas = rangoSeleccionado.length;
    bloque.style.height = `calc(${numCeldas} * 100%)`;
    bloque.style.top = "0";
    bloque.style.left = "0";
    bloque.style.right = "0";
    bloque.style.zIndex = "5";

    // Inserta el bloque en la primera celda del rango
    if (rangoSeleccionado.length > 0) {
      rangoSeleccionado[0].appendChild(bloque);
    }

    console.log("✅ Turno creado visualmente:", result);
	if (typeof mostrarAvisoCelda === "function" && celdaFin) {
  mostrarAvisoCelda(celdaFin, "✓ Creado visualmente", "ok");
}

 alert("Turno creado: " + JSON.stringify(result, null, 2)); // si querés mantener alert

  }

  //  Limpieza visual y reseteo (SIEMPRE al final)
  if (creandoTurno && creandoTurno.celdasSeleccionadas) {
    creandoTurno.celdasSeleccionadas.forEach(c =>
      c.classList.remove("bg-blue-100", "bg-blue-200", "ring", "ring-blue-300")
    );
  }
  creandoTurno = null;
});

  //  Cancelar selección si sale del grid o presiona ESC
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && creandoTurno) {
      // creandoTurno.celdasSeleccionadas.forEach(c => c.classList.remove("bg-blue-100", "bg-blue-200", "ring", "ring-blue-300"));
      if (creandoTurno && Array.isArray(creandoTurno.celdasSeleccionadas)) {
      creandoTurno.celdasSeleccionadas.forEach(c => c.classList.remove("bg-blue-100", "bg-blue-200", "ring", "ring-blue-300"));
    }
	  creandoTurno = null;
    }
  });
}

/* ==========================================================
   🔹 Utilidad: convertir día de la semana → fecha real (YYYY-MM-DD)
   ========================================================== */
/* function calcularFechaPorDia(dia) {
  // dia = 1 (lunes) ... 7 (domingo)
  const hoy = new Date();
  const diaSemana = hoy.getDay(); // 0=domingo ... 6=sábado
  const distanciaDesdeLunes = (diaSemana === 0 ? -6 : 1 - diaSemana);

  // calcular el lunes real de esta semana
  const lunes = new Date(hoy);
  lunes.setDate(hoy.getDate() + distanciaDesdeLunes);

  // agregar los días correctos (sin el -1)
  const fecha = new Date(lunes);
  fecha.setDate(lunes.getDate() + (dia - 1));

  // devolver formato YYYY-MM-DD local (sin UTC shift)
  const anio = fecha.getFullYear();
  const mes = String(fecha.getMonth() + 1).padStart(2, "0");
  const diaNum = String(fecha.getDate()).padStart(2, "0");
  return `${anio}-${mes}-${diaNum}`;
} */

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


/* ==========================================================
   🔹 Popup flotante para elegir punto y crear turno (Promise)
   ========================================================== */
async function mostrarPopupCreacionTurno(fecha, horaInicio, horaFin, celda) {
  return new Promise(async (resolve, reject) => {
    const anterior = document.getElementById("popupTurnoNuevo");
    if (anterior) anterior.remove();

    // 🕓 Corrige caso donde horaInicio == horaFin → suma 1h
    if (horaInicio === horaFin) {
      const [h, m] = horaInicio.split(":").map(Number);
      horaFin = `${String(h + 1).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    }

    const popup = document.createElement("div");
    popup.id = "popupTurnoNuevo";
    popup.className = `
      fixed z-[9999] bg-white border border-gray-300 shadow-2xl rounded-lg p-4 w-72
      animate-fadeIn text-sm
    `;
    popup.innerHTML = `
      <div class="font-semibold text-gray-800 mb-2">
        📅 ${fecha}<br>🕒 ${horaInicio} - ${horaFin}
      </div>
      <label class="block text-sm text-gray-600 mb-1">Seleccioná el punto:</label>
      <select id="selPuntoNuevo" class="w-full border rounded p-1 mb-3 text-sm">
        <option value="">Cargando puntos...</option>
      </select>
      <div class="flex justify-end gap-2">
        <button id="btnCancelarPopup" class="text-sm px-2 py-1 bg-gray-200 rounded hover:bg-gray-300">
          Cancelar
        </button>
        <button id="btnCrearPopup" class="text-sm px-3 py-1 bg-indigo-500 text-white rounded hover:bg-indigo-600">
          Crear
        </button>
      </div>
    `;
    document.body.appendChild(popup);

   // const rect = celda.getBoundingClientRect();
   // popup.style.top = `${rect.top + window.scrollY + 15}px`;
   // popup.style.left = `${rect.left + window.scrollX + 15}px`;
   
   const rect = celda.getBoundingClientRect();

//  Ajuste de posición (si no hay espacio abajo, se pone arriba)
const viewportHeight = window.innerHeight;
const popupHeight = 250; // Altura aproximada del popup

// Posición inicial (abajo y a la derecha de la celda)
let topPosition = rect.top + window.scrollY + 15;
let leftPosition = rect.left + window.scrollX + 15;

// Si el popup queda fuera de la pantalla por abajo, reajustar para que se muestre arriba de la celda.
if (rect.bottom + popupHeight > (viewportHeight)) {
    topPosition = rect.top + window.scrollY - popupHeight - 300; // Mueve el popup hacia arriba
	topPosition = Math.max(topPosition, 5);
}

popup.style.top = `${topPosition}px`;
popup.style.left = `${leftPosition}px`;

// ... dentro de async function mostrarPopupCreacionTurno(fecha, horaInicio, horaFin, celda) { ...
// ... después de document.body.appendChild(popup);

//  Lógica para hacer el popup arrastrable (Draggable)

let isDragging = false;
let currentX;
let currentY;
let initialX;
let initialY;
let xOffset = 0;
let yOffset = 0;

// Asegurar que el popup tenga 'position: fixed' para poder usar 'left' y 'top'
popup.style.position = 'fixed'; 

// 1. MOUSE DOWN: Comienza el arrastre
popup.addEventListener("mousedown", e => {
    // Solo arrastrar si el botón izquierdo está presionado (e.button === 0)
    if (e.button !== 0) return; 
    const tag = e.target.tagName.toLowerCase();
    if (tag === "select" || tag === "option" || tag === "button") return; //  No arrastrar en dropdowns ni botones

    initialX = e.clientX - xOffset;
    initialY = e.clientY - yOffset;

    isDragging = true;
    e.preventDefault(); // Evita la selección de texto
    
    // Opcional: Cambia el cursor para indicar arrastre
    popup.style.cursor = 'grabbing'; 
});

// 2. MOUSE UP: Finaliza el arrastre
document.addEventListener("mouseup", () => {
    isDragging = false;
    // Opcional: Restaura el cursor
    popup.style.cursor = 'default'; 
});

// 3. MOUSE MOVE: Mueve el elemento
document.addEventListener("mousemove", e => {
    if (!isDragging) return;

    currentX = e.clientX - initialX;
    currentY = e.clientY - initialY;

    xOffset = currentX;
    yOffset = currentY;

    // Aplicar las transformaciones para mover el popup
    // Usamos transform en lugar de left/top directos para mejor rendimiento
    popup.style.transform = `translate3d(${currentX}px, ${currentY}px, 0)`;
});

// ... El resto del  código de mostrarPopupCreacionTurno continúa  como si nada...


    // 🔹 Cargar puntos disponibles
    try {
      const resp = await fetch(`${apiBase}/turnos_admin.php?accion=puntos_disponibles&fecha=${fecha}`);
      const puntos = await resp.json();
      const sel = popup.querySelector("#selPuntoNuevo");
      sel.innerHTML = puntos.length
        ? puntos.map(p => `<option value="${p.id}">${p.nombre}</option>`).join("")
        : `<option value="">(Sin puntos disponibles)</option>`;
    } catch (err) {
      console.error("⚠️ Error al cargar puntos:", err);
    }
	
	
	
	
	
	// 💥 Parche 3: Cancelar con ESC
    const handleEscape = (e) => {
    if (e.key === "Escape") {
        popup.remove();
        document.removeEventListener("keydown", handleEscape); // Limpieza
        resolve({ cancelled: true }); // Retorna un objeto para indicar cancelación
    }
     };
    document.addEventListener("keydown", handleEscape);

    // ❌ Cancelar popup
    //popup.querySelector("#btnCancelarPopup").addEventListener("click", () => {
     // popup.remove();
     // resolve(null);
   // });
   
   // ❌ Cancelar popup (Modifica el resolve de 'btnCancelarPopup' para usar el mismo formato)
    popup.querySelector("#btnCancelarPopup").addEventListener("click", () => {
    popup.remove();
    document.removeEventListener("keydown", handleEscape); // Limpieza
    resolve({ cancelled: true }); // Retorna un objeto para indicar cancelación
     });

    // ✅ Crear turno en backend
    popup.querySelector("#btnCrearPopup").addEventListener("click", async () => {
      const puntoId = popup.querySelector("#selPuntoNuevo").value;
	  const puntoNombre = popup.querySelector("#selPuntoNuevo").selectedOptions[0]?.text || "(Sin punto)";
      if (!puntoId) {
        alert("Seleccioná un punto antes de crear el turno.");
        return;
      }

      const btn = popup.querySelector("#btnCrearPopup");
      btn.disabled = true;
      btn.textContent = "Creando...";

      const postData = {
        fecha,
        hora_inicio: horaInicio,
        hora_fin: horaFin,
        punto: puntoNombre,
        maximo_publicadores: 3
      };

      console.log("🧩 Datos que se envían al backend:", postData);
      console.log("📡 URL:", `${apiBase}/turnos_admin.php?accion=crear_manual`);


      try {
        const resp = await fetch(`${apiBase}/turnos_admin.php?accion=crear_manual`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(postData)
        });
        const data = await resp.json();

        if (data.ok) {
          celda.classList.add("bg-green-100");
          const nuevo = document.createElement("div");
          nuevo.className = "absolute inset-1 rounded text-xs text-white p-1 shadow bg-green-500";
          nuevo.textContent = `${horaInicio}-${horaFin}`;
          celda.appendChild(nuevo);
          popup.remove();
          resolve({ ok: true, ...postData });
        } else {
          celda.classList.add("bg-red-100");
          console.error("❌ Error creando turno:", data.error);
          popup.remove();
          resolve({ ok: false, error: data.error });
        }
      } catch (err) {
        console.error("⚠️ Error general creando turno:", err);
        popup.remove();
        reject(err);
      }
    });
  });
}

// ---------------- Animación CSS (una sola vez) --------------------
if (!document.getElementById("popupAnimStyle")) {
  const style = document.createElement("style");
  style.id = "popupAnimStyle";
  style.textContent = `
@keyframes fadeIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}
.animate-fadeIn { animation: fadeIn 0.15s ease-out; }
`;
  document.head.appendChild(style);
}
/* =======================================================================
      Seleccionar turnos en una misma celda ( si hay diferentes puntos )
  ======================================================================== */
async function mostrarSelectorTurno(turnos) {
  return new Promise(resolve => {
    const popup = document.createElement("div");
    popup.className = "fixed inset-0 bg-black/50 flex justify-center items-center z-[9999]";
    popup.innerHTML = `
      <div class="bg-white rounded-lg shadow-xl p-4 w-[340px]">
        <h3 class="font-semibold text-lg mb-2 text-indigo-700">📍 Seleccioná el turno</h3>
        <div class="max-h-[200px] overflow-y-auto mb-3">
          ${turnos.map(t => `
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
        const elegido = turnos.find(t => t.id == id);
        popup.remove();
        resolve(elegido);
      });
    });

    popup.querySelector("#btnCancelarSelTurno").onclick = () => {
      popup.remove();
      resolve(null);
    };
  });
}

/* ===============================================================
     🔹 Renderizar los usuarios para planificar calendario semanal
  ================================================================ */

function renderUsuariosSemana() {
  const list = document.getElementById("usuariosSemana");
  if (!list) return;
  list.innerHTML = "";
  usuarios.forEach(u => {
    const el = document.createElement("div");
    el.className = "draggable-user bg-blue-50 border border-blue-200 rounded p-2 mb-1 cursor-move text-sm";
    el.draggable = true;
    el.dataset.userId = u.id;
    el.textContent = u.full_name || u.name || u.email;
    el.addEventListener("dragstart", onDragStart);
    list.appendChild(el);
  });
}

/* ===============================================================
     🔹 calcular Fecha Desde Semana 
  ================================================================ */

function calcularFechaDesdeSemana(diaIndex) {
  const hoy = new Date();
  const lunes = new Date(hoy);
  const day = hoy.getDay();
  const diff = hoy.getDate() - day + (day === 0 ? -6 : 1); // lunes de esta semana
  lunes.setDate(diff);
  const fecha = new Date(lunes);
  fecha.setDate(lunes.getDate() + (diaIndex - 1));
  return fecha.toISOString().split('T')[0];
}

/* ===============================================================
     🔹 Modal rápido para crear turno (base visual)
  ================================================================ */

function abrirModalNuevoTurno(fecha, horaInicio) {
  const modal = document.createElement("div");
  modal.className = "fixed inset-0 bg-black bg-opacity-40 flex justify-center items-center z-50";
  modal.innerHTML = `
    <div class="bg-white rounded-lg shadow-xl p-6 w-[380px]">
      <h3 class="font-bold text-lg mb-3 text-indigo-700">➕ Crear nuevo turno</h3>
      <label class="block text-sm mb-1">📅 Fecha:</label>
      <input id="fechaTurnoNuevo" type="date" value="${fecha}" class="border rounded px-2 py-1 w-full mb-2">
      
      <label class="block text-sm mb-1">🕒 Hora inicio:</label>
      <input id="horaInicioTurnoNuevo" type="time" value="${horaInicio}" class="border rounded px-2 py-1 w-full mb-2">

      <label class="block text-sm mb-1">🕓 Hora fin:</label>
      <input id="horaFinTurnoNuevo" type="time" value="12:00" class="border rounded px-2 py-1 w-full mb-2">

      <label class="block text-sm mb-1">📍 Punto:</label>
      <input id="puntoTurnoNuevo" type="text" placeholder="Ej: Plaza San Pedro" class="border rounded px-2 py-1 w-full mb-4">

      <div class="flex justify-end gap-2">
        <button id="btnCancelarTurnoNuevo" class="px-3 py-1 bg-gray-300 rounded hover:bg-gray-400">Cancelar</button>
        <button id="btnGuardarTurnoNuevo" class="px-3 py-1 bg-indigo-500 text-white rounded hover:bg-indigo-600">Guardar</button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  document.getElementById("btnCancelarTurnoNuevo").onclick = () => modal.remove();
  document.getElementById("btnGuardarTurnoNuevo").onclick = async () => {
    const nuevo = {
      fecha: document.getElementById("fechaTurnoNuevo").value,
      hora_inicio: document.getElementById("horaInicioTurnoNuevo").value,
      hora_fin: document.getElementById("horaFinTurnoNuevo").value,
      punto: document.getElementById("puntoTurnoNuevo").value
    };

    console.log("🆕 Creando turno nuevo:", nuevo);
	
    // (Llamada a backend pendiente)
    // await fetch(`${apiBase}/turnos_admin.php?accion=crear_manual`, { method:'POST', body: JSON.stringify(nuevo), headers:{'Content-Type':'application/json'} });

    modal.remove();
    alert("Turno creado (simulado). Actualizá la vista para verlo.");
  };
}

/* ========================================================================
     Semanas del calendario para planificar turnos:
  ========================================================================= */
// ==============================================
// 📅 Control de semana sin trabarse
// ==============================================

let semanaInicial = null;  // lunes de referencia absoluto
let offsetSemanas = 0;     // desplazamiento relativo (+1 adelante, -1 atrás)

// Formateo local sin UTC (evita desfasajes de zona)
function formatISOlocal(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

// Calcula el lunes y domingo reales de una fecha base
function getRangoSemana(baseDate) {
  const base = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate());
  base.setHours(12, 0, 0, 0); // medio día → evita bugs DST

  const day = base.getDay(); // 0=domingo
  const diff = (day === 0 ? -6 : 1 - day);

  const lunes = new Date(base);
  lunes.setDate(base.getDate() + diff);
  lunes.setHours(0, 0, 0, 0);

  const domingo = new Date(lunes);
  domingo.setDate(lunes.getDate() + 6);
  domingo.setHours(23, 59, 59, 999);

  return {
    desde: formatISOlocal(lunes),
    hasta: formatISOlocal(domingo),
    lunes,
    domingo
  };
}

// ==============================================
// 🔄 Cambio de semana sin fallas de transición 
// ==============================================
async function cambiarSemana(delta = 0) {
  // Inicializar una vez (base fija = lunes actual)
  if (!semanaInicial) {
    const hoy = new Date();
    const { lunes } = getRangoSemana(hoy);
    semanaInicial = lunes; // punto fijo
  }

  // Actualizamos el contador de desplazamiento
  offsetSemanas += delta;

  // Nueva base: lunes inicial + (offset * 7 días)
  const nuevaBase = new Date(semanaInicial);
  nuevaBase.setDate(semanaInicial.getDate() + offsetSemanas * 7);

  const { desde, hasta, lunes } = getRangoSemana(nuevaBase);

  // Actualizamos el título en pantalla
  const titulo = document.getElementById("tituloSemana");
  titulo.textContent = `📆 Semana del ${desde.split('-').reverse().join('/')} al ${hasta.split('-').reverse().join('/')}`;
 // Tooltip con detalles de depuración
/*const detalle = [
  `Lunes base: ${lunes.toDateString()}`,
  `Domingo base: ${new Date(nuevaBase.getFullYear(), nuevaBase.getMonth(), nuevaBase.getDate() + 6).toDateString()}`,
  `Desde: ${desde}`,
  `Hasta: ${hasta}`
].join('\n'); */

// Texto informativo
  const detalle = [
    `Lunes base (semana mostrada): ${lunes.toDateString()}`,
    `Domingo base: ${new Date(nuevaBase.getFullYear(), nuevaBase.getMonth(), nuevaBase.getDate() + 6).toDateString()}`,
    `Semana inicial global: ${semanaInicial ? semanaInicial.toDateString() : '(no inicializada)'}`,
    `Desplazamiento de semanas: ${offsetSemanas}`,
    `Desde: ${desde}`,
    `Hasta: ${hasta}`
  ].join('\n');

const textoTooltip = detalle.trim();

// Si hay texto, lo guardamos en dataset y en title (compatibilidad)
// Si no, limpiamos atributos para evitar un cuadro vacío
if (textoTooltip) {
  titulo.dataset.tooltip = textoTooltip;
  titulo.setAttribute('title', textoTooltip);
} else {
  delete titulo.dataset.tooltip;
  titulo.removeAttribute('title');
}


  console.log(`📅 Cambiando a semana #${offsetSemanas} → ${desde} → ${hasta}`);

  // Mostrar spinner opcional
  const cont = document.getElementById("gridSemana")?.parentElement || document.body;
  let overlay = document.getElementById("spinnerSemana");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "spinnerSemana";
    overlay.className = "absolute inset-0 flex items-center justify-center bg-white/70 z-50";
    overlay.innerHTML = `<div class="text-indigo-600 text-sm flex items-center gap-2">
        <svg class="animate-spin h-6 w-6 text-indigo-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"/>
        <path fill="currentColor" d="M4 12a8 8 0 018-8v8z" class="opacity-75"/>
      </svg> Cargando...
    </div>`;
    cont.appendChild(overlay);
  } else overlay.classList.remove("hidden");

  try {
    const res = await fetch(`${apiBase}/turnos_admin.php?accion=listar_por_rango&desde=${desde}&hasta=${hasta}`);
    const data = await res.json();

    turnos = Object.entries(data).flatMap(([fecha, arr]) =>
      arr.map(t => ({ ...t, fecha }))
    );

    console.log(`✅ Semana cargada (${turnos.length} turnos)`);

    await renderSemana();
  } catch (err) {
    console.error("❌ Error cargando semana:", err);
  } finally {
    overlay.classList.add("hidden");
  }
}

/* ========================================================================
     Avisos de las operaciones realizadas ( reemplazar el console.log() )
  ========================================================================= */

/*
function mostrarAvisoCelda(celda, texto, tipo = "info") {
  const color =
    tipo === "ok" ? "bg-green-500/80"
    : tipo === "error" ? "bg-red-500/80"
    : "bg-indigo-500/80";

  const aviso = document.createElement("div");
  aviso.className = `absolute inset-0 flex items-center justify-center text-[10px] text-white font-medium rounded ${color} z-50`;
  aviso.textContent = texto;

  celda.appendChild(aviso);
  setTimeout(() => aviso.remove(), 2400);
}  */

function mostrarAvisoCelda(celda, mensaje, tipo = "info") {
  if (!celda) return;  // Por errores por objeto celda vacío (null) me daba en algunos lugares...

  const aviso = document.createElement("div");
  aviso.className = `
    absolute z-50 px-3 py-1 rounded text-xs font-medium text-white shadow-lg
    transition-opacity duration-500
    ${tipo === "ok" ? "bg-green-500" :
      tipo === "error" ? "bg-red-500" :
      "bg-gray-700"}
  `;
  aviso.textContent = mensaje;

  // Posicionar dentro de la celda
  aviso.style.top = "4px";
  aviso.style.left = "4px";
  aviso.style.pointerEvents = "none";

  celda.appendChild(aviso);

  // Desaparece suavemente
  setTimeout(() => (aviso.style.opacity = "0"), 1200);
  setTimeout(() => aviso.remove(), 1800);
}


  /* ==========================================================
     🔹 Actualización del panel lateral
  ========================================================== */
  function actualizarPanelResumen() {
    document.getElementById("countAsignados").textContent = resumen.totalAsignados;
    document.getElementById("countConflictos").textContent = resumen.conflictos.length;

    const listaConflictos = document.getElementById("listaConflictos");
    listaConflictos.innerHTML = resumen.conflictos.map(c => `<div>• ${c}</div>`).join("");

    // Simples cálculos visuales (podés extenderlo más tarde)
    const totalTurnos = turnos.length;
    resumen.turnosCompletos = Math.floor(resumen.totalAsignados / 3); // ejemplo: 3 por turno
    resumen.turnosVacantes = totalTurnos - resumen.turnosCompletos;

    document.getElementById("countCompletos").textContent = resumen.turnosCompletos;
    document.getElementById("countVacantes").textContent = resumen.turnosVacantes;
  }

  return { init };
})();
