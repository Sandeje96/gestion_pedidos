# -*- coding: utf-8 -*-
"""
Script de DIAGNOSTICO y REPARACION de pedidos de sucursales.

Detecta y corrige los pedidos que no aparecen en el panel de Administracion
porque el cliente asociado no tiene ruta='SUCURSALES'.

Ejecutar con: python reparar_pedidos_sucursal.py
"""

import os
import sys
import io

# Forzar UTF-8 en stdout para Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models.pedido import Pedido
from app.models.cliente import Cliente

app = create_app()

with app.app_context():
    print("=" * 70)
    print("DIAGNOSTICO DE PEDIDOS DE SUCURSALES")
    print("=" * 70)

    # 1. Mostrar clientes con ruta SUCURSALES
    sucursales_ok = Cliente.query.filter_by(ruta='SUCURSALES').all()
    print(f"\n[OK] Clientes con ruta='SUCURSALES' ({len(sucursales_ok)}):")
    for c in sucursales_ok:
        total  = c.pedidos.count()
        activos = c.pedidos.filter_by(archivado=False).count()
        print(f"   ID={c.id:>4}  {c.nombre:<40}  pedidos activos={activos}  total={total}")

    # 2. Pedidos visibles en Administracion (logica actual)
    pedidos_visibles = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario.in_(['fabrica', 'admin_minorista', 'admin_mayorista']),
        Cliente.ruta == 'SUCURSALES'
    ).all()
    print(f"\n[OK] Pedidos ACTUALMENTE VISIBLES en Administracion: {len(pedidos_visibles)}")

    # 3. Buscar clientes NO marcados como SUCURSALES pero con pedidos activos
    clientes_problema = (
        db.session.query(Cliente)
        .join(Pedido)
        .filter(
            Pedido.archivado == False,
            Pedido.destinatario.in_(['fabrica', 'admin_minorista', 'admin_mayorista']),
            Cliente.ruta != 'SUCURSALES'
        )
        .distinct()
        .all()
    )

    print(f"\n[ADVERTENCIA] Clientes con pedidos activos pero ruta != 'SUCURSALES' ({len(clientes_problema)}):")

    if not clientes_problema:
        print("   Ninguno encontrado. Los datos parecen correctos.")
        print("\n   Si aun no ves pedidos en Administracion, verifica que:")
        print("   1. La aplicacion fue reiniciada con los nuevos cambios de codigo.")
        print("   2. Los pedidos no estan archivados.")
        print("   3. El destinatario del pedido es 'fabrica', 'admin_minorista' o 'admin_mayorista'.")
    else:
        for c in clientes_problema:
            afectados = c.pedidos.filter(
                Pedido.archivado == False,
                Pedido.destinatario.in_(['fabrica', 'admin_minorista', 'admin_mayorista'])
            ).count()
            print(f"   ID={c.id:>4}  {c.nombre:<40}  ruta='{c.ruta}'  pedidos afectados={afectados}")

    # 4. Mostrar todos los pedidos activos con su estado
    print("\n" + "=" * 70)
    print("TODOS LOS PEDIDOS ACTIVOS (no archivados):")
    print("=" * 70)
    todos = Pedido.query.filter_by(archivado=False).order_by(Pedido.fecha_creacion.desc()).all()
    if not todos:
        print("   No hay pedidos activos en la base de datos.")
    else:
        for p in todos:
            visible = (
                p.destinatario in ('fabrica', 'admin_minorista', 'admin_mayorista')
                and p.cliente.ruta == 'SUCURSALES'
            )
            estado_vis = "[VISIBLE]" if visible else "[OCULTO] "
            motivo = ""
            if not visible:
                if p.cliente.ruta != 'SUCURSALES':
                    motivo = f" <- cliente.ruta='{p.cliente.ruta}' (necesita 'SUCURSALES')"
                else:
                    motivo = f" <- destinatario='{p.destinatario}' no reconocido"
            print(f"   {estado_vis} Pedido #{p.id:<4} | {p.producto_nombre:<25} | dest='{p.destinatario:<15}' | estado='{p.estado:<10}' | cliente='{p.cliente.nombre}' | ruta='{p.cliente.ruta}'{motivo}")

    # 5. Ofrecer reparacion si hay problemas de datos
    if clientes_problema:
        print("\n" + "=" * 70)
        print("REPARACION DISPONIBLE")
        print("=" * 70)
        print(f"\nSe encontraron {len(clientes_problema)} cliente(s) con pedidos")
        print("que NO aparecen en Administracion porque su ruta no es 'SUCURSALES'.")
        print("\nEsto actualizara la ruta de esos clientes a 'SUCURSALES' para que")
        print("sus pedidos sean visibles en el panel de Administracion.")
        respuesta = input("\nEscribi 'SI' para confirmar la reparacion: ").strip().upper()

        if respuesta == 'SI':
            reparados = 0
            for c in clientes_problema:
                ruta_anterior = c.ruta
                c.ruta = 'SUCURSALES'
                reparados += 1
                print(f"   [OK] Cliente '{c.nombre}' (ID={c.id}): ruta '{ruta_anterior}' -> 'SUCURSALES'")
            db.session.commit()
            print(f"\n[OK] {reparados} cliente(s) actualizados exitosamente.")
            print("   Los pedidos ya deberian aparecer en el panel de Administracion.")
        else:
            print("\n   Operacion cancelada. No se realizaron cambios.")
    else:
        print("\n" + "=" * 70)
        if todos:
            print("\n[INFO] Si aun no ves los pedidos en Administracion, el problema")
            print("   podria ser que la app no fue reiniciada con el codigo actualizado.")
            print("   Reinicia la aplicacion y recarga el panel de Administracion.")
