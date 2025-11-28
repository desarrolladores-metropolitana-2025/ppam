# flask_app.py
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from modelos import (
    Publicador,
    PuntoPredicacion,
    Turno,
    SolicitudTurno,
    Experiencia,
    Ausencia
)

from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, timedelta, date, time
from sqlalchemy import func
# from turnos import api
from turnos import bp_turnos
from postulantes import bp_post
from BotAsignador import bot_api, BotAsignador
from planificacion import planificacion_bp
from adminer import adminer_bp
from navegador import navegador_bp

# -------------------------------------------
# Singletons de extensiones
# -------------------------------------------
from extensiones import db, login_manager


# -------------------------------------------
# App
# -------------------------------------------
dotenv_path = os.path.join(os.path.dirname(__file__), "var.env")
load_dotenv(dotenv_path)

NOMBRE_CUENTA = os.getenv("NOMBRE_CUENTA")
PASSWORD_DB = os.getenv("PASSWORD_DB")
INSTANCIA = os.getenv("INSTANCIA")
SECRET_KEY = os.getenv("SECRET_KEY")

app = Flask(__name__)
app.config['FILEBROWSER_ROOT'] = '/home/ppamappcaba/mysite'  
app.register_blueprint(bp_turnos)
app.register_blueprint(bp_post)
app.register_blueprint(bot_api)
app.register_blueprint(planificacion_bp)
app.register_blueprint(adminer_bp, url_prefix="/adminer")
app.register_blueprint(navegador_bp, url_prefix="/navegador")
if __name__ == "__main__":
    app.run(debug=True)
# --- Registro de Blueprints ---
# app.register_blueprint(api)
# app.re gister_blueprint(bp_puntos)
app.config["DEBUG"] = True
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+mysqlconnector://{NOMBRE_CUENTA}:{PASSWORD_DB}"
    f"@{NOMBRE_CUENTA}.mysql.pythonanywhere-services.com/{NOMBRE_CUENTA}${INSTANCIA}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
}


db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"


# -------------------------------------------
# LOGIN MANAGER
# -------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return Publicador.query.get(int(user_id))


#---------------FUNCIONES GENERALES--------------
def time_to_str(t):
    return t.strftime("%H:%M") if t else ""



# -------------------------------------------
# RUTAS
# -------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = Publicador.query.filter_by(usuario=username).first()
        if user and user.check_password(password):
            login_user(user, remember=("remember" in request.form))
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        else:
            error = True
            flash("Usuario o contraseña incorrectos", "danger")
    return render_template("login_page.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada", "info")
    return redirect(url_for("login"))


@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.rol == "Admin" :
            return redirect(url_for("main_page"))
        else:
            return redirect(url_for("pubview"))
    return redirect(url_for("login"))


@app.route("/main")
@login_required
def main_page():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    return render_template("main_page.html", current_user=current_user)

# Nuevo endpoint para el planificador interactivo:
@app.route("/weekplan/")
def weekplan():
    return render_template("weekplan/index.html")
    
@app.route("/api/bot/asignar_rango", methods=["POST"])
def api_bot_asignar_rango():
    data = request.get_json() or {}
    f1 = data.get("fecha_desde")
    f2 = data.get("fecha_hasta")

    if not f1 or not f2:
        return jsonify({"ok": False, "error": "Faltan fechas"}), 400

    try:
        desde = datetime.strptime(f1, "%Y-%m-%d").date()
        hasta = datetime.strptime(f2, "%Y-%m-%d").date()
    except Exception:
        return jsonify({"ok": False, "error": "Fechas inválidas"}), 400

    # acá llamamos al BotAsignador
    
    bot = BotAsignador()

    resultado = bot.ejecutar({
        "mode": "rango",
        "fecha_desde": f1,
        "fecha_hasta": f2
    })

    return jsonify(resultado)



# PAGINA DE ERRORES:


import traceback



# MANEJADOR ESPECÍFICO PARA 403 (PERMISOS)
@app.errorhandler(403)
def handle_forbidden(e):
    return render_template("error_403.html", mensaje="No tenés permisos para acceder a esta función."), 403



@app.errorhandler(Exception)
def handle_exception(e):
    # Extraer el traceback como string
    tb = traceback.format_exc()

    # Podés quedarte con solo las últimas líneas (las más útiles)
    tb_resumido = "\n".join(tb.strip().splitlines()[-50:])  # últimas 50 líneas

    # Si es el error de MySQL desconectado:
    #if "MySQL Connection not available" in str(e):
     #   return render_template("error_conexion.html", log=tb_resumido), 500



    # Para cualquier otro error
    return render_template("error_general.html", log=tb_resumido), 500




# -------------------- CRUD PUBLICADORES --------------------
@app.route("/publicadores")
@login_required
def publicadores_index():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    publicadores = Publicador.query.all()
    return render_template("publicadores.html", publicadores=publicadores, publicador=None)


@app.route("/publicadores/guardar", methods=["POST"])
@login_required
def publicadores_guardar():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    id = request.form.get("id")
    nombre = request.form.get("nombre")
    apellido = request.form.get("apellido")
    mail = request.form.get("mail")
    congregacion = request.form.get("congregacion")
    circuito = request.form.get("circuito")
    usuario = request.form.get("usuario")
    celular = request.form.get("celular")
    rol = request.form.get("rol")
    password = request.form.get("password")
    principiante_bin = request.form.get("principiante")
    ultima_participacion_txt = request.form.get("ultima_participacion")   

    principiante = True if principiante_bin == "1" else False 
    ultima_participacion = None
    if ultima_participacion_txt:
        try:
            ultima_participacion = datetime.strptime(ultima_participacion_txt, "%Y-%m-%d").date()
        except ValueError:
            ultima_participacion = None    

    if id:
        pub = Publicador.query.get(int(id))
        if pub:
            pub.nombre = nombre
            pub.apellido = apellido
            pub.mail = mail
            pub.celular = celular
            pub.congregacion = congregacion
            pub.circuito = circuito
            pub.usuario = usuario
            pub.principiante = principiante
            pub.ultima_participacion = ultima_participacion
            if password:
                pub.password_hash = generate_password_hash(password,method="pbkdf2:sha256", salt_length=16)
            flash("Publicador actualizado", "success")
    else:
        pub = Publicador(
            nombre=nombre,
            apellido=apellido,
            mail=mail,
            congregacion=congregacion,
            circuito=circuito,
            celular=celular,
            usuario=usuario,
            rol=rol,
            principiante=principiante,
            ultima_participacion=ultima_participacion,
            password_hash=generate_password_hash(password,method="pbkdf2:sha256", salt_length=16),
        )
        db.session.add(pub)
        flash("Publicador creado", "success")
    db.session.commit()
    return redirect(url_for("publicadores_index"))


@app.route("/publicadores/editar/<int:id>")
@login_required
def publicadores_editar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    publicador = Publicador.query.get_or_404(id)
    publicadores = Publicador.query.all()
    return render_template("publicadores.html", publicadores=publicadores, publicador=publicador)


@app.route("/publicadores/eliminar/<int:id>")
@login_required
def publicadores_eliminar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    pub = Publicador.query.get_or_404(id)
    db.session.delete(pub)
    db.session.commit()
    flash("Publicador eliminado", "info")
    return redirect(url_for("publicadores_index"))


