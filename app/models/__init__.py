# -*- coding: utf-8 -*-
"""
Modelos de la aplicacion.
Aqui se importan todos los modelos para facilitar su uso.
"""

from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.pedido import Pedido
from app.models.producto import Producto

__all__ = ['Usuario', 'Cliente', 'Pedido', 'Producto']