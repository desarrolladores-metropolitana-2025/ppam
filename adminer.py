# adminer.py
from flask import Blueprint, render_template_string, request, redirect, url_for, flash, current_app, jsonify
from extensiones import db
from modelos import *
import sqlalchemy
from sqlalchemy import inspect, text
import os
import datetime
import json
import html

adminer_bp = Blueprint("adminer", __name__)
@adminer_bp.app_template_filter('getattr')
def jinja_getattr(obj, attr):
    return getattr(obj, attr)

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
# ensure dirs exist
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(os.path.dirname(STRUCT_LOG_PATH), exist_ok=True)

# ------------------ TEMPLATES (LIST + FORM unchanged) ------------------
# (I kept your original LIST_TEMPLATE and FORM_TEMPLATE as-is with small tweaks
#  to add link to "Estructura".)
LIST_TEMPLATE = """
<style>
/* (kept same styles as original, plus small structure btn) */
body {
    font-family: Arial, Helvetica, sans-serif;
    background: #f2f2f2;
    margin: 0;
    padding: 0;
}

.header {
    background: #333;
    padding: 20px;
    color: white;
    font-size: 24px;
    font-weight: bold;
    text-align: center;
    letter-spacing: 1px;
}

.container {
    width: 85%;
    margin: 40px auto;
    background: white;
    padding: 25px;
    border-radius: 10px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}

h1 {
    margin-top: 0;
    color: #444;
}

.table-actions a, .new-btn {
    background: #007acc;
    color: white;
    padding: 7px 12px;
    border-radius: 5px;
    text-decoration: none;
}

.table-actions a:hover, .new-btn:hover {
    background: #005c99;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 15px;
}

th {
    background: #007acc;
    color: white;
    padding: 10px;
    border: none;
}

td {
    background: #fafafa;
    padding: 10px;
    border-bottom: 1px solid #ddd;
}

td:last-child {
    text-align: center;
}

tr:hover td {
    background: #eef6ff;
}
.logo {
    height: 55px;
    vertical-align: middle;
    margin-right: 15px;
    border-radius: 12px;
}
.table-actions {
    display: flex;
    gap: 8px;
    justify-content: center;
}

.table-actions a {
    background: #007acc;
    color: white;
    padding: 6px 10px;
    border-radius: 5px;
    text-decoration: none;
    white-space: nowrap;
}

.table-actions a:hover {
    background: #005c99;
}

.table-actions a.delete-btn {
    background: #cc0000;
}

.table-actions a.delete-btn:hover {
    background: #990000;
}

</style>

<div class="header"><img src="/static/img/jw_logo.png" class="logo">Proyecto PPAM – Panel Admin</div>

<div class="container">
    <h1>{{ table }}</h1>

    <div style="display:flex;gap:8px;margin-bottom:12px;">
      <a class="new-btn" href="{{ url_for('adminer.new_record', table=table) }}">➕ Nuevo Registro</a>
      <a class="new-btn" style="background:#6b21a8" href="{{ url_for('adminer.table_structure', table=table) }}">⚙️ Estructura</a>
    </div>

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
            <td>{{ row | getattr(col) }}</td>
            {% endfor %}
            <td class="table-actions">
    <a href="{{ url_for('adminer.edit_record', table=table, id=row.id) }}">✏ Editar</a>
    <a class="delete-btn" href="{{ url_for('adminer.delete_record', table=table, id=row.id) }}">🗑 Borrar</a>
        </td>
        </tr>
        {% endfor %}
    </table>
</div>
"""

