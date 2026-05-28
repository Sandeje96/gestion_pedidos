/**
 * JavaScript para el Panel de Fábrica
 * Maneja WebSockets, filtros y actualizaciones en tiempo real
 */

// Conectar a Socket.IO
const socket = io();

// Sonido de notificación
const notificationSound = new Audio('/static/sounds/notification.mp3');

// Variables globales para filtros
let filtroEstado = '';
let filtroCliente = '';
let filtroOperario = '';
let filtroRuta = '';  // <--- NUEVO

// ========================================
// WEBSOCKETS - Eventos en tiempo real
// ========================================

socket.on('connect', function() {
    console.log('✅ Conectado al servidor WebSocket (Fábrica)');
});

socket.on('disconnect', function() {
    console.log('❌ Desconectado del servidor WebSocket');
    mostrarToast('Conexión perdida. Reconectando...', 'warning');
});

// Cuando llega un NUEVO pedido
socket.on('nuevo_pedido', function(data) {
    console.log('🆕 Nuevo pedido recibido:', data);
    
    const pedido = data.pedido;
    
    // Reproducir sonido de notificación
    reproducirNotificacion();
    
    // Mostrar toast
    mostrarToast(`¡Nuevo pedido! #${pedido.id} - ${pedido.producto_nombre}`, 'success');
    
    // Recargar la página para mostrar el nuevo pedido
    // NUEVO: Agregar clase de estado al recargar
    setTimeout(() => {
        location.reload();
    }, 1000);
});

// Cuando un pedido es MODIFICADO por el vendedor
socket.on('pedido_modificado', function(data) {
    console.log('⚠️ Pedido modificado:', data);
    
    const pedido = data.pedido;
    const pedidoRow = document.querySelector(`[data-pedido-id="${pedido.id}"]`);
    
    if (pedidoRow) {
        // Resaltar como modificado
        pedidoRow.classList.add('table-danger', 'animate-highlight');
        
        // Agregar badge de modificado
        const productoCelda = pedidoRow.querySelector('td:nth-child(2)');
        if (productoCelda && !productoCelda.querySelector('.badge-danger')) {
            const badge = document.createElement('span');
            badge.className = 'badge bg-danger ms-2';
            badge.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ¡MODIFICADO!';
            productoCelda.appendChild(badge);
        }
        
        // Actualizar datos del pedido
        actualizarDatosPedido(pedidoRow, pedido);
        
        // Reproducir sonido
        reproducirNotificacion();
        
        // Mostrar toast
        mostrarToast(`Pedido #${pedido.id} fue modificado por el vendedor`, 'warning');
        
        // Actualizar contador de modificados
        actualizarEstadisticas();
    }
});

// Cuando un pedido es ELIMINADO
socket.on('pedido_eliminado', function(data) {
    console.log('🗑️ Pedido eliminado:', data);
    
    const pedidoRow = document.querySelector(`[data-pedido-id="${data.pedido_id}"]`);
    if (pedidoRow) {
        // Animación de salida
        pedidoRow.style.transition = 'opacity 0.5s';
        pedidoRow.style.opacity = '0';
        
        setTimeout(() => {
            pedidoRow.remove();
            
            // Actualizar estadísticas y badges
            actualizarEstadisticas();
            actualizarBadgesClientes();
        }, 500);
        
        mostrarToast(`Pedido #${data.pedido_id} eliminado`, 'info');
    }
});

// ========================================
// FUNCIONES DE ACTUALIZACIÓN
// ========================================

// Set para evitar requests duplicados simultáneos
const pedidosEnProceso = new Set();

