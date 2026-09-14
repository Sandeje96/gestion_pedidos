/**
 * JavaScript para el dashboard de ventas
 * Maneja actualizaciones en tiempo real de pedidos
 */

// Conectar a Socket.IO
const socket = io({
    transports: ['polling', 'websocket'],
    upgrade: true
});

// Evento: Conexión exitosa
socket.on('connect', function() {
    console.log('✅ Conectado al servidor WebSocket');
});

// Evento: Desconexión
socket.on('disconnect', function() {
    console.log('❌ Desconectado del servidor WebSocket');
});

// Evento: Pedido actualizado por fábrica
socket.on('pedido_actualizado', function(data) {
    console.log('📝 Pedido actualizado por fábrica:', data);
    
    const pedido = data.pedido;
    const pedidoRow = document.getElementById(`pedido-${pedido.id}`);
    
    if (pedidoRow) {
        actualizarEstadoPedido(pedidoRow, pedido);
        
        // Mostrar notificación
        mostrarToast(`Pedido #${pedido.id} actualizado por fábrica`, 'info');
        
        // Actualizar badges de clientes
        actualizarBadgesClientesVendedor();
    } else {
        console.log('Pedido no encontrado en el DOM, recargando página...');
        setTimeout(() => location.reload(), 1000);
    }
});

// Evento: Pedido eliminado
socket.on('pedido_eliminado', function(data) {
    console.log('🗑️ Pedido eliminado:', data);
    
    const pedidoRow = document.getElementById(`pedido-${data.pedido_id}`);
    if (pedidoRow) {
        pedidoRow.style.transition = 'opacity 0.5s';
        pedidoRow.style.opacity = '0';
        setTimeout(() => {
            pedidoRow.remove();
            actualizarBadgesClientesVendedor();
        }, 500);
    }
});

/**
 * Actualizar visualmente un pedido en la tabla
 */
function actualizarEstadoPedido(pedidoRow, pedido) {
    // Actualizar estado
    const estadoCelda = pedidoRow.querySelector('td:nth-child(3)');
    if (estadoCelda) {
        let badgeClass = 'bg-secondary';
        let estadoTexto = 'Pendiente';
        
        if (pedido.estado === 'completado') {
            badgeClass = 'bg-success';
            estadoTexto = 'Completado';
        } else if (pedido.estado === 'cancelado') {
            badgeClass = 'bg-danger';
            estadoTexto = 'Cancelado';
        }
        
        estadoCelda.innerHTML = `<span class="badge ${badgeClass}">${estadoTexto}</span>`;
    }
    
    // Actualizar operario
    const operarioCelda = pedidoRow.querySelector('td:nth-child(4)');
    if (operarioCelda) {
        operarioCelda.textContent = pedido.operario_nombre || 'Sin asignar';
    }
    
    // Actualizar observaciones
    const observacionesCelda = pedidoRow.querySelector('td:nth-child(5)');
    if (observacionesCelda) {
        if (pedido.observaciones_fabrica) {
            const textoCorto = pedido.observaciones_fabrica.substring(0, 50);
            const puntitos = pedido.observaciones_fabrica.length > 50 ? '...' : '';
            
            // Verificar si ya fue leído
            const esNuevo = !pedido.visto_por_vendedor;
            
            observacionesCelda.innerHTML = `
                <div class="d-flex align-items-center gap-2">
                    <small class="text-muted flex-grow-1">
                        <i class="fas fa-comment"></i>
                        ${textoCorto}${puntitos}
                    </small>
                    ${esNuevo ? `
                        <span class="badge bg-warning animate-pulse" title="Nueva notificación">
                            <i class="fas fa-bell"></i> Nueva
                        </span>
                        <button class="btn btn-sm btn-success" 
                                onclick="marcarComoLeido(${pedido.id})"
                                title="Marcar como leído">
                            <i class="fas fa-check"></i>
                        </button>
                    ` : `
                        <small class="text-success">
                            <i class="fas fa-check-circle"></i> Leído
                        </small>
                    `}
                </div>
            `;
        } else {
            observacionesCelda.innerHTML = '<small class="text-muted">-</small>';
        }
    }
    
    // Actualizar color de fila según estado
    pedidoRow.classList.remove('estado-pendiente', 'estado-completado', 'estado-cancelado');
    pedidoRow.classList.add(`estado-${pedido.estado}`);
    pedidoRow.setAttribute('data-estado', pedido.estado);
    
    // Resaltar cambio
    pedidoRow.classList.add('animate-pulse');
    setTimeout(() => {
        pedidoRow.classList.remove('animate-pulse');
    }, 2000);
}

