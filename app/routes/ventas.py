# -*- coding: utf-8 -*-
"""
Blueprint para el panel de ventas (vendedores).
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db, socketio
from app.models.cliente import Cliente
from app.models.pedido import Pedido
from app.models.producto import Producto
from app.forms.cliente_forms import ClienteForm
from app.forms.pedido_forms import PedidoForm, EditarPedidoForm
from datetime import datetime
from functools import wraps

# Crear el Blueprint
ventas_bp = Blueprint('ventas', __name__)


def vendedor_requerido(f):
    """
    Decorador para verificar que el usuario sea vendedor.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_vendedor():
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@ventas_bp.route('/dashboard')
@vendedor_requerido
def dashboard():
    """
    Panel principal del vendedor.
    Muestra TODOS los clientes con sus pedidos agrupados por ruta (unificado para todos los vendedores).
    """
    
    # Obtener TODOS los clientes activos (sin filtrar por vendedor)
    clientes = Cliente.query.join(Pedido).filter(
        Cliente.activo == True,
        Pedido.archivado == False
    ).distinct().order_by(Cliente.ruta, Cliente.nombre).all()
    
    # Agrupar clientes por ruta
    from collections import defaultdict
    clientes_por_ruta = defaultdict(list)
    for cliente in clientes:
        clientes_por_ruta[cliente.ruta].append(cliente)
    
    # Convertir a dict normal y ordenar rutas
    clientes_por_ruta = dict(sorted(clientes_por_ruta.items()))
    
    # Estadísticas rápidas
    total_clientes = len(clientes)
    total_pedidos = Pedido.query.filter_by(archivado=False).count()
    pedidos_pendientes = Pedido.query.filter_by(archivado=False, estado='pendiente').count()
    pedidos_completados = Pedido.query.filter_by(archivado=False, estado='completado').count()
    
    # Contar notificaciones sin leer
    pedidos_no_leidos = Pedido.query.filter(
        Pedido.archivado == False,
        Pedido.observaciones_fabrica.isnot(None),
        Pedido.visto_por_vendedor == False
    ).count()
    
    return render_template(
        'ventas/dashboard.html',
        title='Panel de Ventas',
        clientes_por_ruta=clientes_por_ruta,  # <--- CAMBIO: enviar agrupados por ruta
        total_clientes=total_clientes,
        total_pedidos=total_pedidos,
        pedidos_pendientes=pedidos_pendientes,
        pedidos_completados=pedidos_completados,
        pedidos_no_leidos=pedidos_no_leidos,
        Pedido=Pedido
    )


@ventas_bp.route('/cliente/nuevo', methods=['GET', 'POST'])
@vendedor_requerido
def nuevo_cliente():
    """
    Crear un nuevo cliente.
    """
    form = ClienteForm()
    
    if form.validate_on_submit():
        # Crear nuevo cliente
        cliente = Cliente(
            nombre=form.nombre.data,
            telefono=form.telefono.data,
            direccion=form.direccion.data,
            ruta=form.ruta.data,
            notas=form.notas.data,
            creado_por_id=current_user.id
        )
        
        db.session.add(cliente)
        db.session.commit()
        
        flash(f'Cliente "{cliente.nombre}" creado exitosamente en {cliente.ruta}', 'success')
        return redirect(url_for('ventas.dashboard'))
    
    return render_template(
        'ventas/cliente_form.html',
        form=form,
        title='Nuevo Cliente',
        accion='Crear'
    )


