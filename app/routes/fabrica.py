# -*- coding: utf-8 -*-
"""
Blueprint para el panel de fábrica (operarios).
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db, socketio
from app.models.pedido import Pedido
from app.models.cliente import Cliente
from app.models.usuario import Usuario
from app.forms.pedido_forms import ActualizarPedidoFabricaForm
from datetime import datetime
from functools import wraps

# Crear el Blueprint
fabrica_bp = Blueprint('fabrica', __name__)


def operario_requerido(f):
    """
    Decorador para verificar que el usuario sea operario.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_operario():
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@fabrica_bp.route('/dashboard')
@operario_requerido
def dashboard():
    """
    Panel principal de la fábrica.
    Muestra todos los pedidos agrupados por ruta.
    """
    
    # Obtener todos los clientes que tienen pedidos, agrupados por ruta
    clientes_con_pedidos = Cliente.query.join(Pedido).filter(
        Pedido.archivado == False
    ).distinct().order_by(Cliente.ruta, Cliente.nombre).all()
    
    # Agrupar clientes por ruta
    from collections import defaultdict
    clientes_por_ruta = defaultdict(list)
    for cliente in clientes_con_pedidos:
        clientes_por_ruta[cliente.ruta].append(cliente)
    
    # Convertir a dict normal y ordenar rutas
    clientes_por_ruta = dict(sorted(clientes_por_ruta.items()))
    
    # Estadísticas generales
    total_pendientes = Pedido.query.filter_by(archivado=False, estado='pendiente').count()
    total_completados = Pedido.query.filter_by(archivado=False, estado='completado').count()
    total_cancelados = Pedido.query.filter_by(archivado=False, estado='cancelado').count()
    pedidos_modificados = Pedido.query.filter_by(archivado=False, modificado=True, visto_por_fabrica=False).count()
    
    # Pedidos con cambios sin ver
    pedidos_modificados = Pedido.query.filter_by(modificado=True, visto_por_fabrica=False).count()
    
    # Obtener operarios para asignación
    operarios = Usuario.query.filter_by(rol='operario', activo=True).all()
    
    # Calcular notificaciones por ruta
    notificaciones_por_ruta = {}
    for ruta in clientes_por_ruta.keys():
        # Contar pedidos modificados sin ver en esta ruta
        count = db.session.query(Pedido).join(Cliente).filter(
            Cliente.ruta == ruta,
            Pedido.archivado == False,
            Pedido.modificado == True,
            Pedido.visto_por_fabrica == False
        ).count()
        notificaciones_por_ruta[ruta] = count
    
    return render_template(
        'fabrica/dashboard.html',
        title='Panel de Fabrica',
        clientes_por_ruta=clientes_por_ruta,  # <--- CAMBIO: enviar agrupados por ruta
        notificaciones_por_ruta=notificaciones_por_ruta,  # <--- NUEVO: notificaciones por ruta
        total_pendientes=total_pendientes,
        total_completados=total_completados,
        total_cancelados=total_cancelados,
        pedidos_modificados=pedidos_modificados,
        operarios=operarios,
        Pedido=Pedido
    )


