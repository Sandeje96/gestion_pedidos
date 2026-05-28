/**
 * JavaScript para el Panel de Sucursal (Sucursales)
 * Maneja Socket.IO en tiempo real para actualizar el estado del pedido
 */

// Conectar a Socket.IO
const socket = io();

// Elemento para reproducir sonido si existe
const audioContext = new (window.AudioContext || window.webkitAudioContext)();
function playNotifSound() {
    try {
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();
        osc.connect(gain);
        gain.connect(audioContext.destination);
        
        // Sonido ascendente tipo "bip-bip"
        osc.frequency.setValueAtTime(587.33, audioContext.currentTime); // D5
        gain.gain.setValueAtTime(0.1, audioContext.currentTime);
        osc.start();
        
        setTimeout(() => {
            osc.frequency.setValueAtTime(880.00, audioContext.currentTime); // A5
        }, 150);
        
        setTimeout(() => {
            osc.stop();
        }, 300);
    } catch (e) {
        console.warn("AudioContext no se pudo iniciar automáticamente:", e);
    }
}

// Mostrar alerta visual mediante Toast de Bootstrap
function showBranchToast(message, type = 'info') {
    // Buscar o crear contenedor de toast
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        toastContainer.style.zIndex = '1090';
        document.body.appendChild(toastContainer);
    }

    const toastId = 'toast-' + Date.now();
    const iconClass = type === 'success' ? 'fa-check-circle text-success' : 
                      type === 'warning' ? 'fa-exclamation-triangle text-warning' : 
                      'fa-info-circle text-primary';
                      
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center bg-white border-0 shadow-lg rounded-3" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body d-flex align-items-center gap-3">
                    <i class="fas ${iconClass} fa-lg"></i>
                    <div>
                        <strong class="d-block text-dark small font-monospace">NOTIFICACIÓN</strong>
                        <span class="text-secondary small">${message}</span>
                    </div>
                </div>
                <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHTML);
    const toastElement = document.getElementById(toastId);
    const bsToast = new bootstrap.Toast(toastElement, { delay: 5000 });
    bsToast.show();
    
    // Remover del DOM al ocultarse
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

// ========================================
// EVENTOS WEBSOCKET - TIEMPO REAL
// ========================================

socket.on('connect', function() {
    console.log('✅ Conectado al servidor WebSocket (Sucursales)');
});

socket.on('disconnect', function() {
    console.log('❌ Conexión WebSocket perdida');
    showBranchToast('Conexión en tiempo real interrumpida. Intentando reconectar...', 'warning');
});

// Cuando llega un NUEVO pedido
socket.on('nuevo_pedido', function(data) {
    const pedido = data.pedido;
    console.log('🆕 Nuevo pedido registrado:', pedido);
    
    // Solo recargar si pertenece a nuestra ruta de sucursales
    if (pedido.cliente_nombre && (
        pedido.cliente_nombre.includes("SUCURSAL") || 
        pedido.cliente_nombre.includes("FRANQUICIA")
    )) {
        playNotifSound();
        showBranchToast(`¡Nuevo pedido cargado! #${pedido.id} para ${pedido.cliente_nombre}`, 'success');
        
        // Recargar dashboard tras 1.5s para re-calcular estadísticas
        setTimeout(() => {
            location.reload();
        }, 1500);
    }
});

// Cuando un pedido es ACTUALIZADO (en fábrica o administración)
socket.on('pedido_actualizado', function(data) {
    const pedido = data.pedido;
    console.log('🔄 Pedido actualizado:', pedido);
    
    const row = document.getElementById(`pedido-row-${pedido.id}`);
    if (row) {
        playNotifSound();
        
        // 1. Resaltar la fila con color
        row.classList.add('order-row-new');
        
        // 2. Actualizar el Badge de Estado
        const badgeEstado = document.getElementById(`estado-badge-${pedido.id}`);
        if (badgeEstado) {
            let badgeHTML = '';
            if (pedido.estado === 'pendiente') {
                badgeHTML = '<span class="badge bg-secondary px-3 py-2 rounded-pill"><i class="fas fa-clock me-1"></i> Pendiente</span>';
            } else if (pedido.estado === 'en_proceso') {
                badgeHTML = '<span class="badge bg-warning text-dark px-3 py-2 rounded-pill"><i class="fas fa-spinner fa-spin me-1"></i> En Proceso</span>';
            } else if (pedido.estado === 'completado') {
                badgeHTML = '<span class="badge bg-success px-3 py-2 rounded-pill"><i class="fas fa-check-circle me-1"></i> Completado</span>';
            } else if (pedido.estado === 'cancelado') {
                badgeHTML = '<span class="badge bg-danger px-3 py-2 rounded-pill"><i class="fas fa-times-circle me-1"></i> Cancelado</span>';
            }
            badgeEstado.innerHTML = badgeHTML;
        }
        
        // 3. Actualizar el Badge de Despacho
        const badgeDespacho = document.getElementById(`despacho-badge-${pedido.id}`);
        if (badgeDespacho && pedido.destinatario !== 'fabrica') {
            if (pedido.despachado) {
                badgeDespacho.innerHTML = '<span class="badge badge-desp-si px-3 py-2 rounded-pill"><i class="fas fa-truck me-1"></i> SI</span>';
            } else {
                badgeDespacho.innerHTML = '<span class="badge badge-desp-no px-3 py-2 rounded-pill"><i class="fas fa-truck-loading me-1"></i> NO</span>';
            }
        }
        
        showBranchToast(`Pedido #${pedido.id} de ${pedido.cliente_nombre} ha sido actualizado`, 'info');
        
        // 4. Recargar estadísticas recargando la página en 1.5s
        setTimeout(() => {
            location.reload();
        }, 1500);
    }
});
