/**
 * JavaScript para el Panel de Ventas
 * Maneja WebSockets y actualizaciones en tiempo real
 */

// Conectar a Socket.IO
const socket = io();

// Sonido de notificación (opcional)
const notificationSound = new Audio('/static/sounds/notification.mp3');

// Cuando se conecta exitosamente
socket.on('connect', function() {
    console.log('✅ Conectado al servidor WebSocket');
});

// Cuando se desconecta
socket.on('disconnect', function() {
    console.log('❌ Desconectado del servidor WebSocket');
    mostrarToast('Conexión perdida. Intentando reconectar...', 'warning');
});

// Cuando la fábrica actualiza un pedido
socket.on('pedido_actualizado', function(data) {
    console.log('📦 Pedido actualizado:', data);
    
    const pedido = data.pedido;
    const pedidoRow = document.getElementById(`pedido-${pedido.id}`);
    
    if (pedidoRow) {
        // Actualizar estado visual
        const estadoSelect = pedidoRow.querySelector('.estado-select');
        if (estadoSelect) {
            estadoSelect.value = pedido.estado;
        }
        
        // Actualizar operario
        const operarioSelect = pedidoRow.querySelector('.operario-select');
        if (operarioSelect && pedido.operario_id) {
            operarioSelect.value = pedido.operario_id;
        }
        
        // Actualizar observaciones
        const observacionesCelda = pedidoRow.querySelector('td:nth-child(6)');
        if (observacionesCelda && pedido.observaciones_fabrica) {
            observacionesCelda.innerHTML = `<small>${pedido.observaciones_fabrica.substring(0, 30)}...</small>`;
        }
        
        // NUEVO: Actualizar color de fila
        pedidoRow.classList.remove('estado-pendiente', 'estado-completado', 'estado-cancelado');
        pedidoRow.classList.add(`estado-${pedido.estado}`);
        pedidoRow.setAttribute('data-estado', pedido.estado);
        
        // Resaltar cambio
        pedidoRow.classList.add('animate-pulse');
        setTimeout(() => {
            pedidoRow.classList.remove('animate-pulse');
        }, 2000);
        
        // Actualizar estadísticas
        actualizarEstadisticas();
        
        mostrarToast(`Pedido #${pedido.id} actualizado`, 'info');
    }
});

// Cuando se elimina un pedido
socket.on('pedido_eliminado', function(data) {
    console.log('🗑️ Pedido eliminado:', data);
    
    const pedidoRow = document.getElementById(`pedido-${data.pedido_id}`);
    
    if (pedidoRow) {
        // Animación de desvanecimiento
        pedidoRow.style.transition = 'opacity 0.5s';
        pedidoRow.style.opacity = '0';
        
        setTimeout(() => {
            pedidoRow.remove();
        }, 500);
    }
});

/**
 * Actualiza visualmente el estado de un pedido
 */
function actualizarEstadoPedido(pedidoRow, pedido) {
    // Buscar la celda de estado
    const estadoCelda = pedidoRow.querySelector('.badge');
    
    if (estadoCelda) {
        // Remover todas las clases de badge
        estadoCelda.className = 'badge';
        
        // Agregar clase según el estado
        switch(pedido.estado) {
            case 'pendiente':
                estadoCelda.classList.add('bg-secondary');
                estadoCelda.textContent = 'Pendiente';
                break;
            case 'completado':
                estadoCelda.classList.add('bg-success');
                estadoCelda.textContent = 'Completado';
                break;
            case 'cancelado':
                estadoCelda.classList.add('bg-danger');
                estadoCelda.textContent = 'Cancelado';
                break;
        }
    }
    
    // Actualizar observaciones si existen
    const observacionesCelda = pedidoRow.querySelector('td:nth-child(5)');
    if (observacionesCelda && pedido.observaciones_fabrica) {
        // Si hay observaciones nuevas y no están leídas, agregar badge y botón
        const contenidoHTML = `
            <div class="d-flex align-items-center gap-2">
                <small class="text-muted flex-grow-1">
                    <i class="fas fa-comment"></i>
                    ${pedido.observaciones_fabrica.substring(0, 50)}${pedido.observaciones_fabrica.length > 50 ? '...' : ''}
                </small>
                ${!pedido.visto_por_vendedor ? `
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
        observacionesCelda.innerHTML = contenidoHTML;
    }
    
    // Actualizar operario
    const operarioCelda = pedidoRow.querySelector('td:nth-child(4)');
    if (operarioCelda) {
        operarioCelda.textContent = pedido.operario_nombre || 'Sin asignar';
    }
    // NUEVO: Actualizar clase de estado para colorear la fila
    pedidoRow.classList.remove('estado-pendiente', 'estado-completado', 'estado-cancelado');
    pedidoRow.classList.add(`estado-${pedido.estado}`);
    pedidoRow.setAttribute('data-estado', pedido.estado);
}

