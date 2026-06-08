# -*- coding: utf-8 -*-
"""
Blueprint para el panel de sucursales.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db, socketio
from app.models.cliente import Cliente
from app.models.pedido import Pedido
from app.models.producto import Producto
from datetime import datetime
from functools import wraps
from sqlalchemy import func

# Crear el Blueprint
sucursal_bp = Blueprint('sucursal', __name__)


def sucursal_requerido(f):
    """
    Decorador para verificar que el usuario sea una sucursal.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_sucursal():
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@sucursal_bp.route('/dashboard')
@sucursal_requerido
def dashboard():
    """
    Panel principal de la sucursal.
    Muestra los pedidos de las sucursales agrupados por cliente.
    """
    # Obtener clientes que pertenecen a la ruta 'SUCURSALES' y tienen pedidos activos
    clientes_con_pedidos = Cliente.query.join(Pedido).filter(
        Cliente.ruta == 'SUCURSALES',
        Pedido.archivado == False
    ).distinct().order_by(Cliente.nombre).all()
    
    # Agrupar pedidos por cliente
    pedidos_por_cliente = {}
    for cliente in clientes_con_pedidos:
        pedidos_por_cliente[cliente] = Pedido.query.filter_by(
            cliente_id=cliente.id,
            archivado=False
        ).order_by(Pedido.fecha_creacion.desc()).all()
        
    # Estadísticas rápidas para la sucursal
    total_pedidos = db.session.query(Pedido).join(Cliente).filter(
        Cliente.ruta == 'SUCURSALES',
        Pedido.archivado == False
    ).count()
    
    pedidos_pendientes = db.session.query(Pedido).join(Cliente).filter(
        Cliente.ruta == 'SUCURSALES',
        Pedido.archivado == False,
        Pedido.estado == 'pendiente'
    ).count()
    
    pedidos_completados = db.session.query(Pedido).join(Cliente).filter(
        Cliente.ruta == 'SUCURSALES',
        Pedido.archivado == False,
        Pedido.estado == 'completado'
    ).count()
    
    # Cantidad total de litros/unidades cargados
    total_cantidad = db.session.query(func.sum(Pedido.cantidad)).join(Cliente).filter(
        Cliente.ruta == 'SUCURSALES',
        Pedido.archivado == False,
        Pedido.estado != 'cancelado'
    ).scalar()
    total_cantidad = float(total_cantidad) if total_cantidad else 0.0

    return render_template(
        'sucursal/dashboard.html',
        title='Panel de Sucursal',
        pedidos_por_cliente=pedidos_por_cliente,
        total_pedidos=total_pedidos,
        pedidos_pendientes=pedidos_pendientes,
        pedidos_completados=pedidos_completados,
        total_cantidad=total_cantidad,
        Pedido=Pedido
    )


