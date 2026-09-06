# -*- coding: utf-8 -*-
"""
Modelo FormulacionProducto - Relaciona productos con sus materias primas (receta/BOM).
"""

from app import db
from datetime import datetime


class FormulacionProducto(db.Model):
    """
    Modelo de Formulación de Producto.
    Representa la "receta" de un producto: cuánto de cada materia prima
    se necesita para producir 1 unidad base del producto (1 litro o 1 unidad).

    El campo cantidad_por_unidad se calcula automáticamente:
        cantidad_por_unidad = cantidad_en_lote / lote_base

    Ejemplo: Para producir 100 litros de Producto X se usan 85 litros de MP-A.
        → cantidad_por_unidad = 85 / 100 = 0.85
    Cuando se produzcan 200 litros:
        → consumo = 0.85 * 200 = 170 litros de MP-A
    """

    __tablename__ = 'formulaciones_producto'

    id = db.Column(db.Integer, primary_key=True)

    # Relaciones FK
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False, index=True)
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=False, index=True)

    # Cantidad de materia prima por 1 unidad base del producto (calculado al guardar)
    cantidad_por_unidad = db.Column(db.Numeric(10, 6), nullable=False)

    # Grupo de alternativas: materias primas con el mismo número de grupo (en el mismo producto)
    # son intercambiables entre sí. NULL = ingrediente único sin alternativas.
    # Ejemplo: grupo=1 puede ser "COLOR BUENOS AIRES" o "COLOR EN POMITO PY"
    grupo_alternativa = db.Column(db.Integer, nullable=True, index=True)

    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Constraint: cada materia prima aparece una sola vez por producto
    __table_args__ = (
        db.UniqueConstraint('producto_id', 'materia_prima_id', name='uq_formulacion_producto_mp'),
    )

    def __repr__(self):
        return (f'<FormulacionProducto producto_id={self.producto_id} '
                f'mp_id={self.materia_prima_id} cant={self.cantidad_por_unidad}>')

    def to_dict(self):
        return {
            'id': self.id,
            'producto_id': self.producto_id,
            'producto_nombre': self.producto.nombre if self.producto else None,
            'materia_prima_id': self.materia_prima_id,
            'materia_prima_nombre': self.materia_prima.nombre if self.materia_prima else None,
            'materia_prima_unidad': self.materia_prima.unidad if self.materia_prima else None,
            'cantidad_por_unidad': float(self.cantidad_por_unidad),
        }
