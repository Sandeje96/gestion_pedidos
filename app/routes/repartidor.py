# -*- coding: utf-8 -*-
"""
Blueprint para el panel del Repartidor.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.cliente import Cliente
from app.models.boleta import Boleta, PagoBoleta
from app.models.gasto_repartidor import GastoRepartidor
from functools import wraps
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

# Crear el Blueprint
repartidor_bp = Blueprint('repartidor', __name__)


def repartidor_requerido(f):
    """
    Decorador para verificar que el usuario sea Repartidor.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_repartidor():
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@repartidor_bp.route('/dashboard')
@repartidor_requerido
def dashboard():
    """
    Panel principal del Repartidor.
    Muestra las rutas existentes con sus clientes activos.
    Excluye la ruta SUCURSALES (esa es interna).
    """
    clientes = (
        Cliente.query
        .filter(Cliente.activo == True, Cliente.ruta != 'SUCURSALES')
        .order_by(Cliente.ruta, Cliente.nombre)
        .all()
    )

    clientes_por_ruta = defaultdict(list)
    for cliente in clientes:
        clientes_por_ruta[cliente.ruta].append(cliente)

    clientes_por_ruta = dict(sorted(clientes_por_ruta.items()))

    total_rutas = len(clientes_por_ruta)
    total_clientes = len(clientes)

    return render_template(
        'repartidor/dashboard.html',
        title='Panel de Repartidor',
        clientes_por_ruta=clientes_por_ruta,
        total_rutas=total_rutas,
        total_clientes=total_clientes
    )


@repartidor_bp.route('/cliente/<int:cliente_id>')
@repartidor_requerido
def cobro_cliente(cliente_id):
    """
    Vista de cobro para un cliente específico.
    Muestra:
      - BOLETA ACTUAL: la boleta pendiente/parcial más reciente del día de hoy.
      - CUENTA CORRIENTE: boletas anteriores (no de hoy) con saldo pendiente.
    """
    cliente = Cliente.query.get_or_404(cliente_id)

    # ── VERIFICAR PAGOS HOY (sesión activa, procesado=False) ──
    from datetime import datetime
    OFFSET_ARG = timedelta(hours=3)
    ahora_utc = datetime.utcnow()
    ahora_arg = ahora_utc - OFFSET_ARG
    inicio_dia_arg = ahora_arg.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_hoy_utc = inicio_dia_arg + OFFSET_ARG
    hoy = ahora_arg.date()  # Fecha argentina local

    pagos_hoy = PagoBoleta.query.filter(
        PagoBoleta.cliente_id == cliente_id,
        PagoBoleta.cobrado_por_id == current_user.id,  # Solo cuenta cobros propios del repartidor
        PagoBoleta.fecha_cobro >= inicio_hoy_utc,
        PagoBoleta.procesado == False
    ).count()

    ya_cobro_hoy = (pagos_hoy > 0)

    # ── BOLETA ACTUAL ──
    boleta_actual = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega == hoy
        )
        .order_by(Boleta.fecha_creacion.desc())
        .first()
    )

    # ── CUENTA CORRIENTE ──
    if ya_cobro_hoy:
        # Si ya cobró hoy, toda la deuda (incluso la de hoy) pasa a ser Cuenta Corriente visualmente
        boletas_cc = (
            Boleta.query
            .filter(
                Boleta.cliente_id == cliente_id,
                Boleta.fecha_entrega <= hoy,
                Boleta.estado.in_(['pendiente', 'parcial'])
            )
            .order_by(Boleta.fecha_entrega.asc())
            .all()
        )
        monto_boleta_actual = 0.0
    else:
        # Comportamiento normal (no cobró hoy)
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
        if boleta_actual and boleta_actual.estado in ['pendiente', 'parcial']:
            monto_boleta_actual = float(boleta_actual.saldo_pendiente)
        else:
            monto_boleta_actual = 0.0

    # Totales
    saldo_cc = sum(float(b.saldo_pendiente) for b in boletas_cc)
    total_deuda = monto_boleta_actual + saldo_cc

    # Historial de pagos recientes (últimos 10 cobros a este cliente)
    historial_pagos = (
        PagoBoleta.query
        .filter_by(cliente_id=cliente_id)
        .order_by(PagoBoleta.fecha_cobro.desc())
        .limit(10)
        .all()
    )

    # Pago más reciente de la sesión activa (editable por el repartidor)
    pago_activo = (
        PagoBoleta.query
        .filter_by(
            cliente_id=cliente_id,
            cobrado_por_id=current_user.id,
            procesado=False
        )
        .order_by(PagoBoleta.fecha_cobro.desc())
        .first()
    )
    pago_activo_id = pago_activo.id if pago_activo else None

    return render_template(
        'repartidor/cobro_cliente.html',
        title=f'Cobro — {cliente.nombre}',
        cliente=cliente,
        boleta_actual=boleta_actual,
        boletas_cc=boletas_cc,
        monto_boleta_actual=monto_boleta_actual,
        saldo_cc=saldo_cc,
        total_deuda=total_deuda,
        historial_pagos=historial_pagos,
        ya_cobro_hoy=ya_cobro_hoy,
        hoy=hoy,
        pago_activo_id=pago_activo_id
    )


