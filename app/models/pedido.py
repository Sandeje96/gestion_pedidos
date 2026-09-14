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

    # Relación con Producto del catálogo (opcional, para descuento de stock)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True, index=True)
    
    # Detalles del pedido
    producto_nombre = db.Column(db.String(200), nullable=False)  # Guardamos el nombre por si cambia el producto
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)       # Litros totales (calculados)
    unidad = db.Column(db.String(50), nullable=True)
    
    # Presentación y envases (sistema nuevo)
    presentacion = db.Column(db.String(20), nullable=True)         # "300ml","500ml","1litro","5litros","20litros"
    cantidad_envases = db.Column(db.Numeric(10, 2), nullable=True) # Cantidad de envases pedidos
    litros_por_presentacion = db.Column(db.Numeric(10, 4), nullable=True)  # Factor de conversión guardado

    # ── Ajuste parcial de cantidad (propuesto por Fábrica) ──
    ajuste_pendiente = db.Column(db.Boolean, default=False, nullable=False)  # Hay una propuesta en vuelo
    cantidad_propuesta = db.Column(db.Numeric(10, 2), nullable=True)          # Cantidad que Fábrica propone enviar
    ajuste_nota_fabrica = db.Column(db.Text, nullable=True)                   # Nota/motivo de la propuesta

    # Estado del pedido
    estado = db.Column(
        db.String(20), 
        nullable=False, 
        default='pendiente',
        index=True
    )  # Estados: 'pendiente', 'en_proceso', 'completado', 'parcial', 'cancelado'
    
    # Destinatario del pedido ('fabrica', 'admin_minorista', 'admin_mayorista')
    destinatario = db.Column(db.String(30), default='fabrica', nullable=False, index=True)
    
    # Control de despacho
    despachado = db.Column(db.Boolean, default=False, nullable=False)
    
    # Operario responsable
    operario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True, index=True)
    
    # Observaciones
    observaciones_fabrica = db.Column(db.Text, nullable=True)  # Lo que dice la fábrica
    notas_vendedor = db.Column(db.Text, nullable=True)  # Notas del vendedor
    
    # Control de cambios
    modificado = db.Column(db.Boolean, default=False, nullable=False)  # Para notificar cambios
    visto_por_fabrica = db.Column(db.Boolean, default=False, nullable=False)  # Si la fábrica ya lo vio
    visto_por_vendedor = db.Column(db.Boolean, default=False, nullable=False)
    esperando_contestacion = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    fecha_completado = db.Column(db.DateTime, nullable=True)

    # Campos de archivo
    recibido_conforme = db.Column(db.Boolean, default=False, nullable=False, index=True)
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

    # ── Métodos de ajuste parcial de cantidad ──

    def solicitar_ajuste(self, cantidad_propuesta, nota=None):
        """
        Fábrica propone enviar una cantidad menor a la pedida.
        El pedido queda bloqueado hasta que el receptor resuelva.
        """
        self.ajuste_pendiente = True
        self.cantidad_propuesta = cantidad_propuesta
        self.ajuste_nota_fabrica = nota
        self.visto_por_vendedor = False
        self.esperando_contestacion = True
        self.fecha_actualizacion = datetime.utcnow()

    def aprobar_ajuste(self, nueva_cantidad=None):
        """
        Ventas/Admin aprueba la propuesta de Fábrica.
        Si se pasa `nueva_cantidad` (contraproposición), se usa esa.
        De lo contrario se usa la propuesta original de Fábrica.
        Actualiza `cantidad` y limpia el estado de ajuste.
        """
        cantidad_final = nueva_cantidad if nueva_cantidad is not None else self.cantidad_propuesta
        self.cantidad = cantidad_final
        # Si tenía envases, los limpiamos para evitar inconsistencia
        if self.presentacion and self.litros_por_presentacion:
            from decimal import Decimal
            lpp = float(self.litros_por_presentacion)
            if lpp > 0:
                self.cantidad_envases = float(cantidad_final) / lpp
        self.ajuste_pendiente = False
        self.cantidad_propuesta = None
        self.ajuste_nota_fabrica = None
        self.esperando_contestacion = False
        self.modificado = True
        self.visto_por_fabrica = False
        self.fecha_actualizacion = datetime.utcnow()

    def rechazar_ajuste(self):
        """
        Ventas/Admin rechaza la propuesta. La cantidad original NO cambia.
        El pedido vuelve a estado normal (pendiente), Fábrica recibe notificación.
        """
        self.ajuste_pendiente = False
        self.cantidad_propuesta = None
        self.ajuste_nota_fabrica = None
        self.esperando_contestacion = False
        self.modificado = True
        self.visto_por_fabrica = False
        self.fecha_actualizacion = datetime.utcnow()

    
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
            'destinatario': self.destinatario,
            'despachado': self.despachado,
            'operario_id': self.operario_id,
            'operario_nombre': self.operario_responsable.nombre if self.operario_responsable else None,
            'observaciones_fabrica': self.observaciones_fabrica,
            'notas_vendedor': self.notas_vendedor,
            'modificado': self.modificado,
            'visto_por_fabrica': self.visto_por_fabrica,
            'visto_por_vendedor': self.visto_por_vendedor,
            'recibido_conforme': self.recibido_conforme,
            'archivado': self.archivado,
            'fecha_archivado': self.fecha_archivado.isoformat() if self.fecha_archivado else None,
            'semana_archivado': self.semana_archivado,
            'fecha_creacion': self.fecha_creacion.isoformat() if self.fecha_creacion else None,
            'fecha_actualizacion': self.fecha_actualizacion.isoformat() if self.fecha_actualizacion else None,
            'fecha_completado': self.fecha_completado.isoformat() if self.fecha_completado else None,
            'esperando_contestacion': self.esperando_contestacion,
            # Ajuste parcial de cantidad
            'ajuste_pendiente': self.ajuste_pendiente,
            'cantidad_propuesta': float(self.cantidad_propuesta) if self.cantidad_propuesta is not None else None,
            'ajuste_nota_fabrica': self.ajuste_nota_fabrica,
        }

    
    def archivar(self, semana):
        """
        Archiva el pedido al cerrar la semana
        """
        self.archivado = True
        self.fecha_archivado = datetime.utcnow()
        self.semana_archivado = semana