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
from app.models.boleta import Boleta, PagoBoleta
from app.forms.cliente_forms import ClienteForm
from app.forms.pedido_forms import PedidoForm, EditarPedidoForm
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import func

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
    
    # Obtener clientes activos EXCLUYENDO los de la ruta SUCURSALES (esos son del panel de sucursal)
    clientes = Cliente.query.join(Pedido).filter(
        Cliente.activo == True,
        Cliente.ruta != 'SUCURSALES',
        Pedido.archivado == False
    ).distinct().order_by(Cliente.ruta, Cliente.nombre).all()
    
    # Agrupar clientes por ruta
    from collections import defaultdict
    clientes_por_ruta = defaultdict(list)
    for cliente in clientes:
        clientes_por_ruta[cliente.ruta].append(cliente)
    
    # Convertir a dict normal y ordenar rutas
    clientes_por_ruta = dict(sorted(clientes_por_ruta.items()))
    
    # Estadísticas rápidas — solo pedidos de clientes que NO son SUCURSALES
    total_clientes = len(clientes)
    total_pedidos = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Cliente.ruta != 'SUCURSALES'
    ).count()
    pedidos_pendientes = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.estado == 'pendiente',
        Cliente.ruta != 'SUCURSALES'
    ).count()
    pedidos_completados = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.estado == 'completado',
        Cliente.ruta != 'SUCURSALES'
    ).count()

    # Notificaciones sin leer — solo de pedidos de clientes que NO son SUCURSALES
    pedidos_no_leidos = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Pedido.observaciones_fabrica.isnot(None),
        Pedido.visto_por_vendedor == False,
        Cliente.ruta != 'SUCURSALES'
    ).count()

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
        'ventas/dashboard.html',
        title='Panel de Ventas',
        clientes_por_ruta=clientes_por_ruta,
        litros_por_ruta=litros_por_ruta,
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
        
        # NUEVO SISTEMA: producto_id + presentacion + cantidad_envases
        producto_ids = request.form.getlist('producto_ids[]')
        presentaciones = request.form.getlist('presentaciones[]')
        cantidades_envases = request.form.getlist('cantidades_envases[]')
        notas = request.form.getlist('notas[]')

        # Tabla de conversión presentacion -> litros
        LITROS_POR_PRESENTACION = {
            '300ml': 0.30,
            '500ml': 0.50,
            '1litro': 1.00,
            '5litros': 5.00,
            '20litros': 20.00,
            '200litros': 200.00,
            '500litros': 500.00,
            '1000litros': 1000.00,
        }

        # Validar que haya al menos un producto
        tiene_producto = any(p for p in producto_ids if p and p.strip())
        if not tiene_producto:
            flash('Debes agregar al menos un pedido con producto', 'warning')
            productos_disponibles = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()
            return render_template('ventas/pedido_form.html', form=form, title='Nuevo Pedido', accion='Crear', productos_disponibles=productos_disponibles)

        # Crear múltiples pedidos
        pedidos_creados = []
        total_items = len(producto_ids)

        for i in range(total_items):
            pid_str = producto_ids[i] if i < len(producto_ids) else ''
            if not pid_str or not pid_str.strip():
                continue

            try:
                producto_obj = Producto.query.get(int(pid_str))
            except (ValueError, TypeError):
                continue
            if not producto_obj:
                continue

            presentacion = presentaciones[i] if i < len(presentaciones) else '1litro'
            if presentacion not in LITROS_POR_PRESENTACION:
                presentacion = '1litro'

            factor = LITROS_POR_PRESENTACION[presentacion]

            try:
                envases = float(cantidades_envases[i]) if i < len(cantidades_envases) and cantidades_envases[i] else 1.0
            except (ValueError, TypeError):
                envases = 1.0

            litros_totales = round(envases * factor, 4)
            nota = notas[i] if i < len(notas) and notas[i] else None

            try:
                pedido = Pedido(
                    cliente_id=cliente_id,
                    producto_nombre=producto_obj.nombre,
                    producto_id=producto_obj.id,
                    cantidad=litros_totales,
                    unidad='litros',
                    presentacion=presentacion,
                    cantidad_envases=envases,
                    litros_por_presentacion=factor,
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
    
    # Cargar lista de productos disponibles para el selector
    productos_disponibles = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()
    return render_template(
        'ventas/pedido_form.html',
        form=form,
        title='Nuevo Pedido',
        accion='Crear',
        productos_disponibles=productos_disponibles
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
    
    form = EditarPedidoForm(obj=pedido)
    
    if form.validate_on_submit():
        pedido.producto_nombre = form.producto_nombre.data
        pedido.cantidad = form.cantidad.data
        pedido.unidad = form.unidad.data
        pedido.notas_vendedor = form.notas_vendedor.data
        
        # Si cambió algo, marcar como modificado
        pedido.modificado = True
        pedido.visto_por_fabrica = False
        
        # NUEVO: Si el vendedor agregó o cambió notas, guardar mensaje
        if form.notas_vendedor.data and form.notas_vendedor.data != notas_anteriores:
            from app.models.mensaje_pedido import MensajePedido
            
            mensaje = MensajePedido(
                pedido_id=pedido.id,
                usuario_id=current_user.id,
                mensaje=form.notas_vendedor.data,
                tipo='vendedor',
                leido=False
            )
            db.session.add(mensaje)
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

@ventas_bp.route('/pedido/<int:pedido_id>/toggle-despachado', methods=['POST'])
@vendedor_requerido
def toggle_despachado(pedido_id):
    """
    AJAX: Alterna el estado despachado (SI/NO) de un pedido individual.
    """
    pedido = Pedido.query.get_or_404(pedido_id)

    try:
        pedido.despachado = not pedido.despachado
        pedido.fecha_actualizacion = datetime.utcnow()
        db.session.commit()

        # Notificar en tiempo real
        socketio.emit('pedido_actualizado', {
            'pedido': pedido.to_dict(),
            'despacho_cambiado': True,
        }, namespace='/')

        return jsonify({
            'success': True,
            'despachado': pedido.despachado,
            'pedido_id': pedido.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@ventas_bp.route('/cliente/<int:cliente_id>/despachar-todos', methods=['POST'])
@vendedor_requerido
def despachar_todos(cliente_id):
    """
    AJAX: Marca como despachado=True todos los pedidos activos de un cliente.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    pedidos = Pedido.query.filter_by(cliente_id=cliente_id, archivado=False).all()

    try:
        actualizados = 0
        for pedido in pedidos:
            if not pedido.despachado:
                pedido.despachado = True
                pedido.fecha_actualizacion = datetime.utcnow()
                actualizados += 1

        db.session.commit()

        # Notificar cada pedido actualizado
        for pedido in pedidos:
            socketio.emit('pedido_actualizado', {
                'pedido': pedido.to_dict(),
                'despacho_cambiado': True,
            }, namespace='/')

        return jsonify({
            'success': True,
            'actualizados': actualizados,
            'cliente_id': cliente_id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


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

@ventas_bp.route('/pedido/<int:pedido_id>/mensajes')
@vendedor_requerido
def ver_mensajes_pedido(pedido_id):
    """
    Ver historial de mensajes de un pedido.
    """
    pedido = Pedido.query.get_or_404(pedido_id)
    
    from app.models.mensaje_pedido import MensajePedido
    mensajes = MensajePedido.query.filter_by(pedido_id=pedido_id).order_by(MensajePedido.fecha_creacion.asc()).all()
    
    return render_template(
        'ventas/mensajes_pedido.html',
        pedido=pedido,
        mensajes=mensajes,
        title=f'Conversación - Pedido #{pedido.id}'
    )

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
    
    # Obtener solo los pedidos de clientes que NO son SUCURSALES
    # Los pedidos de sucursales tienen su propio ciclo de vida y no deben archivarse aquí
    pedidos_activos = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Cliente.ruta != 'SUCURSALES'
    ).all()
    
    if not pedidos_activos:
        flash('No hay pedidos activos para archivar', 'warning')
        return redirect(url_for('ventas.dashboard'))
    
    # Archivar los pedidos de ventas
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


@ventas_bp.route('/cerrar-semana-ruta/<path:ruta_nombre>', methods=['POST'])
@vendedor_requerido
def cerrar_semana_ruta(ruta_nombre):
    """
    Cierra la semana actual para una ruta específica,
    archivando únicamente los pedidos activos de esa ruta.
    """
    from datetime import datetime

    # Generar nombre de semana (misma lógica que cerrar_semana)
    fecha_actual = datetime.utcnow()
    mes_numero = fecha_actual.month
    meses_letras = {
        1: 'E', 2: 'F', 3: 'M', 4: 'A', 5: 'MY',
        6: 'JN', 7: 'JL', 8: 'AG', 9: 'S',
        10: 'O', 11: 'N', 12: 'D'
    }
    mes_letra = meses_letras[mes_numero]
    dia_del_mes = fecha_actual.day
    numero_semana_mes = ((dia_del_mes - 1) // 7) + 1
    nombre_semana = f"Semana {fecha_actual.year}-{numero_semana_mes}{mes_letra}"

    # Obtener pedidos activos SOLO de la ruta indicada (excluyendo SUCURSALES)
    pedidos_activos = Pedido.query.join(Cliente).filter(
        Pedido.archivado == False,
        Cliente.ruta == ruta_nombre,
        Cliente.ruta != 'SUCURSALES'
    ).all()

    if not pedidos_activos:
        flash(f'No hay pedidos activos para archivar en la ruta "{ruta_nombre}"', 'warning')
        return redirect(url_for('ventas.dashboard'))

    total_archivados = 0
    for pedido in pedidos_activos:
        pedido.archivar(nombre_semana)
        total_archivados += 1

    db.session.commit()

    # Notificar via WebSocket
    socketio.emit('semana_cerrada', {
        'semana': nombre_semana,
        'ruta': ruta_nombre,
        'total_archivados': total_archivados,
        'mensaje': f'Ruta "{ruta_nombre}": {total_archivados} pedidos archivados en {nombre_semana}'
    }, namespace='/')

    flash(f'✅ Ruta "{ruta_nombre}" cerrada: {total_archivados} pedido(s) archivado(s) en "{nombre_semana}"', 'success')
    return redirect(url_for('ventas.dashboard'))


@ventas_bp.route('/historial-semanas')
@vendedor_requerido
def historial_semanas():
    """
    Muestra el historial de semanas cerradas.
    """
    from datetime import datetime
    
    # Obtener semanas únicas de pedidos archivados (solo los que tienen semana definida)
    semanas = db.session.query(
        Pedido.semana_archivado,
        db.func.count(Pedido.id).label('total_pedidos'),
        db.func.min(Pedido.fecha_archivado).label('fecha')
    ).filter(
        Pedido.archivado == True,
        Pedido.semana_archivado.isnot(None)
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

@ventas_bp.route('/desarchivar-semana/<string:semana>', methods=['POST'])
@vendedor_requerido
def desarchivar_semana(semana):
    """
    Restaura todos los pedidos de una semana archivada, devolviéndolos al estado activo.
    Útil cuando se cerró la semana por error o se necesita recuperar los pedidos.
    """
    pedidos_archivados = Pedido.query.filter(
        Pedido.archivado == True,
        Pedido.semana_archivado == semana
    ).all()

    if not pedidos_archivados:
        flash(f'No se encontraron pedidos archivados en "{semana}"', 'warning')
        return redirect(url_for('ventas.historial_semanas'))

    total_restaurados = 0
    for pedido in pedidos_archivados:
        pedido.archivado = False
        pedido.fecha_archivado = None
        pedido.semana_archivado = None
        total_restaurados += 1

    db.session.commit()

    # Notificar via WebSocket
    socketio.emit('semana_desarchivada', {
        'semana': semana,
        'total_restaurados': total_restaurados,
        'mensaje': f'Se restauraron {total_restaurados} pedidos de "{semana}"'
    }, namespace='/')

    flash(f'✅ Se restauraron {total_restaurados} pedido(s) de "{semana}". Ya son visibles en el dashboard.', 'success')
    return redirect(url_for('ventas.dashboard'))


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


@ventas_bp.route('/api/productos')
@vendedor_requerido
def api_productos():
    """
    API: Obtener lista de productos disponibles para el selector de pedidos.
    """
    productos = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()
    return jsonify({
        'productos': [p.to_dict() for p in productos]
    })


# La ruta /productos/nuevo fue eliminada de ventas.
# Los productos solo pueden ser creados por Administración.


@ventas_bp.route('/stock')
@vendedor_requerido
def stock():
    """
    Permite al usuario de ventas visualizar el stock de productos en fábrica.
    """
    # 1. Obtener todas las producciones históricas para filtrar el catálogo
    from app.models import ProduccionDiaria
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

    return render_template(
        'fabrica/stock.html',
        title='Stock en Fábrica',
        productos=productos,
        semanales_dict=semanales_dict
    )


# ══════════════════════════════════════════════════════════
# MÓDULO DE BOLETAS — Solo visible para Ventas y Repartidor
# ══════════════════════════════════════════════════════════

@ventas_bp.route('/boletas')
@vendedor_requerido
def boletas():
    """
    Lista todos los clientes activos (no sucursales) agrupados por ruta,
    con el estado de su boleta del día y el saldo de cuenta corriente.
    Solo accesible por el usuario Vendedor.
    """
    hoy = date.today()

    clientes = (
        Cliente.query
        .filter(Cliente.activo == True, Cliente.ruta != 'SUCURSALES')
        .order_by(Cliente.ruta, Cliente.nombre)
        .all()
    )

    # Para cada cliente, obtener boleta activa y saldo CC
    datos_clientes = []
    for cliente in clientes:
        # Boleta de HOY solamente (fecha_entrega == hoy)
        # Si no hay boleta hoy, no se muestra en la columna Boleta hoy
        boleta_hoy = (
            Boleta.query
            .filter(
                Boleta.cliente_id == cliente.id,
                Boleta.fecha_entrega == hoy
            )
            .order_by(Boleta.fecha_creacion.desc())
            .first()
        )

        # Deuda pendiente (boletas de cualquier fecha con saldo sin cobrar)
        deuda_actual_agregada = db.session.query(
            func.sum(Boleta.saldo_pendiente)
        ).filter(
            Boleta.cliente_id == cliente.id,
            Boleta.estado.in_(['pendiente', 'parcial'])
        ).scalar()
        deuda_actual = float(deuda_actual_agregada) if deuda_actual_agregada else 0.0

        # Total cobrado en la sesión activa (procesado=False)
        pagos_sesion = db.session.query(
            func.sum(PagoBoleta.aplicado_boleta + PagoBoleta.aplicado_cc)
        ).filter(
            PagoBoleta.cliente_id == cliente.id,
            PagoBoleta.procesado == False
        ).scalar()
        cobrado_hoy = float(pagos_sesion) if pagos_sesion else 0.0

        # Monto de la boleta de hoy (0 si no hay boleta de hoy)
        monto_hoy = float(boleta_hoy.monto_boleta) if boleta_hoy else 0.0

        # Total a cobrar = lo que debe AHORA + lo que ya pagó en la sesión
        total_a_cobrar = deuda_actual + cobrado_hoy

        # Cuenta Corriente = todo lo que se debe que NO es la boleta de hoy
        saldo_cc = total_a_cobrar - monto_hoy
        if saldo_cc < 0:
            saldo_cc = 0.0

        # Último cobro registrado por el repartidor
        ultimo_cobro = (
            PagoBoleta.query
            .filter_by(cliente_id=cliente.id)
            .order_by(PagoBoleta.fecha_cobro.desc())
            .first()
        )
        ultimo_cobro_fecha = None
        if ultimo_cobro and ultimo_cobro.fecha_cobro:
            # Convertir de UTC a GMT-3 (Argentina)
            ultimo_cobro_fecha = ultimo_cobro.fecha_cobro - timedelta(hours=3)

        datos_clientes.append({
            'cliente': cliente,
            'boleta_hoy': boleta_hoy,
            'monto_hoy': monto_hoy,
            'saldo_cc': saldo_cc,
            'total_a_cobrar': total_a_cobrar,
            'cobrado_hoy': cobrado_hoy,
            'debe': deuda_actual,
            'ultimo_cobro': ultimo_cobro,
            'ultimo_cobro_fecha': ultimo_cobro_fecha,
        })

    # Agrupar por ruta, ordenadas alfabéticamente
    from collections import defaultdict
    datos_por_ruta = defaultdict(list)
    for d in datos_clientes:
        datos_por_ruta[d['cliente'].ruta].append(d)
    datos_por_ruta = dict(sorted(datos_por_ruta.items()))

    # Calcular resumen por ruta
    resumen_rutas = {}
    for ruta, datos in datos_por_ruta.items():
        resumen_rutas[ruta] = {
            'total_clientes': len(datos),
            'con_boleta': sum(1 for d in datos if d['boleta_hoy']),
            'sin_boleta': sum(1 for d in datos if not d['boleta_hoy']),
            'total_a_cobrar': sum(d['total_a_cobrar'] for d in datos),
            'total_debe': sum(d['debe'] for d in datos),
            'con_cc': sum(1 for d in datos if d['saldo_cc'] > 0),
        }

    # Lista plana de nombres para autocompletado
    nombres_clientes = [d['cliente'].nombre for d in datos_clientes]

    # Totales globales de cobro de la sesión activa (procesado=False)
    totales_cobro = db.session.query(
        func.sum(PagoBoleta.efectivo).label('total_efectivo'),
        func.sum(PagoBoleta.transferencia).label('total_transferencia'),
        func.sum(PagoBoleta.cheque).label('total_cheque')
    ).filter(
        PagoBoleta.procesado == False
    ).first()

    total_efectivo = float(totales_cobro.total_efectivo) if totales_cobro and totales_cobro.total_efectivo else 0.0
    total_transferencia = float(totales_cobro.total_transferencia) if totales_cobro and totales_cobro.total_transferencia else 0.0
    total_cheque = float(totales_cobro.total_cheque) if totales_cobro and totales_cobro.total_cheque else 0.0

    return render_template(
        'ventas/boletas.html',
        title='Boletas y Cobros',
        datos_por_ruta=datos_por_ruta,
        resumen_rutas=resumen_rutas,
        nombres_clientes=nombres_clientes,
        total_clientes=len(datos_clientes),
        total_efectivo=total_efectivo,
        total_transferencia=total_transferencia,
        total_cheque=total_cheque,
        hoy=hoy
    )


@ventas_bp.route('/cliente/<int:cliente_id>/boleta', methods=['GET', 'POST'])
@vendedor_requerido
def gestionar_boleta(cliente_id):
    """
    Ver y gestionar la boleta del día de un cliente específico.
    Permite crear una boleta nueva o editar la del día si ya existe.
    También muestra el historial completo de cobros del repartidor.
    Solo accesible por el usuario Vendedor.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    hoy = date.today()

    # Boleta activa de hoy
    boleta_hoy = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega == hoy,
            Boleta.estado.in_(['pendiente', 'parcial'])
        )
        .order_by(Boleta.fecha_creacion.desc())
        .first()
    )

    # Cuenta corriente (boletas anteriores pendientes)
    boletas_cc = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega < hoy,
            Boleta.estado.in_(['pendiente', 'parcial'])
        )
        .order_by(Boleta.fecha_entrega.asc())
        .all()
    )
    saldo_cc = sum(float(b.saldo_pendiente) for b in boletas_cc)

    # Historial de cobros del repartidor para este cliente
    historial_cobros = (
        PagoBoleta.query
        .filter_by(cliente_id=cliente_id)
        .order_by(PagoBoleta.fecha_cobro.desc())
        .limit(20)
        .all()
    )

    # Historial de boletas cobradas (para referencia)
    boletas_cobradas = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.estado == 'cobrada'
        )
        .order_by(Boleta.fecha_entrega.desc())
        .limit(10)
        .all()
    )

    return render_template(
        'ventas/boleta_cliente.html',
        title=f'Boleta — {cliente.nombre}',
        cliente=cliente,
        boleta_hoy=boleta_hoy,
        boletas_cc=boletas_cc,
        saldo_cc=saldo_cc,
        historial_cobros=historial_cobros,
        boletas_cobradas=boletas_cobradas,
        hoy=hoy
    )


