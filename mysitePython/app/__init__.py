from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    load_dotenv("var.env")

    nombrecuenta = os.getenv("NOMBRE_CUENTA")
    passworddb = os.getenv("PASSWORD_DB")
    instancia = os.getenv("INSTANCIA")
    secret_key = os.getenv("SECRET_KEY")

    app = Flask(__name__)
    app.config["DEBUG"] = True
    app.secret_key = secret_key

    # Config DB
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+mysqlconnector://{nombrecuenta}:{passworddb}"
        f"@{nombrecuenta}.mysql.pythonanywhere-services.com/{nombrecuenta}${instancia}"
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    login_manager.init_app(app)

    # 👇 Registrar blueprint
    from .routes import bp
    app.register_blueprint(bp)

    return app
