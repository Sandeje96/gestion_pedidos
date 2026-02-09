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
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(ventas_bp, url_prefix='/ventas')
    app.register_blueprint(fabrica_bp, url_prefix='/fabrica')
    
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