/**
 * Marcar observaciones como leídas por el vendedor
 */
function marcarComoLeido(pedidoId) {
    fetch(`/ventas/pedido/${pedidoId}/marcar-leido`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const pedidoRow = document.getElementById(`pedido-${pedidoId}`);
            if (pedidoRow) {
                const observacionesCelda = pedidoRow.querySelector('td:nth-child(5)');
                if (observacionesCelda) {
                    // Remover badge "Nueva" y botón
                    const badge = observacionesCelda.querySelector('.badge.bg-warning');
                    const boton = observacionesCelda.querySelector('.btn-success');
                    
                    if (badge) badge.remove();
                    if (boton) {
                        boton.outerHTML = `
                            <small class="text-success">
                                <i class="fas fa-check-circle"></i> Leído
                            </small>
                        `;
                    }
                }
            }
            
            // Actualizar contadores
            actualizarBadgesClientesVendedor();
            
            mostrarToast('Marcado como leído', 'success');
        }
    })
    .catch(error => {
        console.error('Error al marcar como leído:', error);
        mostrarToast('Error al actualizar', 'danger');
    });
}

/**
 * Actualizar badges de clientes (Nuevos, Pendientes, etc.)
 */
function actualizarBadgesClientesVendedor() {
    // Iterar sobre cada cliente en el acordeón
    document.querySelectorAll('[id^="cliente-"]').forEach(clienteDiv => {
        const clienteId = clienteDiv.id.replace('cliente-', '');
        const botonCliente = document.querySelector(`[data-bs-target="#collapseCliente${clienteId}"]`);
        
        if (!botonCliente) return;
        
        // Contar pedidos con observaciones nuevas en este cliente
        const pedidosRows = clienteDiv.querySelectorAll('.pedido-row');
        let tieneNuevos = false;
        let pendientesCount = 0;
        let modificadosCount = 0;
        
        pedidosRows.forEach(row => {
            // Verificar si tiene badge "Nueva"
            const badgeNueva = row.querySelector('.badge.bg-warning.animate-pulse');
            if (badgeNueva && badgeNueva.textContent.includes('Nueva')) {
                tieneNuevos = true;
            }
            
            // Contar pendientes
            const estado = row.getAttribute('data-estado');
            if (estado === 'pendiente') {
                pendientesCount++;
            }
            
            // Contar modificados
            if (row.classList.contains('table-warning')) {
                modificadosCount++;
            }
        });
        
        // Actualizar badge "Nuevos"
        let badgeNuevos = botonCliente.querySelector('.badge.bg-warning');
        if (tieneNuevos) {
            if (!badgeNuevos) {
                const nuevosBadge = document.createElement('span');
                nuevosBadge.className = 'badge bg-warning ms-2';
                nuevosBadge.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Respuestas nuevas';
                botonCliente.appendChild(nuevosBadge);
            }
        } else {
            if (badgeNuevos) badgeNuevos.remove();
        }
        
        // Actualizar badge de pendientes
        let badgePendientes = botonCliente.querySelector('.badge.bg-info');
        if (badgePendientes) {
            if (pendientesCount > 0) {
                badgePendientes.innerHTML = `<i class="fas fa-clock"></i> ${pendientesCount} pendiente(s)`;
            } else {
                badgePendientes.remove();
            }
        }
    });
    
    // Actualizar badges de rutas también
    document.querySelectorAll('[id^="ruta-"]').forEach(rutaDiv => {
        const rutaIndex = rutaDiv.id.replace('ruta-', '');
        const botonRuta = document.querySelector(`[data-bs-target="#collapseRuta${rutaIndex}"]`);
        
        if (!botonRuta) return;
        
        // Contar en todos los clientes de esta ruta
        let tieneNuevosRuta = false;
        const clientesDivs = rutaDiv.querySelectorAll('[id^="cliente-"]');
        
        clientesDivs.forEach(clienteDiv => {
            const pedidosRows = clienteDiv.querySelectorAll('.pedido-row');
            pedidosRows.forEach(row => {
                const badgeNueva = row.querySelector('.badge.bg-warning.animate-pulse');
                if (badgeNueva && badgeNueva.textContent.includes('Nueva')) {
                    tieneNuevosRuta = true;
                }
            });
        });
        
        // Actualizar badge de ruta
        let badgeNuevosRuta = botonRuta.querySelector('.badge.bg-warning');
        if (tieneNuevosRuta) {
            if (!badgeNuevosRuta) {
                const nuevosBadge = document.createElement('span');
                nuevosBadge.className = 'badge bg-warning ms-2';
                nuevosBadge.innerHTML = '<i class="fas fa-bell"></i> Respuestas nuevas';
                botonRuta.appendChild(nuevosBadge);
            }
        } else {
            if (badgeNuevosRuta) badgeNuevosRuta.remove();
        }
    });
    // Actualizar badges de rutas
    actualizarBadgesRutas();
}