function actualizarEstadoRapido(pedidoId, nuevoEstado) {
    console.log(`Actualizando estado del pedido ${pedidoId} a ${nuevoEstado}`);

    // Evitar requests duplicados para el mismo pedido
    if (pedidosEnProceso.has(pedidoId)) {
        console.warn(`Pedido ${pedidoId} ya tiene una actualización en curso`);
        return;
    }

    const selectEstado = document.querySelector(`.estado-select[data-pedido-id="${pedidoId}"]`);

    // Guardar estado anterior para revertir si falla
    const estadoAnterior = selectEstado ? selectEstado.getAttribute('data-estado-actual') || selectEstado.value : null;
    // Actualizar data-estado-actual para evitar doble revert
    if (selectEstado) {
        selectEstado.setAttribute('data-estado-actual', nuevoEstado);
        selectEstado.disabled = true;
    }

    pedidosEnProceso.add(pedidoId);

    fetch(`/fabrica/pedido/${pedidoId}/actualizar-estado-rapido`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ estado: nuevoEstado })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // ✅ Éxito: actualizar el DOM
            const pedidoRow = document.querySelector(`[data-pedido-id="${pedidoId}"]`);
            if (pedidoRow) {
                pedidoRow.setAttribute('data-estado', nuevoEstado);
                pedidoRow.classList.remove('estado-pendiente', 'estado-completado', 'estado-cancelado');
                pedidoRow.classList.add(`estado-${nuevoEstado}`);
            }

            mostrarToast(`Estado actualizado a: ${nuevoEstado}`, 'success');

            // Toast adicional con info del stock si se completó
            if (nuevoEstado === 'completado' && data.stock_info) {
                const s = data.stock_info;
                if (s.ok) {
                    mostrarToast(
                        `📦 Stock ${s.producto_nombre}: ${s.stock_anterior} → ${s.stock_nuevo} ${s.unidad}`,
                        'info'
                    );
                } else {
                    mostrarToast(
                        `⚠️ Stock no descontado: ${s.motivo || 'Producto sin vincular al catálogo'}`,
                        'warning'
                    );
                }
            }

            actualizarEstadisticas();

        } else {
            // ❌ Error del servidor: revertir select
            console.error('Error del servidor:', data.error);
            if (selectEstado && estadoAnterior) {
                selectEstado.value = estadoAnterior;
                selectEstado.setAttribute('data-estado-actual', estadoAnterior);
            }
            mostrarToast(`Error: ${data.error || 'No se pudo actualizar el estado'}`, 'danger');
        }
    })
    .catch(error => {
        // ❌ Error de red: revertir select
        console.error('Error de conexión:', error);
        if (selectEstado && estadoAnterior) {
            selectEstado.value = estadoAnterior;
            selectEstado.setAttribute('data-estado-actual', estadoAnterior);
        }
        mostrarToast('Error de conexión al actualizar estado', 'danger');
    })
    .finally(() => {
        pedidosEnProceso.delete(pedidoId);
        if (selectEstado) {
            selectEstado.disabled = false;
        }
    });
}

/**
 * Asigna un operario a un pedido rápidamente
 */
function asignarOperarioRapido(pedidoId, operarioId) {
    console.log(`Asignando operario ${operarioId} al pedido ${pedidoId}`);
    
    const formData = new FormData();
    formData.append('operario_id', operarioId);
    
    fetch(`/fabrica/pedido/${pedidoId}/asignar-operario`, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            mostrarToast('Operario asignado correctamente', 'success');
        } else {
            mostrarToast('Error al asignar operario', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        mostrarToast('Error de conexión', 'danger');
    });
}

/**
 * Marca un pedido modificado como visto
 */
function marcarComoVisto(pedidoId) {
    fetch(`/fabrica/pedido/${pedidoId}/marcar-visto`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            const pedidoRow = document.querySelector(`[data-pedido-id="${pedidoId}"]`);
            if (pedidoRow) {
                // Remover fondo rojo y animación
                pedidoRow.classList.remove('table-danger', 'animate-highlight');
                
                // Remover badge "¡MODIFICADO!"
                const badge = pedidoRow.querySelector('.badge.bg-danger');
                if (badge && badge.textContent.includes('¡MODIFICADO!')) {
                    badge.remove();
                }
                
                // Remover botón de marcar visto
                const botonVisto = pedidoRow.querySelector('.btn-success[onclick*="marcarComoVisto"]');
                if (botonVisto) {
                    botonVisto.remove();
                }
                
                // Actualizar estadísticas y badges
                actualizarEstadisticas();
                actualizarBadgesClientes();
            }
            
            mostrarToast('Pedido marcado como visto', 'success');
        }
    })
    .catch(error => {
        console.error('Error al marcar como visto:', error);
        mostrarToast('Error al actualizar', 'danger');
    });
}

