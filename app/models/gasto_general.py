# -*- coding: utf-8 -*-
"""
Modelo GastoGeneral - Representa los pagos a proveedores, servicios,
alquileres y otros gastos generales registrados por Gerencia o Administración.
"""

from app import db
from datetime import datetime, date

class GastoGeneral(db.Model):
    """
    Gastos generales de la empresa: compras a proveedores,
    alquileres, servicios, mantenimiento, impuestos, etc.
    """
    __tablename__ = 'gastos_generales'

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False, default=date.today, index=True)
    categoria = db.Column(db.String(60), nullable=False, index=True)
    # Categorías sugeridas:
    # - 'proveedor_materia_prima'
    # - 'proveedor_insumos'
    # - 'alquiler_servicios'
    # - 'mantenimiento'
    # - 'impuestos'
    # - 'otros'

    concepto = db.Column(db.String(255), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    medio_pago = db.Column(db.String(50), nullable=False, default='efectivo')
    # Medios: 'efectivo', 'transferencia', 'cheque'

    comprobante_nro = db.Column(db.String(100), nullable=True)
    notas = db.Column(db.Text, nullable=True)

    creado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    creado_por = db.relationship('Usuario', foreign_keys=[creado_por_id])

    # Etiquetas amigables para categorías
    CATEGORIAS_LABELS = {
        'proveedor_materia_prima': 'Proveedor de Materia Prima',
        'proveedor_insumos': 'Proveedor de Insumos / Envases',
        'alquiler_servicios': 'Alquiler y Servicios (Luz, Agua, etc.)',
        'mantenimiento': 'Mantenimiento y Reparaciones',
        'impuestos': 'Impuestos y Tasas',
        'otros': 'Otros Gastos'
    }

    @property
    def categoria_label(self):
        return self.CATEGORIAS_LABELS.get(self.categoria, self.categoria)

    def __repr__(self):
        return f'<GastoGeneral #{self.id} {self.concepto} ${self.monto}>'

    def to_dict(self):
        return {
            'id': self.id,
            'fecha': self.fecha.isoformat() if self.fecha else None,
            'categoria': self.categoria,
            'categoria_label': self.categoria_label,
            'concepto': self.concepto,
            'monto': float(self.monto),
            'medio_pago': self.medio_pago,
            'comprobante_nro': self.comprobante_nro,
            'notas': self.notas,
            'creado_por': self.creado_por.nombre if self.creado_por else None,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }
