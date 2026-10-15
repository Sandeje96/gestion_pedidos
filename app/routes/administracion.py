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
from app.models.materia_prima import MateriaPrima
from app.models.movimiento_materia_prima import MovimientoMateriaPrima
from app.models.personal import Personal, RegistroAsistencia, formatear_minutos
from app.routes.fabrica import _descontar_stock_pedido, _preview_materias_primas, _registrar_movimientos_mp, _validar_stock_materias_primas
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import func
import json

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


def administracion_o_gerente_requerido(f):
    """
    Decorador para verificar que el usuario sea del área de Administración de Fábrica o Gerente.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not (current_user.es_administracion() or current_user.es_gerente()):
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ─────────────────────────────────────────────
# SECCIÓN: AJUSTE PARCIAL DE CANTIDAD
# ─────────────────────────────────────────────

@administracion_bp.route('/pedido/<int:pedido_id>/resolver-ajuste', methods=['POST'])
@administracion_requerido
def resolver_ajuste(pedido_id):
    """
    Administración resuelve una solicitud de ajuste de cantidad propuesta por Fábrica.
    Acciones posibles:
      - 'aprobar': acepta la cantidad propuesta por Fábrica (o una cantidad nueva si contraproponemos).
      - 'rechazar': rechaza la propuesta; la cantidad original queda intacta.
    """
    pedido = Pedido.query.get_or_404(pedido_id)

    # Solo pedidos de fábrica con ajuste pendiente
    if pedido.destinatario not in ['fabrica', 'admin_minorista', 'admin_mayorista']:
        return jsonify({'success': False, 'error': 'Pedido no elegible para resolución de ajuste'}), 403

    if not pedido.ajuste_pendiente:
        return jsonify({'success': False, 'error': 'No hay ajuste pendiente en este pedido'}), 400

    data = request.get_json(force=True, silent=True) or {}
    accion = data.get('accion')  # 'aprobar' | 'rechazar'
    nueva_cantidad_raw = data.get('nueva_cantidad')
    nota_respuesta = data.get('nota', '').strip() or None

    if accion not in ['aprobar', 'rechazar']:
        return jsonify({'success': False, 'error': 'Acción inválida. Use "aprobar" o "rechazar"'}), 400

    try:
        cantidad_original = float(pedido.cantidad)
        cantidad_propuesta_fab = float(pedido.cantidad_propuesta) if pedido.cantidad_propuesta else None

        if accion == 'aprobar':
            # Determinar cantidad final: contraproposición o la de Fábrica
            if nueva_cantidad_raw is not None:
                try:
                    nueva_cantidad = float(nueva_cantidad_raw)
                    if nueva_cantidad <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    return jsonify({'success': False, 'error': 'Nueva cantidad inválida'}), 400
            else:
                nueva_cantidad = None  # Usar la propuesta de Fábrica

            cantidad_final = nueva_cantidad if nueva_cantidad is not None else cantidad_propuesta_fab
            pedido.aprobar_ajuste(nueva_cantidad)

            texto_mensaje = (
                f"✅ AJUSTE APROBADO por Administración\n"
                f"• Cantidad original: {cantidad_original:g} {pedido.unidad or ''}\n"
                f"• Cantidad propuesta por Fábrica: {cantidad_propuesta_fab:g} {pedido.unidad or ''}\n"
                f"• Cantidad APROBADA: {cantidad_final:g} {pedido.unidad or ''}"
            )
            if nota_respuesta:
                texto_mensaje += f"\n• Nota: {nota_respuesta}"

            tipo_mensaje = 'ajuste_aprobado'
            evento_ws = 'pedido_ajuste_resuelto'

        else:  # rechazar
            pedido.rechazar_ajuste()
            texto_mensaje = (
                f"❌ AJUSTE RECHAZADO por Administración\n"
                f"• Cantidad original mantiene: {cantidad_original:g} {pedido.unidad or ''}\n"
                f"• Propuesta de Fábrica ({cantidad_propuesta_fab:g}) fue rechazada"
            )
            if nota_respuesta:
                texto_mensaje += f"\n• Motivo: {nota_respuesta}"

            tipo_mensaje = 'ajuste_rechazado'
            evento_ws = 'pedido_ajuste_resuelto'

        # Notificar a Fábrica
        pedido.visto_por_fabrica = False

        from app.models.mensaje_pedido import MensajePedido
        mensaje = MensajePedido(
            pedido_id=pedido.id,
            usuario_id=current_user.id,
            mensaje=texto_mensaje,
            tipo=tipo_mensaje,
            leido=False
        )
        db.session.add(mensaje)
        db.session.commit()

        socketio.emit(evento_ws, {
            'pedido': pedido.to_dict(),
            'accion': accion,
            'resuelto_por': current_user.nombre,
        }, namespace='/')

        return jsonify({
            'success': True,
            'message': f'Ajuste {"aprobado" if accion == "aprobar" else "rechazado"} correctamente',
            'pedido': pedido.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

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

    # Ajustes pendientes solicitados por fábrica
    ajustes_fabrica = sum(1 for p in pedidos_fabrica if p.ajuste_pendiente)
    ajustes_minoristas = sum(1 for p in pedidos_minoristas if p.ajuste_pendiente)
    ajustes_mayoristas = sum(1 for p in pedidos_mayoristas if p.ajuste_pendiente)
    total_ajustes = ajustes_fabrica + ajustes_minoristas + ajustes_mayoristas

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
        ajustes_fabrica=ajustes_fabrica,
        ajustes_minoristas=ajustes_minoristas,
        ajustes_mayoristas=ajustes_mayoristas,
        total_ajustes=total_ajustes,
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

# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# SECCIÓN: PRODUCCIÓN DIARIA Y STOCK
# ─────────────────────────────────────────────

@administracion_bp.route('/produccion/preview-materias')
@administracion_o_gerente_requerido
def preview_materias_produccion():
    """
    Endpoint AJAX: devuelve la lista de materias primas calculadas para
    una producción, agrupadas por grupo_alternativa.
    """
    producto_id = request.args.get('producto_id', type=int)
    cantidad = request.args.get('cantidad', type=float)

    if not producto_id or not cantidad or cantidad <= 0:
        return jsonify({'grupos': [], 'todas_mp': []})

    grupos = _preview_materias_primas(producto_id, cantidad)

    todas_mp = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()

    return jsonify({
        'grupos': grupos,
        'todas_mp': [{'id': mp.id, 'nombre': mp.nombre, 'unidad': mp.unidad,
                      'stock_actual': float(mp.stock_actual or 0)} for mp in todas_mp],
    })


@administracion_bp.route('/produccion', methods=['GET', 'POST'])
@administracion_o_gerente_requerido
def produccion():
    """
    Ver y cargar producción diaria.
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
            return redirect(url_for('administracion.produccion'))

        if cantidad <= 0:
            flash('La cantidad debe ser mayor a cero.', 'danger')
            return redirect(url_for('administracion.produccion'))

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
            return redirect(url_for('administracion.produccion'))

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
        stock_ant_mp = (mp_vinc.stock_actual or 0) if mp_vinc else 0
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
                usuario_id=current_user.id,
                stock_anterior=stock_ant_mp,
                stock_resultante=mp_vinc.stock_actual
            )
            db.session.add(mov_mp_in)

        # Registrar movimientos de materias primas si vienen del modal
        if materias_primas_json:
            try:
                mp_data = json.loads(materias_primas_json)
                _registrar_movimientos_mp(prod.id, mp_data, current_user.id)
            except Exception as e:
                pass  # No bloquear si hay error en MP

        db.session.commit()
        flash(f'Se registraron {cantidad} {unidad} de {producto.nombre} y se actualizaron los stocks.', 'success')
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

    # Precargar movimientos de MP por producción para mostrar en la tabla
    # (evita problemas de lazy loading en el template)
    prod_ids = [p.id for p in producciones]
    movimientos_por_produccion = {}
    if prod_ids:
        movs = MovimientoMateriaPrima.query.filter(
            MovimientoMateriaPrima.produccion_id.in_(prod_ids),
            MovimientoMateriaPrima.tipo == 'egreso_produccion'
        ).all()
        for m in movs:
            movimientos_por_produccion.setdefault(m.produccion_id, []).append(m.to_dict())

    return render_template(
        'administracion/produccion.html',
        title='Carga de Producción',
        producciones=producciones,
        productos=productos,
        fecha_filtro=fecha_filtro,
        hoy=date.today(),
        totales_dia=totales_dia,
        movimientos_por_produccion=movimientos_por_produccion
    )


