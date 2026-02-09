"""
Archivo principal para ejecutar la aplicación Flask.
Ejecutar con: python run.py
"""

from app import create_app, socketio
import os

# Seleccionar configuración según variable de entorno
config_name = os.environ.get('FLASK_ENV', 'development')
app = create_app(config_name)

if __name__ == '__main__':
    # Ejecutar con SocketIO para tiempo real
    socketio.run(
        app,
        debug=True,
        host='0.0.0.0',  # Accesible desde toda la red local
        port=5000,
        allow_unsafe_werkzeug=True  # Solo para desarrollo
    )