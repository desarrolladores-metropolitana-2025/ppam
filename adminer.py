from flask import Blueprint, render_template_string, request, redirect, url_for
from extensiones import db
from modelos import *

adminer_bp = Blueprint("adminer", __name__)
@adminer_bp.app_template_filter('getattr')
def jinja_getattr(obj, attr):
    return getattr(obj, attr)


MODELS = {
    "publicadores": Publicador,
    "puntos_predicacion": PuntoPredicacion,
    "solicitudes_turno": SolicitudTurno,
    "experiencias": Experiencia,
    "ausencias": Ausencia,
    "turnos": Turno
}

LIST_TEMPLATE = """
<style>
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

    <a class="new-btn" href="{{ url_for('adminer.new_record', table=table) }}">➕ Nuevo Registro</a>

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


@adminer_bp.route("/")
def index():
    INDEX_TEMPLATE = """
    <style>
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
        <a href="/adminer/table/{{ t }}">
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
    model = MODELS[table]
    rows = model.query.all()
    columns = [c.name for c in model.__table__.columns]
    return render_template_string(LIST_TEMPLATE, table=table, rows=rows, columns=columns)

@adminer_bp.route("/table/<table>/new", methods=["GET", "POST"])
def new_record(table):
    model = MODELS[table]
    columns = [c.name for c in model.__table__.columns if c.name != "id"]

    if request.method == "POST":
        data = {col: request.form[col] for col in columns}
        obj = model(**data)
        db.session.add(obj)
        db.session.commit()
        return redirect(url_for("adminer.table_view", table=table))

    return render_template_string(FORM_TEMPLATE, action="Nuevo", table=table, columns=columns, values={})

@adminer_bp.route("/table/<table>/edit/<int:id>", methods=["GET", "POST"])
def edit_record(table, id):
    model = MODELS[table]
    obj = model.query.get(id)
    columns = [c.name for c in model.__table__.columns if c.name != "id"]

    if request.method == "POST":
        for col in columns:
            setattr(obj, col, request.form[col])
        db.session.commit()
        return redirect(url_for("adminer.table_view", table=table))

    values = {col: getattr(obj, col) for col in columns}
    return render_template_string(FORM_TEMPLATE, action="Editar", table=table, columns=columns, values=values)

@adminer_bp.route("/table/<table>/delete/<int:id>")
def delete_record(table, id):
    model = MODELS[table]
    obj = model.query.get(id)
    db.session.delete(obj)
    db.session.commit()
    return redirect(url_for("adminer.table_view", table=table))
