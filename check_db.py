# -*- coding: utf-8 -*-
"""
Script para verificar el contenido de la base de datos.
Ejecutar con: python check_db.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.producto import Producto
from app.models.pedido import Pedido


def check_database():
    """
    Muestra el contenido actual de la base de datos.
    """
    print("\n" + "=" * 60)
    print("VERIFICACION DE BASE DE DATOS")
    print("=" * 60)
    
    app = create_app('development')
    
    with app.app_context():
        try:
            # Verificar usuarios
            usuarios = Usuario.query.all()
            print("\nUSUARIOS (" + str(len(usuarios)) + "):")
            for u in usuarios:
                print("   - " + u.nombre + " (@" + u.username + ") - " + u.rol)
            
            # Verificar clientes
            clientes = Cliente.query.all()
            print("\nCLIENTES (" + str(len(clientes)) + "):")
            for c in clientes:
                print("   - " + c.nombre + " - Pedidos: " + str(c.pedidos.count()))
            
            # Verificar productos
            productos = Producto.query.all()
            print("\nPRODUCTOS (" + str(len(productos)) + "):")
            for p in productos:
                print("   - " + p.nombre + " - $" + str(p.precio) + "/" + str(p.unidad))
            
            # Verificar pedidos
            pedidos = Pedido.query.all()
            print("\nPEDIDOS (" + str(len(pedidos)) + "):")
            print("   - Pendientes: " + str(Pedido.query.filter_by(estado='pendiente').count()))
            print("   - En Proceso: " + str(Pedido.query.filter_by(estado='en_proceso').count()))
            print("   - Completados: " + str(Pedido.query.filter_by(estado='completado').count()))
            print("   - Modificados: " + str(Pedido.query.filter_by(modificado=True).count()))
            
            print("\n" + "=" * 60)
            print("VERIFICACION COMPLETADA")
            print("=" * 60 + "\n")
            
        except Exception as e:
            print("\nERROR al verificar la base de datos:")
            print("   " + str(e))
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    check_database()