/**
 * Actualiza los datos de un pedido en la tabla
 */
function actualizarDatosPedido(pedidoRow, pedido) {
    // Actualizar cantidad
    const cantidadCelda = pedidoRow.querySelector('td:nth-child(3)');
    if (cantidadCelda) {
        cantidadCelda.innerHTML = `<strong>${pedido.cantidad}</strong> ${pedido.unidad || ''}`;
    }
    
    // Actualizar notas del vendedor
    const productoCelda = pedidoRow.querySelector('td:nth-child(2)');
    if (productoCelda && pedido.notas_vendedor) {
        // Remover notas anteriores
        const notasAnteriores = productoCelda.querySelector('small');
        if (notasAnteriores) {
            notasAnteriores.remove();
        }
        
        // Agregar nuevas notas
        const notasElement = document.createElement('small');
        notasElement.className = 'text-muted d-block';
        notasElement.innerHTML = `<i class="fas fa-sticky-note"></i> ${pedido.notas_vendedor}`;
        productoCelda.appendChild(notasElement);
    }
}

/**
 * Actualiza las estadísticas en las tarjetas superiores
 */
function actualizarEstadisticas() {
    // Contar TODOS los pedidos (no solo visibles)
    const todasLasFilas = document.querySelectorAll('.pedido-row');
    
    let pendientes = 0;
    let completados = 0;
    let cancelados = 0;
    let modificados = 0;
    
    todasLasFilas.forEach(row => {
        const estado = row.getAttribute('data-estado');
        
        if (estado === 'pendiente') pendientes++;
        if (estado === 'completado') completados++;
        if (estado === 'cancelado') cancelados++;
        
        // Contar solo los que tienen la clase table-danger (modificados sin ver)
        if (row.classList.contains('table-danger')) {
            modificados++;
        }
    });
    
    // Actualizar las tarjetas superiores
    const statPendientes = document.getElementById('stat-pendientes');
    const statCompletados = document.getElementById('stat-completados');
    const statCancelados = document.getElementById('stat-cancelados');
    const statModificados = document.getElementById('stat-modificados');
    
    if (statPendientes) statPendientes.textContent = pendientes;
    if (statCompletados) statCompletados.textContent = completados;
    if (statCancelados) statCancelados.textContent = cancelados;
    if (statModificados) statModificados.textContent = modificados;
    
    // Actualizar los badges de cada cliente
    actualizarBadgesClientes();
}

