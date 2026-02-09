# -*- coding: utf-8 -*-
"""
Script para agregar columna ruta a clientes
"""
from app import create_app, db
from sqlalchemy import text

app = create_app('development')

with app.app_context():
    try:
        # Agregar columna ruta
        db.session.execute(text(
            "ALTER TABLE clientes ADD COLUMN ruta VARCHAR(50) DEFAULT 'Ruta 14' NOT NULL"
        ))
        db.session.commit()
        print("Columna 'ruta' agregada exitosamente a la tabla clientes")
        
    except Exception as e:
        print(f"Error: {e}")
        db.session.rollback()