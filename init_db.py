# -*- coding: utf-8 -*-
"""
Script para inicializar la base de datos.
Ejecutar con: python init_db.py
"""

import os
import sys

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.producto import Producto
from app.models.pedido import Pedido


def init_database():
    """
    Inicializa la base de datos creando todas las tablas.
    """
    print("=" * 60)
    print("INICIALIZANDO BASE DE DATOS")
    print("=" * 60)
    
    # Crear la aplicacion
    app = create_app('development')
    
    with app.app_context():
        try:
            # Eliminar todas las tablas existentes
            print("\nEliminando tablas existentes...")
            db.drop_all()
            print("OK - Tablas eliminadas")
            
            # Crear todas las tablas
            print("\nCreando nuevas tablas...")
            db.create_all()
            print("OK - Tablas creadas exitosamente")
            
            # Verificar tablas creadas
            print("\nTablas creadas:")
            inspector = db.inspect(db.engine)
            for table_name in inspector.get_table_names():
                print("   - " + table_name)
            
            print("\n" + "=" * 60)
            print("BASE DE DATOS INICIALIZADA CORRECTAMENTE")
            print("=" * 60)
            print("\nAhora puedes ejecutar: python seed_db.py")
            print("Para cargar datos de prueba\n")
            
        except Exception as e:
            print("\nERROR al inicializar la base de datos:")
            print("   " + str(e))
            sys.exit(1)


if __name__ == '__main__':
    init_database()