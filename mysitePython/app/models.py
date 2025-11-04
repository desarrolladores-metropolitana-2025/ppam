from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db  # importa la instancia de SQLAlchemy desde __init__.py

class Publicador(UserMixin, db.Model):
    __tablename__ = 'publicadores'

    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    nombre = db.Column(db.String(50), nullable=False)
    apellido = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    # ----------------------
    # Métodos de contraseña
    # ----------------------
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