@ventas_bp.route('/cliente/<int:cliente_id>/editar', methods=['GET', 'POST'])
@vendedor_requerido
def editar_cliente(cliente_id):
    """
    Editar un cliente existente.
    Cualquier vendedor puede editar cualquier cliente.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    
    form = ClienteForm(obj=cliente)
    
    if form.validate_on_submit():
        cliente.nombre = form.nombre.data
        cliente.telefono = form.telefono.data
        cliente.direccion = form.direccion.data
        cliente.ruta = form.ruta.data
        cliente.notas = form.notas.data
        cliente.fecha_actualizacion = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Cliente "{cliente.nombre}" actualizado exitosamente', 'success')
        return redirect(url_for('ventas.dashboard'))
    
    return render_template(
        'ventas/cliente_form.html',
        form=form,
        title='Editar Cliente',
        accion='Actualizar',
        cliente=cliente
    )


@ventas_bp.route('/pedido/nuevo', methods=['GET', 'POST'])
@vendedor_requerido
def nuevo_pedido():
    """
    Crear uno o varios pedidos nuevos para un cliente.
    """
    form = PedidoForm()
    
    if request.method == 'POST':
        # Validar cliente
        cliente_id = request.form.get('cliente_id', type=int)
        
        if not cliente_id or cliente_id == 0:
            flash('Debes seleccionar un cliente', 'danger')
            return render_template('ventas/pedido_form.html', form=form, title='Nuevo Pedido', accion='Crear')
        
        # Obtener arrays de datos
        productos = request.form.getlist('productos[]')
        cantidades = request.form.getlist('cantidades[]')
        unidades = request.form.getlist('unidades[]')
        notas = request.form.getlist('notas[]')
        
        # Validar que haya al menos un producto
        productos_validos = [p for p in productos if p and p.strip()]
        
        if not productos_validos:
            flash('Debes agregar al menos un pedido con producto', 'warning')
            return render_template('ventas/pedido_form.html', form=form, title='Nuevo Pedido', accion='Crear')
        
        # Crear múltiples pedidos
        pedidos_creados = []
        
        for i in range(len(productos)):
            if productos[i] and productos[i].strip():  # Solo si hay producto
                try:
                    cantidad = float(cantidades[i]) if i < len(cantidades) and cantidades[i] else 1.0
                    unidad = unidades[i] if i < len(unidades) else 'unidades'
                    nota = notas[i] if i < len(notas) and notas[i] else None
                    
                    pedido = Pedido(
                        cliente_id=cliente_id,
                        producto_nombre=productos[i].strip(),
                        cantidad=cantidad,
                        unidad=unidad,
                        estado='pendiente',
                        notas_vendedor=nota,
                        modificado=False,
                        visto_por_fabrica=False,
                        esperando_contestacion=False
                    )
                    db.session.add(pedido)
                    pedidos_creados.append(pedido)
                    
                except Exception as e:
                    flash(f'Error en pedido #{i+1}: {str(e)}', 'danger')
                    db.session.rollback()
                    return render_template('ventas/pedido_form.html', form=form, title='Nuevo Pedido', accion='Crear')
        
        # Guardar todos los pedidos
        try:
            db.session.commit()
            
            # Emitir eventos de WebSocket para cada pedido
            for pedido in pedidos_creados:
                socketio.emit('nuevo_pedido', {
                    'pedido': pedido.to_dict()
                }, namespace='/')
            
            total_pedidos = len(pedidos_creados)
            cliente = Cliente.query.get(cliente_id)
            
            flash(f'✅ Se crearon {total_pedidos} pedido(s) para {cliente.nombre}', 'success')
            return redirect(url_for('ventas.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar pedidos: {str(e)}', 'danger')
            return render_template('ventas/pedido_form.html', form=form, title='Nuevo Pedido', accion='Crear')
    
    return render_template(
        'ventas/pedido_form.html',
        form=form,
        title='Nuevo Pedido',
        accion='Crear'
    )


@ventas_bp.route('/pedido/<int:pedido_id>/editar', methods=['GET', 'POST'])
@vendedor_requerido
def editar_pedido(pedido_id):
    """
    Editar un pedido existente.
    Cualquier vendedor puede editar cualquier pedido.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Guardar valores anteriores para detectar cambios
    notas_anteriores = pedido.notas_vendedor
    
    form = PedidoForm(obj=pedido)
    
    if form.validate_on_submit():
        pedido.producto_nombre = form.producto_nombre.data
        pedido.cantidad = form.cantidad.data
        pedido.unidad = form.unidad.data
        pedido.notas_vendedor = form.notas_vendedor.data
        
        # Si cambió algo, marcar como modificado
        pedido.modificado = True
        pedido.visto_por_fabrica = False
        
        # Si el vendedor respondió (agregó o cambió notas), quitar "esperando contestación"
        if form.notas_vendedor.data and form.notas_vendedor.data != notas_anteriores:
            pedido.esperando_contestacion = False
        
        pedido.fecha_actualizacion = datetime.utcnow()
        
        db.session.commit()
        
        # Emitir evento de WebSocket
        socketio.emit('pedido_modificado', {
            'pedido': pedido.to_dict()
        }, namespace='/')
        
        flash('Pedido actualizado correctamente', 'success')
        return redirect(url_for('ventas.dashboard'))
    
    return render_template(
        'ventas/editar_pedido.html',
        form=form,
        pedido=pedido,
        title='Editar Pedido'
    )