FORM_TEMPLATE = """
<style>
/* (kept original form styles) */
body {
    font-family: Arial, Helvetica, sans-serif;
    background: #f2f2f2;
    margin: 0;
    padding: 0;
}

.header {
    background: #333;
    padding: 20px;
    color: white;
    font-size: 24px;
    font-weight: bold;
    text-align: center;
}

.container {
    width: 60%;
    margin: 40px auto;
    background: white;
    padding: 25px;
    border-radius: 10px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}

h1 {
    margin-top: 0;
    color: #444;
}

input {
    width: 100%;
    padding: 10px;
    margin: 8px 0 18px 0;
    border-radius: 5px;
    border: 1px solid #ccc;
}

button {
    background: #007acc;
    color: white;
    padding: 12px 18px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
}

button:hover {
    background: #005c99;
}
.logo {
    height: 55px;
    vertical-align: middle;
    margin-right: 15px;
    border-radius: 12px;
}


</style>
<div class="header"><img src="/static/img/jw_logo.png" class="logo">Proyecto PPAM – Panel Admin</div>
<div class="container">
    <h1>{{ action }} {{ table }}</h1>
    <form method="post">
        {% for col in columns %}
        <label>{{ col }}:</label><br>
        <input name="{{ col }}" value="{{ values.get(col,'') }}">
        {% endfor %}
        <button type="submit">Guardar</button>
    </form>
</div>
"""

# ------------------ STRUCTURE TEMPLATES ------------------
STRUCTURE_TEMPLATE = """
<style>
body {
    font-family: Arial, sans-serif !important;
    background:#f2f2f2;
    margin:0;
    padding:0;
}

.container { 
    width: 85%; 
    margin: 30px auto; 
    background:#fff; 
    padding:20px; 
    border-radius:10px; 
    box-shadow: 0 4px 14px rgba(0,0,0,0.08); 
}
.header { 
    background:#333; 
    color:#fff; 
    padding:16px; 
    font-weight:600; 
    display:flex;
    align-items:center;
}
.table { 
    width:100%; 
    border-collapse:collapse; 
    margin-top:12px;
}
.table th { 
    text-align:left; 
    background:#0f172a; 
    color:#fff; 
    padding:8px; 
}
.table td { 
    padding:10px; 
    border-bottom:1px solid #eee; 
}
.actions { 
    display:flex; 
    gap:8px; 
    justify-content:flex-end; 
}
.btn { 
    padding:6px 10px; 
    border-radius:6px; 
    text-decoration:none; 
    color:#fff; 
}
.btn.edit { background:#0ea5e9; } 
.btn.add { background:#10b981; } 
.btn.delete { background:#ef4444; }

.preview { 
    background:#fafafa; 
    padding:8px; 
    border-radius:6px; 
    font-family: monospace; 
    font-size:13px; 
    white-space:pre-wrap; 
    margin-top:10px;
}
.small { font-size:12px; color:#666; }

.topbar { 
    display:flex; 
    justify-content:space-between; 
    align-items:center; 
    gap:12px; 
}
.logo {
    height: 55px;
    margin-right: 15px;
    border-radius: 12px;
}
</style>

<div class="header">
    <img src="/static/img/jw_logo.png" class="logo">
    Estructura — {{ table }}
</div>

<div class="container">

  <div class="topbar">
    <div>
      <strong>Tabla:</strong> {{ table }} &nbsp;
      <span class="small">Columnas: {{ meta|length }}</span>
    </div>

    <div class="actions">
      <a class="btn add" href="{{ url_for('adminer.table_add_column', table=table) }}">➕ Agregar Columna</a>
      <a class="btn" style="background:#6b21a8" href="{{ url_for('adminer.table_view', table=table) }}">⟲ Volver</a>
    </div>
  </div>

  <table class="table">
    <tr>
      <th>Columna</th>
      <th>Tipo</th>
      <th>Nulo</th>
      <th>Default</th>
      <th>PK</th>
      <th>Extra</th>
      <th style="text-align:right;">Acciones</th>
    </tr>

    {% for c in meta %}
    <tr>
      <td><strong>{{ c.Field }}</strong></td>
      <td>{{ c.Type }}</td>
      <td>{{ c.Null }}</td>
      <td>{{ c.Default if c.Default is not none else '—' }}</td>
      <td>{{ '✔' if c.Key == 'PRI' else '—' }}</td>
      <td>{{ c.Extra }}</td>

      <td style="text-align:right;">
        <a class="btn edit" href="{{ url_for('adminer.table_modify_column', table=table, col=c.Field) }}">✏ Modificar</a>
        <a class="btn delete" href="{{ url_for('adminer.table_delete_column', table=table, col=c.Field) }}">🗑 Eliminar</a>
      </td>
    </tr>
    {% endfor %}
  </table>

  {% if preview_sql %}
  <div class="preview">
    <strong>Preview SQL:</strong>
    <pre>{{ preview_sql }}</pre>
  </div>
  {% endif %}

  {% if log %}
  <h4 style="margin-top:16px">Últimos logs</h4>
  <pre class="preview">{{ log }}</pre>
  {% endif %}

</div>
"""


