# -*- coding: utf-8 -*-
"""
Blueprint para el panel del Repartidor.
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.cliente import Cliente
from functools import wraps
from collections import defaultdict

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
    Muestra las rutas existentes con sus clientes activos.
    Excluye la ruta SUCURSALES (esa es interna).
    """
    # Obtener todos los clientes activos, excluyendo la ruta SUCURSALES
    clientes = (
        Cliente.query
        .filter(Cliente.activo == True, Cliente.ruta != 'SUCURSALES')
        .order_by(Cliente.ruta, Cliente.nombre)
        .all()
    )

    # Agrupar por ruta
    clientes_por_ruta = defaultdict(list)
    for cliente in clientes:
        clientes_por_ruta[cliente.ruta].append(cliente)

    # Ordenar rutas alfabéticamente
    clientes_por_ruta = dict(sorted(clientes_por_ruta.items()))

    total_rutas = len(clientes_por_ruta)
    total_clientes = len(clientes)

    return render_template(
        'repartidor/dashboard.html',
        title='Panel de Repartidor',
        clientes_por_ruta=clientes_por_ruta,
        total_rutas=total_rutas,
        total_clientes=total_clientes
    )
