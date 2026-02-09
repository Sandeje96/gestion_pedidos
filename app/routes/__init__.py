# -*- coding: utf-8 -*-
"""
Blueprints (rutas) de la aplicacion.
"""

from app.routes.auth import auth_bp
from app.routes.ventas import ventas_bp
from app.routes.fabrica import fabrica_bp

__all__ = ['auth_bp', 'ventas_bp', 'fabrica_bp']