# -*- coding: utf-8 -*-
"""
Script para resetear completamente la base de datos.
CUIDADO! Esto eliminara TODOS los datos.
Ejecutar con: python reset_db.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db


def reset_database():
    """
    Resetea completamente la base de datos.
    """
    print("\n" + "=" * 60)
    print("ADVERTENCIA: RESETEO COMPLETO DE BASE DE DATOS")
    print("=" * 60)
    print("\nEsto eliminara TODOS los datos existentes.")
    
    respuesta = input("\nEstas seguro? Escribe 'SI' para continuar: ")
    
    if respuesta.upper() != 'SI':
        print("\nOperacion cancelada")
        return
    
    app = create_app('development')
    
    with app.app_context():
        try:
            print("\nEliminando base de datos...")
            
            # Eliminar archivo de base de datos SQLite si existe
            if os.path.exists('gestion_pedidos.db'):
                os.remove('gestion_pedidos.db')
                print("OK - Archivo de base de datos eliminado")
            
            # Eliminar todas las tablas
            db.drop_all()
            print("OK - Tablas eliminadas")
            
            # Recrear todas las tablas
            db.create_all()
            print("OK - Tablas recreadas")
            
            print("\n" + "=" * 60)
            print("BASE DE DATOS RESETEADA CORRECTAMENTE")
            print("=" * 60)
            print("\nAhora ejecuta: python seed_db.py")
            print("Para cargar datos de prueba\n")
            
        except Exception as e:
            print("\nERROR al resetear la base de datos:")
            print("   " + str(e))
            sys.exit(1)


if __name__ == '__main__':
    reset_database()