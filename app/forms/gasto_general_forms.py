# -*- coding: utf-8 -*-
"""
Formularios para registro y edición de Gastos Generales y Pagos a Proveedores.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, TextAreaField, DateField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Length, Optional
from datetime import date


class GastoGeneralForm(FlaskForm):
    """Formulario para crear o editar un Gasto General / Pago a Proveedor."""

    fecha = DateField(
        'Fecha',
        default=date.today,
        validators=[DataRequired(message='La fecha es obligatoria')],
        render_kw={'class': 'form-control'}
    )

    categoria = SelectField(
        'Categoría',
        choices=[
            ('proveedor_materia_prima', 'Proveedor de Materia Prima'),
            ('proveedor_insumos', 'Proveedor de Insumos / Envases'),
            ('alquiler_servicios', 'Alquiler y Servicios (Luz, Agua, etc.)'),
            ('mantenimiento', 'Mantenimiento y Reparaciones'),
            ('impuestos', 'Impuestos y Tasas'),
            ('otros', 'Otros Gastos')
        ],
        validators=[DataRequired(message='Debes seleccionar una categoría')],
        render_kw={'class': 'form-select'}
    )

    concepto = StringField(
        'Concepto / Proveedor',
        validators=[
            DataRequired(message='Indica el proveedor o concepto del gasto'),
            Length(max=255, message='Máximo 255 caracteres')
        ],
        render_kw={'class': 'form-control', 'placeholder': 'Ej: Química Oeste - Cloro, Alquiler Galpón Central, etc.'}
    )

    monto = DecimalField(
        'Monto ($)',
        validators=[
            DataRequired(message='El monto es obligatorio'),
            NumberRange(min=0.01, message='El monto debe ser mayor a 0')
        ],
        places=2,
        render_kw={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}
    )

    medio_pago = SelectField(
        'Medio de Pago',
        choices=[
            ('efectivo', 'Efectivo'),
            ('transferencia', 'Transferencia'),
            ('cheque', 'Cheque')
        ],
        validators=[DataRequired(message='Selecciona el medio de pago')],
        render_kw={'class': 'form-select'}
    )

    comprobante_nro = StringField(
        'Nº Comprobante / Factura (Opcional)',
        validators=[Optional(), Length(max=100)],
        render_kw={'class': 'form-control', 'placeholder': 'Ej: FC-A-0001-00004523, Recibo X, etc.'}
    )

    notas = TextAreaField(
        'Notas / Observaciones (Opcional)',
        validators=[Optional()],
        render_kw={'class': 'form-control', 'rows': '2', 'placeholder': 'Detalles adicionales...'}
    )

    submit = SubmitField('Guardar Gasto', render_kw={'class': 'btn btn-primary'})
