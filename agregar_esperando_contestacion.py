# -*- coding: utf-8 -*-
from app import create_app, db
from sqlalchemy import text

app = create_app('development')

with app.app_context():
    try:
        db.session.execute(text(
            "ALTER TABLE pedidos ADD COLUMN esperando_contestacion BOOLEAN DEFAULT 0 NOT NULL"
        ))
        db.session.commit()
        print("Columna 'esperando_contestacion' agregada exitosamente")
    except Exception as e:
        print(f"Error: {e}")
        db.session.rollback()