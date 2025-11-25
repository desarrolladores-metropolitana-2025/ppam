/*                     
 *
 *   postulantes_disponibles.js
 *
 *   PPAM
 *
 *   25/11/2025
 */
async function fetchDisponibles(fecha, hi, hf, puntoId) {
    const params = new URLSearchParams({
        accion: "disponibles",
        fecha: fecha,
        hora_inicio: hi,
        hora_fin: hf,
        punto_id: puntoId
    });
    const url = `/api/postulantes?${params.toString()}`;
    try {
        const res = await fetch(url);
        if (!res.ok) {
            console.warn("fetchDisponibles: error", await res.text());
            return [];
        }
        const data = await res.json();
        return Array.isArray(data) ? data : [];
    } catch (e) {
        console.error("fetchDisponibles exception", e);
        return [];
    }
}

function buildOption(pub) {
    const opt = document.createElement('option');
    opt.value = pub.id;
    opt.textContent = `${pub.nombre || ''} ${pub.apellido || ''}`.trim();
    return opt;
}

async function rellenarSelect(select) {
    const fecha = select.dataset.fecha;
    const hi = select.dataset.horaInicio || select.dataset.hora_inicio || select.getAttribute('data-hora-inicio');
    const hf = select.dataset.horaFin || select.dataset.hora_fin || select.getAttribute('data-hora-fin');
    const punto = select.dataset.punto || select.getAttribute('data-punto');

    // conservar selección actual si existe
    const currentVal = select.value || null;

    // mostrar spinner/temporal
    select.innerHTML = '<option value="">Cargando...</option>';
    select.disabled = true;

    const disponibles = await fetchDisponibles(fecha, hi, hf, punto);

    // reconstruir opciones
    select.innerHTML = '<option value="">-</option>';
    disponibles.forEach(pub => {
        const opt = buildOption(pub);
        select.appendChild(opt);
    });

    // si tenía un valor asignado que ya no está en la lista, reinsertarlo al inicio
    if (currentVal) {
        const exists = Array.from(select.options).some(o => o.value == currentVal);
        if (!exists) {
            // intentar obtener nombre por petición simple (opcional) o mostrar ID
            const placeholder = document.createElement('option');
            placeholder.value = currentVal;
            placeholder.textContent = `Asignado: #${currentVal}`;
            placeholder.selected = true;
            // insertar en segunda posición (después del '-')
            select.insertBefore(placeholder, select.children[1]);
        } else {
            select.value = currentVal;
        }
    }

    select.disabled = false;
}

async function inicializarDisponibilidades() {
    const selects = document.querySelectorAll('select.available-select');
    const promises = [];
    selects.forEach(sel => promises.push(rellenarSelect(sel)));
    await Promise.all(promises);
}

// Llamar al cargar la página
document.addEventListener('DOMContentLoaded', function() {
    // inicializar disponibilidad
    inicializarDisponibilidades();

    // opcional: si ponemos un botón "Recargar disponibilidad", asociar evento para refrescar
    const recargarBtn = document.getElementById('recargarDisponibilidadBtn');
    if (recargarBtn) recargarBtn.addEventListener('click', inicializarDisponibilidades);
});

