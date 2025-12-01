/**
 *
 *   PPAM tools
 *
 *   Equipo de desarrolladores de la PPAM app
 *
 *   30/11/2025
 *
 **/

// ----------------- DARK MODE -----------------
const toggleDarkBtn = document.getElementById("toggleDark");
if (toggleDarkBtn) {
  toggleDarkBtn.addEventListener('click', ()=> {
    document.body.classList.toggle('dark-mode');
    toggleDarkBtn.querySelector('i').classList.toggle('fa-moon');
    toggleDarkBtn.querySelector('i').classList.toggle('fa-sun');
  });
}

// ----------------- WIDGETS -----------------
async function cargarWidgets(){
  try{
    const res = await fetch('/ppamtools/api/metrics');
    const d = await res.json();
    document.getElementById('w_publicadores').innerText = d.publicadores;
    document.getElementById('w_asignaciones').innerText = d.asignaciones;
    document.getElementById('w_solicitudes').innerText = d.solicitudes;
    document.getElementById('w_cpu').innerText = d.cpu;
    document.getElementById('w_mem').innerText = d.mem;
    document.getElementById('w_uptime').innerText = d.uptime;
  }catch(e){ console.warn(e) }
}
setInterval(cargarWidgets, 15000);
cargarWidgets();

// =====================================================
// GRAFICO (solo 1 Chart en memoria, nunca recreado)
// =====================================================

let graficoChart = null;

async function grafico(){
  try{
    const res = await fetch('/ppamtools/api/activity');
    if (!res.ok) return;

    const datos = await res.json();
    const ctx = document.getElementById('grafico_semanal');
    if (!ctx) return;

    const labels = datos.map(x => x.dia);
    const valores = datos.map(x => x.valor);

    if (!graficoChart) {
      // Crear UNA sola instancia
      graficoChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'Asignaciones',
            data: valores,
            borderWidth: 3,
            tension: 0.3,
            fill: false
          }]
        },
        options: {
          animation: false,
          plugins: { legend: { display:false } }
        }
      });
    } else {
      // Actualizar sin recrear
      graficoChart.data.labels = labels;
      graficoChart.data.datasets[0].data = valores;
      graficoChart.update();
    }

  }catch(e){
    console.warn("Error en gráfico:", e);
  }
}

// actualizar gráfico cada 30 s (suficiente)
grafico();
setInterval(grafico, 30000);


// ----------------- NOTIFICACIONES SOLO POLLING -----------------

function mostrarNotificacion(msg){
  try{
    const cont = document.getElementById('notif-container');
    const div = document.createElement('div');
    div.className = 'notif';

    // Mostrar sólo el texto si existe
    if (msg.texto) {
      div.innerText = msg.texto;
    } else {
      div.innerText = JSON.stringify(msg);
    }

    cont.appendChild(div);

    // que desaparezca a los 7s
    setTimeout(()=> div.remove(), 7000);

  }catch(e){
    console.warn("Error mostrando notificación", e);
  }
}
// ------ Modo NOTIFICACIONES: SOLO POLLING ------
fallbackNoti();
/*
let useSSE = false;
try{
  const sse = new EventSource('/ppamtools/notificaciones_stream');
  sse.onmessage = function(e){
    try{ const d = JSON.parse(e.data); mostrarNotificacion(d); }catch{ mostrarNotificacion(e.data); }
  }
  sse.onerror = function(){ sse.close(); fallbackNoti(); }
  useSSE = true;
}catch(e){ fallbackNoti(); }
   */
async function fallbackNoti(){
	setInterval(async () => {
    try {
      const r = await fetch('/ppamtools/notificaciones_poll');
      const arr = await r.json();

      // mostrar SOLO las últimas 5 para evitar spam
      arr.slice(-5).forEach(a => mostrarNotificacion(a));

    } catch (e) {
      console.warn("Error en notificaciones_poll", e);
    }
  }, 2500); // 2.5 segundos = real-time controlado
 }

// ----------------- MINI CHAT -----------------
const chatBtn = document.getElementById('chat-btn');
const chatBox = document.getElementById('chat-box');
if (chatBtn) chatBtn.addEventListener('click', ()=> chatBox.classList.toggle('d-none'));
const chatClose = document.getElementById('chat-close');
if (chatClose) chatClose.addEventListener('click', ()=> chatBox.classList.add('d-none'));

async function cargarChat(){
  try{
    const r = await fetch('/ppamtools/chat/get');
    const msgs = await r.json();
    const box = document.getElementById('chat-mensajes');
    box.innerHTML = '';
    msgs.slice(-200).forEach(m => {
      const div = document.createElement('div');
      div.innerHTML = `<small><strong>${m.usuario}</strong> <span class="text-muted">${new Date(m.ts).toLocaleString()}</span></small><div>${m.texto}</div><hr/>`;
      box.appendChild(div);
    });
    box.scrollTop = box.scrollHeight;
  }catch(e){ console.warn(e) }
}
setInterval(cargarChat, 3000); cargarChat();

const chatSend = document.getElementById('chat-send');
if (chatSend) chatSend.addEventListener('click', async ()=>{
  const txt = document.getElementById('chat-texto');
  if (!txt.value.trim()) return;
  await fetch('/ppamtools/chat/enviar', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ texto: txt.value }) });
  txt.value = '';
  cargarChat();
});

// enviar mensaje con Enter
const chatInput = document.getElementById('chat-texto');
if (chatInput) chatInput.addEventListener('keydown', async (e)=>{ if (e.key==='Enter'){ e.preventDefault(); chatSend.click(); } });

// ----------------- LOGS -----------------
async function cargarLogs(){
  try{
    const r = await fetch('/ppamtools/logs');
    const txt = await r.text();
    const pre = document.getElementById('logs_sistema');
    if (pre) pre.innerText = txt;
  }catch(e){ console.warn(e) }
}
setInterval(cargarLogs, 5000); cargarLogs();

async function limpiarLogs(){
  await fetch('/ppamtools/logs/limpiar', { method:'POST' });
  cargarLogs();
}

// fin