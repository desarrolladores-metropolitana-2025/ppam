// /js/app_turnos.js
// Sistema PPAM - 8/10/2025
const AppTurnos = (function(){
  const apiBase = "../api";

  async function fetchJSON(url, options = {}) {
    const res = await fetch(url, options);
    if (!res.ok) {
      let text = await res.text();
      try { text = JSON.parse(text); } catch(e){}
      throw new Error("HTTP " + res.status + " — " + (text.message || text || res.statusText));
    }
    return res.json();
  }

  // carga puntos (para index)
  async function loadPuntos(){
    const grid = document.getElementById('puntosGrid');
    if (!grid) return;
    try {
      const pts = await fetchJSON(`${apiBase}/puntos.php?accion=listar`);
      grid.innerHTML = '';
      pts.forEach(p => {
        const a = document.createElement('a');
        a.href = `/application/calendario.php?p=${p.id}&nomb=${p.nombre}`;
        a.className = 'punto-card';
        a.innerHTML = `<div>${p.nombre}</div>`;
        grid.appendChild(a);
      });
    } catch (err) {
      grid.innerHTML = `<div class="loader">Error cargando puntos: ${err.message}</div>`;
      console.error(err);
    }
  }

 async function marcarDiasConTurnos(pointId, year, month) {
  const desde = `${year}-${String(month+1).padStart(2,'0')}-01`;
  const hasta = `${year}-${String(month+1).padStart(2,'0')}-31`;
  const res = await fetch(`../api/turnos.php?accion=listar_por_rango&punto=${pointId}&desde=${desde}&hasta=${hasta}`);
  const data = await res.json();
  return data;
}   // ← acá termina la función, sin coma


  // Calendar logic for calendario.php
  const cal = {
    elRoot: null,
    pointId: 1,
	pointNombre: ' ',
    month: null,
    year: null,
    init(pointId, pointNomb) {
      this.pointId = pointId||1;
	  this.pointNombre = pointNomb||'no hay punto';
      this.elRoot = document.getElementById('calendarRoot');
      this.month = (new Date()).getMonth();
      this.year = (new Date()).getFullYear();
      document.getElementById('puntoName').innerText = 'Punto: ' + this.pointNombre;
      document.getElementById('prevM').addEventListener('click', ()=>{ this.change(-1) });
      document.getElementById('nextM').addEventListener('click', ()=>{ this.change(1) });
      this.render();
    },
async change(d) {
  const calendar = document.getElementById('calendarRoot');
  const label = document.getElementById('monthLabel');

  // animación de salida
  label.classList.add('fade-out');
  calendar.classList.add(d > 0 ? 'slide-left' : 'slide-right');

  await new Promise(r => setTimeout(r, 350));

  // cambiar mes
  this.month += d;
  if (this.month < 0) { this.month = 11; this.year--; }
  if (this.month > 11) { this.month = 0; this.year++; }

  // re-render
  await this.render();

  // reset clases viejas
  calendar.classList.remove('slide-left', 'slide-right');
  label.classList.remove('fade-out');

  // animación de entrada
  calendar.style.opacity = '0';
  calendar.style.transform = d > 0 ? 'translateX(40px)' : 'translateX(-40px)';
  label.classList.add('fade-in');

  await new Promise(r => setTimeout(r, 350));

  calendar.style.transition = 'transform 0.4s ease, opacity 0.4s ease';
  calendar.style.opacity = '1';
  calendar.style.transform = 'translateX(0)';

  setTimeout(() => {
    label.classList.remove('fade-in');
    calendar.style.transition = '';
  }, 400);
},


async render() {
  const months = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
  document.getElementById('monthLabel').innerText = months[this.month] + ' ' + this.year;

  // Datos de mes actual
  const first = new Date(this.year, this.month, 1);
  const last = new Date(this.year, this.month+1, 0);
  const startWeekday = first.getDay(); // 0=Dom
  const total = last.getDate();

  // 1️⃣ Pedimos al backend los días que tienen turnos abiertos
  let diasConTurnos = {};
  try {
    const desde = `${this.year}-${String(this.month+1).padStart(2,'0')}-01`;
    const hasta = `${this.year}-${String(this.month+1).padStart(2,'0')}-${String(total).padStart(2,'0')}`;
    const res = await fetch(`${apiBase}/turnos.php?accion=listar_por_rango&punto=${this.pointId}&desde=${desde}&hasta=${hasta}`);
    if (res.ok) diasConTurnos = await res.json();
  } catch(e) {
    console.warn('no se pudo obtener resumen mensual', e);
  }

  // 2️⃣ Construimos el calendario visual
  this.elRoot.innerHTML = '';

  // Cabecera de días (Dom, Lun, Mar...)
  const nombres = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
  nombres.forEach(n => {
    const h = document.createElement('div');
    h.className = 'day day-empty';
    h.style.fontWeight = '800';
    h.style.background = 'transparent';
    h.innerText = n;
    this.elRoot.appendChild(h);
  });

  // Espacios vacíos antes del primer día
  for (let i=0; i<startWeekday; i++) {
    const d = document.createElement('div');
    d.className = 'day day-empty';
    this.elRoot.appendChild(d);
  }

  // 3️⃣ Días del mes
  for (let day=1; day<=total; day++) {
    const d = document.createElement('div');
    d.className = 'day';
    d.innerHTML = `<div style="font-weight:800">${day}</div>`;

    // Fecha en formato YYYY-MM-DD
    const key = `${this.year}-${String(this.month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;

    //  Si el backend marcó turnos para ese día, coloreamos
    // if (diasConTurnos[key]) {
    //  d.classList.add(diasConTurnos[key] > 2 ? 'day-orange' : 'day-green');
    // }
	
	// Cambio: Resaltamos en que estado está el turno...
	
	const items = diasConTurnos[key] || [];

  // 🔹 Aquí va el bloque de colores
  if (items.length > 0) {
    const estados = items.map(it => it.estado);
	
	/*
creado
pendiente
abierto
asignado
planificado
publicado
completado
cancelado
DB:  enum('creado','pendiente','abierto','asignado','planificado','publicado','completado','cancelado')
		*/

    if (estados.includes('creado')) {
      d.classList.add('day-green');
    } else if (estados.includes('pendiente')) {
      d.classList.add('day-purple');
    } else if (estados.includes('abierto')) {
      d.classList.add('day-yellow');
    } else if (estados.includes('asignado')) {
      d.classList.add('day-mustard');
    } else if (estados.includes('planificado')) {
      d.classList.add('day-red');
	} else if (estados.includes('publicado')) {
      d.classList.add('day-blue');
	} else if (estados.includes('completado')) {
      d.classList.add('day-orange');
	} else if (estados.includes('cancelado')) {
      d.classList.add('day-gray');  
	} else {
      d.classList.add('day-dark');
    }
  }


    // Resalta el día actual
    const hoy = new Date();
    if (
      day === hoy.getDate() &&
      this.month === hoy.getMonth() &&
      this.year === hoy.getFullYear()
    ) {
      d.classList.add('day-dark');
    }  
    
	// Click → cargar turnos de ese día
	d.addEventListener('click', ()=> {
  // 🔹 eliminar selección previa
  document.querySelectorAll('.day.selected').forEach(el => el.classList.remove('selected'));
  // 🔹 marcar el nuevo
  d.classList.add('selected');
  // 🔹 cargar los turnos del día
  loadTurnosForDay(this.pointId, key);
});

    this.elRoot.appendChild(d);
    }
  } // Fin de render()
   
  };     // Fin de const cal

  // load turnos for a specific point & date -> shows in side panel
  async function loadTurnosForDay(pointId, dateISO) {
    const cont = document.getElementById('turnosContainer');
    const list = document.getElementById('turnosList');
    const label = document.getElementById('turnosForLabel');
    cont.classList.remove('card-hidden');
    label.innerText = `Turnos disponibles — ${dateISO}`;
    list.innerHTML = '<div class="loader">Cargando turnos...</div>';
    try {
      const resp = await fetch(`${apiBase}/turnos.php?accion=listar&punto=${pointId}&fecha=${dateISO}`);
      if (!resp.ok) throw new Error('Error ' + resp.status);
      const data = await resp.json();
      if (!Array.isArray(data) || data.length === 0) {
        list.innerHTML = '<div class="loader">No hay turnos en esa fecha.</div>';
        return;
      }
      list.innerHTML = '';
      const container = document.createElement('div');
      container.className = 'turnos-list';
      data.forEach(t => {
        const item = document.createElement('div');
        item.className = 'turno-item';
        item.innerHTML = `
          <div class="turno-meta">
            <div>${t.punto}</div>
            <div style="font-weight:700">${t.hora_inicio} - ${t.hora_fin}</div>
            <div style="font-size:13px;color:#666">${t.cupos ? t.cupos + ' lugares' : ''} ${t.estado ? '['+t.estado+']':''}</div>
          </div>
          <div class="turno-actions">
            <button class="btn-request">Solicitar</button>
          </div>
        `;
        item.querySelector('.btn-request').addEventListener('click', ()=> solicitarTurno(t.id));
		container.appendChild(item);
		        
      });
      list.appendChild(container);
    } catch (err) {
      list.innerHTML = `<div class="loader">Error al cargar: ${err.message}</div>`;
      console.error(err);
    }
  }   // Fin función loadTurnosForDay();
  
  // Agregado ahora: cerrarTurnos()
  
 const boton = document.getElementById("closeTurnos");
if (boton) {
  boton.addEventListener('click', () => cerrarTurno());
}

  
function cerrarTurno() {
  console.log("Cerrando turno:");

  // localizar el contenedor principal
  const contenedor = document.getElementById('turnosContainer');
  if (!contenedor) return;

  // agregar clase para ocultar con animación
  contenedor.classList.add('card-hidden');

  // opcional: mostrar mensaje breve o limpiar contenido
  setTimeout(() => {
    // contenedor.style.display = 'none';
    console.log(`Turnos cerrado visualmente`);
  }, 400); // coincide con la duración del transition
}
  
  // -----------Fin cerrarTurnos()

  async function solicitarTurno(turnoId) {
    if (!confirm('¿Deseás solicitar este turno?')) return;
    try {
      const res = await fetch(`${apiBase}/turnos.php?accion=solicitar&id=${turnoId}`, {
        method: 'POST',
        credentials: 'same-origin'
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || json.message || 'Error al solicitar');
      alert(json.mensaje || 'Solicitud enviada correctamente');
      // luego puedes recargar paneles
      // recargar solicitudes o calendario
      if (document.getElementById('turnosList')) {
        // try to refresh visible list (simple approach: close panel)
        document.getElementById('turnosContainer').classList.add('card-hidden');
      }
    } catch (err) {
      alert('No se pudo solicitar: ' + err.message);
      console.error(err);
    }
  }

  // expose functions
  return {
    loadPuntos,
    initCalendar(p, nomb) { cal.init(p, nomb); },
    loadGlobalTurnos: async function(){
      const root = document.getElementById('globalTurnos');
      if (!root) return;
      try {
        const data = await fetchJSON(`${apiBase}/turnos.php?accion=listar&estado=abierto`);
        root.innerHTML = '';
        data.forEach(t => {
          const card = document.createElement('div');
          card.className = 'turno-card';
          card.innerHTML = `<div style="font-weight:800">${t.punto}</div>
                            <div style="margin:6px 0">${t.fecha} — ${t.hora_inicio} - ${t.hora_fin}</div>
                            <div><button class="btn-request" style="background:linear-gradient(180deg,#4fa7a7,#2f8f8f);color:#fff;padding:8px 10px;border-radius:8px;border:none;cursor:pointer">Solicitar</button></div>`;
          card.querySelector('.btn-request').addEventListener('click', ()=> solicitarTurno(t.id));
          root.appendChild(card);
        });
      } catch (err) {
        root.innerHTML = `<div class="loader">Error: ${err.message}</div>`;
      }
    },
    //  Pequeña utilidad para delplegar el calendario desde otras páginas...
    loadTurnosForDay
  };
})();
