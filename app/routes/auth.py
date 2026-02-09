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

@auth_bp.route('/setup-db-x9k2m4p7', methods=['GET'])
def setup_database_production():
    """
    Endpoint temporal para inicializar PostgreSQL en producción.
    ⚠️ ELIMINAR DESPUÉS DE USAR
    """
    from app import db
    from app.models.usuario import Usuario
    from app.models.cliente import Cliente
    from app.models.producto import Producto
    from app.models.pedido import Pedido
    
    try:
        # Crear todas las tablas
        db.create_all()
        
        # Verificar si ya hay usuarios
        usuario_count = Usuario.query.count()
        if usuario_count > 0:
            return f"<h1>✅ Base de datos ya inicializada</h1><p>Usuarios existentes: {usuario_count}</p><p><strong>AHORA ELIMINA ESTE ENDPOINT</strong></p>"
        
        # Crear usuarios de prueba
        print("Creando vendedores...")
        vendedor1 = Usuario(
            nombre="Juan Perez",
            username="juan",
            email="juan@ejemplo.com",
            rol="vendedor",
            activo=True
        )
        vendedor1.set_password("123456")
        db.session.add(vendedor1)
        
        vendedor2 = Usuario(
            nombre="Maria Gonzalez",
            username="maria",
            email="maria@ejemplo.com",
            rol="vendedor",
            activo=True
        )
        vendedor2.set_password("123456")
        db.session.add(vendedor2)
        
        # Crear operarios
        print("Creando operarios...")
        operario1 = Usuario(
            nombre="Carlos Rodriguez",
            username="carlos",
            email="carlos@ejemplo.com",
            rol="operario",
            activo=True
        )
        operario1.set_password("123456")
        db.session.add(operario1)
        
        operario2 = Usuario(
            nombre="Ana Martinez",
            username="ana",
            email="ana@ejemplo.com",
            rol="operario",
            activo=True
        )
        operario2.set_password("123456")
        db.session.add(operario2)
        
        operario3 = Usuario(
            nombre="Luis Fernandez",
            username="luis",
            email="luis@ejemplo.com",
            rol="operario",
            activo=True
        )
        operario3.set_password("123456")
        db.session.add(operario3)
        
        db.session.commit()
        
        return """
        <html>
        <head><title>Setup Completado</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #28a745;">✅ Base de datos inicializada correctamente</h1>
                <h3>Usuarios creados:</h3>
                <ul>
                    <li><strong>Vendedores:</strong>
                        <ul>
                            <li>juan / 123456</li>
                            <li>maria / 123456</li>
                        </ul>
                    </li>
                    <li><strong>Operarios:</strong>
                        <ul>
                            <li>carlos / 123456</li>
                            <li>ana / 123456</li>
                            <li>luis / 123456</li>
                        </ul>
                    </li>
                </ul>
                <hr>
                <h3 style="color: #dc3545;">⚠️ IMPORTANTE:</h3>
                <p><strong>AHORA DEBES ELIMINAR ESTE ENDPOINT del código por seguridad.</strong></p>
                <p>Ve a <code>app/routes/auth.py</code> y elimina la función <code>setup_database_production</code></p>
                <hr>
                <a href="/" style="display: inline-block; background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px;">Ir al Login</a>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return f"""
        <html>
        <head><title>Error Setup</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #dc3545;">❌ Error al inicializar base de datos</h1>
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">{error_detail}</pre>
                <p><strong>Verifica:</strong></p>
                <ul>
                    <li>Que DATABASE_URL esté configurada correctamente</li>
                    <li>Que la base de datos PostgreSQL esté activa</li>
                    <li>Revisa los logs en Railway</li>
                </ul>
            </div>
        </body>
        </html>
        """

