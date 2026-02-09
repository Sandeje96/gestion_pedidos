# -*- coding: utf-8 -*-
"""
Script para eliminar pedidos archivados de más de 1 mes.
Ejecutar este script periódicamente (por ejemplo, una vez al día con cron/task scheduler).
"""

from app import create_app, db
from app.models.pedido import Pedido
from datetime import datetime, timedelta

app = create_app('development')

with app.app_context():
    try:
        # Calcular fecha límite (hace 1 mes)
        fecha_limite = datetime.utcnow() - timedelta(days=30)
        
        print(f"Buscando pedidos archivados antes de: {fecha_limite.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Buscar pedidos archivados hace más de 1 mes
        pedidos_antiguos = Pedido.query.filter(
            Pedido.archivado == True,
            Pedido.fecha_archivado < fecha_limite
        ).all()
        
        if not pedidos_antiguos:
            print("No hay pedidos antiguos para eliminar.")
        else:
            total_eliminados = len(pedidos_antiguos)
            
            # Agrupar por semana para mostrar info
            semanas_eliminadas = {}
            for pedido in pedidos_antiguos:
                semana = pedido.semana_archivado or "Sin semana"
                if semana not in semanas_eliminadas:
                    semanas_eliminadas[semana] = 0
                semanas_eliminadas[semana] += 1
            
            # Eliminar pedidos
            for pedido in pedidos_antiguos:
                db.session.delete(pedido)
            
            db.session.commit()
            
            print(f"\n✅ Se eliminaron {total_eliminados} pedidos antiguos:")
            for semana, cantidad in semanas_eliminadas.items():
                print(f"   - {semana}: {cantidad} pedidos")
            
            print(f"\nEspacio liberado en la base de datos.")
        
    except Exception as e:
        print(f"\n❌ Error al limpiar pedidos antiguos:")
        print(f"   {str(e)}")
        db.session.rollback()