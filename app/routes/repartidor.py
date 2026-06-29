# -*- coding: utf-8 -*-
"""
Blueprint para el panel del Repartidor.
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from functools import wraps

# Crear el Blueprint
repartidor_bp = Blueprint('repartidor', __name__)


def repartidor_requerido(f):
    """
    Decorador para verificar que el usuario sea Repartidor.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_repartidor():
            from flask import flash
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@repartidor_bp.route('/dashboard')
@repartidor_requerido
def dashboard():
    """
    Panel principal del Repartidor.
    """
    return render_template(
        'repartidor/dashboard.html',
        title='Panel de Repartidor'
    )
