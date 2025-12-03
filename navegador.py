# navegador.py
#
# Equipo de desarrollo PPAM
# 28/11/2025
#
import os
import io
import zipfile
import shutil
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
from flask import (
    Blueprint, current_app, request, jsonify,
    render_template_string, send_file, abort, url_for
)
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user
from functools import wraps
# --- Config ---
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200MB por archivo aprox (ajustable)

navegador_bp = Blueprint("navegador_full", __name__, url_prefix="/navegador")
# ----- usar API Pythonanywhere ------------------------------------------------
PA_USERNAME = "ppamappcaba"
API_TOKEN = os.getenv("PA_API_TOKEN")  # Mejor guardarlo en variable de entorno
WEBAPP_DOMAIN = "ppamappcaba.pythonanywhere.com"
# -------- login admin ----------------------------------------------------------
def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login", next=request.url))

        if getattr(current_user, "rol", None) != "Admin":
            abort(403, description="No tenés permisos para acceder a esta sección.")

        return func(*args, **kwargs)
    return wrapper
# -- Proteger todas las páginas ------------------------------------------------    
@navegador_bp.before_request
@login_required
@admin_required
def protect_navegador_routes():
    pass
# -------- Fin Login ------------------------------------------------------------
@navegador_bp.route("/reload_webapp", methods=["POST"])
def reload_webapp():
    url = f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}/webapps/{WEBAPP_DOMAIN}/reload/"
    headers = {
        "Authorization": f"Token {API_TOKEN}"
    }
    r = requests.post(url, headers=headers)
    
    if r.status_code == 200:
        return jsonify({"status": "ok", "message": "Webapp reloaded"})
    else:
        return jsonify({"status": "error", "message": r.text}), 400

# --- Helpers ---
def get_root():
    root = current_app.config.get("FILEBROWSER_ROOT", os.getcwd())
    return os.path.abspath(root)

def abs_safe(relpath):
    # normaliza y asegura que quede dentro de root
    root = get_root()
    # permitir '' o '.' como root
    rel = (relpath or "").strip("/")
    joined = os.path.normpath(os.path.join(root, rel))
    if not joined.startswith(root):
        abort(403, "Acceso fuera del directorio permitido")
    return joined

def rel_from_abs(abs_path):
    root = get_root()
    return os.path.relpath(abs_path, root).replace("\\", "/")

def list_dir(relpath):
    abs_path = abs_safe(relpath)
    entries = []
    try:
        names = sorted(os.listdir(abs_path), key=lambda s: s.lower())
    except FileNotFoundError:
        return []
    for name in names:
        p = os.path.join(abs_path, name)
        try:
            stat = os.stat(p)
            entries.append({
                "name": name,
                "is_dir": os.path.isdir(p),
                "size": stat.st_size if os.path.isfile(p) else None,
                "mtime": int(stat.st_mtime),
                "relpath": rel_from_abs(p)
            })
        except Exception:
            # skip files we can't stat
            continue
    return entries

def human_size(n):
    if n is None: return ""
    n = float(n)
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"

def is_text_file(path):
    # simple heuristic by extension
    text_exts = {'.txt','.py','.md','.html','.htm','.css','.js','.json','.csv','.ini','.cfg','.log','.sql','.yml','.yaml'}
    return Path(path).suffix.lower() in text_exts

