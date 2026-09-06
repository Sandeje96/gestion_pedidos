# -*- coding: utf-8 -*-
"""
Modelo FormulacionMateriaPrima - Receta propia de una Materia Prima.
Permite que una MP se produzca internamente a partir de otras MPs (semi-elaborado).
"""

from app import db
from datetime import datetime


class FormulacionMateriaPrima(db.Model):
    """
    Fórmula/receta de una Materia Prima.

    Representa que una MP puede fabricarse internamente a partir de otras MPs.
    Ejemplo: "BASE CONCENTRADA" = 0.5 kg de MP-A + 0.3 L de MP-B + 0.2 L de MP-C

    cantidad_por_unidad se calcula igual que en FormulacionProducto:
        cantidad_por_unidad = cantidad_en_lote / lote_base

    Relaciones (dos FK a la misma tabla):
        materia_prima  → la MP que se PRODUCE (output)
        componente     → la MP que se CONSUME como insumo (input)
    """

    __tablename__ = 'formulaciones_materia_prima'

    id = db.Column(db.Integer, primary_key=True)

    # La MP que se fabrica internamente (output)
    materia_prima_id = db.Column(
        db.Integer,
        db.ForeignKey('materias_primas.id'),
        nullable=False,
        index=True
    )

    # El componente/insumo que entra en la receta (input)
    componente_id = db.Column(
        db.Integer,
        db.ForeignKey('materias_primas.id'),
        nullable=False,
        index=True
    )

    # Cantidad de componente por 1 unidad de MP producida (calculado al guardar)
    cantidad_por_unidad = db.Column(db.Numeric(10, 6), nullable=False)

    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Cada componente aparece una sola vez por MP
    __table_args__ = (
        db.UniqueConstraint(
            'materia_prima_id', 'componente_id',
            name='uq_formulacion_mp_componente'
        ),
    )

    # Relaciones explícitas (dos FK a la misma tabla requieren foreign_keys)
    materia_prima = db.relationship(
        'MateriaPrima',
        foreign_keys=[materia_prima_id],
        back_populates='formula_propia'
    )
    componente = db.relationship(
        'MateriaPrima',
        foreign_keys=[componente_id],
        back_populates='usado_como_componente'
    )

    def __repr__(self):
        return (f'<FormulacionMP mp_id={self.materia_prima_id} '
                f'comp_id={self.componente_id} cant={self.cantidad_por_unidad}>')

    def to_dict(self):
        return {
            'id': self.id,
            'materia_prima_id': self.materia_prima_id,
            'componente_id': self.componente_id,
            'componente_nombre': self.componente.nombre if self.componente else None,
            'componente_unidad': self.componente.unidad if self.componente else None,
            'cantidad_por_unidad': float(self.cantidad_por_unidad),
        }
