# -*- coding: utf-8 -*-
"""
Modelo MovimientoMateriaPrima - Log de todos los movimientos de stock de materias primas.
"""

from app import db
from datetime import datetime


class MovimientoMateriaPrima(db.Model):
    """
    Modelo de Movimiento de Materia Prima.
    Registra cada ingreso o egreso de stock de una materia prima.
    Sirve para auditoría, trazabilidad y cálculo de consumos.

    Tipos:
        - 'ingreso'           : Compra / entrada de stock (registrada por gerente)
        - 'egreso_produccion' : Consumo por producción (registrado automáticamente)
        - 'ajuste'            : Ajuste manual de inventario
    """

    __tablename__ = 'movimientos_materia_prima'

    id = db.Column(db.Integer, primary_key=True)

    # Materia prima afectada
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'),
                                  nullable=False, index=True)

    # Tipo de movimiento
    tipo = db.Column(db.String(25), nullable=False, index=True)
    # 'ingreso', 'egreso_produccion', 'ajuste'

    # Cantidad (siempre positiva; el tipo indica si suma o resta)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)

    # Descripción libre: proveedor, lote de producción, motivo del ajuste, etc.
    descripcion = db.Column(db.String(300), nullable=True)

    # Referencia opcional a una producción (para egresos automáticos - Fase 2)
    produccion_id = db.Column(db.Integer, db.ForeignKey('producciones.id'), nullable=True)

    # Quién registró el movimiento
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)

    # Timestamp
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relaciones
    usuario = db.relationship('Usuario', backref='movimientos_mp_registrados', lazy='joined')
    produccion = db.relationship('ProduccionDiaria', backref='movimientos_mp', lazy='joined')

    @property
    def descripcion_completa(self):
        """
        Retorna la descripción del movimiento.
        Para egresos de producción, si existe la producción vinculada,
        incluye el nombre del producto fabricado y la cantidad de la producción.
        """
        if self.tipo == 'egreso_produccion' and self.produccion and self.produccion.producto:
            p = self.produccion.producto
            cant = float(self.produccion.cantidad or 0)
            unid = self.produccion.unidad or ''
            return f"Producción #{self.produccion_id} - {p.nombre} ({cant:.2f} {unid})"
        return self.descripcion or '—'

    def __repr__(self):
        return f'<MovimientoMP #{self.id} {self.tipo} {self.cantidad} mp_id={self.materia_prima_id}>'

    def to_dict(self):
        return {
            'id': self.id,
            'materia_prima_id': self.materia_prima_id,
            'materia_prima_nombre': self.materia_prima.nombre if self.materia_prima else None,
            'tipo': self.tipo,
            'cantidad': float(self.cantidad),
            'descripcion': self.descripcion_completa,
            'produccion_id': self.produccion_id,
            'usuario_id': self.usuario_id,
            'usuario_nombre': self.usuario.nombre if self.usuario else None,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }
