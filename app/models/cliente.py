# -*- coding: utf-8 -*-
"""
Modelo Cliente - Representa a los clientes que realizan pedidos.
"""

from app import db
from datetime import datetime


class Cliente(db.Model):
    """
    Modelo de Cliente.
    Un cliente puede tener múltiples pedidos.
    """
    
    __tablename__ = 'clientes'
    
    # Campos de la tabla
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, index=True)
    telefono = db.Column(db.String(50), nullable=True)
    direccion = db.Column(db.String(300), nullable=True)
    ruta = db.Column(db.String(50), nullable=False, default='Ruta 14', index=True)  # <--- NUEVO CAMPO
    notas = db.Column(db.Text, nullable=True)  # Notas adicionales del cliente
    activo = db.Column(db.Boolean, default=True, nullable=False)
    
    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con Usuario (quién creó el cliente)
    creado_por_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    
    # Relaciones
    # Un cliente puede tener muchos pedidos
    pedidos = db.relationship('Pedido', backref='cliente', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        """Representación en string del cliente"""
        return f'<Cliente {self.nombre}>'
    
    def total_pedidos(self):
        """Retorna el total de pedidos del cliente"""
        return self.pedidos.count()
    
    def pedidos_pendientes(self):
        """Retorna pedidos pendientes del cliente"""
        return self.pedidos.filter_by(estado='pendiente').count()
    
    def pedidos_completados(self):
        """Retorna pedidos completados del cliente"""
        return self.pedidos.filter_by(estado='completado').count()
    
    def to_dict(self):
        """Convierte el cliente a diccionario"""
        return {
            'id': self.id,
            'nombre': self.nombre,
            'telefono': self.telefono,
            'direccion': self.direccion,
            'ruta': self.ruta,
            'notas': self.notas,
            'activo': self.activo,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'total_pedidos': self.total_pedidos(),
            'pedidos_pendientes': self.pedidos_pendientes(),
            'pedidos_completados': self.pedidos_completados()
        }