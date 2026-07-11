# -*- coding: utf-8 -*-
"""
Blueprint para el panel de Administración de Fábrica.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db, socketio
from app.models.pedido import Pedido
from app.models.cliente import Cliente
from app.models.mensaje_pedido import MensajePedido
from app.models.producto import Producto
from app.models.produccion import ProduccionDiaria
from app.routes.fabrica import _descontar_stock_pedido
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import func

# Crear el Blueprint
administracion_bp = Blueprint('administracion', __name__)


def administracion_requerido(f):
    """
    Decorador para verificar que el usuario sea del área de Administración de Fábrica.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_administracion():
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@administracion_bp.route('/dashboard')
@administracion_requerido
def dashboard():
    """
    Panel principal de Administración de Fábrica.
    Muestra los pedidos minoristas, mayoristas y TODOS los pedidos de fábrica (todos los estados).
    Administración es responsable del despacho, por lo tanto ve todos los pedidos de fábrica
    sin importar si están pendientes, en proceso o completados.
    """
    # Pedidos minoristas y mayoristas no archivados — SOLO de clientes de la ruta SUCURSALES
    pedidos_minoristas = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'admin_minorista',
        Cliente.ruta == 'SUCURSALES'
    ).order_by(Pedido.fecha_creacion.desc()).all()
    
    pedidos_mayoristas = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'admin_mayorista',
        Cliente.ruta == 'SUCURSALES'
    ).order_by(Pedido.fecha_creacion.desc()).all()

    # Pedidos de fábrica — TODOS los estados — SOLO de clientes de la ruta SUCURSALES
    # Administración ve todos los pedidos de fábrica porque es responsable del despacho
    pedidos_fabrica = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'fabrica',
        Cliente.ruta == 'SUCURSALES'
    ).order_by(Pedido.fecha_creacion.desc()).all()

    # Pedidos que el usuario Ventas hizo a Fábrica (clientes fuera de SUCURSALES) — todos los estados
    pedidos_ventas_fabrica = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'fabrica',
        Cliente.ruta != 'SUCURSALES'
    ).order_by(Pedido.fecha_creacion.desc()).all()
    
    # Estadísticas generales
    total_minoristas = len(pedidos_minoristas)
    total_mayoristas = len(pedidos_mayoristas)
    total_fabrica = len(pedidos_fabrica)
    total_ventas_fabrica = len(pedidos_ventas_fabrica)
    
    pendientes_minoristas = sum(1 for p in pedidos_minoristas if p.estado == 'pendiente')
    pendientes_mayoristas = sum(1 for p in pedidos_mayoristas if p.estado == 'pendiente')
    pendientes_fabrica = sum(1 for p in pedidos_fabrica if p.estado == 'pendiente')
    
    completados_minoristas = sum(1 for p in pedidos_minoristas if p.estado == 'completado')
    completados_mayoristas = sum(1 for p in pedidos_mayoristas if p.estado == 'completado')
    completados_fabrica = sum(1 for p in pedidos_fabrica if p.estado == 'completado')
    
    # Litros/Unidades totales — SOLO SUCURSALES
    cantidad_minorista = db.session.query(func.sum(Pedido.cantidad)).join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'admin_minorista',
        Pedido.estado != 'cancelado',
        Cliente.ruta == 'SUCURSALES'
    ).scalar()
    cantidad_minorista = float(cantidad_minorista) if cantidad_minorista else 0.0
    
    cantidad_mayorista = db.session.query(func.sum(Pedido.cantidad)).join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'admin_mayorista',
        Pedido.estado != 'cancelado',
        Cliente.ruta == 'SUCURSALES'
    ).scalar()
    cantidad_mayorista = float(cantidad_mayorista) if cantidad_mayorista else 0.0

    # Litros/Unidades fábrica (todos los estados activos) — SOLO SUCURSALES
    cantidad_fabrica = db.session.query(func.sum(Pedido.cantidad)).join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'fabrica',
        Pedido.estado != 'cancelado',
        Cliente.ruta == 'SUCURSALES'
    ).scalar()
    cantidad_fabrica = float(cantidad_fabrica) if cantidad_fabrica else 0.0
    
    # Pedidos despachados (de administración y fábrica)
    despachados_minoristas = sum(1 for p in pedidos_minoristas if p.despachado)
    despachados_mayoristas = sum(1 for p in pedidos_mayoristas if p.despachado)
    despachados_fabrica = sum(1 for p in pedidos_fabrica if p.despachado)
    despachados_ventas_fabrica = sum(1 for p in pedidos_ventas_fabrica if p.despachado)

    return render_template(
        'administracion/dashboard.html',
        title='Panel de Administración',
        pedidos_minoristas=pedidos_minoristas,
        pedidos_mayoristas=pedidos_mayoristas,
        pedidos_fabrica=pedidos_fabrica,
        pedidos_ventas_fabrica=pedidos_ventas_fabrica,
        total_minoristas=total_minoristas,
        total_mayoristas=total_mayoristas,
        total_fabrica=total_fabrica,
        total_ventas_fabrica=total_ventas_fabrica,
        pendientes_minoristas=pendientes_minoristas,
        pendientes_mayoristas=pendientes_mayoristas,
        pendientes_fabrica=pendientes_fabrica,
        completados_minoristas=completados_minoristas,
        completados_mayoristas=completados_mayoristas,
        completados_fabrica=completados_fabrica,
        cantidad_minorista=cantidad_minorista,
        cantidad_mayorista=cantidad_mayorista,
        cantidad_fabrica=cantidad_fabrica,
        despachados_minoristas=despachados_minoristas,
        despachados_mayoristas=despachados_mayoristas,
        despachados_fabrica=despachados_fabrica,
        despachados_ventas_fabrica=despachados_ventas_fabrica,
        Pedido=Pedido
    )