@administracion_bp.route('/produccion/<int:prod_id>/eliminar', methods=['POST'])
@administracion_o_gerente_requerido
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
    nuevo_stock = request.form.get('stock_actual')
    
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
    
    if nuevo_stock is not None:
        try:
            val_stock = float(nuevo_stock)
            producto.stock_actual = val_stock
            # Si el producto tiene una MP vinculada, mantener ambos stocks sincronizados
            mp_vinc = producto.get_materia_prima_vinculada()
            if mp_vinc:
                mp_vinc.stock_actual = val_stock
        except ValueError:
            flash('Valor de stock inválido.', 'danger')
    
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


# ─────────────────────────────────────────────────────────────
# SECCIÓN: CONTROL DE HORARIOS, ASISTENCIA Y BANCO DE HORAS
# ─────────────────────────────────────────────────────────────

@administracion_bp.route('/personal', methods=['GET'])
@administracion_o_gerente_requerido
def personal():
    """
    Panel de Gestión de Personal, Asistencias Diarias y Banco de Horas.
    Horario habitual: 08:00 a 17:00 hs (lunes a sábado).
    Permite registrar horarios de ingreso y salida diarios, calcular horas a favor / adeudadas
    y gestionar compensaciones durante la semana.
    """
    OFFSET_ARG = timedelta(hours=3)
    hoy_arg = (datetime.utcnow() - OFFSET_ARG).date()

    fecha_str = request.args.get('fecha')
    if fecha_str:
        try:
            fecha_sel = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            fecha_sel = hoy_arg
    else:
        fecha_sel = hoy_arg

    fecha_ant = fecha_sel - timedelta(days=1)
    fecha_sig = fecha_sel + timedelta(days=1)

    DIAS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    dia_semana_nombre = DIAS_ES[fecha_sel.weekday()]
    es_sabado = (fecha_sel.weekday() == 5)
    es_domingo = (fecha_sel.weekday() == 6)

    # Personal activo e inactivo
    personal_list = Personal.query.order_by(Personal.nombre.asc(), Personal.apellido.asc()).all()
    activos = [p for p in personal_list if p.activo]
    inactivos = [p for p in personal_list if not p.activo]

    # Asistencias existentes en la fecha seleccionada
    asistencias_map = {
        a.personal_id: a
        for a in RegistroAsistencia.query.filter_by(fecha=fecha_sel).all()
    }

    # Planilla del día combinando personal y registros
    planilla_dia = []
    for p in activos:
        asist = asistencias_map.get(p.id)
        pact_ing, pact_sal, pact_mins = p.get_horario_pactado_para_fecha(fecha_sel)

        if asist:
            ingreso = asist.hora_ingreso
            salida = asist.hora_salida
            tipo_dia = asist.tipo_dia
            observaciones = asist.observaciones or ''
            dif_mins = asist.diferencia_minutos
            mins_trab = asist.minutos_trabajados
            registrado = True
        else:
            if es_domingo:
                tipo_dia = 'franco'
                ingreso = ''
                salida = ''
            elif es_sabado and not p.trabaja_sabados:
                tipo_dia = 'franco'
                ingreso = ''
                salida = ''
            else:
                tipo_dia = 'normal'
                ingreso = pact_ing or '08:00'
                salida = pact_sal or '17:00'
            observaciones = ''
            dif_mins = 0
            mins_trab = pact_mins
            registrado = False

        planilla_dia.append({
            'personal': p,
            'asistencia': asist,
            'registrado': registrado,
            'hora_ingreso_pactada': pact_ing or '08:00',
            'hora_salida_pactada': pact_sal or '17:00',
            'hora_ingreso': ingreso,
            'hora_salida': salida,
            'tipo_dia': tipo_dia,
            'observaciones': observaciones,
            'diferencia_minutos': dif_mins,
            'diferencia_formateada': formatear_minutos(dif_mins),
            'minutos_trabajados': mins_trab,
            'minutos_esperados': pact_mins,
            'saldo_actual_minutos': p.get_saldo_banco_minutos(),
            'saldo_actual_formateado': p.saldo_formateado,
            'saldo_estado': p.saldo_estado,
        })

    # Estadísticas globales del Banco de Horas
    total_a_favor = 0
    cant_a_favor = 0
    total_adeudado = 0
    cant_adeudado = 0
    cant_al_dia = 0

    for p in activos:
        s = p.get_saldo_banco_minutos()
        if s > 0:
            cant_a_favor += 1
            total_a_favor += s
        elif s < 0:
            cant_adeudado += 1
            total_adeudado += abs(s)
        else:
            cant_al_dia += 1

    tab_activa = request.args.get('tab', 'diario')

    return render_template(
        'administracion/personal.html',
        fecha_sel=fecha_sel,
        fecha_ant=fecha_ant,
        fecha_sig=fecha_sig,
        dia_semana_nombre=dia_semana_nombre,
        es_sabado=es_sabado,
        es_domingo=es_domingo,
        planilla_dia=planilla_dia,
        personal_list=activos,
        inactivos=inactivos,
        cant_a_favor=cant_a_favor,
        total_a_favor_fmt=formatear_minutos(total_a_favor),
        cant_adeudado=cant_adeudado,
        total_adeudado_fmt=formatear_minutos(-total_adeudado),
        cant_al_dia=cant_al_dia,
        hoy_arg=hoy_arg,
        tab_activa=tab_activa,
    )