@ventas_bp.route('/pedido/<int:pedido_id>/eliminar', methods=['POST'])
@vendedor_requerido
def eliminar_pedido(pedido_id):
    """
    Eliminar un pedido.
    Cualquier vendedor puede eliminar cualquier pedido.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Guardar datos antes de eliminar
    pedido_info = {
        'id': pedido.id,
        'producto_nombre': pedido.producto_nombre,
        'cliente_id': pedido.cliente_id
    }
    
    # Eliminar el pedido
    db.session.delete(pedido)
    db.session.commit()
    
    # Emitir evento WebSocket
    socketio.emit('pedido_eliminado', {
        'pedido_id': pedido_info['id'],
        'cliente_id': pedido_info['cliente_id']
    }, namespace='/')
    
    flash(f'Pedido eliminado correctamente', 'success')
    return redirect(url_for('ventas.dashboard'))

@ventas_bp.route('/pedido/<int:pedido_id>/marcar-leido', methods=['POST'])
@vendedor_requerido
def marcar_pedido_leido(pedido_id):
    """
    Marcar las observaciones de fábrica como leídas por el vendedor.
    Cualquier vendedor puede marcar como leído.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Marcar como visto
    pedido.marcar_como_visto_por_vendedor()
    pedido.esperando_contestacion = False  # <--- AGREGAR ESTA LÍNEA
    db.session.commit()
    
    return jsonify({'success': True, 'pedido_id': pedido.id})

