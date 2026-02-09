# -*- coding: utf-8 -*-
"""
Punto de entrada de la aplicación Flask.
Ejecutar con: python run.py
"""

import os
from app import create_app, socketio

# Determinar entorno (desarrollo o producción)
config_name = os.getenv('FLASK_ENV', 'development')
app = create_app(config_name)

if __name__ == '__main__':
    # En desarrollo
    socketio.run(
        app,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=(config_name == 'development')
    )