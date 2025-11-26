# adminer.py
# Adminer casero (versión "todo integrado")
# - Lista / CRUD
# - Estructura (SHOW COLUMNS) con editor visual (preview SQL + ejecutar)
# - Export CSV / JSON
# - Buscador simple (filtros)
# - Endpoints auxiliares: show_create, enum detector
# - Backup antes de ALTER (opcional)
# - Logs de estructura
#
# Autor: Tito (generado por ChatGPT) — adaptado para PPAM
# Fecha: 2025-11-25

from flask import Blueprint, render_template_string, request, redirect, url_for, flash, current_app, jsonify, send_file, abort
from extensiones import db
from modelos import *
from sqlalchemy import text
import os, datetime, json, io, csv, html

adminer_bp = Blueprint("adminer", __name__, url_prefix="/adminer")
@adminer_bp.app_template_filter('getattr')
def jinja_getattr(obj, attr):
    return getattr(obj, attr, None)


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
    """Return result of SHOW COLUMNS FROM table as list of dict (Field, Type, Null, Key, Default, Extra)"""
    try:
        with db.engine.connect() as conn:
            res = conn.execute(text(f"SHOW COLUMNS FROM `{table}`"))
            rows = [dict(r) for r in res.fetchall()]
        return rows
    except Exception:
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
    return table in MODELS

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

# ------------------ ROUTES (index / list / CRUD) ------------------

@adminer_bp.route("/")
def index():
    tables = list(MODELS.keys())
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
    </head><body>
    <div class="header"><img src="/static/img/jw_logo.png" style="height:42px"> Adminer — PPAM</div>
    <div class="cards">
      {% for t in tables %}
        <a href="{{ url_for('adminer.table_view', table=t) }}"><div class="card">{{ t.replace('_',' ').title() }}</div></a>
      {% endfor %}
    </div>
    </body></html>
    """
    return render_template_string(INDEX_TEMPLATE, tables=tables)

@adminer_bp.route("/table/<table>")
def table_view(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    model = MODELS[table]

    # Simple search support via ?q=...&col=...
    q = request.args.get("q","").strip()
    col = request.args.get("col","").strip()
    columns = [c.name for c in model.__table__.columns]

    # Base query
    q_obj = model.query
    if q:
        # if col provided and valid -> filter by that column (LIKE)
        if col and col in columns:
            # use text filter to avoid SQLAlchemy complexities for arbitrary columns
            pattern = f"%{q}%"
            q_obj = q_obj.filter(text(f"`{col}` LIKE :p")).params(p=pattern)
        else:
            # search across string-like columns (naive)
            from sqlalchemy import or_, cast, String
            clauses = []
            for c in model.__table__.columns:
                if getattr(c.type, "__class__", None).__name__.lower() in ("varchar","string","text","nvarchar","char"):
                    clauses.append(c.cast(String).ilike(f"%{q}%"))
            # if no string columns, fallback to id match
            if clauses:
                q_obj = q_obj.filter(or_(*clauses))
            else:
                try:
                    q_int = int(q)
                    q_obj = q_obj.filter(model.id == q_int)
                except Exception:
                    pass

    rows = q_obj.limit(1000).all()
    return render_template_string(LIST_TEMPLATE, table=table, rows=rows, columns=columns, request=request)

@adminer_bp.route("/table/<table>/new", methods=["GET","POST"])
def new_record(table):
    if not _validate_table(table):
        return "Tabla no permitida", 404
    model = MODELS[table]
    columns = [c.name for c in model.__table__.columns if c.name != "id"]
    if request.method == "POST":
        data = {}
        for col in columns:
            val = request.form.get(col)
            data[col] = val if val != "" else None
        obj = model(**data)
        db.session.add(obj)
        db.session.commit()
        return redirect(url_for("adminer.table_view", table=table))
    return render_template_string(FORM_TEMPLATE, action="Nuevo", table=table, columns=columns, values={})

@adminer_bp.route("/table/<table>/edit/<int:id>", methods=["GET","POST"])
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
    if table not in MODELS:
        return "Tabla no encontrada", 404

    model = MODELS.get(table)

    # Intentamos obtener meta desde SHOW COLUMNS para que coincida con la plantilla
    meta = _get_table_meta_from_model(model)

    # leer log de estructura si existe
    log_text = _read_struct_log_text(limit=50)

    preview_sql = None

    return render_template_string(
        STRUCTURE_TEMPLATE,
        table=table,
        meta=meta,
        preview_sql=preview_sql,
        log=log_text
    )

# Add column -> preview -> execute
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
        default = request.form.get("default","").strip()
        backup = request.form.get("backup", "1")
        default_clause = ""
        if default:
            # naive detection number or string
            try:
                float(default)
                default_clause = f" DEFAULT {default}"
            except Exception:
                safe = default.replace("'", "''")
                default_clause = f" DEFAULT '{safe}'"
        preview_sql = f"ALTER TABLE `{table}` ADD COLUMN `{col_name}` {col_type} {is_null}{default_clause};"
        return render_template_string(ADD_COLUMN_TEMPLATE, table=table, preview_sql=preview_sql, backup=backup)
    return render_template_string(ADD_COLUMN_TEMPLATE, table=table, preview_sql=None, backup=backup)

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

# ------------------ END ------------------
# Note: register blueprint in your flask_app: app.register_blueprint(adminer_bp)
# Example:
#   from adminer import adminer_bp
#   app.register_blueprint(adminer_bp)
#
# Security note: add @login_required or proper checks in production.
