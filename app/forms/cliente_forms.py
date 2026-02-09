"""
Formularios para gestión de clientes.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField, SelectField  # <--- Agregar SelectField
from wtforms.validators import DataRequired, Length, Optional


class ClienteForm(FlaskForm):
    """
    Formulario para crear/editar clientes.
    """
    
    nombre = StringField(
        'Nombre del Cliente',
        validators=[
            DataRequired(message='El nombre es obligatorio'),
            Length(min=2, max=200, message='El nombre debe tener entre 2 y 200 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ej: Panadería El Sol',
            'autofocus': True
        }
    )
    
    telefono = StringField(
        'Teléfono',
        validators=[
            Optional(),
            Length(max=50, message='El teléfono no puede superar 50 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ej: +54 9 376 123-4567',
            'type': 'tel'
        }
    )
    
    direccion = StringField(
        'Dirección',
        validators=[
            Optional(),
            Length(max=300, message='La dirección no puede superar 300 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ej: Av. Corrientes 1234'
        }
    )
    
    ruta = SelectField(
        'Ruta',
        choices=[
            ('Ruta 14', 'Ruta 14'),
            ('Ruta 12', 'Ruta 12'),
            ('Corrientes', 'Corrientes')
        ],
        validators=[
            DataRequired(message='Debes seleccionar una ruta')
        ],
        render_kw={
            'class': 'form-select'
        }
    )
    
    notas = TextAreaField(
        'Notas Adicionales',
        validators=[
            Optional()
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Información adicional del cliente...',
            'rows': 3
        }
    )
    
    submit = SubmitField(
        'Guardar Cliente',
        render_kw={
            'class': 'btn btn-primary'
        }
    )