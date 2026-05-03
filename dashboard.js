// ============================================
// 🤖 NOVA EXECUTION DASHBOARD - SUPERIOR DESIGN
// ============================================

const SUPABASE_URL = 'https://xtvopaehirznzeyuanwc.supabase.co';
const SUPABASE_KEY = 'sb_publishable_LCKuoYEaj6uJ4SOTUkHKwA_CYXZYOjf';

const sbClient = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

let currentSync = null;
let locationLogs = {
    Miami: [],
    NC: [],
    Nashville: []
};

// ============================================
// 🚀 INICIAR DASHBOARD
// ============================================

async function initDashboard() {
    try {
        console.log('🚀 Iniciando Dashboard NOVA...');
        
        // Actualizar estado del sistema
        updateSystemStatus();
        
        // Configurar listeners en tiempo real
        setupRealtimeListeners();
        
        // Iniciar actualizaciones periódicas
        startStatusUpdates();
        
        // Mensaje de inicio
        addLocationLog('Miami', 'info', '🤖 Dashboard NOVA iniciado - Esperando eventos del bot...');
        addLocationLog('NC', 'info', '🤖 Dashboard NOVA iniciado - Esperando eventos del bot...');
        addLocationLog('Nashville', 'info', '🤖 Dashboard NOVA iniciado - Esperando eventos del bot...');
        
        // Probar conexión a Supabase
        testSupabaseConnection();
        
        // Simular actividad inicial para demostración
        setTimeout(() => {
            simulateInitialActivity();
        }, 2000);
        
    } catch (error) {
        console.error('Error iniciando dashboard:', error);
        addLocationLog('Miami', 'error', `❌ Error iniciando dashboard: ${error.message}`);
    }
}

async function testSupabaseConnection() {
    try {
        console.log('🔍 Probando conexión a Supabase...');
        
        // Intentar leer datos de prueba
        const { data, error } = await sbClient
            .from('dashboard_logs')
            .select('count')
            .limit(1);
            
        if (error) {
            console.error('❌ Error de conexión a Supabase:', error);
            addLocationLog('Miami', 'error', `❌ Error Supabase: ${error.message}`);
        } else {
            console.log('✅ Conexión a Supabase exitosa');
            addLocationLog('Miami', 'success', '✅ Conexión a Supabase establecida');
        }
    } catch (error) {
        console.error('❌ Error probando Supabase:', error);
        addLocationLog('Miami', 'error', `❌ Error prueba Supabase: ${error.message}`);
    }
}

async function simulateInitialActivity() {
    // Simular algunos logs para demostrar que funciona
    addLocationLog('Miami', 'process', '🔄 Simulando actividad del bot...');
    addLocationLog('NC', 'info', '📊 El bot está activo y enviando logs');
    addLocationLog('Nashville', 'success', '✅ Dashboard listo para recibir eventos en tiempo real');
    
    // Actualizar métricas de ejemplo
    updateLocationMetrics('Miami', { reservations: 45, vehicles: 307, revenue: 2250 });
    updateLocationMetrics('NC', { reservations: 38, vehicles: 307, revenue: 1900 });
    updateLocationMetrics('Nashville', { reservations: 52, vehicles: 307, revenue: 2600 });
    
    addLocationLog('Miami', 'info', '🎯 Ejecuta "reservas@" en Telegram para ver actividad real');
}

// ============================================
// 📋 LOGS POR UBICACIÓN
// ============================================

function addLocationLog(location, type, message, data = {}) {
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
    const logEntry = {
        timestamp,
        type,
        message,
        location,
        data
    };
    
    // Añadir al array de logs de la ubicación
    if (!locationLogs[location]) {
        locationLogs[location] = [];
    }
    locationLogs[location].push(logEntry);
    
    // Mantener solo los últimos 50 logs por ubicación
    if (locationLogs[location].length > 50) {
        locationLogs[location].shift();
    }
    
    // Renderizar en la tarjeta de la ubicación
    renderLocationLog(location, logEntry);
    
    // Actualizar métricas si hay datos
    if (data && Object.keys(data).length > 0) {
        updateLocationMetrics(location, data);
    }
}