@fabrica_bp.route('/pedido/<int:pedido_id>/actualizar', methods=['GET', 'POST'])
@operario_requerido
def actualizar_pedido(pedido_id):
    """
    Actualizar el estado de un pedido.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    form = ActualizarPedidoFabricaForm(obj=pedido)
    
    if form.validate_on_submit():
        # Actualizar pedido
        pedido.estado = form.estado.data
        pedido.operario_id = form.operario_id.data if form.operario_id.data else None
        pedido.observaciones_fabrica = form.observaciones_fabrica.data
        
        # Si se completó, registrar fecha
        if pedido.estado == 'completado' and not pedido.fecha_completado:
            pedido.marcar_como_completado()
        
        # Marcar como visto si estaba modificado
        if pedido.modificado:
            pedido.marcar_como_visto()
        
        # Si agregó o modificó observaciones, marcar como no visto por vendedor
        if form.observaciones_fabrica.data:
            pedido.visto_por_vendedor = False  # <--- ESTE ES EL CAMBIO
        
        db.session.commit()
        
        # Emitir evento de WebSocket
        socketio.emit('pedido_actualizado', {
            'pedido': pedido.to_dict()
        }, namespace='/')
        
        flash(f'Pedido actualizado a estado: {pedido.estado}', 'success')
        return redirect(url_for('fabrica.dashboard'))
    
    return render_template(
        'fabrica/actualizar_pedido.html',
        form=form,
        pedido=pedido,
        title='Actualizar Pedido'
    )


@fabrica_bp.route('/pedido/<int:pedido_id>/marcar-visto', methods=['POST'])
@operario_requerido
def marcar_pedido_visto(pedido_id):
    """
    Marcar un pedido modificado como visto por la fábrica.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Marcar como visto
    pedido.modificado = False
    pedido.visto_por_fabrica = True
    pedido.fecha_actualizacion = datetime.utcnow()
    
    db.session.commit()
    
    # Emitir evento WebSocket para notificar a ventas
    socketio.emit('pedido_visto_por_fabrica', {
        'pedido_id': pedido.id,
        'pedido': pedido.to_dict()
    }, namespace='/')
    
    return jsonify({
        'success': True,
        'message': 'Pedido marcado como visto'
    })


@fabrica_bp.route('/api/pedidos')
@operario_requerido
def obtener_todos_pedidos():
    """
    API para obtener todos los pedidos en formato JSON.
    """
    
    # Filtros opcionales
    estado = request.args.get('estado')
    cliente_id = request.args.get('cliente_id', type=int)
    
    query = Pedido.query
    
    if estado:
        query = query.filter_by(estado=estado)
    
    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)
    
    pedidos = query.order_by(Pedido.fecha_creacion.desc()).all()
    
    return jsonify({
        'pedidos': [p.to_dict() for p in pedidos],
        'total': len(pedidos)
    })


@fabrica_bp.route('/pedido/<int:pedido_id>/asignar-operario', methods=['POST'])
@operario_requerido
def asignar_operario(pedido_id):
    """
    Asignar un operario responsable a un pedido.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    operario_id = request.form.get('operario_id', type=int)
    
    if operario_id:
        operario = Usuario.query.get_or_404(operario_id)
        
        if not operario.es_operario():
            return jsonify({'error': 'El usuario no es operario'}), 400
        
        pedido.operario_id = operario_id
    else:
        pedido.operario_id = None
    
    db.session.commit()
    
    # Emitir evento
    socketio.emit('pedido_asignado', {
        'pedido': pedido.to_dict()
    }, namespace='/')
    
    return jsonify({'success': True, 'pedido': pedido.to_dict()})

@fabrica_bp.route('/pedido/<int:pedido_id>/actualizar-estado-rapido', methods=['POST'])
@operario_requerido
def actualizar_estado_rapido(pedido_id):
    """
    Actualizar solo el estado de un pedido rapidamente.
    """
    from flask import request, jsonify
    
    pedido = Pedido.query.get_or_404(pedido_id)
    
    data = request.get_json()
    nuevo_estado = data.get('estado')
    
    if not nuevo_estado:
        return jsonify({'success': False, 'error': 'Estado no proporcionado'}), 400
    
    # Validar que el estado sea válido
    estados_validos = ['pendiente', 'completado', 'cancelado']
    if nuevo_estado not in estados_validos:
        return jsonify({'success': False, 'error': 'Estado inválido'}), 400
    
    # Actualizar estado
    pedido.estado = nuevo_estado
    
    # Si se completó, registrar fecha
    if nuevo_estado == 'completado' and not pedido.fecha_completado:
        pedido.marcar_como_completado()
    
    # Marcar como visto si estaba modificado
    if pedido.modificado:
        pedido.marcar_como_visto()

    
    
    db.session.commit()
    
    # Emitir evento de WebSocket
    socketio.emit('pedido_actualizado', {
        'pedido': pedido.to_dict()
    }, namespace='/')
    
    return jsonify({
        'success': True,
        'pedido': pedido.to_dict()
    })