# -*- coding: utf-8 -*-
"""
Script para crear tabla de mensajes de pedido
"""
from app import create_app, db
from app.models.mensaje_pedido import MensajePedido

app = create_app('development')

with app.app_context():
    try:
        # Crear tabla
        db.create_all()
        print("✅ Tabla 'mensajes_pedido' creada exitosamente")
    except Exception as e:
        print(f"❌ Error: {e}")