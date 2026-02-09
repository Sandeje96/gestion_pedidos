# -*- coding: utf-8 -*-
"""
Modelo Pedido - Representa los pedidos realizados por clientes.
"""

from app import db
from datetime import datetime


class Pedido(db.Model):
    """
    Modelo de Pedido.
    Conecta clientes con productos y permite seguimiento en tiempo real.
    """
    
    __tablename__ = 'pedidos'
    
    # Campos de la tabla
    id = db.Column(db.Integer, primary_key=True)
    
    # Relación con Cliente
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False, index=True)
    
    # Detalles del pedido
    producto_nombre = db.Column(db.String(200), nullable=False)  # Guardamos el nombre por si cambia el producto
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    unidad = db.Column(db.String(50), nullable=True)
    
    # Estado del pedido
    estado = db.Column(
        db.String(20), 
        nullable=False, 
        default='pendiente',
        index=True
    )  # Estados: 'pendiente', 'en_proceso', 'completado', 'parcial', 'cancelado'
    
    # Operario responsable
    operario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True, index=True)
    
    # Observaciones
    observaciones_fabrica = db.Column(db.Text, nullable=True)  # Lo que dice la fábrica
    notas_vendedor = db.Column(db.Text, nullable=True)  # Notas del vendedor
    
    # Control de cambios
    modificado = db.Column(db.Boolean, default=False, nullable=False)  # Para notificar cambios
    visto_por_fabrica = db.Column(db.Boolean, default=False, nullable=False)  # Si la fábrica ya lo vio
    visto_por_vendedor = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    fecha_completado = db.Column(db.DateTime, nullable=True)

    # Campos de archivo
    archivado = db.Column(db.Boolean, default=False, nullable=False, index=True)
    fecha_archivado = db.Column(db.DateTime, nullable=True)
    semana_archivado = db.Column(db.String(50), nullable=True)  # Ej: "Semana 2025-01"
    
    
    def __repr__(self):
        """Representación en string del pedido"""
        return f'<Pedido #{self.id} - {self.producto_nombre} - {self.estado}>'
    
    def marcar_como_completado(self):
        """Marca el pedido como completado"""
        self.estado = 'completado'
        self.fecha_completado = datetime.utcnow()
    
    def marcar_como_modificado(self):
        """Marca el pedido como modificado (para notificar a fábrica)"""
        self.modificado = True
        self.visto_por_fabrica = False
    
    def marcar_como_visto(self):
        """Marca que la fábrica ya vio la modificación"""
        self.modificado = False
        self.visto_por_fabrica = True

    def marcar_como_visto_por_vendedor(self):
        """Marca que el vendedor ya vió la actualización de fábrica"""
        self.visto_por_vendedor = True
    
    def to_dict(self):
        """Convierte el pedido a diccionario"""
        return {
            'id': self.id,
            'cliente_id': self.cliente_id,
            'cliente_nombre': self.cliente.nombre if self.cliente else None,
            'producto_nombre': self.producto_nombre,
            'cantidad': float(self.cantidad),
            'unidad': self.unidad,
            'estado': self.estado,
            'operario_id': self.operario_id,
            'operario_nombre': self.operario_responsable.nombre if self.operario_responsable else None,
            'observaciones_fabrica': self.observaciones_fabrica,
            'notas_vendedor': self.notas_vendedor,
            'modificado': self.modificado,
            'visto_por_fabrica': self.visto_por_fabrica,
            'visto_por_vendedor': self.visto_por_vendedor,
            'archivado': self.archivado,  # <--- AGREGAR
            'fecha_archivado': self.fecha_archivado.isoformat() if self.fecha_archivado else None,  # <--- AGREGAR
            'semana_archivado': self.semana_archivado,  # <--- AGREGAR
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'fecha_actualizacion': self.fecha_actualizacion.isoformat() if self.fecha_actualizacion else None,
            'fecha_completado': self.fecha_completado.isoformat() if self.fecha_completado else None
        }
    
    def archivar(self, semana):
        """
        Archiva el pedido al cerrar la semana
        """
        self.archivado = True
        self.fecha_archivado = datetime.utcnow()
        self.semana_archivado = semana