/**
 * Mostrar notificación toast
 */
function mostrarToast(mensaje, tipo = 'info') {
    const iconos = {
        success: 'fa-check-circle',
        danger: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };
    
    const colores = {
        success: '#28a745',
        danger: '#dc3545',
        warning: '#ffc107',
        info: '#17a2b8'
    };
    
    const icono = iconos[tipo] || iconos.info;
    const color = colores[tipo] || colores.info;
    
    // Crear toast
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 9999;
        min-width: 250px;
        border-left: 4px solid ${color};
        animation: slideIn 0.3s ease-out;
    `;
    
    toast.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px;">
            <i class="fas ${icono}" style="color: ${color}; font-size: 20px;"></i>
            <span style="flex: 1;">${mensaje}</span>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    // Remover después de 3 segundos
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Evento: Pedido marcado como visto por fábrica
socket.on('pedido_visto_por_fabrica', function(data) {
    console.log('👁️ Pedido visto por fábrica:', data);
    
    const pedidoRow = document.getElementById(`pedido-${data.pedido_id}`);
    
    if (pedidoRow) {
        // Remover la clase table-warning (fondo amarillo de modificado)
        pedidoRow.classList.remove('table-warning');
        
        // Remover el badge "Modificado" si existe
        const badgeModificado = pedidoRow.querySelector('.badge.bg-warning');
        if (badgeModificado && badgeModificado.textContent.includes('Modificado')) {
            badgeModificado.remove();
        }
        
        // Actualizar badges de clientes
        actualizarBadgesClientesVendedor();
        actualizarBadgesModificadosSinVer();
        
        mostrarToast('La fábrica vio tu modificación', 'success');
    }
});

/**
 * Actualizar badges de pedidos modificados sin ver
 */
function actualizarBadgesModificadosSinVer() {
    // Actualizar badges de clientes
    document.querySelectorAll('[id^="cliente-"]').forEach(clienteDiv => {
        const clienteId = clienteDiv.id.replace('cliente-', '');
        const botonCliente = document.querySelector(`[data-bs-target="#collapseCliente${clienteId}"]`);
        
        if (!botonCliente) return;
        
        // Contar pedidos modificados sin ver
        const pedidosRows = clienteDiv.querySelectorAll('.pedido-row');
        let modificadosSinVer = 0;
        
        pedidosRows.forEach(row => {
            if (row.classList.contains('table-warning')) {
                modificadosSinVer++;
            }
        });
        
        // Actualizar/remover badge de modificados
        let badgeModificados = botonCliente.querySelector('.badge.bg-danger.animate-pulse');
        
        if (modificadosSinVer > 0) {
            if (!badgeModificados) {
                // Crear badge si no existe
                const nuevosBadge = document.createElement('span');
                nuevosBadge.className = 'badge bg-danger ms-2 animate-pulse';
                nuevosBadge.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${modificadosSinVer} sin ver`;
                
                // Insertarlo después del badge de total pedidos
                const badgeTotal = botonCliente.querySelector('.badge.bg-secondary');
                if (badgeTotal) {
                    badgeTotal.insertAdjacentElement('afterend', nuevosBadge);
                } else {
                    botonCliente.appendChild(nuevosBadge);
                }
            } else {
                // Actualizar el número
                badgeModificados.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${modificadosSinVer} sin ver`;
            }
        } else {
            // Remover badge si ya no hay modificados
            if (badgeModificados) {
                badgeModificados.remove();
            }
        }
    });
    
    // Actualizar badges de rutas
    document.querySelectorAll('[id^="ruta-"]').forEach(rutaDiv => {
        const rutaIndex = rutaDiv.id.replace('ruta-', '');
        const botonRuta = document.querySelector(`[data-bs-target="#collapseRuta${rutaIndex}"]`);
        
        if (!botonRuta) return;
        
        // Contar modificados en toda la ruta
        let modificadosRuta = 0;
        const clientesDivs = rutaDiv.querySelectorAll('[id^="cliente-"]');
        
        clientesDivs.forEach(clienteDiv => {
            const pedidosRows = clienteDiv.querySelectorAll('.pedido-row');
            pedidosRows.forEach(row => {
                if (row.classList.contains('table-warning')) {
                    modificadosRuta++;
                }
            });
        });
        
        // Actualizar/remover badge de ruta
        let badgeModificadosRuta = botonRuta.querySelector('.badge.bg-danger.animate-pulse');
        
        if (modificadosRuta > 0) {
            if (!badgeModificadosRuta) {
                const nuevosBadge = document.createElement('span');
                nuevosBadge.className = 'badge bg-danger ms-2 animate-pulse';
                nuevosBadge.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${modificadosRuta} sin ver`;
                botonRuta.appendChild(nuevosBadge);
            } else {
                badgeModificadosRuta.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${modificadosRuta} sin ver`;
            }
        } else {
            if (badgeModificadosRuta) {
                badgeModificadosRuta.remove();
            }
        }
    });
}

/**
 * Actualizar badges de rutas (pendientes y modificados)
 */
function actualizarBadgesRutas() {
    document.querySelectorAll('[id^="ruta-"]').forEach(rutaDiv => {
        const rutaIndex = rutaDiv.id.replace('ruta-', '');
        const botonRuta = document.querySelector(`[data-bs-target="#collapseRuta${rutaIndex}"]`);
        
        if (!botonRuta) return;
        
        // Contar pendientes y modificados en toda la ruta
        let pendientesRuta = 0;
        let modificadosRuta = 0;
        
        const pedidosEnRuta = rutaDiv.querySelectorAll('.pedido-row');
        pedidosEnRuta.forEach(row => {
            const estado = row.getAttribute('data-estado');
            if (estado === 'pendiente') {
                pendientesRuta++;
            }
            if (row.classList.contains('table-warning')) {
                modificadosRuta++;
            }
        });
        
        // Actualizar badge de pendientes
        let badgePendientes = botonRuta.querySelector('.badge.bg-info');
        if (pendientesRuta > 0) {
            if (!badgePendientes) {
                badgePendientes = document.createElement('span');
                badgePendientes.className = 'badge bg-info ms-2';
                botonRuta.appendChild(badgePendientes);
            }
            badgePendientes.innerHTML = `<i class="fas fa-clock"></i> ${pendientesRuta} pendiente(s)`;
        } else if (badgePendientes) {
            badgePendientes.remove();
        }
        
        // Actualizar badge de modificados
        let badgeModificados = botonRuta.querySelector('.badge.bg-danger.animate-pulse');
        if (modificadosRuta > 0) {
            if (!badgeModificados) {
                badgeModificados = document.createElement('span');
                badgeModificados.className = 'badge bg-danger ms-2 animate-pulse';
                botonRuta.appendChild(badgeModificados);
            }
            badgeModificados.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${modificadosRuta} sin ver`;
        } else if (badgeModificados) {
            badgeModificados.remove();
        }
    });
}