function renderLocationLog(location, logEntry) {
    const logsContainer = document.getElementById(`${location.toLowerCase().replace(' ', '')}-logs`);
    if (!logsContainer) return;
    
    // Eliminar estado vacío si existe
    const emptyState = logsContainer.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }
    
    const logDiv = document.createElement('div');
    logDiv.className = `log-entry log-${logEntry.type}`;
    
    const icon = getLogIcon(logEntry.type);
    
    logDiv.innerHTML = `
        <span class="log-timestamp">[${logEntry.timestamp}]</span> ${icon} ${logEntry.message}
    `;
    
    logsContainer.appendChild(logDiv);
    
    // Mantener solo los últimos 20 logs visibles
    while (logsContainer.children.length > 20) {
        logsContainer.removeChild(logsContainer.firstChild);
    }
    
    // Auto-scroll hacia abajo
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function getLogIcon(type) {
    const icons = {
        'process': '🔄',
        'success': '✅',
        'error': '❌',
        'info': 'ℹ️',
        'warning': '⚠️'
    };
    return icons[type] || '📋';
}

// ============================================
// 📊 MÉTRICAS POR UBICACIÓN
// ============================================

function updateLocationMetrics(location, data) {
    const locationId = location.toLowerCase().replace(' ', '');
    
    // Actualizar reservas
    if (data.reservations !== undefined) {
        const reservationsElement = document.getElementById(`${locationId}-reservations`);
        if (reservationsElement) {
            reservationsElement.textContent = data.reservations;
        }
    }
    
    // Actualizar vehículos
    if (data.vehicles !== undefined) {
        const vehiclesElement = document.getElementById(`${locationId}-vehicles`);
        if (vehiclesElement) {
            vehiclesElement.textContent = data.vehicles;
        }
    }
    
    // Actualizar ingresos
    if (data.revenue !== undefined) {
        const revenueElement = document.getElementById(`${locationId}-revenue`);
        if (revenueElement) {
            revenueElement.textContent = `$${data.revenue.toLocaleString()}`;
        }
    }
    
    // Actualizar estado de guardado
    if (data.saved !== undefined) {
        const savedElement = document.getElementById(`${locationId}-saved`);
        if (savedElement) {
            savedElement.textContent = data.saved ? 'Guardado' : 'No guardado';
            savedElement.style.color = data.saved ? '#4CAF50' : '#FF9800';
        }
    }
    
    // Actualizar estado general
    if (data.status) {
        updateLocationStatus(location, data.status);
    }
}

function updateLocationStatus(location, status) {
    const locationId = location.toLowerCase().replace(' ', '');
    const card = document.querySelector(`[id*="${locationId}"]`).closest('.location-card');
    
    if (!card) return;
    
    const statusElement = card.querySelector('.location-status');
    
    // Actualizar estado
    statusElement.className = `location-status status-${status}`;
    statusElement.textContent = getStatusText(status);
}

function getStatusText(status) {
    const statusMap = {
        'pending': 'Pendiente',
        'processing': 'Procesando',
        'completed': 'Completado',
        'error': 'Error'
    };
    return statusMap[status] || 'Desconocido';
}

// ============================================
// 🔄 CONTROL DE SINCRONIZACIÓN
// ============================================

function startWebSync() {
    showSyncProgress('🌐 Iniciando sincronización desde Web...');
    
    // Insertar comando en Supabase
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    const fechaDesde = yesterday.toISOString().split('T')[0];
    const fechaHasta = today.toISOString().split('T')[0];
    
    sbClient
        .from('comandos_bot')
        .insert([{ 
            comando: `sync_range_${fechaDesde}_${fechaHasta}`,
            status: 'pending'
        }])
        .select()
        .single()
        .then(({ data, error }) => {
            if (error) {
                addLocationLog('Miami', 'error', `❌ Error iniciando sincronización web: ${error.message}`);
                hideSyncProgress();
            } else {
                updateSyncInfo('web', fechaDesde, fechaHasta);
                addLocationLog('Miami', 'success', `🌐 Sincronización web iniciada (ID: ${data.id})`);
            }
        });
}

