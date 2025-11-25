from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensiones import db


# ----------------------
# PUBLICADORES
# ----------------------
class Publicador(UserMixin, db.Model):
    __tablename__ = "publicadores"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    apellido = db.Column(db.String(50), nullable=False)
    mail = db.Column(db.String(100), unique=True, nullable=False)
    congregacion = db.Column(db.String(100))
    circuito = db.Column(db.String(100))
    rol = db.Column(db.String(50))  # ej: publicador, precursor, anciano
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    principiante = db.Column(db.Boolean, default=False)
    ultima_participacion = db.Column(db.Date, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)


# ----------------------
# EXPERIENCIAS
# ----------------------
class Experiencia(db.Model):
    __tablename__ = "experiencias"

    id = db.Column(db.Integer, primary_key=True)
    publicador_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"), nullable=False)
    punto_id = db.Column(db.Integer, db.ForeignKey("puntos_predicacion.id"), nullable=False)
    fecha = db.Column(db.Date)
    notas = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=False)


# ----------------------
# PUNTOS DE PREDICACIÓN
# ----------------------
class PuntoPredicacion(db.Model):
    __tablename__ = "puntos_predicacion"

    id = db.Column(db.Integer, primary_key=True)
    fecha_inicio = db.Column(db.Date)
    fecha_fin = db.Column(db.Date)
    nombre_punto = db.Column(db.String(100))
    # horarios por día de la semana
    lunes_inicio = db.Column(db.Time)
    lunes_fin = db.Column(db.Time)
    martes_inicio = db.Column(db.Time)
    martes_fin = db.Column(db.Time)
    miercoles_inicio = db.Column(db.Time)
    miercoles_fin = db.Column(db.Time)
    jueves_inicio = db.Column(db.Time)
    jueves_fin = db.Column(db.Time)
    viernes_inicio = db.Column(db.Time)
    viernes_fin = db.Column(db.Time)
    sabado_inicio = db.Column(db.Time)
    sabado_fin = db.Column(db.Time)
    domingo_inicio = db.Column(db.Time)
    domingo_fin = db.Column(db.Time)

    duracion_turno = db.Column(db.Integer)  # minutos
    direccion_deposito = db.Column(db.String(200))
    contacto_deposito = db.Column(db.String(100))
    telefono_deposito = db.Column(db.String(50))


# ----------------------
# SOLICITUD DE TURNO
# ----------------------
class SolicitudTurno(db.Model):
    __tablename__ = "solicitudes_turno"

    id = db.Column(db.Integer, primary_key=True)
    punto_id = db.Column(db.Integer, db.ForeignKey("puntos_predicacion.id"), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    prioridad = db.Column(db.Integer, default=1)
    publicador_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"), nullable=False)
    frecuencia = db.Column(db.String(50))  # ej: semanal, 1mes, 2mes, 3mes, 4mes, 5mes


# ----------------------
# AUSENCIAS
# ----------------------
class Ausencia(db.Model):
    __tablename__ = "ausencias"

    id = db.Column(db.Integer, primary_key=True)
    publicador_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    motivo = db.Column(db.String(200))

    publicador = db.relationship("Publicador", lazy="joined")

# ----------------------
# TURNOS
# ----------------------
class Turno(db.Model):
    __tablename__ = "turnos"

    id = db.Column(db.Integer, primary_key=True)
    punto_id = db.Column(db.Integer, db.ForeignKey("puntos_predicacion.id"), nullable=False)

    publicador1_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    publicador2_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    publicador3_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    publicador4_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    capitan_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))

    dia =   dia = db.Column(db.Enum('lunes','martes','miercoles','jueves','viernes','sabado','domingo','feriado', name='enum_dia'), nullable=False, default='lunes')
  # lunes, martes, etc
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    is_public = db.Column(db.Boolean, default=False)


# ----------------------
# CAPITAN
# ----------------------
class Capitan(db.Model):
    __tablename__ = "capitanes"

    id = db.Column(db.Integer, primary_key=True)
    punto_id = db.Column(db.Integer, db.ForeignKey("puntos_predicacion.id"), nullable=False)

    lunes = db.Column(db.Boolean, default=False)
    martes = db.Column(db.Boolean, default=False)
    miercoles = db.Column(db.Boolean, default=False)
    jueves = db.Column(db.Boolean, default=False)
    viernes = db.Column(db.Boolean, default=False)
    sabado = db.Column(db.Boolean, default=False)
    domingo = db.Column(db.Boolean, default=False)
