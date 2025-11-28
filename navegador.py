# navegador.py
import os
import io
import zipfile
from pathlib import Path
from flask import Blueprint, current_app, request, render_template_string, send_file, redirect, url_for, abort
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from datetime import datetime

navegador_bp = Blueprint("navegador", __name__, url_prefix="/navegador")
# ------ Trampita --------------------------------------------
@navegador_bp.app_template_filter('datetimeformat')
def datetimeformat(value):
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return value

# --- Helpers ---
def get_root():
    # Configurable root directory: set app.config['FILEBROWSER_ROOT'] in your Flask app
    root = current_app.config.get("FILEBROWSER_ROOT", os.getcwd())
    return os.path.abspath(root)

def safe_path(relpath):
    """
    Devuelve la ruta absoluta si está dentro del root, o lanza abort(403).
    relpath puede ser '' o estar compuesto por subcarpetas.
    """
    root = get_root()
    # Normalizar y unir
    joined = os.path.normpath(os.path.join(root, relpath))
    # Evitar salir del root
    if not joined.startswith(root):
        abort(403, "Acceso fuera del directorio permitido")
    return joined

def list_dir(abs_path):
    items = []
    for name in sorted(os.listdir(abs_path), key=lambda s: s.lower()):
        p = os.path.join(abs_path, name)
        items.append({
            "name": name,
            "is_dir": os.path.isdir(p),
            "size": os.path.getsize(p) if os.path.isfile(p) else None,
            "mtime": os.path.getmtime(p)
        })
    return items

def human_size(n):
    for unit in ['B','KB','MB','GB','TB']:
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}PB"

# --- Template (inline para mantener un solo archivo) ---
TEMPLATE = """
<!doctype html>
<html><head><meta charset="utf-8">
<title>Navegador de archivos - {{ relpath or '/' }}</title>
<style>
  body{font-family:Arial, sans-serif;background:#f6f8fb;margin:0;padding:0}
  .wrap{width:95%;max-width:1100px;margin:18px auto;background:#fff;padding:16px;border-radius:8px}
  h2{margin:0 0 12px 0}
  .tools{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
  .btn{background:#0b74da;color:#fff;padding:8px 10px;border-radius:6px;text-decoration:none}
  table{width:100%;border-collapse:collapse}
  th{background:#0b74da;color:#fff;padding:8px;text-align:center}
  td{padding:8px;border-bottom:1px solid #eee;text-align:center;vertical-align:middle}
  .muted{color:#666;font-size:90%}
  footer{margin-top:18px;padding-top:8px;border-top:1px solid #eee;font-size:90%;color:#444}
  .name{ text-align:left }
  input[type=text]{padding:6px;border:1px solid #ccc;border-radius:4px}
  .small{font-size:90%}
  .danger{background:#cc3333}
  .success{background:#2a9d8f}
  .inline-form{display:inline-block;margin-right:6px}
</style>
</head><body>
<div class="wrap">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <h2>Navegador: /{{ relpath }}</h2>
    <div class="muted">Root: {{ root_display }}</div>
  </div>

  {% if msg %}
    <div style="padding:8px;background:#f0f8ff;border:1px solid #cfe8ff;margin-bottom:8px">{{ msg }}</div>
  {% endif %}

  <div class="tools">
    <a class="btn" href="{{ url_for('navegador.browser', p=relpath) }}">Refrescar</a>

    <form class="inline-form" action="{{ url_for('navegador.upload') }}" method="post" enctype="multipart/form-data">
      <input type="hidden" name="p" value="{{ relpath }}">
      <input type="file" name="file" required>
      <button class="btn" type="submit">Subir</button>
    </form>

    <form class="inline-form" action="{{ url_for('navegador.new_folder') }}" method="post">
      <input type="hidden" name="p" value="{{ relpath }}">
      <input type="text" name="folder" placeholder="Nueva carpeta" required>
      <button class="btn" type="submit">Crear carpeta</button>
    </form>

    <form class="inline-form" action="{{ url_for('navegador.create_file') }}" method="post">
      <input type="hidden" name="p" value="{{ relpath }}">
      <input type="text" name="filename" placeholder="nuevo.txt" required>
      <button class="btn" type="submit">Crear archivo</button>
    </form>

    <form class="inline-form" action="{{ url_for('navegador.compress') }}" method="post">
      <input type="hidden" name="p" value="{{ relpath }}">
      <input type="text" name="names" placeholder="archivo1.txt,carpeta2 (lista separada por ,)">
      <button class="btn" type="submit">Comprimir (zip)</button>
    </form>
  </div>

  <table>
    <tr>
      <th>Nombre</th><th>Tipo</th><th>Tamaño</th><th>Modificado</th><th>Acciones</th>
    </tr>
    {% if relpath %}
    <tr>
      <td class="name"><a href="{{ url_for('navegador.browser', p=parent_path) }}">.. &nbsp; (subir)</a></td>
      <td class="muted">dir</td><td></td><td></td><td></td>
    </tr>
    {% endif %}

    {% for it in items %}
      <tr>
        <td class="name">
          {% if it.is_dir %}
            <a href="{{ url_for('navegador.browser', p=join_path(relpath, it.name)) }}">{{ it.name }}/</a>
          {% else %}
            <a href="{{ url_for('navegador.view', path=join_path(relpath, it.name)) }}">{{ it.name }}</a>
          {% endif %}
        </td>
        <td>{{ 'carpeta' if it.is_dir else 'archivo' }}</td>
        <td>{{ human_size(it.size) if it.size is not none else '' }}</td>
        <td>{{ it.mtime|datetimeformat }}</td>
        <td>
          {% if not it.is_dir %}
            <a class="btn" href="{{ url_for('navegador.download', path=join_path(relpath, it.name)) }}">Descargar</a>
            <a class="btn" href="{{ url_for('navegador.edit', path=join_path(relpath, it.name)) }}">Editar</a>
          {% endif %}
          <form class="inline-form" action="{{ url_for('navegador.delete') }}" method="post" onsubmit="return confirm('Confirmar borrar {{ it.name }}?')">
            <input type="hidden" name="p" value="{{ join_path(relpath,it.name) }}">
            <button class="btn danger" type="submit">Borrar</button>
          </form>
          <form class="inline-form" action="{{ url_for('navegador.move') }}" method="post">
            <input type="hidden" name="src" value="{{ join_path(relpath,it.name) }}">
            <input type="text" name="dst" placeholder="dest/ {{ it.name }}" required>
            <button class="btn" type="submit">Mover/Renombrar</button>
          </form>
        </td>
      </tr>
    {% endfor %}
  </table>

  <footer>
    Equipo de desarrollo PPAM 2025 · ©
  </footer>
</div>
</body></html>
"""