# -------------------- CRUD PUNTOS --------------------
@app.route("/puntos")
@login_required
def puntos_index():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    puntos = PuntoPredicacion.query.all()
    return render_template("puntos.html", puntos=puntos, punto=None,time_to_str=time_to_str)
@app.route("/api/puntos")
@login_required
def api_listar_puntos():
    puntos = PuntoPredicacion.query.all()

    data = []
    for p in puntos:
        data.append({
            "id": p.id,
            "nombre": p.punto_nombre,
            "direccion": p.direccion_deposito or "",
            "contacto": p.contacto_deposito or "",
            "telefono": p.telefono_deposito or ""
        })

    return jsonify(data)

@app.route("/puntos/guardar", methods=["POST"])
@login_required
def puntos_guardar():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    id = request.form.get("id")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")

    mismo_inicio = request.form.get("mismo_inicio") == "on"
    mismo_fin = request.form.get("mismo_fin") == "on"

    def to_time(val):
        if not val:
            return None
        parts = val.split(":")
        return time(int(parts[0]), int(parts[1]))

    data = {
        "punto_nombre": request.form.get("punto_nombre"),
        "fecha_inicio": datetime.strptime(fecha_inicio, "%Y-%m-%d").date() if fecha_inicio else None,
        "fecha_fin": datetime.strptime(fecha_fin, "%Y-%m-%d").date() if fecha_fin else None,
    }

    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    for dia in dias:
        inicio = request.form.get(f"{dia}_inicio")
        fin = request.form.get(f"{dia}_fin")

        if mismo_inicio and inicio:
            inicio_val = to_time(inicio)
            for d in dias:
                data[f"{d}_inicio"] = inicio_val
        else:
            data[f"{dia}_inicio"] = to_time(inicio)

        if mismo_fin and fin:
            fin_val = to_time(fin)
            for d in dias:
                data[f"{d}_fin"] = fin_val
        else:
            data[f"{dia}_fin"] = to_time(fin)

    data["duracion_turno"] = request.form.get("duracion_turno")
    data["direccion_deposito"] = request.form.get("direccion_deposito")
    data["contacto_deposito"] = request.form.get("contacto_deposito")
    data["telefono_deposito"] = request.form.get("telefono_deposito")

    if id:
        punto = PuntoPredicacion.query.get(int(id))
        for key, val in data.items():
            setattr(punto, key, val)
        msg = "Punto de predicación actualizado"
    else:
        punto = PuntoPredicacion(**data)
        db.session.add(punto)
        msg = "Punto de predicación creado"

    db.session.commit()
    flash(msg, "success")
    return redirect(url_for("puntos_index",time_to_str=time_to_str))


@app.route("/puntos/editar/<int:id>")
@login_required
def puntos_editar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    punto = PuntoPredicacion.query.get_or_404(id)
    puntos = PuntoPredicacion.query.all()
    return render_template("puntos.html", puntos=puntos, punto=punto,time_to_str=time_to_str)


@app.route("/puntos/eliminar/<int:id>")
@login_required
def puntos_eliminar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    punto = PuntoPredicacion.query.get_or_404(id)
    db.session.delete(punto)
    db.session.commit()
    flash("Punto eliminado", "info")
    return redirect(url_for("puntos_index"))


# -------------------- CRUD SOLICITUDES --------------------
@app.route("/solicitudes")
@login_required
def solicitudes_index():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    solicitudes = SolicitudTurno.query.all()
    publicadores = Publicador.query.all()
    puntos = PuntoPredicacion.query.all()
    return render_template(
        "solicitudes.html",
        solicitudes=solicitudes,
        solicitud=None,
        publicadores=publicadores,
        puntos=puntos,
    )

@app.route("/solicitudes/guardar", methods=["POST"])
@login_required
def solicitudes_guardar():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    id = request.form.get("id")
    punto_id = request.form.get("punto_id")
    publicador_id = request.form.get("publicador_id")
    frecuencia = request.form.get("frecuencia")
    dia = request.form.get("dia")

    def to_time(val):
        if not val:
            return None
        parts = val.split(":")
        if len(parts) >= 2:
            return time(int(parts[0]), int(parts[1]))
        return None

    hora_inicio = to_time(request.form.get("hora_inicio"))
    hora_fin = to_time(request.form.get("hora_fin"))
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    prioridad = int(request.form.get("prioridad") or 1)

    data = {
        "punto_id": int(punto_id),
        "publicador_id": int(publicador_id),
        "frecuencia": frecuencia,
        "dia": dia,
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "prioridad": prioridad,
    }

    if id:  # edición
        solicitud = SolicitudTurno.query.get(int(id))
        for key, val in data.items():
            setattr(solicitud, key, val)
        msg = "Solicitud de turno actualizada"
    else:  # nueva
        solicitud = SolicitudTurno(**data)
        db.session.add(solicitud)
        msg = "Solicitud de turno creada"

    db.session.commit()
    flash(msg, "success")
    return redirect(url_for("solicitudes_index"))



@app.route("/solicitudes/editar/<int:id>")
@login_required
def solicitudes_editar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    solicitud = SolicitudTurno.query.get_or_404(id)
    solicitudes = SolicitudTurno.query.all()
    publicadores = Publicador.query.all()
    puntos = PuntoPredicacion.query.all()
    return render_template(
        "solicitudes.html", solicitudes=solicitudes, solicitud=solicitud, publicadores=publicadores, puntos=puntos
    )


@app.route("/solicitudes/eliminar/<int:id>")
@login_required
def solicitudes_eliminar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    solicitud = SolicitudTurno.query.get_or_404(id)
    db.session.delete(solicitud)
    db.session.commit()
    flash("Solicitud eliminada", "info")
    return redirect(url_for("solicitudes_index"))


# -------------------------
# LISTAR SOLICITUDES
# -------------------------
@app.route("/api/solicitudez", methods=["GET"])
def api_listar_solicitudes():
    solicitudes = SolicitudTurno.query.all()

    data = []
    for s in solicitudes:
        data.append({
            "id": s.id,
            "punto": s.punto.punto_nombre if s.punto else "",
            "fecha": str(s.hora_inicio) + " - " + str(s.hora_fin),
            "usuario": s.publicador.nombre + " " + s.publicador.apellido if s.publicador else "",
            "rol": s.frecuencia,
            "estado": "Activa"
        })

    return jsonify(data)


# -------------------------
# CREAR SOLICITUD
# -------------------------
@app.route("/api/solicitudez", methods=["POST"])
def api_crear_solicitud():
    punto_id = request.form.get("punto_id")
    rol = request.form.get("rol")

    nueva = SolicitudTurno(
        punto_id=punto_id,
        publicador_id=current_user.id,
        frecuencia=rol,
        hora_inicio="08:00",
        hora_fin="10:00",
        dia="lunes"
    )

    db.session.add(nueva)
    db.session.commit()

    return jsonify({"ok": True})


