// Sistema PPAM - 18/102025
// app_planificador.js - Planificador visual básico (drag & drop)
// Requiere: tener un contenedor #tab-planificar en el DOM.
const AppPlanificador = (() => {
  const apiBase = '../api/turnos_admin.php';
  let root, usersPanel, gridRoot, weekStartDate;

  // configura rango semana (lunes..domingo) a partir de fecha (Date)
  function startOfWeek(d) {
    const date = new Date(d);
    const day = (date.getDay() + 6) % 7; // lunes=0
    date.setDate(date.getDate() - day);
    date.setHours(0,0,0,0);
    return date;
  }

  function formatISO(d) {
    return d.toISOString().slice(0,10);
  }

  // crea estructura DOM dentro de #tab-planificar
  function renderShell() {
    root = document.getElementById('tab-planificar');
    root.innerHTML = `
      <div class="planificador">
        <div class="panel-lateral">
          <h3>Usuarios / Solicitudes</h3>
          <div id="usuariosDisponibles">Cargando usuarios...</div>
          <div style="margin-top:8px">
            <button id="btnSugerir" class="plan-ctrl">💡 Sugerir con Bot</button>
            <button id="btnRefresh" class="plan-ctrl" style="margin-left:8px">🔄 Refrescar</button>
          </div>
          <div class="plan-legend" style="margin-top:8px">
            <div><span class="legend-dot" style="background:#55c373"></span>Disponible</div>
            <div><span class="legend-dot" style="background:#f7dc6f"></span>Abierto</div>
            <div><span class="legend-dot" style="background:#f4a261"></span>Otros</div>
          </div>
        </div>

        <div class="panel-calendario">
          <div class="plan-toolbar">
            <div class="left">
              <button id="prevWeek" class="secondary">← Semana</button>
              <div id="tituloSemana" style="font-weight:700; margin:0 8px"></div>
              <button id="nextWeek" class="secondary">Semana →</button>
            </div>
            <div>
              <button id="btnGuardar" class="">Guardar cambios</button>
              <button id="btnVolver" class="secondary" style="margin-left:8px">Volver</button>
            </div>
          </div>

          <div class="grid-planificacion" id="gridPlanificacion">
            <!-- grid construido programáticamente -->
          </div>
        </div>
      </div>
    `;

    usersPanel = document.getElementById('usuariosDisponibles');
    gridRoot = document.getElementById('gridPlanificacion');

    document.getElementById('prevWeek').addEventListener('click', ()=> changeWeek(-1));
    document.getElementById('nextWeek').addEventListener('click', ()=> changeWeek(1));
    document.getElementById('btnRefresh').addEventListener('click', initData);
    document.getElementById('btnVolver').addEventListener('click', () => {
      // oculta la pestaña planificar y vuelve a 'turnos' (tu mostrarTab)
      if (typeof mostrarTab === 'function') mostrarTab('turnos');
      else document.getElementById('tab-planificar').classList.add('hidden');
    });
    document.getElementById('btnSugerir').addEventListener('click', sugerirConBot);
    document.getElementById('btnGuardar').addEventListener('click', () => alert('Guardar: en esta versión base guardado automático al soltar (ver consola).'));
  }

  // navegar semana
  function changeWeek(delta) {
    weekStartDate.setDate(weekStartDate.getDate() + delta*7);
    buildGrid();
    loadTurnosToGrid();
  }

  // carga usuarios (pendientes / disponibles)
  async function loadUsers() {
    usersPanel.innerHTML = 'Cargando usuarios...';
    try {
      // endpoint asumido: /api/postulantes.php?accion=listar_disponibles  (fallback /api/postulantes.php?accion=listar)
      let resp = await fetch('/api/postulantes.php?accion=listar_disponibles');
      if (!resp.ok) resp = await fetch('/api/postulantes.php?accion=listar');
      const users = await resp.json();
      usersPanel.innerHTML = '';
      if (!Array.isArray(users) || users.length === 0) {
        usersPanel.innerHTML = '<div>No hay usuarios disponibles.</div>';
        return;
      }
      users.forEach(u => {
        const div = document.createElement('div');
        div.className = 'user-chip';
        div.draggable = true;
        div.dataset.userid = u.id ?? u.user_id ?? u.usuario ?? 0;
        div.innerHTML = `<div class="name">${u.full_name ?? u.last_name ?? u.name ?? ('U' + div.dataset.userid)}</div>
                         <div class="meta">${u.pref ?? ''}</div>`;
        div.addEventListener('dragstart', onDragStart);
        div.addEventListener('dragend', onDragEnd);
        usersPanel.appendChild(div);
      });
    } catch (e) {
      usersPanel.innerHTML = '<div class="error">Error cargando usuarios</div>';
      console.error(e);
    }
  }

  function onDragStart(e) {
    e.dataTransfer.setData('text/plain', JSON.stringify({
      usuario_id: this.dataset.userid,
      nombre: this.querySelector('.name').innerText
    }));
    this.classList.add('dragging');
  }
  function onDragEnd(e) {
    this.classList.remove('dragging');
  }

  // crea la grilla semanal: columna tiempo + 7 días
  function buildGrid() {
    gridRoot.innerHTML = '';
    const hours = [8,9,10,11,12,13,14,15,16,17,18,19]; // franjas por defecto
    // header row (empty time cell + day names)
    gridRoot.appendChild(makeHeader(''));
    const days = [];
    for (let i=0;i<7;i++){
      const d = new Date(weekStartDate);
      d.setDate(weekStartDate.getDate() + i);
      days.push(d);
      const h = makeHeader(d.toLocaleDateString('es-ES', { weekday:'short', day:'numeric', month:'short' }));
      gridRoot.appendChild(h);
    }

    // rows: time + cells
    hours.forEach(hour => {
      const timeCol = document.createElement('div');
      timeCol.className = 'time-col';
      timeCol.innerText = (hour < 10 ? '0'+hour : hour) + ':00';
      gridRoot.appendChild(timeCol);

      for (let i=0;i<7;i++){
        const cell = document.createElement('div');
        cell.className = 'slot-cell';
        cell.dataset.date = formatISO(new Date(weekStartDate.getFullYear(), weekStartDate.getMonth(), weekStartDate.getDate() + i));
        cell.dataset.hour = String(hour).padStart(2,'0') + ':00';
        // make cell droppable
        cell.addEventListener('dragover', (ev)=> { ev.preventDefault(); cell.classList.add('drop-hover'); });
        cell.addEventListener('dragleave', ()=> cell.classList.remove('drop-hover'));
        cell.addEventListener('drop', async (ev) => {
          ev.preventDefault();
          cell.classList.remove('drop-hover');
          try {
            const payload = JSON.parse(ev.dataTransfer.getData('text/plain'));
            await onDropUsuarioEnCelda(payload.usuario_id, payload.nombre, cell);
          } catch(e) { console.error(e); }
        });
        gridRoot.appendChild(cell);
      }
    });

    // mostrar semana en titulo
    const start = new Date(weekStartDate);
    const end = new Date(weekStartDate);
    end.setDate(start.getDate() + 6);
    document.getElementById('tituloSemana').innerText = `${start.toLocaleDateString()} — ${end.toLocaleDateString()}`;
  }

  function makeHeader(text) {
    const h = document.createElement('div');
    h.className = 'slot-header';
    h.innerText = text;
    return h;
  }

  // carga turnos del rango semana y los empotra en las celdas correspondientes
  async function loadTurnosToGrid() {
    // calculo desde / hasta
    const desde = formatISO(weekStartDate);
    const hastaDate = new Date(weekStartDate);
    hastaDate.setDate(hastaDate.getDate() + 6);
    const hasta = formatISO(hastaDate);

    // endpoint: listar_por_rango (según tu API)
    try {
      const resp = await fetch(`${apiBase}?accion=listar_por_rango&desde=${desde}&hasta=${hasta}`);
      if (!resp.ok) throw new Error('Error al pedir turnos');
      const data = await resp.json();
      // tu listar_por_rango devolvía arreglo por fecha -> aquí lo adaptamos:
      // si devuelve { "2025-10-21":[{...}], ... } lo usamos, si devuelve lista lo convertimos
      const mapping = {};
      if (Array.isArray(data)) {
        // lista plana -> agrupar por fecha
        data.forEach(t => {
          (mapping[t.fecha] = mapping[t.fecha] || []).push(t);
        });
      } else {
        Object.assign(mapping, data);
      }
      // vaciar células y luego poner turnos
      gridRoot.querySelectorAll('.slot-cell').forEach(c => c.innerHTML = '');
      gridRoot.querySelectorAll('.slot-cell').forEach(cell => {
        const date = cell.dataset.date;
        const hour = cell.dataset.hour;
        const items = mapping[date] || [];
        // filtrar turnos que empiecen en esa hora
        items.filter(t => (t.hora_inicio || '').slice(0,2)+':00' === hour).forEach(t => {
          const b = document.createElement('div');
          b.className = 'turno-block';
          b.dataset.turnoId = t.id ?? t.turno_id ?? t.turnoId ?? 0;
          b.innerHTML = `<div class="turno-meta">${(t.hora_inicio||'') .slice(0,5)} - ${(t.hora_fin||'').slice(0,5)}</div>
                         <div style="font-size:12px;color:#345">${t.punto ?? t.nombre ?? t.punto }</div>
                         <div class="turno-users"></div>`;
          // si ya hay participantes info: puede venir como array turno_participantes
          const usersWrap = b.querySelector('.turno-users');
          if (Array.isArray(t.participantes)) {
            t.participantes.forEach(p => {
              const up = document.createElement('span');
              up.className = 'user-pill';
              up.innerText = p.nombre ?? p.usuario ?? p.user ?? p.usuario_id;
              usersWrap.appendChild(up);
            });
          }
          cell.appendChild(b);
        });
      });
    } catch (e) {
      console.error('Error cargarTurnosToGrid', e);
    }
  }

  // manejador cuando soltás usuario en celda
  async function onDropUsuarioEnCelda(usuarioId, nombre, cell) {
    // busca turno-block dentro de la celda (si hay varios tomamos el primero)
    const turnoBlock = cell.querySelector('.turno-block');
    if (!turnoBlock) {
      alert('No hay un turno creado en esa franja. Primero crea un turno o suelta sobre un bloque de turno.');
      return;
    }
    const turnoId = turnoBlock.dataset.turnoId;
    if (!turnoId) {
      alert('Turno desconocido');
      return;
    }

    // feedback inmediato UI (optimista)
    const pill = document.createElement('span');
    pill.className = 'user-pill';
    pill.innerText = nombre;
    turnoBlock.querySelector('.turno-users').appendChild(pill);

    // POST a tu API (asignación manual)
    try {
      const resp = await fetch('../api/turnos_admin.php?accion=asignar_manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ turno_id: turnoId, usuario_id: usuarioId, rol: 'publicador' })
      });
      if (!resp.ok) {
        // intentar fallback a 'asignar' (si existe)
        const resp2 = await fetch('../api/turnos.php?accion=asignar', {
          method: 'POST',
          body: new URLSearchParams({ turno_id: turnoId })
        });
        if (!resp2.ok) throw new Error('Error en backend al asignar');
        const r2 = await resp2.json();
        console.log('fallback asignar ->', r2);
      } else {
        const json = await resp.json();
        console.log('asignar_manual ->', json);
        if (json.error) {
          alert('Backend: ' + json.error);
          pill.remove();
        } else {
          // ok: puedes refrescar listados si querés
        }
      }
    } catch (e) {
      console.error(e);
      alert('Error al asignar: ' + e.message);
      pill.remove();
    }
  }

  // Sugerir con Bot (llama al endpoint dispatcher que tengas)
  async function sugerirConBot() {
    if (!confirm('Generar sugerencias del Bot para esta semana?')) return;
    try {
      const desde = formatISO(weekStartDate);
      const hastaDate = new Date(weekStartDate);
      hastaDate.setDate(hastaDate.getDate() + 6);
      const hasta = formatISO(hastaDate);
      const resp = await fetch('/api/bot.php?accion=sugerir&desde=' + desde + '&hasta=' + hasta);
      const json = await resp.json();
      console.log('sugerencias bot', json);
      alert('Sugerencias generadas (ver consola). Luego podés revisar y aceptar manualmente.');
      // opcional: refrescar la grilla con sugerencias si tu API pone propuestas en DB
      await loadTurnosToGrid();
    } catch(e) {
      console.error(e);
      alert('Error al solicitar al bot: ' + e.message);
    }
  }

  // inicializadores
  async function initData() {
    await loadUsers();
    await loadTurnosToGrid();
  }

  function init() {
    weekStartDate = startOfWeek(new Date()); // esta semana por defecto
    renderShell();
    buildGrid();
    initData();
  }

  return { init };
})();
