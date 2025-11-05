from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from .models import Publicador
from . import db, login_manager

bp = Blueprint("main", __name__)

@login_manager.user_loader
def load_user(user_id):
    return Publicador.query.get(int(user_id))

@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = Publicador.query.filter_by(usuario=username).first()
        if user and user.check_password(password):
            login_user(user, remember=("remember" in request.form))
            flash("Bienvenido, " + user.nombre, "success")
            return redirect(url_for("main.main_page"))
        else:
            error = True
    return render_template("login_page.html", error=error)

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada", "info")
    return redirect(url_for("main.login"))

@bp.route("/main")
@login_required
def main_page():
    return render_template(
        "main_page.html",
        usuarioceh=current_user.nombre + " " + current_user.apellido,
        medic=[],
        institut=[],
        cehs=[],
        gvp=[]
    )
