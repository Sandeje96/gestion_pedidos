# -*- coding: utf-8 -*-
"""
Modelo ProduccionDiaria - Registro de producción diaria de la fábrica.
Cada entrada representa una carga de producción que suma al stock del producto.
"""

from app import db
from datetime import datetime, date


class ProduccionDiaria(db.Model):
    """
    Modelo de Producción Diaria.
    Registra cada lote de producción de la fábrica.
    Al crear un registro, se suma al stock_actual del Producto correspondiente.
    Al eliminar un registro, se resta del stock_actual.
    """

    __tablename__ = 'producciones'

    # Campos de la tabla
    id = db.Column(db.Integer, primary_key=True)

    # Producto fabricado (FK a tabla productos)
    producto_id = db.Column(
        db.Integer,
        db.ForeignKey('productos.id'),
        nullable=False,
        index=True
    )

    # Cantidad y unidad producidas
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    unidad = db.Column(db.String(50), nullable=False, default='litros')

    # Fecha en que se realizó la producción (puede ser distinta al día de carga)
    fecha_produccion = db.Column(db.Date, nullable=False, default=date.today, index=True)

    # Quién registró la producción
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey('usuarios.id'),
        nullable=True
    )

    # Notas opcionales
    observaciones = db.Column(db.Text, nullable=True)

    # Timestamp de creación del registro
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    usuario = db.relationship('Usuario', backref='producciones_registradas', lazy='joined')

    def __repr__(self):
        return f'<ProduccionDiaria #{self.id} - {self.cantidad} {self.unidad} de producto_id={self.producto_id}>'

    def to_dict(self):
        """Convierte el registro a diccionario"""
        return {
            'id': self.id,
            'producto_id': self.producto_id,
            'producto_nombre': self.producto.nombre if self.producto else None,
            'cantidad': float(self.cantidad),
            'unidad': self.unidad,
            'fecha_produccion': self.fecha_produccion.isoformat() if self.fecha_produccion else None,
            'usuario_id': self.usuario_id,
            'usuario_nombre': self.usuario.nombre if self.usuario else None,
            'observaciones': self.observaciones,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None
        }