function actualizarBadgesClientes() {
    // Para cada cliente, actualizar sus badges
    const clienteItems = document.querySelectorAll('.cliente-item');
    
    clienteItems.forEach(clienteItem => {
        const clienteId = clienteItem.getAttribute('data-cliente-id');
        const pedidosDelCliente = clienteItem.querySelectorAll('.pedido-row');
        
        let totalPedidos = pedidosDelCliente.length;
        let pendientes = 0;
        let modificados = 0;
        let esperando = 0;
        
        pedidosDelCliente.forEach(row => {
            const estado = row.getAttribute('data-estado');
            if (estado === 'pendiente') pendientes++;
            
            // Solo contar los que tienen la clase table-danger
            if (row.classList.contains('table-danger')) {
                modificados++;
            }
            
            // Contar esperando respuesta
            const estadoCelda = row.querySelector('td:nth-child(4)');
            if (estadoCelda) {
                const badgeEsperando = estadoCelda.querySelector('.badge.bg-info');
                if (badgeEsperando && badgeEsperando.textContent.includes('Esperando contestación')) {
                    esperando++;
                }
            }
        });
        
        const accordionButton = clienteItem.querySelector('.accordion-button');
        
        // Actualizar badge de total
        const badgeTotal = clienteItem.querySelector('.badge.bg-primary');
        if (badgeTotal) {
            badgeTotal.textContent = totalPedidos + ' pedido(s)';
        }
        
        // Actualizar o crear badge de pendientes
        let badgePendientes = accordionButton.querySelector('.badge.bg-warning');
        if (pendientes > 0) {
            if (!badgePendientes) {
                badgePendientes = document.createElement('span');
                badgePendientes.className = 'badge bg-warning ms-2';
                accordionButton.appendChild(badgePendientes);
            }
            badgePendientes.textContent = pendientes + ' pendiente(s)';
            badgePendientes.style.display = '';
        } else if (badgePendientes) {
            badgePendientes.style.display = 'none';
        }
        
        // Actualizar o crear badge de modificados
        let badgeModificados = accordionButton.querySelector('.badge.bg-danger.animate-pulse');
        if (modificados > 0) {
            if (!badgeModificados) {
                badgeModificados = document.createElement('span');
                badgeModificados.className = 'badge bg-danger ms-2 animate-pulse';
                accordionButton.appendChild(badgeModificados);
            }
            badgeModificados.innerHTML = '<i class="fas fa-bell"></i> ' + modificados + ' modificado(s)';
            badgeModificados.style.display = '';
        } else if (badgeModificados) {
            badgeModificados.remove();
        }
        
        // Actualizar o crear badge de esperando respuesta
        let badgeEsperando = accordionButton.querySelector('.badge.bg-info');
        if (esperando > 0) {
            if (!badgeEsperando) {
                badgeEsperando = document.createElement('span');
                badgeEsperando.className = 'badge bg-info ms-2';
                accordionButton.appendChild(badgeEsperando);
            }
            badgeEsperando.innerHTML = `<i class="fas fa-reply"></i> ${esperando} esperando`;
        } else if (badgeEsperando) {
            badgeEsperando.remove();
        }
    });
    
    // Actualizar badges de RUTAS
    document.querySelectorAll('.ruta-item').forEach(rutaItem => {
        const ruta = rutaItem.getAttribute('data-ruta');
        const botonRuta = rutaItem.querySelector('.accordion-button');
        
        if (!botonRuta) return;
        
        // Contar modificados, pendientes y esperando en toda la ruta
        let modificadosRuta = 0;
        let pendientesRuta = 0;
        let esperandoRuta = 0;
        
        const pedidosEnRuta = document.querySelectorAll(`[data-ruta="${ruta}"]`);
        pedidosEnRuta.forEach(pedidoRow => {
            if (pedidoRow.classList.contains('table-danger')) {
                modificadosRuta++;
            }
            if (pedidoRow.getAttribute('data-estado') === 'pendiente') {
                pendientesRuta++;
            }
            
            // Contar esperando respuesta
            const estadoCelda = pedidoRow.querySelector('td:nth-child(4)');
            if (estadoCelda) {
                const badgeEsperando = estadoCelda.querySelector('.badge.bg-info');
                if (badgeEsperando && badgeEsperando.textContent.includes('Esperando contestación')) {
                    esperandoRuta++;
                }
            }
        });
        
        // Actualizar badge de modificados
        let badgeModificadosRuta = botonRuta.querySelector('.badge.bg-danger.animate-pulse');
        if (modificadosRuta > 0) {
            if (!badgeModificadosRuta) {
                badgeModificadosRuta = document.createElement('span');
                badgeModificadosRuta.className = 'badge bg-danger ms-2 animate-pulse';
                botonRuta.appendChild(badgeModificadosRuta);
            }
            badgeModificadosRuta.innerHTML = `<i class="fas fa-bell"></i> ${modificadosRuta} modificado(s)`;
        } else if (badgeModificadosRuta) {
            badgeModificadosRuta.remove();
        }
        
        // Actualizar badge de pendientes
        let badgePendientesRuta = botonRuta.querySelector('.badge.bg-warning');
        if (pendientesRuta > 0) {
            if (!badgePendientesRuta) {
                badgePendientesRuta = document.createElement('span');
                badgePendientesRuta.className = 'badge bg-warning ms-2';
                botonRuta.appendChild(badgePendientesRuta);
            }
            badgePendientesRuta.textContent = `${pendientesRuta} pendiente(s)`;
        } else if (badgePendientesRuta) {
            badgePendientesRuta.remove();
        }
        
        // Actualizar badge de esperando respuesta
        let badgeEsperandoRuta = botonRuta.querySelector('.badge.bg-info');
        if (esperandoRuta > 0) {
            if (!badgeEsperandoRuta) {
                badgeEsperandoRuta = document.createElement('span');
                badgeEsperandoRuta.className = 'badge bg-info ms-2';
                botonRuta.appendChild(badgeEsperandoRuta);
            }
            badgeEsperandoRuta.innerHTML = `<i class="fas fa-reply"></i> ${esperandoRuta} esperando`;
        } else if (badgeEsperandoRuta) {
            badgeEsperandoRuta.remove();
        }

        // ── Actualizar badge de litros (excluye cancelados) ──────────────
        let totalLitros = 0;
        rutaItem.querySelectorAll('.pedido-row').forEach(row => {
            if (row.getAttribute('data-estado') !== 'cancelado') {
                totalLitros += parseFloat(row.getAttribute('data-cantidad') || 0);
            }
        });

        let badgeLitros = botonRuta.querySelector('.badge-litros-ruta');
        if (totalLitros > 0) {
            if (!badgeLitros) {
                badgeLitros = document.createElement('span');
                badgeLitros.className = 'badge bg-secondary ms-2 badge-litros-ruta';
                const flexDiv = botonRuta.querySelector('.d-flex');
                if (flexDiv) flexDiv.appendChild(badgeLitros);
                else botonRuta.appendChild(badgeLitros);
            }
            badgeLitros.innerHTML = `<i class="fas fa-tint"></i> ${totalLitros.toFixed(1)} lts`;
            badgeLitros.style.display = '';
        } else if (badgeLitros) {
            badgeLitros.style.display = 'none';
        }
    });
}