@ventas_bp.route('/cliente/<int:cliente_id>/boleta/guardar', methods=['POST'])
@vendedor_requerido
def guardar_boleta(cliente_id):
    """
    Crear o actualizar la boleta del día para un cliente.
    Si ya existe una boleta pendiente/parcial del día, la actualiza.
    Si no existe, crea una nueva.
    Solo accesible por el usuario Vendedor.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    hoy = date.today()

    monto_str = request.form.get('monto_boleta', '0').strip().replace(',', '.')
    descripcion = request.form.get('descripcion', '').strip() or None

    try:
        monto = float(monto_str)
        if monto < 0:
            raise ValueError('El monto no puede ser negativo.')
    except (ValueError, TypeError):
        flash('El monto ingresado no es válido.', 'danger')
        return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))

    # Buscar boleta existente del día
    boleta = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega == hoy,
            Boleta.estado.in_(['pendiente', 'parcial'])
        )
        .order_by(Boleta.fecha_creacion.desc())
        .first()
    )

    if boleta:
        # Actualizar boleta existente
        boleta.monto_boleta = monto
        boleta.saldo_pendiente = monto
        boleta.descripcion = descripcion
        boleta.fecha_actualizacion = datetime.utcnow()
        accion = 'actualizada'
    else:
        # Crear boleta nueva
        boleta = Boleta(
            cliente_id=cliente_id,
            fecha_entrega=hoy,
            monto_boleta=monto,
            saldo_pendiente=monto,
            descripcion=descripcion,
            estado='pendiente',
            creado_por_id=current_user.id
        )
        db.session.add(boleta)
        accion = 'creada'

    try:
        db.session.commit()
        flash(f'Boleta {accion} correctamente para {cliente.nombre}: ${monto:.2f}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar la boleta: {str(e)}', 'danger')

    return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))


@ventas_bp.route('/cliente/<int:cliente_id>/boleta/saldo_inicial', methods=['POST'])
@vendedor_requerido
def cargar_saldo_inicial(cliente_id):
    """
    Carga una boleta con fecha de ayer para que figure directamente 
    en la cuenta corriente del cliente como saldo inicial / deuda anterior.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    
    monto_str = request.form.get('monto_inicial', '0').strip().replace(',', '.')
    descripcion = request.form.get('descripcion', 'Saldo inicial / Deuda anterior').strip()
    if not descripcion:
        descripcion = 'Saldo inicial / Deuda anterior'
        
    try:
        monto = float(monto_str)
        if monto <= 0:
            raise ValueError('El monto debe ser mayor a cero.')
    except (ValueError, TypeError):
        flash('El monto ingresado no es válido.', 'danger')
        return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))
        
    # Creamos la boleta con fecha de ayer para que entre en Cuenta Corriente (fecha < hoy)
    ayer = date.today() - timedelta(days=1)
    
    boleta = Boleta(
        cliente_id=cliente_id,
        fecha_entrega=ayer,
        monto_boleta=monto,
        saldo_pendiente=monto,
        descripcion=descripcion,
        estado='pendiente',
        creado_por_id=current_user.id
    )
    db.session.add(boleta)
    
    try:
        db.session.commit()
        flash(f'Saldo inicial de ${monto:.2f} cargado correctamente a la cuenta corriente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cargar el saldo inicial: {str(e)}', 'danger')
        
    return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))



