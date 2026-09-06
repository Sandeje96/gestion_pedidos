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
        elif current_user.es_sucursal():
            return redirect(url_for('sucursal.dashboard'))
        elif current_user.es_administracion():
            return redirect(url_for('administracion.dashboard'))
        elif current_user.es_repartidor():
            return redirect(url_for('repartidor.dashboard'))
        elif current_user.es_gerente():
            return redirect(url_for('gerente.dashboard'))
    
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
            elif usuario.es_sucursal():
                return redirect(url_for('sucursal.dashboard'))
            elif usuario.es_administracion():
                return redirect(url_for('administracion.dashboard'))
            elif usuario.es_repartidor():
                return redirect(url_for('repartidor.dashboard'))
            elif usuario.es_gerente():
                return redirect(url_for('gerente.dashboard'))
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

@auth_bp.route('/crear-tabla-mensajes-x9m5k1', methods=['GET'])
def crear_tabla_mensajes():
    """
    Endpoint temporal para crear tabla mensajes_pedido
    ⚠️ ELIMINAR DESPUÉS DE USAR
    """
    from sqlalchemy import text
    from app import db
    
    try:
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS mensajes_pedido (
                id SERIAL PRIMARY KEY,
                pedido_id INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                mensaje TEXT NOT NULL,
                tipo VARCHAR(20) NOT NULL,
                leido BOOLEAN DEFAULT FALSE NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_mensajes_pedido_pedido_id ON mensajes_pedido(pedido_id)"
        ))
        
        db.session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_mensajes_pedido_fecha ON mensajes_pedido(fecha_creacion)"
        ))
        
        db.session.commit()
        return "<h1>✅ Tabla mensajes_pedido creada exitosamente</h1><p><strong>AHORA ELIMINA ESTE ENDPOINT</strong></p>"
    except Exception as e:
        db.session.rollback()
        return f"<h1>❌ Error:</h1><pre>{str(e)}</pre>"

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


@auth_bp.route('/setup-repartidor-v7h3k9x2', methods=['GET'])
def setup_repartidor_production():
    """
    Endpoint temporal para crear el usuario Repartidor en producción.
    ⚠️ ELIMINAR DESPUÉS DE USAR
    """
    from app.models.usuario import Usuario

    try:
        u_repartidor = Usuario.query.filter_by(username='repartidor').first()
        if not u_repartidor:
            u_repartidor = Usuario(
                nombre="Repartidor",
                username="repartidor",
                email="repartidor@ejemplo.com",
                rol="repartidor",
                activo=True
            )
            u_repartidor.set_password("123456")
            db.session.add(u_repartidor)
            db.session.commit()
            mensaje = "Usuario 'repartidor' creado exitosamente."
        else:
            mensaje = "Usuario 'repartidor' ya existía en la base de datos."

        return f"""
        <html>
        <head><title>Setup Repartidor</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #28a745;">✅ {mensaje}</h1>
                <h3>Credenciales:</h3>
                <ul>
                    <li><strong>Usuario:</strong> repartidor</li>
                    <li><strong>Contraseña:</strong> 123456</li>
                    <li><strong>Rol:</strong> repartidor</li>
                </ul>
                <hr>
                <h3 style="color: #dc3545;">⚠️ IMPORTANTE:</h3>
                <p><strong>Elimina este endpoint después de verificar que funciona correctamente.</strong></p>
                <hr>
                <a href="/" style="display: inline-block; background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px;">Ir al Inicio</a>
            </div>
        </body>
        </html>
        """

    except Exception as e:
        db.session.rollback()
        import traceback
        error_detail = traceback.format_exc()
        return f"""
        <html>
        <head><title>Error Setup Repartidor</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #dc3545;">❌ Error al crear usuario repartidor</h1>
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">{error_detail}</pre>
            </div>
        </body>
        </html>
        """


