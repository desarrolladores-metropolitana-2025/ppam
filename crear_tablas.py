# crear_tablas.py
from extensiones import db
from flask_app import create_app

app = create_app()

# Importá los modelos DESPUÉS de crear la app para registrar las tablas
import models  # noqa: F401

with app.app_context():
    print("📌 Creando tablas en la base de datos...")
    db.create_all()
    print("✅ Tablas creadas correctamente")

