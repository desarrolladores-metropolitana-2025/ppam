from functools import wraps
from flask import abort
from flask_login import current_user, login_required

def admin_required(f):
    """
    Decorador que asegura que el usuario esté logueado
    y tenga rol 'admin'. Si no, devuelve 403.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if current_user.rol != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
