from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensiones import db

# -------------------------------------------
# MODELOS
# -------------------------------------------
class Publicador(db.Model):
    __tablename__ = "publicadores"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50))
    apellido = db.Column(db.String(50))
    mail = db.Column(db.String(100))
    congregacion = db.Column(db.String(100))
    circuito = db.Column(db.String(50))
    celular = db.Column(db.String(50))
    usuario = db.Column(db.String(50), unique=True)
    rol = db.Column(db.String(50))
    password_hash = db.Column(db.String(200))
    principiante = db.Column(db.Boolean, default=False)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

class PuntoPredicacion(db.Model):
    __tablename__ = "puntos_predicacion"
    id = db.Column(db.Integer, primary_key=True)
    punto_nombre = db.Column(db.String(100))
    fecha_inicio = db.Column(db.Date)
    fecha_fin = db.Column(db.Date)
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
    duracion_turno = db.Column(db.Integer)
    direccion_deposito = db.Column(db.String(200))
    contacto_deposito = db.Column(db.String(100))
    telefono_deposito = db.Column(db.String(50))

class SolicitudTurno(db.Model):
    __tablename__ = "solicitudes_turno"
    id = db.Column(db.Integer, primary_key=True)
    punto_id = db.Column(db.Integer, db.ForeignKey("puntos_predicacion.id"), nullable=True)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    prioridad = db.Column(db.Integer, default=1)
    publicador_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"), nullable=True)
    frecuencia = db.Column(db.String(50))
    dia = db.Column(db.Enum('lunes','martes','miercoles','jueves','viernes','sabado','domingo','feriado', name='enum_dia'), nullable=False, default='lunes')

    fecha_inicio = db.Column(db.Date, nullable=True, default=None)
    fecha_fin = db.Column(db.Date, nullable=True, default=None)
    # Relaciones para acceder desde Jinja
    publicador = db.relationship("Publicador", backref="solicitudes")
    punto = db.relationship("PuntoPredicacion", backref="solicitudes")

class Experiencia(db.Model):
    __tablename__ = "experiencias"

    id = db.Column(db.Integer, primary_key=True)
    publicador_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"), nullable=True)
    punto_id = db.Column(db.Integer, db.ForeignKey("puntos_predicacion.id"), nullable=True)
    fecha = db.Column(db.Date)
    notas = db.Column(db.Text)
    is_public = db.Column(db.Boolean, default=False)

    publicador = db.relationship("Publicador", lazy="joined")
    punto = db.relationship("PuntoPredicacion", lazy="joined")

class Ausencia(db.Model):
    __tablename__ = "ausencias"

    id = db.Column(db.Integer, primary_key=True)
    publicador_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"), nullable=True)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    motivo = db.Column(db.String(200))

    publicador = db.relationship("Publicador", lazy="joined")

class Turno(db.Model):
    __tablename__ = "turnos"

    id = db.Column(db.Integer, primary_key=True)
    punto_id = db.Column(db.Integer, db.ForeignKey("puntos_predicacion.id"), nullable=True)

    publicador1_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    publicador2_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    publicador3_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    publicador4_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))
    capitan_id = db.Column(db.Integer, db.ForeignKey("publicadores.id"))

    dia =   dia = db.Column(db.Enum('lunes','martes','miercoles','jueves','viernes','sabado','domingo','feriado', name='enum_dia'), nullable=False, default='lunes')
  # lunes, martes, etc
    fecha = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fin = db.Column(db.Time, nullable=False)
    is_public = db.Column(db.Boolean, default=False)

    punto = db.relationship("PuntoPredicacion", lazy="joined")
    publicador1 = db.relationship("Publicador", foreign_keys=[publicador1_id])
    publicador2 = db.relationship("Publicador", foreign_keys=[publicador2_id])
    publicador3 = db.relationship("Publicador", foreign_keys=[publicador3_id])
    publicador4 = db.relationship("Publicador", foreign_keys=[publicador4_id])
    capitan = db.relationship("Publicador", foreign_keys=[capitan_id])
#----------------------------------------------------------------------------FIN CLASES---------------------------------------------