@ventas_bp.route('/cerrar-semana', methods=['POST'])
@vendedor_requerido
def cerrar_semana():
    """
    Cierra la semana actual archivando todos los pedidos activos.
    """
    from datetime import datetime
    
    # Generar nombre de semana (Ej: "Semana 2026-1F")
    fecha_actual = datetime.utcnow()

    # Obtener mes
    mes_numero = fecha_actual.month
    meses_letras = {
        1: 'E',   # Enero
        2: 'F',   # Febrero
        3: 'M',   # Marzo
        4: 'A',   # Abril
        5: 'MY',  # Mayo
        6: 'JN',  # Junio
        7: 'JL',  # Julio
        8: 'AG',  # Agosto
        9: 'S',   # Septiembre
        10: 'O',  # Octubre
        11: 'N',  # Noviembre
        12: 'D'   # Diciembre
    }
    mes_letra = meses_letras[mes_numero]

    # Calcular número de semana dentro del mes
    dia_del_mes = fecha_actual.day
    numero_semana_mes = ((dia_del_mes - 1) // 7) + 1

    # Formato: Semana YYYY-#L (ej: Semana 2026-1F)
    nombre_semana = f"Semana {fecha_actual.year}-{numero_semana_mes}{mes_letra}"
    
    # Obtener todos los pedidos no archivados
    pedidos_activos = Pedido.query.filter_by(archivado=False).all()
    
    if not pedidos_activos:
        flash('No hay pedidos activos para archivar', 'warning')
        return redirect(url_for('ventas.dashboard'))
    
    # Archivar todos los pedidos
    total_archivados = 0
    for pedido in pedidos_activos:
        pedido.archivar(nombre_semana)
        total_archivados += 1
    
    db.session.commit()
    
    # Emitir evento de WebSocket para notificar a fábrica
    socketio.emit('semana_cerrada', {
        'semana': nombre_semana,
        'total_archivados': total_archivados,
        'mensaje': f'Se archivaron {total_archivados} pedidos de {nombre_semana}'
    }, namespace='/')
    
    flash(f'✅ Semana cerrada: {total_archivados} pedidos archivados en "{nombre_semana}"', 'success')
    return redirect(url_for('ventas.dashboard'))


@ventas_bp.route('/historial-semanas')
@vendedor_requerido
def historial_semanas():
    """
    Muestra el historial de semanas cerradas.
    """
    from datetime import datetime
    
    # Obtener semanas únicas de pedidos archivados
    semanas = db.session.query(
        Pedido.semana_archivado,
        db.func.count(Pedido.id).label('total_pedidos'),
        db.func.min(Pedido.fecha_archivado).label('fecha')
    ).filter(
        Pedido.archivado == True
    ).group_by(
        Pedido.semana_archivado
    ).order_by(
        db.desc('fecha')
    ).all()
    
    return render_template(
        'ventas/historial_semanas.html',
        title='Historial de Semanas',
        semanas=semanas,
        now=datetime.utcnow()  # <--- AGREGAR ESTO
    )


@ventas_bp.route('/ver-semana/<string:semana>')
@vendedor_requerido
def ver_semana(semana):
    """
    Ver los pedidos de una semana archivada específica.
    """
    # Obtener pedidos de esa semana agrupados por ruta
    clientes_con_pedidos = Cliente.query.join(Pedido).filter(
        Pedido.semana_archivado == semana
    ).distinct().order_by(Cliente.ruta, Cliente.nombre).all()
    
    # Agrupar por ruta
    from collections import defaultdict
    clientes_por_ruta = defaultdict(list)
    for cliente in clientes_con_pedidos:
        clientes_por_ruta[cliente.ruta].append(cliente)
    
    clientes_por_ruta = dict(sorted(clientes_por_ruta.items()))
    
    return render_template(
        'ventas/ver_semana.html',
        title=f'Pedidos de {semana}',
        semana=semana,
        clientes_por_ruta=clientes_por_ruta,
        Pedido=Pedido
    )

@ventas_bp.route('/limpiar-pedidos-antiguos', methods=['POST'])
@vendedor_requerido
def limpiar_pedidos_antiguos():
    """
    Elimina pedidos archivados de más de 30 días.
    Esta acción la ejecuta manualmente el usuario.
    """
    from datetime import timedelta
    
    # Calcular fecha límite (hace 30 días)
    fecha_limite = datetime.utcnow() - timedelta(days=30)
    
    # Buscar pedidos archivados hace más de 30 días
    pedidos_antiguos = Pedido.query.filter(
        Pedido.archivado == True,
        Pedido.fecha_archivado < fecha_limite
    ).all()
    
    if not pedidos_antiguos:
        flash('No hay pedidos antiguos para eliminar (mayores a 30 días)', 'info')
        return redirect(url_for('ventas.historial_semanas'))
    
    # Contar por semana
    semanas_afectadas = {}
    for pedido in pedidos_antiguos:
        semana = pedido.semana_archivado or "Sin semana"
        if semana not in semanas_afectadas:
            semanas_afectadas[semana] = 0
        semanas_afectadas[semana] += 1
    
    total_eliminados = len(pedidos_antiguos)
    
    # Eliminar pedidos
    for pedido in pedidos_antiguos:
        db.session.delete(pedido)
    
    db.session.commit()
    
    # Crear mensaje detallado
    mensaje_detalle = f"Se eliminaron {total_eliminados} pedidos antiguos: "
    mensaje_detalle += ", ".join([f"{sem} ({cant})" for sem, cant in semanas_afectadas.items()])
    
    flash(f'✅ {mensaje_detalle}', 'success')
    return redirect(url_for('ventas.historial_semanas'))

@ventas_bp.route('/api/cliente/<int:cliente_id>/info')
@vendedor_requerido
def api_cliente_info(cliente_id):
    """
    API: Obtener información básica de un cliente.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    
    return jsonify({
        'id': cliente.id,
        'nombre': cliente.nombre,
        'telefono': cliente.telefono,
        'direccion': cliente.direccion,
        'ruta': cliente.ruta
    })


@ventas_bp.route('/api/cliente/<int:cliente_id>/pedidos')
@vendedor_requerido
def api_cliente_pedidos(cliente_id):
    """
    API: Obtener los pedidos de un cliente.
    Todos los vendedores pueden ver todos los pedidos.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    
    pedidos = Pedido.query.filter_by(cliente_id=cliente_id).order_by(Pedido.fecha_creacion.desc()).all()
    
    return jsonify({
        'cliente': cliente.to_dict(),
        'pedidos': [p.to_dict() for p in pedidos]
    })