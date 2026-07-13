# -*- coding: utf-8 -*-
"""
Modelo GastoRepartidor - Representa los gastos diarios registrados por el repartidor.
"""

from app import db
from datetime import datetime, date

class GastoRepartidor(db.Model):
    """
    Gastos registrados por un repartidor durante su jornada.
    Tipos posibles: Combustible, Hospedaje, Viático (Comida), Otros.
    """
    __tablename__ = 'gastos_repartidor'
    
    id = db.Column(db.Integer, primary_key=True)
    repartidor_id = db.Column(
        db.Integer, db.ForeignKey('usuarios.id'), nullable=False, index=True
    )
    fecha = db.Column(db.Date, nullable=False, default=date.today, index=True)
    tipo = db.Column(db.String(50), nullable=False)
    monto = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    notas = db.Column(db.Text, nullable=True)
    procesado = db.Column(db.Boolean, default=False, nullable=False)
    
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relaciones
    repartidor = db.relationship('Usuario', foreign_keys=[repartidor_id], backref=db.backref('gastos', lazy='dynamic'))
    
    def __repr__(self):
        return f'<GastoRepartidor {self.tipo} ${self.monto}>'