@administracion_bp.route('/personal/nuevo', methods=['POST'])
@administracion_o_gerente_requerido
def nuevo_personal():
    """
    Registrar un nuevo integrante del personal de fábrica.
    """
    nombre = request.form.get('nombre', '').strip()
    apellido = request.form.get('apellido', '').strip()
    dni = request.form.get('dni', '').strip() or None
    telefono = request.form.get('telefono', '').strip() or None
    puesto = request.form.get('puesto', '').strip() or 'Fábrica / Producción'

    hora_ingreso = request.form.get('hora_ingreso_habitual', '08:00').strip() or '08:00'
    hora_salida = request.form.get('hora_salida_habitual', '17:00').strip() or '17:00'
    trabaja_sabados = bool(request.form.get('trabaja_sabados'))
    hora_ingreso_sabado = request.form.get('hora_ingreso_sabado', '08:00').strip() or '08:00'
    hora_salida_sabado = request.form.get('hora_salida_sabado', '17:00').strip() or '17:00'

    saldo_horas = request.form.get('saldo_inicial_horas', '0').strip()
    saldo_minutos = request.form.get('saldo_inicial_minutos', '0').strip()
    notas = request.form.get('notas', '').strip() or None

    if not nombre:
        flash('El nombre del personal es obligatorio.', 'danger')
        return redirect(url_for('administracion.personal', tab='personal'))

    try:
        sh = float(saldo_horas or 0)
        sm = int(saldo_minutos or 0)
        total_saldo_inicial = int(sh * 60) + (sm if sh >= 0 else -sm)
    except ValueError:
        total_saldo_inicial = 0

    p = Personal(
        nombre=nombre,
        apellido=apellido,
        dni=dni,
        telefono=telefono,
        puesto=puesto,
        hora_ingreso_habitual=hora_ingreso,
        hora_salida_habitual=hora_salida,
        trabaja_sabados=trabaja_sabados,
        hora_ingreso_sabado=hora_ingreso_sabado,
        hora_salida_sabado=hora_salida_sabado,
        saldo_inicial_minutos=total_saldo_inicial,
        activo=True,
        notas=notas,
    )
    db.session.add(p)
    db.session.commit()
    flash(f'✅ Personal "{p.nombre_completo}" agregado correctamente.', 'success')
    return redirect(url_for('administracion.personal', tab='personal'))


