/**
 * JavaScript para el Panel de Administración de Fábrica
 * Maneja Socket.IO en tiempo real, alertas visuales y alternar despacho vía AJAX
 */

// Conectar a Socket.IO
const socket = io();

// Contexto de audio para notificaciones sonoras sin depender de archivos de audio
const audioContext = new (window.AudioContext || window.webkitAudioContext)();
function playNotifSound() {
    try {
        const osc = audioContext.createOscillator();
        const gain = audioContext.createGain();
        osc.connect(gain);
        gain.connect(audioContext.destination);
        
        // Sonido tipo campana/notificación premium
        osc.frequency.setValueAtTime(523.25, audioContext.currentTime); // C5
        gain.gain.setValueAtTime(0.08, audioContext.currentTime);
        osc.start();
        
        setTimeout(() => {
            osc.frequency.setValueAtTime(659.25, audioContext.currentTime); // E5
        }, 120);
        
        setTimeout(() => {
            osc.frequency.setValueAtTime(783.99, audioContext.currentTime); // G5
        }, 240);
        
        setTimeout(() => {
            osc.stop();
        }, 360);
    } catch (e) {
        console.warn("AudioContext no se pudo iniciar:", e);
    }
}

// Mostrar alerta mediante Toast de Bootstrap
function showAdminToast(message, type = 'info') {
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
                        <strong class="d-block text-dark small font-monospace">ADMINISTRACIÓN</strong>
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
    
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

// Alternar despacho vía AJAX (POST)
const pedidosEnDespacho = new Set();
function toggleDespacho(pedidoId) {
    if (pedidosEnDespacho.has(pedidoId)) return;
    
    const btn = document.getElementById(`despacho-toggle-${pedidoId}`);
    if (!btn) return;
    
    // Deshabilitar botón temporalmente para evitar peticiones redundantes
    btn.disabled = true;
    pedidosEnDespacho.add(pedidoId);
    
    fetch(`/administracion/pedido/${pedidoId}/actualizar-despachado`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Actualizar estilo del botón e icono
            if (data.despachado) {
                btn.className = 'despacho-toggle-btn despacho-si';
                btn.innerHTML = '<i class="fas fa-truck"></i> <span>SI</span>';
                showAdminToast(`Pedido #${pedidoId} marcado como DESPACHADO`, 'success');
            } else {
                btn.className = 'despacho-toggle-btn despacho-no';
                btn.innerHTML = '<i class="fas fa-truck-loading"></i> <span>NO</span>';
                showAdminToast(`Pedido #${pedidoId} marcado como PENDIENTE de despacho`, 'info');
            }
            
            // Recalcular estadísticas del dashboard localmente
            recalcularEstadisticas();
        } else {
            showAdminToast(`Error: ${data.error || 'No se pudo actualizar el despacho'}`, 'warning');
        }
    })
    .catch(err => {
        console.error('Error al actualizar despacho:', err);
        showAdminToast('Error de conexión al cambiar despacho', 'warning');
    })
    .finally(() => {
        pedidosEnDespacho.delete(pedidoId);
        btn.disabled = false;
    });
}

// Recalcular estadísticas en el DOM sin recargar la página completa
function recalcularEstadisticas() {
    const todosLosBotones = document.querySelectorAll('.despacho-toggle-btn');
    let despachados = 0;
    let totales = 0;
    
    todosLosBotones.forEach(btn => {
        totales++;
        if (btn.classList.contains('despacho-si')) {
            despachados++;
        }
    });
    
    const pendientes = totales - despachados;
    
    // Actualizar badges e indicadores
    const statDespachados = document.getElementById('stat-total-despachados');
    const statPendientes = document.getElementById('stat-pendientes-despacho');
    
    if (statDespachados) statDespachados.textContent = despachados;
    if (statPendientes) statPendientes.textContent = pendientes;
}

// ========================================
// EVENTOS WEBSOCKET - TIEMPO REAL
// ========================================

socket.on('connect', function() {
    console.log('✅ Conectado al servidor WebSocket (Administración)');
});

socket.on('disconnect', function() {
    console.log('❌ Conexión WebSocket perdida');
    showAdminToast('Conexión en tiempo real interrumpida. Intentando reconectar...', 'warning');
});

// Al recibir un NUEVO pedido
socket.on('nuevo_pedido', function(data) {
    const pedido = data.pedido;
    console.log('🆕 Nuevo pedido en el sistema:', pedido);
    
    // Validar si está destinado a administración
    if (pedido.destinatario === 'admin_minorista' || pedido.destinatario === 'admin_mayorista') {
        playNotifSound();
        const sector = pedido.destinatario === 'admin_minorista' ? 'Minorista' : 'Mayorista';
        showAdminToast(`Nuevo pedido ${sector} recibido! #${pedido.id} para ${pedido.cliente_nombre}`, 'success');
        
        // Recargar el panel en 1.5s para incluirlo con sus badges de conteo y datos frescos
        setTimeout(() => {
            location.reload();
        }, 1500);
    }
});

// Al actualizar un pedido
socket.on('pedido_actualizado', function(data) {
    const pedido = data.pedido;
    console.log('🔄 Pedido actualizado:', pedido);
    
    // Solo procesar si el pedido está destinado a administración
    if (pedido.destinatario === 'admin_minorista' || pedido.destinatario === 'admin_mayorista') {
        const row = document.getElementById(`pedido-row-${pedido.id}`);
        if (row) {
            playNotifSound();
            
            // Destacar fila con efecto warning temporal
            row.classList.add('table-warning');
            
            // Actualizar badge de estado
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
            
            // Actualizar botón de despacho
            const btnDespachoCell = document.getElementById(`despacho-cell-${pedido.id}`);
            if (btnDespachoCell) {
                if (pedido.estado === 'cancelado') {
                    btnDespachoCell.innerHTML = '<span class="text-muted small">-</span>';
                } else {
                    let btnHtml = '';
                    if (pedido.despachado) {
                        btnHtml = `<button type="button" id="despacho-toggle-${pedido.id}" class="despacho-toggle-btn despacho-si" onclick="toggleDespacho(${pedido.id})"><i class="fas fa-truck"></i> <span>SI</span></button>`;
                    } else {
                        btnHtml = `<button type="button" id="despacho-toggle-${pedido.id}" class="despacho-toggle-btn despacho-no" onclick="toggleDespacho(${pedido.id})"><i class="fas fa-truck-loading"></i> <span>NO</span></button>`;
                    }
                    btnDespachoCell.innerHTML = btnHtml;
                }
            }
            
            showAdminToast(`Pedido #${pedido.id} ha sido actualizado`, 'info');
            recalcularEstadisticas();
            
            // Recargar para recalcular estadísticas globales de litros y cantidades tras 1.5s
            setTimeout(() => {
                location.reload();
            }, 1500);
        }
    }
});
