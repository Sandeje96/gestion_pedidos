# -*- coding: utf-8 -*-
"""
Blueprint para el panel de Gerencia.
"""

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.pedido import Pedido
from app.models.cliente import Cliente
from app.models.usuario import Usuario
from functools import wraps
from sqlalchemy import distinct

# Crear el Blueprint
gerente_bp = Blueprint('gerente', __name__)


def gerente_requerido(f):
    """
    Decorador para verificar que el usuario sea Gerente.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_gerente():
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@gerente_bp.route('/dashboard')
@gerente_requerido
def dashboard():
    """
    Panel principal de Gerencia.
    Muestra los productos únicos pedidos a fábrica por vendedores y sucursales.
    """
    # IDs de usuarios con rol vendedor o sucursal
    usuarios_ids = db.session.query(Usuario.id).filter(
        Usuario.rol.in_(['vendedor', 'sucursal'])
    ).subquery()

    # Productos únicos (sin repetir) pedidos a fábrica por vendedores/sucursales,
    # mediante sus clientes — pedidos no archivados
    productos = db.session.query(
        distinct(Pedido.producto_nombre)
    ).join(Cliente, Pedido.cliente_id == Cliente.id).filter(
        Pedido.destinatario == 'fabrica',
        Pedido.archivado == False,
        Cliente.creado_por_id.in_(usuarios_ids)
    ).order_by(Pedido.producto_nombre).all()

    # Convertir lista de tuplas a lista de strings
    productos_lista = [p[0] for p in productos]

    return render_template(
        'gerente/dashboard.html',
        title='Panel de Gerencia',
        productos=productos_lista
    )