@ventas_bp.route('/boleta/<int:boleta_id>/anular', methods=['POST'])
@vendedor_requerido
def anular_boleta(boleta_id):
    """
    Anula (elimina) una boleta pendiente del día.
    Solo se puede anular si todavía no tiene pagos registrados.
    """
    boleta = Boleta.query.get_or_404(boleta_id)

    # Solo se puede anular si es del cliente correcto y no tiene pagos
    if boleta.pagos.count() > 0:
        flash('No se puede anular una boleta que ya tiene pagos registrados.', 'danger')
        return redirect(url_for('ventas.gestionar_boleta', cliente_id=boleta.cliente_id))

    cliente_id = boleta.cliente_id
    db.session.delete(boleta)
    try:
        db.session.commit()
        flash('Boleta anulada correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al anular: {str(e)}', 'danger')

    return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))


@ventas_bp.route('/cliente/<int:cliente_id>/resetear_dia', methods=['POST'])
@vendedor_requerido
def resetear_cliente_dia(cliente_id):
    """
    Cierra la sesión activa del cliente.
    1. Mueve la boleta de hoy a 'ayer' → deja de aparecer como 'Boleta hoy'.
       El saldo pendiente queda como Cuenta Corriente automáticamente.
    2. Marca todos sus pagos activos como procesado=True (archivados) →
       el resumen del repartidor se resetea a $0.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    hoy = date.today()
    ayer = hoy - timedelta(days=1)

    # 1. Mover boletas de hoy a ayer (pasan a ser Cuenta Corriente)
    Boleta.query.filter(
        Boleta.cliente_id == cliente_id,
        Boleta.fecha_entrega == hoy
    ).update({'fecha_entrega': ayer}, synchronize_session=False)

    # 2. Archivar todos los pagos activos del cliente
    PagoBoleta.query.filter(
        PagoBoleta.cliente_id == cliente_id,
        PagoBoleta.procesado == False
    ).update({'procesado': True}, synchronize_session=False)
    
    db.session.commit()

    # Archivar los gastos activos del repartidor correspondientes a este cliente.
    # Se archivan los gastos de cualquier ruta, ya que el repartidor puede haber
    # registrado gastos de distintas rutas durante el mismo viaje.
    # Solo se archivan si ya no quedan pagos sin procesar en todo el sistema
    # (para no interrumpir viajes en curso de otros clientes).
    pagos_pendientes = PagoBoleta.query.filter_by(procesado=False).count()
    if pagos_pendientes == 0:
        from app.models.gasto_repartidor import GastoRepartidor
        gastos_activos = GastoRepartidor.query.filter_by(procesado=False).all()
        for g in gastos_activos:
            g.procesado = True
        if gastos_activos:
            db.session.commit()

    flash(f'El día para {cliente.nombre} ha sido cerrado. Saldo pendiente pasado a Cuenta Corriente.', 'success')
    return redirect(url_for('ventas.boletas'))


@ventas_bp.route('/ruta/<ruta_nombre>/resetear_dia', methods=['POST'])
@vendedor_requerido
def resetear_ruta_dia(ruta_nombre):
    """
    Cierra la sesión activa para todos los clientes de una ruta.
    1. Mueve todas las boletas de hoy a 'ayer' → dejan de aparecer como 'Boleta hoy'.
       El saldo pendiente queda automáticamente en Cuenta Corriente.
    2. Marca todos los pagos activos como procesado=True →
       el resumen del repartidor se resetea a $0.
    """
    hoy = date.today()
    ayer = hoy - timedelta(days=1)

    # 1. Obtener todos los clientes activos de esta ruta
    clientes_ruta = Cliente.query.filter(
        Cliente.ruta == ruta_nombre,
        Cliente.activo == True
    ).all()

    if not clientes_ruta:
        flash(f'No se encontraron clientes activos en la ruta {ruta_nombre}.', 'warning')
        return redirect(url_for('ventas.boletas'))

    clientes_ids = [c.id for c in clientes_ruta]

    # 2. Mover boletas de hoy a ayer (pasan a ser Cuenta Corriente)
    boletas_movidas = Boleta.query.filter(
        Boleta.cliente_id.in_(clientes_ids),
        Boleta.fecha_entrega == hoy
    ).update({'fecha_entrega': ayer}, synchronize_session=False)

    # 3. Archivar todos los pagos activos de la ruta
    total_procesados = PagoBoleta.query.filter(
        PagoBoleta.cliente_id.in_(clientes_ids),
        PagoBoleta.procesado == False
    ).update({'procesado': True}, synchronize_session=False)

    db.session.commit()

    # Archivar gastos activos del repartidor que correspondan a esta ruta.
    # Si ventas cierra una ruta entera, los gastos de esa ruta se archivan.
    # Los gastos de otras rutas que aún estén en curso no se tocan.
    from app.models.gasto_repartidor import GastoRepartidor
    gastos_ruta = GastoRepartidor.query.filter_by(
        procesado=False,
        ruta=ruta_nombre
    ).all()
    for g in gastos_ruta:
        g.procesado = True
    if gastos_ruta:
        db.session.commit()

    # Adicionalmente, si ya no quedan pagos activos en todo el sistema,
    # archivar cualquier gasto restante de otras rutas
    pagos_pendientes = PagoBoleta.query.filter_by(procesado=False).count()
    if pagos_pendientes == 0:
        gastos_restantes = GastoRepartidor.query.filter_by(procesado=False).all()
        for g in gastos_restantes:
            g.procesado = True
        if gastos_restantes:
            db.session.commit()

    flash(
        f'Ruta {ruta_nombre} cerrada correctamente. '
        f'{boletas_movidas} boleta(s) pasaron a Cuenta Corriente. '
        f'{total_procesados} cobro(s) archivado(s).',
        'success'
    )
    return redirect(url_for('ventas.boletas'))

@ventas_bp.route('/historial_gastos')
@vendedor_requerido
def historial_gastos():
    """
    Muestra el historial de gastos archivados/procesados de todos los repartidores.
    Agrupados por fecha.
    """
    from collections import defaultdict
    from app.models.gasto_repartidor import GastoRepartidor
    
    gastos_procesados = GastoRepartidor.query.filter_by(
        procesado=True
    ).order_by(GastoRepartidor.fecha.desc(), GastoRepartidor.fecha_creacion.desc()).all()
    
    gastos_agrupados = defaultdict(list)
    for g in gastos_procesados:
        gastos_agrupados[g.fecha].append(g)
        
    return render_template(
        'ventas/historial_gastos.html',
        gastos_agrupados=gastos_agrupados,
        title='Historial de Gastos'
    )


@ventas_bp.route('/cliente/<int:cliente_id>/registrar-pago-ventas', methods=['POST'])
@vendedor_requerido
def registrar_pago_ventas(cliente_id):
    """
    Registra un cobro directamente desde el usuario Ventas.

    Lógica idéntica a la del repartidor pero:
      - Protegida por @vendedor_requerido.
      - cobrado_por_id = current_user.id (usuario ventas, no repartidor).
      - procesado = False (ciclo normal: se archiva al cerrar el día con resetear_cliente_dia).

    Estos pagos NO aparecen en el resumen ni en los cobros del Repartidor,
    ya que el repartidor filtra siempre por cobrado_por_id == su propio id.
    SÍ se reflejan en /ventas/boletas (columna Total cobrado).
    """
    from app.models.boleta import Boleta, PagoBoleta
    from decimal import Decimal, InvalidOperation

    cliente = Cliente.query.get_or_404(cliente_id)

    # ── Leer y validar campos del formulario ──
    def parse_decimal(field_name, default=Decimal('0')):
        raw = request.form.get(field_name, '').strip().replace(',', '.')
        if not raw:
            return default
        try:
            val = Decimal(raw)
            return val if val >= 0 else default
        except InvalidOperation:
            return default

    efectivo      = parse_decimal('efectivo')
    transferencia = parse_decimal('transferencia')
    cheque_monto  = parse_decimal('cheque')
    fecha_cheque_str = request.form.get('fecha_cobro_cheque', '').strip()
    notas = request.form.get('notas', '').strip() or None

    # Validar fecha de cheque si se cargó monto
    fecha_cobro_cheque = None
    if cheque_monto > 0:
        if not fecha_cheque_str:
            flash('Si cargás un cheque debés indicar la fecha de cobro.', 'danger')
            return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))
        try:
            fecha_cobro_cheque = datetime.strptime(fecha_cheque_str, '%Y-%m-%d').date()
        except ValueError:
            flash('La fecha de cobro del cheque no es válida.', 'danger')
            return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))

    total_recibido = efectivo + transferencia + cheque_monto

    if total_recibido <= 0:
        flash('El total recibido debe ser mayor a $0.', 'warning')
        return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))

    hoy = date.today()

    # ── Boleta actual y CC ──
    boleta_actual = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega == hoy,
            Boleta.estado.in_(['pendiente', 'parcial'])
        )
        .order_by(Boleta.fecha_creacion.desc())
        .first()
    )

    boletas_cc = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega < hoy,
            Boleta.estado.in_(['pendiente', 'parcial'])
        )
        .order_by(Boleta.fecha_entrega.asc())
        .all()
    )

    # ── Distribuir el pago ──
    remanente = total_recibido
    aplicado_boleta = Decimal('0')
    aplicado_cc     = Decimal('0')

    # 1. Aplicar a boleta actual
    if boleta_actual and remanente > 0:
        saldo = Decimal(str(boleta_actual.saldo_pendiente))
        a_aplicar = min(remanente, saldo)
        boleta_actual.saldo_pendiente = saldo - a_aplicar
        boleta_actual.estado = 'cobrada' if boleta_actual.saldo_pendiente == 0 else 'parcial'
        boleta_actual.fecha_actualizacion = datetime.utcnow()
        aplicado_boleta = a_aplicar
        remanente -= a_aplicar

    # 2. Aplicar remanente a cuenta corriente (más antigua primero)
    for b in boletas_cc:
        if remanente <= 0:
            break
        saldo = Decimal(str(b.saldo_pendiente))
        a_aplicar = min(remanente, saldo)
        b.saldo_pendiente = saldo - a_aplicar
        b.estado = 'cobrada' if b.saldo_pendiente == 0 else 'parcial'
        b.fecha_actualizacion = datetime.utcnow()
        aplicado_cc += a_aplicar
        remanente -= a_aplicar

    # 3. Lo que sobra es saldo a favor
    saldo_favor = remanente

    boleta_ref_id = boleta_actual.id if boleta_actual else (boletas_cc[0].id if boletas_cc else None)

    pago = PagoBoleta(
        boleta_id=boleta_ref_id,
        cliente_id=cliente_id,
        efectivo=efectivo,
        transferencia=transferencia,
        cheque=cheque_monto,
        fecha_cobro_cheque=fecha_cobro_cheque,
        total_recibido=total_recibido,
        aplicado_boleta=aplicado_boleta,
        aplicado_cc=aplicado_cc,
        saldo_favor=saldo_favor,
        cobrado_por_id=current_user.id,  # Marca explícitamente que lo cobró Ventas
        notas=notas,
        procesado=False  # Ciclo normal: se archiva al cerrar el día
    )
    db.session.add(pago)

    try:
        db.session.commit()
        flash(
            f'✅ Pago registrado por Ventas. '
            f'Total: ${float(total_recibido):,.2f}',
            'success'
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar el pago: {str(e)}', 'danger')

    return redirect(url_for('ventas.gestionar_boleta', cliente_id=cliente_id))


# ─────────────────────────────────────────────
#  REPORTE DE VENTAS POR PRODUCTO
# ─────────────────────────────────────────────

@ventas_bp.route('/reporte-producto', methods=['GET'])
@login_required
@vendedor_requerido
def reporte_producto():
    """
    Muestra un reporte de litros vendidos por producto en un rango de fechas.
    Solo considera pedidos con estado 'completado'.
    """
    # Parámetros del formulario
    producto_filtro = request.args.get('producto', '').strip()
    fecha_desde_str = request.args.get('fecha_desde', '')
    fecha_hasta_str = request.args.get('fecha_hasta', '')

    # Parsear fechas
    fecha_desde = None
    fecha_hasta = None
    try:
        if fecha_desde_str:
            fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
        if fecha_hasta_str:
            fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            )
    except ValueError:
        flash('Las fechas ingresadas no son válidas.', 'danger')

    # Construir query base: solo completados (activos y archivados)
    query = Pedido.query.filter(Pedido.estado == 'completado')

    if producto_filtro:
        query = query.filter(Pedido.producto_nombre.ilike(f'%{producto_filtro}%'))
    if fecha_desde:
        query = query.filter(Pedido.fecha_completado >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Pedido.fecha_completado <= fecha_hasta)

    pedidos = query.order_by(Pedido.fecha_completado.desc()).all()

    # Agrupar totales por nombre de producto
    totales_por_producto = {}
    for p in pedidos:
        nombre = p.producto_nombre.upper()
        if nombre not in totales_por_producto:
            totales_por_producto[nombre] = {
                'litros': 0.0,
                'cantidad_pedidos': 0,
                'unidad': p.unidad or 'litros'
            }
        totales_por_producto[nombre]['litros'] += float(p.cantidad or 0)
        totales_por_producto[nombre]['cantidad_pedidos'] += 1

    # Ordenar por mayor cantidad
    totales_ordenados = sorted(
        totales_por_producto.items(),
        key=lambda x: x[1]['litros'],
        reverse=True
    )

    total_general = sum(float(p.cantidad or 0) for p in pedidos)

    # Lista de productos disponibles para el autocomplete
    productos_disponibles = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()

    return render_template(
        'ventas/reporte_producto.html',
        pedidos=pedidos,
        totales_ordenados=totales_ordenados,
        total_general=total_general,
        producto_filtro=producto_filtro,
        fecha_desde_str=fecha_desde_str,
        fecha_hasta_str=fecha_hasta_str,
        productos_disponibles=productos_disponibles,
        hay_resultados=len(pedidos) > 0,
        se_busco=(bool(producto_filtro) or bool(fecha_desde_str) or bool(fecha_hasta_str))
    )
