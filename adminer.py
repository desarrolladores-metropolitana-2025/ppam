# adminer.py
# Adminer casero para DB PPAM (versión "todo integrado")
# - Lista / CRUD
# - Estructura (SHOW COLUMNS) con editor visual (preview SQL + ejecutar)
# - Export CSV / JSON
# - Buscador simple (filtros)
# - Endpoints auxiliares: show_create, enum detector
# - Backup antes de ALTER (opcional)
# - Logs de estructura
#
# Autor: Desarrollo PPAM
# Fecha: 26-11-2025

from flask import Blueprint, render_template_string, request, redirect, url_for, flash, current_app, jsonify, send_file, abort
from extensiones import db
# Todos los modelos reales deben importarse sin "*"
from modelos import Publicador, PuntoPredicacion, SolicitudTurno, Experiencia, Ausencia, Turno
from sqlalchemy import text
from flask_login import login_required, current_user
import os, datetime, json, io, csv, html

adminer_bp = Blueprint("adminer", __name__, url_prefix="/adminer")
@adminer_bp.app_template_filter('getattr')
def jinja_getattr(obj, attr):
    return getattr(obj, attr, None)
# ----- Login Admin --------------------------    
def admin_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login", next=request.url))

        if getattr(current_user, "rol", None) != "Admin":
            abort(403, description="No tenés permisos para acceder a esta sección.")

        return func(*args, **kwargs)
    return wrapper
# ------------------ CONFIG ------------------
MODELS = {
    "publicadores": Publicador,
    "puntos_predicacion": PuntoPredicacion,
    "solicitudes_turno": SolicitudTurno,
    "experiencias": Experiencia,
    "ausencias": Ausencia,
    "turnos": Turno
}

BACKUP_DIR = "/home/ppamappcaba/backups"
STRUCT_LOG_PATH = "/home/ppamappcaba/mysite/tmp/adminer_struct_log.json"
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STRUCT_LOG_PATH), exist_ok=True)
# ----- usar API Pythonanywhere ------------------------------------------------
PA_USERNAME = "ppamappcaba"
API_TOKEN = os.getenv("PA_API_TOKEN")  # Mejor guardarlo en variable de entorno
WEBAPP_DOMAIN = "ppamappcaba.pythonanywhere.com"

