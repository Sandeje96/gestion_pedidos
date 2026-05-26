import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

class Config:
    """Configuración base de la aplicación"""
    
    # Clave secreta para sesiones (Flask)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'clave-por-defecto-cambiar-en-produccion'
    
    # Base de datos — convertir URL al driver correcto (psycopg3)
    _db_url = os.environ.get('DATABASE_URL') or 'sqlite:///gestion_pedidos.db'
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif _db_url.startswith('postgresql://'):
        _db_url = _db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuración de sesión
    SESSION_COOKIE_SECURE = False  # En producción poner True (requiere HTTPS)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SQLALCHEMY_ECHO = False  # Mostrar consultas SQL en consola

class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    TESTING = False
    
    # Obtener DATABASE_URL
    database_url = os.getenv('DATABASE_URL', '')
    
    # Convertir postgres:// a postgresql+psycopg://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    
    SQLALCHEMY_DATABASE_URI = database_url or 'sqlite:///gestion_pedidos.db'

# Diccionario para seleccionar configuración
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}