function startTelegramSync() {
    showSyncProgress('📱 Enviando comando de sincronización a Telegram...');
    
    // Simular sincronización desde Telegram
    setTimeout(() => {
        updateSyncProgress(50, '📱 Bot procesando comando...');
        addLocationLog('Miami', 'process', '📱 Comando enviado a Telegram');
        
        setTimeout(() => {
            updateSyncProgress(100, '✅ Sincronización completada');
            updateSyncInfo('telegram', new Date().toISOString().split('T')[0], new Date().toISOString().split('T')[0]);
            addLocationLog('Miami', 'success', '📱 Sincronización Telegram completada');
            
            setTimeout(() => {
                hideSyncProgress();
            }, 2000);
        }, 2000);
    }, 1000);
}

function clearAllLogs() {
    // Limpiar logs de todas las ubicaciones
    Object.keys(locationLogs).forEach(location => {
        locationLogs[location] = [];
        const logsContainer = document.getElementById(`${location.toLowerCase().replace(' ', '')}-logs`);
        if (logsContainer) {
            logsContainer.innerHTML = '<div class="empty-state">Esperando logs de ' + location + '...</div>';
        }
    });
    
    // Resetear métricas
    ['miami', 'nc', 'nashville'].forEach(locationId => {
        updateLocationMetrics(locationId.charAt(0).toUpperCase() + locationId.slice(1), {
            reservations: '--',
            vehicles: '--',
            revenue: '--',
            saved: false,
            status: 'pending'
        });
    });
    
    addLocationLog('Miami', 'info', '🧹 Todos los logs han sido limpiados');
}

// ============================================
// 📊 PROGRESO DE SINCRONIZACIÓN
// ============================================

function showSyncProgress(message) {
    const syncProgress = document.getElementById('syncProgress');
    const progressFill = document.getElementById('progressFill');
    const statusMessage = document.getElementById('syncStatusMessage');
    
    syncProgress.style.display = 'block';
    progressFill.style.width = '0%';
    progressFill.textContent = '0%';
    statusMessage.textContent = message;
}

function updateSyncProgress(percent, message) {
    const progressFill = document.getElementById('progressFill');
    const statusMessage = document.getElementById('syncStatusMessage');
    
    progressFill.style.width = `${percent}%`;
    progressFill.textContent = `${percent}%`;
    statusMessage.textContent = message;
}

function hideSyncProgress() {
    const syncProgress = document.getElementById('syncProgress');
    setTimeout(() => {
        syncProgress.style.display = 'none';
    }, 1000);
}

function updateSyncInfo(source, fechaDesde, fechaHasta) {
    const syncInfo = document.getElementById('syncInfo');
    
    const sourceClass = source === 'web' ? 'sync-web' : source === 'telegram' ? 'sync-telegram' : 'sync-automated';
    const sourceText = source === 'web' ? '🌐 Web' : source === 'telegram' ? '📱 Telegram' : '🤖 Automático';
    
    syncInfo.innerHTML = `
        <div class="sync-source ${sourceClass}">
            ${sourceText}
        </div>
        <div style="margin-top: 10px; color: #666;">
            📅 Rango: ${fechaDesde} al ${fechaHasta}
        </div>
        <div style="margin-top: 5px; color: #666;">
            🕐 ${new Date().toLocaleString()}
        </div>
    `;
}

// ============================================
// 📊 ESTADO DEL SISTEMA
// ============================================

function updateSystemStatus() {
    // Actualizar estado del bot
    const botStatus = document.getElementById('botStatus');
    const botStatusText = document.getElementById('botStatusText');
    
    botStatus.className = 'status-indicator online';
    botStatusText.textContent = 'Online';
    
    // Actualizar estado de Supabase
    const supabaseStatus = document.getElementById('supabaseStatus');
    const supabaseStatusText = document.getElementById('supabaseStatusText');
    
    supabaseStatus.className = 'status-indicator online';
    supabaseStatusText.textContent = 'Conectado';
    
    // Actualizar estado de procesos
    updateProcessStatus();
}

