// static/js/calendario_full.js
const CalendarioFull = (function(){
  let calendar = null;
  let currentEvent = null;
  const modal = document.getElementById('turnoModal');

  function init(cfg){
    const calendarEl = document.getElementById('calendar');
    calendar = new FullCalendar.Calendar(calendarEl, {
      initialView: 'dayGridMonth',
      headerToolbar: {
        left: 'prev,next today',
        center: 'title',
        right: 'dayGridMonth,timeGridWeek,timeGridDay'
      },
      events: fetchEvents,
      eventClick: onEventClick,
      height: 'auto',
    });
    calendar.render();

    document.getElementById('refreshBtn').addEventListener('click', ()=>calendar.refetchEvents());
    document.getElementById('puntoFilter').addEventListener('change', ()=>calendar.refetchEvents());
    document.getElementById('solicitarBtn').addEventListener('click', onSolicitar);
  }

  async function fetchEvents(info, successCallback, failureCallback){
    try {
      const punto = document.getElementById('puntoFilter').value;
      const url = `/turnos/api/events?punto_id=${encodeURIComponent(punto)}&start=${encodeURIComponent(info.startStr)}&end=${encodeURIComponent(info.endStr)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Error cargando eventos');
      const data = await res.json();
      // convertimos a formato FullCalendar
      const events = data.turnos.map(t => ({
        id: t.id,
        title: t.title || `Turno #${t.id}`,
        start: `${t.fecha}T${t.hora_inicio || '00:00'}`,
        end: `${t.fecha}T${t.hora_fin || '23:59'}`,
        extendedProps: t
      }));
      successCallback(events);
    } catch (err) {
      console.error(err);
      failureCallback(err);
    }
  }

  function onEventClick(info){
    const ev = info.event;
    currentEvent = ev;
    const p = ev.extendedProps;
    document.getElementById('modalTurnoId').innerText = ev.id;
    document.getElementById('modalFecha').innerText = p.fecha;
    document.getElementById('modalHora').innerText = (p.hora_inicio || '') + ' - ' + (p.hora_fin || '');
    document.getElementById('modalPunto').innerText = p.punto_nombre || p.punto_id || '';
    // limpiar mensajes
    const msg = document.getElementById('modalMsg');
    msg.classList.add('d-none'); msg.innerText = '';
    showModal();
  }

  function showModal(){ modal.style.display = 'block'; modal.classList.add('show'); }
  function hideModal(){ modal.style.display = 'none'; modal.classList.remove('show'); }

  async function onSolicitar(){
    if (!currentEvent) return;
    const turnoId = currentEvent.id;
    document.getElementById('solicitarBtn').disabled = true;
    try {
      const res = await fetch('/turnos/api/solicitar', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({turno_id: turnoId})
      });
      const data = await res.json();
      const msg = document.getElementById('modalMsg');
      msg.classList.remove('d-none');
      if (!data.ok){
        msg.classList.remove('alert-success'); msg.classList.add('alert-danger');
        msg.innerText = data.error || 'Error al solicitar el turno';
      } else {
        msg.classList.remove('alert-danger'); msg.classList.add('alert-success');
        msg.innerText = data.message || 'Solicitud creada';
        // actualizar calendario para reflejar cambio
        calendar.refetchEvents();
      }
    } catch(err){
      console.error(err);
      const msg = document.getElementById('modalMsg');
      msg.classList.remove('alert-success'); msg.classList.add('alert-danger');
      msg.classList.remove('d-none'); msg.innerText = 'Error de conexión';
    } finally {
      document.getElementById('solicitarBtn').disabled = false;
    }
  }

  return { init };
})();