# -------------------------
# ELIMINAR SOLICITUD
# -------------------------
@app.route("/api/solicitudez/<int:id>", methods=["DELETE"])
def api_eliminar_solicitud(id):
    s = SolicitudTurno.query.get(id)
    if not s:
        return jsonify({"ok": False, "error": "No existe"}), 404

    db.session.delete(s)
    db.session.commit()

    return jsonify({"ok": True})
    
@app.route("/api/notificaciones/enviar", methods=["POST"])
@login_required
def api_enviar_notificaciones():
    if current_user.rol != "Admin":
        return jsonify({"ok": False, "error": "No autorizado"}), 403

    try:
        hoy = date.today()

        # buscar turnos desde hoy
        turnos = Turno.query.filter(Turno.fecha >= hoy).order_by(Turno.fecha.asc()).all()

        if not turnos:
            return jsonify({"ok": True, "msj": "No hay turnos para notificar."})

        enviados = 0
        errores = []

        for t in turnos:
            try:
                enviar_notificacion_turno(t)
                enviados += 1
            except Exception as e:
                errores.append(str(e))

        return jsonify({
            "ok": True,
            "enviados": enviados,
            "errores": errores,
            "msj": f"Proceso finalizado. Turnos procesados: {enviados}"
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": f"Error general: {str(e)}"
        }), 500


# ------------------------------------------- FIN NOTIFICACIONES -------------------------------------------------



def date_to_str(d):
    return d.strftime("%Y-%m-%d") if d else ""



@app.route("/experiencias")
@login_required
def experiencias_index():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    experiencias = Experiencia.query.all()
    publicadores = Publicador.query.all()
    puntos = PuntoPredicacion.query.all()
    return render_template(
        "experiencias.html",
        experiencias=experiencias,
        publicadores=publicadores,
        puntos=puntos,
        experiencia=None,
        date_to_str=date_to_str,
    )

@app.route("/experiencias/guardar", methods=["POST"])
@login_required
def experiencias_guardar():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    id = request.form.get("id")
    publicador_id = request.form.get("publicador_id")
    punto_id = request.form.get("punto_id")
    fecha_str = request.form.get("fecha")
    notas = request.form.get("notas")
    is_public = request.form.get("is_public") == "on"

    fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else None

    if id:
        exp = Experiencia.query.get(int(id))
        if exp:
            exp.publicador_id = publicador_id
            exp.punto_id = punto_id
            exp.fecha = fecha
            exp.notas = notas
            exp.is_public = is_public
            flash("Experiencia actualizada", "success")
    else:
        exp = Experiencia(
            publicador_id=publicador_id,
            punto_id=punto_id,
            fecha=fecha,
            notas=notas,
            is_public=is_public,
        )
        db.session.add(exp)
        flash("Experiencia creada", "success")

    db.session.commit()

    experiencias = Experiencia.query.all()
    publicadores = Publicador.query.all()
    puntos = PuntoPredicacion.query.all()
    return render_template(
        "experiencias.html",
        experiencias=experiencias,
        publicadores=publicadores,
        puntos=puntos,
        experiencia=exp,
        date_to_str=date_to_str,
    )

@app.route("/experiencias/editar/<int:id>")
@login_required
def experiencias_editar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    exp = Experiencia.query.get_or_404(id)
    experiencias = Experiencia.query.all()
    publicadores = Publicador.query.all()
    puntos = PuntoPredicacion.query.all()
    return render_template(
        "experiencias.html",
        experiencias=experiencias,
        publicadores=publicadores,
        puntos=puntos,
        experiencia=exp,
        date_to_str=date_to_str,
    )

@app.route("/experiencias/eliminar/<int:id>")
@login_required
def experiencias_eliminar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    exp = Experiencia.query.get_or_404(id)
    db.session.delete(exp)
    db.session.commit()
    flash("Experiencia eliminada", "info")
    return redirect(url_for("experiencias_index"))

#------------------------------AUSENCIAS-----------------------------------------------------




@app.route("/ausencias")
@login_required
def ausencias_index():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    ausencias = Ausencia.query.all()
    publicadores = Publicador.query.all()
    return render_template("ausencias.html", ausencias=ausencias, publicadores=publicadores, ausencia=None)


@app.route("/ausencias/guardar", methods=["POST"])
@login_required
def ausencias_guardar():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")

    id = request.form.get("id")
    publicador_id = request.form.get("publicador_id")
    fecha_inicio = request.form.get("fecha_inicio")
    fecha_fin = request.form.get("fecha_fin")
    motivo = request.form.get("motivo")

    data = {
        "publicador_id": int(publicador_id),
        "fecha_inicio": datetime.strptime(fecha_inicio, "%Y-%m-%d").date() if fecha_inicio else None,
        "fecha_fin": datetime.strptime(fecha_fin, "%Y-%m-%d").date() if fecha_fin else None,
        "motivo": motivo,
    }

    if id:
        ausencia = Ausencia.query.get(int(id))
        for key, val in data.items():
            setattr(ausencia, key, val)
        flash("Ausencia actualizada", "success")
    else:
        ausencia = Ausencia(**data)
        db.session.add(ausencia)
        flash("Ausencia creada", "success")

    db.session.commit()
    return redirect(url_for("ausencias_index"))


@app.route("/ausencias/editar/<int:id>")
@login_required
def ausencias_editar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    ausencia = Ausencia.query.get_or_404(id)
    ausencias = Ausencia.query.all()
    publicadores = Publicador.query.all()
    return render_template("ausencias.html", ausencias=ausencias, publicadores=publicadores, ausencia=ausencia)


@app.route("/ausencias/eliminar/<int:id>")
@login_required
def ausencias_eliminar(id):
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    ausencia = Ausencia.query.get_or_404(id)
    db.session.delete(ausencia)
    db.session.commit()
    flash("Ausencia eliminada", "info")
    return redirect(url_for("ausencias_index"))



#----------------------CONFIGURACION---------------------------------------------------------------------------------

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default = {
            "turnos_consecutivos": False,
            "dos_turnos_mismo_dia": False,
            "validar_ausencias": True,
            # Nuevos campos de alertas
            "alerta_dos_turnos": "",
            "alerta_sin_capitan": "advertencia",
            "alerta_sin_publicadores": "advertencia",
            "alerta_un_publicador": "alerta",
            "min_publicadores": 2
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(default, f, indent=4)
        return default

    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)

    # Aseguramos que existan todos los campos nuevos aunque el config.json sea viejo
    defaults = {
        "alerta_dos_turnos": "",
        "alerta_sin_capitan": "advertencia",
        "alerta_sin_publicadores": "advertencia",
        "alerta_un_publicador": "alerta",
        "min_publicadores": 2
    }
    for k, v in defaults.items():
        if k not in data:
            data[k] = v

    return data

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ------------------------------
# Rutas de configuración
# ------------------------------
# ------------------------------
# Rutas de configuración
# ------------------------------
@app.route("/configuracion", methods=["GET", "POST"])
@login_required
def configuracion():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    config = load_config()

    # Asegurarse de que los nuevos campos existan
    if "alerta_dos_turnos" not in config:
        config["alerta_dos_turnos"] = ""
    if "alerta_sin_capitan" not in config:
        config["alerta_sin_capitan"] = ""
    if "alerta_sin_publicadores" not in config:
        config["alerta_sin_publicadores"] = ""
    if "alerta_un_publicador" not in config:
        config["alerta_un_publicador"] = ""
    if "min_publicadores" not in config:
        config["min_publicadores"] = 2

    if request.method == "POST":
        # Obtenemos valores del formulario
        config["turnos_consecutivos"] = request.form.get("turnos_consecutivos") == "on"
        config["dos_turnos_mismo_dia"] = request.form.get("dos_turnos_mismo_dia") == "on"
        config["validar_ausencias"] = request.form.get("validar_ausencias") == "on"

        # Nuevas opciones
        config["alerta_dos_turnos"] = request.form.get("alerta_dos_turnos", "")
        config["alerta_sin_capitan"] = request.form.get("alerta_sin_capitan", "")
        config["alerta_sin_publicadores"] = request.form.get("alerta_sin_publicadores", "")
        config["alerta_un_publicador"] = request.form.get("alerta_un_publicador", "")
        try:
            config["min_publicadores"] = int(request.form.get("min_publicadores", 2))
        except ValueError:
            config["min_publicadores"] = 2

        save_config(config)
        flash("Configuración guardada correctamente.", "success")
        return redirect(url_for("configuracion"))

    return render_template("configuracion.html", config=config)