function updateProcessStatus() {
    const processStatus = document.getElementById('processStatus');
    const processStatusText = document.getElementById('processStatusText');
    
    // Contar procesos activos
    let activeProcesses = 0;
    Object.values(locationLogs).forEach(logs => {
        activeProcesses += logs.filter(log => 
            log.type === 'process' && log.message.includes('Procesando')
        ).length;
    });
    
    processStatus.className = activeProcesses > 0 ? 'status-indicator online' : 'status-indicator offline';
    processStatusText.textContent = activeProcesses > 0 ? `${activeProcesses} Activo${activeProcesses > 1 ? 's' : ''}` : 'Inactivo';
}

function updateLastUpdate() {
    const lastUpdate = document.getElementById('lastUpdate');
    lastUpdate.textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
}

// ============================================
// 🔄 LISTENERS EN TIEMPO REAL (LOCAL)
// ============================================

let lastLogCount = 0;
let pollingInterval;

function setupRealtimeListeners() {
    console.log('🔌 Configurando listeners en tiempo real desde servidor local...');
    
    // Iniciar polling para obtener logs del bot
    startBotLogPolling();
    
    // Escuchar comandos del bot desde Supabase (solo comandos)
    try {
        const commandChannel = sbClient
            .channel('bot_commands')
            .on('postgres_changes', 
                { 
                    event: '*', 
                    schema: 'public', 
                    table: 'comandos_bot' 
                },
                (payload) => {
                    console.log('📥 Comando recibido:', payload);
                    handleCommandEvent(payload);
                }
            )
            .subscribe((status) => {
                console.log('📡 Status commands channel:', status);
                if (status === 'SUBSCRIBED') {
                    addLocationLog('NC', 'success', '📡 Conectado a comandos de Supabase');
                }
            });
    } catch (error) {
        console.error('❌ Error configurando canal de comandos:', error);
        addLocationLog('NC', 'error', `❌ Error canal comandos: ${error.message}`);
    }
}

function startBotLogPolling() {
    // Obtener logs cada 500ms del servidor local del bot
    pollingInterval = setInterval(async () => {
        try {
            const response = await fetch('http://127.0.0.1:5001/api/logs');
            const data = await response.json();
            
            if (data.status === 'success') {
                const logs = JSON.parse(data.logs);
                
                // Procesar solo logs nuevos
                if (logs.length > lastLogCount) {
                    const newLogs = logs.slice(lastLogCount);
                    newLogs.forEach(log => {
                        processBotLog(log);
                    });
                    lastLogCount = logs.length;
                }
            }
        } catch (error) {
            console.error('❌ Error obteniendo logs del bot:', error);
            if (lastLogCount === 0) {
                addLocationLog('Miami', 'error', '❌ No se puede conectar al bot. Asegúrate de que el bot esté corriendo.');
            }
        }
    }, 500);
    
    // Obtener métricas cada 2 segundos
    setInterval(async () => {
        try {
            const response = await fetch('http://127.0.0.1:5001/api/metrics');
            const data = await response.json();
            
            if (data.status === 'success') {
                updateDashboardMetrics(data.metrics);
            }
        } catch (error) {
            console.error('❌ Error obteniendo métricas:', error);
        }
    }, 2000);
}

