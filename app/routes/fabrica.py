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
from app.models.materia_prima import MateriaPrima
from app.models.formulacion_producto import FormulacionProducto
from app.models.movimiento_materia_prima import MovimientoMateriaPrima
from app.forms.pedido_forms import ActualizarPedidoFabricaForm
from datetime import datetime, date
from functools import wraps
from sqlalchemy import func
import logging
import json

logger = logging.getLogger(__name__)


def _verificar_stock_disponible_pedido(pedido):
    """
    Verifica si hay stock suficiente en el catálogo (o materia prima vinculada)
    para poder marcar el pedido como completado.
    Retorna: (es_valido: bool, mensaje_error: str | None, stock_disponible: float, producto: Producto | None)
    """
    producto = None

    # Primero: buscar por ID (pedidos nuevos)
    if pedido.producto_id:
        producto = Producto.query.get(pedido.producto_id)

    # Fallback: buscar por nombre (pedidos creados antes del nuevo sistema)
    if not producto and pedido.producto_nombre:
        producto = Producto.query.filter(
            func.lower(Producto.nombre) == pedido.producto_nombre.strip().lower()
        ).first()
        if producto:
            pedido.producto_id = producto.id

    if not producto:
        return (
            False,
            f"El producto '{pedido.producto_nombre}' no está registrado en el catálogo. No se puede completar el pedido sin stock registrado.",
            0.0,
            None
        )

    cantidad_requerida = float(pedido.cantidad or 0)
    stock_disponible = float(producto.stock_actual_real or 0)

    if stock_disponible <= 0:
        return (
            False,
            f"Stock insuficiente: '{producto.nombre}' no tiene stock disponible (Stock actual: 0 {producto.unidad or ''}). Registrá la producción correspondiente o proponé un ajuste de cantidad.",
            stock_disponible,
            producto
        )

    if stock_disponible < cantidad_requerida:
        return (
            False,
            f"Stock insuficiente para '{producto.nombre}'. Stock disponible: {stock_disponible:g} {producto.unidad or ''}, pero el pedido requiere {cantidad_requerida:g} {producto.unidad or ''}. Registrá la producción o proponé un ajuste parcial.",
            stock_disponible,
            producto
        )

    return (True, None, stock_disponible, producto)


def _descontar_stock_pedido(pedido):
    """
    Intenta descontar el stock del producto asociado a un pedido.
    Busca primero por producto_id; si no tiene, busca por producto_nombre.
    Retorna dict con info del resultado.
    """
    producto = None

    # Primero: buscar por ID (pedidos nuevos)
    if pedido.producto_id:
        producto = Producto.query.get(pedido.producto_id)

    # Fallback: buscar por nombre (pedidos creados antes del nuevo sistema)
    if not producto and pedido.producto_nombre:
        producto = Producto.query.filter(
            func.lower(Producto.nombre) == pedido.producto_nombre.strip().lower()
        ).first()
        # Si encontramos por nombre, vincular para el futuro
        if producto:
            pedido.producto_id = producto.id

    if producto:
        cantidad = float(pedido.cantidad or 0)
        if cantidad > 0:
            stock_anterior = float(producto.stock_actual or 0)
            producto.descontar_stock(cantidad)
            stock_nuevo = float(producto.stock_actual or 0)

            # Si el producto tiene una materia prima vinculada, descontar también su stock
            mp_vinc = producto.get_materia_prima_vinculada()
            if mp_vinc:
                mp_vinc.descontar_stock(cantidad)
                mov_mp = MovimientoMateriaPrima(
                    materia_prima_id=mp_vinc.id,
                    tipo='ajuste',
                    cantidad=cantidad,
                    descripcion=f'Despacho de Pedido #{pedido.id} ({producto.nombre})',
                    usuario_id=getattr(pedido, 'usuario_id', 1) or 1
                )
                db.session.add(mov_mp)

            logger.info(
                f"Stock descontado: {cantidad} de '{producto.nombre}' "
                f"por pedido #{pedido.id}. {stock_anterior} -> {stock_nuevo}"
            )
            return {
                'ok': True,
                'producto_nombre': producto.nombre,
                'unidad': producto.unidad or '',
                'stock_anterior': stock_anterior,
                'stock_nuevo': stock_nuevo,
                'descontado': cantidad,
            }

    logger.warning(
        f"No se encontro producto para descontar stock del pedido #{pedido.id} "
        f"(producto_id={pedido.producto_id}, nombre='{pedido.producto_nombre}')"
    )
    return {'ok': False, 'motivo': 'Producto no encontrado en el catálogo'}


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