@app.route("/api/config/list", methods=["GET"])
@login_required
def api_config_list():
    if current_user.rol != "Admin":
        return jsonify({"ok": False, "error": "Sin permisos"}), 403

    cfg = load_config()
    configuraciones = []

    # convertimos el dict en lista de objetos (idéntico a tu frontend)
    for clave, valor in cfg.items():
        configuraciones.append({
            "id": clave,            # clave será el identificador
            "seccion": "general",
            "clave": clave,
            "tipo": type(valor).__name__,
            "valor": valor
        })

    return jsonify({"ok": True, "configuraciones": configuraciones})
    
@app.route("/api/config/save", methods=["POST"])
@login_required
def api_config_save():
    if current_user.rol != "Admin":
        return jsonify({"ok": False, "error": "Sin permisos"}), 403

    key = request.form.get("id")
    valor = request.form.get("valor")

    if not key:
        return jsonify({"ok": False, "error": "Falta clave"}), 400

    cfg = load_config()

    if key not in cfg:
        return jsonify({"ok": False, "error": "Clave inexistente"}), 404

    # convertir tipo automáticamente
    actual = cfg[key]

    if isinstance(actual, bool):
        valor = valor.lower() in ("1", "true", "on", "si")
    elif isinstance(actual, int):
        try:
            valor = int(valor)
        except:
            return jsonify({"ok": False, "error": "Debe ser numérico"})
    # strings ya están OK

    cfg[key] = valor
    save_config(cfg)

    return jsonify({"ok": True})

#*************************** ESTADISTICAS ************************************************************************
@app.route("/api/estadisticas")
@login_required
def api_estadisticas():
    if current_user.rol != "Admin":
        return jsonify({"ok": False, "error": "Sin permisos"}), 403

    hoy = date.today()

    data = {
        "publicadores": db.session.query(func.count(Publicador.id)).scalar(),
        "puntos": db.session.query(func.count(PuntoPredicacion.id)).scalar(),
        "turnos_totales": db.session.query(func.count(Turno.id)).scalar(),
        "turnos_hoy": db.session.query(func.count(Turno.id)).filter(Turno.fecha == hoy).scalar(),
        "solicitudes_pendientes": db.session.query(func.count(SolicitudTurno.id)).scalar(),
        "experiencias": db.session.query(func.count(Experiencia.id)).scalar(),
        "ausencias_vigentes": db.session.query(func.count(Ausencia.id))
            .filter(Ausencia.fecha_inicio <= hoy, Ausencia.fecha_fin >= hoy)
            .scalar()
    }

    return jsonify({"ok": True, "data": data})

#********************TURNOS------*********************************************************************************


@app.route("/turnos")
@login_required
def turnos_index():

    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    config = load_config()
    puntos = PuntoPredicacion.query.all()
    publicadores = Publicador.query.all()
    turnos = {}

    # Obtener semana actual o pasada por parámetro
    week_start_str = request.args.get("week_start")
    if week_start_str:
        week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # lunes de la semana actual

    week_end = week_start + timedelta(days=6)

    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

    for punto in puntos:
        turnos[punto.id] = {}

        for i, dia in enumerate(dias):
            fecha_dia = week_start + timedelta(days=i)
            if punto.fecha_inicio and fecha_dia < punto.fecha_inicio:
                continue
            if punto.fecha_fin and fecha_dia > punto.fecha_fin:
                continue

            inicio_attr = f"{dia}_inicio"
            fin_attr = f"{dia}_fin"
            hora_inicio = getattr(punto, inicio_attr)
            hora_fin = getattr(punto, fin_attr)
            duracion = punto.duracion_turno or 60

            if not hora_inicio or not hora_fin:
                continue

            turnos[punto.id][dia] = []

            current = datetime.combine(fecha_dia, hora_inicio)
            end_time = datetime.combine(fecha_dia, hora_fin)

            while current < end_time:
                turno = Turno.query.filter_by(
                    punto_id=punto.id,
                    dia=dia,
                    hora_inicio=current.time(),
                    fecha=fecha_dia
                ).first()

                if not turno:
                    # Crear turno y guardar en DB
                    turno = Turno(
                        punto_id=punto.id,
                        dia=dia,
                        fecha=fecha_dia,
                        hora_inicio=current.time(),
                        hora_fin=(current + timedelta(minutes=duracion)).time()
                    )
                    db.session.add(turno)
                    db.session.commit()

                turno_dict = {
                    "id": turno.id,
                    "dia": turno.dia,
                    "fecha": turno.fecha,
                    "hora_inicio": turno.hora_inicio,
                    "hora_fin": turno.hora_fin,
                    "publicador1_id": turno.publicador1_id,
                    "publicador2_id": turno.publicador2_id,
                    "publicador3_id": turno.publicador3_id,
                    "publicador4_id": turno.publicador4_id,
                    "capitan_id": turno.capitan_id
                }

                turnos[punto.id][dia].append(turno_dict)
                current += timedelta(minutes=duracion)

    # URLs para semana anterior y siguiente
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)

    prev_week_url = url_for('turnos_index', week_start=prev_week.strftime('%Y-%m-%d'))
    next_week_url = url_for('turnos_index', week_start=next_week.strftime('%Y-%m-%d'))

    return render_template(
        "turnos.html",
        config=config,
        puntos=puntos,
        publicadores=publicadores,
        turnos=turnos,
        week_start=week_start,
        week_end=week_end,
        prev_week=prev_week,
        next_week=next_week,
        prev_week_url=prev_week_url,
        next_week_url=next_week_url
    )


