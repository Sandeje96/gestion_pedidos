# -*- coding: utf-8 -*-
"""
Modelo MensajePedido - Historial de conversación entre ventas y fábrica.
"""

from app import db
from datetime import datetime


class MensajePedido(db.Model):
    """
    Modelo de Mensaje de Pedido.
    Guarda el historial de comunicación entre ventas y fábrica.
    """
    
    __tablename__ = 'mensajes_pedido'
    
    # Campos de la tabla
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id', ondelete='CASCADE'), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'vendedor' o 'fabrica'
    leido = db.Column(db.Boolean, default=False, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relaciones
    pedido = db.relationship('Pedido', backref=db.backref('mensajes', lazy='dynamic', cascade='all, delete-orphan'))
    usuario = db.relationship('Usuario', backref='mensajes_enviados')
    
    def __repr__(self):
        return f'<MensajePedido {self.id} - Pedido {self.pedido_id} - {self.tipo}>'
    
    def to_dict(self):
        """Convierte el mensaje a diccionario"""
        return {
            'id': self.id,
            'pedido_id': self.pedido_id,
            'usuario_id': self.usuario_id,
            'usuario_nombre': self.usuario.nombre if self.usuario else 'Desconocido',
            'mensaje': self.mensaje,
            'tipo': self.tipo,
            'leido': self.leido,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None
        }