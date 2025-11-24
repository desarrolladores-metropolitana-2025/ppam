// static/js/app_turnos_flask.js
const AppTurnos = (function(){
  // ---------- CONFIG: revisá estas URLs si tu Blueprint añade prefijos ---
  const apiBase = "/api/turnos";          // endpoint principal (turnos.py) -> listar, listar_por_rango, listar
  // const apiSolicitar = "/turnos/api/solicitar"; // endpoint para solicitar; ajustar según tu deploy
  const apiSolicitar = "/api/turnos?accion=solicitar";
  // Nota: si en tu turnos.py el route quedó en /api/api/solicitar cambia a "/api/api/solicitar"

  // ---------- Helpers ----------
  async function fetchJSON(url, opts = {}) {
    const res = await fetch(url, opts);
    if (!res.ok) {
      let text = await res.text().catch(()=>"");
      try { text = JSON.parse(text); } catch(e){}
      throw new Error("HTTP " + res.status + " — " + (text.message || text || res.statusText));
    }
    return res.json();
  }

  // ---------- Estado local ----------
  let state = { pointId: 1, pointNombre: '', month: null, year: null };

  // ---------- Init ----------
  function init(cfg){
    state.pointId = cfg.punto_id || 1;
    state.pointNombre = cfg.punto_name || 'Punto';
    state.month = (new Date()).getMonth();
    state.year = (new Date()).getFullYear();

    document.getElementById('puntoName').textContent = 'Punto: ' + state.pointNombre;
    document.getElementById('prevM').addEventListener('click', ()=> change(-1));
    document.getElementById('nextM').addEventListener('click', ()=> change(1));
    document.getElementById('closeTurnos').addEventListener('click', cerrarTurno);

    render();
  }

  // ---------- Cambiar mes ----------
  async function change(delta){
    // animación ligera
    const calendar = document.getElementById('calendarRoot');
    calendar.style.opacity = '0.3';
    await new Promise(r=>setTimeout(r,150));
    state.month += delta;
    if (state.month < 0) { state.month = 11; state.year--; }
    if (state.month > 11) { state.month = 0; state.year++; }
    await render();
    calendar.style.opacity = '1';
  }

  // ---------- Render del mes ----------
  async function render(){
    const months = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
    document.getElementById('monthLabel').innerText = months[state.month] + ' ' + state.year;

    const first = new Date(state.year, state.month, 1);
    const last = new Date(state.year, state.month+1, 0);
    const startWeekday = first.getDay(); // 0=Dom
    const total = last.getDate();

    const calendarRoot = document.getElementById('calendarRoot');
    calendarRoot.innerHTML = '';

    // headers
    const nombres = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
    nombres.forEach(n => {
      const h = document.createElement('div');
      h.className = 'day day-empty fw-bold text-center';
      h.style.background = 'transparent';
      h.innerText = n;
      calendarRoot.appendChild(h);
    });

    // empty slots
    for (let i=0;i<startWeekday;i++){
      const d = document.createElement('div');
      d.className = 'day day-empty';
      calendarRoot.appendChild(d);
    }

    // fetch días con turnos: usar listar_por_rango?punto=...&desde=...&hasta=...
    const desde = `${state.year}-${String(state.month+1).padStart(2,'0')}-01`;
    const hasta = `${state.year}-${String(state.month+1).padStart(2,'0')}-${String(total).padStart(2,'0')}`;

    let diasConTurnos = {};
    try {
      const url = `${apiBase}?accion=listar_por_rango&desde=${desde}&hasta=${hasta}&punto=${state.pointId}`;
      const res = await fetch(url);
      if (res.ok) diasConTurnos = await res.json();
    } catch (e) {
      console.warn("No se pudo obtener resumen mensual:", e);
    }

    // fill days
    for (let day = 1; day <= total; day++){
      const d = document.createElement('div');
      d.className = 'day';
      d.innerHTML = `<div style="font-weight:800">${day}</div>`;

      const key = `${state.year}-${String(state.month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
      const items = diasConTurnos[key] || [];

      // compute states array if available
      if (items.length > 0) {
        const estados = items.map(it => it.estado || '');
        if (estados.includes('creado')) d.classList.add('day-green');
        else if (estados.includes('pendiente')) d.classList.add('day-purple');
        else if (estados.includes('abierto')) d.classList.add('day-yellow');
        else if (estados.includes('asignado')) d.classList.add('day-mustard');
        else if (estados.includes('planificado')) d.classList.add('day-red');
        else if (estados.includes('publicado')) d.classList.add('day-blue');
        else if (estados.includes('completado')) d.classList.add('day-orange');
        else if (estados.includes('cancelado')) d.classList.add('day-gray');
        else d.classList.add('day-green');
      }

      // highlight today
      const hoy = new Date();
      if (day === hoy.getDate() && state.month === hoy.getMonth() && state.year === hoy.getFullYear()) {
        d.classList.add('day-dark');
      }

      // click -> load turnos of the day
      d.addEventListener('click', () => {
        document.querySelectorAll('.day.selected').forEach(el => el.classList.remove('selected'));
        d.classList.add('selected');
        loadTurnosForDay(state.pointId, key);
      });

      calendarRoot.appendChild(d);
    }

  }

  // ---------- cargar turnos del día ----------
  async function loadTurnosForDay(pointId, dateISO){
    const cont = document.getElementById('turnosContainer');
    const list = document.getElementById('turnosList');
    const label = document.getElementById('turnosForLabel');
    cont.classList.remove('d-none');
    label.innerText = `Turnos disponibles — ${dateISO}`;
    list.innerHTML = '<div class="loader">Cargando turnos...</div>';

    try {
      // llamar al endpoint listar por punto+fecha: /api/turnos?accion=listar&fecha=...&punto=...
      const url = `${apiBase}?accion=listar&fecha=${encodeURIComponent(dateISO)}&punto=${encodeURIComponent(pointId)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Error ' + res.status);
      const data = await res.json();
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
        const meta = document.createElement('div');
        meta.innerHTML = `<div><strong>${t.punto || ''}</strong></div>
                          <div style="font-weight:700">${t.hora_inicio || ''} - ${t.hora_fin || ''}</div>
                          <div class="small text-muted">${t.cupos ? t.cupos + ' lugares' : ''} ${t.estado ? '['+t.estado+']':''}</div>`;
        const actions = document.createElement('div');
        const btn = document.createElement('button');
        btn.className = 'btn btn-sm btn-primary btn-request';
        btn.textContent = 'Solicitar';
        btn.addEventListener('click', ()=> solicitarTurno(t.id, t));
        actions.appendChild(btn);

        item.appendChild(meta);
        item.appendChild(actions);
        container.appendChild(item);
      });

      list.appendChild(container);
    } catch(err){
      list.innerHTML = `<div class="loader">Error al cargar: ${err.message}</div>`;
      console.error(err);
    }
  }

  // cerrar panel lateral
  function cerrarTurno(){
    const cont = document.getElementById('turnosContainer');
    cont.classList.add('d-none');
    document.querySelectorAll('.day.selected').forEach(el=>el.classList.remove('selected'));
  }

  // ---------- solicitar turno ----------
  async function solicitarTurno(turnoId, turnoObj){
    if (!confirm('¿Deseás solicitar este turno?')) return;

    // Si el usuario no está logueado el backend devolverá 401
    try {
      // POST JSON a la URL de solicitar
      const res = await fetch(apiSolicitar, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ turno_id: turnoId })
      });

      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.error || JSON.stringify(json) || 'Error');
      }

      alert(json.message || 'Solicitud enviada correctamente');
      // refrescar lista local (simple: recargar los turnos del día)
      if (turnoObj && turnoObj.fecha) loadTurnosForDay(state.pointId, turnoObj.fecha);
    } catch(err){
      alert('No se pudo solicitar: ' + (err.message || err));
      console.error(err);
    }
  }
  // ----------------------  DESDE PUBVIEW.HTML -------------------------------------
  async function initCalendarTest(rootId, monthLabelId, prevId, nextId){
    const tempState = {
        pointId: 1,
        pointNombre: 'Punto de prueba',
        month: (new Date()).getMonth(),
        year: (new Date()).getFullYear()
    };

    const calendarRoot = document.getElementById(rootId);
    const monthLabel = document.getElementById(monthLabelId);
    const prevBtn = document.getElementById(prevId);
    const nextBtn = document.getElementById(nextId);

    monthLabel.innerText = new Date(tempState.year, tempState.month).toLocaleString('es-ES',{month:'long', year:'numeric'});

    prevBtn.addEventListener('click', async ()=>{ tempState.month--; if(tempState.month<0){ tempState.month=11; tempState.year--; } await renderTest(); });
    nextBtn.addEventListener('click', async ()=>{ tempState.month++; if(tempState.month>11){ tempState.month=0; tempState.year++; } await renderTest(); });

    async function renderTest(){
        const first = new Date(tempState.year, tempState.month, 1);
        const last = new Date(tempState.year, tempState.month+1, 0);
        const startWeekday = first.getDay();
        const total = last.getDate();

        calendarRoot.innerHTML = '';

        const nombres = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
        nombres.forEach(n => {
            const h = document.createElement('div');
            h.className = 'day day-empty fw-bold text-center';
            h.innerText = n;
            calendarRoot.appendChild(h);
        });

        for(let i=0;i<startWeekday;i++){
            const d = document.createElement('div');
            d.className='day day-empty';
            calendarRoot.appendChild(d);
        }

        for(let day=1; day<=total; day++){
            const d = document.createElement('div');
            d.className='day';
            d.innerHTML = `<div style="font-weight:800">${day}</div>`;
            calendarRoot.appendChild(d);
        }

        monthLabel.innerText = new Date(tempState.year,tempState.month).toLocaleString('es-ES',{month:'long', year:'numeric'});
    }

    await renderTest();
}

async function cambiarPunto(puntoId, puntoName){
    // Cambiar state interno
    state = this.state || {};
    state.pointId = puntoId;
    state.pointNombre = puntoName;
    state.month = (new Date()).getMonth();
    state.year = (new Date()).getFullYear();

    document.getElementById('puntoName').textContent = 'Punto: ' + puntoName;
	 // Renderizar limpio
    const calendarRoot = document.getElementById('calendarRoot');
    calendarRoot.innerHTML = '';
	 // Limpiar turnos
    const turnosList = document.getElementById('turnosList');
    if(turnosList) turnosList.innerHTML = '';


    await render();
}
  // exposed
  return {
    init: init,
    loadTurnosForDay: loadTurnosForDay,
	 cambiarPunto: cambiarPunto,  // <--- aquí la expongo
	 initCalendarTest: initCalendarTest // <-- lo mismo esta...
  };  

  
})();