@administracion_bp.route('/personal/<int:personal_id>/editar', methods=['POST'])
@administracion_o_gerente_requerido
def editar_personal(personal_id):
    """
    Editar datos de un personal existente.
    """
    p = Personal.query.get_or_404(personal_id)
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash('El nombre no puede estar vacío.', 'danger')
        return redirect(url_for('administracion.personal', tab='personal'))

    p.nombre = nombre
    p.apellido = request.form.get('apellido', '').strip()
    p.dni = request.form.get('dni', '').strip() or None
    p.telefono = request.form.get('telefono', '').strip() or None
    p.puesto = request.form.get('puesto', '').strip() or 'Fábrica / Producción'
    p.hora_ingreso_habitual = request.form.get('hora_ingreso_habitual', '08:00').strip() or '08:00'
    p.hora_salida_habitual = request.form.get('hora_salida_habitual', '17:00').strip() or '17:00'
    p.trabaja_sabados = bool(request.form.get('trabaja_sabados'))
    p.hora_ingreso_sabado = request.form.get('hora_ingreso_sabado', '08:00').strip() or '08:00'
    p.hora_salida_sabado = request.form.get('hora_salida_sabado', '17:00').strip() or '17:00'
    p.notas = request.form.get('notas', '').strip() or None

    db.session.commit()
    flash(f'✅ Datos de "{p.nombre_completo}" actualizados correctamente.', 'success')
    return redirect(url_for('administracion.personal', tab='personal'))