/**
 * Muestra una notificación toast
 */
function mostrarToast(mensaje, tipo = 'info') {
    // Crear el toast
    const toastContainer = document.getElementById('toast-container') || crearToastContainer();
    
    const toastId = `toast-${Date.now()}`;
    const iconos = {
        success: 'fa-check-circle',
        info: 'fa-info-circle',
        warning: 'fa-exclamation-triangle',
        danger: 'fa-exclamation-circle'
    };
    
    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `toast align-items-center text-white bg-${tipo} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="fas ${iconos[tipo]} me-2"></i>
                ${mensaje}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    // Mostrar el toast
    const bsToast = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 5000
    });
    bsToast.show();
    
    // Eliminar del DOM cuando se oculta
    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

/**
 * Crea el contenedor de toasts si no existe
 */
function crearToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '9999';
    document.body.appendChild(container);
    return container;
}

/**
 * Marca las observaciones de fábrica como leídas
 */
function marcarComoLeido(pedidoId) {
    console.log(`Marcando pedido ${pedidoId} como leído`);
    
    fetch(`/ventas/pedido/${pedidoId}/marcar-leido`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const pedidoRow = document.getElementById(`pedido-${pedidoId}`);
            
            if (pedidoRow) {
                // Buscar la celda de observaciones (columna 5)
                const observacionesCelda = pedidoRow.querySelector('td:nth-child(5)');
                
                if (observacionesCelda) {
                    // Buscar y remover el badge amarillo "Nueva"
                    const badge = observacionesCelda.querySelector('.badge.bg-warning');
                    if (badge) {
                        badge.remove();
                    }
                    
                    // Buscar y remover el botón verde
                    const boton = observacionesCelda.querySelector('button[onclick*="marcarComoLeido"]');
                    if (boton) {
                        boton.remove();
                    }
                    
                    // Agregar el texto "Leído" si no existe
                    const contenedorFlex = observacionesCelda.querySelector('.d-flex');
                    if (contenedorFlex && !observacionesCelda.querySelector('.text-success')) {
                        const leidoText = document.createElement('small');
                        leidoText.className = 'text-success';
                        leidoText.innerHTML = '<i class="fas fa-check-circle"></i> Leído';
                        contenedorFlex.appendChild(leidoText);
                    }
                }
            }
            
            mostrarToast('Marcado como leído', 'success');
            
            // Actualizar el contador de notificaciones si existe
            actualizarContadorNotificaciones();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        mostrarToast('Error al marcar como leído', 'danger');
    });
}

/**
 * Actualiza el contador de notificaciones no leídas
 */
function actualizarContadorNotificaciones() {
    // Contar todos los badges "Nueva" que quedan
    const badgesNuevos = document.querySelectorAll('.badge.bg-warning.animate-pulse');
    const totalNoLeidos = badgesNuevos.length;
    
    // Actualizar la tarjeta de notificaciones si existe
    const statNotificaciones = document.querySelector('#stat-notificaciones');
    if (statNotificaciones) {
        statNotificaciones.textContent = totalNoLeidos;
    }
    
    // Actualizar badges de clientes
    actualizarBadgesClientesVendedor();
}

/**
 * Actualiza los badges de cada cliente (vendedor)
 */
function actualizarBadgesClientesVendedor() {
    const clienteItems = document.querySelectorAll('.accordion-item');
    
    clienteItems.forEach(clienteItem => {
        const pedidos = clienteItem.querySelectorAll('.pedido-row');
        
        let tieneNuevos = false;
        
        // Verificar si algún pedido tiene badge "Nueva"
        pedidos.forEach(pedido => {
            const badgeNuevo = pedido.querySelector('.badge.bg-warning.animate-pulse');
            if (badgeNuevo) {
                tieneNuevos = true;
            }
        });
        
        // Actualizar o remover el badge "Nuevos" del cliente
        const accordionButton = clienteItem.querySelector('.accordion-button');
        let badgeNuevos = accordionButton.querySelector('.badge.bg-warning');
        
        if (tieneNuevos) {
            if (!badgeNuevos) {
                badgeNuevos = document.createElement('span');
                badgeNuevos.className = 'badge bg-warning ms-2';
                accordionButton.appendChild(badgeNuevos);
            }
            badgeNuevos.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Nuevos';
            badgeNuevos.style.display = '';
        } else if (badgeNuevos) {
            badgeNuevos.remove();
        }
    });
}

/**
 * Confirmación antes de eliminar un pedido
 */
document.addEventListener('DOMContentLoaded', function() {
    // Agregar confirmación a los botones de eliminar
    const formsEliminar = document.querySelectorAll('form[onsubmit*="confirm"]');
    
    formsEliminar.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!confirm('¿Estás seguro de que deseas eliminar este pedido?')) {
                e.preventDefault();
            }
        });
    });
});