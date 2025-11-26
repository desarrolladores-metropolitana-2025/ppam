/* 
 * PPAM - (c) Desarrolladores equipo PPAM
 *
 * 26/11/2025
 *
 *  Módulo de reemplazos
 *
 * static/js/app_reemplazos_flask.js
 *
 **/

const AppReemplazos = (function(){

    const apiSemana = "/api/reemplazos/semana";

    // Estado interno
    let state = {
        fechaBase: new Date()  // hoy
    };

    // Formato YYYY-MM-DD
    /* function toISO(d){
        return d.toISOString().split("T")[0];
        }
    */
	function toISO(d){
    return d.getFullYear() + "-" +
           String(d.getMonth()+1).padStart(2,'0') + "-" +
           String(d.getDate()).padStart(2,'0');
			}

	
    function obtenerSemana(){
        const base = state.fechaBase;
		const day = base.getDay() || 7;  // domingo (0) pasa a 7
		const lunes = new Date(base);
        // lunes.setDate(base.getDate() - base.getDay() + 1);		
		lunes.setDate(base.getDate() - day + 1);
		lunes.setHours(0,0,0,0);


        const dias = [];
        for(let i=0; i<7; i++){
            const d = new Date(lunes);
            d.setDate(lunes.getDate()+i);
			d.setHours(0,0,0,0);
            dias.push(d);
        }
        return dias;
    }

    async function cargarSemana(){
        const dias = obtenerSemana();
        const fechaISO = toISO(dias[0]); // lunes

        const cont = document.getElementById("reemplazosCalendar");
        cont.innerHTML = `<div class='p-2 text-center text-muted'>Cargando...</div>`;

        try {
            const url = `${apiSemana}?fecha=${encodeURIComponent(fechaISO)}`;
            const res = await fetch(url);
            if(!res.ok) throw new Error("Error al cargar");
            const data = await res.json();

            // Agrupar por fecha
            const mapa = {};
            dias.forEach(d => mapa[toISO(d)] = []);
            data.forEach(t => mapa[t.fecha].push(t));

            // Dibujar
            cont.innerHTML = "";

            dias.forEach(d => {
                const iso = toISO(d);
                const celda = document.createElement("div");
                celda.className = "reemp-dia";

                celda.innerHTML = `
                    <div class="fw-bold">${d.toLocaleDateString("es-AR",{weekday:'short', day:'numeric'})}</div>
                `;

                const lista = mapa[iso];
                if(lista.length === 0){
                    celda.innerHTML += `<div class="text-muted small">Sin reemplazos</div>`;
                } else {
                    lista.forEach(t => {
                        const div = document.createElement("div");
                        div.className = "reemp-item";
                        div.innerHTML = `
                            <strong>${t.hora_inicio} - ${t.hora_fin}</strong><br>
                            <small>${t.punto}</small><br>
                            <span class="badge bg-warning text-dark">${t.vacantes} vacantes</span>
                        `;

                        div.addEventListener("click", () => tomarReemplazo(t.id));
                        celda.appendChild(div);
                    });
                }

                cont.appendChild(celda);
            });

        } catch (e){
            cont.innerHTML = `<div class='text-danger'>Error: ${e}</div>`;
        }
    }

    async function tomarReemplazo(turnoId){
        if(!confirm("¿Deseás tomar este reemplazo?")) return;

        try{
            const url = `/tomar_reemplazo/${turnoId}`;
            const res = await fetch(url, {method:"POST"});
            if(!res.ok) throw new Error("Error");

            alert("Solicitud enviada correctamente");
            cargarSemana();
        } catch(err){
            alert("No se pudo enviar: " + err.message);
        }
    }

    function init(){
        document.getElementById("semPrev").addEventListener("click", ()=>{
            state.fechaBase.setDate(state.fechaBase.getDate() - 7);
            cargarSemana();
        });
        document.getElementById("semNext").addEventListener("click", ()=>{
            state.fechaBase.setDate(state.fechaBase.getDate() + 7);
            cargarSemana();
        });

        cargarSemana();
    }

    return { init };

})();
