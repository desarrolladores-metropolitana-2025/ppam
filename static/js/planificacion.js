/* 
 *  PPAM
 *  planificacion.js
 *  25/11/2025
 *
 */
 
/* ----------------------
  Helper fetch (JSON + errores)
   ---------------------- */
async function fetchJSON(url, opts = {}) {
    opts.credentials = opts.credentials || 'same-origin';
    if (opts.body && typeof opts.body === 'object' && !(opts.body instanceof FormData)) {
        opts.headers = Object.assign({}, opts.headers || {}, {"Content-Type": "application/json"});
        opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(url, opts);
    const txt = await res.text();
    let data;
    try { data = txt ? JSON.parse(txt) : null; } catch(e){ data = txt; }
    if (!res.ok) {
        const msg = (data && data.error) ? data.error : res.statusText || 'Error';
        throw new Error(msg);
    }
    return data;
}

/* ----------------------
  showTab original y wrapper seguro + inicialización
   ---------------------- */
const cards = document.querySelectorAll('.punto-card');
const tabs  = document.querySelectorAll('.tab');

function showTab(index){
    cards.forEach((c,i)=>c.style.display = i===index ? 'block' : 'none');
    tabs.forEach((t,i)=>t.classList.toggle('active', i===index));
}

/* Wrapper seguro: mantiene original si estaba y añade hook onTabChanged */
(function(){
    const original = window.showTab ?? null;
    window.showTab = function(index){
        if (original) original(index);
        const cards = document.querySelectorAll('.punto-card');
        const card = cards[index];
        if (window.onTabChanged) window.onTabChanged(index, card);
    };

    document.addEventListener("DOMContentLoaded", () => {
        // asegurar que la primera card esté visible
        if (cards.length === 0) return;
        const anyVisible = [...cards].some(c => c.style.display === "block");
        if (!anyVisible) {
            cards.forEach(c => c.style.display = "none");
            cards[0].style.display = "block";
            if (tabs[0]) tabs[0].classList.add('active');
        }
        // disparar onTabChanged para la primera
        if (window.onTabChanged) window.onTabChanged(0, cards[0]);
    });
})();

/* ----------------------
  Funciones AJAX: stats + publish + changes poll
   ---------------------- */

async function fetchStatsForCard(cardEl) {
    if (!cardEl) return null;
    const puntoId = cardEl.dataset.punto;
    const weekStart = document.querySelector('input[name="week_start"]').value;
    const url = `/api/planificacion/stats?punto_id=${encodeURIComponent(puntoId)}&week_start=${encodeURIComponent(weekStart)}`;
    try {
        const resp = await fetchJSON(url);
        if (resp && resp.ok) {
            // actualizar UI dentro de la card
            const pub = cardEl.querySelector('.stat-publicos em');
            const bor = cardEl.querySelector('.stat-borradores em');
            const dias = cardEl.querySelector('.stat-dias em');
            if (pub) pub.textContent = resp.publicos;
            if (bor) bor.textContent = resp.borradores;
            if (dias) dias.textContent = resp.dias_completos;
            return resp.version || "";
        }
    } catch (e) {
        console.warn("fetchStatsForCard error:", e);
    }
    return "";
}

async function publishTurnosBulk(turnoIds = [], action = "publicar", cardEl = null) {
    if (!Array.isArray(turnoIds) || turnoIds.length === 0) return;
    try {
        const body = { turno_ids: turnoIds, action: action };
        const resp = await fetchJSON("/api/planificacion/publish", { method: "POST", body: body });
        if (resp && resp.ok) {
            // actualizar visual: reemplazar filas afectadas (fácil: recargar card parcial)
            if (cardEl) {
                await reloadCardPartial(cardEl);
            } else {
                location.reload(); // fallback
            }
        } else {
            alert("Error: " + (resp.error || "No se pudo actualizar"));
        }
    } catch (e) {
        alert("Error publicando turnos: " + e.message);
    }
}

/* ----------------------
  Partial card reload (fetch /planificacion?week_start=... y extraer card)
   ---------------------- */
async function reloadCardPartial(cardEl) {
    try {
        const puntoId = cardEl.dataset.punto;
        const weekStart = document.querySelector('input[name="week_start"]').value;
        const url = `/planificacion?week_start=${encodeURIComponent(weekStart)}`; // servidor devuelve toda la página
        const txt = await (await fetch(url, { credentials: 'same-origin' })).text();
        // parsear y extraer la card correspondiente
        const parser = new DOMParser();
        const doc = parser.parseFromString(txt, 'text/html');
        const newCard = doc.querySelector(`.punto-card[data-punto="${puntoId}"]`);
        if (newCard) {
            cardEl.innerHTML = newCard.innerHTML;
            // re-run local initializers on the replaced content:
            rebindCardEventListeners(cardEl);
            // refresh stats too
            await fetchStatsForCard(cardEl);
        } else {
            // como fallback recargamos la página entera
            location.reload();
        }
    } catch (e) {
        console.warn("reloadCardPartial error:", e);
        // fallback: recargar
        // location.reload();
    }
}

/* ----------------------
  Re-bind event listeners en una card recién reemplazada
   ---------------------- */
function rebindCardEventListeners(card) {
    // reasignar check-dia, check-semana y turno-checkbox listeners dentro de card
    card.querySelectorAll('.check-dia').forEach(cb=>{
        cb.addEventListener('change', function(){
            const puntoId = this.dataset.punto;
            const dia = this.dataset.dia;
            const c = document.querySelector(`.punto-card[data-punto='${puntoId}']`);
            const checks = c.querySelectorAll(`.turno-checkbox[data-dia='${dia}']`);
            checks.forEach(ch => ch.checked = this.checked);
            syncPuntoMasterState(puntoId);
        });
    });
    card.querySelectorAll('.check-semana').forEach(cb=>{
        cb.addEventListener('change', function(){
            const puntoId = this.dataset.punto;
            const c = document.querySelector(`.punto-card[data-punto='${puntoId}']`);
            const all = c.querySelectorAll('.turno-checkbox');
            all.forEach(ch => ch.checked = this.checked);
            c.querySelectorAll('.check-dia').forEach(d => d.checked = this.checked);
        });
    });
    card.querySelectorAll('.turno-checkbox').forEach(cb=>{
        cb.addEventListener('change', function(){
            const puntoId = this.dataset.punto;
            const dia = this.dataset.dia;
            const c = document.querySelector(`.punto-card[data-punto='${puntoId}']`);
            const checks = c.querySelectorAll(`.turno-checkbox[data-dia='${dia}']`);
            const master = c.querySelector(`.check-dia[data-dia='${dia}']`);
            if (master) master.checked = Array.from(checks).every(c=>c.checked);
            syncPuntoMasterState(puntoId);
        });
    });
}

/* ----------------------
  Polling para detectar cambios colaborativos
   ---------------------- */
const POLL_INTERVAL_MS = 25000; // 25s
const versionsByPunto = {}; // cache de versión por punto

async function pollChangesLoop() {
    const weekStart = document.querySelector('input[name="week_start"]').value;
    document.querySelectorAll('.punto-card').forEach(async (card) => {
        const puntoId = card.dataset.punto;
        const known = versionsByPunto[puntoId] || "";
        const url = `/api/planificacion/changes?punto_id=${encodeURIComponent(puntoId)}&week_start=${encodeURIComponent(weekStart)}&version=${encodeURIComponent(known)}`;
        try {
            const resp = await fetchJSON(url);
            if (resp && resp.ok) {
                if (resp.changed) {
                    // actualizar versión y recargar parcial
                    versionsByPunto[puntoId] = resp.version;
                    // si la card está visible recargar parcial, si no, marcar con badge (simple)
                    if (card.style.display === 'block') {
                        await reloadCardPartial(card);
                    } else {
                        // marcamos tab con un pequeño punto (notification)
                        const tabIndex = Array.from(document.querySelectorAll('.punto-card')).indexOf(card);
                        const tabEl = document.querySelectorAll('.tab')[tabIndex];
                        if (tabEl && !tabEl.querySelector('.badge')) {
                            const span = document.createElement('span');
                            span.className = 'badge';
                            span.textContent = ' •';
                            span.style.color = '#c0392b';
                            tabEl.appendChild(span);
                        }
                    }
                } else {
                    // guardar version si aun no la tenía
                    if (!versionsByPunto[puntoId] && resp.version) versionsByPunto[puntoId] = resp.version;
                }
            }
        } catch (e) {
            console.debug("pollChangesLoop error:", e);
        }
    });

    setTimeout(pollChangesLoop, POLL_INTERVAL_MS);
}

/* ----------------------
  onTabChanged: cuando cambia de punto
   ---------------------- */
window.onTabChanged = async function(index, cardEl){
    if (!cardEl) return;
    // limpiar badge si existía
    const tabEl = document.querySelectorAll('.tab')[index];
    if (tabEl) {
        const b = tabEl.querySelector('.badge');
        if (b) b.remove();
    }

    // traer stats y version
    const version = await fetchStatsForCard(cardEl);
    if (version) {
        versionsByPunto[cardEl.dataset.punto] = version;
    }

    // opcional: iniciar polling si no activo
    if (!window._planificacion_polling_started) {
        window._planificacion_polling_started = true;
        setTimeout(pollChangesLoop, POLL_INTERVAL_MS);
    }

    // también podés ejecutar otras inicializaciones de esta card aquí
};

/* ----------------------
  Publicar / Privar via AJAX (ejemplo de uso)
   ---------------------- */
/* Ejemplo: agregar botones que llamen a esta función:
   publishSelectedInCard(cardEl, 'publicar') o ('privado') */

function collectSelectedTurnosFromCard(cardEl) {
    const checked = Array.from(cardEl.querySelectorAll('input.turno-checkbox:checked'));
    return checked.map(ch => parseInt(ch.value));
}

async function publishSelectedInCard(cardEl, action) {
    const turnos = collectSelectedTurnosFromCard(cardEl);
    if (turnos.length === 0) { alert("No se seleccionaron turnos."); return; }
    if (!confirm(`Confirmás ${action === 'publicar' ? 'publicar' : 'poner en borrador'} ${turnos.length} turno(s)?`)) return;
    await publishTurnosBulk(turnos, action, cardEl);
}

/* ----------------------
  Inicial: rebind a elementos estáticos existentes (por si no se recargó)
   ---------------------- */
document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.punto-card').forEach(card => rebindCardEventListeners(card));
});

