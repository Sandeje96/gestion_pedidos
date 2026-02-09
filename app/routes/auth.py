# -*- coding: utf-8 -*-
"""
Blueprint de autenticación (login, logout).
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app import db
from app.models.usuario import Usuario
from app.forms.auth_forms import LoginForm
from datetime import datetime

# Crear el Blueprint
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Ruta de inicio de sesión.
    GET: Muestra el formulario
    POST: Procesa el login
    """
    
    # Si ya está logueado, redirigir a su dashboard
    if current_user.is_authenticated:
        if current_user.es_vendedor():
            return redirect(url_for('ventas.dashboard'))
        elif current_user.es_operario():
            return redirect(url_for('fabrica.dashboard'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        # Buscar usuario por username
        usuario = Usuario.query.filter_by(username=form.username.data).first()
        
        # Verificar si existe y la contraseña es correcta
        if usuario and usuario.check_password(form.password.data):
            
            # Verificar si está activo
            if not usuario.activo:
                flash('Tu cuenta está desactivada. Contacta al administrador.', 'danger')
                return redirect(url_for('auth.login'))
            
            # Iniciar sesión
            login_user(usuario, remember=form.remember_me.data)
            
            # Actualizar última conexión
            usuario.ultima_conexion = datetime.utcnow()
            db.session.commit()
            
            flash(f'¡Bienvenido {usuario.nombre}!', 'success')
            
            # Redirigir según el rol
            if usuario.es_vendedor():
                return redirect(url_for('ventas.dashboard'))
            elif usuario.es_operario():
                return redirect(url_for('fabrica.dashboard'))
            else:
                return redirect(url_for('index'))
        
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
    
    return render_template('auth/login.html', form=form, title='Iniciar Sesión')


@auth_bp.route('/logout')
def logout():
    """
    Ruta para cerrar sesión.
    """
    logout_user()
    flash('Has cerrado sesión correctamente', 'info')
    return redirect(url_for('auth.login'))