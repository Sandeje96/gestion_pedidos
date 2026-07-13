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
        hoy=hoy
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

    # Verificar que no se haya operado ya hoy en esta sesión activa
    pagos_hoy = PagoBoleta.query.filter(
        PagoBoleta.cliente_id == cliente_id,
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
        'subtotal': 0.0, 'visitas': 0
    })
    for p in pagos_hoy:
        ruta = p.cliente.ruta if p.cliente and p.cliente.ruta else 'Sin ruta'
        rutas_dict[ruta]['efectivo']      += float(p.efectivo)
        rutas_dict[ruta]['transferencia'] += float(p.transferencia)
        rutas_dict[ruta]['cheque']        += float(p.cheque)
        rutas_dict[ruta]['subtotal']      += float(p.total_recibido)
        rutas_dict[ruta]['visitas']       += 1

    resumen_rutas = [
        {'ruta': ruta, **datos}
        for ruta, datos in sorted(rutas_dict.items())
    ]

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
    
    return render_template(
        'repartidor/gastos.html',
        title='Mis Gastos',
        gastos_hoy=gastos_hoy,
        total_gastos=total_gastos,
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