@administracion_bp.route('/pedido/<int:pedido_id>/actualizar-despachado', methods=['POST'])
@administracion_requerido
def actualizar_despachado(pedido_id):
    """
    Ruta AJAX para alternar el estado despachado (SI/NO).
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Validar que sea un pedido dirigido a la administración o completado de fábrica (incluyendo pedidos de ventas a fábrica)
    if pedido.destinatario not in ['admin_minorista', 'admin_mayorista', 'fabrica']:
        return jsonify({'success': False, 'error': 'El pedido no es elegible para despacho'}), 400
        
    try:
        # Alternar el estado
        pedido.despachado = not pedido.despachado
        pedido.fecha_actualizacion = datetime.utcnow()
        db.session.commit()
        
        # Emitir cambio por Socket.IO
        socketio.emit('pedido_actualizado', {
            'pedido': pedido.to_dict(),
            'despacho_cambiado': True,
            'mensaje': f'Pedido #{pedido.id} despacho cambiado a {"SI" if pedido.despachado else "NO"}'
        }, namespace='/')
        
        return jsonify({
            'success': True,
            'despachado': pedido.despachado,
            'pedido_id': pedido.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@administracion_bp.route('/pedido/<int:pedido_id>/actualizar', methods=['GET', 'POST'])
@administracion_requerido
def actualizar_pedido(pedido_id):
    """
    Actualiza el estado y las observaciones de un pedido de administración.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Validar que sea un pedido de administración
    if pedido.destinatario not in ['admin_minorista', 'admin_mayorista']:
        flash('No tienes permisos para actualizar este pedido', 'danger')
        return redirect(url_for('administracion.dashboard'))
        
    if request.method == 'POST':
        nuevo_estado = request.form.get('estado')
        observaciones = request.form.get('observaciones_fabrica', '').strip()
        
        if nuevo_estado not in ['pendiente', 'completado', 'cancelado']:
            flash('Estado seleccionado no válido', 'danger')
            return redirect(url_for('administracion.actualizar_pedido', pedido_id=pedido.id))
            
        try:
            observaciones_anteriores = pedido.observaciones_fabrica
            estado_anterior = pedido.estado
            
            pedido.estado = nuevo_estado
            pedido.observaciones_fabrica = observaciones if observaciones else None
            
            # Si se completa, guardar fecha y descontar stock
            if nuevo_estado == 'completado' and estado_anterior != 'completado':
                pedido.marcar_como_completado()
                # Descontar del catálogo
                try:
                    _descontar_stock_pedido(pedido)
                except Exception as stock_err:
                    # Loggeamos el error pero no bloqueamos la actualización del pedido
                    print(f"Error al descontar stock para pedido {pedido.id}: {stock_err}")
            
            # Si cambió o se agregaron observaciones, insertar en el historial de mensajes
            if observaciones and observaciones != observaciones_anteriores:
                mensaje = MensajePedido(
                    pedido_id=pedido.id,
                    usuario_id=current_user.id,
                    mensaje=observaciones,
                    tipo='fabrica', # Usamos fábrica para mantener coherencia en las burbujas de chat
                    leido=False
                )
                db.session.add(mensaje)
                pedido.visto_por_vendedor = False
                pedido.esperando_contestacion = True
                
            db.session.commit()
            
            # Emitir evento de Socket.IO
            socketio.emit('pedido_actualizado', {
                'pedido': pedido.to_dict(),
                'mensaje': f'Pedido #{pedido.id} actualizado por Administración'
            }, namespace='/')
            
            flash(f'Pedido #{pedido.id} actualizado correctamente a {nuevo_estado}', 'success')
            return redirect(url_for('administracion.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar pedido: {str(e)}', 'danger')
            return redirect(url_for('administracion.actualizar_pedido', pedido_id=pedido.id))
            
    return render_template(
        'administracion/actualizar_pedido.html',
        pedido=pedido,
        title=f'Actualizar Pedido #{pedido.id}'
    )


@administracion_bp.route('/pedido/<int:pedido_id>/mensajes')
@administracion_requerido
def ver_mensajes_pedido(pedido_id):
    """
    Ver mensajes (chat) de un pedido.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Validar que pertenezca a la administración o a fábrica
    if pedido.destinatario not in ['admin_minorista', 'admin_mayorista', 'fabrica']:
        flash('No tienes acceso a este pedido', 'danger')
        return redirect(url_for('administracion.dashboard'))
        
    mensajes = MensajePedido.query.filter_by(pedido_id=pedido_id).order_by(MensajePedido.fecha_creacion.asc()).all()
    
    return render_template(
        'administracion/mensajes_pedido.html',
        pedido=pedido,
        mensajes=mensajes,
        title=f'Chat Pedido #{pedido.id}'
    )


@administracion_bp.route('/reparar-sucursales', methods=['GET', 'POST'])
@administracion_requerido
def reparar_sucursales():
    """
    Ruta de diagnóstico y reparación de pedidos de sucursales.
    Detecta clientes con pedidos activos que no tienen ruta='SUCURSALES'
    y permite corregirlos para que aparezcan en el panel de Administración.
    """
    # Pedidos visibles actualmente en Administración
    pedidos_visibles = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.destinatario.in_(['fabrica', 'admin_minorista', 'admin_mayorista']),
        Cliente.ruta == 'SUCURSALES'
    ).count()

    # Clientes con pedidos activos pero sin ruta='SUCURSALES'
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

    # Armar detalle de pedidos afectados por cliente
    detalle = []
    for c in clientes_problema:
        pedidos_afectados = Pedido.query.filter(
            Pedido.cliente_id == c.id,
            Pedido.archivado == False,
            Pedido.destinatario.in_(['fabrica', 'admin_minorista', 'admin_mayorista'])
        ).all()
        detalle.append({
            'cliente': c,
            'pedidos': pedidos_afectados
        })

    reparados = 0
    if request.method == 'POST':
        ids_a_reparar = request.form.getlist('cliente_ids[]', type=int)
        for c in clientes_problema:
            if c.id in ids_a_reparar:
                c.ruta = 'SUCURSALES'
                reparados += 1
        try:
            db.session.commit()
            flash(
                f'{reparados} cliente(s) actualizados a ruta SUCURSALES. '
                f'Sus pedidos ahora son visibles en Administración.',
                'success'
            )
            return redirect(url_for('administracion.reparar_sucursales'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al reparar: {str(e)}', 'danger')

    return render_template(
        'administracion/reparar_sucursales.html',
        title='Reparar Pedidos de Sucursales',
        pedidos_visibles=pedidos_visibles,
        detalle=detalle,
    )


@administracion_bp.route('/stock')
@administracion_requerido
def stock():
    """
    Vista de solo lectura del stock actual de fábrica para el usuario Administración.
    """
    # Obtener todas las producciones históricas para filtrar el catálogo
    producciones_totales = db.session.query(
        ProduccionDiaria.producto_id,
        func.sum(ProduccionDiaria.cantidad).label('total_producido')
    ).group_by(ProduccionDiaria.producto_id).all()

    totales_dict = {r.producto_id: float(r.total_producido) for r in producciones_totales}

    # Calcular límites de la semana actual (Lunes a Viernes)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    # Obtener producciones de la semana actual
    producciones_semanales = db.session.query(
        ProduccionDiaria.producto_id,
        func.sum(ProduccionDiaria.cantidad).label('total_semanal')
    ).filter(
        ProduccionDiaria.fecha_produccion >= monday,
        ProduccionDiaria.fecha_produccion <= friday
    ).group_by(ProduccionDiaria.producto_id).all()

    semanales_dict = {r.producto_id: float(r.total_semanal) for r in producciones_semanales}

    # Mostrar todo el catálogo disponible para que puedan editarlo o eliminarlo
    productos = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()

    return render_template(
        'fabrica/stock.html',
        title='Stock Actual',
        productos=productos,
        semanales_dict=semanales_dict
    )

# ─────────────────────────────────────────────
# SECCIÓN: PRODUCCIÓN DIARIA Y STOCK
# ─────────────────────────────────────────────

@administracion_bp.route('/produccion', methods=['GET', 'POST'])
@administracion_requerido
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
            return redirect(url_for('administracion.produccion'))

        if cantidad <= 0:
            flash('La cantidad debe ser mayor a cero.', 'danger')
            return redirect(url_for('administracion.produccion'))

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
        return redirect(url_for('administracion.produccion'))

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
        'administracion/produccion.html',
        title='Carga de Producción',
        producciones=producciones,
        productos=productos,
        fecha_filtro=fecha_filtro,
        hoy=date.today(),
        totales_dia=totales_dia
    )


@administracion_bp.route('/produccion/<int:prod_id>/eliminar', methods=['POST'])
@administracion_requerido
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
    return redirect(url_for('administracion.produccion'))


@administracion_bp.route('/productos/nuevo', methods=['POST'])
@administracion_requerido
def nuevo_producto():
    """
    Agregar un nuevo producto al catálogo desde el panel de administración.
    """
    nombre = request.form.get('nombre', '').strip()
    unidad = request.form.get('unidad', '').strip()
    descripcion = request.form.get('descripcion', '').strip() or None

    if not nombre:
        flash('El nombre del producto es obligatorio.', 'danger')
        return redirect(url_for('administracion.produccion'))

    # Verificar que no exista ya
    existente = Producto.query.filter(
        func.lower(Producto.nombre) == nombre.lower()
    ).first()
    if existente:
        flash(f'Ya existe un producto con el nombre "{existente.nombre}".', 'warning')
        return redirect(url_for('administracion.produccion'))

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
    return redirect(url_for('administracion.produccion'))


@administracion_bp.route('/productos/<int:prod_id>/editar', methods=['POST'])
@administracion_requerido
def editar_producto(prod_id):
    """
    Editar el nombre o descripción de un producto existente.
    """
    producto = Producto.query.get_or_404(prod_id)
    
    nuevo_nombre = request.form.get('nombre', '').strip()
    nueva_descripcion = request.form.get('descripcion', '').strip() or None
    
    if not nuevo_nombre:
        flash('El nombre del producto no puede estar vacío.', 'danger')
        return redirect(url_for('administracion.stock'))
        
    # Verificar si el nuevo nombre ya existe en OTRO producto
    existente = Producto.query.filter(
        func.lower(Producto.nombre) == nuevo_nombre.lower(),
        Producto.id != prod_id
    ).first()
    
    if existente:
        flash(f'Ya existe otro producto con el nombre "{existente.nombre}".', 'warning')
        return redirect(url_for('administracion.stock'))
        
    producto.nombre = nuevo_nombre
    producto.descripcion = nueva_descripcion
    
    db.session.commit()
    flash(f'✅ Producto actualizado a "{nuevo_nombre}".', 'success')
    return redirect(url_for('administracion.stock'))


@administracion_bp.route('/productos/<int:prod_id>/eliminar_catalogo', methods=['POST'])
@administracion_requerido
def eliminar_producto_catalogo(prod_id):
    """
    Eliminar un producto del catálogo (baja lógica).
    """
    producto = Producto.query.get_or_404(prod_id)
    producto.disponible = False
    db.session.commit()
    flash(f'⚠️ Producto "{producto.nombre}" eliminado del catálogo.', 'warning')
    return redirect(url_for('administracion.stock'))