@app.route("/turnos/guardar", methods=["POST"])
@login_required
def turnos_guardar():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")


    punto_id = request.form.get("punto_id", type=int)
    accion = request.form.get("accion")  # "guardar", "validar", "autocompletar"
    week_start = request.form.get("week_start")

    # Convertir la fecha de inicio de semana
    fecha_inicio = datetime.strptime(week_start, "%Y-%m-%d").date()
    fecha_fin = fecha_inicio + timedelta(days=6)

    # Filtrar solo los turnos del punto y de esa semana
    turnos = Turno.query.filter(
        Turno.punto_id == punto_id,
        Turno.fecha >= fecha_inicio,
        Turno.fecha <= fecha_fin
    ).all()

    if accion == "guardar":
        for t in turnos:
            for i in range(1, 5):
                pub_key = f"publicador{i}_{t.id}"
                valor = request.form.get(pub_key)
                setattr(t, f"publicador{i}_id", int(valor) if valor else None)
            cap_key = f"capitan_{t.id}"
            valor_cap = request.form.get(cap_key)
            t.capitan_id = int(valor_cap) if valor_cap else None
        db.session.commit()
        flash("Turnos guardados correctamente.", "success")

    elif accion == "validar":
        errores, advertencias, marcados = validar_turnos(turnos)  # ahora retorna también los ids marcados
        if errores:
            flash(f"Errores: {len(errores)}", "danger")
        if advertencias:
            flash(f"Advertencias: {len(advertencias)}", "warning")

    # Pasar info al template si querés mostrar nombres en colores
        return render_template(
            "turnos.html",
            turnos=turnos,
            marcados=marcados,   # para pintar en rojo/amarillo en el HTML
            punto_id=punto_id,
            week_start=week_start
            )




    elif accion == "autocompletar":
        total_vacantes, asignados, quedan = autocompletar_turnos(turnos)
        db.session.commit()
        flash(
            f"Vacantes: {total_vacantes}, Asignados: {asignados}, Quedan: {quedan}",
            "info",
        )

    return redirect(url_for("turnos_index", week_start=week_start))


def validar_turnos(turnos):
    """
    Valida los turnos según reglas de configuración.
    Devuelve tres valores:
      - errores: lista de mensajes críticos
      - advertencias: lista de mensajes leves
      - marcados: diccionario con IDs de publicadores afectados
    """
    from datetime import time

    config = load_config() or {}
    errores = []
    advertencias = []
    marcados = {"error": set(), "advertencia": set()}  # 👈 para colorear en HTML

    turnos_por_pub = {}

    for t in turnos:
        dia = t.dia
        publicadores = [
            t.publicador1_id,
            t.publicador2_id,
            t.publicador3_id,
            t.publicador4_id,
        ]
        llenos = [p for p in publicadores if p]

        # === 1. Validar capitán ===
        if not t.capitan_id:
            modo = config.get("turno_sin_capitan", "advertencia")
            msg = f"Turno {t.id} sin capitán"
            if modo == "alerta":
                errores.append(msg)
                marcados["error"].update(llenos)
            elif modo == "advertencia":
                advertencias.append(msg)
                marcados["advertencia"].update(llenos)

        # === 2. Validar cantidad de publicadores ===
        if len(llenos) == 0:
            modo = config.get("turno_sin_publicadores", "advertencia")
            msg = f"Turno {t.id} sin publicadores"
            if modo == "alerta":
                errores.append(msg)
            elif modo == "advertencia":
                advertencias.append(msg)

        elif len(llenos) == 1:
            modo = config.get("turno_un_publicador", "advertencia")
            msg = f"Turno {t.id} con un solo publicador"
            if modo == "alerta":
                errores.append(msg)
                marcados["error"].update(llenos)
            elif modo == "advertencia":
                advertencias.append(msg)
                marcados["advertencia"].update(llenos)

        # === 3. Validar cantidad mínima ===
        min_pub = int(config.get("cantidad_minima_por_turno", 2))
        if len(llenos) < min_pub:
            errores.append(f"Turno {t.id} no cumple la cantidad mínima ({len(llenos)}/{min_pub})")
            marcados["error"].update(llenos)
        elif len(llenos) == min_pub:
            advertencias.append(f"Turno {t.id} justo con la cantidad mínima de publicadores")
            marcados["advertencia"].update(llenos)

        # === 4. Registrar turnos para validar más adelante ===
        for p in llenos:
            turnos_por_pub.setdefault(p, {}).setdefault(dia, []).append(t)

    # === 5. Validar solapamientos y cantidad de turnos por día ===
    for pub, dias in turnos_por_pub.items():
        for dia, lista in dias.items():
            t_list = sorted(lista, key=lambda x: x.hora_inicio or time(0, 0))
            for i in range(len(t_list) - 1):
                t_actual = t_list[i]
                t_siguiente = t_list[i + 1]

                # Solapamiento o consecutivo
                if t_siguiente.hora_inicio <= t_actual.hora_fin:
                    if not config.get("turnos_consecutivos", False):
                        errores.append(f"Publicador {pub} tiene turnos consecutivos o solapados el {dia}")
                        marcados["error"].add(pub)

            # Cantidad máxima por día
            cant = len(t_list)
            permitir_dos = config.get("dos_turnos_mismo_dia", False)

            if not permitir_dos and cant > 1:
                errores.append(f"Publicador {pub} tiene más de un turno el {dia}")
                marcados["error"].add(pub)
            elif permitir_dos:
                if cant > 2:
                    errores.append(f"Publicador {pub} tiene más de 2 turnos el {dia}")
                    marcados["error"].add(pub)
                elif cant == 2:
                    advertencias.append(f"Publicador {pub} tiene 2 turnos el {dia} (advertencia)")
                    marcados["advertencia"].add(pub)

    return errores, advertencias, marcados





def autocompletar_turnos(turnos):
    if not turnos:
        return 0, 0, 0  # no hay nada que completar

    total_vacantes = 0
    asignados = 0

    solicitudes = SolicitudTurno.query.filter_by(prioridad=100).all()

    ausencias = Ausencia.query.all()

    # Mapeo de ausencias
    ausencias_por_publicador = {
        a.publicador_id: (a.fecha_inicio, a.fecha_fin) for a in ausencias
    }

    turnos_ordenados = sorted(turnos, key=lambda x: (x.fecha, x.hora_inicio))

    for t in turnos_ordenados:
        asignados_en_turno = {
            getattr(t, f"publicador{i}_id")
            for i in range(1, 5)
            if getattr(t, f"publicador{i}_id") is not None
        }

        for i in range(1, 5):
            campo_pub = f"publicador{i}_id"

            if getattr(t, campo_pub):
                continue

            total_vacantes += 1

            # Candidatos base
            candidatos = [
                s for s in solicitudes
                if s.punto_id == t.punto_id
                and s.dia == t.dia
                and s.hora_inicio <= t.hora_inicio
                and s.hora_fin >= t.hora_fin
                and s.fecha_inicio <= t.fecha
                and s.fecha_fin >= t.fecha
            ]

            candidatos_filtrados = []
            for s in candidatos:
                if s.frecuencia == "semanal":
                    candidatos_filtrados.append(s)
                elif s.frecuencia == "1mes" and t.fecha.day <= 7:
                    candidatos_filtrados.append(s)
                elif s.frecuencia == "2mes" and t.fecha.day in range(8, 15):
                    candidatos_filtrados.append(s)
                elif s.frecuencia == "3mes" and t.fecha.day in range(15, 22):
                    candidatos_filtrados.append(s)
                elif s.frecuencia == "4mes" and t.fecha.day in range(22, 29):
                    candidatos_filtrados.append(s)
                elif s.frecuencia == "5mes" and t.fecha.day >= 29:
                    candidatos_filtrados.append(s)


            candidatos_finales = []
            for s in candidatos_filtrados:
                if s.publicador_id in asignados_en_turno:
                    continue
                ausencia = ausencias_por_publicador.get(s.publicador_id)
                if ausencia:
                    inicio, fin = ausencia
                    if inicio <= t.fecha <= fin:
                        continue
                candidatos_finales.append(s)

            candidatos_finales.sort(key=lambda x: x.prioridad, reverse=True)

            if candidatos_finales:
                elegido = candidatos_finales[0]
                setattr(t, campo_pub, elegido.publicador_id)
                asignados_en_turno.add(elegido.publicador_id)
                asignados += 1

    quedan = total_vacantes - asignados
    return total_vacantes, asignados, quedan




