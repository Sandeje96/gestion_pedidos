# -*- coding: utf-8 -*-
"""
Modelo CierreRuta - Snapshot del balance del repartidor al momento de cerrar ruta.

Cada vez que Ventas ejecuta un cierre de ruta (total o por cliente individual),
se guarda un registro por cada repartidor involucrado con el estado exacto
de su billetera en ese momento.

Esto permite al Gerente consultar históricamente cuánto tenía cada repartidor
antes de rendir, filtrando por fecha, ruta o repartidor.
"""

from app import db
from datetime import datetime


class CierreRuta(db.Model):
    """
    Snapshot del balance del repartidor al momento del cierre de ruta.

    Se genera automáticamente en dos situaciones:
        - Ventas cierra la ruta completa (resetear_ruta_dia)
        - Ventas cierra el día de un cliente individual (resetear_cliente_dia)

    En ambos casos se captura el balance ANTES de marcar los registros
    como procesado=True, garantizando que el snapshot refleja el valor real
    que tenía el repartidor en ese instante.
    """

    __tablename__ = 'cierres_ruta'

    id = db.Column(db.Integer, primary_key=True)

    # ── Contexto del cierre ──
    ruta = db.Column(db.String(100), nullable=False, index=True)
    # Tipo: 'ruta_completa' o 'cliente_individual'
    tipo_cierre = db.Column(db.String(30), nullable=False, default='ruta_completa')

    # ── Actores ──
    repartidor_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True
    )
    cerrado_por_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=False
    )

    # ── Snapshot del balance ──
    total_efectivo = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_transferencia = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_cheque = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_gastos = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    # neto_efectivo = total_efectivo - total_gastos (el dinero que el repartidor debe rendir)
    neto_efectivo = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    # ── Contadores ──
    cantidad_cobros = db.Column(db.Integer, nullable=False, default=0)
    cantidad_gastos = db.Column(db.Integer, nullable=False, default=0)

    # ── Timestamp ──
    fecha_cierre = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    # ── Relaciones ──
    repartidor = db.relationship(
        'Usuario',
        foreign_keys=[repartidor_id],
        backref=db.backref('cierres_ruta', lazy='dynamic')
    )
    cerrado_por = db.relationship(
        'Usuario',
        foreign_keys=[cerrado_por_id]
    )

    def __repr__(self):
        return (
            f'<CierreRuta #{self.id} '
            f'Ruta:{self.ruta} '
            f'Rep:{self.repartidor_id} '
            f'Neto:${self.neto_efectivo}>'
        )

    def to_dict(self):
        """Serializa el cierre a diccionario."""
        return {
            'id': self.id,
            'ruta': self.ruta,
            'tipo_cierre': self.tipo_cierre,
            'repartidor_id': self.repartidor_id,
            'repartidor_nombre': self.repartidor.nombre if self.repartidor else None,
            'cerrado_por_id': self.cerrado_por_id,
            'cerrado_por_nombre': self.cerrado_por.nombre if self.cerrado_por else None,
            'total_efectivo': float(self.total_efectivo),
            'total_transferencia': float(self.total_transferencia),
            'total_cheque': float(self.total_cheque),
            'total_gastos': float(self.total_gastos),
            'neto_efectivo': float(self.neto_efectivo),
            'cantidad_cobros': self.cantidad_cobros,
            'cantidad_gastos': self.cantidad_gastos,
            'fecha_cierre': self.fecha_cierre.isoformat() if self.fecha_cierre else None,
        }
