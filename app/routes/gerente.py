# -*- coding: utf-8 -*-
"""
Blueprint para el panel de Gerencia.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.producto import Producto
from app.models.materia_prima import MateriaPrima
from app.models.formulacion_producto import FormulacionProducto
from app.models.movimiento_materia_prima import MovimientoMateriaPrima
from functools import wraps
from decimal import Decimal, InvalidOperation

# Crear el Blueprint
gerente_bp = Blueprint('gerente', __name__)


def gerente_requerido(f):
    """
    Decorador para verificar que el usuario sea Gerente.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.es_gerente():
            flash('No tienes permisos para acceder a esta sección', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

@gerente_bp.route('/dashboard')
@gerente_requerido
def dashboard():
    """
    Panel principal de Gerencia.
    Muestra el catálogo completo de productos (mismo que gestiona administración),
    desde donde el gerente identifica cuáles son fabricados internamente y les asigna fórmula.
    """
    # Catálogo completo de productos disponibles (misma fuente que administración)
    productos_lista = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()

    # Alertas de stock bajo en materias primas
    mp_todas = MateriaPrima.query.filter_by(activo=True).all()
    alertas_stock = [mp for mp in mp_todas if mp.stock_bajo]

    return render_template(
        'gerente/dashboard.html',
        title='Panel de Gerencia',
        productos=productos_lista,
        alertas_stock=alertas_stock
    )


# ─────────────────────────────────────────────
# MATERIAS PRIMAS
# ─────────────────────────────────────────────

@gerente_bp.route('/materias-primas')
@gerente_requerido
def materias_primas():
    """Lista de todas las materias primas activas."""
    mps = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
    return render_template('gerente/materias_primas.html', title='Materias Primas', mps=mps)


@gerente_bp.route('/materias-primas/nueva', methods=['GET', 'POST'])
@gerente_requerido
def nueva_materia_prima():
    """Formulario para registrar una nueva materia prima."""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        unidad = request.form.get('unidad', '').strip()
        stock_minimo_str = request.form.get('stock_minimo', '0').strip()

        # Validaciones
        if not nombre or not unidad:
            flash('El nombre y la unidad son obligatorios.', 'danger')
            return render_template('gerente/nueva_materia_prima.html', title='Nueva Materia Prima')

        if MateriaPrima.query.filter_by(nombre=nombre).first():
            flash(f'Ya existe una materia prima con el nombre "{nombre}".', 'danger')
            return render_template('gerente/nueva_materia_prima.html', title='Nueva Materia Prima')

        try:
            stock_minimo = Decimal(stock_minimo_str) if stock_minimo_str else Decimal('0')
        except InvalidOperation:
            flash('El stock mínimo debe ser un número válido.', 'danger')
            return render_template('gerente/nueva_materia_prima.html', title='Nueva Materia Prima')

        mp = MateriaPrima(
            nombre=nombre,
            descripcion=descripcion or None,
            unidad=unidad,
            stock_minimo=stock_minimo,
            stock_actual=Decimal('0'),
            activo=True
        )
        db.session.add(mp)
        db.session.commit()
        flash(f'Materia prima "{nombre}" registrada correctamente.', 'success')
        return redirect(url_for('gerente.materias_primas'))

    return render_template('gerente/nueva_materia_prima.html', title='Nueva Materia Prima')


@gerente_bp.route('/materias-primas/<int:mp_id>/ingreso', methods=['GET', 'POST'])
@gerente_requerido
def ingreso_stock(mp_id):
    """Registrar un ingreso de stock para una materia prima (compra)."""
    mp = MateriaPrima.query.get_or_404(mp_id)

    if request.method == 'POST':
        cantidad_str = request.form.get('cantidad', '').strip()
        descripcion = request.form.get('descripcion', '').strip()

        try:
            cantidad = Decimal(cantidad_str)
            if cantidad <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            flash('La cantidad debe ser un número mayor a cero.', 'danger')
            return render_template('gerente/ingreso_stock.html', title='Registrar Ingreso', mp=mp)

        # Sumar al stock
        mp.agregar_stock(cantidad)

        # Registrar movimiento
        movimiento = MovimientoMateriaPrima(
            materia_prima_id=mp.id,
            tipo='ingreso',
            cantidad=cantidad,
            descripcion=descripcion or f'Ingreso de stock — {mp.nombre}',
            usuario_id=current_user.id
        )
        db.session.add(movimiento)
        db.session.commit()

        flash(f'Se agregaron {cantidad} {mp.unidad} de "{mp.nombre}". '
              f'Stock actual: {mp.stock_actual} {mp.unidad}.', 'success')
        return redirect(url_for('gerente.materias_primas'))

    return render_template('gerente/ingreso_stock.html', title='Registrar Ingreso', mp=mp)


@gerente_bp.route('/materias-primas/<int:mp_id>/movimientos')
@gerente_requerido
def movimientos_mp(mp_id):
    """Historial de movimientos de una materia prima."""
    mp = MateriaPrima.query.get_or_404(mp_id)
    movimientos = MovimientoMateriaPrima.query.filter_by(
        materia_prima_id=mp_id
    ).order_by(MovimientoMateriaPrima.fecha_creacion.desc()).limit(100).all()
    return render_template('gerente/movimientos_mp.html',
                           title=f'Movimientos — {mp.nombre}', mp=mp, movimientos=movimientos)


@gerente_bp.route('/materias-primas/<int:mp_id>/editar', methods=['GET', 'POST'])
@gerente_requerido
def editar_materia_prima(mp_id):
    """Editar nombre, descripción, unidad y stock mínimo de una materia prima.
    Al cambiar el nombre se actualiza automáticamente en todas las fórmulas
    que la usan, ya que se relacionan por ID."""
    mp = MateriaPrima.query.get_or_404(mp_id)

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        unidad = request.form.get('unidad', '').strip()
        stock_minimo_str = request.form.get('stock_minimo', '0').strip()

        if not nombre or not unidad:
            flash('El nombre y la unidad son obligatorios.', 'danger')
            return render_template('gerente/editar_materia_prima.html',
                                   title=f'Editar — {mp.nombre}', mp=mp)

        # Verificar que el nuevo nombre no lo use otra MP distinta
        duplicada = MateriaPrima.query.filter(
            MateriaPrima.nombre == nombre,
            MateriaPrima.id != mp_id
        ).first()
        if duplicada:
            flash(f'Ya existe otra materia prima con el nombre "{nombre}".', 'danger')
            return render_template('gerente/editar_materia_prima.html',
                                   title=f'Editar — {mp.nombre}', mp=mp)

        try:
            stock_minimo = Decimal(stock_minimo_str) if stock_minimo_str else Decimal('0')
        except InvalidOperation:
            flash('El stock mínimo debe ser un número válido.', 'danger')
            return render_template('gerente/editar_materia_prima.html',
                                   title=f'Editar — {mp.nombre}', mp=mp)

        nombre_anterior = mp.nombre
        mp.nombre = nombre
        mp.descripcion = descripcion or None
        mp.unidad = unidad
        mp.stock_minimo = stock_minimo
        db.session.commit()

        if nombre != nombre_anterior:
            flash(f'Materia prima renombrada de "{nombre_anterior}" a "{nombre}". '
                  f'Se actualizó en todas las fórmulas automáticamente.', 'success')
        else:
            flash(f'Materia prima "{nombre}" actualizada correctamente.', 'success')

        return redirect(url_for('gerente.materias_primas'))

    return render_template('gerente/editar_materia_prima.html',
                           title=f'Editar — {mp.nombre}', mp=mp)



# ─────────────────────────────────────────────
# FÓRMULAS DE PRODUCTOS
# ─────────────────────────────────────────────

@gerente_bp.route('/productos/formulas')
@gerente_requerido
def formulas():
    """Lista de productos con indicador de si tienen fórmula cargada."""
    productos = Producto.query.filter_by(disponible=True).order_by(Producto.nombre).all()
    return render_template('gerente/formulas.html', title='Fórmulas de Productos', productos=productos)


@gerente_bp.route('/productos/<int:producto_id>/formula', methods=['GET', 'POST'])
@gerente_requerido
def editar_formula(producto_id):
    """
    Editar la fórmula de un producto.
    El gerente ingresa:
        - Lote base: para cuántos litros/unidades es la fórmula
        - Cantidad de cada materia prima usada en ese lote
    El sistema calcula y guarda cantidad_por_unidad = cantidad / lote_base.
    """
    producto = Producto.query.get_or_404(producto_id)
    mps_disponibles = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
    formulaciones_actuales = FormulacionProducto.query.filter_by(
        producto_id=producto_id
    ).order_by(FormulacionProducto.grupo_alternativa.nullslast(), FormulacionProducto.id).all()

    if request.method == 'POST':
        accion = request.form.get('accion')

        # ── Agregar ingrediente (normal o variante) ──
        if accion == 'agregar':
            mp_id_str = request.form.get('materia_prima_id', '').strip()
            lote_base_str = request.form.get('lote_base', '').strip()
            cantidad_lote_str = request.form.get('cantidad_lote', '').strip()
            # ID del ingrediente al que queremos agregar como variante (opcional)
            variante_de_id_str = request.form.get('variante_de_id', '').strip()

            try:
                mp_id = int(mp_id_str)
                lote_base = Decimal(lote_base_str)
                cantidad_lote = Decimal(cantidad_lote_str)
                if lote_base <= 0 or cantidad_lote <= 0:
                    raise ValueError
            except (ValueError, InvalidOperation):
                flash('Verificá que el lote base, la materia prima y la cantidad sean válidos.', 'danger')
                return redirect(url_for('gerente.editar_formula', producto_id=producto_id))

            mp = MateriaPrima.query.get(mp_id)
            if not mp:
                flash('Materia prima no encontrada.', 'danger')
                return redirect(url_for('gerente.editar_formula', producto_id=producto_id))

            cantidad_por_unidad = cantidad_lote / lote_base

            # Verificar si ya existe esa MP en la fórmula
            existente = FormulacionProducto.query.filter_by(
                producto_id=producto_id, materia_prima_id=mp_id
            ).first()

            if existente:
                existente.cantidad_por_unidad = cantidad_por_unidad
                flash(f'Se actualizó "{mp.nombre}" en la fórmula.', 'success')
                db.session.commit()
                return redirect(url_for('gerente.editar_formula', producto_id=producto_id))

            # Determinar grupo_alternativa
            grupo = None
            if variante_de_id_str:
                try:
                    variante_de_id = int(variante_de_id_str)
                    origen = FormulacionProducto.query.get(variante_de_id)
                    if origen and origen.producto_id == producto_id:
                        if origen.grupo_alternativa:
                            # El origen ya tiene grupo → usar el mismo
                            grupo = origen.grupo_alternativa
                        else:
                            # El origen no tiene grupo → crear uno nuevo y asignarlo al origen también
                            max_grupo = db.session.query(
                                db.func.max(FormulacionProducto.grupo_alternativa)
                            ).filter_by(producto_id=producto_id).scalar() or 0
                            grupo = max_grupo + 1
                            origen.grupo_alternativa = grupo
                except (ValueError, TypeError):
                    pass

            nueva = FormulacionProducto(
                producto_id=producto_id,
                materia_prima_id=mp_id,
                cantidad_por_unidad=cantidad_por_unidad,
                grupo_alternativa=grupo
            )
            db.session.add(nueva)
            db.session.commit()

            if grupo:
                flash(f'"{mp.nombre}" agregada como variante del grupo {grupo}.', 'success')
            else:
                flash(f'"{mp.nombre}" agregada a la fórmula '
                      f'({cantidad_lote} {mp.unidad} / {lote_base} → '
                      f'{float(cantidad_por_unidad):.4f}/unidad).', 'success')

            return redirect(url_for('gerente.editar_formula', producto_id=producto_id))

        # ── Eliminar una línea de la fórmula ──
        elif accion == 'eliminar':
            formulacion_id = request.form.get('formulacion_id')
            formulacion = FormulacionProducto.query.get(formulacion_id)
            if formulacion and formulacion.producto_id == producto_id:
                nombre_mp = formulacion.materia_prima.nombre
                grupo_era = formulacion.grupo_alternativa

                db.session.delete(formulacion)
                db.session.flush()

                # Si al eliminar queda solo una MP en ese grupo, quitar el grupo (ya no hay alternativa)
                if grupo_era is not None:
                    restantes = FormulacionProducto.query.filter_by(
                        producto_id=producto_id, grupo_alternativa=grupo_era
                    ).count()
                    if restantes == 1:
                        unico = FormulacionProducto.query.filter_by(
                            producto_id=producto_id, grupo_alternativa=grupo_era
                        ).first()
                        if unico:
                            unico.grupo_alternativa = None

                db.session.commit()
                flash(f'Se eliminó "{nombre_mp}" de la fórmula.', 'info')
            return redirect(url_for('gerente.editar_formula', producto_id=producto_id))

    # Organizar formulaciones para el template: agrupar por grupo_alternativa
    grupos = {}    # grupo_num → [FormulacionProducto, ...]
    sin_grupo = [] # ingredientes sin variantes

    for f in formulaciones_actuales:
        if f.grupo_alternativa is not None:
            grupos.setdefault(f.grupo_alternativa, []).append(f)
        else:
            sin_grupo.append(f)

    return render_template(
        'gerente/editar_formula.html',
        title=f'Fórmula — {producto.nombre}',
        producto=producto,
        formulaciones=formulaciones_actuales,
        sin_grupo=sin_grupo,
        grupos=grupos,
        mps_disponibles=mps_disponibles
    )