@repartidor_bp.route('/cliente/<int:cliente_id>/registrar-pago', methods=['POST'])
@repartidor_requerido
def registrar_pago(cliente_id):
    """
    Procesa el pago registrado por el Repartidor.

    Lógica de aplicación:
      1. Primero se aplica a la boleta del día (boleta_actual).
      2. El remanente se aplica a las boletas de cuenta corriente (de más antigua a más reciente).
      3. Si sobra dinero → se registra como saldo_favor.
    """
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

    efectivo = parse_decimal('efectivo')
    transferencia = parse_decimal('transferencia')
    cheque_monto = parse_decimal('cheque')
    fecha_cheque_str = request.form.get('fecha_cobro_cheque', '').strip()
    notas = request.form.get('notas', '').strip() or None

    # Validar fecha de cheque si se cargó monto
    fecha_cobro_cheque = None
    if cheque_monto > 0:
        if not fecha_cheque_str:
            flash('Si cargás un cheque debés indicar la fecha de cobro.', 'danger')
            return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))
        try:
            fecha_cobro_cheque = datetime.strptime(fecha_cheque_str, '%Y-%m-%d').date()
        except ValueError:
            flash('La fecha de cobro del cheque no es válida.', 'danger')
            return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))

    total_recibido = efectivo + transferencia + cheque_monto

    if total_recibido <= 0:
        flash('El total recibido debe ser mayor a $0.', 'warning')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))

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
    aplicado_cc = Decimal('0')

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

    # ── Guardar el registro de pago ──
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
        cobrado_por_id=current_user.id,
        notas=notas
    )
    db.session.add(pago)

    try:
        db.session.commit()
        flash(
            f'✅ Pago registrado correctamente. '
            f'Total recibido: ${float(total_recibido):,.2f}',
            'success'
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar el pago: {str(e)}', 'danger')

    return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))


