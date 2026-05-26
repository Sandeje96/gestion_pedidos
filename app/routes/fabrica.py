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
from app.models.producto import Producto
from app.models.produccion import ProduccionDiaria
from app.forms.pedido_forms import ActualizarPedidoFabricaForm
from datetime import datetime, date
from functools import wraps
from sqlalchemy import func

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

    # Calcular litros totales por ruta (pedidos no archivados y no cancelados)
    litros_por_ruta = {}
    for ruta in clientes_por_ruta.keys():
        total = db.session.query(func.sum(Pedido.cantidad)).join(Cliente).filter(
            Cliente.ruta == ruta,
            Pedido.archivado == False,
            Pedido.estado != 'cancelado'
        ).scalar()
        litros_por_ruta[ruta] = float(total) if total else 0.0

    return render_template(
        'fabrica/dashboard.html',
        title='Panel de Fabrica',
        clientes_por_ruta=clientes_por_ruta,
        notificaciones_por_ruta=notificaciones_por_ruta,
        litros_por_ruta=litros_por_ruta,
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
        # Guardar observaciones anteriores para comparar
        observaciones_anteriores = pedido.observaciones_fabrica
        
        # Actualizar pedido
        pedido.estado = form.estado.data
        pedido.operario_id = form.operario_id.data if form.operario_id.data else None
        pedido.observaciones_fabrica = form.observaciones_fabrica.data
        
        # Si se completó, registrar fecha
        if pedido.estado == 'completado' and not pedido.fecha_completado:
            pedido.marcar_como_completado()
            # Descontar stock si el pedido tiene producto vinculado
            if pedido.producto_id:
                producto = Producto.query.get(pedido.producto_id)
                if producto:
                    producto.descontar_stock(float(pedido.cantidad))
        
        # Marcar como visto si estaba modificado
        if pedido.modificado:
            pedido.marcar_como_visto()
        
        # NUEVO: Si agregó o modificó observaciones, guardar mensaje
        if form.observaciones_fabrica.data and form.observaciones_fabrica.data != observaciones_anteriores:
            from app.models.mensaje_pedido import MensajePedido
            
            mensaje = MensajePedido(
                pedido_id=pedido.id,
                usuario_id=current_user.id,
                mensaje=form.observaciones_fabrica.data,
                tipo='fabrica',
                leido=False
            )
            db.session.add(mensaje)
            pedido.visto_por_vendedor = False
            pedido.esperando_contestacion = True
        
        db.session.commit()
        
        # Emitir evento de WebSocket
        socketio.emit('pedido_actualizado', {
            'pedido': pedido.to_dict(),
            'mensaje': f'Pedido #{pedido.id} actualizado'
        }, namespace='/')
        
        flash(f'Pedido actualizado a estado: {pedido.estado}', 'success')
        return redirect(url_for('fabrica.dashboard'))
    
    return render_template(
        'fabrica/actualizar_pedido.html',
        form=form,
        pedido=pedido,
        title='Actualizar Pedido'
    )

@fabrica_bp.route('/pedido/<int:pedido_id>/mensajes')
@operario_requerido
def ver_mensajes_pedido(pedido_id):
    """
    Ver historial de mensajes de un pedido.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    from app.models.mensaje_pedido import MensajePedido
    mensajes = MensajePedido.query.filter_by(pedido_id=pedido_id).order_by(MensajePedido.fecha_creacion.asc()).all()
    
    return render_template(
        'fabrica/mensajes_pedido.html',
        pedido=pedido,
        mensajes=mensajes,
        title=f'Conversación - Pedido #{pedido.id}'
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
        # Descontar stock si el pedido tiene producto vinculado
        if pedido.producto_id:
            producto = Producto.query.get(pedido.producto_id)
            if producto:
                producto.descontar_stock(float(pedido.cantidad))
    
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


# ─────────────────────────────────────────────
# SECCIÓN: PRODUCCIÓN DIARIA Y STOCK
# ─────────────────────────────────────────────

@fabrica_bp.route('/produccion', methods=['GET', 'POST'])
@operario_requerido
def produccion():
    """
    Ver y cargar producción diaria.
    GET: muestra historial filtrado por fecha.
    POST: registra una nueva producción y suma al stock del producto.
    """
    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        cantidad = request.form.get('cantidad', type=float)
        unidad = request.form.get('unidad', '').strip()
        fecha_str = request.form.get('fecha_produccion', '').strip()
        observaciones = request.form.get('observaciones', '').strip() or None

        # Validaciones básicas
        if not producto_id or not cantidad or not unidad:
            flash('Producto, cantidad y unidad son obligatorios.', 'danger')
            return redirect(url_for('fabrica.produccion'))

        if cantidad <= 0:
            flash('La cantidad debe ser mayor a cero.', 'danger')
            return redirect(url_for('fabrica.produccion'))

        producto = Producto.query.get_or_404(producto_id)

        # Parsear fecha
        try:
            fecha_prod = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else date.today()
        except ValueError:
            fecha_prod = date.today()

        # Crear registro de producción
        prod = ProduccionDiaria(
            producto_id=producto_id,
            cantidad=cantidad,
            unidad=unidad,
            fecha_produccion=fecha_prod,
            usuario_id=current_user.id,
            observaciones=observaciones
        )
        db.session.add(prod)

        # Sumar al stock actual del producto
        producto.agregar_stock(cantidad)

        db.session.commit()
        flash(f'✅ Se registraron {cantidad} {unidad} de {producto.nombre}.', 'success')
        return redirect(url_for('fabrica.produccion'))

    # GET: filtrar por fecha
    fecha_filtro_str = request.args.get('fecha', date.today().isoformat())
    try:
        fecha_filtro = datetime.strptime(fecha_filtro_str, '%Y-%m-%d').date()
    except ValueError:
        fecha_filtro = date.today()

    producciones = ProduccionDiaria.query.filter(
        ProduccionDiaria.fecha_produccion == fecha_filtro
    ).order_by(ProduccionDiaria.fecha_creacion.desc()).all()

    # Total producido por producto en ese día
    totales_dia = db.session.query(
        ProduccionDiaria.producto_id,
        func.sum(ProduccionDiaria.cantidad).label('total')
    ).filter(
        ProduccionDiaria.fecha_produccion == fecha_filtro
    ).group_by(ProduccionDiaria.producto_id).all()

    productos = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()

    return render_template(
        'fabrica/produccion.html',
        title='Carga de Producción',
        producciones=producciones,
        productos=productos,
        fecha_filtro=fecha_filtro,
        hoy=date.today(),
        totales_dia=totales_dia
    )


@fabrica_bp.route('/produccion/<int:prod_id>/eliminar', methods=['POST'])
@operario_requerido
def eliminar_produccion(prod_id):
    """
    Eliminar un registro de producción y restar del stock del producto.
    """
    prod = ProduccionDiaria.query.get_or_404(prod_id)
    producto = Producto.query.get(prod.producto_id)

    if producto:
        producto.descontar_stock(float(prod.cantidad))

    nombre_prod = producto.nombre if producto else 'desconocido'
    cantidad = float(prod.cantidad)
    unidad = prod.unidad

    db.session.delete(prod)
    db.session.commit()

    flash(f'⚠️ Se eliminó la producción de {cantidad} {unidad} de {nombre_prod} y se ajustó el stock.', 'warning')
    return redirect(url_for('fabrica.produccion'))


@fabrica_bp.route('/stock')
@operario_requerido
def stock():
    """
    Vista del stock actual de todos los productos.
    """
    productos = Producto.query.order_by(Producto.nombre).all()

    # Total producido histórico por producto
    producciones_totales = db.session.query(
        ProduccionDiaria.producto_id,
        func.sum(ProduccionDiaria.cantidad).label('total_producido')
    ).group_by(ProduccionDiaria.producto_id).all()

    totales_dict = {r.producto_id: float(r.total_producido) for r in producciones_totales}

    return render_template(
        'fabrica/stock.html',
        title='Stock Actual',
        productos=productos,
        totales_dict=totales_dict
    )


@fabrica_bp.route('/productos/nuevo', methods=['POST'])
@operario_requerido
def nuevo_producto():
    """
    Agregar un nuevo producto al catálogo desde el panel de fábrica.
    """
    nombre = request.form.get('nombre', '').strip()
    unidad = request.form.get('unidad', '').strip()
    descripcion = request.form.get('descripcion', '').strip() or None

    if not nombre:
        flash('El nombre del producto es obligatorio.', 'danger')
        return redirect(url_for('fabrica.produccion'))

    # Verificar que no exista ya
    existente = Producto.query.filter(
        func.lower(Producto.nombre) == nombre.lower()
    ).first()
    if existente:
        flash(f'Ya existe un producto con el nombre "{existente.nombre}".', 'warning')
        return redirect(url_for('fabrica.produccion'))

    nuevo = Producto(
        nombre=nombre,
        unidad=unidad if unidad else None,
        descripcion=descripcion,
        disponible=True,
        stock_actual=0
    )
    db.session.add(nuevo)
    db.session.commit()

    flash(f'✅ Producto "{nombre}" agregado al catálogo.', 'success')
    return redirect(url_for('fabrica.produccion'))