# -*- coding: utf-8 -*-
"""
Modelos para el sistema de cobros del Repartidor.

Boleta       → Boleta de entrega del día (la crea Ventas, la cobra Repartidor).
PagoBoleta   → Registro de un cobro realizado por el Repartidor a un cliente.
"""

from app import db
from datetime import datetime, date
from decimal import Decimal


class Boleta(db.Model):
    """
    Boleta de entrega diaria para un cliente.

    Estados:
        - pendiente : Aún no se cobró nada.
        - parcial   : Se cobró parte del monto.
        - cobrada   : Cobrada en su totalidad.
    """

    __tablename__ = 'boletas'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer, db.ForeignKey('clientes.id'), nullable=False, index=True
    )
    fecha_entrega = db.Column(db.Date, nullable=False, default=date.today, index=True)
    monto_boleta = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    descripcion = db.Column(db.Text, nullable=True)  # Detalle opcional de Ventas
    estado = db.Column(db.String(20), nullable=False, default='pendiente', index=True)
    # saldo_pendiente se recalcula cada vez que se registra un pago
    saldo_pendiente = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    creado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=True
    )
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relaciones
    cliente = db.relationship('Cliente', backref=db.backref('boletas', lazy='dynamic'))
    creado_por = db.relationship('Usuario', foreign_keys=[creado_por_id])
    pagos = db.relationship(
        'PagoBoleta', backref='boleta', lazy='dynamic', cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Boleta #{self.id} Cliente:{self.cliente_id} ${self.monto_boleta} [{self.estado}]>'

    def total_cobrado(self):
        """Suma de todos los pagos aplicados a esta boleta."""
        result = db.session.query(
            db.func.sum(PagoBoleta.aplicado_boleta)
        ).filter_by(boleta_id=self.id).scalar()
        return Decimal(str(result)) if result else Decimal('0')

    def to_dict(self):
        return {
            'id': self.id,
            'cliente_id': self.cliente_id,
            'fecha_entrega': self.fecha_entrega.isoformat() if self.fecha_entrega else None,
            'monto_boleta': float(self.monto_boleta),
            'descripcion': self.descripcion,
            'estado': self.estado,
            'saldo_pendiente': float(self.saldo_pendiente),
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
        }


class PagoBoleta(db.Model):
    """
    Registro de un cobro realizado por el Repartidor a un cliente.

    Un pago puede cubrir la boleta del día y/o deudas anteriores (cuenta corriente).
    """

    __tablename__ = 'pagos_boleta'

    id = db.Column(db.Integer, primary_key=True)

    # A qué boleta pertenece este pago (la del día, o la más antigua de CC)
    boleta_id = db.Column(
        db.Integer, db.ForeignKey('boletas.id'), nullable=True, index=True
    )
    # Cliente cobrado (referencia directa para búsquedas rápidas)
    cliente_id = db.Column(
        db.Integer, db.ForeignKey('clientes.id'), nullable=False, index=True
    )

    # Formas de pago
    efectivo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    transferencia = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cheque = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    fecha_cobro_cheque = db.Column(db.Date, nullable=True)  # Fecha de cobro del cheque

    # Totales calculados al registrar
    total_recibido = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    aplicado_boleta = db.Column(db.Numeric(10, 2), nullable=False, default=0)  # Aplicado a boleta del día
    aplicado_cc = db.Column(db.Numeric(10, 2), nullable=False, default=0)      # Aplicado a cuenta corriente
    saldo_favor = db.Column(db.Numeric(10, 2), nullable=False, default=0)      # Excedente si pagó de más

    # Quién cobró
    cobrado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=False
    )
    notas = db.Column(db.Text, nullable=True)
    fecha_cobro = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    # Indica si este pago fue cerrado por Ventas (cierre de ruta).
    # False = sesión activa (se muestra en resumen). True = sesión cerrada (archivado).
    procesado = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # Relaciones
    cliente = db.relationship('Cliente', backref=db.backref('pagos', lazy='dynamic'))
    cobrado_por = db.relationship('Usuario', foreign_keys=[cobrado_por_id])

    def __repr__(self):
        return f'<PagoBoleta #{self.id} Cliente:{self.cliente_id} Total:${self.total_recibido}>'

    def to_dict(self):
        return {
            'id': self.id,
            'boleta_id': self.boleta_id,
            'cliente_id': self.cliente_id,
            'efectivo': float(self.efectivo),
            'transferencia': float(self.transferencia),
            'cheque': float(self.cheque),
            'fecha_cobro_cheque': self.fecha_cobro_cheque.isoformat() if self.fecha_cobro_cheque else None,
            'total_recibido': float(self.total_recibido),
            'aplicado_boleta': float(self.aplicado_boleta),
            'aplicado_cc': float(self.aplicado_cc),
            'saldo_favor': float(self.saldo_favor),
            'notas': self.notas,
            'fecha_cobro': self.fecha_cobro.isoformat() if self.fecha_cobro else None,
        }