@repartidor_bp.route('/cliente/<int:cliente_id>/todo-a-cuenta-corriente', methods=['POST'])
@repartidor_requerido
def todo_a_cuenta_corriente(cliente_id):
    """
    Registra que toda la deuda del cliente queda pendiente en cuenta corriente.
    Funciona en dos casos:
      1. Hay boleta del día → esa boleta queda como CC (se acumula a las anteriores).
      2. Solo hay deudas anteriores (CC puras) → se asienta la visita sin cobro.
    No se cobra nada: se asienta un PagoBoleta con total_recibido=0 como
    constancia de la visita.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    # Calcular fecha argentina local (UTC-3)
    OFFSET_ARG = timedelta(hours=3)
    ahora_utc = datetime.utcnow()
    ahora_arg = ahora_utc - OFFSET_ARG
    inicio_dia_arg = ahora_arg.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_hoy_utc = inicio_dia_arg + OFFSET_ARG
    hoy = ahora_arg.date()

    # Verificar que no se haya operado ya hoy en esta sesión activa (solo cobros propios del repartidor)
    pagos_hoy = PagoBoleta.query.filter(
        PagoBoleta.cliente_id == cliente_id,
        PagoBoleta.cobrado_por_id == current_user.id,  # Solo cuenta cobros propios del repartidor
        PagoBoleta.fecha_cobro >= inicio_hoy_utc,
        PagoBoleta.procesado == False
    ).count()

    if pagos_hoy > 0:
        flash('Ya se registró una operación para este cliente hoy.', 'warning')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))

    # Boleta del día (puede no existir)
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

    # Boletas de CC anteriores
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

    # Necesitamos al menos alguna deuda para registrar
    if not boleta_actual and not boletas_cc:
        flash('Este cliente no tiene deudas pendientes.', 'warning')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))

    # Referencia: usar boleta del día si existe, sino la más antigua de CC
    boleta_ref = boleta_actual if boleta_actual else boletas_cc[0]

    # Calcular monto total pendiente para el mensaje
    monto_hoy = float(boleta_actual.saldo_pendiente) if boleta_actual else 0.0
    monto_cc = sum(float(b.saldo_pendiente) for b in boletas_cc)
    total_pendiente = monto_hoy + monto_cc

    # Registrar constancia de visita con pago $0 → "Todo a cuenta corriente"
    pago = PagoBoleta(
        boleta_id=boleta_ref.id,
        cliente_id=cliente_id,
        efectivo=Decimal('0'),
        transferencia=Decimal('0'),
        cheque=Decimal('0'),
        fecha_cobro_cheque=None,
        total_recibido=Decimal('0'),
        aplicado_boleta=Decimal('0'),
        aplicado_cc=Decimal('0'),
        saldo_favor=Decimal('0'),
        cobrado_por_id=current_user.id,
        notas='Todo a cuenta corriente'
    )
    db.session.add(pago)

    try:
        db.session.commit()
        flash(
            f'✅ Deuda de {cliente.nombre} dejada en cuenta corriente. '
            f'Total pendiente: ${total_pendiente:,.2f}',
            'success'
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Error al registrar: {str(e)}', 'danger')

    return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))


@repartidor_bp.route('/resumen')
@repartidor_requerido
def resumen():
    """
    Resumen del viaje activo del repartidor:
    - Totales generales: efectivo, transferencia, cheque, gastos, neto.
    - Detalle por ruta: efectivo, transferencia, cheque, subtotal.
    Incluye TODOS los cobros realizados por el repartidor en la sesión activa,
    sin importar la fecha. Los valores solo se reinician cuando el usuario
    Ventas cierra la ruta (que es cuando resetea las fechas en la base de datos).
    Los cobros 'todo a cuenta corriente' (total_recibido=0) no suman dinero
    pero se contabilizan como visitas.
    """
    # Fecha argentina para mostrar en el template
    OFFSET_ARG = timedelta(hours=3)
    hoy = (datetime.utcnow() - OFFSET_ARG).date()

    # Todos los cobros de la sesión activa (procesado=False)
    pagos_hoy = (
        PagoBoleta.query
        .filter(
            PagoBoleta.cobrado_por_id == current_user.id,
            PagoBoleta.procesado == False
        )
        .all()
    )

    # Totales generales
    total_efectivo     = sum(float(p.efectivo)      for p in pagos_hoy)
    total_transferencia = sum(float(p.transferencia) for p in pagos_hoy)
    total_cheque       = sum(float(p.cheque)         for p in pagos_hoy)
    total_cobrado      = total_efectivo + total_transferencia + total_cheque

    # Gastos de la sesión activa (procesado=False)
    gastos_hoy = GastoRepartidor.query.filter(
        GastoRepartidor.repartidor_id == current_user.id,
        GastoRepartidor.procesado == False
    ).order_by(GastoRepartidor.fecha_creacion.asc()).all()
    total_gastos = sum(float(g.monto) for g in gastos_hoy)

    neto_efectivo = total_efectivo - total_gastos

    # Agrupado por ruta del cliente
    rutas_dict = defaultdict(lambda: {
        'efectivo': 0.0, 'transferencia': 0.0, 'cheque': 0.0,
        'subtotal': 0.0, 'visitas': 0, 'gastos': 0.0, 'neto_efectivo': 0.0
    })
    
    for p in pagos_hoy:
        ruta = p.cliente.ruta if p.cliente and p.cliente.ruta else 'Sin ruta'
        rutas_dict[ruta]['efectivo']      += float(p.efectivo)
        rutas_dict[ruta]['transferencia'] += float(p.transferencia)
        rutas_dict[ruta]['cheque']        += float(p.cheque)
        rutas_dict[ruta]['subtotal']      += float(p.total_recibido)
        rutas_dict[ruta]['visitas']       += 1
        
    for g in gastos_hoy:
        ruta = g.ruta if g.ruta else 'Sin ruta'
        rutas_dict[ruta]['gastos'] += float(g.monto)
        
    for r in rutas_dict.values():
        r['neto_efectivo'] = r['efectivo'] - r['gastos']

    resumen_rutas = [
        {'ruta': ruta, **datos}
        for ruta, datos in sorted(rutas_dict.items())
    ]

    # Agrupado por cliente (para la pestaña "Por cliente")
    clientes_dict = defaultdict(lambda: {
        'nombre': '', 'ruta': '', 'efectivo': 0.0,
        'transferencia': 0.0, 'cheque': 0.0, 'total': 0.0, 'es_cc': False
    })
    for p in pagos_hoy:
        cid = p.cliente_id
        ruta = p.cliente.ruta if p.cliente and p.cliente.ruta else 'Sin ruta'
        clientes_dict[cid]['nombre'] = p.cliente.nombre if p.cliente else f'Cliente #{cid}'
        clientes_dict[cid]['ruta']   = ruta
        clientes_dict[cid]['efectivo']      += float(p.efectivo)
        clientes_dict[cid]['transferencia'] += float(p.transferencia)
        clientes_dict[cid]['cheque']        += float(p.cheque)
        clientes_dict[cid]['total']         += float(p.total_recibido)
        if p.notas == 'Todo a cuenta corriente' and float(p.total_recibido) == 0:
            clientes_dict[cid]['es_cc'] = True

    resumen_por_cliente = sorted(
        clientes_dict.values(),
        key=lambda x: (x['ruta'], x['nombre'])
    )

    return render_template(
        'repartidor/resumen.html',
        title='Resumen del día',
        hoy=hoy,
        total_efectivo=total_efectivo,
        total_transferencia=total_transferencia,
        total_cheque=total_cheque,
        total_cobrado=total_cobrado,
        total_gastos=total_gastos,
        neto_efectivo=neto_efectivo,
        gastos_hoy=gastos_hoy,
        resumen_rutas=resumen_rutas,
        resumen_por_cliente=resumen_por_cliente,
        total_visitas=len(pagos_hoy)
    )


@repartidor_bp.route('/gastos', methods=['GET', 'POST'])
@repartidor_requerido
def gastos():
    """
    Panel para cargar y visualizar los gastos diarios del repartidor.
    """
    hoy = date.today()
    
    if request.method == 'POST':
        tipo = request.form.get('tipo', '').strip()
        monto_str = request.form.get('monto', '0').strip().replace(',', '.')
        notas = request.form.get('notas', '').strip()
        ruta_seleccionada = request.form.get('ruta', '').strip()
        
        if not ruta_seleccionada:
            flash('Debe seleccionar a qué ruta corresponde el gasto.', 'warning')
            return redirect(url_for('repartidor.gastos'))
        
        try:
            monto = Decimal(monto_str)
            if monto <= 0:
                raise ValueError
        except (ValueError, InvalidOperation):
            flash('El monto debe ser un número válido mayor a 0.', 'danger')
            return redirect(url_for('repartidor.gastos'))
            
        if tipo == 'Otros' and not notas:
            flash('Debes especificar en las notas de qué trata este gasto.', 'warning')
            return redirect(url_for('repartidor.gastos'))
            
        nuevo_gasto = GastoRepartidor(
            repartidor_id=current_user.id,
            fecha=hoy,
            tipo=tipo,
            monto=monto,
            ruta=ruta_seleccionada,
            notas=notas if notas else None
        )
        
        db.session.add(nuevo_gasto)
        db.session.commit()
        flash('Gasto registrado correctamente.', 'success')
        return redirect(url_for('repartidor.gastos'))
        
    # Obtener gastos activos (no procesados)
    gastos_hoy = GastoRepartidor.query.filter_by(
        repartidor_id=current_user.id,
        procesado=False
    ).order_by(GastoRepartidor.fecha_creacion.desc()).all()
    
    total_gastos = sum(g.monto for g in gastos_hoy)
    
    rutas_db = db.session.query(Cliente.ruta).filter(
        Cliente.activo == True,
        Cliente.ruta != 'SUCURSALES',
        Cliente.ruta != None,
        Cliente.ruta != ''
    ).distinct().order_by(Cliente.ruta).all()
    rutas_disponibles = [r[0] for r in rutas_db]

    return render_template(
        'repartidor/gastos.html',
        title='Mis Gastos',
        gastos_hoy=gastos_hoy,
        total_gastos=total_gastos,
        rutas=rutas_disponibles,
        hoy=hoy
    )


@repartidor_bp.route('/gastos/<int:gasto_id>/eliminar', methods=['POST'])
@repartidor_requerido
def eliminar_gasto(gasto_id):
    """
    Elimina un gasto registrado por error.
    """
    gasto = GastoRepartidor.query.get_or_404(gasto_id)
    
    if gasto.repartidor_id != current_user.id:
        flash('No tienes permiso para eliminar este gasto.', 'danger')
        return redirect(url_for('repartidor.gastos'))
        
    db.session.delete(gasto)
    db.session.commit()
    flash('Gasto eliminado correctamente.', 'success')
    return redirect(url_for('repartidor.gastos'))


@repartidor_bp.route('/gastos/limpiar', methods=['POST'])
@repartidor_requerido
def limpiar_gastos():
    """
    Limpia los gastos activos del repartidor actual, marcándolos como procesados.
    """
    gastos_activos = GastoRepartidor.query.filter_by(
        repartidor_id=current_user.id,
        procesado=False
    ).all()
    
    if not gastos_activos:
        flash('No hay gastos para limpiar en este viaje.', 'warning')
        return redirect(url_for('repartidor.gastos'))
        
    for gasto in gastos_activos:
        gasto.procesado = True
        
    db.session.commit()
    flash('Viaje limpiado con éxito. Los gastos volvieron a cero.', 'success')
    return redirect(url_for('repartidor.gastos'))

@repartidor_bp.route('/cliente/<int:cliente_id>/editar-pago/<int:pago_id>', methods=['GET'])
@repartidor_requerido
def editar_pago_form(cliente_id, pago_id):
    """
    Muestra el formulario de edición de un pago de la sesión activa.
    Solo permite editar pagos propios y no procesados.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    pago = PagoBoleta.query.get_or_404(pago_id)

    # Validaciones de seguridad
    if pago.cobrado_por_id != current_user.id:
        flash('No tenés permiso para editar este pago.', 'danger')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))
    if pago.procesado:
        flash('Este pago ya fue procesado y no se puede editar.', 'warning')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))
    if pago.cliente_id != cliente_id:
        flash('El pago no corresponde a este cliente.', 'danger')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))

    return render_template(
        'repartidor/editar_pago.html',
        title=f'Editar cobro — {cliente.nombre}',
        cliente=cliente,
        pago=pago
    )