// ========================================
// FILTROS
// ========================================

document.addEventListener('DOMContentLoaded', function() {
    // Filtro por estado
    const filtroEstadoSelect = document.getElementById('filtro-estado');
    if (filtroEstadoSelect) {
        filtroEstadoSelect.addEventListener('change', function() {
            filtroEstado = this.value;
            aplicarFiltros();
        });
    }

    // Filtro por ruta (NUEVO)
    const filtroRutaSelect = document.getElementById('filtro-ruta');
    if (filtroRutaSelect) {
        filtroRutaSelect.addEventListener('change', function() {
            filtroRuta = this.value;
            aplicarFiltros();
        });
    }
    
    // Filtro por cliente
    const filtroClienteSelect = document.getElementById('filtro-cliente');
    if (filtroClienteSelect) {
        filtroClienteSelect.addEventListener('change', function() {
            filtroCliente = this.value;
            aplicarFiltros();
        });
    }
    
    // Filtro por operario
    const filtroOperarioSelect = document.getElementById('filtro-operario');
    if (filtroOperarioSelect) {
        filtroOperarioSelect.addEventListener('change', function() {
            filtroOperario = this.value;
            aplicarFiltros();
        });
    }
});

/**
 * Aplica los filtros seleccionados
 */
function aplicarFiltros() {
    const rutaItems = document.querySelectorAll('.ruta-item');
    
    rutaItems.forEach(rutaItem => {
        const ruta = rutaItem.getAttribute('data-ruta');
        const clienteItems = rutaItem.querySelectorAll('.cliente-item');
        
        let rutaVisible = false;
        
        // Aplicar filtro de ruta
        if (filtroRuta && ruta !== filtroRuta) {
            rutaItem.style.display = 'none';
            return; // Skip this ruta
        } else {
            rutaItem.style.display = '';
        }
        
        clienteItems.forEach(clienteItem => {
            const clienteId = clienteItem.getAttribute('data-cliente-id');
            const pedidosRows = clienteItem.querySelectorAll('.pedido-row');
            
            let clienteVisible = false;
            
            pedidosRows.forEach(row => {
                const estado = row.getAttribute('data-estado');
                const operarioId = row.getAttribute('data-operario-id');
                
                let visible = true;
                
                // Aplicar filtro de estado
                if (filtroEstado && estado !== filtroEstado) {
                    visible = false;
                }
                
                // Aplicar filtro de operario
                if (filtroOperario && operarioId !== filtroOperario) {
                    visible = false;
                }
                
                // Mostrar/ocultar fila
                row.style.display = visible ? '' : 'none';
                
                if (visible) {
                    clienteVisible = true;
                    rutaVisible = true;
                }
            });
            
            // Mostrar/ocultar cliente completo
            clienteItem.style.display = clienteVisible ? '' : 'none';
        });
        
        // Mostrar/ocultar ruta completa
        if (!rutaVisible) {
            rutaItem.style.display = 'none';
        }
    });
    
    // Actualizar estadísticas después de filtrar
    actualizarEstadisticas();
}

