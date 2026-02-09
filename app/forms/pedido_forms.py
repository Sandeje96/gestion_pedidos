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
    Formulario para crear/editar pedidos.
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
    
    producto_nombre = StringField(
        'Producto',
        validators=[
            DataRequired(message='El nombre del producto es obligatorio'),
            Length(min=2, max=200, message='El producto debe tener entre 2 y 200 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ej: Pan integral',
            'list': 'productos-list'  # Para autocompletado HTML5
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
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0.01'
        }
    )
    
    unidad = StringField(
        'Unidad',
        validators=[
            Optional(),
            Length(max=50, message='La unidad no puede superar 50 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ej: kg, unidades, litros',
            'list': 'unidades-list'
        }
    )
    
    notas_vendedor = TextAreaField(
        'Notas del Vendedor',
        validators=[
            Optional()
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Instrucciones especiales para la fábrica...',
            'rows': 2
        }
    )
    
    submit = SubmitField(
        'Crear Pedido',
        render_kw={
            'class': 'btn btn-success'
        }
    )
    
    def __init__(self, *args, **kwargs):
        """
        Constructor que carga los clientes disponibles.
        """
        super(PedidoForm, self).__init__(*args, **kwargs)
        
        # Cargar clientes activos para el SelectField
        clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
        self.cliente_id.choices = [
            (c.id, c.nombre) for c in clientes
        ]
        
        # Si no hay clientes, agregar mensaje
        if not clientes:
            self.cliente_id.choices = [(0, '-- No hay clientes disponibles --')]


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
        coerce=lambda x: int(x) if x else None,  # <--- CAMBIAR ESTA LÍNEA
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
        """
        Constructor que carga los operarios disponibles.
        """
        super(ActualizarPedidoFabricaForm, self).__init__(*args, **kwargs)
        
        # Cargar operarios activos
        operarios = Usuario.query.filter_by(rol='operario', activo=True).order_by(Usuario.nombre).all()
        self.operario_id.choices = [(None, 'Sin asignar')] + [  # <--- CAMBIAR '' por None
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