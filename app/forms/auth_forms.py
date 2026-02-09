"""
Formularios de autenticación (login).
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    """
    Formulario de inicio de sesión.
    """
    
    username = StringField(
        'Usuario',
        validators=[
            DataRequired(message='El usuario es obligatorio'),
            Length(min=3, max=80, message='El usuario debe tener entre 3 y 80 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ingresa tu usuario',
            'autocomplete': 'username'
        }
    )
    
    password = PasswordField(
        'Contraseña',
        validators=[
            DataRequired(message='La contraseña es obligatoria')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Ingresa tu contraseña',
            'autocomplete': 'current-password'
        }
    )
    
    remember_me = BooleanField(
        'Recordarme',
        default=False,
        render_kw={
            'class': 'form-check-input'
        }
    )
    
    submit = SubmitField(
        'Iniciar Sesión',
        render_kw={
            'class': 'btn btn-primary w-100'
        }
    )


class RegistroForm(FlaskForm):
    """
    Formulario de registro de usuario (opcional, por si querés agregar usuarios desde la web).
    """
    
    nombre = StringField(
        'Nombre Completo',
        validators=[
            DataRequired(message='El nombre es obligatorio'),
            Length(min=3, max=100, message='El nombre debe tener entre 3 y 100 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Juan Pérez'
        }
    )
    
    username = StringField(
        'Usuario',
        validators=[
            DataRequired(message='El usuario es obligatorio'),
            Length(min=3, max=80, message='El usuario debe tener entre 3 y 80 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'juanperez'
        }
    )
    
    email = StringField(
        'Email',
        validators=[
            DataRequired(message='El email es obligatorio'),
            Email(message='Email inválido')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'juan@ejemplo.com',
            'type': 'email'
        }
    )
    
    password = PasswordField(
        'Contraseña',
        validators=[
            DataRequired(message='La contraseña es obligatoria'),
            Length(min=6, message='La contraseña debe tener al menos 6 caracteres')
        ],
        render_kw={
            'class': 'form-control',
            'placeholder': 'Mínimo 6 caracteres'
        }
    )
    
    submit = SubmitField(
        'Registrarse',
        render_kw={
            'class': 'btn btn-success w-100'
        }
    )