// Agregar estilos de animación
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);



console.log('✅ Script de ventas cargado correctamente');


// ══════════════════════════════════════════════════════════════════════
// SECCIÓN: AJUSTE PARCIAL DE CANTIDAD (Ventas — Resolución)
// ══════════════════════════════════════════════════════════════════════

let _resolverPedidoId = null;
let _resolverAccion = null;   // 'aprobar' | 'rechazar' | 'contraproponer'
let _resolverBlueprint = null; // 'ventas' | 'administracion'

/**
 * Abre el modal de resolución de ajuste propuesto por Fábrica.
 */
function abrirModalResolverAjuste(pedidoId, cantidadOriginal, cantidadPropuesta, unidad, producto, notaFabrica, blueprint) {
    _resolverPedidoId = pedidoId;
    _resolverAccion = null;
    _resolverBlueprint = blueprint;

    document.getElementById('resolver-producto').textContent = producto;
    document.getElementById('resolver-cantidad-original').textContent = `${cantidadOriginal} ${unidad}`;
    document.getElementById('resolver-cantidad-propuesta').textContent = `${cantidadPropuesta} ${unidad}`;
    document.getElementById('resolver-unidad').textContent = unidad;

    const notaDiv = document.getElementById('resolver-nota');
    const notaContainer = document.getElementById('resolver-nota-container');
    if (notaFabrica && notaFabrica.trim()) {
        notaDiv.textContent = notaFabrica;
        notaContainer.classList.remove('d-none');
    } else {
        notaContainer.classList.add('d-none');
    }

    // Reset state
    document.getElementById('panel-contraproponer').classList.add('d-none');
    document.getElementById('panel-nota-respuesta').classList.add('d-none');
    document.getElementById('resolver-nueva-cantidad').value = '';
    document.getElementById('resolver-nota-respuesta').value = '';
    document.getElementById('btn-confirmar-resolver').disabled = true;

    const modal = new bootstrap.Modal(document.getElementById('modalResolverAjuste'));
    modal.show();
}