def fabrica_o_admin_requerido(f):
    """
    Decorador que permite acceso a usuarios con rol 'operario' (fábrica) o 'administracion'.
    Usado para rutas compartidas como la carga de producción.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.es_operario() or current_user.es_administracion()):
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ─────────────────────────────────────────────
# SECCIÓN: AJUSTE PARCIAL DE CANTIDAD
# ─────────────────────────────────────────────

@fabrica_bp.route('/pedido/<int:pedido_id>/solicitar-ajuste', methods=['POST'])
@operario_requerido
def solicitar_ajuste(pedido_id):
    """
    Fábrica propone enviar una cantidad menor a la pedida.
    El pedido queda bloqueado (ajuste_pendiente=True) hasta que el receptor resuelva.
    La solicitud llega a Ventas (si el cliente no es SUCURSALES) o a Administración.
    """
    from app.models.mensaje_pedido import MensajePedido
    from app.models.cliente import Cliente

    pedido = Pedido.query.get_or_404(pedido_id)

    if pedido.destinatario != 'fabrica':
        return jsonify({'success': False, 'error': 'Pedido no pertenece a fábrica'}), 403

    if pedido.archivado:
        return jsonify({'success': False, 'error': 'El pedido está archivado'}), 400

    if pedido.estado in ['completado', 'cancelado']:
        return jsonify({'success': False, 'error': 'No se puede solicitar ajuste en un pedido completado o cancelado'}), 400

    data = request.get_json(force=True, silent=True) or {}
    cantidad_propuesta = data.get('cantidad_propuesta')
    nota = data.get('nota', '').strip() or None

    # Validaciones
    try:
        cantidad_propuesta = float(cantidad_propuesta)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Cantidad propuesta inválida'}), 400

    if cantidad_propuesta <= 0:
        return jsonify({'success': False, 'error': 'La cantidad propuesta debe ser mayor a cero'}), 400

    cantidad_original = float(pedido.cantidad)
    if cantidad_propuesta >= cantidad_original:
        return jsonify({'success': False, 'error': f'La cantidad propuesta ({cantidad_propuesta}) debe ser menor a la original ({cantidad_original})'}), 400

    try:
        pedido.solicitar_ajuste(cantidad_propuesta, nota)

        # Mensaje en el historial de chat
        texto_mensaje = (
            f"📦 PROPUESTA DE AJUSTE DE CANTIDAD\n"
            f"• Cantidad original: {cantidad_original:g} {pedido.unidad or ''}\n"
            f"• Cantidad que podemos enviar: {cantidad_propuesta:g} {pedido.unidad or ''}"
        )
        if nota:
            texto_mensaje += f"\n• Motivo: {nota}"

        mensaje = MensajePedido(
            pedido_id=pedido.id,
            usuario_id=current_user.id,
            mensaje=texto_mensaje,
            tipo='solicitud_ajuste',
            leido=False
        )
        db.session.add(mensaje)
        db.session.commit()

        # Emitir WebSocket
        socketio.emit('pedido_ajuste_solicitado', {
            'pedido': pedido.to_dict(),
            'cantidad_propuesta': cantidad_propuesta,
            'cantidad_original': cantidad_original,
            'nota': nota,
            'operario': current_user.nombre,
        }, namespace='/')

        logger.info(
            f"Ajuste solicitado: pedido #{pedido.id} — "
            f"original={cantidad_original}, propuesta={cantidad_propuesta} — por {current_user.username}"
        )

        return jsonify({
            'success': True,
            'message': 'Solicitud de ajuste enviada correctamente',
            'pedido': pedido.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en solicitar_ajuste pedido #{pedido_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@fabrica_bp.route('/pedido/<int:pedido_id>/cancelar-ajuste', methods=['POST'])
@operario_requerido
def cancelar_ajuste(pedido_id):
    """
    Fábrica retira su propuesta de ajuste.
    El pedido vuelve al estado normal (sin ajuste pendiente).
    """
    from app.models.mensaje_pedido import MensajePedido

    pedido = Pedido.query.get_or_404(pedido_id)

    if pedido.destinatario != 'fabrica':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    if not pedido.ajuste_pendiente:
        return jsonify({'success': False, 'error': 'No hay ajuste pendiente en este pedido'}), 400

    try:
        cantidad_propuesta_anterior = float(pedido.cantidad_propuesta) if pedido.cantidad_propuesta else None
        pedido.rechazar_ajuste()  # Reutilizamos la misma lógica de limpieza

        mensaje = MensajePedido(
            pedido_id=pedido.id,
            usuario_id=current_user.id,
            mensaje=f"🔄 Fábrica retiró la propuesta de ajuste (cantidad propuesta era: {cantidad_propuesta_anterior:g} {pedido.unidad or ''}).",
            tipo='ajuste_cancelado',
            leido=False
        )
        db.session.add(mensaje)
        db.session.commit()

        socketio.emit('pedido_ajuste_cancelado', {
            'pedido': pedido.to_dict(),
        }, namespace='/')

        return jsonify({
            'success': True,
            'message': 'Propuesta de ajuste retirada',
            'pedido': pedido.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@fabrica_bp.route('/dashboard')
@operario_requerido
def dashboard():
    """
    Panel principal de la fábrica.
    Muestra todos los pedidos agrupados por ruta.
    """
    
    # Obtener todos los clientes que tienen pedidos, agrupados por ruta (filtrando por fábrica)
    clientes_con_pedidos = Cliente.query.join(Pedido).filter(
        Pedido.archivado == False,
        Pedido.destinatario == 'fabrica'
    ).distinct().order_by(Cliente.ruta, Cliente.nombre).all()
    
    # Agrupar clientes por ruta
    from collections import defaultdict
    clientes_por_ruta = defaultdict(list)
    for cliente in clientes_con_pedidos:
        clientes_por_ruta[cliente.ruta].append(cliente)
    
    # Convertir a dict normal y ordenar rutas
    clientes_por_ruta = dict(sorted(clientes_por_ruta.items()))
    
    # Estadísticas generales
    total_pendientes = Pedido.query.filter_by(archivado=False, estado='pendiente', destinatario='fabrica').count()
    total_completados = Pedido.query.filter_by(archivado=False, estado='completado', destinatario='fabrica').count()
    total_cancelados = Pedido.query.filter_by(archivado=False, estado='cancelado', destinatario='fabrica').count()
    pedidos_modificados = Pedido.query.filter_by(archivado=False, modificado=True, visto_por_fabrica=False, destinatario='fabrica').count()
    
    # Pedidos con cambios sin ver
    pedidos_modificados = Pedido.query.filter_by(modificado=True, visto_por_fabrica=False, destinatario='fabrica').count()
    
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
            Pedido.visto_por_fabrica == False,
            Pedido.destinatario == 'fabrica'
        ).count()
        notificaciones_por_ruta[ruta] = count

    # Calcular litros totales por ruta (pedidos no archivados y no cancelados)
    litros_por_ruta = {}
    for ruta in clientes_por_ruta.keys():
        total = db.session.query(func.sum(Pedido.cantidad)).join(Cliente).filter(
            Cliente.ruta == ruta,
            Pedido.archivado == False,
            Pedido.estado != 'cancelado',
            Pedido.destinatario == 'fabrica'
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
    if pedido.destinatario != 'fabrica':
        flash('No tienes permisos para acceder a este pedido', 'danger')
        return redirect(url_for('fabrica.dashboard'))
    form = ActualizarPedidoFabricaForm(obj=pedido)
    
    if form.validate_on_submit():
        # Guardar observaciones anteriores para comparar
        observaciones_anteriores = pedido.observaciones_fabrica
        
        # Actualizar pedido
        pedido.estado = form.estado.data
        pedido.operario_id = form.operario_id.data if form.operario_id.data else None
        pedido.observaciones_fabrica = form.observaciones_fabrica.data
        
        # Si se completó, validar stock disponible y registrar fecha
        if pedido.estado == 'completado' and not pedido.fecha_completado:
            valido, err_msg, _, _ = _verificar_stock_disponible_pedido(pedido)
            if not valido:
                flash(err_msg, 'danger')
                return render_template(
                    'fabrica/actualizar_pedido.html',
                    form=form,
                    pedido=pedido,
                    title='Actualizar Pedido'
                )
            pedido.marcar_como_completado()
            # Descontar stock con fallback por nombre
            try:
                _descontar_stock_pedido(pedido)
            except Exception as e:
                logger.warning(f"Error descontando stock en actualizar_pedido #{pedido.id}: {e}")
        
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
    if pedido.destinatario != 'fabrica':
        flash('No tienes permisos para acceder a este pedido', 'danger')
        return redirect(url_for('fabrica.dashboard'))
    
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
    if pedido.destinatario != 'fabrica':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    
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
    
    query = Pedido.query.filter_by(destinatario='fabrica')
    
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
    if pedido.destinatario != 'fabrica':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
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
    from flask import request, jsonify, current_app

    pedido = Pedido.query.get_or_404(pedido_id)
    if pedido.destinatario != 'fabrica':
        return jsonify({'success': False, 'error': 'No autorizado'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Datos inválidos'}), 400

    nuevo_estado = data.get('estado')

    if not nuevo_estado:
        return jsonify({'success': False, 'error': 'Estado no proporcionado'}), 400

    # Validar que el estado sea válido
    estados_validos = ['pendiente', 'completado', 'cancelado']
    if nuevo_estado not in estados_validos:
        return jsonify({'success': False, 'error': 'Estado inválido'}), 400

    # Validar que el pedido tenga un operario asignado antes de permitir el cambio de estado
    if not pedido.operario_id:
        return jsonify({
            'success': False,
            'error': 'Debes asignar un operario al pedido antes de cambiar su estado.'
        }), 400

    try:
        # Guardar estado anterior por si necesitamos revertir
        estado_anterior = pedido.estado

        # Actualizar estado
        pedido.estado = nuevo_estado

        # Inicializar info_stock siempre para evitar UnboundLocalError
        info_stock = None

        # Si se completó, validar stock disponible y registrar fecha
        if nuevo_estado == 'completado' and not pedido.fecha_completado:
            valido, err_msg, _, _ = _verificar_stock_disponible_pedido(pedido)
            if not valido:
                return jsonify({
                    'success': False,
                    'error': err_msg,
                    'bloqueado_por_stock': True
                }), 400

            pedido.marcar_como_completado()
            # Descontar stock con fallback por nombre
            try:
                info_stock = _descontar_stock_pedido(pedido)
            except Exception as stock_err:
                current_app.logger.warning(
                    f"Error descontando stock del pedido {pedido_id}: {stock_err}"
                )
                info_stock = {'ok': False, 'motivo': str(stock_err)}

        # Marcar como visto si estaba modificado
        if pedido.modificado:
            pedido.marcar_como_visto()

        db.session.commit()

        # Emitir evento de WebSocket
        socketio.emit('pedido_actualizado', {
            'pedido': pedido.to_dict()
        }, namespace='/')

        resp = {
            'success': True,
            'pedido': pedido.to_dict()
        }
        if nuevo_estado == 'completado' and info_stock:
            resp['stock_info'] = info_stock

        return jsonify(resp)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error en actualizar_estado_rapido pedido {pedido_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────
# SECCIÓN: PRODUCCIÓN DIARIA Y STOCK
# ─────────────────────────────────────────────


@fabrica_bp.route('/stock')
@operario_requerido
def stock():
    """
    Vista del stock actual de todos los productos.
    """
    # 1. Obtener todas las producciones históricas para filtrar el catálogo
    producciones_totales = db.session.query(
        ProduccionDiaria.producto_id,
        func.sum(ProduccionDiaria.cantidad).label('total_producido')
    ).group_by(ProduccionDiaria.producto_id).all()

    totales_dict = {r.producto_id: float(r.total_producido) for r in producciones_totales}

    # 2. Calcular límites de la semana actual (Lunes a Viernes)
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    # 3. Obtener producciones de la semana actual (Lunes a Viernes)
    producciones_semanales = db.session.query(
        ProduccionDiaria.producto_id,
        func.sum(ProduccionDiaria.cantidad).label('total_semanal')
    ).filter(
        ProduccionDiaria.fecha_produccion >= monday,
        ProduccionDiaria.fecha_produccion <= friday
    ).group_by(ProduccionDiaria.producto_id).all()

    semanales_dict = {r.producto_id: float(r.total_semanal) for r in producciones_semanales}

    # Mostrar solo productos que tienen al menos un registro de producción (cargado/manipulado por la fábrica)
    productos = Producto.query.filter(Producto.id.in_(totales_dict.keys())).order_by(Producto.nombre).all()

    # Sincronizar en base de datos los productos vinculados con materias primas
    for p in productos:
        mp_vinc = p.get_materia_prima_vinculada()
        if mp_vinc and p.stock_actual != mp_vinc.stock_actual:
            p.stock_actual = mp_vinc.stock_actual
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return render_template(
        'fabrica/stock.html',
        title='Stock Actual',
        productos=productos,
        semanales_dict=semanales_dict
    )




@fabrica_bp.route('/diagnostico')
@operario_requerido
def diagnostico():
    """
    Diagnóstico del estado de la BD en producción.
    Muestra si las columnas existen, el stock de cada producto
    y los últimos pedidos con su producto_id.
    """
    from sqlalchemy import text, inspect as sa_inspect

    resultado = {}

    # 1. Verificar columnas en tabla productos
    try:
        inspector = sa_inspect(db.engine)
        cols_productos = [c['name'] for c in inspector.get_columns('productos')]
        cols_pedidos   = [c['name'] for c in inspector.get_columns('pedidos')]
        resultado['columnas_productos'] = cols_productos
        resultado['columnas_pedidos']   = cols_pedidos
        resultado['stock_actual_existe'] = 'stock_actual' in cols_productos
        resultado['producto_id_existe']  = 'producto_id' in cols_pedidos
    except Exception as e:
        resultado['error_columnas'] = str(e)

    # 2. Stock actual de cada producto
    try:
        productos = Producto.query.order_by(Producto.nombre).all()
        resultado['productos'] = [
            {
                'id': p.id,
                'nombre': p.nombre,
                'stock_actual': float(p.stock_actual or 0),
                'unidad': p.unidad,
            }
            for p in productos
        ]
    except Exception as e:
        resultado['error_productos'] = str(e)

    # 3. Últimos 10 pedidos con producto_id
    try:
        pedidos = Pedido.query.order_by(Pedido.id.desc()).limit(10).all()
        resultado['pedidos_recientes'] = [
            {
                'id': p.id,
                'producto_nombre': p.producto_nombre,
                'producto_id': p.producto_id,
                'cantidad': float(p.cantidad or 0),
                'estado': p.estado,
            }
            for p in pedidos
        ]
    except Exception as e:
        resultado['error_pedidos'] = str(e)

    # 4. Tabla alembic_version
    try:
        rows = db.session.execute(text('SELECT version_num FROM alembic_version')).fetchall()
        resultado['alembic_versions'] = [r[0] for r in rows]
    except Exception as e:
        resultado['error_alembic'] = str(e)

    return jsonify(resultado)


# ─────────────────────────────────────────────
# HELPER COMPARTIDO: Materias primas y producción
# ─────────────────────────────────────────────

def _preview_materias_primas(producto_id, cantidad):
    """
    Calcula las materias primas a descontar para una producción.
    Devuelve una lista de grupos listos para el modal de confirmación.

    Cada elemento del resultado tiene:
      - grupo_id: None si es ingrediente único, número si hay variantes
      - ingredientes: lista de MPs del grupo con cantidad calculada
      - seleccionado_id: MP preseleccionada (la primera del grupo)
    """
    formulaciones = FormulacionProducto.query.filter_by(
        producto_id=producto_id
    ).all()

    if not formulaciones:
        return []

    # Agrupar por grupo_alternativa
    grupos = {}  # grupo_id -> [formulacion, ...]
    unicos = []  # formulaciones sin grupo

    for f in formulaciones:
        if f.grupo_alternativa is None:
            unicos.append(f)
        else:
            grupos.setdefault(f.grupo_alternativa, []).append(f)

    resultado = []

    # Ingredientes únicos (sin variantes)
    for f in unicos:
        mp = f.materia_prima
        cantidad_calculada = round(float(f.cantidad_por_unidad) * cantidad, 4)
        resultado.append({
            'grupo_id': None,
            'ingredientes': [{
                'mp_id': mp.id,
                'mp_nombre': mp.nombre,
                'mp_unidad': mp.unidad,
                'stock_actual': float(mp.stock_actual or 0),
                'cantidad_calculada': cantidad_calculada,
            }],
            'seleccionado_id': mp.id,
        })

    # Grupos con variantes (el usuario elige cuál usó)
    for grupo_id, formulaciones_grupo in grupos.items():
        ingredientes = []
        for f in formulaciones_grupo:
            mp = f.materia_prima
            cantidad_calculada = round(float(f.cantidad_por_unidad) * cantidad, 4)
            ingredientes.append({
                'mp_id': mp.id,
                'mp_nombre': mp.nombre,
                'mp_unidad': mp.unidad,
                'stock_actual': float(mp.stock_actual or 0),
                'cantidad_calculada': cantidad_calculada,
            })
        resultado.append({
            'grupo_id': grupo_id,
            'ingredientes': ingredientes,
            'seleccionado_id': ingredientes[0]['mp_id'],
        })

    return resultado


def _validar_stock_materias_primas(producto_id, cantidad, materias_primas_data=None):
    """
    Valida que todas las materias primas necesarias para la producción tengan stock suficiente.
    Retorna (True, None) si todo el stock es suficiente, o (False, mensaje_error) si falta stock.
    """
    if materias_primas_data:
        for item in materias_primas_data:
            if item.get('excluida'):
                continue

            mp_id = item.get('mp_id')
            cant_consumir = float(item.get('cantidad', 0))

            if not mp_id or cant_consumir <= 0:
                continue

            mp = MateriaPrima.query.get(mp_id)
            if not mp:
                continue

            stock_actual = float(mp.stock_actual or 0)
            if stock_actual < cant_consumir or stock_actual <= 0:
                return False, (
                    f"No se puede registrar la producción: La materia prima '{mp.nombre}' no tiene stock suficiente. "
                    f"Stock disponible: {stock_actual:.2f} {mp.unidad}, requerido: {cant_consumir:.2f} {mp.unidad}. "
                    f"Por favor, actualicen el stock de materia prima antes de registrar la producción."
                )
    else:
        formulaciones = FormulacionProducto.query.filter_by(producto_id=producto_id).all()
        grupos_vistos = set()
        for f in formulaciones:
            if f.grupo_alternativa is not None:
                if f.grupo_alternativa in grupos_vistos:
                    continue
                grupos_vistos.add(f.grupo_alternativa)

            mp = f.materia_prima
            if not mp:
                continue

            cant_necesaria = float(f.cantidad_por_unidad) * float(cantidad)
            stock_actual = float(mp.stock_actual or 0)
            if stock_actual < cant_necesaria or stock_actual <= 0:
                return False, (
                    f"No se puede registrar la producción: La materia prima '{mp.nombre}' no tiene stock suficiente. "
                    f"Stock disponible: {stock_actual:.2f} {mp.unidad}, requerido: {cant_necesaria:.2f} {mp.unidad}. "
                    f"Por favor, actualicen el stock de materia prima antes de registrar la producción."
                )

    return True, None


def _registrar_movimientos_mp(produccion_id, materias_primas_data, usuario_id):
    """
    Registra los movimientos de stock de materias primas para una producción.
    materias_primas_data: lista de dicts con {mp_id, cantidad, excluida}
    Si una MP consumida está vinculada a un Producto del catálogo, descuenta también de ese Producto.
    """
    produccion = ProduccionDiaria.query.get(produccion_id)
    if produccion and produccion.producto:
        producto_nombre = produccion.producto.nombre
        cant_prod = float(produccion.cantidad or 0)
        unid_prod = produccion.unidad or ''
        desc_base = f'Producción #{produccion_id} - {producto_nombre} ({cant_prod:.2f} {unid_prod})'
    else:
        desc_base = f'Producción #{produccion_id}'

    for item in materias_primas_data:
        if item.get('excluida'):
            continue

        mp_id = item.get('mp_id')
        cantidad = float(item.get('cantidad', 0))

        if not mp_id or cantidad <= 0:
            continue

        mp = MateriaPrima.query.get(mp_id)
        if not mp:
            continue

        # Descontar stock de la Materia Prima
        mp.descontar_stock(cantidad)

        # Si esta MP está vinculada a un Producto, descontar también del Producto
        prod_vinc = mp.get_producto_vinculado()
        if prod_vinc:
            prod_vinc.descontar_stock(cantidad)

        # Registrar movimiento
        mov = MovimientoMateriaPrima(
            materia_prima_id=mp_id,
            tipo='egreso_produccion',
            cantidad=cantidad,
            descripcion=desc_base,
            produccion_id=produccion_id,
            usuario_id=usuario_id,
        )
        db.session.add(mov)


# ─────────────────────────────────────────────
# SECCIÓN: PRODUCCIÓN (accesible para fábrica Y administración)
# ─────────────────────────────────────────────

@fabrica_bp.route('/produccion/preview-materias')
@fabrica_o_admin_requerido
def preview_materias_produccion():
    """
    Endpoint AJAX: devuelve la lista de materias primas calculadas para
    una producción, agrupadas por grupo_alternativa.
    También devuelve todas las MPs disponibles para que el usuario pueda
    agregar extras que no estén en la fórmula.
    """
    producto_id = request.args.get('producto_id', type=int)
    cantidad = request.args.get('cantidad', type=float)

    if not producto_id or not cantidad or cantidad <= 0:
        return jsonify({'grupos': [], 'todas_mp': []})

    grupos = _preview_materias_primas(producto_id, cantidad)

    # Todas las MPs activas para el selector de "agregar extra"
    todas_mp = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()

    return jsonify({
        'grupos': grupos,
        'todas_mp': [{'id': mp.id, 'nombre': mp.nombre, 'unidad': mp.unidad,
                      'stock_actual': float(mp.stock_actual or 0)} for mp in todas_mp],
    })


@fabrica_bp.route('/produccion', methods=['GET', 'POST'])
@fabrica_o_admin_requerido
def produccion():
    """
    Ver y cargar producción diaria.
    Accesible tanto para operarios de fábrica como para administración.
    Fábrica NO puede agregar productos al catálogo (eso sigue siendo exclusivo de administración).
    GET: muestra historial filtrado por fecha.
    POST: registra producción, suma al stock del producto y descuenta materias primas.
    """
    if request.method == 'POST':
        producto_id = request.form.get('producto_id', type=int)
        cantidad = request.form.get('cantidad', type=float)
        unidad = request.form.get('unidad', '').strip()
        fecha_str = request.form.get('fecha_produccion', '').strip()
        observaciones = request.form.get('observaciones', '').strip() or None
        materias_primas_json = request.form.get('materias_primas_json', '').strip()

        # Validaciones básicas
        if not producto_id or not cantidad or not unidad:
            flash('Producto, cantidad y unidad son obligatorios.', 'danger')
            return redirect(url_for('fabrica.produccion'))

        if cantidad <= 0:
            flash('La cantidad debe ser mayor a cero.', 'danger')
            return redirect(url_for('fabrica.produccion'))

        producto = Producto.query.get_or_404(producto_id)

        # Validar stock de materias primas antes de proceder
        mp_data = []
        if materias_primas_json:
            try:
                mp_data = json.loads(materias_primas_json)
            except Exception:
                mp_data = []

        stock_valido, error_stock = _validar_stock_materias_primas(producto_id, cantidad, mp_data)
        if not stock_valido:
            flash(error_stock, 'danger')
            return redirect(url_for('fabrica.produccion'))

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

        # Sincronizar con Materia Prima vinculada si este producto es también un insumo
        mp_vinc = producto.get_materia_prima_vinculada()
        if mp_vinc:
            mp_vinc.agregar_stock(cantidad)
            producto.stock_actual = mp_vinc.stock_actual

        # Flush para obtener prod.id antes de los movimientos
        db.session.flush()

        # Registrar movimiento de ingreso para la MP vinculada
        if mp_vinc:
            mov_mp_in = MovimientoMateriaPrima(
                materia_prima_id=mp_vinc.id,
                tipo='ingreso',
                cantidad=cantidad,
                descripcion=f'Ingreso automático por Producción #{prod.id} de {producto.nombre}',
                produccion_id=prod.id,
                usuario_id=current_user.id
            )
            db.session.add(mov_mp_in)

        # Registrar movimientos de materias primas si vienen del modal
        if materias_primas_json:
            try:
                mp_data = json.loads(materias_primas_json)
                _registrar_movimientos_mp(prod.id, mp_data, current_user.id)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f'Error procesando materias primas en produccion #{prod.id}: {e}')

        db.session.commit()
        flash(f'Se registraron {cantidad} {unidad} de {producto.nombre} y se actualizaron los stocks.', 'success')
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
@fabrica_o_admin_requerido
def eliminar_produccion(prod_id):
    """
    Eliminar un registro de producción y restar del stock del producto.
    También revierte los movimientos de materias primas asociados.
    """
    prod = ProduccionDiaria.query.get_or_404(prod_id)
    producto = Producto.query.get(prod.producto_id)

    if producto:
        producto.descontar_stock(float(prod.cantidad))
        # Revertir stock de MP vinculada
        mp_vinc = producto.get_materia_prima_vinculada()
        if mp_vinc:
            mp_vinc.descontar_stock(float(prod.cantidad))

    # Revertir movimientos de MP asociados a esta producción
    movimientos_mp = MovimientoMateriaPrima.query.filter_by(
        produccion_id=prod_id
    ).all()
    for mov in movimientos_mp:
        if mov.tipo == 'egreso_produccion':
            mp = MateriaPrima.query.get(mov.materia_prima_id)
            if mp:
                mp.agregar_stock(float(mov.cantidad))
                prod_vinc = mp.get_producto_vinculado()
                if prod_vinc:
                    prod_vinc.agregar_stock(float(mov.cantidad))
        db.session.delete(mov)

    nombre_prod = producto.nombre if producto else 'desconocido'
    cantidad = float(prod.cantidad)
    unidad = prod.unidad

    db.session.delete(prod)
    db.session.commit()

    flash(f'Se eliminó la producción de {cantidad} {unidad} de {nombre_prod} y se ajustó el stock.', 'warning')
    return redirect(url_for('fabrica.produccion'))