@administracion_bp.route('/personal/<int:personal_id>/toggle-activo', methods=['POST'])
@administracion_o_gerente_requerido
def toggle_activo_personal(personal_id):
    """
    Activar o desactivar a un empleado.
    """
    p = Personal.query.get_or_404(personal_id)
    p.activo = not p.activo
    db.session.commit()
    estado = "activado" if p.activo else "dado de baja"
    flash(f'El personal "{p.nombre_completo}" fue {estado}.', 'info')
    return redirect(url_for('administracion.personal', tab='personal'))


def _normalizar_hhmm(val):
    """Limpia y estandariza cadenas de hora al formato HH:MM (ej. '8' -> '08:00', '1730' -> '17:30')."""
    if not val:
        return None
    val = str(val).strip()
    if not val:
        return None
    if ':' in val or '.' in val or ',' in val:
        sep = ':' if ':' in val else ('.' if '.' in val else ',')
        parts = val.split(sep)
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
            if 0 <= h <= 24 and 0 <= m < 60:
                return f"{h:02d}:{m:02d}"
        except (ValueError, TypeError):
            return val
    elif val.isdigit():
        try:
            if len(val) <= 2:
                h = int(val)
                if 0 <= h <= 24:
                    return f"{h:02d}:00"
            elif len(val) == 3:
                h, m = int(val[0]), int(val[1:])
                if 0 <= h <= 24 and 0 <= m < 60:
                    return f"{h:02d}:{m:02d}"
            elif len(val) >= 4:
                h, m = int(val[:2]), int(val[2:4])
                if 0 <= h <= 24 and 0 <= m < 60:
                    return f"{h:02d}:{m:02d}"
        except (ValueError, TypeError):
            return val
    return val


