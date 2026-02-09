# -*- coding: utf-8 -*-
"""
Script para cargar datos de prueba en la base de datos.
Ejecutar con: python seed_db.py
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.producto import Producto
from app.models.pedido import Pedido


def seed_database():
    """
    Carga datos de prueba en la base de datos.
    """
    print("=" * 60)
    print("CARGANDO DATOS DE PRUEBA")
    print("=" * 60)
    
    app = create_app('development')
    
    with app.app_context():
        try:
            # CREAR USUARIOS
            print("\nCreando usuarios...")
            
            vendedor1 = Usuario(
                nombre="Juan Perez",
                username="juan",
                email="juan@ejemplo.com",
                rol="vendedor",
                activo=True
            )
            vendedor1.set_password("123456")
            db.session.add(vendedor1)
            
            vendedor2 = Usuario(
                nombre="Maria Gonzalez",
                username="maria",
                email="maria@ejemplo.com",
                rol="vendedor",
                activo=True
            )
            vendedor2.set_password("123456")
            db.session.add(vendedor2)
            
            operario1 = Usuario(
                nombre="Carlos Rodriguez",
                username="carlos",
                email="carlos@ejemplo.com",
                rol="operario",
                activo=True
            )
            operario1.set_password("123456")
            db.session.add(operario1)
            
            operario2 = Usuario(
                nombre="Ana Martinez",
                username="ana",
                email="ana@ejemplo.com",
                rol="operario",
                activo=True
            )
            operario2.set_password("123456")
            db.session.add(operario2)
            
            operario3 = Usuario(
                nombre="Luis Fernandez",
                username="luis",
                email="luis@ejemplo.com",
                rol="operario",
                activo=True
            )
            operario3.set_password("123456")
            db.session.add(operario3)
            
            db.session.commit()
            print("OK - Usuarios creados:")
            print("   - juan / 123456 (Vendedor)")
            print("   - maria / 123456 (Vendedor)")
            print("   - carlos / 123456 (Operario)")
            print("   - ana / 123456 (Operario)")
            print("   - luis / 123456 (Operario)")
            
            # CREAR PRODUCTOS
            print("\nCreando productos...")
            
            productos_data = [
                {"nombre": "Pan Integral", "descripcion": "Pan de harina integral", "precio": 350.00, "unidad": "kg"},
                {"nombre": "Pan de Campo", "descripcion": "Pan tradicional de campo", "precio": 300.00, "unidad": "kg"},
                {"nombre": "Facturas", "descripcion": "Medialunas y facturas variadas", "precio": 150.00, "unidad": "docena"},
                {"nombre": "Medialunas", "descripcion": "Medialunas de manteca", "precio": 120.00, "unidad": "docena"},
                {"nombre": "Bizcochos", "descripcion": "Bizcochos caseros", "precio": 180.00, "unidad": "docena"},
            ]
            
            for producto_data in productos_data:
                producto = Producto(**producto_data)
                db.session.add(producto)
            
            db.session.commit()
            print("OK - " + str(len(productos_data)) + " productos creados")
            
            # CREAR CLIENTES
            print("\nCreando clientes...")
            
            cliente1 = Cliente(
                nombre="Panaderia El Sol",
                telefono="+54 9 376 123-4567",
                direccion="Av. Corrientes 1234, Posadas",
                notas="Cliente preferencial",
                creado_por_id=vendedor1.id
            )
            db.session.add(cliente1)
            
            cliente2 = Cliente(
                nombre="Supermercado La Esquina",
                telefono="+54 9 376 234-5678",
                direccion="Calle San Martin 456, Posadas",
                notas="Pedidos grandes",
                creado_por_id=vendedor1.id
            )
            db.session.add(cliente2)
            
            cliente3 = Cliente(
                nombre="Despensa Don Pedro",
                telefono="+54 9 376 345-6789",
                direccion="Av. Mitre 789, Posadas",
                creado_por_id=vendedor2.id
            )
            db.session.add(cliente3)
            
            db.session.commit()
            print("OK - 3 clientes creados")
            
            # CREAR PEDIDOS
            print("\nCreando pedidos...")
            
            pedido1 = Pedido(
                cliente_id=cliente1.id,
                producto_nombre="Pan Integral",
                cantidad=10,
                unidad="kg",
                estado="pendiente",
                notas_vendedor="Entregar antes de las 7am"
            )
            db.session.add(pedido1)
            
            pedido2 = Pedido(
                cliente_id=cliente1.id,
                producto_nombre="Facturas",
                cantidad=5,
                unidad="docenas",
                estado="en_proceso",
                operario_id=operario1.id
            )
            db.session.add(pedido2)
            
            pedido3 = Pedido(
                cliente_id=cliente2.id,
                producto_nombre="Pan de Campo",
                cantidad=15,
                unidad="kg",
                estado="pendiente",
                modificado=True
            )
            db.session.add(pedido3)
            
            pedido4 = Pedido(
                cliente_id=cliente3.id,
                producto_nombre="Medialunas",
                cantidad=8,
                unidad="docenas",
                estado="completado",
                operario_id=operario2.id,
                observaciones_fabrica="Completado y empaquetado",
                fecha_completado=datetime.utcnow()
            )
            db.session.add(pedido4)
            
            db.session.commit()
            print("OK - 4 pedidos creados")
            
            print("\n" + "=" * 60)
            print("DATOS DE PRUEBA CARGADOS EXITOSAMENTE")
            print("=" * 60)
            
            print("\nRESUMEN:")
            print("   - Usuarios: " + str(Usuario.query.count()))
            print("   - Clientes: " + str(Cliente.query.count()))
            print("   - Productos: " + str(Producto.query.count()))
            print("   - Pedidos: " + str(Pedido.query.count()))
            
            print("\nCREDENCIALES DE ACCESO:")
            print("\n   VENDEDORES:")
            print("   - juan / 123456")
            print("   - maria / 123456")
            print("\n   OPERARIOS:")
            print("   - carlos / 123456")
            print("   - ana / 123456")
            print("   - luis / 123456")
            
            print("\nSIGUIENTE PASO:")
            print("   Ejecuta: python run.py")
            print("   Luego ingresa a: http://localhost:5000\n")
            
        except Exception as e:
            db.session.rollback()
            print("\nERROR al cargar datos de prueba:")
            print("   " + str(e))
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    seed_database()