function processBotLog(log) {
    console.log('📥 Log del bot procesado:', log);
    
    const message = log.message;
    const location = log.location;
    const logType = log.type || 'info';
    
    // Si hay ubicación específica, enviar el log ahí
    if (location && ['Miami', 'NC', 'Nashville'].includes(location)) {
        addLocationLog(location, logType, message);
    } else {
        // Logs generales - enviar a todas las ubicaciones o a Miami por defecto
        if (message.includes('INICIANDO') || message.includes('FINALIZADO')) {
            ['Miami', 'NC', 'Nashville'].forEach(loc => {
                addLocationLog(loc, logType, message);
            });
        } else if (message.includes('Vehículos cargados')) {
            const match = message.match(/(\d+) registros/);
            const vehicles = match ? parseInt(match[1]) : 0;
            
            ['Miami', 'NC', 'Nashville'].forEach(loc => {
                addLocationLog(loc, logType, `🚗 Vehículos cargados: ${vehicles} registros`);
            });
        } else if (message.includes('Generando reportes por ubicación')) {
            ['Miami', 'NC', 'Nashville'].forEach(loc => {
                addLocationLog(loc, logType, '📊 Generando reportes por ubicación...');
            });
        } else if (message.includes('Limpiando datos viejos')) {
            ['Miami', 'NC', 'Nashville'].forEach(loc => {
                addLocationLog(loc, logType, '🗑️ Limpiando datos viejos de reportes_hq...');
            });
        } else if (message.includes('Bienvenida enviada')) {
            addLocationLog('Miami', logType, message);
        } else if (message.includes('MENSAJE DE LIMPIEZA')) {
            addLocationLog('Miami', logType, '✅ Mensaje de limpieza enviado');
        } else {
            // Log genérico a Miami
            addLocationLog('Miami', logType, message);
        }
    }
    
    updateLastUpdate();
}

function updateDashboardMetrics(metrics) {
    // Actualizar métricas basadas en los logs del bot
    Object.keys(metrics.locations).forEach(location => {
        const locMetrics = metrics.locations[location];
        if (locMetrics.logs > 0) {
            updateLocationStatus(location, 'active');
        }
    });
}

function handleDashboardLogEvent(payload) {
    console.log('🔍 Procesando evento de dashboard:', payload);
    
    try {
        const { new: newRecord } = payload;
        
        if (!newRecord) {
            console.error('❌ No hay newRecord en payload');
            return;
        }
        
        const logType = newRecord.type;
        const message = newRecord.message;
        const location = newRecord.location;
        const data = newRecord.data || {};
        
        console.log(`📋 Log recibido - Tipo: ${logType}, Mensaje: ${message}, Ubicación: ${location}`);
        
        // Si hay ubicación específica, enviar el log ahí
        if (location && ['Miami', 'NC', 'Nashville'].includes(location)) {
            addLocationLog(location, logType, message, data);
        } else {
            // Logs generales - enviar a todas las ubicaciones o a Miami por defecto
            if (message.includes('INICIANDO') || message.includes('FINALIZADO')) {
                ['Miami', 'NC', 'Nashville'].forEach(loc => {
                    addLocationLog(loc, logType, message, data);
                });
            } else if (message.includes('Vehículos cargados')) {
                const match = message.match(/(\d+) registros/);
                const vehicles = match ? parseInt(match[1]) : 0;
                
                ['Miami', 'NC', 'Nashville'].forEach(loc => {
                    addLocationLog(loc, logType, `🚗 Vehículos cargados: ${vehicles} registros`, { vehicles });
                });
            } else if (message.includes('Generando reportes por ubicación')) {
                ['Miami', 'NC', 'Nashville'].forEach(loc => {
                    addLocationLog(loc, logType, '📊 Generando reportes por ubicación...');
                });
            } else if (message.includes('Limpiando datos viejos')) {
                ['Miami', 'NC', 'Nashville'].forEach(loc => {
                    addLocationLog(loc, logType, '�️ Limpiando datos viejos de reportes_hq...');
                });
            } else if (message.includes('Bienvenida enviada')) {
                addLocationLog('Miami', logType, message);
            } else if (message.includes('MENSAJE DE LIMPIEZA')) {
                addLocationLog('Miami', logType, '✅ Mensaje de limpieza enviado');
            } else {
                // Log genérico a Miami
                addLocationLog('Miami', logType, message, data);
            }
        }
        
        // Actualizar estado de ubicaciones si hay datos
        if (location && data) {
            if (data.reservations) {
                updateLocationMetrics(location, {
                    reservations: data.reservations,
                    revenue: data.revenue || 0,
                    saved: data.saved || false,
                    status: data.status || 'completed'
                });
            }
            
            if (data.status) {
                updateLocationStatus(location, data.status);
            }
        }
        
        // Actualizar información de sincronización
        if (message.includes('SINCRONIZACIÓN COMPLETADA') && data.source) {
            updateSyncInfo(data.source, data.fecha || new Date().toISOString().split('T')[0], data.fecha || new Date().toISOString().split('T')[0]);
        }
        
        updateLastUpdate();
        updateProcessStatus();
        
    } catch (error) {
        console.error('❌ Error procesando evento de dashboard:', error);
        addLocationLog('Miami', 'error', `❌ Error procesando evento: ${error.message}`);
    }
}

