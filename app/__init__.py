# -*- coding: utf-8 -*-
"""
Inicializacion de la aplicacion Flask.
Aqui se configuran todas las extensiones y se registran las rutas.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from config import config

# Inicializar extensiones (sin asignar a la app todavia)
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO(cors_allowed_origins="*")  # Permitir WebSocket desde cualquier origen

def create_app(config_name='development'):
    """
    Factory para crear la aplicacion Flask.
    
    Args:
        config_name: Tipo de configuracion ('development' o 'production')
    
    Returns:
        app: Aplicacion Flask configurada
    """
    
    # Crear instancia de Flask
    app = Flask(__name__)
    
    # Cargar configuracion
    app.config.from_object(config[config_name])
    
    # Inicializar extensiones con la app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app)
    
    # Configuracion de Flask-Login
    login_manager.login_view = 'auth.login'  # Ruta para login
    login_manager.login_message = 'Por favor inicia sesion para acceder.'
    login_manager.login_message_category = 'warning'
    
    # Registrar Blueprints (rutas)
    # Los importamos aqui para evitar importaciones circulares
    from app.routes.auth import auth_bp
    from app.routes.ventas import ventas_bp
    from app.routes.fabrica import fabrica_bp
    from app.routes.sucursal import sucursal_bp
    from app.routes.administracion import administracion_bp
    from app.routes.repartidor import repartidor_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(ventas_bp, url_prefix='/ventas')
    app.register_blueprint(fabrica_bp, url_prefix='/fabrica')
    app.register_blueprint(sucursal_bp, url_prefix='/sucursal')
    app.register_blueprint(administracion_bp, url_prefix='/administracion')
    app.register_blueprint(repartidor_bp, url_prefix='/repartidor')
    
    # Ruta principal (redirecciona segun el rol del usuario)
    from flask import redirect, url_for
    from flask_login import current_user
    
    @app.route('/')
    def index():
        """Ruta de inicio - redirige segun el usuario"""
        if current_user.is_authenticated:
            if current_user.rol == 'vendedor':
                return redirect(url_for('ventas.dashboard'))
            elif current_user.rol == 'operario':
                return redirect(url_for('fabrica.dashboard'))
            elif current_user.rol == 'sucursal':
                return redirect(url_for('sucursal.dashboard'))
            elif current_user.rol == 'administracion':
                return redirect(url_for('administracion.dashboard'))
            elif current_user.rol == 'repartidor':
                return redirect(url_for('repartidor.dashboard'))
        return redirect(url_for('auth.login'))
    
    # Manejador de errores 404
    @app.errorhandler(404)
    def page_not_found(e):
        return {'error': 'Pagina no encontrada'}, 404
    
    # Manejador de errores 500
    @app.errorhandler(500)
    def internal_server_error(e):
        return {'error': 'Error interno del servidor'}, 500
    
    # Crear tablas si no existen (solo en desarrollo)
    with app.app_context():
        db.create_all()
        
        # Migraciones automáticas de base de datos para producción (PostgreSQL) y local (SQLite)
        from sqlalchemy import text
        
        # 1. Agregar columna 'destinatario'
        try:
            db.session.execute(text("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS destinatario VARCHAR(30) DEFAULT 'fabrica' NOT NULL"))
            db.session.commit()
        except Exception as e_dest:
            db.session.rollback()
            print(f"Migración: columna 'destinatario' ya existe o no se pudo agregar: {e_dest}")
            
        # 2. Agregar columna 'despachado'
        try:
            db.session.execute(text("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS despachado BOOLEAN DEFAULT FALSE NOT NULL"))
            db.session.commit()
        except Exception as e_desp:
            db.session.rollback()
            print(f"Migración: columna 'despachado' ya existe o no se pudo agregar: {e_desp}")
            
        # 3. Crear índice para 'destinatario'
        try:
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_pedidos_destinatario ON pedidos(destinatario)"))
            db.session.commit()
        except Exception as e_idx:
            db.session.rollback()
            print(f"Migración: índice 'idx_pedidos_destinatario' no se pudo crear: {e_idx}")

        # 4. Agregar columna 'recibido_conforme'
        try:
            db.session.execute(text("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS recibido_conforme BOOLEAN DEFAULT FALSE NOT NULL"))
            db.session.commit()
        except Exception as e_recibido:
            db.session.rollback()
            print(f"Migración: columna 'recibido_conforme' ya existe o no se pudo agregar: {e_recibido}")
    
    # ── Filtros Jinja2 personalizados ──
    def formato_peso(value, decimales=2):
        """Formatea un número con punto como separador de miles y coma para decimales.
        Ejemplo: 1234567.89 → '1.234.567,89'
        """
        try:
            value = float(value)
        except (TypeError, ValueError):
            return value
        # Formatear con los decimales solicitados usando locale-style manual
        formatted = f"{value:,.{decimales}f}"          # '1,234,567.89' (anglosajón)
        formatted = formatted.replace(',', 'X')        # '1X234X567.89'
        formatted = formatted.replace('.', ',')        # '1X234X567,89'
        formatted = formatted.replace('X', '.')        # '1.234.567,89'
        return formatted

    app.jinja_env.filters['formato_peso'] = formato_peso

    return app


# Funcion para cargar usuario (requerida por Flask-Login)
from app.models.usuario import Usuario

@login_manager.user_loader
def load_user(user_id):
    """
    Carga un usuario desde la base de datos.
    Flask-Login usa esto para mantener la sesion.
    """
    return Usuario.query.get(int(user_id))