ADD_COLUMN_TEMPLATE = """
<div class="header"><img src="/static/img/jw_logo.png" class="logo">Agregar columna — {{ table }}</div>
<div class="container">
  <form method="post">
    <label>Nombre columna</label><br>
    <input name="col_name" required><br>
    <label>Tipo (ej: VARCHAR(255), INT, DATE, TEXT, TINYINT(1), ENUM('a','b'))</label><br>
    <input name="col_type" required><br>
    <label>NULL?</label>
    <select name="is_null"><option value="NULL">NULL</option><option value="NOT NULL">NOT NULL</option></select><br>
    <label>DEFAULT (opcional)</label><br>
    <input name="default"><br><br>
    <label><input type="checkbox" name="backup" checked> Hacer backup antes de ejecutar (recomendado)</label><br><br>
    <button type="submit">Generar SQL Preview</button>
    <a href="{{ url_for('adminer.table_structure', table=table) }}" class="btn" style="background:#6b21a8;margin-left:8px">Cancelar</a>
  </form>

  {% if preview_sql %}
  <div class="preview">
    <strong>SQL a ejecutar:</strong>
    <pre>{{ preview_sql }}</pre>
    <form method="post" action="{{ url_for('adminer.table_add_column_execute', table=table) }}">
      <input type="hidden" name="sql" value="{{ preview_sql|e }}">
      <input type="hidden" name="backup" value="{{ backup }}">
      <button type="submit" class="btn add">Confirmar y ejecutar</button>
    </form>
  </div>
  {% endif %}
</div>
"""

MODIFY_COLUMN_TEMPLATE = """
<div class="header"><img src="/static/img/jw_logo.png" class="logo">Modificar columna — {{ table }} / {{ col }}</div>
<div class="container">
  <form method="post">
    <label>Nombre columna (nuevo nombre)</label><br>
    <input name="col_name" value="{{ col }}" required><br>
    <label>Tipo (ej: VARCHAR(255), INT, DATE, TEXT, TINYINT(1), ENUM('a','b'))</label><br>
    <input name="col_type" value="{{ col_type }}" required><br>
    <label>NULL?</label>
    <select name="is_null"><option value="NULL" {% if is_null=='YES' %}selected{% endif %}>NULL</option><option value="NOT NULL" {% if is_null!='YES' %}selected{% endif %}>NOT NULL</option></select><br>
    <label>DEFAULT (opcional)</label><br>
    <input name="default" value="{{ default }}"><br><br>

    <label><input type="checkbox" name="backup" checked> Hacer backup antes de ejecutar (recomendado)</label><br><br>
    <button type="submit">Generar SQL Preview</button>
    <a href="{{ url_for('adminer.table_structure', table=table) }}" class="btn" style="background:#6b21a8;margin-left:8px">Cancelar</a>
  </form>

  {% if preview_sql %}
  <div class="preview">
    <strong>SQL a ejecutar:</strong>
    <pre>{{ preview_sql }}</pre>
    <form method="post" action="{{ url_for('adminer.table_modify_column_execute', table=table, col=col) }}">
      <input type="hidden" name="sql" value="{{ preview_sql|e }}">
      <input type="hidden" name="backup" value="{{ backup }}">
      <button type="submit" class="btn edit">Confirmar y ejecutar</button>
    </form>
  </div>
  {% endif %}
</div>
"""

