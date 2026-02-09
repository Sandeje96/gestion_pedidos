# -*- coding: utf-8 -*-
"""
Script para agregar campos de archivado a pedidos
"""
from app import create_app, db
from sqlalchemy import text

app = create_app('development')

with app.app_context():
    try:
        # Agregar columnas de archivado
        db.session.execute(text(
            "ALTER TABLE pedidos ADD COLUMN archivado BOOLEAN DEFAULT 0 NOT NULL"
        ))
        db.session.execute(text(
            "ALTER TABLE pedidos ADD COLUMN fecha_archivado DATETIME"
        ))
        db.session.execute(text(
            "ALTER TABLE pedidos ADD COLUMN semana_archivado VARCHAR(50)"
        ))
        
        # Crear índice para consultas rápidas
        db.session.execute(text(
            "CREATE INDEX idx_pedidos_archivado ON pedidos(archivado)"
        ))
        
        db.session.commit()
        print("Columnas de archivado agregadas exitosamente")
        
    except Exception as e:
        print(f"Error: {e}")
        db.session.rollback()