/****
 *
 *  apiapp.js
 *
 *
 *
 ****/
// Consoles
el("btn-list-consoles").onclick = async ()=>{
  const r = await call("/api/consoles");
  if(!r.ok){
    el("consoles-list").innerHTML = `<div>Error: ${r.text || r.json?.error}</div>`;
    return;
  }

  const consoles = r.json.data || [];

  if(!consoles.length){
    el("consoles-list").innerHTML = `<div class="muted small">No consoles running</div>`;
    return;
  }

  el("consoles-list").innerHTML = consoles.map(c => `
    <div style="padding:6px;border-bottom:1px solid #f0f4f8">
      <b>ID: ${c.id}</b>
      <div class="muted small">Type: ${c.console_type}</div>
      <div class="muted small">Created: ${c.created}</div>
      <button class="btn light" style="margin-top:6px"
        onclick="closeConsole('${c.id}')">Close</button>
    </div>
  `).join("");
};

function closeConsole(id){
  fetch("/apiapp/api/consoles/" + id + "/close", {method:"POST"})
    .then(r => r.json())
    .then(j => alert(JSON.stringify(j)))
    .then(()=> el("btn-list-consoles").click());
}
// Tareas...
el("btn-list-tasks").onclick = async ()=>{
  const r = await call("/api/tasks");
  if(!r.ok){
    el("tasks-list").innerHTML = `<div>Error: ${r.text || r.json?.error}</div>`;
    return;
  }

  const tasks = r.json.data || [];

  if(!tasks.length){
    el("tasks-list").innerHTML = `<div class="muted small">No scheduled tasks</div>`;
    return;
  }

  el("tasks-list").innerHTML = tasks.map(t => `
    <div style="padding:6px;border-bottom:1px solid #f0f4f8">
      <b>${t.id}</b>
      <div class="muted small">Cmd: ${t.command}</div>
      <div class="muted small">Schedule: ${t.schedule}</div>
      <div class="muted small">Enabled: ${t.enabled}</div>

      <button class="btn" style="margin-top:6px"
        onclick="runTask('${t.id}')">Run</button>

      <button class="btn light" style="margin-top:6px"
        onclick="deleteTask('${t.id}')">Delete</button>
    </div>
  `).join("");
};

function runTask(id){
  fetch("/apiapp/api/tasks/" + id + "/run", {method:"POST"})
    .then(r=>r.json()).then(j=>alert(JSON.stringify(j)));
}

function deleteTask(id){
  if(!confirm("Delete task?")) return;
  fetch("/apiapp/api/tasks/" + id + "/delete", {method:"POST"})
    .then(r=>r.json())
    .then(j=>alert(JSON.stringify(j)))
    .then(()=> el("btn-list-tasks").click());
}
// --- Workers

el("btn-list-workers").onclick = async ()=>{
  const r = await call("/api/workers");
  if(!r.ok){
    el("workers-list").innerHTML = `<div>Error: ${r.text || r.json?.error}</div>`;
    return;
  }

  const workers = r.json.data || [];

  if(!workers.length){
    el("workers-list").innerHTML = `<div class="muted small">No workers</div>`;
    return;
  }

  el("workers-list").innerHTML = workers.map(w => `
    <div style="padding:6px;border-bottom:1px solid #f0f4f8">
      <b>${w.name}</b>
      <div class="muted small">Running: ${w.running}</div>
      <div class="muted small">Last restart: ${w.last_restart_time}</div>

      <button class="btn light" style="margin-top:6px"
        onclick="deleteWorker('${w.name}')">Delete</button>
    </div>
  `).join("");
};

function deleteWorker(name){
  if(!confirm("Delete worker " + name + "?")) return;
  fetch("/apiapp/api/workers/" + name + "/delete", {method:"POST"})
    .then(r=>r.json())
    .then(j=>alert(JSON.stringify(j)))
    .then(()=> el("btn-list-workers").click());
}
