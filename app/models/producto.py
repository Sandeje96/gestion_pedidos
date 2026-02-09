# -*- coding: utf-8 -*-
"""
Modelo Producto - Catálogo de productos disponibles para pedidos.
"""

from app import db
from datetime import datetime


class Producto(db.Model):
    """
    Modelo de Producto.
    Representa los productos que se pueden pedir.
    """
    
    __tablename__ = 'productos'
    
    # Campos de la tabla
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, unique=True, index=True)
    descripcion = db.Column(db.Text, nullable=True)
    precio = db.Column(db.Numeric(10, 2), nullable=True)  # Precio opcional
    unidad = db.Column(db.String(50), nullable=True)  # Ej: "kg", "unidad", "litro"
    disponible = db.Column(db.Boolean, default=True, nullable=False)
    stock_minimo = db.Column(db.Integer, default=0)  # Para alertas de stock
    
    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        """Representación en string del producto"""
        return f'<Producto {self.nombre}>'
    
    def to_dict(self):
        """Convierte el producto a diccionario"""
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'precio': float(self.precio) if self.precio else None,
            'unidad': self.unidad,
            'disponible': self.disponible,
            'stock_minimo': self.stock_minimo
        }