@administracion_bp.route('/personal/guardar-asistencias', methods=['POST'])
@administracion_o_gerente_requerido
def guardar_asistencias():
    """
    Guarda o actualiza las asistencias diarias para la fecha indicada.
    Soporta envío masivo JSON o envío por formulario tradicional.
    """
    if request.is_json:
        data = request.get_json() or {}
        fecha_str = data.get('fecha')
        registros = data.get('registros', [])
    else:
        fecha_str = request.form.get('fecha')
        registros = []
        personal_ids = request.form.getlist('personal_ids[]') or request.form.getlist('personal_id')
        for pid in personal_ids:
            registros.append({
                'personal_id': int(pid),
                'hora_ingreso': request.form.get(f'hora_ingreso_{pid}', '').strip(),
                'hora_salida': request.form.get(f'hora_salida_{pid}', '').strip(),
                'tipo_dia': request.form.get(f'tipo_dia_{pid}', 'normal').strip(),
                'observaciones': request.form.get(f'observaciones_{pid}', '').strip(),
            })

    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        OFFSET_ARG = timedelta(hours=3)
        fecha_obj = (datetime.utcnow() - OFFSET_ARG).date()

    guardados = 0
    for reg in registros:
        pid = reg.get('personal_id')
        if not pid:
            continue
        p = Personal.query.get(pid)
        if not p:
            continue

        hora_ing = _normalizar_hhmm(reg.get('hora_ingreso', ''))
        hora_sal = _normalizar_hhmm(reg.get('hora_salida', ''))
        tipo_dia = reg.get('tipo_dia', 'normal').strip() or 'normal'
        obs = reg.get('observaciones', '').strip() or None

        pact_ing, pact_sal, pact_mins = p.get_horario_pactado_para_fecha(fecha_obj)

        asist = RegistroAsistencia.query.filter_by(personal_id=p.id, fecha=fecha_obj).first()
        if not asist:
            asist = RegistroAsistencia(
                personal_id=p.id,
                fecha=fecha_obj,
                hora_ingreso_pactada=pact_ing or '08:00',
                hora_salida_pactada=pact_sal or '17:00',
                registrado_por_id=current_user.id
            )
            db.session.add(asist)

        asist.hora_ingreso = hora_ing
        asist.hora_salida = hora_sal
        asist.tipo_dia = tipo_dia
        asist.observaciones = obs
        asist.hora_ingreso_pactada = pact_ing or '08:00'
        asist.hora_salida_pactada = pact_sal or '17:00'
        asist.registrado_por_id = current_user.id
        asist.recalcular()
        guardados += 1

    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'guardados': guardados,
            'mensaje': f'Se guardaron {guardados} asistencias correctamente.'
        })

    flash(f'✅ Asistencias guardadas para el día {fecha_obj.strftime("%d/%m/%Y")} ({guardados} empleados).', 'success')
    return redirect(url_for('administracion.personal', fecha=fecha_obj.strftime('%Y-%m-%d'), tab='diario'))


@administracion_bp.route('/personal/<int:personal_id>/historial', methods=['GET'])
@administracion_o_gerente_requerido
def historial_personal(personal_id):
    """
    Devuelve el historial cronológico de asistencias y movimientos de banco de horas
    de un empleado en formato JSON para el modal interactivo.
    """
    p = Personal.query.get_or_404(personal_id)
    asistencias = RegistroAsistencia.query.filter_by(personal_id=p.id).order_by(RegistroAsistencia.fecha.desc()).all()

    DIAS_ES = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    items = []
    for a in asistencias:
        items.append({
            'id': a.id,
            'fecha': a.fecha.strftime('%d/%m/%Y'),
            'fecha_iso': a.fecha.strftime('%Y-%m-%d'),
            'dia_nombre': DIAS_ES[a.fecha.weekday()],
            'hora_ingreso': a.hora_ingreso or '—',
            'hora_salida': a.hora_salida or '—',
            'hora_ingreso_pactada': a.hora_ingreso_pactada,
            'hora_salida_pactada': a.hora_salida_pactada,
            'minutos_trabajados': a.minutos_trabajados,
            'horas_trabajadas': a.horas_trabajadas_formateadas,
            'minutos_esperados': a.minutos_esperados,
            'horas_esperadas': a.horas_esperadas_formateadas,
            'diferencia_minutos': a.diferencia_minutos,
            'diferencia_formateada': a.diferencia_formateada,
            'tipo_dia': a.tipo_dia,
            'observaciones': a.observaciones or '',
        })

    return jsonify({
        'personal': p.to_dict(),
        'historial': items,
    })