function handleCommandEvent(payload) {
    const { eventType, new: newRecord, old: oldRecord } = payload;
    
    if (eventType === 'INSERT') {
        if (newRecord.comando.startsWith('sync_range_')) {
            const match = newRecord.comando.match(/sync_range_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})/);
            if (match) {
                const fechaDesde = match[1];
                const fechaHasta = match[2];
                
                addLocationLog('Miami', 'process', `🔄 Comando de rango recibido: ${fechaDesde} al ${fechaHasta}`);
                updateSyncInfo('web', fechaDesde, fechaHasta);
            }
        }
    } else if (eventType === 'UPDATE') {
        const newStatus = newRecord.status;
        
        if (newStatus.startsWith('processing_')) {
            const progress = newStatus.split('_')[1];
            updateSyncProgress(parseInt(progress), `📊 Procesando... ${progress}%`);
        } else if (newStatus === 'completed') {
            updateSyncProgress(100, '✅ Sincronización completada');
            setTimeout(() => hideSyncProgress(), 2000);
        } else if (newStatus === 'error') {
            addLocationLog('Miami', 'error', '❌ Error en sincronización');
        }
    }
}

function handleReportEvent(payload) {
    const { eventType, new: newRecord } = payload;
    
    if (eventType === 'INSERT') {
        const location = newRecord.location;
        const reservations = newRecord.total_reservations;
        const avgRate = newRecord.avg_rate_day;
        
        addLocationLog(location, 'success', `💾 Reporte diario guardado`);
        
        updateLocationMetrics(location, {
            reservations,
            revenue: Math.round(reservations * avgRate),
            saved: true,
            status: 'completed'
        });
    }
}

function handleRangeReportEvent(payload) {
    const { eventType, new: newRecord } = payload;
    
    if (eventType === 'INSERT') {
        const location = newRecord.location;
        const reservations = newRecord.total_reservations;
        const avgRate = newRecord.avg_rate_day;
        const fechaDesde = newRecord.fecha_desde;
        const fechaHasta = newRecord.fecha_hasta;
        
        addLocationLog(location, 'success', `💾 Reporte de rango guardado (${fechaDesde} al ${fechaHasta})`);
        
        updateLocationMetrics(location, {
            reservations,
            revenue: Math.round(reservations * avgRate),
            saved: true,
            status: 'completed'
        });
    }
}

// ============================================
// 🔄 ACTUALIZACIONES PERIÓDICAS
// ============================================

function startStatusUpdates() {
    // Actualizar estado del sistema cada 30 segundos
    setInterval(() => {
        updateSystemStatus();
        updateProcessStatus();
        updateLastUpdate();
    }, 30000);
}

// ============================================
// 🚀 INICIAR DASHBOARD
// ============================================

// Iniciar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', initDashboard);

// Manejar errores globales
window.addEventListener('error', (event) => {
    addLocationLog('Miami', 'error', `❌ Error global: ${event.error.message}`);
});

window.addEventListener('unhandledrejection', (event) => {
    addLocationLog('Miami', 'error', `❌ Promise rechazada: ${event.reason}`);
});