#planificacion, pasa turnos a publicos y a privados






# --- RUTA: Planificación (mostrar) ---
@app.route("/planificacion")
@login_required
def planificacion_index():

    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")
    # Obtener week_start por query param (permite navegar entre semanas)
    week_start_str = request.args.get("week_start")
    if week_start_str:
        try:
            week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
        except Exception:
            week_start = date.today() - timedelta(days=date.today().weekday())
    else:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # lunes
    week_end = week_start + timedelta(days=6)

    puntos = PuntoPredicacion.query.all()
    publicadores = Publicador.query.all()
    pub_map = {p.id: {"nombre": f"{p.nombre} {p.apellido}"} for p in publicadores}

    # mapa turno_count: publicador_id -> cantidad de asignaciones esta semana
    turno_count = {p.id: 0 for p in publicadores}
    # mapa id -> "Nombre Apellido"
    pub_map = {p.id: f"{p.nombre} {p.apellido}".strip() for p in publicadores}

    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

    # Estructura final: { punto_id: { dia: [turno_dicts...] } }
    turnos_by_punto = {}

    # Traer todos los turnos de la semana para optimizar
    all_turnos = Turno.query.filter(Turno.fecha >= week_start, Turno.fecha <= week_end).all()
    for t in all_turnos:   # ya lo tenés
        for pid in [t.capitan_id, t.publicador1_id, t.publicador2_id, t.publicador3_id, t.publicador4_id]:
            if pid:
                turno_count[pid] += 1
    # hoy
    hoy = date.today()            
    # Agrupar por punto y por dia
    for punto in puntos:
        turnos_by_punto[punto.id] = {}
        # filtrar turnos de este punto
        t_punto = [t for t in all_turnos if t.punto_id == punto.id]
        for dia in dias:
            lista_dia = [t for t in t_punto if t.dia == dia]
            if not lista_dia:
                continue
            # ordenar por hora_inicio
            lista_dia.sort(key=lambda x: (x.fecha or date.min, x.hora_inicio or datetime.min.time()))
            turnos_list = []
            for t in lista_dia:
                # construir dict con nombres al lado
                d = {
                    "id": t.id,
                    "dia": t.dia,
                    "fecha": t.fecha,
                    "hora_inicio": t.hora_inicio,
                    "hora_fin": t.hora_fin,
                    "capitan_id": t.capitan_id,
                    "publicador1_id": t.publicador1_id,
                    "publicador2_id": t.publicador2_id,
                    "publicador3_id": t.publicador3_id,
                    "publicador4_id": t.publicador4_id,
                    "is_public": bool(t.is_public)
                }
                # nombres (si no existe el id, queda cadena vacía)
                d["capitan_nombre"] = pub_map.get(t.capitan_id, "")
                d["publicador1_nombre"] = pub_map.get(t.publicador1_id, "")
                d["publicador2_nombre"] = pub_map.get(t.publicador2_id, "")
                d["publicador3_nombre"] = pub_map.get(t.publicador3_id, "")
                d["publicador4_nombre"] = pub_map.get(t.publicador4_id, "")
                turnos_list.append(d)
            turnos_by_punto[punto.id][dia] = turnos_list

    # URLs para semana anterior y siguiente
    prev_week = week_start - timedelta(days=7)
    next_week = week_start + timedelta(days=7)
    prev_week_url = url_for("planificacion_index", week_start=prev_week.strftime("%Y-%m-%d"))
    next_week_url = url_for("planificacion_index", week_start=next_week.strftime("%Y-%m-%d"))
    
    
    turnos_semana = Turno.query.filter(
    Turno.fecha >= week_start,
    Turno.fecha <= week_end
    ).all()

    turnos_por_publicador = {}

    for t in turnos_semana:
        for pid in [
            t.publicador1_id,
            t.publicador2_id,
            t.publicador3_id,
            t.publicador4_id,
            t.capitan_id,
        ]:
            if pid:
                turnos_por_publicador.setdefault(pid, 0)
                turnos_por_publicador[pid] += 1
        
        
    ultimos_turnos = db.session.query(
        Turno.publicador1_id.label("pid"),
        Turno.fecha
    ).filter(Turno.publicador1_id != None)

    # repetir para publicador2/3/4/capitan si querés exacto

    # o alternativa rápida:
    ultima_participacion = {}
    for t in Turno.query.order_by(Turno.fecha.desc()).all():
        for pid in [
            t.publicador1_id, t.publicador2_id,
            t.publicador3_id, t.publicador4_id,
            t.capitan_id
        ]:
            if pid and pid not in ultima_participacion:
                ultima_participacion[pid] = t.fecha


    pub_info = {}
    for p in publicadores:
        cant = turnos_por_publicador.get(p.id, 0)
        fecha_ultima = ultima_participacion.get(p.id)
        semanas = None

        if fecha_ultima:
            semanas = (week_start - fecha_ultima).days // 7
        # días sin participar
        if p.ultima_participacion:
            dias_inactivo = (hoy - p.ultima_participacion).days
        else:
            dias_inactivo = 180  # nunca participó

        pub_info[p.id] = {
            "nombre": f"{p.nombre} {p.apellido}",
            "turnos_semana": turno_count.get(p.id, 0),
            "principiante": bool(getattr(p, "principiante", False)),
            "semanas_sin_participar": semanas,
            "inactivo": dias_inactivo > 120,
            "dias_inactivo": dias_inactivo
        }


    return render_template(
        "planificacion.html",
        puntos=puntos,
        publicadores=publicadores,
        turnos=turnos_by_punto,
        pub_map=pub_map,
        pub_info=pub_info,   
        week_start=week_start,
        week_end=week_end,
        prev_week=prev_week,
        next_week=next_week,
        prev_week_url=prev_week_url,
        next_week_url=next_week_url
    )