@administracion_bp.route('/personal/<int:personal_id>/ajustar-banco', methods=['POST'])
@administracion_o_gerente_requerido
def ajustar_banco(personal_id):
    """
    Asentar un ajuste manual o compensación acordada en el banco de horas.
    """
    p = Personal.query.get_or_404(personal_id)
    tipo_ajuste = request.form.get('tipo_ajuste', 'sumar')  # 'sumar' | 'restar' | 'fijar'
    minutos_raw = request.form.get('minutos', '0')
    horas_raw = request.form.get('horas', '0')
    motivo = request.form.get('motivo', '').strip() or 'Ajuste manual de banco de horas'

    try:
        h = float(horas_raw or 0)
        m = int(minutos_raw or 0)
        delta_mins = int(h * 60) + m
    except ValueError:
        flash('Valores de tiempo inválidos.', 'danger')
        return redirect(url_for('administracion.personal', tab='banco'))

    OFFSET_ARG = timedelta(hours=3)
    hoy_arg = (datetime.utcnow() - OFFSET_ARG).date()

    if tipo_ajuste == 'restar':
        delta_mins = -abs(delta_mins)
    elif tipo_ajuste == 'sumar':
        delta_mins = abs(delta_mins)
    elif tipo_ajuste == 'fijar':
        saldo_actual = p.get_saldo_banco_minutos()
        delta_mins = delta_mins - saldo_actual

    existente = RegistroAsistencia.query.filter_by(personal_id=p.id, fecha=hoy_arg).first()
    if existente:
        existente.diferencia_minutos += delta_mins
        existente.observaciones = (existente.observaciones or '') + f" | Ajuste: {motivo} ({formatear_minutos(delta_mins)})"
    else:
        asist = RegistroAsistencia(
            personal_id=p.id,
            fecha=hoy_arg,
            hora_ingreso=None,
            hora_salida=None,
            hora_ingreso_pactada='00:00',
            hora_salida_pactada='00:00',
            minutos_trabajados=max(0, delta_mins) if delta_mins > 0 else 0,
            minutos_esperados=abs(delta_mins) if delta_mins < 0 else 0,
            diferencia_minutos=delta_mins,
            tipo_dia='compensacion',
            observaciones=f"Ajuste manual: {motivo}",
            registrado_por_id=current_user.id
        )
        db.session.add(asist)

    db.session.commit()
    flash(f'✅ Banco de horas de {p.nombre_completo} actualizado ({formatear_minutos(delta_mins)}).', 'success')
    return redirect(url_for('administracion.personal', tab='banco'))


@administracion_bp.route('/personal/asistencia/<int:asistencia_id>/eliminar', methods=['POST'])
@administracion_o_gerente_requerido
def eliminar_asistencia(asistencia_id):
    """
    Eliminar un registro de asistencia específico.
    """
    asist = RegistroAsistencia.query.get_or_404(asistencia_id)
    fecha_str = asist.fecha.strftime('%Y-%m-%d')
    p_nombre = asist.personal.nombre_completo if asist.personal else 'Personal'
    db.session.delete(asist)
    db.session.commit()
    flash(f'Asistencia de {p_nombre} eliminada.', 'info')
    return redirect(url_for('administracion.personal', fecha=fecha_str))

