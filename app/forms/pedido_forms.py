# -*- coding: utf-8 -*-
"""
Formularios para gestión de pedidos.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, TextAreaField, SubmitField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Length, Optional
from app.models.cliente import Cliente
from app.models.usuario import Usuario
from app import db


class PedidoForm(FlaskForm):
    """
    Formulario para crear pedidos (versión simplificada para múltiples pedidos).
    """
    
    cliente_id = SelectField(
        'Cliente',
        coerce=int,
        validators=[
            DataRequired(message='Debes seleccionar un cliente')
        ],
        render_kw={
            'class': 'form-select'
        }
    )
    
    submit = SubmitField(
        'Guardar Pedido',
        render_kw={
            'class': 'btn btn-success'
        }
    )
    
    def __init__(self, *args, **kwargs):
        super(PedidoForm, self).__init__(*args, **kwargs)
        # Cargar clientes activos
        self.cliente_id.choices = [
            (c.id, f"{c.nombre} - {c.ruta}") 
            for c in Cliente.query.filter_by(activo=True).order_by(Cliente.ruta, Cliente.nombre).all()
        ]
        self.cliente_id.choices.insert(0, (0, 'Selecciona un cliente...'))


class ActualizarPedidoFabricaForm(FlaskForm):
    """
    Formulario para que la fábrica actualice el estado de un pedido.
    """
    
    estado = SelectField(
        'Estado del Pedido',
        choices=[
            ('pendiente', 'Pendiente'),
            ('completado', 'Completado'),
            ('cancelado', 'Cancelado')
        ],
        validators=[
            DataRequired(message='Debes seleccionar un estado')
        ],
        render_kw={
            'class': 'form-select'
        }
    )
    
    operario_id = SelectField(
        'Operario Responsable',
        coerce=lambda x: int(x) if x else None,
        validators=[
            Optional()
        ],
        render_kw={
            'class': 'form-select'
        }
    )
    
    observaciones_fabrica = TextAreaField(
        'Observaciones',
        validators=[
            Optional()
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ej: No hay suficiente materia prima, se preparará mañana...',
            'rows': 3
        }
    )
    
    submit = SubmitField(
        'Actualizar Pedido',
        render_kw={
            'class': 'btn btn-primary'
        }
    )
    
    def __init__(self, *args, **kwargs):
        super(ActualizarPedidoFabricaForm, self).__init__(*args, **kwargs)
        operarios = Usuario.query.filter_by(rol='operario', activo=True).order_by(Usuario.nombre).all()
        self.operario_id.choices = [(None, 'Sin asignar')] + [
            (op.id, op.nombre) for op in operarios
        ]


class EditarPedidoForm(FlaskForm):
    """
    Formulario para que el vendedor edite un pedido existente.
    """
    
    producto_nombre = StringField(
        'Producto',
        validators=[
            DataRequired(message='El nombre del producto es obligatorio'),
            Length(min=2, max=200)
        ],
        render_kw={
            'class': 'form-control'
        }
    )
    
    cantidad = DecimalField(
        'Cantidad',
        validators=[
            DataRequired(message='La cantidad es obligatoria'),
            NumberRange(min=0.01, message='La cantidad debe ser mayor a 0')
        ],
        render_kw={
            'class': 'form-control',
            'step': '0.01'
        }
    )
    
    unidad = StringField(
        'Unidad',
        validators=[
            Optional(),
            Length(max=50)
        ],
        render_kw={
            'class': 'form-control'
        }
    )
    
    notas_vendedor = TextAreaField(
        'Notas',
        validators=[
            Optional()
        ],
        render_kw={
            'class': 'form-control',
            'rows': 2
        }
    )
    
    submit = SubmitField(
        'Guardar Cambios',
        render_kw={
            'class': 'btn btn-warning'
        }
    )