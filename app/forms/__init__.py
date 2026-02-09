# -*- coding: utf-8 -*-
"""
Formularios WTForms de la aplicacion.
"""

from app.forms.auth_forms import LoginForm
from app.forms.cliente_forms import ClienteForm
from app.forms.pedido_forms import PedidoForm

__all__ = ['LoginForm', 'ClienteForm', 'PedidoForm']