/**
 * Selecciona la acción del usuario en el modal de resolución.
 */
function seleccionarRespuesta(accion) {
    _resolverAccion = accion;

    const panelContraproponer = document.getElementById('panel-contraproponer');
    const panelNota = document.getElementById('panel-nota-respuesta');

    if (accion === 'contraproponer') {
        panelContraproponer.classList.remove('d-none');
        panelNota.classList.remove('d-none');
    } else if (accion === 'rechazar') {
        panelContraproponer.classList.add('d-none');
        panelNota.classList.remove('d-none');
    } else {
        // aprobar
        panelContraproponer.classList.add('d-none');
        panelNota.classList.add('d-none');
    }

    document.getElementById('btn-confirmar-resolver').disabled = false;
}

/**
 * Confirma la resolución del ajuste (aprobación, contraproposición o rechazo).
 */
async function confirmarResolucionAjuste() {
    if (!_resolverAccion || !_resolverPedidoId) return;

    const btnConfirmar = document.getElementById('btn-confirmar-resolver');
    btnConfirmar.disabled = true;
    btnConfirmar.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Procesando...';

    const nota = document.getElementById('resolver-nota-respuesta').value.trim();
    let accion = _resolverAccion === 'contraproponer' ? 'aprobar' : _resolverAccion;
    let nuevaCantidad = null;

    if (_resolverAccion === 'contraproponer') {
        const val = parseFloat(document.getElementById('resolver-nueva-cantidad').value);
        if (!isNaN(val) && val > 0) {
            nuevaCantidad = val;
        }
    }

    const url = `/${_resolverBlueprint}/pedido/${_resolverPedidoId}/resolver-ajuste`;
    const body = { accion, nota };
    if (nuevaCantidad !== null) body.nueva_cantidad = nuevaCantidad;

    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await resp.json();

        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('modalResolverAjuste')).hide();
            const msg = accion === 'aprobar' ? 'Ajuste aprobado correctamente' : 'Propuesta rechazada';
            console.log(`✅ ${msg}`);
            setTimeout(() => location.reload(), 800);
        } else {
            alert('Error: ' + (data.error || 'No se pudo resolver el ajuste'));
            btnConfirmar.disabled = false;
            btnConfirmar.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Confirmar';
        }
    } catch (e) {
        alert('Error de conexión.');
        btnConfirmar.disabled = false;
        btnConfirmar.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Confirmar';
    }
}

// ── Listener WebSocket: Ventas recibe solicitud de ajuste de Fábrica ──
socket.on('pedido_ajuste_solicitado', function(data) {
    const pedido = data.pedido;
    const cantidadPropuesta = data.cantidad_propuesta;
    const cantidadOriginal = data.cantidad_original;
    const operario = data.operario;

    // Marcar fila del pedido con clase de alerta
    const pedidoRow = document.getElementById(`pedido-${pedido.id}`);
    if (pedidoRow) {
        pedidoRow.classList.add('table-warning');
    }

    // Toast de notificación
    const toast = document.createElement('div');
    toast.className = 'toast align-items-center text-white bg-danger border-0 show position-fixed';
    toast.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 320px;';
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <strong>⚠️ Fábrica propone ajuste:</strong><br>
                Pedido #${pedido.id} — ${operario} propone enviar <strong>${cantidadPropuesta}</strong> en lugar de <strong>${cantidadOriginal}</strong>
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="this.closest('.toast').remove()"></button>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 8000);
});