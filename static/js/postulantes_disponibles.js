/*
 * PPAM - Disponibilidad BULK (Optimizada)
 * reemplaza a postulantes_disponibles.js
 * 25/11/2025
 */
const cachePublicadores = {};
async function getPublicadorNombre(id) {
    if (!id) return null;

    // si ya lo tengo => retorno
    if (cachePublicadores[id]) return cachePublicadores[id];

    try {
        const res = await fetch(`/api/publicador?id=${id}`);
        if (!res.ok) return null;

        const data = await res.json();
        const nombre = `${data.nombre} ${data.apellido}`.trim();

        cachePublicadores[id] = nombre;
        return nombre;

    } catch (e) {
        console.error("Error buscando nombre del publicador", id, e);
        return null;
    }
}

async function cargarDisponiblesBulkForCard(cardEl) {
    const selects = cardEl.querySelectorAll("select.available-select");
    if (selects.length === 0) return;

    // → evitar duplicados: capitán + 4 publicadores del mismo turno
    const mapaTurnos = {};
    selects.forEach(s => {
        const tid = s.dataset.turnoId;
        if (!mapaTurnos[tid]) {
		mapaTurnos[tid] = {
        id: parseInt(tid),
        fecha: s.dataset.fecha,
        hora_inicio: s.dataset.horaInicio,
        hora_fin: s.dataset.horaFin
    };
		}

    });

    const turnos = Object.values(mapaTurnos);
    const puntoId = selects[0].dataset.punto;

    let data = {};
    try {
        const res = await fetch("/api/postulantes?accion=disponibles_bulk", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                punto_id: puntoId,
                turnos: turnos
            })
        });
        data = await res.json();
    } catch (e) {
        console.error("Error BULK", e);
        return;
    }

   // poblar selects
selects.forEach(sel => {
	    const turnoId = sel.dataset.turnoId;
    const disponibles = data[turnoId] || [];

console.log(
    "SELECT:",
    "turno", sel.dataset.turnoId,
    "name", sel.name,
    "data-actual =", sel.dataset.actual,
    "valor inicial =", sel.value
);

    // normalizamos a string para evitar mismatch 8 vs "8"
    const actual = (sel.dataset.actual || sel.value || "").toString();
	// console.log("TURN:", sel.dataset.turnoId, 
    //       "actual=", actual, 
    //        "options loaded=", disponibles.length);

    sel.innerHTML = '<option value="">-</option>';

    // agregar disponibles "válidos"
    disponibles.forEach(pub => {
        const opt = document.createElement("option");
        opt.value = pub.id.toString();
        opt.textContent = `${pub.nombre} ${pub.apellido}`;
        opt.style.color = "#000"; // normal
        sel.appendChild(opt);
    });

    // si el asignado previo NO está en la lista disponible → agregar aviso
   if (actual) {
    // ¿existe ya entre los disponibles?
    const exists = sel.querySelector(`option[value="${actual}"]`);

    if (!exists) {
        // buscar nombre real
        getPublicadorNombre(actual).then(nombreReal => {

            const texto = nombreReal
                ? `⚠️ Asignado previamente: ${nombreReal} — no disponible`
                : `⚠️ Asignado previamente: #${actual} — no disponible`;

            const opt = document.createElement("option");
            opt.value = actual;
            opt.textContent = texto;

            // insertar en segunda posición
            sel.insertBefore(opt, sel.children[1]);

            sel.value = actual;
        });

    } else {
        sel.value = actual; // estaba disponible
    }
}

});

}

/*
 * Al cargar, inicializamos SOLO la card visible
 */
document.addEventListener("DOMContentLoaded", () => {
    const card = document.querySelector(".punto-card[style*='block']");
    if (card) cargarDisponiblesBulkForCard(card);
});

/*
 * Integración automática con showTab(index)
 * (si ya existe showTab, esto no interfiere)
 */
document.addEventListener("DOMContentLoaded", () => {

    // ahora sí, showTab ORIGINAL ya existe
    const originalShowTab = window.showTab;

    // si POR ALGUNA RAZÓN aún no existe (muy raro), lo esperamos
    if (typeof originalShowTab !== "function") {
        console.warn("⚠ showTab no estaba aún. Reintentando...");
        setTimeout(() => window.showTab(0), 50);
    }

    window.showTab = function(index){
        // 1) ejecutar la original
        if (typeof originalShowTab === "function") {
            originalShowTab(index);
        }

        // 2) ejecutar la carga de disponibles
        const cards = document.querySelectorAll(".punto-card");
        const card = cards[index];
        if (card) cargarDisponiblesBulkForCard(card);
    };

    // --- Inicialización automática ---
    const cards = document.querySelectorAll(".punto-card");
    if (cards.length > 0) {
        const visible = [...cards].some(c => c.style.display === "block");
        if (!visible) {
            cards.forEach(c => c.style.display = "none");
            cards[0].style.display = "block";
        }
        cargarDisponiblesBulkForCard(cards[0]);
    }
});