@sucursal_bp.route('/pedido/nuevo', methods=['GET', 'POST'])
@sucursal_requerido
def nuevo_pedido():
    """
    Carga de pedidos para sucursales.
    Solo muestra clientes que tengan la ruta 'SUCURSALES'.
    """
    if request.method == 'POST':
        cliente_id = request.form.get('cliente_id', type=int)
        
        if not cliente_id or cliente_id == 0:
            flash('Debes seleccionar una sucursal', 'danger')
            return redirect(url_for('sucursal.nuevo_pedido'))
            
        # Verificar que el cliente pertenezca a SUCURSALES
        cliente = Cliente.query.get_or_404(cliente_id)
        if cliente.ruta != 'SUCURSALES':
            flash('Cliente no válido para esta sección', 'danger')
            return redirect(url_for('sucursal.nuevo_pedido'))
            
        # Obtener arreglos de productos, cantidades, destinatarios y notas
        producto_ids = request.form.getlist('producto_ids[]')
        productos_texto = request.form.getlist('productos[]')
        cantidades = request.form.getlist('cantidades[]')
        unidades = request.form.getlist('unidades[]')
        destinatarios = request.form.getlist('destinatarios[]')
        notas = request.form.getlist('notas[]')
        
        # Validar que haya al menos un producto
        tiene_producto = any(p for p in producto_ids if p and p.strip()) or \
                         any(p for p in productos_texto if p and p.strip())
                         
        if not tiene_producto:
            flash('Debes agregar al menos un pedido con producto', 'warning')
            return redirect(url_for('sucursal.nuevo_pedido'))
            
        pedidos_creados = []
        total_items = max(len(producto_ids), len(productos_texto))
        
        for i in range(total_items):
            pid_str = producto_ids[i] if i < len(producto_ids) else ''
            ptxt = productos_texto[i] if i < len(productos_texto) else ''
            
            nombre_final = None
            id_final = None

            if pid_str and pid_str.strip():
                try:
                    producto_obj = Producto.query.get(int(pid_str))
                    if producto_obj:
                        nombre_final = producto_obj.nombre
                        id_final = producto_obj.id
                except (ValueError, TypeError):
                    pass

            if not nombre_final and ptxt and ptxt.strip():
                nombre_final = ptxt.strip()

            if not nombre_final:
                continue  # Saltar filas vacías

            try:
                cantidad = float(cantidades[i]) if i < len(cantidades) and cantidades[i] else 1.0
                unidad = unidades[i] if i < len(unidades) else 'unidades'
                dest = destinatarios[i] if i < len(destinatarios) else 'fabrica'
                nota = notas[i] if i < len(notas) and notas[i] else None
                
                # Validar destinatario
                if dest not in ['fabrica', 'admin_minorista', 'admin_mayorista']:
                    dest = 'fabrica'
                
                pedido = Pedido(
                    cliente_id=cliente_id,
                    producto_nombre=nombre_final,
                    producto_id=id_final,
                    cantidad=cantidad,
                    unidad=unidad,
                    destinatario=dest,
                    despachado=False,
                    estado='pendiente',
                    notas_vendedor=nota,
                    modificado=False,
                    visto_por_fabrica=False,
                    esperando_contestacion=False
                )
                db.session.add(pedido)
                pedidos_creados.append(pedido)
                
            except Exception as e:
                db.session.rollback()
                flash(f'Error al procesar el pedido en fila {i+1}: {str(e)}', 'danger')
                return redirect(url_for('sucursal.nuevo_pedido'))
                
        try:
            db.session.commit()
            
            # Emitir eventos de WebSocket para tiempo real
            for p in pedidos_creados:
                socketio.emit('nuevo_pedido', {
                    'pedido': p.to_dict()
                }, namespace='/')
                
            flash(f'✅ Se cargaron {len(pedidos_creados)} pedido(s) correctamente para {cliente.nombre}.', 'success')
            return redirect(url_for('sucursal.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar pedidos en base de datos: {str(e)}', 'danger')
            return redirect(url_for('sucursal.nuevo_pedido'))
            
    # GET: Cargar clientes de la ruta 'SUCURSALES' y productos del catálogo
    sucursales = Cliente.query.filter_by(ruta='SUCURSALES', activo=True).order_by(Cliente.nombre).all()
    productos_disponibles = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()
    
    return render_template(
        'sucursal/pedido_form.html',
        title='Cargar Pedido Sucursal',
        sucursales=sucursales,
        productos_disponibles=productos_disponibles
    )


@sucursal_bp.route('/pedido/<int:pedido_id>/marcar-leido', methods=['POST'])
@sucursal_requerido
def marcar_pedido_leido(pedido_id):
    """
    Marcar las observaciones de fábrica como leídas por la sucursal.
    Limpia el flag 'esperando_contestacion' para que la fábrica no vea la notificación pendiente.
    """
    pedido = Pedido.query.get_or_404(pedido_id)

    # Validar que pertenezca a la sucursal
    if pedido.cliente.ruta != 'SUCURSALES':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    pedido.visto_por_vendedor = True
    pedido.esperando_contestacion = False
    db.session.commit()

    # Emitir evento WebSocket para que fábrica actualice en tiempo real
    socketio.emit('pedido_actualizado', {
        'pedido': pedido.to_dict()
    }, namespace='/')

    return jsonify({'success': True, 'pedido_id': pedido.id})


@sucursal_bp.route('/pedido/<int:pedido_id>/mensajes')
@sucursal_requerido
def ver_mensajes_pedido(pedido_id):
    """
    Ver historial de mensajes de un pedido de sucursal.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Validar que pertenezca a una sucursal
    if pedido.cliente.ruta != 'SUCURSALES':
        flash('No tienes acceso a este pedido', 'danger')
        return redirect(url_for('sucursal.dashboard'))
        
    from app.models.mensaje_pedido import MensajePedido
    mensajes = MensajePedido.query.filter_by(pedido_id=pedido_id).order_by(MensajePedido.fecha_creacion.asc()).all()
    
    return render_template(
        'sucursal/mensajes_pedido.html',
        pedido=pedido,
        mensajes=mensajes,
        title=f'Chat Pedido #{pedido.id}'
    )


@sucursal_bp.route('/productos/nuevo', methods=['POST'])
@sucursal_requerido
def nuevo_producto():
    """
    Agregar un nuevo producto al catálogo desde el panel de sucursal.
    Redirige de vuelta al formulario de nuevo pedido.
    """
    nombre = request.form.get('nombre', '').strip()
    unidad = request.form.get('unidad', '').strip()
    descripcion = request.form.get('descripcion', '').strip() or None

    if not nombre:
        flash('El nombre del producto es obligatorio.', 'danger')
        return redirect(url_for('sucursal.nuevo_pedido'))

    # Verificar que no exista ya
    existente = Producto.query.filter(
        func.lower(Producto.nombre) == nombre.lower()
    ).first()
    if existente:
        flash(f'Ya existe un producto con el nombre "{existente.nombre}".', 'warning')
        return redirect(url_for('sucursal.nuevo_pedido'))

    nuevo = Producto(
        nombre=nombre,
        unidad=unidad if unidad else None,
        descripcion=descripcion,
        disponible=True,
        stock_actual=0
    )
    db.session.add(nuevo)
    db.session.commit()

    flash(f'✅ Producto "{nombre}" agregado al catálogo. Ya podés seleccionarlo en el pedido.', 'success')
    return redirect(url_for('sucursal.nuevo_pedido'))


@sucursal_bp.route('/pedido/<int:pedido_id>/eliminar', methods=['POST'])
@sucursal_requerido
def eliminar_pedido(pedido_id):
    """
    Eliminar un pedido realizado por la sucursal.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Validar que pertenezca a la sucursal (ruta SUCURSALES)
    if pedido.cliente.ruta != 'SUCURSALES':
        flash('No tienes permisos para eliminar este pedido', 'danger')
        return redirect(url_for('sucursal.dashboard'))
        
    pedido_info = {
        'id': pedido.id,
        'producto_nombre': pedido.producto_nombre,
        'cliente_id': pedido.cliente_id
    }
    
    db.session.delete(pedido)
    db.session.commit()
    
    # Emitir evento WebSocket
    socketio.emit('pedido_eliminado', {
        'pedido_id': pedido_info['id'],
        'cliente_id': pedido_info['cliente_id']
    }, namespace='/')
    
    flash(f'🗑️ Pedido #{pedido_info["id"]} de "{pedido_info["producto_nombre"]}" eliminado exitosamente.', 'success')
    return redirect(url_for('sucursal.dashboard'))


@sucursal_bp.route('/pedido/<int:pedido_id>/recibir', methods=['POST'])
@sucursal_requerido
def recibir_pedido(pedido_id):
    """
    Confirmar recepción conforme de un pedido por parte de la sucursal.
    Lo marca como recibido_conforme y archivado para removerlo visualmente.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Validar que pertenezca a la sucursal (ruta SUCURSALES)
    if pedido.cliente.ruta != 'SUCURSALES':
        flash('No tienes permisos para operar este pedido', 'danger')
        return redirect(url_for('sucursal.dashboard'))
        
    pedido.recibido_conforme = True
    pedido.archivado = True
    pedido.fecha_archivado = datetime.utcnow()
    
    # Asegurar que quede como completado solo si no estaba cancelado
    if pedido.estado not in ['completado', 'cancelado']:
        pedido.estado = 'completado'
        
    db.session.commit()
    
    # Emitir eventos WebSocket para sincronización en tiempo real en otros paneles
    socketio.emit('pedido_archivado', {
        'pedido_id': pedido.id,
        'cliente_id': pedido.cliente_id
    }, namespace='/')
    
    socketio.emit('pedido_actualizado', {
        'pedido': pedido.to_dict()
    }, namespace='/')
    
    if pedido.estado == 'cancelado':
        flash(f'ℹ️ Tomaste conocimiento de que el pedido #{pedido.id} de "{pedido.producto_nombre}" fue cancelado. Ha sido archivado en el historial.', 'info')
    else:
        flash(f'📦 Pedido #{pedido.id} de "{pedido.producto_nombre}" marcado como Recibido Conforme y archivado.', 'success')
        
    return redirect(url_for('sucursal.dashboard'))


@sucursal_bp.route('/recibidos')
@sucursal_requerido
def recibidos():
    """
    Historial de pedidos recibidos conforme o archivados de las sucursales.
    """
    # Obtener pedidos que pertenecen a SUCURSALES y están marcados como recibidos o archivados
    pedidos_recibidos = Pedido.query.join(Cliente).filter(
        Cliente.ruta == 'SUCURSALES',
        db.or_(Pedido.recibido_conforme == True, Pedido.archivado == True)
    ).order_by(func.coalesce(Pedido.fecha_archivado, Pedido.fecha_actualizacion).desc()).all()
    
    # Calcular algunas estadísticas rápidas del historial
    total_recibidos = len(pedidos_recibidos)
    total_unidades = sum(float(p.cantidad) for p in pedidos_recibidos if p.estado != 'cancelado')
    
    return render_template(
        'sucursal/recibidos.html',
        title='Pedidos Recibidos',
        pedidos=pedidos_recibidos,
        total_recibidos=total_recibidos,
        total_unidades=total_unidades
    )


@sucursal_bp.route('/recuperar-pedidos')
@login_required
def recuperar_pedidos():
    """
    Ruta temporal de emergencia para desarchivar pedidos de SUCURSALES
    que fueron archivados por error al cerrar la semana en ventas.
    """
    # Buscamos los pedidos de sucursales que están archivados
    pedidos_archivados = Pedido.query.join(Cliente).filter(
        Pedido.archivado == True,
        Cliente.ruta == 'SUCURSALES'
    ).all()

    recuperados = 0
    for pedido in pedidos_archivados:
        # Solo desarchivamos los que no hayan sido recibidos conforme (que es el fin natural en sucursal)
        if not pedido.recibido_conforme:
            pedido.archivado = False
            pedido.semana_archivada = None
            pedido.fecha_archivado = None
            recuperados += 1

    db.session.commit()
    flash(f'¡Recuperados {recuperados} pedidos de sucursales!', 'success')
    return redirect(url_for('sucursal.dashboard'))
