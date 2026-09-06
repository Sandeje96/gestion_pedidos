# -*- coding: utf-8 -*-
"""
Modelo Producto - Catálogo de productos disponibles para pedidos.
"""

from app import db
from datetime import datetime
from decimal import Decimal


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
    stock_minimo = db.Column(db.Numeric(10, 2), default=0)  # Para alertas de stock
    stock_actual = db.Column(db.Numeric(10, 2), default=0, nullable=False)  # Stock acumulado de producción
    
    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con producciones
    producciones = db.relationship('ProduccionDiaria', backref='producto', lazy='dynamic')

    # Relación con formulaciones (receta/BOM del producto)
    formulaciones = db.relationship('FormulacionProducto', backref='producto', lazy='dynamic',
                                    cascade='all, delete-orphan')


    def __repr__(self):
        """Representación en string del producto"""
        return f'<Producto {self.nombre}>'

    def agregar_stock(self, cantidad):
        """Suma cantidad al stock actual (al registrar producción)"""
        self.stock_actual = (self.stock_actual or Decimal('0')) + Decimal(str(cantidad))

    def descontar_stock(self, cantidad):
        """Resta cantidad del stock actual (al completar un pedido)"""
        nuevo = (self.stock_actual or Decimal('0')) - Decimal(str(cantidad))
        self.stock_actual = max(nuevo, Decimal('0'))  # No permitir stock negativo
    
    def to_dict(self):
        """Convierte el producto a diccionario"""
        return {
            'id': self.id,
            'nombre': self.nombre,
            'descripcion': self.descripcion,
            'precio': float(self.precio) if self.precio else None,
            'unidad': self.unidad,
            'disponible': self.disponible,
            'stock_minimo': float(self.stock_minimo) if self.stock_minimo else 0,
            'stock_actual': float(self.stock_actual) if self.stock_actual else 0
        }