# --- Filters para template ---
from datetime import datetime
def datetimeformat(value):
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S") if value else ""

# --- Routes ---
@navegador_bp.app_template_filter()
def datetimeformat_filter(v): return datetimeformat(v)

@navegador_bp.route("/", methods=["GET"])
def browser():
    rel = request.args.get("p", "").strip("/")
    abs_path = safe_path(rel or "")
    items = list_dir(abs_path)
    # convert items to objects usable in template
    class Item: pass
    objs = []
    for it in items:
        o = Item()
        o.name = it["name"]
        o.is_dir = it["is_dir"]
        o.size = it["size"]
        o.mtime = it["mtime"]
        objs.append(o)
    parent = "/".join(rel.split("/")[:-1]) if rel else ""
    return render_template_string(TEMPLATE,
                                  relpath=rel,
                                  root_display=get_root(),
                                  items=objs,
                                  parent_path=parent,
                                  join_path=lambda a,b: "/".join([x for x in [a.strip("/"), b.strip("/")] if x]),
                                  human_size=human_size,
                                  datetimeformat=datetimeformat,
                                  msg=request.args.get("msg"))

@navegador_bp.route("/download")
def download():
    path = request.args.get("path", "")
    abs_path = safe_path(path)
    if os.path.isdir(abs_path):
        abort(400, "No se puede descargar una carpeta directamente.")
    if not os.path.exists(abs_path):
        abort(404)
    return send_file(abs_path, as_attachment=True)

@navegador_bp.route("/view")
def view():
    path = request.args.get("path", "")
    abs_path = safe_path(path)
    if not os.path.exists(abs_path):
        abort(404)
    # Determinar tipo simple por sufijo
    mimetype = None
    try:
        import mimetypes
        mimetype = mimetypes.guess_type(abs_path)[0]
    except Exception:
        mimetype = None

    if mimetype and mimetype.startswith("text"):
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return render_template_string("""
            <pre style="white-space:pre-wrap;word-wrap:break-word;padding:12px;background:#fff;margin:16px;border-radius:6px">{{content}}</pre>
            <p><a href="{{url}}">Volver</a> - <a href="{{edit_url}}">Editar</a></p>
        """, content=content, url=url_for("navegador.browser", p="/".join(path.split("/")[:-1])), edit_url=url_for("navegador.edit", path=path))
    else:
        # enviar como archivo (imágenes, pdf, etc)
        return send_file(abs_path)