# --- RUTA: actualizar estado público/privado ---
@app.route("/planificacion/actualizar", methods=["POST"])
@login_required
def planificacion_actualizar():
    if current_user.rol != 'Admin':
        abort(403, description="No tenés permisos para acceder a esta función.")


    """
    Recibe:
      - punto_id
      - dia
      - turno_ids (lista de ids, puede venir vacía)
      - accion -> 'publicar' o 'privado'
      - opcional: week_start (para redirigir a la misma semana)
    """
    try:
        punto_id = int(request.form.get("punto_id"))
    except (TypeError, ValueError):
        flash("Punto inválido.", "danger")
        return redirect(url_for("planificacion_index"))

    accion = request.form.get("accion")
    turno_ids = request.form.getlist("turno_ids") or []
    week_start = request.form.get("week_start")

    # convertir a ints y filtrar valores no numéricos
    ids = []
    for s in turno_ids:
        try:
            ids.append(int(s))
        except Exception:
            continue

    if not ids:
        flash("No se seleccionaron turnos.", "warning")
        return redirect(url_for("planificacion_index", week_start=week_start) if week_start else url_for("planificacion_index"))

    # Obtener turnos por ids (y opcionalmente filtrar por punto_id para seguridad)
    turnos_query = Turno.query.filter(Turno.id.in_(ids))
    if punto_id:
        turnos_query = turnos_query.filter(Turno.punto_id == punto_id)

    turnos_a_modificar = turnos_query.all()

    if not turnos_a_modificar:
        flash("No se encontraron los turnos seleccionados.", "danger")
        return redirect(url_for("planificacion_index", week_start=week_start) if week_start else url_for("planificacion_index"))

    cambios = 0
    for t in turnos_a_modificar:
        if accion == "publicar":
            if not t.is_public:
                t.is_public = True
                cambios += 1
                # ENVIAR MAIL AUTOMÁTICAMENTE
                try:
                    enviar_notificacion_turno(t)
                except Exception as e:
                    print(f"❌ Error enviando mail para turno {t.id}: {e}")
                # FIN MAIL AUTOMATICO
        elif accion == "privado":
            if t.is_public:
                t.is_public = False
                cambios += 1
        # si llega otra accion, la ignoramos (podrías agregar manejo)

    db.session.commit()
    flash(f"{cambios} turno(s) actualizados.", "success")

    return redirect(url_for("planificacion_index", week_start=week_start) if week_start else redirect(url_for("planificacion_index")))



###ENVIO DE MAILS


from flask_mail import Mail, Message

# Configuración de Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_DEFAULT_SENDER'] = 'ppamappcaba@gmail.com'
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'ppamappcaba@gmail.com'
app.config['MAIL_PASSWORD'] = 'ddbg ssvz pinf klsz'
app.config['MAIL_DEBUG'] = True
app.config['MAIL_SUPPRESS_SEND'] = False  # asegurarse de enviar mails
mail = Mail(app)


def enviar_notificacion_turno(turno):
    """
    Envía mail a todos los assigned (capitán + publicadores) del turno.
    Añade en BCC la casilla ppamappcaba@gmail.com.
    """
    try:
        # obtener punto
        punto = PuntoPredicacion.query.get(turno.punto_id)
        punto_nombre = punto.punto_nombre if punto else f"Punto {turno.punto_id}"
        print(f"[DEBUG] Punto seleccionado: {punto_nombre}")

        # IDs de publicadores asignados (filter None)
        pub_ids = [
            turno.capitan_id,
            turno.publicador1_id,
            turno.publicador2_id,
            turno.publicador3_id,
            turno.publicador4_id,
        ]
        pub_ids = [p for p in pub_ids if p]
        print(f"[DEBUG] IDs de publicadores: {pub_ids}")

        if not pub_ids:
            print("[INFO] No hay publicadores asignados. Se omite el envío.")
            return

        # traer publicadores y sus mails
        publicadores = Publicador.query.filter(Publicador.id.in_(pub_ids)).all()
        destinatarios = []
        listado_nombres = []
        for p in publicadores:
            listado_nombres.append(f"{p.nombre} {p.apellido}".strip())
            if p.mail:
                destinatarios.append(p.mail)
        print(f"[DEBUG] Destinatarios con mail válido: {destinatarios}")

        if not destinatarios:
            print("[INFO] No hay emails válidos. Se omite el envío.")
            return

        # armar asunto y cuerpo
        fecha = turno.fecha.strftime("%d-%m-%Y") if turno.fecha else ""
        hora_inicio = turno.hora_inicio.strftime("%H:%M") if turno.hora_inicio else ""
        hora_fin = turno.hora_fin.strftime("%H:%M") if turno.hora_fin else ""
        asunto = f"PPAM - Nuevo turno publicado en {punto_nombre} ({fecha} {hora_inicio}-{hora_fin})"

        cuerpo = f"""Hola,

Se ha publicado el siguiente turno:

Punto: {punto_nombre}
Fecha: {fecha}
Horario: {hora_inicio} - {hora_fin}

Asignados:
{chr(10).join(['- ' + n for n in listado_nombres])}

Gracias,
PPAM App
"""

        print("----- Mail a enviar -----")
        print("Asunto:", asunto)
        print("Destinatarios:", destinatarios)
        print("BCC:", ["ppamappcaba@gmail.com"])
        print("Cuerpo:", cuerpo)
        print("-------------------------")

        # crear mensaje
        msg = Message(
            subject=asunto,
            sender=("PPAM App", app.config.get("MAIL_USERNAME")),
            recipients=destinatarios,
            bcc=["ppamappcaba@gmail.com"],
            body=cuerpo
        )

        # enviar mail
        mail.send(msg)
        print(f"✅ Mail enviado correctamente a {destinatarios}")

    except Exception as e:
        print(f"❌ ERROR enviando mail: {e}")





# -------------------------------------------

# -------------------- Otros --------------------




@app.route("/capitanes")
@login_required
def capitanes_index():
    return redirect(url_for("main_page"))




#----------------VISTA DEL PUBLICADOR---------------------------------------------------------------------------------------------






@app.route('/pubview')
@login_required
def pubview():
    user = current_user
    hoy = date.today()
    # --- Turnos asignados al usuario ---
    turnos = Turno.query.filter(
    (
        (Turno.publicador1_id == user.id) |
        (Turno.publicador2_id == user.id) |
        (Turno.publicador3_id == user.id) |
        (Turno.publicador4_id == user.id) |
        (Turno.capitan_id == user.id)
    )
    & (Turno.is_public == True)
    & (Turno.fecha >= hoy)
    ).all()

    # --- Experiencias ---
    experiencias = Experiencia.query.filter_by(is_public=True).all()

    # --- Todos los puntos ---
    puntos = PuntoPredicacion.query.all()


    # --- Solicitudes y ausencias del usuario ---
    solicitudes_turno = SolicitudTurno.query.filter_by(publicador_id=user.id).all()
    ausencias = Ausencia.query.filter_by(publicador_id=user.id).all()

    # --- Reemplazos: turnos publicos con vacantes en el futuro ---
    turnos_publicos = Turno.query.filter(Turno.is_public==True).order_by(Turno.fecha.asc()).all()
    reemplazos = []

    for t in turnos_publicos:
        # Solo futuros
        if t.fecha >= hoy:
            # Contar cuántos publicadores ya están asignados
            ocupados = sum(1 for p in [t.publicador1_id, t.publicador2_id, t.publicador3_id, t.publicador4_id] if p)
            vacantes = 4 - ocupados
            if vacantes > 0:
                reemplazos.append({
                    "id": t.id,
                    "punto_nombre": t.punto.punto_nombre if t.punto else "Sin punto",
                    "dia": t.fecha,
                    "hora_inicio": t.hora_inicio,
                    "hora_fin": t.hora_fin,
                    "vacantes": vacantes
                })

    return render_template(
        'pubview.html',
        user=user,
        turnos=turnos,
        experiencias=experiencias,
        puntos=puntos,
        hoy=hoy,
        solicitudes_turno=solicitudes_turno,
        ausencias=ausencias,
        reemplazos=reemplazos
    )