// ========================================
// UTILIDADES
// ========================================

/**
 * Reproduce sonido de notificación
 */
function reproducirNotificacion() {
    notificationSound.play().catch(e => {
        console.log('No se pudo reproducir el sonido:', e);
    });
}

/**
 * Muestra un toast de notificación
 */
function mostrarToast(mensaje, tipo = 'info') {
    const toastContainer = document.getElementById('toast-container') || crearToastContainer();
    
    const iconos = {
        success: 'fa-check-circle',
        info: 'fa-info-circle',
        warning: 'fa-exclamation-triangle',
        danger: 'fa-exclamation-circle'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${tipo} border-0`;
    toast.setAttribute('role', 'alert');
    
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
    
    const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: 5000 });
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

function crearToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '9999';
    document.body.appendChild(container);
    return container;
}

// Evento: Pedido modificado por ventas
socket.on('pedido_modificado', function(data) {
    console.log('📝 Pedido modificado por ventas:', data);
    
    const pedido = data.pedido;
    const pedidoRow = document.querySelector(`[data-pedido-id="${pedido.id}"]`);
    
    if (pedidoRow) {
        // Agregar fondo rojo y badge
        pedidoRow.classList.add('table-danger', 'animate-highlight');
        
        // Buscar celda del producto (segunda columna)
        const productoCelda = pedidoRow.querySelector('td:nth-child(2)');
        if (productoCelda) {
            // Verificar si ya existe el badge
            let badgeModificado = productoCelda.querySelector('.badge.bg-danger');
            if (!badgeModificado) {
                badgeModificado = document.createElement('span');
                badgeModificado.className = 'badge bg-danger';
                badgeModificado.innerHTML = '<i class="fas fa-exclamation-triangle"></i> ¡MODIFICADO!';
                
                const strong = productoCelda.querySelector('strong');
                if (strong) {
                    strong.insertAdjacentElement('afterend', document.createElement('br'));
                    strong.insertAdjacentElement('afterend', badgeModificado);
                }
            }
        }
        
        // NUEVO: Si ventas respondió, quitar "Esperando contestación"
        if (!pedido.esperando_contestacion) {
            const estadoCelda = pedidoRow.querySelector('td:nth-child(4)');
            if (estadoCelda) {
                const badgeEsperando = estadoCelda.querySelector('.badge.bg-info');
                if (badgeEsperando && badgeEsperando.textContent.includes('Esperando contestación')) {
                    // Reemplazar por el selector de estado
                    estadoCelda.innerHTML = `
                        <select class="form-select form-select-sm estado-select" 
                                data-pedido-id="${pedido.id}"
                                onchange="actualizarEstadoRapido(${pedido.id}, this.value)">
                            <option value="pendiente" ${pedido.estado === 'pendiente' ? 'selected' : ''}>
                                Pendiente
                            </option>
                            <option value="completado" ${pedido.estado === 'completado' ? 'selected' : ''}>
                                Completado
                            </option>
                            <option value="cancelado" ${pedido.estado === 'cancelado' ? 'selected' : ''}>
                                Cancelado
                            </option>
                        </select>
                    `;
                }
            }
        }
        
        // Agregar botón de marcar visto si no existe
        const accionesCelda = pedidoRow.querySelector('td:nth-child(7)');
        if (accionesCelda) {
            let botonVisto = accionesCelda.querySelector('.btn-success[onclick*="marcarComoVisto"]');
            if (!botonVisto) {
                botonVisto = document.createElement('button');
                botonVisto.className = 'btn btn-sm btn-success';
                botonVisto.setAttribute('onclick', `marcarComoVisto(${pedido.id})`);
                botonVisto.setAttribute('title', 'Marcar como visto');
                botonVisto.innerHTML = '<i class="fas fa-check"></i>';
                accionesCelda.appendChild(botonVisto);
            }
        }
        
        // Actualizar estadísticas
        actualizarEstadisticas();
        actualizarBadgesClientes();
        
        mostrarToast(`Pedido #${pedido.id} modificado`, 'warning');
    }
});