DELETE_CONFIRM_TEMPLATE = """
<div class="header"><img src="/static/img/jw_logo.png" class="logo">Eliminar Columna — {{ table }} / {{ col }}</div>
<div class="container">
  <p>Vas a eliminar la columna <strong>{{ col }}</strong> de la tabla <strong>{{ table }}</strong>. Esto <strong>es destructivo</strong> y perderás datos.</p>
  <form method="post">
    <label><input type="checkbox" name="backup" checked> Hacer backup antes de ejecutar (recomendado)</label><br><br>
    <button type="submit" class="btn delete">Confirmar eliminación</button>
    <a href="{{ url_for('adminer.table_structure', table=table) }}" class="btn" style="background:#6b21a8;margin-left:8px">Cancelar</a>
  </form>
</div>
"""

# ------------------ UTILITIES ------------------
def _validate_table(table):
    return table in MODELS

def _show_create_table_sql(table):
    # MySQL: SHOW CREATE TABLE table
    sql = f"SHOW CREATE TABLE `{table}`"
    try:
        res = db.engine.execute(sql)
        row = res.fetchone()
        if row:
            # row typically: (table_name, create_sql)
            return row[1]
    except Exception as e:
        current_app.logger.exception("Error SHOW CREATE TABLE")
    return None

def _backup_table(table):
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    create_sql = _show_create_table_sql(table)
    if not create_sql:
        # fallback: try to build simple CREATE via SQLAlchemy metadata? skip for now
        create_sql = f"-- NO CREATE AVAILABLE for {table} at {ts}\n"
    fname = os.path.join(BACKUP_DIR, f"{table}_backup_{ts}.sql")
    try:
        with open(fname, "w", encoding="utf-8") as f:
            f.write(f"-- Backup generated at {ts} UTC\n")
            f.write(create_sql)
            f.write("\n")
            # optionally export rows (careful with size) - skip for performance
        _append_struct_log(f"Backup creado: {fname}")
        return fname
    except Exception as e:
        _append_struct_log(f"Error creando backup: {e}")
        return None

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
    # keep last 200
    logs = logs[:200]
    try:
        with open(STRUCT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        current_app.logger.exception("No pudo guardar struct log")

def _exec_sql(sql):
    try:
        current_app.logger.info("EXEC SQL: %s", sql)
        res = db.engine.execute(sql)
        _append_struct_log(f"SQL ejecutado: {sql}")
        return True, None
    except Exception as e:
        current_app.logger.exception("Error ejecutando SQL")
        _append_struct_log(f"Error SQL: {e} -- SQL: {sql}")
        return False, str(e)

def _get_table_meta(table):
    q = db.engine.execute(f"SHOW COLUMNS FROM `{table}`")
    return [dict(r) for r in q.fetchall()]

def _read_struct_log_text(limit=20):
    if not os.path.exists(STRUCT_LOG_PATH):
        return ""
    try:
        with open(STRUCT_LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)
        #text = "\n".join([f\"[{l['ts']}] {l['msg']}\" for l in logs[:limit]])
        text = "\n".join([f"[{l['ts']}] {l['msg']}" for l in logs[:limit]])

        return text
    except Exception:
        return ""

#    Table Meta from model
def _get_table_meta_from_model(model):
    """Devuelve metadata estilo SHOW COLUMNS para usar en STRUCTURE_TEMPLATE"""
    try:
        table_name = model.__table__.name
        engine = db.get_engine()

        query = text(f"SHOW COLUMNS FROM `{table_name}`")

        with engine.connect() as conn:
            result = conn.execute(query)
            rows = result.fetchall()

        meta = []
        for row in rows:
            meta.append({
                "Field": row[0],      # nombre de columna
                "Type": row[1],       # tipo
                "Null": row[2],       # YES/NO
                "Key": row[3],        # PRI/UNI/etc
                "Default": row[4],    # valor por defecto
                "Extra": row[5],      # AUTO_INCREMENT etc
            })

        return meta

    except Exception as e:
        current_app.logger.exception(f"Error en _get_table_meta_from_model: {e}")
        return []

# ------------------ ROUTES ------------------

@adminer_bp.route("/")
def index():
    INDEX_TEMPLATE = """
    <style>
    /* (same as before) */
   body {
        font-family: Arial, Helvetica, sans-serif;
        background: #f2f2f2;
        margin: 0;
        padding: 0;
    }

    .header {
        background: #333;
        padding: 20px;
        color: white;
        font-size: 28px;
        font-weight: bold;
        text-align: center;
        letter-spacing: 1px;
    }

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

    </style>

    <div class="header"><img src="/static/img/jw_logo.png" class="logo">Proyecto PPAM – Panel Admin</div>
    <div class="sub">Seleccione una tabla para administrar</div>

    <div class="cards">
        {% for t in tables %}
        <a href="{{ url_for('adminer.table_view', table=t) }}">
            <div class="card">
                <span class="emoji">📄</span>
                {{ t.replace('_', ' ').title() }}
            </div>
        </a>
        {% endfor %}
    </div>
    """
    return render_template_string(INDEX_TEMPLATE, tables=MODELS.keys())


@adminer_bp.route("/table/<table>")
def table_view(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    model = MODELS[table]
    rows = model.query.all()
    columns = [c.name for c in model.__table__.columns]
    return render_template_string(LIST_TEMPLATE, table=table, rows=rows, columns=columns)


@adminer_bp.route("/table/<table>/new", methods=["GET", "POST"])
def new_record(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    model = MODELS[table]
    columns = [c.name for c in model.__table__.columns if c.name != "id"]

    if request.method == "POST":
        data = {}
        for col in columns:
            # attempt simple type casting: if column is Integer and form empty -> None
            val = request.form.get(col)
            data[col] = val if val != "" else None
        obj = model(**data)
        db.session.add(obj)
        db.session.commit()
        return redirect(url_for("adminer.table_view", table=table))

    return render_template_string(FORM_TEMPLATE, action="Nuevo", table=table, columns=columns, values={})


@adminer_bp.route("/table/<table>/edit/<int:id>", methods=["GET", "POST"])
def edit_record(table, id):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    model = MODELS[table]
    obj = model.query.get(id)
    if not obj:
        return "Registro no encontrado", 404
    columns = [c.name for c in model.__table__.columns if c.name != "id"]

    if request.method == "POST":
        for col in columns:
            val = request.form.get(col)
            setattr(obj, col, val if val != "" else None)
        db.session.commit()
        return redirect(url_for("adminer.table_view", table=table))

    values = {col: getattr(obj, col) for col in columns}
    return render_template_string(FORM_TEMPLATE, action="Editar", table=table, columns=columns, values=values)


@adminer_bp.route("/table/<table>/delete/<int:id>")
def delete_record(table, id):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    model = MODELS[table]
    obj = model.query.get(id)
    if not obj:
        return "Registro no encontrado", 404
    db.session.delete(obj)
    db.session.commit()
    return redirect(url_for("adminer.table_view", table=table))

# ------------------ STRUCTURE ROUTES ------------------
@adminer_bp.route("/table/<table>/structure", methods=["GET", "POST"])
def table_structure(table):
    # Validar existencia del modelo
    if table not in MODELS:
        return "Tabla no encontrada", 404

    model = MODELS[table]

    # Obtener metadata de columnas (lista)
    try:
        meta = _get_table_meta_from_model(model)
    except Exception as e:
        meta = []
        current_app.logger.exception("Error obteniendo meta para table_structure: %s", e)

    # leer log de estructura (si lo usás)
    try:
        log_text = _read_struct_log_text(limit=50)
    except Exception:
        log_text = ""

    # preview_sql placeholder (puedes generar ALTER/CREATE aquí si querés)
    preview_sql = None

    # Asegurarnos que 'meta' sea iterable y calculable su longitud
    col_count = len(meta) if hasattr(meta, "__len__") else 0

    #return render_template_string(STRUCTURE_TEMPLATE, table=table, meta=meta, columns=col_count, preview_sql=preview_sql, log=log_text)
    return render_template_string(
    STRUCTURE_TEMPLATE,
    table=table,
    meta=meta,
    columns=meta,      # ← columns es ahora la lista completa
    preview_sql=preview_sql,
    log=log_text
)


@adminer_bp.route("/adminer/table/<table>/structure/add", methods=["GET", "POST"])
def table_add_column(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    preview_sql = None
    backup = "1"
    if request.method == "POST":
        col_name = request.form.get("col_name").strip()
        col_type = request.form.get("col_type").strip()
        is_null = request.form.get("is_null") or "NULL"
        default = request.form.get("default")
        backup = request.form.get("backup", "1")
        default_clause = ""
        if default:
            # try to determine numeric vs string
            if default.isdigit():
                default_clause = f" DEFAULT {default}"
            else:
                default_clause = f" DEFAULT '{default.replace('\"','\\\"')}'"
        preview_sql = f"ALTER TABLE `{table}` ADD COLUMN `{col_name}` {col_type} {is_null}{default_clause};"
        return render_template_string(ADD_COLUMN_TEMPLATE, table=table, preview_sql=preview_sql, backup=backup)

    return render_template_string(ADD_COLUMN_TEMPLATE, table=table, preview_sql=None, backup=backup)


@adminer_bp.route("/adminer/table/<table>/structure/add/execute", methods=["POST"])
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


@adminer_bp.route("/adminer/table/<table>/structure/modify/<col>", methods=["GET", "POST"])
def table_modify_column(table, col):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    col = col
    meta = _get_table_meta(table)
    col_info = next((c for c in meta if c["Field"] == col), None)
    if not col_info:
        return "Columna no encontrada", 404

    preview_sql = None
    backup = "1"
    if request.method == "POST":
        new_name = request.form.get("col_name").strip()
        col_type = request.form.get("col_type").strip()
        is_null = request.form.get("is_null") or "NULL"
        default = request.form.get("default")
        backup = request.form.get("backup", "1")
        default_clause = ""
        if default:
            if default.isdigit():
                default_clause = f" DEFAULT {default}"
            else:
                default_clause = f" DEFAULT '{default.replace('\"','\\\"')}'"
        # MySQL CHANGE syntax: CHANGE `old` `new` <type> [NULL | NOT NULL] [DEFAULT ...]
        preview_sql = f"ALTER TABLE `{table}` CHANGE COLUMN `{col}` `{new_name}` {col_type} {is_null}{default_clause};"
        return render_template_string(MODIFY_COLUMN_TEMPLATE, table=table, col=col, col_type=col_info.get("Type"), is_null=col_info.get("Null"), default=col_info.get("Default"), preview_sql=preview_sql, backup=backup)

    return render_template_string(MODIFY_COLUMN_TEMPLATE, table=table, col=col, col_type=col_info.get("Type"), is_null=col_info.get("Null"), default=col_info.get("Default"), preview_sql=None, backup=backup)


@adminer_bp.route("/adminer/table/<table>/structure/modify/<col>/execute", methods=["POST"])
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


@adminer_bp.route("/adminer/table/<table>/structure/delete/<col>", methods=["GET", "POST"])
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


# small helper endpoint to fetch create table (for debug / ajax)
@adminer_bp.route("/adminer/table/<table>/show_create", methods=["GET"])
def table_show_create(table):
    if not _validate_table(table):
        return jsonify({"ok": False, "error": "tabla no permitida"}), 404
    create = _show_create_table_sql(table)
    return jsonify({"ok": True, "create": create})


# expose struct log quickly
@adminer_bp.route("/adminer/struct_log")
def struct_log():
    if not os.path.exists(STRUCT_LOG_PATH):
        return jsonify({"ok": True, "logs": []})
    try:
        with open(STRUCT_LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)
        return jsonify({"ok": True, "logs": logs})
    except Exception:
        return jsonify({"ok": False, "error": "no pudo leer logs"}), 500

# ------------------ END FILE ------------------