@auth_bp.route('/setup-nuevos-usuarios-v9n2p5q', methods=['GET'])
def setup_nuevos_usuarios_production():
    """
    Endpoint temporal para agregar los nuevos usuarios y clientes de sucursal en producción.
    ⚠️ ELIMINAR DESPUÉS DE USAR
    """
    from app.models.usuario import Usuario
    from app.models.cliente import Cliente
    
    from sqlalchemy import text
    
    # Intentar agregar las nuevas columnas a la tabla de pedidos online si no existen
    columnas_agregadas = []
    
    # 1. Agregar destinatario
    try:
        db.session.execute(text("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS destinatario VARCHAR(30) DEFAULT 'fabrica' NOT NULL"))
        db.session.commit()
        columnas_agregadas.append("Columna 'destinatario' agregada/verificada.")
    except Exception as e_dest:
        db.session.rollback()
        columnas_agregadas.append(f"Nota columna 'destinatario': {str(e_dest)}")
        
    # 2. Agregar despachado
    try:
        db.session.execute(text("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS despachado BOOLEAN DEFAULT FALSE NOT NULL"))
        db.session.commit()
        columnas_agregadas.append("Columna 'despachado' agregada/verificada.")
    except Exception as e_desp:
        db.session.rollback()
        columnas_agregadas.append(f"Nota columna 'despachado': {str(e_desp)}")

    # 3. Crear índice
    try:
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_pedidos_destinatario ON pedidos(destinatario)"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        mensajes_resultado = list(columnas_agregadas)
        
        # 1. Crear usuario sucursal si no existe
        u_sucursal = Usuario.query.filter_by(username='sucursal').first()
        if not u_sucursal:
            u_sucursal = Usuario(
                nombre="Sucursales",
                username="sucursal",
                email="sucursales@ejemplo.com",
                rol="sucursal",
                activo=True
            )
            u_sucursal.set_password("123456")
            db.session.add(u_sucursal)
            mensajes_resultado.append("Usuario 'sucursal' creado.")
        else:
            mensajes_resultado.append("Usuario 'sucursal' ya existía.")
            
        # 2. Crear usuario administracion si no existe
        u_admin = Usuario.query.filter_by(username='administracion').first()
        if not u_admin:
            u_admin = Usuario(
                nombre="Administración Fábrica",
                username="administracion",
                email="administracion@ejemplo.com",
                rol="administracion",
                activo=True
            )
            u_admin.set_password("123456")
            db.session.add(u_admin)
            mensajes_resultado.append("Usuario 'administracion' creado.")
        else:
            mensajes_resultado.append("Usuario 'administracion' ya existía.")
            
        # Flush de sesión para que los IDs de los usuarios nuevos se generen en la BD
        db.session.flush()
        
        # Determinar el ID del creador para los clientes (referencia a la sucursal o al primer usuario)
        creador_id = u_sucursal.id if u_sucursal and u_sucursal.id else None
        if not creador_id:
            u_sucursal_db = Usuario.query.filter_by(username='sucursal').first()
            if u_sucursal_db:
                creador_id = u_sucursal_db.id
            else:
                first_u = Usuario.query.first()
                if first_u:
                    creador_id = first_u.id
                    
        # 3. Crear los 5 clientes sucursales si no existen
        clientes_sucursales = [
            "SUCURSAL URUGUAY",
            "SUCURSAL TAMBOR DE TACUARI",
            "SUCURSAL CANDELARIA",
            "FRANQUICIA VILLA CABELLO",
            "FRANQUICIA LOPEZ Y PLANES"
        ]
        
        for c_nombre in clientes_sucursales:
            cliente = Cliente.query.filter_by(nombre=c_nombre).first()
            if not cliente:
                new_c = Cliente(
                    nombre=c_nombre,
                    direccion="Dirección Sucursal",
                    telefono="000-0000",
                    ruta="SUCURSALES",
                    activo=True,
                    creado_por_id=creador_id
                )
                db.session.add(new_c)
                mensajes_resultado.append(f"Cliente '{c_nombre}' creado.")
            else:
                # Asegurar que tenga la ruta SUCURSALES
                if cliente.ruta != "SUCURSALES":
                    cliente.ruta = "SUCURSALES"
                    mensajes_resultado.append(f"Cliente '{c_nombre}' actualizado a ruta SUCURSALES.")
                else:
                    mensajes_resultado.append(f"Cliente '{c_nombre}' ya existía con ruta correcta.")
                    
        db.session.commit()
        
        detalles = "<br>".join([f"<li>{m}</li>" for m in mensajes_resultado])
        return f"""
        <html>
        <head><title>Nuevos Usuarios Setup</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #28a745;">✅ Nuevos usuarios y sucursales procesados</h1>
                <h3>Resultados:</h3>
                <ul>
                    {detalles}
                </ul>
                <hr>
                <h3 style="color: #dc3545;">⚠️ IMPORTANTE:</h3>
                <p><strong>Los usuarios y clientes están listos para ser usados online.</strong></p>
                <p>Una vez verifiques su funcionamiento, puedes eliminar este endpoint temporal por seguridad.</p>
                <hr>
                <a href="/" style="display: inline-block; background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px;">Ir al Inicio</a>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        db.session.rollback()
        import traceback
        error_detail = traceback.format_exc()
        return f"""
        <html>
        <head><title>Error Setup</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #dc3545;">❌ Error al inicializar nuevos usuarios</h1>
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">{error_detail}</pre>
            </div>
        </body>
        </html>
        """


@auth_bp.route('/setup-gerente-v4r8t2w6', methods=['GET'])
def setup_gerente_production():
    """
    Endpoint temporal para crear el usuario Gerente en producción.
    ⚠️ ELIMINAR DESPUÉS DE USAR
    """
    from app.models.usuario import Usuario

    try:
        u_gerente = Usuario.query.filter_by(username='gerente').first()
        if not u_gerente:
            u_gerente = Usuario(
                nombre="Gerente",
                username="gerente",
                email="gerente@ejemplo.com",
                rol="gerente",
                activo=True
            )
            u_gerente.set_password("admin123")
            db.session.add(u_gerente)
            db.session.commit()
            mensaje = "Usuario 'gerente' creado exitosamente."
        else:
            u_gerente.set_password("admin123")
            db.session.commit()
            mensaje = "Usuario 'gerente' ya existía — contraseña actualizada a admin123."

        return f"""
        <html>
        <head><title>Setup Gerente</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #28a745;">✅ {mensaje}</h1>
                <h3>Credenciales:</h3>
                <ul>
                    <li><strong>Usuario:</strong> gerente</li>
                    <li><strong>Contraseña:</strong> 123456</li>
                    <li><strong>Rol:</strong> gerente</li>
                </ul>
                <hr>
                <h3 style="color: #dc3545;">⚠️ IMPORTANTE:</h3>
                <p><strong>Elimina este endpoint después de verificar que funciona correctamente.</strong></p>
                <hr>
                <a href="/" style="display: inline-block; background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px;">Ir al Inicio</a>
            </div>
        </body>
        </html>
        """

    except Exception as e:
        db.session.rollback()
        import traceback
        error_detail = traceback.format_exc()
        return f"""
        <html>
        <head><title>Error Setup Gerente</title></head>
        <body style="font-family: Arial; padding: 40px; background: #f0f0f0;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 600px; margin: 0 auto;">
                <h1 style="color: #dc3545;">❌ Error al crear usuario gerente</h1>
                <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">{error_detail}</pre>
            </div>
        </body>
        </html>
        """