@repartidor_bp.route('/cliente/<int:cliente_id>/editar-pago/<int:pago_id>', methods=['POST'])
@repartidor_requerido
def editar_pago(cliente_id, pago_id):
    """
    Procesa la edición de un pago activo:
      1. Revierte los saldos de las boletas afectadas por el pago original.
      2. Elimina el pago original.
      3. Aplica los nuevos montos con la misma lógica que registrar_pago.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    pago = PagoBoleta.query.get_or_404(pago_id)

    # Validaciones de seguridad
    if pago.cobrado_por_id != current_user.id:
        flash('No tenés permiso para editar este pago.', 'danger')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))
    if pago.procesado:
        flash('Este pago ya fue procesado y no se puede editar.', 'warning')
        return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))

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

    fecha_cobro_cheque = None
    if cheque_monto > 0:
        if not fecha_cheque_str:
            flash('Si cargás un cheque debés indicar la fecha de cobro.', 'danger')
            return redirect(url_for('repartidor.editar_pago_form', cliente_id=cliente_id, pago_id=pago_id))
        try:
            fecha_cobro_cheque = datetime.strptime(fecha_cheque_str, '%Y-%m-%d').date()
        except ValueError:
            flash('La fecha de cobro del cheque no es válida.', 'danger')
            return redirect(url_for('repartidor.editar_pago_form', cliente_id=cliente_id, pago_id=pago_id))

    total_recibido = efectivo + transferencia + cheque_monto

    if total_recibido <= 0:
        flash('El total recibido debe ser mayor a $0.', 'warning')
        return redirect(url_for('repartidor.editar_pago_form', cliente_id=cliente_id, pago_id=pago_id))

    # ── PASO 1: Revertir saldos de boletas afectadas por el pago original ──
    # El pago original aplicó aplicado_boleta a una boleta y aplicado_cc a boletas de CC.
    # Recuperamos esas boletas y devolvemos sus saldos.
    hoy = (datetime.utcnow() - timedelta(hours=3)).date()

    boleta_actual = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega == hoy
        )
        .order_by(Boleta.fecha_creacion.desc())
        .first()
    )

    boletas_cc = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega < hoy,
            Boleta.estado.in_(['pendiente', 'parcial', 'cobrada'])
        )
        .order_by(Boleta.fecha_entrega.asc())
        .all()
    )

    # Revertir aplicado_boleta sobre la boleta del día
    remanente_revertir = Decimal(str(pago.aplicado_boleta))
    if boleta_actual and remanente_revertir > 0:
        boleta_actual.saldo_pendiente = Decimal(str(boleta_actual.saldo_pendiente)) + remanente_revertir
        boleta_actual.estado = 'pendiente' if boleta_actual.saldo_pendiente >= boleta_actual.monto_boleta else 'parcial'
        boleta_actual.fecha_actualizacion = datetime.utcnow()

    # Revertir aplicado_cc sobre boletas de CC (de más antigua a más reciente)
    remanente_cc = Decimal(str(pago.aplicado_cc))
    for b in boletas_cc:
        if remanente_cc <= 0:
            break
        a_revertir = min(remanente_cc, Decimal(str(b.monto_boleta)) - Decimal(str(b.saldo_pendiente)))
        if a_revertir > 0:
            b.saldo_pendiente = Decimal(str(b.saldo_pendiente)) + a_revertir
            b.estado = 'pendiente' if b.saldo_pendiente >= b.monto_boleta else 'parcial'
            b.fecha_actualizacion = datetime.utcnow()
            remanente_cc -= a_revertir

    # ── PASO 2: Eliminar el pago original ──
    db.session.delete(pago)

    # ── PASO 3: Aplicar nuevos montos (misma lógica que registrar_pago) ──
    remanente = total_recibido
    aplicado_boleta = Decimal('0')
    aplicado_cc     = Decimal('0')

    # Refrescar estado de boletas tras la reversión
    db.session.flush()

    boleta_actual_fresh = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega == hoy,
            Boleta.estado.in_(['pendiente', 'parcial'])
        )
        .order_by(Boleta.fecha_creacion.desc())
        .first()
    )
    boletas_cc_fresh = (
        Boleta.query
        .filter(
            Boleta.cliente_id == cliente_id,
            Boleta.fecha_entrega < hoy,
            Boleta.estado.in_(['pendiente', 'parcial'])
        )
        .order_by(Boleta.fecha_entrega.asc())
        .all()
    )

    # Aplicar a boleta actual
    if boleta_actual_fresh and remanente > 0:
        saldo = Decimal(str(boleta_actual_fresh.saldo_pendiente))
        a_aplicar = min(remanente, saldo)
        boleta_actual_fresh.saldo_pendiente = saldo - a_aplicar
        boleta_actual_fresh.estado = 'cobrada' if boleta_actual_fresh.saldo_pendiente == 0 else 'parcial'
        boleta_actual_fresh.fecha_actualizacion = datetime.utcnow()
        aplicado_boleta = a_aplicar
        remanente -= a_aplicar

    # Aplicar remanente a cuenta corriente
    for b in boletas_cc_fresh:
        if remanente <= 0:
            break
        saldo = Decimal(str(b.saldo_pendiente))
        a_aplicar = min(remanente, saldo)
        b.saldo_pendiente = saldo - a_aplicar
        b.estado = 'cobrada' if b.saldo_pendiente == 0 else 'parcial'
        b.fecha_actualizacion = datetime.utcnow()
        aplicado_cc += a_aplicar
        remanente -= a_aplicar

    saldo_favor = remanente

    boleta_ref_id = (
        boleta_actual_fresh.id if boleta_actual_fresh
        else (boletas_cc_fresh[0].id if boletas_cc_fresh else None)
    )

    nuevo_pago = PagoBoleta(
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
        cobrado_por_id=current_user.id,
        notas=notas
    )
    db.session.add(nuevo_pago)

    try:
        db.session.commit()
        flash(
            f'✅ Cobro actualizado correctamente. '
            f'Total recibido: ${float(total_recibido):,.2f}',
            'success'
        )
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar el pago: {str(e)}', 'danger')

    return redirect(url_for('repartidor.cobro_cliente', cliente_id=cliente_id))


@repartidor_bp.route('/historial_gastos')
@repartidor_requerido
def historial_gastos():
    """
    Muestra el historial de gastos del repartidor actual, agrupados por viaje
    (ruta + semana ISO).

    Se incluyen dos tipos de gastos:
      1. procesado=True  → archivados correctamente por Ventas al cerrar la ruta.
      2. procesado=False de semanas ANTERIORES → gastos "huérfanos" que no se
         archivaron porque el sistema requería que todos los pagos del sistema
         estuvieran cerrados. Se muestran igual para que no se pierdan.

    Los gastos procesado=False de la semana ACTUAL no se incluyen aquí;
    esos se ven en la pantalla de Gastos activos.
    """
    from collections import defaultdict

    # Inicio del lunes de la semana actual (para separar semana actual de anteriores)
    hoy = date.today()
    lunes_actual = hoy - timedelta(days=hoy.weekday())

    # Traer gastos archivados + gastos de semanas anteriores no archivados
    gastos_historial = GastoRepartidor.query.filter(
        GastoRepartidor.repartidor_id == current_user.id,
        db.or_(
            GastoRepartidor.procesado == True,
            GastoRepartidor.fecha < lunes_actual   # semanas pasadas aunque no estén archivados
        )
    ).order_by(GastoRepartidor.fecha.asc(), GastoRepartidor.fecha_creacion.asc()).all()

    # Agrupar por (ruta, año ISO, semana ISO)
    viajes_dict = defaultdict(lambda: {
        'ruta': '',
        'anio': 0,
        'semana': 0,
        'gastos': [],
        'fecha_inicio': None,
        'fecha_fin': None,
        'total': 0.0,
        'breakdown': defaultdict(float),
        'tiene_sin_archivar': False,  # True si algún gasto del viaje no fue archivado formalmente
    })

    for g in gastos_historial:
        iso = g.fecha.isocalendar()
        anio, semana = iso[0], iso[1]
        ruta = g.ruta or 'Sin ruta'
        key = (ruta, anio, semana)

        v = viajes_dict[key]
        v['ruta']   = ruta
        v['anio']   = anio
        v['semana'] = semana
        v['gastos'].append(g)
        v['total']  += float(g.monto)
        v['breakdown'][g.tipo] += float(g.monto)
        if not g.procesado:
            v['tiene_sin_archivar'] = True

        if v['fecha_inicio'] is None or g.fecha < v['fecha_inicio']:
            v['fecha_inicio'] = g.fecha
        if v['fecha_fin'] is None or g.fecha > v['fecha_fin']:
            v['fecha_fin'] = g.fecha

    # Ordenar: viaje más reciente primero
    viajes = sorted(
        viajes_dict.values(),
        key=lambda v: (v['fecha_fin'], v['ruta']),
        reverse=True
    )

    rutas_distintas = len({v['ruta'] for v in viajes})

    return render_template(
        'repartidor/historial_gastos.html',
        viajes=viajes,
        rutas_distintas=rutas_distintas,
        title='Historial de Gastos'
    )