# --- Templates (inline para un solo archivo) ---
TEMPLATE = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>File Browser · /{{ cwd or "" }}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg: #f6f8fb; --card:#fff; --accent:#0b74da; --muted:#666; --danger:#cc3333;
  --text:#222; --panel:#f3f5f9;
}
body{font-family:Inter,Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text);margin:0}
.app{max-width:1200px;margin:18px auto;padding:12px}
.header{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:12px}
.brand{display:flex;align-items:center;gap:12px}
.brand h1{font-size:18px;margin:0}
.controls{display:flex;gap:8px;flex-wrap:wrap}
.btn{background:var(--accent);color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;border:none;cursor:pointer}
.btn.alt{background:#6b7280}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--panel)}
.toolbar{display:flex;gap:8px;align-items:center}
.card{background:var(--card);padding:12px;border-radius:10px;box-shadow:0 1px 4px rgba(10,10,10,0.04)}
.breadcrumbs{font-size:14px;color:var(--muted)}
.search{padding:8px;border-radius:8px;border:1px solid #e5e7eb}
.main{display:flex;gap:12px}
.sidebar{width:250px}
.content{flex:1}
.view-toggle{display:flex;gap:6px;align-items:center}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-top:12px}
.tile{background:var(--card);padding:10px;border-radius:8px;min-height:80px;display:flex;flex-direction:column;gap:6px;justify-content:space-between;border:1px solid #eee}
.tile .name{font-weight:600;word-break:break-word}
.tile .meta{font-size:12px;color:var(--muted)}
.list table{width:100%;border-collapse:collapse;margin-top:12px}
.list th{background:var(--accent);color:#fff;padding:8px;text-align:left;border-radius:4px 4px 0 0}
.list td{padding:8px;border-bottom:1px solid #f0f0f0}
.actions{display:flex;gap:6px;align-items:center}
.small{font-size:12px;color:var(--muted)}
.footer{margin-top:14px;text-align:center;color:var(--muted)}
.dropzone{border:2px dashed #dfe6f3;padding:10px;border-radius:8px;text-align:center;color:var(--muted);margin-top:8px}
.inline{display:inline-block}
input[type="text"], textarea{padding:8px;border-radius:6px;border:1px solid #e2e8f0}
.rename-input{padding:6px;border-radius:6px;border:1px solid #ddd}
.topbar-right{display:flex;gap:8px;align-items:center}
.kv{font-size:12px;color:var(--muted)}
/* dark mode support simple */
body.dark{
  --bg:#0b1014;--card:#0b1220;--accent:#2563eb;--muted:#9aa3b2;--text:#e6eef9;--panel:#071021
}
body.dark-mode a {
    color: #fff !important;
}

body.dark-mode a:hover {
    color: #ddd !important;
}
body.dark-mode .btn {
    color: #fff !important;
    border-color: #fff !important;
}
/* Fuerza color blanco en TODOS los links del modo dark */
body.dark-mode a,
body.dark-mode a:link,
body.dark-mode a:visited,
body.dark-mode a:active {
    color: #ffffff !important;
}

/* Hover */
body.dark-mode a:hover {
    color: #dddddd !important;
}
body.dark-mode table a {
    color: #ffffff !important;
}
body.dark-mode .btn a,
body.dark-mode a.btn {
    color: #ffffff !important;
}
@media (max-width:800px){
  .main{flex-direction:column}
  .sidebar{width:100%}
}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="brand">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" aria-hidden><rect width="24" height="24" rx="6" fill="#0b74da"/></svg>
      <h1>File Browser</h1>
      <div class="kv">Root: <span class="small">{{ root_display }}</span></div>
    </div>
    <div class="topbar-right">
      <input id="search" class="search" placeholder="Buscar por nombre..." />
      <div class="view-toggle">
        <button class="btn alt" id="toggle-view">Grid</button>
        <button class="btn ghost" id="toggle-theme">Dark</button>
      </div>
      <button class="btn" id="refresh">Refrescar</button>
      <a href="https://www.pythonanywhere.com/user/ppamappcaba/webapps/#tab_id_ppamappcaba_pythonanywhere_com"
   target="_blank"
   class="btn btn-success"
   style="font-size:14px; padding:6px 12px; display:inline-flex; align-items:center; gap:6px;">
    <i class="bi bi-arrow-repeat"></i>
    Reload WebApp
</a><a href="/ppamtools" class="btn" style="text-decoration:none; display:flex; align-items:center;">
    Panel
  </a>
<a href="/logout" class="btn" style="text-decoration:none; display:flex; align-items:center;">
    Salir
  </a>
    </div>
  </div>

  <div class="card">
    <div class="breadcrumbs" id="breadcrumbs"></div>

    <div style="display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap">
      <label class="inline">
        <input id="upload-input" type="file" multiple style="display:none">
        <button class="btn">Subir archivos</button>
      </label>
      <button class="btn alt" id="btn-new-folder">Nueva carpeta</button>
      <button class="btn alt" id="btn-new-file">Nuevo archivo</button>
      <button class="btn" id="btn-zip">Comprimir seleccionados</button>
      <div class="kv" style="margin-left:8px">Seleccionados: <span id="selected-count">0</span></div>
    </div>

    <div class="dropzone" id="dropzone">Arrastrá archivos aquí para subir</div>

    <div class="main">
      <div class="sidebar card">
        <div style="font-weight:600;margin-bottom:8px">Acciones Rápidas</div>
        <div><button class="btn" id="go-root">Ir al root</button></div>
        <div style="margin-top:8px"><button class="btn alt" id="show-hidden">Mostrar ocultos</button></div>
        <div style="margin-top:8px"><button class="btn ghost" id="clear-selected">Limpiar selección</button></div>
        <div style="margin-top:12px" class="small">Atajos: Enter abrir · Del borrar · F2 renombrar</div>
      </div>

      <div class="content">
        <div id="listing" class="list">
          <!-- listado dinámico -->
        </div>

        <div id="grid" class="grid" style="display:none"></div>
      </div>
    </div>
  </div>

  <div class="footer">Equipo de desarrollo PPAM 2025 · ©</div>
</div>

<!-- Editor modal simple -->
<div id="editor-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);align-items:center;justify-content:center">
  <div style="background:var(--card);padding:12px;border-radius:8px;width:90%;max-width:900px;max-height:90%;overflow:auto">
    <h3 id="editor-title"></h3>
    <textarea id="editor-area" style="width:100%;height:60vh"></textarea>
    <div style="margin-top:8px">
      <button class="btn" id="save-edit">Guardar</button>
      <button class="btn alt" id="cancel-edit">Cancelar</button>
    </div>
  </div>
</div>

<script>
const root = "{{ cwd or '' }}";
const root_display = "{{ root_display }}";
let current = root;
let viewMode = 'list';
let showHidden = false;
let selected = new Set();

function qs(s){return document.querySelector(s)}
function qsa(s){return Array.from(document.querySelectorAll(s))}

async function api(path, opts){
  const res = await fetch(path, opts);
  if(!res.ok){
    const t = await res.text();
    alert("Error: " + t);
    throw new Error(t);
  }
  return res.json();
}

function humanSize(n){
  if(!n) return '';
  let i=0; const units=['B','KB','MB','GB','TB'];
  while(n>=1024 && i<units.length-1){ n/=1024; i++; }
  return n.toFixed(1)+units[i];
}

function mkBreadcrumbs(rel){
  const parts = rel ? rel.split('/').filter(Boolean) : [];
  let acc = '';
  const el = qs('#breadcrumbs'); el.innerHTML='';
  const rootA = document.createElement('a'); rootA.href='#'; rootA.textContent='/'; rootA.onclick=(e)=>{ e.preventDefault(); load(''); }; el.appendChild(rootA);
  parts.forEach((p, idx)=>{
    acc = parts.slice(0, idx+1).join('/');
    const sep = document.createTextNode(' / ');
    el.appendChild(sep);
    const a = document.createElement('a');
    a.href='#'; a.textContent=p;
    a.onclick=(e)=>{ e.preventDefault(); load(acc); };
    el.appendChild(a);
  });
}

function renderList(items){
  const container = qs('#listing');
  container.innerHTML = '';
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  thead.innerHTML = '<tr><th> </th><th>Nombre</th><th>Tamaño</th><th>Modificado</th><th>Acciones</th></tr>';
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  items.forEach(it=>{
    if(!showHidden && it.name.startsWith('.')) return;
    const tr = document.createElement('tr');
    const chkTd = document.createElement('td');
    const chk = document.createElement('input'); chk.type='checkbox';
    chk.onchange = ()=>{ if(chk.checked) selected.add(it.relpath); else selected.delete(it.relpath); qs('#selected-count').textContent=selected.size; };
    chkTd.appendChild(chk);
    tr.appendChild(chkTd);

    const nameTd = document.createElement('td');
    nameTd.style.padding='8px';
    const a = document.createElement('a'); a.href='#';
    a.textContent = it.is_dir ? (it.name + '/') : it.name;
    a.onclick = (e)=>{ e.preventDefault(); if(it.is_dir) load(it.relpath); else viewFile(it.relpath); }
    nameTd.appendChild(a);
    tr.appendChild(nameTd);

    const sizeTd = document.createElement('td'); sizeTd.textContent = it.size ? humanSize(it.size) : '';
    tr.appendChild(sizeTd);

    const mTd = document.createElement('td'); mTd.textContent = it.mtime ? new Date(it.mtime*1000).toLocaleString() : '';
    tr.appendChild(mTd);

    const actTd = document.createElement('td'); actTd.className='actions';

    if(!it.is_dir){
      const dl = document.createElement('a'); dl.href='#'; dl.className='btn'; dl.textContent='Descargar';
      dl.onclick = (e)=>{ e.preventDefault(); window.location = '/navegador/download?path=' + encodeURIComponent(it.relpath); }
      actTd.appendChild(dl);

      const edit = document.createElement('button'); edit.className='btn alt'; edit.textContent='Editar';
      edit.onclick = ()=>{ editFile(it.relpath); };
      actTd.appendChild(edit);
    } else {
      const open = document.createElement('button'); open.className='btn'; open.textContent='Abrir';
      open.onclick = ()=>{ load(it.relpath); };
      actTd.appendChild(open);
    }

    const rename = document.createElement('button'); rename.className='btn ghost'; rename.textContent='Renombrar';
    rename.onclick = ()=>{ inlineRename(it.relpath, it.name); };
    actTd.appendChild(rename);

    const del = document.createElement('button'); del.className='btn danger'; del.textContent='Borrar';
    del.onclick = ()=>{ if(confirm('Borrar ' + it.name + '?')) deleteItem(it.relpath); };
    actTd.appendChild(del);

    tr.appendChild(actTd);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderGrid(items){
  const cont = qs('#grid'); cont.innerHTML='';
  items.forEach(it=>{
    if(!showHidden && it.name.startsWith('.')) return;
    const div = document.createElement('div'); div.className='tile';
    const top = document.createElement('div'); top.className='name'; top.textContent = it.name + (it.is_dir?'/':'');
    div.appendChild(top);
    const m = document.createElement('div'); m.className='meta'; m.textContent = (it.is_dir ? 'Carpeta' : humanSize(it.size)) + ' · ' + (it.mtime? new Date(it.mtime*1000).toLocaleString() : '');
    div.appendChild(m);
    const actions = document.createElement('div'); actions.className='actions';
    if(!it.is_dir){
      const dl = document.createElement('a'); dl.className='btn'; dl.textContent='Descargar'; dl.href='/navegador/download?path=' + encodeURIComponent(it.relpath);
      actions.appendChild(dl);
      const ed = document.createElement('button'); ed.className='btn alt'; ed.textContent='Editar'; ed.onclick=()=>editFile(it.relpath);
      actions.appendChild(ed);
    } else {
      const open = document.createElement('button'); open.className='btn'; open.textContent='Abrir'; open.onclick=()=>load(it.relpath);
      actions.appendChild(open);
    }
    const ren = document.createElement('button'); ren.className='btn ghost'; ren.textContent='Renombrar'; ren.onclick=()=>inlineRename(it.relpath,it.name);
    actions.appendChild(ren);
    div.appendChild(actions);
    cont.appendChild(div);
  });
}

async function load(rel){
  current = rel || '';
  mkBreadcrumbs(current);
  const params = new URLSearchParams({p: current});
  const data = await api('/navegador/api/list?' + params.toString(), {method:'GET'});
  // store items
  window._items = data.items;
  if(viewMode === 'list'){
    qs('#listing').style.display='block'; qs('#grid').style.display='none';
    renderList(data.items);
  } else {
    qs('#listing').style.display='none'; qs('#grid').style.display='grid';
    renderGrid(data.items);
  }
  qs('#selected-count').textContent = selected.size;
}

async function viewFile(rel){
  // if text -> open editor view, else download
  const params = new URLSearchParams({path: rel});
  const meta = await api('/navegador/api/meta?' + params.toString(), {method:'GET'});
  if(meta.type && meta.type.startsWith('text')){
    editFile(rel);
  } else {
    window.location = '/navegador/download?path=' + encodeURIComponent(rel);
  }
}

async function editFile(rel){
  const params = new URLSearchParams({path: rel});
  const data = await api('/navegador/api/view?' + params.toString(), {method:'GET'});
  qs('#editor-title').textContent = rel;
  qs('#editor-area').value = data.content;
  qs('#editor-modal').style.display = 'flex';
  qs('#save-edit').onclick = async ()=>{
    const body = new FormData();
    body.append('path', rel);
    body.append('content', qs('#editor-area').value);
    const res = await fetch('/navegador/api/edit', {method:'POST', body});
    if(res.ok){ qs('#editor-modal').style.display='none'; load(current); } else { alert('Error guardando'); }
  };
  qs('#cancel-edit').onclick = ()=>{ qs('#editor-modal').style.display='none'; };
}

async function deleteItem(rel){
  const body = new FormData(); body.append('path', rel);
  const res = await fetch('/navegador/api/delete', {method:'POST', body});
  if(res.ok) load(current);
}

async function inlineRename(rel, name){
  const newName = prompt('Nuevo nombre para ' + name, name);
  if(!newName) return;
  const body = new FormData(); body.append('src', rel); body.append('dst', (current?current + '/':'') + newName);
  const res = await fetch('/navegador/api/move', {method:'POST', body});
  if(res.ok) load(current);
}

async function zipSelected(){
  if(selected.size === 0){ alert('No hay seleccionados'); return; }
  const body = new FormData(); selected.forEach(s=> body.append('items', s));
  body.append('base', current);
  const res = await fetch('/navegador/api/zip', {method:'POST', body});
  if(!res.ok){ alert('Error creando zip'); return; }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'selected.zip'; a.click();
  URL.revokeObjectURL(url);
}

function attachUI(){
  qs('#toggle-view').onclick = ()=>{ viewMode = viewMode==='list'?'grid':'list'; qs('#toggle-view').textContent = viewMode==='list'?'Grid':'List'; load(current); };
  qs('#toggle-theme').onclick = ()=>{ document.body.classList.toggle('dark'); qs('#toggle-theme').textContent = document.body.classList.contains('dark')?'Light':'Dark'; };
  qs('#refresh').onclick = ()=>load(current);
  qs('#show-hidden').onclick = ()=>{ showHidden = !showHidden; qs('#show-hidden').textContent = showHidden?'Ocultar ocultos':'Mostrar ocultos'; load(current); };
  qs('#go-root').onclick = ()=>load('');
  qs('#clear-selected').onclick = ()=>{ selected.clear(); qs('#selected-count').textContent='0'; load(current); };
  qs('#btn-zip').onclick = ()=>zipSelected();
//----  Botones faltantes -------------
qs('#btn-new-folder').onclick = async () => {
  const name = prompt('Nombre de la nueva carpeta:');
  if(!name) return;
  const body = new FormData();
  body.append('p', current);
  body.append('name', name);
  const res = await fetch('/navegador/api/new_folder', {method:'POST', body});
  if(res.ok) load(current);
};
qs('#btn-new-file').onclick = async () => {
  const name = prompt('Nombre del nuevo archivo:');
  if(!name) return;
  const body = new FormData();
  body.append('p', current);
  body.append('name', name);
  const res = await fetch('/navegador/api/new_file', {method:'POST', body});
  if(res.ok) load(current);
};
// ---- Fin BF ------------
  // file input
  const input = qs('#upload-input');
  input.onchange = async (e)=>{
    const files = Array.from(e.target.files);
    await uploadFiles(files);
    input.value='';
    load(current);
  };
  // wrapper button
  // qs('.btn').onclick = (e)=>{}; // noop to keep styling
  // drag & drop
  const drop = qs('#dropzone');
  drop.ondragover = e=>{ e.preventDefault(); drop.style.background='#eef'; };
  drop.ondragleave = e=>{ drop.style.background=''; };
  drop.ondrop = async (e)=>{ e.preventDefault(); drop.style.background=''; const files = Array.from(e.dataTransfer.files); await uploadFiles(files); load(current); };

  // search
  qs('#search').oninput = (e)=>{ const q = e.target.value.trim().toLowerCase(); if(!window._items) return; const filtered = window._items.filter(it=> it.name.toLowerCase().includes(q)); if(viewMode==='list') renderList(filtered); else renderGrid(filtered); };
}

async function uploadFiles(files){
  for(const f of files){
    if(f.size > {{ max_upload_size }}){ alert(f.name + ' supera el tamaño máximo'); continue; }
    const fd = new FormData(); fd.append('p', current); fd.append('file', f);
    const res = await fetch('/navegador/api/upload', { method: 'POST', body: fd });

    if(!res.ok){ const t = await res.text(); alert('Error: '+ t); }
  }
}

async function init(){
  attachUI();
  load(current);
  // keyboard shortcuts
document.addEventListener('keydown', async (e)=>{
    if(e.key === 'F2'){ 
        const sel = Array.from(selected)[0]; 
        if(sel) inlineRename(sel, sel.split('/').slice(-1)[0]); 
    }

    if(e.key === 'Delete'){ 
        const sel = Array.from(selected); 
        if(sel.length){ 
            if(confirm('Borrar seleccionados?')){ 
                for(const s of sel){
                    await fetch('/navegador/api/delete',
                        {method:'POST', body: new URLSearchParams({path:s})}
                    );
                }
                selected.clear(); 
                load(current);
            } 
        }
    }

    if(e.key === 'Enter'){ 
        const sel = Array.from(selected)[0]; 
        if(sel){ 
            const meta = await fetch('/navegador/api/meta?path=' + encodeURIComponent(sel)); 
            if(meta.ok){ 
                const j = await meta.json(); 
                if(j.is_dir) load(sel); 
                else viewFile(sel); 
            }
        }
    }
});  // ✔️ AHORA SÍ CIERRA BIEN
}

window.addEventListener('load', init);
</script>
</body>
</html>
"""

# --- API endpoints ---
@navegador_bp.route("/", methods=["GET"])
@login_required
@admin_required
def index():
    if not API_TOKEN or not PA_USERNAME:
        return render_template_string(INDEX_TEMPLATE.replace(
            "No logs yet",
            "⚠️ Set PA_API_TOKEN and PA_USERNAME..."
        ))
    cwd = request.args.get('p', '').strip('/')
    return render_template_string(TEMPLATE, cwd=cwd, root_display=get_root(), max_upload_size=MAX_UPLOAD_SIZE)

@navegador_bp.route("/api/list", methods=["GET"])
def api_list():
    p = request.args.get('p', '').strip('/')
    items = list_dir(p)
    return jsonify({"items": items})

@navegador_bp.route("/api/meta", methods=["GET"])
def api_meta():
    path = request.args.get('path', '')
    abs_p = abs_safe(path)
    if not os.path.exists(abs_p):
        return jsonify({"error":"no existe"}), 404
    st = os.stat(abs_p)
    mime = None
    try:
        import mimetypes
        mime = mimetypes.guess_type(abs_p)[0] or ''
    except:
        mime = ''
    return jsonify({"is_dir": os.path.isdir(abs_p), "size": st.st_size, "mtime": int(st.st_mtime), "type": mime})

@navegador_bp.route("/api/view", methods=["GET"])
def api_view():
    path = request.args.get('path', '')
    abs_p = abs_safe(path)
    if not os.path.exists(abs_p):
        return jsonify({"error":"no existe"}), 404
    if os.path.isdir(abs_p):
        return jsonify({"error":"es carpeta"}), 400
    # si es texto devolvemos contenido
    if is_text_file(abs_p):
        try:
            with open(abs_p, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return jsonify({"content": content})
    else:
        # devolver meta para previsualizar/download en UI
        try:
            import mimetypes
            mime = mimetypes.guess_type(abs_p)[0] or ''
        except:
            mime = ''
        return jsonify({"type": mime})

@navegador_bp.route("/api/edit", methods=["POST"])
def api_edit():
    path = request.form.get('path', '')
    content = request.form.get('content', '')
    abs_p = abs_safe(path)
    if not os.path.exists(abs_p):
        return "no existe", 404
    if os.path.isdir(abs_p):
        return "es carpeta", 400
    if not is_text_file(abs_p):
        return "No editable", 400
    try:
        with open(abs_p, "w", encoding="utf-8") as f:
            f.write(content or '')
        return jsonify({"ok": True})
    except Exception as e:
        return str(e), 500

@navegador_bp.route("/download")
def download():
    path = request.args.get('path', '')
    abs_p = abs_safe(path)
    if not os.path.exists(abs_p):
        abort(404)
    if os.path.isdir(abs_p):
        # comprimir carpeta y enviar
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(abs_p):
                for f in files:
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, abs_p)
                    zf.write(full, arcname)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"{Path(abs_p).name}.zip", mimetype="application/zip")
    else:
        return send_file(abs_p, as_attachment=True)

@navegador_bp.route("/api/upload", methods=["POST"])
def api_upload():
    p = request.form.get('p', '').strip('/')
    abs_dir = abs_safe(p)
    if 'file' not in request.files:
        return "no file", 400
    f = request.files.get('file')
    filename = secure_filename(f.filename)
    dest = os.path.join(abs_dir, filename)
    # guarda
    try:
        f.save(dest)
    except Exception as e:
        return str(e), 500
    return jsonify({"ok": True})

@navegador_bp.route("/api/new_folder", methods=["POST"])
def api_new_folder():
    p = request.form.get('p', '').strip('/')
    name = request.form.get('name', '')
    if not name:
        return "no name", 400
    dest = abs_safe(os.path.join(p, secure_filename(name)))
    try:
        os.makedirs(dest, exist_ok=True)
        return jsonify({"ok": True})
    except Exception as e:
        return str(e), 500

@navegador_bp.route("/api/new_file", methods=["POST"])
def api_new_file():
    p = request.form.get('p', '').strip('/')
    name = request.form.get('name', '')
    if not name:
        return "no name", 400
    dest = abs_safe(os.path.join(p, secure_filename(name)))
    try:
        open(dest, "w", encoding="utf-8").close()
        return jsonify({"ok": True})
    except Exception as e:
        return str(e), 500

@navegador_bp.route("/api/delete", methods=["POST"])
def api_delete():
    path = request.form.get('path', '') or request.get_data(as_text=True)
    abs_p = abs_safe(path)
    try:
        if os.path.isdir(abs_p):
            shutil.rmtree(abs_p)
        else:
            os.remove(abs_p)
        return jsonify({"ok": True})
    except Exception as e:
        return str(e), 500

@navegador_bp.route("/api/move", methods=["POST"])
def api_move():
    src = request.form.get('src', '')
    dst = request.form.get('dst', '')
    if not src or not dst:
        return "faltan params", 400
    abs_src = abs_safe(src)
    dst_rel = dst.strip('/')
    abs_dst = abs_safe(dst_rel)
    # si dst es carpeta existente, mover dentro
    if os.path.isdir(abs_dst):
        dst_final = os.path.join(abs_dst, os.path.basename(abs_src))
    else:
        dst_final = abs_dst
    os.makedirs(os.path.dirname(dst_final), exist_ok=True)
    try:
        os.rename(abs_src, dst_final)
        return jsonify({"ok": True})
    except Exception as e:
        return str(e), 500

@navegador_bp.route("/api/zip", methods=["POST"])
def api_zip():
    items = request.form.getlist('items')
    base = request.form.get('base', '').strip('/')
    if not items:
        return "no items", 400
    abs_base = abs_safe(base)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for it in items:
            abs_item = abs_safe(it)
            if os.path.isdir(abs_item):
                for root, _, files in os.walk(abs_item):
                    for f in files:
                        full = os.path.join(root, f)
                        arcname = os.path.relpath(full, abs_base)
                        zf.write(full, arcname)
            else:
                arcname = os.path.relpath(abs_item, abs_base)
                zf.write(abs_item, arcname)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"selection_{Path(base or '.').name or 'root'}.zip", mimetype="application/zip")

# --- simple search (nombre contiene) ---
@navegador_bp.route("/api/search", methods=["GET"])
def api_search():
    q = request.args.get('q', '').lower().strip()
    p = request.args.get('p', '').strip('/')
    if not q:
        return jsonify({"items": []})
    abs_p = abs_safe(p)
    found = []
    for root, dirs, files in os.walk(abs_p):
        for name in dirs + files:
            if q in name.lower():
                full = os.path.join(root, name)
                st = os.stat(full)
                found.append({
                    "name": name,
                    "is_dir": os.path.isdir(full),
                    "size": st.st_size if os.path.isfile(full) else None,
                    "mtime": int(st.st_mtime),
                    "relpath": rel_from_abs(full)
                })
    return jsonify({"items": found})

# --- small meta endpoint for client usage ---
@navegador_bp.route("/api/download_list", methods=["POST"])
def api_download_list():
    # recibe lista de paths y devuelve zip
    items = request.form.getlist('items')
    if not items:
        return "no items", 400
    abs0 = abs_safe('')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for it in items:
            abs_item = abs_safe(it)
            if os.path.isdir(abs_item):
                for root, _, files in os.walk(abs_item):
                    for f in files:
                        full = os.path.join(root, f)
                        arcname = os.path.relpath(full, abs0)
                        zf.write(full, arcname)
            else:
                arcname = os.path.relpath(abs_item, abs0)
                zf.write(abs_item, arcname)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="download_selection.zip", mimetype="application/zip")
# ---- Protección ----
def protect_navegador(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith("navegador_full."):
            view = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = login_required(admin_required(view))
