# -*- coding: utf-8 -*-
"""
Script de diagnóstico: muestra los pedidos recientes de sucursales
y por qué podrían no aparecer en el panel de Administración.
Ejecutar con: python diagnostico_pedido.py
"""

from app import create_app, db
from app.models.pedido import Pedido
from app.models.cliente import Cliente

app = create_app()

with app.app_context():
    print("=" * 70)
    print("DIAGNÓSTICO: Pedidos de SUCURSALES (últimos 20, no archivados)")
    print("=" * 70)

    pedidos = (
        Pedido.query
        .join(Cliente)
        .filter(Pedido.archivado == False)
        .order_by(Pedido.fecha_creacion.desc())
        .limit(20)
        .all()
    )

    if not pedidos:
        print("No hay pedidos activos en la base de datos.")
    else:
        for p in pedidos:
            visible_admin = (
                p.destinatario in ('admin_minorista', 'admin_mayorista')
                and p.cliente.ruta == 'SUCURSALES'
            )
            visible_fabrica = (
                p.destinatario == 'fabrica'
                and p.cliente.ruta == 'SUCURSALES'
            )
            print(f"\nPedido #{p.id}")
            print(f"  Producto    : {p.producto_nombre}")
            print(f"  Cliente     : {p.cliente.nombre}")
            print(f"  Ruta cliente: {p.cliente.ruta}")
            print(f"  Destinatario: {p.destinatario}")
            print(f"  Estado      : {p.estado}")
            print(f"  Archivado   : {p.archivado}")
            print(f"  Fecha       : {p.fecha_creacion}")
            if visible_admin:
                print(f"  >>> VISIBLE en panel ADMINISTRACIÓN ✅")
            elif visible_fabrica:
                print(f"  >>> VISIBLE en panel FÁBRICA (destinatario='fabrica') ⚠️")
            else:
                print(f"  >>> NO VISIBLE en ningún panel de fábrica/admin ❌")
                if p.cliente.ruta != 'SUCURSALES':
                    print(f"      CAUSA: cliente.ruta='{p.cliente.ruta}' (necesita 'SUCURSALES')")
                if p.destinatario not in ('admin_minorista', 'admin_mayorista', 'fabrica'):
                    print(f"      CAUSA: destinatario='{p.destinatario}' no reconocido")

    print("\n" + "=" * 70)
    print("CLIENTES con ruta SUCURSALES:")
    print("=" * 70)
    sucursales = Cliente.query.filter_by(ruta='SUCURSALES').all()
    if sucursales:
        for c in sucursales:
            print(f"  ID={c.id}  {c.nombre}")
    else:
        print("  ¡NINGÚN cliente tiene ruta='SUCURSALES'!")