# ------------------ HELPERS / UTIL ------------------
def _append_struct_log(msg):
    entry = {"ts": datetime.datetime.utcnow().isoformat(), "msg": str(msg)}
    logs = []
    try:
        if os.path.exists(STRUCT_LOG_PATH):
            with open(STRUCT_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
    except Exception:
        logs = []
    logs.insert(0, entry)
    logs = logs[:500]
    try:
        with open(STRUCT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        current_app.logger.exception("No pudo guardar struct log")

def _show_create_table_sql(table):
    try:
        with db.engine.connect() as conn:
            res = conn.execute(text(f"SHOW CREATE TABLE `{table}`"))
            row = res.fetchone()
            if row:
                # row usually is (table_name, create_sql)
                return row[1] if len(row) > 1 else str(row)
    except Exception:
        current_app.logger.exception("Error SHOW CREATE TABLE")
    return None

def _backup_table(table):
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    create_sql = _show_create_table_sql(table) or f"-- NO CREATE for {table} at {ts}\n"
    fname = os.path.join(BACKUP_DIR, f"{table}_backup_{ts}.sql")
    try:
        with open(fname, "w", encoding="utf-8") as f:
            f.write(f"-- Backup generated at {ts} UTC\n")
            f.write(create_sql)
            f.write("\n")
        _append_struct_log(f"Backup creado: {fname}")
        return fname
    except Exception as e:
        _append_struct_log(f"Error creando backup: {e}")
        current_app.logger.exception("Error backup table")
        return None

def _read_struct_log_text(limit=50):
    """
    Devuelve los últimos registros del log estructural como texto.
    Si no existe el archivo, devuelve string vacío.
    """
    if not os.path.exists(STRUCT_LOG_PATH):
        return ""

    try:
        with open(STRUCT_LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)

        # logs = lista de dicts { ts, msg }
        out = []
        for l in logs[:limit]:
            ts = l.get("ts", "?")
            msg = l.get("msg", "")
            out.append(f"[{ts}] {msg}")

        return "\n".join(out)

    except Exception as e:
        current_app.logger.exception(f"Error leyendo struct log: {e}")
        return ""

def _exec_sql(sql):
    try:
        current_app.logger.info("EXEC SQL: %s", sql)
        with db.engine.connect() as conn:
            conn.execute(text(sql))
        _append_struct_log(f"SQL ejecutado: {sql}")
        return True, None
    except Exception as e:
        current_app.logger.exception("Error ejecutando SQL")
        _append_struct_log(f"Error SQL: {e} -- SQL: {sql}")
        return False, str(e)

def _get_table_meta(table):
    """Return result of SHOW COLUMNS FROM table as list of dicts"""
    try:
        with db.engine.connect() as conn:
            res = conn.execute(text(f"SHOW COLUMNS FROM `{table}`"))

            meta = []
            for row in res.fetchall():
                r = row._mapping    # ← ESTA ES LA CLAVE

                meta.append({
                    "Field": r.get("Field"),
                    "Type": r.get("Type"),
                    "Null": r.get("Null"),
                    "Key": r.get("Key"),
                    "Default": r.get("Default"),
                    "Extra": r.get("Extra")
                })

            return meta

    except Exception as e:
        current_app.logger.exception("Error SHOW COLUMNS")
        return []


from sqlalchemy import text

def _get_table_meta_from_model(model):
    """
    Devuelve metadata estilo `SHOW COLUMNS`:
    lista de dicts con claves: Field, Type, Null, Key, Default, Extra
    """
    try:
        # si te pasan directamente el nombre de tabla en vez del model, soportamos ambos
        if isinstance(model, str):
            table_name = model
        else:
            table_name = model.__table__.name

        engine = db.get_engine() if hasattr(db, "get_engine") else db.engine

        with engine.connect() as conn:
            # asegurar que usamos texto literal (escape con backticks)
            result = conn.execute(text(f"SHOW COLUMNS FROM `{table_name}`"))
            rows = result.fetchall()

        meta = []
        # filas pueden venir como RowMapping o tuple; accesible por nombre en RowMapping
        for row in rows:
            # row keys normalmente: Field, Type, Null, Key, Default, Extra
            # algunos drivers devuelven listas; manejamos ambos casos
            try:
                # row es mapeo
                meta.append({
                    "Field": row["Field"],
                    "Type": row["Type"],
                    "Null": row["Null"],
                    "Key": row.get("Key", "") if hasattr(row, "get") else (row["Key"] if "Key" in row else ""),
                    "Default": row["Default"],
                    "Extra": row.get("Extra", "") if hasattr(row, "get") else (row["Extra"] if "Extra" in row else "")
                })
            except Exception:
                # intentar por posición si no es mapping
                r = list(row)
                meta.append({
                    "Field": r[0],
                    "Type": r[1],
                    "Null": r[2],
                    "Key": r[3] if len(r) > 3 else "",
                    "Default": r[4] if len(r) > 4 else None,
                    "Extra": r[5] if len(r) > 5 else ""
                })
        return meta

    except Exception as e:
        current_app.logger.exception("Error en _get_table_meta_from_model: %s", e)
        return []


def _validate_table(table):
    # Aceptamos tablas ORM
    if table in MODELS:
        return True

    # Aceptamos tablas reales del MySQL
    result = db.session.execute(text("SHOW TABLES")).fetchall()

    tables = []
    for row in result:
        val = row[0]
        if isinstance(val, (bytes, bytearray)):
            try:
                val = val.decode("utf-8")
            except:
                val = val.decode("latin1", errors="replace")
        tables.append(val)

    return table in tables

# ------------------ TEMPLATES ------------------
# Keep templates here for single-file convenience.
# Fonts: Arial (explicit).

LIST_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Adminer — {{ table }}</title>
  <script src="/static/js/admin_ui.js"></script>
  <style>
    body{font-family:Arial, sans-serif;background:#f2f2f2;margin:0;padding:0}
    .header{background:#111;color:#fff;padding:12px 18px;display:flex;align-items:center;gap:12px}
    .logo{height:42px}
    .container{width:90%;margin:22px auto;background:#fff;padding:18px;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,0.06)}
    h1{margin:0 0 10px 0}
    .tools{display:flex;gap:8px;margin-bottom:12px;align-items:center}
    .btn{background:#0b74da;color:#fff;padding:8px 10px;border-radius:6px;text-decoration:none}
    .btn.alt{background:#6b21a8}
    .btn.danger{background:#cc3333}
    table{width:100%;border-collapse:collapse;margin-top:12px}
    th{background:#0b74da;color:#fff;padding:10px;text-align:left}
    td{padding:10px;border-bottom:1px solid #eee}
    .actions{display:flex;gap:6px}
    .search-row{margin-left:auto;display:flex;gap:6px;align-items:center}
    .small{font-size:12px;color:#666}
    .export-buttons{margin-left:8px}
  </style>
</head>
<body>
<div class="header">
  <img src="/static/img/jw_logo.png" class="logo">
  <div>
    <div style="font-weight:700">{{ table.replace('_',' ').title() }}</div>
    <div class="small">Adminer casero — tablas &amp; estructura</div>
  </div>
  <div style="margin-bottom: 15px;">
    <a href="{{ url_for('adminer.index') }}" 
       style="
           display:inline-block;
           background:#444;
           color:white;
           padding:6px 12px;
           text-decoration:none;
           border-radius:6px;">
        ← Volver
    </a>
</div>
</div>

<div class="container">
  <div style="display:flex;align-items:center">
    <div class="tools">
      <a class="btn" href="{{ url_for('adminer.new_record', table=table) }}">➕ Nuevo Registro</a>
      <a class="btn alt" href="{{ url_for('adminer.table_structure', table=table) }}">⚙️ Estructura</a>
      <a class="btn" href="{{ url_for('adminer.table_show_create', table=table) }}">🔎 SHOW CREATE</a>
      <div class="export-buttons">
        <a class="btn" href="{{ url_for('adminer.export_table', table=table, fmt='csv') }}">Export CSV</a>
        <a class="btn" href="{{ url_for('adminer.export_table', table=table, fmt='json') }}">Export JSON</a>
      </div>
    </div>

    <div class="search-row">
      <form method="get" action="{{ url_for('adminer.table_view', table=table) }}" style="display:flex;gap:6px;">
        <input name="q" placeholder="buscar..." value="{{ request.args.get('q','') }}" style="padding:8px;border-radius:6px;border:1px solid #ccc">
        <select name="col" style="padding:8px;border-radius:6px;border:1px solid #ccc">
          <option value="">— Todas —</option>
          {% for c in columns %}
            <option value="{{ c }}" {% if request.args.get('col')==c %}selected{% endif %}>{{ c }}</option>
          {% endfor %}
        </select>
        <button class="btn" type="submit">Buscar</button>
      </form>
    </div>
  </div>

  <table aria-live="polite">
    <tr>
      {% for col in columns %}
      <th>{{ col }}</th>
      {% endfor %}
      <th>Acciones</th>
    </tr>
    {% for row in rows %}
    <tr>
      {% for col in columns %}
      <td>{{ row|getattr(col) }}</td>
      {% endfor %}
      <td class="actions">
        <a class="btn" href="{{ url_for('adminer.edit_record', table=table, id=row.id) }}">✏ Editar</a>
        <a class="btn danger" href="{{ url_for('adminer.delete_record', table=table, id=row.id) }}" onclick="return confirm('Borrar registro?')">🗑 Borrar</a>
      </td>
    </tr>
    {% endfor %}
  </table>
</div>
</body>
</html>
"""

FORM_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ action }} — {{ table }}</title>
  <script src="/static/js/admin_ui.js"></script>
  <style>
    body{font-family:Arial,sans-serif;background:#f2f2f2;margin:0;padding:0}
    .header{background:#111;color:#fff;padding:12px 18px;display:flex;align-items:center;gap:12px}
    .container{width:60%;margin:22px auto;background:#fff;padding:18px;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,0.06)}
    label{display:block;margin-top:8px;font-weight:600}
    input, textarea, select{width:100%;padding:8px;border-radius:6px;border:1px solid #ccc;margin-top:6px}
    button{background:#0b74da;color:#fff;padding:10px 14px;border-radius:6px;border:none;margin-top:12px}
  </style>
</head>
<body>
<div class="header"><img src="/static/img/jw_logo.png" style="height:42px"> <strong>{{ action }} {{ table }}</strong></div>
<div class="container">
  <form method="post">
    {% for col in columns %}
      <label>{{ col }}</label>
      <input name="{{ col }}" value="{{ values.get(col, '') }}">
    {% endfor %}
    <button type="submit">Guardar</button>
    <a href="{{ url_for('adminer.table_view', table=table) }}" style="margin-left:12px">Cancelar</a>
  </form>
</div>
</body>
</html>
"""

# STRUCTURE TEMPLATE (modern + Arial)
STRUCTURE_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Estructura — {{ table }}</title>
  <script src="/static/js/admin_ui.js"></script>
  <style>
    body{font-family:Arial, sans-serif;background:#f2f2f2;margin:0;padding:0}
    .header{background:#111;color:#fff;padding:12px 18px;display:flex;align-items:center;gap:12px}
    .container{width:90%;margin:22px auto;background:#fff;padding:18px;border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,0.06)}
    .topbar { display:flex; justify-content:space-between; align-items:center;  gap: 8px; flex-wrap: wrap; }
    .topbar div:last-child { display:flex; gap:8px; }
    .btn{background:#0b74da;color:#fff;padding:8px 10px;border-radius:6px;text-decoration:none}
    table{width:100%;border-collapse:collapse;margin-top:12px}
    .table-wrapper { overflow-x: auto; width: 100%; }
    th{background:#0b74da;color:#fff;padding:10px;text-align:left}
    td{padding:10px;border-bottom:1px solid #eee}
    td:nth-child(2), th:nth-child(2) {white-space: nowrap; max-width: 240px; overflow: hidden; text-overflow: ellipsis; }
    .preview{background:#fafafa;padding:10px;border-radius:6px;margin-top:12px;font-family:monospace;white-space:pre-wrap}
    .small{font-size:13px;color:#666}
    .actions{display:flex;gap:8px;justify-content:flex-end}
    .enum-chip{background:#e2f4ff;padding:3px 8px;border-radius:12px;color:#055; font-weight:600; font-size:12px}
  </style>
  <script>
    // AJAX helpers
    async function showPreviewSQL(e, formId) {
      e.preventDefault();
      const form = document.getElementById(formId);
      const fd = new FormData(form);
      const body = Object.fromEntries(fd.entries());
      const res = await fetch(location.pathname + '/preview', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const json = await res.json();
      document.getElementById('previewBox').innerText = json.preview || json.error || '';
    }

    async function executeSQL(formId) {
      if (!confirm('Confirmar ejecución SQL?')) return;
      const form = document.getElementById(formId);
      const fd = new FormData(form);
      const body = Object.fromEntries(fd.entries());
      const res = await fetch(location.pathname + '/execute', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const j = await res.json();
      alert(j.ok ? 'OK' : ('ERROR: ' + (j.error||'')));
      if (j.ok) location.reload();
    }

    async function openModify(table, col) {
      location.href = '{{ url_for("adminer.table_modify_column", table=table, col="__COL__") }}'.replace('__COL__', col);
    }
  </script>
</head>
<body>
<div class="header"><img src="/static/img/jw_logo.png" style="height:42px"> <strong>Estructura — {{ table }}</strong>
<div style="margin-bottom: 15px;">
    <a href="{{ url_for('adminer.index') }}" 
       style="
           display:inline-block;
           background:#444;
           color:white;
           padding:6px 12px;
           text-decoration:none;
           border-radius:6px;">
        ← Volver
    </a>
</div>
</div>
<div class="container">
  <div class="topbar">
    <div><strong>Tabla:</strong> {{ table }} <span class="small"> &middot; columnas: {{ meta|length }}</span></div>
    <div class="table-wrapper">
      <a class="btn" href="{{ url_for('adminer.table_add_column', table=table) }}">➕ Agregar columna</a>
      <a class="btn" href="{{ url_for('adminer.table_add_fk', table=table) }}">Agregar FK</a>
      <a class="btn danger" href="{{ url_for('adminer.table_delete', table=table) }}">🗑 Eliminar tabla</a>
      <a class="btn" href="{{ url_for('adminer.table_view', table=table) }}">⟲ Volver</a>
    </div>
  </div>

  <table aria-live="polite">
    <tr><th>Columna</th><th>Tipo</th><th>Null</th><th>Default</th><th>Key</th><th style="text-align:right">Acciones</th></tr>
    {% for c in meta %}
    <tr>
      <td><strong>{{ c.Field }}</strong></td>
      <td>
        {{ c.Type }}
        {% if 'enum(' in c.Type|lower %}
          <span class="enum-chip">ENUM</span>
        {% endif %}
      </td>
      <td>{{ 'YES' if c.Null=='YES' else 'NO' }}</td>
      <td>{{ c.Default if c.Default is not none else '—' }}</td>
      <td>{{ c.Key if c.Key else '—' }}</td>
      <td style="text-align:right">
        <a class="btn" href="{{ url_for('adminer.table_modify_column', table=table, col=c.Field) }}">✏ Modificar</a>
        <a class="btn" style="background:#cc3333" href="{{ url_for('adminer.table_delete_column', table=table, col=c.Field) }}" onclick="return confirm('Eliminar columna?')">🗑 Eliminar</a>
      </td>
    </tr>
    {% endfor %}
  </table>

  {% if preview_sql %}
  <div class="preview"><strong>Preview SQL</strong><pre>{{ preview_sql }}</pre></div>
  {% endif %}

  {% if log %}
  <h4 style="margin-top:12px">Logs</h4>
  <div class="preview">{{ log }}</div>
  {% endif %}

  <div id="previewBox" class="preview" style="display:block;margin-top:14px"></div>
</div>
</body>
</html>
"""

ADD_COLUMN_TEMPLATE = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Agregar columna — {{ table }}</title>
<style>body{font-family:Arial,sans-serif;padding:0;margin:0;background:#f2f2f2}.container{width:70%;margin:30px auto;background:#fff;padding:18px;border-radius:8px}</style>
</head><body>
<div class="container">
  <h3>Agregar columna — {{ table }}</h3>
  <form method="post">
    <label>Nombre columna</label><input name="col_name" required><br>
    <label>Tipo (ej: VARCHAR(255), INT, DATE, TEXT, TINYINT(1), ENUM('a','b'))</label><input name="col_type" required><br>
    <label>NULL?</label>
      <select name="is_null"><option value="NULL">NULL</option><option value="NOT NULL">NOT NULL</option></select><br>
    <label>DEFAULT (opcional)</label><input name="default"><br>
    <label><input type="checkbox" name="backup" checked> Hacer backup antes de ejecutar</label><br><br>
    <button type="submit">Generar Preview</button>
    <a href="{{ url_for('adminer.table_structure', table=table) }}">Cancelar</a>
  </form>

  {% if preview_sql %}
    <h4>SQL a ejecutar</h4>
    <pre>{{ preview_sql }}</pre>
    <form method="post" action="{{ url_for('adminer.table_add_column_execute', table=table) }}">
      <input type="hidden" name="sql" value="{{ preview_sql|e }}">
      <input type="hidden" name="backup" value="{{ backup }}">
      <button type="submit">Confirmar y ejecutar</button>
    </form> 
  {% endif %}
</div>
</body></html>
"""

MODIFY_COLUMN_TEMPLATE = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Modificar columna — {{ table }}/{{ col }}</title>
<style>body{font-family:Arial,sans-serif;padding:0;margin:0;background:#f2f2f2}.container{width:70%;margin:30px auto;background:#fff;padding:18px;border-radius:8px}</style>
</head><body>
<div class="container">
  <h3>Modificar columna — {{ table }} / {{ col }}</h3>
  <form method="post">
    <label>Nuevo nombre columna</label><input name="col_name" value="{{ col }}" required><br>
    <label>Tipo</label><input name="col_type" value="{{ col_type }}" required><br>
    <label>NULL?</label>
      <select name="is_null">
        <option value="NULL" {% if is_null=='YES' %}selected{% endif %}>NULL</option>
        <option value="NOT NULL" {% if is_null!='YES' %}selected{% endif %}>NOT NULL</option>
      </select><br>
    <label>Default</label><input name="default" value="{{ default if default is not none else '' }}"><br>
    <label><input type="checkbox" name="backup" checked> Hacer backup antes de ejecutar</label><br><br>
    <button type="submit">Generar Preview</button>
    <a href="{{ url_for('adminer.table_structure', table=table) }}">Cancelar</a>
  </form>

  {% if preview_sql %}
    <h4>SQL a ejecutar</h4>
    <pre>{{ preview_sql }}</pre>
    <form method="post" action="{{ url_for('adminer.table_modify_column_execute', table=table, col=col) }}">
      <input type="hidden" name="sql" value="{{ preview_sql|e }}">
      <input type="hidden" name="backup" value="{{ backup }}">
      <button type="submit">Confirmar y ejecutar</button>
    </form>
  {% endif %}
</div>
</body></html>
"""

ADD_FK_TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Agregar Foreign Key — {{ table }}</title>

<style>
body {
    font-family: Arial, sans-serif;
    padding: 0;
    margin: 0;
    background: #f2f2f2;
}
.container {
    width: 60%;
    margin: 30px auto;
    background: #fff;
    padding: 20px 25px;
    border-radius: 8px;
}
h3, h4 {
    margin-top: 0;
}
.form-group {
    margin-bottom: 15px;
}
label {
    display: block;
    font-weight: bold;
    margin-bottom: 5px;
}
input, select {
    padding: 7px;
    width: 100%;
    box-sizing: border-box;
}
button {
    padding: 8px 15px;
    cursor: pointer;
}
pre {
    background: #eee;
    padding: 10px;
    border-radius: 5px;
    white-space: pre-wrap;
}
</style>

</head>
<body>
<div class="container">

  <h3>Agregar Foreign Key — {{ table }}</h3>

  <form method="post">

    <div class="form-group">
        <label>Columna local</label>
        <input name="local_col" required>
    </div>

    <div class="form-group">
        <label>Tabla referenciada</label>
        <input name="ref_table" required>
    </div>

    <div class="form-group">
        <label>Columna referenciada</label>
        <input name="ref_col" required>
    </div>

    <div class="form-group">
        <label>ON DELETE</label>
        <select name="on_delete">
            <option value="">(nada)</option>
            <option value="CASCADE">CASCADE</option>
            <option value="SET NULL">SET NULL</option>
            <option value="RESTRICT">RESTRICT</option>
            <option value="NO ACTION">NO ACTION</option>
        </select>
    </div>

    <div class="form-group">
        <label>ON UPDATE</label>
        <select name="on_update">
            <option value="">(nada)</option>
            <option value="CASCADE">CASCADE</option>
            <option value="SET NULL">SET NULL</option>
            <option value="RESTRICT">RESTRICT</option>
            <option value="NO ACTION">NO ACTION</option>
        </select>
    </div>

    <div class="form-group">
        <label><input type="checkbox" name="backup" checked> Hacer backup antes de ejecutar</label>
    </div>

    <button type="submit">Generar Preview</button>
    <a href="{{ url_for('adminer.table_structure', table=table) }}">Cancelar</a>

  </form>

  {% if preview_sql %}
    <h4>SQL a ejecutar</h4>
    <pre>{{ preview_sql }}</pre>

    <form method="post" action="{{ url_for('adminer.table_add_fk_execute', table=table) }}">
      <input type="hidden" name="sql" value="{{ preview_sql|e }}">
      <input type="hidden" name="backup" value="{{ backup }}">
      <button type="submit">Confirmar y ejecutar</button>
    </form>
  {% endif %}

</div>
</body>
</html>
"""

DELETE_CONFIRM_TEMPLATE = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Eliminar columna</title></head><body style="font-family:Arial,sans-serif">
<div style="width:60%;margin:30px auto;background:#fff;padding:18px;border-radius:8px">
  <h3>Eliminar columna — {{ table }} / {{ col }}</h3>
  <p>Esto es destructivo. Se perderán datos.</p>
  <form method="post">
    <label><input type="checkbox" name="backup" checked> Hacer backup</label><br><br>
    <button type="submit">Confirmar eliminación</button>
    <a href="{{ url_for('adminer.table_structure', table=table) }}">Cancelar</a>
  </form>
</div>
</body></html>
"""
DELETE_TABLE_TEMPLATE = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Eliminar tabla</title></head>
<body style="font-family:Arial;background:#f2f2f2;padding:30px">
<div style="max-width:600px;margin:auto;background:white;padding:20px;border-radius:8px">
  <h2>Eliminar tabla — {{ table }}</h2>
  <p>⚠️ Esto eliminará <strong>toda la tabla completa</strong> y no se podrá deshacer.</p>
  <p>Se hará un backup automático del CREATE TABLE antes de borrar.</p>

  <form method="post">
      <label><input type="checkbox" name="backup" checked> Hacer backup</label><br><br>
      <button style="background:#cc3333;color:white;padding:10px 14px;border:none;border-radius:6px">
          Confirmar eliminación
      </button>
      <a href="{{ url_for('adminer.table_structure', table=table) }}" style="margin-left:20px">Cancelar</a>
  </form>
</div>
</body>
</html>
"""

# ------------------ ROUTES (index / list / CRUD) ------------------

@adminer_bp.route("/")
@login_required
@admin_required
def index():
    if not API_TOKEN or not PA_USERNAME:
        return render_template_string(INDEX_TEMPLATE.replace(
            "No logs yet",
            "⚠️ Set API_TOKEN and PA_USERNAME..."
        ))
    # print("MODELS:", MODELS)
    # tables = list(MODELS.keys())
    # Obtener TODAS las tablas reales del MySQL
    with db.engine.connect() as conn:
        res = conn.execute(text("SHOW TABLES"))

        tables = []
        for row in res.fetchall():
            val = row[0]
            if isinstance(val, (bytes, bytearray)):
                try:
                    val = val.decode("utf-8")
                except:
                    val = val.decode("latin1", errors="replace")
            tables.append(val)

    INDEX_TEMPLATE = """
    <!doctype html><html><head><meta charset="utf-8"><title>Adminer</title>
     <style>
    /* (same as before) */
   body {
        font-family: Arial, Helvetica, sans-serif;
        background: #f2f2f2;
        margin: 0;
        padding: 0;
    }
.btn{background:var(--accent);color:#fff;padding:8px 10px;border-radius:8px;text-decoration:none;border:none;cursor:pointer}
.btn.alt{background:#6b7280}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--panel)}
   .header {
    background: #333;
    padding: 20px;
    color: white;
    font-size: 28px;
    font-weight: bold;
    text-align: center;   /* el título sigue centrado */
    letter-spacing: 1px;
    position: relative;   /* permite ubicar los botones flotando */
}
/* Contenedor de botones en esquina superior derecha */
.header-actions {
    position: absolute;
    right: 20px;
    top: 50%;
    transform: translateY(-50%); /* centra verticalmente */
    display: flex;
    gap: 10px;
}
/* Tus botones existentes siguen funcionando con tu estilo */
.btn {
    background: var(--accent);
    color: #fff;
    padding: 8px 10px;
    border-radius: 8px;
    text-decoration: none;
    border: none;
    cursor: pointer;
}
.btn.alt {
    background: #6b7280;
    font-size: 16px;
}
.btn.ghost {
    background: transparent;
    color: var(--accent);
    border: 1px solid var(--panel);
    font-size: 16px;
}
    .header .logout-btn {
    position: absolute;         /* <-- la ubicamos sin romper el centrado */
    right: 20px;                /* botón a la derecha */
    top: 50%;
    transform: translateY(-50%);
    font-size: 16px;
    padding: 6px 12px;}

    .sub {
        text-align: center;
        margin-top: 10px;
        font-size: 17px;
        color: #555;
    }

    .cards {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
        gap: 20px;
        width: 85%;
        margin: 40px auto;
    }

    .card {
        background: white;
        padding: 25px;
        border-radius: 12px;
        text-align: center;
        font-size: 18px;
        font-weight: bold;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        transition: transform 0.15s, box-shadow 0.15s;
        cursor: pointer;
        border-top: 5px solid #007acc;
    }

    .card:hover {
        transform: translateY(-6px);
        box-shadow: 0 6px 18px rgba(0,0,0,0.16);
    }

    a {
        text-decoration: none;
        color: #333;
    }

    .emoji {
        font-size: 40px;
        margin-bottom: 10px;
        display: block;
    }
    .logo {
    height: 55px;
    vertical-align: middle;
    margin-right: 15px;
    border-radius: 12px;
}
.fab-btn {
    position: fixed;
    bottom: 28px;
    right: 28px;
    width: 72px;
    height: 72px;
    border-radius: 50%;
    border: none;
    background: #db74da;
    color: #fff;
    font-size: 36px;
    cursor: pointer;
    box-shadow: 0 6px 14px rgba(0,0,0,0.25);
    transition: transform .2s;
    z-index: 9999;
}
.fab-btn:hover { transform: scale(1.12); }

/* Modal */
.modal-overlay {
    position: fixed;
    top:0;left:0;right:0;bottom:0;
    background: rgba(0,0,0,0.5);
    display:flex;
    align-items:center;
    justify-content:center;
    z-index:99999;
}
.modal-box {
    background:#fff;
    padding:24px;
    border-radius:10px;
    width: 360px;
    box-shadow:0 4px 18px rgba(0,0,0,0.3);
}
.modal-box h3 { margin-top:0; margin-bottom:14px; }
.modal-box input {
    width:100%;
    margin-top:6px;
    margin-bottom:12px;
    padding:8px;
    border-radius:6px;
    border:1px solid #ccc;
}
.modal-actions {
    display:flex;
    justify-content:flex-end;
    gap:8px;
}
.btn.danger { background:#cc3333; }
footer {
    width: 100%;
    text-align: center;
    padding: 12px;
    background: #0b74da;
    color: white;
    position: fixed;
    bottom: 0;
    left: 0;
    font-size: 14px;
}
    </style>
    </head><body>
   <div class="header">
    <span class="title">adminer – PPAM</span>
    <div class="header-actions">
        <a href="/ppamtools" class="btn ghost">Volver al Panel</a>
        <a href="/logout" class="btn alt">Logout</a>
    </div>
</div>

    <div class="cards">
      {% for t in tables %}
        <a href="{{ url_for('adminer.table_view', table=t) }}"><div class="card">{{ t.replace('_',' ').title() }}</div></a>
      {% endfor %}
    </div>
    <!-- Floating Action Button -->
<button id="fabAddTable" class="fab-btn">+</button>

<!-- Modal Crear Tabla -->
<div id="modalCreateTable" class="modal-overlay" style="display:none;">
  <div class="modal-box">
    <h3>Crear nueva tabla</h3>

    <form id="formCreateTable">
      <label>Nombre de la tabla</label>
      <input name="table_name" required placeholder="p.ej. nuevos_datos">

      <label>Engine (opcional)</label>
      <input name="engine" placeholder="InnoDB">

      <label>Charset (opcional)</label>
      <input name="charset" placeholder="utf8mb4">

      <div class="modal-actions">
        <button type="submit" class="btn">Crear</button>
        <button type="button" class="btn danger" onclick="closeCreateModal()">Cancelar</button>
      </div>
    </form>
  </div>
</div>
<script>
function openCreateModal() {
    document.getElementById("modalCreateTable").style.display = "flex";
}
function closeCreateModal() {
    document.getElementById("modalCreateTable").style.display = "none";
}
document.getElementById("fabAddTable").onclick = openCreateModal;

document.getElementById("formCreateTable").onsubmit = async (e) => {
    e.preventDefault();
    let fd = new FormData(e.target);
    let data = Object.fromEntries(fd);

    let res = await fetch("/adminer/create_table", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify(data)
    });

    let j = await res.json();
    if (!j.ok) {
        alert("ERROR: " + j.error);
        return;
    }

    alert("Tabla creada correctamente.");
    location.reload();
};
</script>
<footer>
    Equipo de desarrollo PPAM 2025 · ©
</footer>
    </body></html>
    """
    return render_template_string(INDEX_TEMPLATE, tables=tables)

@adminer_bp.route("/table/<table>")
def table_view(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    # Caso ORM
    if table in MODELS and MODELS[table] is not None:
        model = MODELS[table]
        columns = [c.name for c in model.__table__.columns]
        # SELECT * FROM MODEL
        rows = model.query.limit(500).all()
        ... # búsqueda ORM normal

        return render_template_string(LIST_TEMPLATE, table=table, columns=columns, rows=rows)

    # Caso tabla genérica
    # Obtener columnas manualmente
    meta = _get_table_meta(table)
    columns = []
    for m in meta:
        col = m["Field"]
        if isinstance(col, (bytes, bytearray)):
            try:
                col = col.decode("utf-8")
            except:
                col = col.decode("latin1", errors="replace")
        columns.append(col)


    # SELECT * FROM table LIMIT 500
    with db.engine.connect() as conn:
        res = conn.execute(text(f"SELECT * FROM `{table}` LIMIT 500"))

        def normalize_row(r):
            clean = {}
            for k, v in r._mapping.items():
                if isinstance(v, (bytes, bytearray)):
                    try:
                        clean[k] = v.decode("utf-8")
                    except:
                        clean[k] = v.decode("latin1", errors="replace")
                else:
                    clean[k] = v
            return clean

        rows = [normalize_row(r) for r in res]
        print("ROWS:", rows)
        #for r in rows:
            # print("ROW TYPE:", type(r))
            # print("DIR:", dir(r))
            # print("AS MAPPING:", getattr(r, "_mapping", None))


    # Usamos un template simplificado para tablas genéricas
    GENERIC_TEMPLATE = """
    <!doctype html>
    <html><head><meta charset="utf-8">
    <title>{{ table }}</title>
    <style>
      body{font-family:Arial;background:#f2f2f2;margin:0;padding:0}
    .container{width:90%;margin:22px auto;background:#fff;padding:18px;border-radius:8px}
    .tools{display:flex;gap:8px;margin-bottom:12px;align-items:center}
    .btn{background:#0b74da;color:#fff;padding:8px 10px;border-radius:6px;text-decoration:none}
    .btn.alt{background:#6b21a8}
    .btn.danger{background:#cc3333}
      table{width:100%;border-collapse:collapse}
      th{background:#0b74da;color:#fff;padding:8px}
      td{padding:8px;border-bottom:1px solid #eee}
    table { width: 100%; border-collapse: collapse; table-layout: fixed;}
    th, td { padding: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: center; vertical-align: middle; }  
    </style>
    </head><body>
    <div class="container">
     <div style="display:flex;align-items:center">
    <div class="tools">
      <a class="btn" href="{{ url_for('adminer.new_record', table=table) }}">➕ Nuevo Registro</a>
      <a class="btn alt" href="{{ url_for('adminer.table_structure', table=table) }}">⚙️ Estructura</a>
      <a class="btn" href="{{ url_for('adminer.table_show_create', table=table) }}">🔎 SHOW CREATE</a>
      <div class="export-buttons">
        <a class="btn" href="{{ url_for('adminer.export_table', table=table, fmt='csv') }}">Export CSV</a>
        <a class="btn" href="{{ url_for('adminer.export_table', table=table, fmt='json') }}">Export JSON</a>
      </div>
      <div style="margin-bottom: 15px;">
    <a class="btn" href="{{ url_for('adminer.index') }}"> ← Volver </a>
</div>
    </div>
   </div>
      <h2>Tabla: {{ table }}</h2>
      <table>
        <tr>
        {% for col in columns %}
            <th>{{ col }}</th>
        {% endfor %}
        <th>Acciones</th>
        </tr>

        {% for row in rows %}
        <tr>
            {% for col in columns %}
                <td>{{ row[col] }}</td>
            {% endfor %}
     <td class="actions">
        <a class="btn" href="{{ url_for('adminer.edit_record', table=table, id=row.id) }}">✏ Editar</a>
        <a class="btn danger" href="{{ url_for('adminer.delete_record', table=table, id=row.id) }}" onclick="return confirm('Borrar registro?')">🗑 Borrar</a>
    </td>
        </tr>
        {% endfor %}
      </table>

      <p style="margin-top:18px;">
         Esta tabla no está registrada como modelo SQLAlchemy.<br>
         Podés agregar columnas en “Estructura”.
      </p>
    </div>
    </body></html>
    """

    return render_template_string(GENERIC_TEMPLATE, table=table, columns=columns, rows=rows)
# ------------------ GENERIC + ORM: NEW RECORD ------------------

@adminer_bp.route("/table/<table>/new", methods=["GET","POST"])
def new_record(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    # TABLA CON MODELO ORM
    if table in MODELS and MODELS[table] is not None:
        model = MODELS[table]
        columns = [c.name for c in model.__table__.columns if c.name != "id"]

        if request.method == "POST":
            data = {}
            for col in columns:
                column_obj = model.__table__.columns[col]
                val = request.form.get(col)

                # --- FIX para BOOLEAN ---
                if hasattr(column_obj.type, "python_type") and column_obj.type.python_type is bool:
                    if val in ("True", "true", "1", "on"):
                        data[col] = True
                    elif val in ("False", "false", "0", "", None):
                        data[col] = False
                    else:
                        data[col] = None
                else:
                    data[col] = val if val != "" else None

            obj = model(**data)
            db.session.add(obj)
            db.session.commit()
            return redirect(url_for("adminer.table_view", table=table))

        return render_template_string(FORM_TEMPLATE, action="Nuevo", table=table, columns=columns, values={})

    # TABLA GENERICA SIN MODELO
    meta = _get_table_meta(table)
    columns = [m["Field"] for m in meta if m["Field"] != "id"]

    if request.method == "POST":
        fields = []
        values = []
        params = {}

        for col in columns:
            val = request.form.get(col)
            fields.append(f"`{col}`")
            values.append(f":{col}")
            params[col] = val if val != "" else None

        sql = f"INSERT INTO `{table}` ({', '.join(fields)}) VALUES ({', '.join(values)})"

        try:
            with db.engine.begin() as conn:
                conn.execute(text(sql), params)
        except Exception as e:
            return f"Error al guardar: {e}"

        return redirect(url_for("adminer.table_view", table=table))

    return render_template_string(FORM_TEMPLATE, action="Nuevo", table=table, columns=columns, values={})

# ------------------ GENERIC + ORM: EDIT RECORD ------------------
@adminer_bp.route("/table/<table>/edit/<int:id>", methods=["GET","POST"])
def edit_record(table, id):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    # ORM
    if table in MODELS and MODELS[table] is not None:
        model = MODELS[table]
        obj = model.query.get(id)
        if not obj:
            return "Registro no encontrado", 404

        columns = [c.name for c in model.__table__.columns if c.name != "id"]

        if request.method == "POST":
            for col in columns:
                column_obj = model.__table__.columns[col]
                val = request.form.get(col)

                # --- FIX para BOOLEAN ---
                if hasattr(column_obj.type, "python_type") and column_obj.type.python_type is bool:
                    if val in ("True", "true", "1", "on"):
                        setattr(obj, col, True)
                    elif val in ("False", "false", "0", "", None):
                        setattr(obj, col, False)
                    else:
                        setattr(obj, col, None)
                else:
                    setattr(obj, col, val if val != "" else None)

            db.session.commit()
            return redirect(url_for("adminer.table_view", table=table))

        values = {col: getattr(obj, col) for col in columns}
        return render_template_string(FORM_TEMPLATE, action="Editar", table=table, columns=columns, values=values)

    # GENERIC TABLE (RAW SQL)
    meta = _get_table_meta(table)
    columns = [m["Field"] for m in meta if m["Field"] != "id"]

    # cargar fila
    with db.engine.connect() as conn:
        row = conn.execute(text(f"SELECT * FROM `{table}` WHERE id=:id"), {"id": id}).fetchone()
    if not row:
        return "Registro no encontrado", 404

    row = row._mapping

    if request.method == "POST":
        sets = []
        params = {"id": id}
        for col in columns:
            sets.append(f"`{col}` = :{col}")
            params[col] = request.form.get(col) or None

        sql = f"UPDATE `{table}` SET {', '.join(sets)} WHERE id=:id"

        with db.engine.connect() as conn:
            conn.execute(text(sql), params)

        return redirect(url_for("adminer.table_view", table=table))

    values = {c: row[c] for c in columns}
    return render_template_string(FORM_TEMPLATE, action="Editar", table=table, columns=columns, values=values)

# ------------------ GENERIC + ORM: DELETE RECORD ------------------

@adminer_bp.route("/table/<table>/delete/<int:id>")
def delete_record(table, id):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    # ORM
    if table in MODELS and MODELS[table] is not None:
        model = MODELS[table]
        obj = model.query.get(id)
        if not obj:
            return "Registro no encontrado", 404
        db.session.delete(obj)
        db.session.commit()
        return redirect(url_for("adminer.table_view", table=table))

    # GENERIC TABLE
    sql = f"DELETE FROM `{table}` WHERE id=:id"
    with db.engine.connect() as conn:
        conn.execute(text(sql), {"id": id})

    return redirect(url_for("adminer.table_view", table=table))

# ------------------ STRUCTURE ROUTES ------------------

@adminer_bp.route("/table/<table>/structure", methods=["GET", "POST"])
@adminer_bp.route("/table/<table>/structure", methods=["GET", "POST"])
def table_structure(table):

    # verificar acceso
    if not _validate_table(table):
        return "Tabla no permitida", 404

    if table in MODELS and MODELS[table] is not None:
        # usar modelo ORM
        meta = _get_table_meta_from_model(MODELS[table])
    else:
        # tabla genérica sin modelo
        meta = _get_table_meta(table)

    log_text = _read_struct_log_text(limit=50)

    return render_template_string(
        STRUCTURE_TEMPLATE,
        table=table,
        meta=meta,
        preview_sql=None,
        log=log_text
    )
# --- AGREGAR COLUMNA ---------------------------------------------------    
@adminer_bp.route("/table/<table>/structure/add", methods=["GET","POST"])
def table_add_column(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    preview_sql = None
    backup = "1"

    if request.method == "POST":
        col_name = request.form.get("col_name", "").strip()
        col_type = request.form.get("col_type", "").strip()
        is_null = request.form.get("is_null") or "NULL"
        default = request.form.get("default", "").strip()
        backup = request.form.get("backup", "1")
        default_clause = ""

        if default:
            safe = default.replace("'", "''")

            # Palabras clave SQL que no llevan comillas
            SQL_KEYWORDS = {
                "CURRENT_TIMESTAMP",
                "CURRENT_DATE",
                "CURRENT_TIME",
                "NOW()",
                "UUID()",
            }

            # Si coincide con keyword exacta
            if default.upper() in SQL_KEYWORDS:
                default_clause = f" DEFAULT {default}"

            # Si el usuario ya puso comillas manualmente
            elif (default.startswith("'") and default.endswith("'")) \
              or (default.startswith('"') and default.endswith('"')):
                default_clause = f" DEFAULT {default}"

            # Si es número → dejar sin comillas
            else:
                try:
                    float(default)
                    default_clause = f" DEFAULT {default}"
                except:
                    default_clause = f" DEFAULT '{safe}'"

        preview_sql = (
            f"ALTER TABLE `{table}` ADD COLUMN `{col_name}` "
            f"{col_type} {is_null}{default_clause};"
        )

        return render_template_string(
            ADD_COLUMN_TEMPLATE,
            table=table,
            preview_sql=preview_sql,
            backup=backup
        )

    return render_template_string(
        ADD_COLUMN_TEMPLATE,
        table=table,
        preview_sql=None,
        backup=backup
    )


@adminer_bp.route("/table/<table>/structure/add/execute", methods=["POST"])
def table_add_column_execute(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    sql = request.form.get("sql")
    backup = request.form.get("backup") == "1"
    if backup:
        _backup_table(table)
    ok, err = _exec_sql(sql)
    if not ok:
        return f"Error ejecutando SQL: {err}", 500
    return redirect(url_for("adminer.table_structure", table=table))

# modify column (show current info using SHOW COLUMNS)
@adminer_bp.route("/table/<table>/structure/modify/<col>", methods=["GET","POST"])
def table_modify_column(table, col):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    meta = _get_table_meta(table)
    col_info = next((c for c in meta if c.get("Field") == col), None)
    if not col_info:
        return "Columna no encontrada", 404
    preview_sql = None
    backup = "1"
    if request.method == "POST":
        new_name = request.form.get("col_name").strip()
        col_type = request.form.get("col_type").strip()
        is_null = request.form.get("is_null") or "NULL"
        default = request.form.get("default","").strip()
        backup = request.form.get("backup","1")
        default_clause = ""
        if default:
            try:
                float(default)
                default_clause = f" DEFAULT {default}"
            except Exception:
                safe = default.replace("'", "''")
                default_clause = f" DEFAULT '{safe}'"
        preview_sql = f"ALTER TABLE `{table}` CHANGE `{col}` `{new_name}` {col_type} {is_null}{default_clause};"
        return render_template_string(MODIFY_COLUMN_TEMPLATE, table=table, col=col, col_type=col_info.get("Type"), is_null=col_info.get("Null"), default=col_info.get("Default"), preview_sql=preview_sql, backup=backup)
    return render_template_string(MODIFY_COLUMN_TEMPLATE, table=table, col=col, col_type=col_info.get("Type"), is_null=col_info.get("Null"), default=col_info.get("Default"), preview_sql=None, backup=backup)

@adminer_bp.route("/table/<table>/structure/modify/<col>/execute", methods=["POST"])
def table_modify_column_execute(table, col):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    sql = request.form.get("sql")
    backup = request.form.get("backup") == "1"
    if backup:
        _backup_table(table)
    ok, err = _exec_sql(sql)
    if not ok:
        return f"Error ejecutando SQL: {err}", 500
    return redirect(url_for("adminer.table_structure", table=table))

@adminer_bp.route("/table/<table>/structure/delete/<col>", methods=["GET","POST"])
def table_delete_column(table, col):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    if request.method == "POST":
        backup = request.form.get("backup") == "on"
        sql = f"ALTER TABLE `{table}` DROP COLUMN `{col}`;"
        if backup:
            _backup_table(table)
        ok, err = _exec_sql(sql)
        if not ok:
            return f"Error ejecutando SQL: {err}", 500
        return redirect(url_for("adminer.table_structure", table=table))
    return render_template_string(DELETE_CONFIRM_TEMPLATE, table=table, col=col)

# small AJAX helpers
@adminer_bp.route("/table/<table>/show_create")
def table_show_create(table):
    if not _validate_table(table):
        return jsonify({"ok": False, "error": "tabla no permitida"}), 404
    create = _show_create_table_sql(table)
    return jsonify({"ok": True, "create": create})

# ------------------ EXPORT / SEARCH / AUX APIs ------------------

@adminer_bp.route("/table/<table>/export.<fmt>")
def export_table(table, fmt="csv"):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    model = MODELS[table]
    rows = model.query.all()
    columns = [c.name for c in model.__table__.columns]

    if fmt == "json":
        out = []
        for r in rows:
            d = {}
            for c in columns:
                v = getattr(r, c)
                if isinstance(v, (datetime.date, datetime.datetime)):
                    d[c] = v.isoformat()
                else:
                    d[c] = v
            out.append(d)
        return jsonify(out)
    else:
        # CSV
        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(columns)
        for r in rows:
            writer.writerow([getattr(r, c) for c in columns])
        mem = io.BytesIO()
        mem.write(si.getvalue().encode("utf-8"))
        mem.seek(0)
        return send_file(mem, mimetype="text/csv", download_name=f"{table}.csv", as_attachment=True)

@adminer_bp.route("/search", methods=["GET"])
def adminer_search():
    """
    Simple search API:
    ?table=turnos&q=texto&col=nombre
    returns up to 200 rows (json)
    """
    table = request.args.get("table")
    q = request.args.get("q","").strip()
    col = request.args.get("col")
    if not table or not _validate_table(table):
        return jsonify({"ok": False, "error": "tabla inválida"}), 400
    model = MODELS[table]
    columns = [c.name for c in model.__table__.columns]
    q_obj = model.query
    if q:
        if col and col in columns:
            pattern = f"%{q}%"
            q_obj = q_obj.filter(text(f"`{col}` LIKE :p")).params(p=pattern)
        else:
            # naive: search string columns
            from sqlalchemy import or_, cast, String
            clauses = []
            for c in model.__table__.columns:
                if getattr(c.type, "__class__", None).__name__.lower() in ("varchar","string","text","nvarchar","char"):
                    clauses.append(c.cast(String).ilike(f"%{q}%"))
            if clauses:
                q_obj = q_obj.filter(or_(*clauses))
    rows = q_obj.limit(500).all()
    out = []
    for r in rows:
        d = {c: getattr(r, c) for c in [c.name for c in model.__table__.columns]}
        out.append(d)
    return jsonify({"ok": True, "rows": out})

@adminer_bp.route("/table/<table>/enum_values/<col>")
def enum_values(table, col):
    """Return enum possible values for a column, if any (used in UI)."""
    if not _validate_table(table):
        return jsonify({"ok": False, "error": "tabla no permitida"}), 404
    meta = _get_table_meta(table)
    c = next((x for x in meta if x.get("Field") == col), None)
    if not c:
        return jsonify({"ok": False, "error": "columna no encontrada"}), 404
    t = c.get("Type","")
    if not t.lower().startswith("enum("):
        return jsonify({"ok": False, "enum": []})
    # extract values
    inside = t[t.find("(")+1:t.rfind(")")]
    # split by ',' but values are quoted
    vals = []
    cur = ""
    inq = False
    for ch in inside:
        if ch == "'" and not inq:
            inq = True
            cur = ""
            continue
        if ch == "'" and inq:
            inq = False
            vals.append(cur)
            cur = ""
            continue
        if inq:
            cur += ch
    return jsonify({"ok": True, "enum": vals})

# ------------------ STRUCT LOG API ------------------
@adminer_bp.route("/struct_log")
def struct_log():
    if not os.path.exists(STRUCT_LOG_PATH):
        return jsonify({"ok": True, "logs": []})
    try:
        with open(STRUCT_LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)
        return jsonify({"ok": True, "logs": logs})
    except Exception:
        return jsonify({"ok": False, "error": "no pudo leer logs"}), 500

# ------------------ Small utility route used by templates (preview & execute) ------------------
@adminer_bp.route("/table/<table>/structure/preview", methods=["POST"])
def table_structure_preview(table):
    """
    Preview endpoint: receives JSON body (keys from form) and returns {"preview": sql}
    Used by AJAX in STRUCTURE_TEMPLATE (if desired).
    For safety simply return the preview already produced in ADD/MODIFY handlers.
    """
    body = request.get_json(silent=True) or {}
    # very naive: if contains col_name & col_type produce ADD, if contains new_name produce CHANGE
    if "col_name" in body and "col_type" in body and "action" in body and body["action"] == "add":
        col_name = body.get("col_name")
        col_type = body.get("col_type")
        is_null = body.get("is_null","NULL")
        default = body.get("default","")
        default_clause = f" DEFAULT '{default}'" if default else ""
        sql = f"ALTER TABLE `{table}` ADD COLUMN `{col_name}` {col_type} {is_null}{default_clause};"
        return jsonify({"preview": sql})
    if "col_name" in body and "col_type" in body and "action" in body and body["action"] == "modify":
        old = body.get("old_col")
        new = body.get("col_name")
        col_type = body.get("col_type")
        is_null = body.get("is_null","NULL")
        default = body.get("default","")
        default_clause = f" DEFAULT '{default}'" if default else ""
        sql = f"ALTER TABLE `{table}` CHANGE `{old}` `{new}` {col_type} {is_null}{default_clause};"
        return jsonify({"preview": sql})
    return jsonify({"error": "No se pudo generar preview"}), 400

@adminer_bp.route("/table/<table>/structure/execute", methods=["POST"])
def table_structure_execute(table):
    data = request.get_json(silent=True) or {}
    sql = data.get("sql")
    backup = data.get("backup", True)
    if not sql:
        return jsonify({"ok": False, "error": "sql faltante"}), 400
    if backup:
        _backup_table(table)
    ok, err = _exec_sql(sql)
    if not ok:
        return jsonify({"ok": False, "error": err}), 500
    return jsonify({"ok": True})
# -------------------------- CREATE TABLE (sql) -----------------------------------------------    
@adminer_bp.route("/create_table", methods=["POST"])
def create_table():
    data = request.get_json(force=True)
    table = data.get("table_name", "").strip()
    engine = data.get("engine", "InnoDB").strip() or "InnoDB"
    charset = data.get("charset", "utf8mb4").strip() or "utf8mb4"

    if not table:
        return jsonify({"ok": False, "error": "nombre de tabla requerido"}), 400

    # Validaciones básicas
    if " " in table or "-" in table:
        return jsonify({"ok": False, "error": "nombre inválido (sin espacios ni guiones)"}), 400

    sql = f"""
    CREATE TABLE `{table}` (
        `id` INT NOT NULL AUTO_INCREMENT,
        PRIMARY KEY (`id`)
    ) ENGINE={engine} DEFAULT CHARSET={charset};
    """.strip()

    try:
        _backup_table("ALL_TABLES_BEFORE_CREATE")
        ok, err = _exec_sql(sql)
        if not ok:
            return jsonify({"ok": False, "error": err}), 500

        # Logging
        _append_struct_log(f"Tabla creada: {table}")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@adminer_bp.route("/table/execute_sql", methods=["POST"])
def adminer_execute_sql():
    sql = request.form.get("sql", "").strip()
    table = request.form.get("table", "")

    if not sql:
        return "SQL vacío", 400

    if not _validate_table(table):
        return "Tabla no permitida", 403

    try:
        db.session.execute(db.text(sql))
        db.session.commit()
        flash("SQL ejecutado correctamente", "success")
    except Exception as e:
        flash(f"Error al ejecutar SQL: {e}", "danger")
        return redirect(url_for("adminer.table_structure", table=table))

    return redirect(url_for("adminer.table_structure", table=table))
# ----------------------- DROP TABLE ------------------------------------
@adminer_bp.route("/table/<table>/delete", methods=["GET", "POST"])
def table_delete(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    if request.method == "POST":
        backup = request.form.get("backup") == "on"
        if backup:
            _backup_table(table)

        ok, err = _exec_sql(f"DROP TABLE `{table}`;")
        if not ok:
            return f"Error eliminando tabla: {err}", 500

        # Si era un modelo ORM, lo removemos de MODELS para evitar errores
        if table in MODELS:
            del MODELS[table]

        return redirect(url_for("adminer.index"))

    return render_template_string(DELETE_TABLE_TEMPLATE, table=table)
# ------------------ Proteger todo el archivo ----------------------------------
def protect_adminer(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith("apiapp."):
            view = app.view_functions[rule.endpoint]
            app.view_functions[rule.endpoint] = login_required(admin_required(view))
# ------------------ AGREGAR FK -----------
# Add Foreign Key -> preview -> execute
@adminer_bp.route("/table/<table>/structure/add_fk", methods=["GET", "POST"])
def table_add_fk(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    preview_sql = None
    backup = "1"

    if request.method == "POST":
        local_col = request.form.get("local_col", "").strip()
        ref_table = request.form.get("ref_table", "").strip()
        ref_col = request.form.get("ref_col", "").strip()
        on_delete = request.form.get("on_delete", "").strip()
        on_update = request.form.get("on_update", "").strip()
        backup = request.form.get("backup", "1")

        # constraint name automático
        constraint_name = f"fk_{table}_{local_col}"

        sql = (
            f"ALTER TABLE `{table}` "
            f"ADD CONSTRAINT `{constraint_name}` "
            f"FOREIGN KEY (`{local_col}`) "
            f"REFERENCES `{ref_table}`(`{ref_col}`)"
        )

        if on_delete:
            sql += f" ON DELETE {on_delete}"

        if on_update:
            sql += f" ON UPDATE {on_update}"

        sql += ";"

        preview_sql = sql

        return render_template_string(
            ADD_FK_TEMPLATE,
            table=table,
            preview_sql=preview_sql,
            backup=backup
        )

    return render_template_string(
        ADD_FK_TEMPLATE,
        table=table,
        preview_sql=None,
        backup=backup
    )
# Ejecutar FK final
@adminer_bp.route("/table/<table>/structure/add_fk/execute", methods=["POST"])
def table_add_fk_execute(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404

    sql = request.form.get("sql")
    backup = request.form.get("backup") == "1"

    if backup:
        _backup_table(table)

    ok, err = _exec_sql(sql)
    if not ok:
        return f"Error ejecutando SQL: {err}", 500

    return redirect(url_for("adminer.table_structure", table=table))

# ------------------ END ------------------
# Note: register blueprint in your flask_app: app.register_blueprint(adminer_bp)
# Example:
#   from adminer import adminer_bp
#   app.register_blueprint(adminer_bp)
#
# Security note: add @login_required or proper checks in production.
