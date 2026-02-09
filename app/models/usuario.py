# -*- coding: utf-8 -*-
"""
Modelo Usuario - Representa a vendedores y operarios de fábrica.
"""

from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class Usuario(UserMixin, db.Model):
    """
    Modelo de Usuario del sistema.
    
    Roles:
        - vendedor: Puede crear clientes y pedidos
        - operario: Puede ver pedidos y marcarlos como completados
    """
    
    __tablename__ = 'usuarios'
    
    # Campos de la tabla
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='vendedor')  # 'vendedor' o 'operario'
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ultima_conexion = db.Column(db.DateTime)
    
    # Relaciones
    # Un vendedor puede crear muchos clientes
    clientes_creados = db.relationship('Cliente', backref='creado_por_usuario', lazy='dynamic')
    
    # Un operario puede tener muchos pedidos asignados
    pedidos_asignados = db.relationship('Pedido', backref='operario_responsable', lazy='dynamic')
    
    def __repr__(self):
        """Representación en string del usuario"""
        return f'<Usuario {self.username} - {self.rol}>'
    
    # Métodos para manejar contraseñas
    def set_password(self, password):
        """
        Encripta y guarda la contraseña.
        NUNCA se guarda la contraseña en texto plano.
        """
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """
        Verifica si la contraseña es correcta.
        """
        return check_password_hash(self.password_hash, password)
    
    # Métodos auxiliares para verificar roles
    def es_vendedor(self):
        """Verifica si el usuario es vendedor"""
        return self.rol == 'vendedor'
    
    def es_operario(self):
        """Verifica si el usuario es operario"""
        return self.rol == 'operario'
    
    # Método requerido por Flask-Login
    def get_id(self):
        """Retorna el ID del usuario como string"""
        return str(self.id)
    
    # Método para serializar a JSON (útil para APIs)
    def to_dict(self):
        """Convierte el usuario a diccionario (sin contraseña)"""
        return {
            'id': self.id,
            'nombre': self.nombre,
            'username': self.username,
            'email': self.email,
            'rol': self.rol,
            'activo': self.activo,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'ultima_conexion': self.ultima_conexion.isoformat() if self.ultima_conexion else None
        }