@navegador_bp.route("/upload", methods=["POST"])
def upload():
    rel = request.form.get("p", "").strip("/")
    abs_dir = safe_path(rel)
    f: FileStorage = request.files.get("file")
    if not f:
        return redirect(url_for("navegador.browser", p=rel, msg="No hay archivo."))
    filename = secure_filename(f.filename)
    dest = os.path.join(abs_dir, filename)
    f.save(dest)
    return redirect(url_for("navegador.browser", p=rel, msg="Archivo subido."))

@navegador_bp.route("/new_folder", methods=["POST"])
def new_folder():
    rel = request.form.get("p", "").strip("/")
    folder = request.form.get("folder")
    if not folder:
        return redirect(url_for("navegador.browser", p=rel, msg="Nombre inválido."))
    dest = safe_path(os.path.join(rel, secure_filename(folder)))
    os.makedirs(dest, exist_ok=True)
    return redirect(url_for("navegador.browser", p=rel, msg="Carpeta creada."))

@navegador_bp.route("/create_file", methods=["POST"])
def create_file():
    rel = request.form.get("p", "").strip("/")
    name = request.form.get("filename")
    if not name:
        return redirect(url_for("navegador.browser", p=rel, msg="Nombre inválido."))
    dest = safe_path(os.path.join(rel, secure_filename(name)))
    open(dest, "w", encoding="utf-8").close()
    return redirect(url_for("navegador.browser", p=rel, msg="Archivo creado."))

@navegador_bp.route("/delete", methods=["POST"])
def delete():
    p = request.form.get("p", "")
    abs_path = safe_path(p)
    if os.path.isdir(abs_path):
        # borrar recursivamente
        import shutil
        shutil.rmtree(abs_path)
    else:
        os.remove(abs_path)
    parent = "/".join(p.split("/")[:-1])
    return redirect(url_for("navegador.browser", p=parent, msg="Eliminado."))

@navegador_bp.route("/move", methods=["POST"])
def move():
    src = request.form.get("src", "")
    dst = request.form.get("dst", "")
    if not src or not dst:
        return redirect(url_for("navegador.browser", msg="Faltan parámetros."))
    abs_src = safe_path(src)
    # dst puede ser relativo desde root o relativo a la carpeta actual: normalizamos
    # si dst comienza con '/', lo tratamos relativo al root
    dst_rel = dst.strip("/")
    abs_dst = safe_path(dst_rel)
    # si dst es carpeta, mover dentro con mismo nombre
    if os.path.isdir(abs_dst):
        dst_final = os.path.join(abs_dst, os.path.basename(abs_src))
    else:
        dst_final = abs_dst
    os.makedirs(os.path.dirname(dst_final), exist_ok=True)
    os.rename(abs_src, dst_final)
    parent = "/".join(dst_rel.split("/")[:-1])
    return redirect(url_for("navegador.browser", p=parent, msg="Movido/Renombrado."))

@navegador_bp.route("/edit", methods=["GET","POST"])
def edit():
    path = request.args.get("path") if request.method == "GET" else request.form.get("path")
    if not path:
        abort(400)
    abs_path = safe_path(path)
    if request.method == "GET":
        if not os.path.exists(abs_path):
            abort(404)
        # solo editar archivos de texto
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return render_template_string("""
            <h3>Editar: {{ path }}</h3>
            <form method="post">
              <input type="hidden" name="path" value="{{ path }}">
              <textarea name="content" style="width:100%;height:400px">{{content}}</textarea><br>
              <button type="submit">Guardar</button>
              <a href="{{ url_for('navegador.browser', p=parent) }}">Cancelar</a>
            </form>
        """, path=path, content=content, parent="/".join(path.split("/")[:-1]))
    else:
        text = request.form.get("content", "")
        # grabar
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(text)
        return redirect(url_for("navegador.browser", p="/".join(path.split("/")[:-1]), msg="Guardado."))

@navegador_bp.route("/compress", methods=["POST"])
def compress():
    rel = request.form.get("p", "").strip("/")
    names = request.form.get("names", "")
    if not names:
        return redirect(url_for("navegador.browser", p=rel, msg="No se indicó qué comprimir."))
    items = [n.strip() for n in names.split(",") if n.strip()]
    abs_base = safe_path(rel)
    # crear zip en memoria
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in items:
            abs_item = safe_path(os.path.join(rel, name))
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
    return send_file(buf, as_attachment=True, download_name=f"compress_{Path(rel or '.').name or 'root'}.zip", mimetype="application/zip")