# NUEVO TURNO FIJO
@app.route("/nuevo_turno_fijo", methods=["POST"])
@login_required
def nuevo_turno_fijo():
    data = request.form
    nuevo = SolicitudTurno(
        punto_id=data["punto_id"],
        hora_inicio=data["hora_inicio"],
        hora_fin=data["hora_fin"],
        fecha_inicio = "2000-01-01",
        fecha_fin = "9999-01-01" ,
        prioridad=data.get("prioridad", 1),
        publicador_id=current_user.id,
        frecuencia=data["frecuencia"],
        dia=data["dia"]
    )
    db.session.add(nuevo)
    db.session.commit()
    flash("Solicitud de turno creada correctamente.")
    return redirect(url_for("pubview"))


# NUEVA AUSENCIA
@app.route("/nueva_ausencia", methods=["POST"])
@login_required
def nueva_ausencia():
    data = request.form
    nueva = Ausencia(
        publicador_id=current_user.id,
        fecha_inicio=data["fecha_inicio"],
        fecha_fin=data["fecha_fin"],
        motivo=data["motivo"]
    )
    db.session.add(nueva)
    db.session.commit()
    flash("Ausencia registrada.")
    return redirect(url_for("pubview"))


# NUEVA EXPERIENCIA (privada)
@app.route("/nueva_experiencia", methods=["POST"])
@login_required
def nueva_experiencia():
    data = request.form
    exp = Experiencia(
        publicador_id=current_user.id,
        punto_id=data["punto_id"],
        fecha=data["fecha"],
        notas=data["notas"],
        is_public=False
    )
    db.session.add(exp)
    db.session.commit()
    flash("Experiencia agregada.")
    return redirect(url_for("pubview"))


# PERFIL


@app.route("/mi_perfil", methods=["GET", "POST"])
@login_required
def mi_perfil():
    if request.method == "POST":
        # Campos editables
        mail = request.form.get("mail", "").strip()
        congregacion = request.form.get("congregacion", "").strip()
        circuito = request.form.get("circuito", "").strip()
        celular = request.form.get("celular", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        # Validaciones de contraseña
        if password or password_confirm:
            if password != password_confirm:
                flash("Las contraseñas no coinciden. Intente nuevamente", "danger")
                return redirect(url_for("pubview"))

            if len(password) < 6:
                flash("La contraseña debe tener al menos 6 caracteres.", "danger")
                return redirect(url_for("pubview"))

            # Guardar nueva contraseña
            current_user.password_hash = generate_password_hash(password)

        # Guardar cambios en otros campos
        current_user.mail = mail
        current_user.congregacion = congregacion
        current_user.circuito = circuito
        current_user.celular = celular

        db.session.commit()
        flash("Perfil actualizado correctamente.", "success")
        return redirect(url_for("pubview"))

    # GET request
    return render_template("pubview.html", user=current_user)
# -------------------------------
# 🔹 Eliminar solicitud de turno
# -------------------------------

@app.route("/eliminar_solicitud/<int:id>", methods=["POST"])
@login_required
def eliminar_solicitud(id):
    solicitud = SolicitudTurno.query.get_or_404(id)

    # Validar que la solicitud pertenezca al usuario logueado
    if solicitud.publicador_id != current_user.id:
        flash("No tenés permiso para eliminar esta solicitud.", "danger")
        return redirect(url_for("pubview"))

    db.session.delete(solicitud)
    db.session.commit()
    flash("Solicitud eliminada correctamente.", "success")
    return redirect(url_for("pubview"))



# ----------------------------
# 🔹 Eliminar ausencia
# ----------------------------

@app.route("/eliminar_ausencia/<int:id>", methods=["POST"])
@login_required
def eliminar_ausencia(id):
    ausencia = Ausencia.query.get_or_404(id)

    # Validar que la ausencia pertenezca al usuario logueado
    if ausencia.publicador_id != current_user.id:
        flash("No tenés permiso para eliminar esta ausencia.", "danger")
        return redirect(url_for("pubview"))

    db.session.delete(ausencia)
    db.session.commit()
    flash("Ausencia eliminada correctamente.", "success")
    return redirect(url_for("pubview"))
# ------------------------- Reemplazos --------------------- #
# ------------------------- Calendario --------------------- #
# ------------------------- Semanal ------------------------ #
@app.route("/api/reemplazos/semana")
@login_required
def api_reemplazos_semana():
    fecha = request.args.get("fecha")  # YYYY-MM-DD
    if not fecha:
        return {"error": "Falta fecha"}, 400

    base = datetime.strptime(fecha, "%Y-%m-%d").date()
    lunes = base - timedelta(days=base.weekday())
    domingo = lunes + timedelta(days=6)

    turnos = Turno.query.filter(
        Turno.fecha >= lunes,
        Turno.fecha <= domingo,
        Turno.is_public == True
    ).all()

    out = []
    for t in turnos:
        ocupados = sum(1 for p in
                       [t.publicador1_id, t.publicador2_id, t.publicador3_id, t.publicador4_id]
                       if p)
        vacantes = 4 - ocupados

        if vacantes > 0:
            out.append({
                "id": t.id,
                "fecha": t.fecha.strftime("%Y-%m-%d"),
                "hora_inicio": t.hora_inicio.strftime("%H:%M"),
                "hora_fin": t.hora_fin.strftime("%H:%M"),
                "punto": t.punto.punto_nombre,
                "vacantes": vacantes
            })

    return jsonify(out)

@app.route("/tomar_reemplazo/<int:turno_id>", methods=["POST"])
@login_required
def tomar_reemplazo(turno_id):
    turno = Turno.query.get_or_404(turno_id)

    # Contar vacantes
    publicadores_ids = [turno.publicador1_id, turno.publicador2_id, turno.publicador3_id, turno.publicador4_id]
    vacantes = 4 - sum(1 for p in publicadores_ids if p)

    if vacantes == 0:
        flash("Este turno ya está completo.", "warning")
        return redirect(url_for("pubview"))

    # Crear solicitud para el current_user
    nueva_solicitud = SolicitudTurno(
        punto_id=turno.punto_id,
        hora_inicio=turno.hora_inicio,
        hora_fin=turno.hora_fin,
        fecha_inicio=turno.fecha,
        fecha_fin=turno.fecha,
        prioridad=30,
        publicador_id=current_user.id,
        frecuencia="semanal",  # valor por defecto
        dia=turno.dia
    )
    db.session.add(nueva_solicitud)
    db.session.commit()
    flash("Solicitud de reemplazo creada correctamente.", "success")
    return redirect(url_for("pubview"))











# -------------------------------------------
# RUN
# -------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run()
    import logging

    logging.basicConfig(level=logging.DEBUG)

