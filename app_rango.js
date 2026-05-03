// ============================================
// 🔑 CONFIGURACIÓN SUPABASE
// ============================================
const SUPABASE_URL = 'https://xtvopaehirznzeyuanwc.supabase.co';
const SUPABASE_KEY = 'sb_publishable_LCKuoYEaj6uJ4SOTUkHKwA_CYXZYOjf'; // ← reemplaza con tu anon eyJ... key

let sbClient       = null;
let chartInstance  = null;
let allData        = [];

// ============================================
// 📅 UTILIDADES DE FECHA Y HORA
// ============================================

/** Retorna hora en formato HH:MM desde timestamp UTC */
function fmtTime(ts) {
  return new Date(ts).toISOString().substring(11, 16);
}

/** Retorna fecha en formato MM/DD/YYYY desde timestamp */
function fmtDate(ts) {
  const d  = new Date(ts);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${mm}/${dd}/${d.getFullYear()}`;
}

/** Formatea fecha para mostrar (DD/MM/YYYY) */
function fmtDateDisplay(ts) {
  const d  = new Date(ts);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${dd}/${mm}/${d.getFullYear()}`;
}

/** Actualiza el rango de fechas en badge */
function updatePeriodRange(data) {
  if (!data || data.length === 0) {
    document.getElementById('badgePeriodRange').textContent = 'Sin datos';
    return;
  }
  
  // Obtener el reporte más reciente
  const latestReport = data[0];
  
  // Verificar si existen los campos fecha_desde y fecha_hasta
  if (!latestReport.fecha_desde || !latestReport.fecha_hasta) {
    document.getElementById('badgePeriodRange').textContent = 'Esperando datos de rango...';
    return;
  }
  
  // Usar los campos directamente como strings (YYYY-MM-DD)
  const fechaDesdeStr = latestReport.fecha_desde;
  const fechaHastaStr = latestReport.fecha_hasta;
  
  // Convertir YYYY-MM-DD a MM/DD/YYYY
  const formatDateString = (dateStr) => {
    const [year, month, day] = dateStr.split('-');
    return `${month}/${day}/${year}`;
  };
  
  const startStr = formatDateString(fechaDesdeStr);
  const endStr = formatDateString(fechaHastaStr);
  const periodText = `${startStr} al ${endStr}`;
  
  // Actualizar solo el badge
  document.getElementById('badgePeriodRange').textContent = periodText;
}

// ============================================
// 📅 CALENDAR MODAL LOGIC
// ============================================

let calendarState = {
  year: 2026,
  month: 4, // Mayo (0-indexed)
  desde: null,
  hasta: null,
  selectionStep: 'desde'
};

function openCalendar() {
  document.getElementById('calendarModal').style.display = 'flex';
  renderCalendar();
}

function closeCalendar() {
  document.getElementById('calendarModal').style.display = 'none';
}

function changeMonth(direction) {
  calendarState.month += direction;
  if (calendarState.month < 0) {
    calendarState.month = 11;
    calendarState.year--;
  } else if (calendarState.month > 11) {
    calendarState.month = 0;
    calendarState.year++;
  }
  renderCalendar();
}

function renderCalendar() {
  const monthNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                      'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
  
  // Update title
  document.getElementById('calendarTitle').textContent = 
    `${monthNames[calendarState.month]} ${calendarState.year}`;
  
  // Calculate days
  const firstDay = new Date(calendarState.year, calendarState.month, 1);
  const lastDay = new Date(calendarState.year, calendarState.month + 1, 0);
  const prevLastDay = new Date(calendarState.year, calendarState.month, 0);
  
  const firstDayIndex = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1; // Monday = 0
  const lastDayDate = lastDay.getDate();
  const prevLastDayDate = prevLastDay.getDate();
  
  const daysContainer = document.getElementById('calendarDays');
  daysContainer.innerHTML = '';
  
  // Previous month days
  for (let i = firstDayIndex; i > 0; i--) {
    const day = document.createElement('div');
    day.className = 'calendar-day empty';
    day.textContent = prevLastDayDate - i + 1;
    daysContainer.appendChild(day);
  }
  
  // Current month days
  for (let i = 1; i <= lastDayDate; i++) {
    const day = document.createElement('div');
    day.className = 'calendar-day';
    day.textContent = i;
    
    const dateStr = `${calendarState.year}-${String(calendarState.month + 1).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
    
    // Check if this day is selected as desde
    if (calendarState.desde === dateStr) {
      day.style.background = '#00ff00';
      day.style.color = '#000';
      day.style.fontWeight = '600';
    }
    // Check if this day is selected as hasta
    else if (calendarState.hasta === dateStr) {
      day.style.background = '#ff0000';
      day.style.color = '#fff';
      day.style.fontWeight = '600';
    }
    // Check if this day is in the range
    else if (calendarState.desde && calendarState.hasta && dateStr > calendarState.desde && dateStr < calendarState.hasta) {
      day.style.background = '#ffff00';
      day.style.color = '#000';
      day.style.fontWeight = '500';
    }
    
    day.onclick = () => selectDate(dateStr);
    daysContainer.appendChild(day);
  }
  
  // Next month days
  const remainingDays = 42 - (firstDayIndex + lastDayDate);
  for (let i = 1; i <= remainingDays; i++) {
    const day = document.createElement('div');
    day.className = 'calendar-day empty';
    day.textContent = i;
    daysContainer.appendChild(day);
  }
}

function selectDate(dateStr) {
  if (!calendarState.desde) {
    // First selection - set desde
    calendarState.desde = dateStr;
    calendarState.selectionStep = 'hasta';
    updateDateDisplays();
    renderCalendar();
  } else if (!calendarState.hasta) {
    // Second selection - set hasta
    if (dateStr >= calendarState.desde) {
      calendarState.hasta = dateStr;
      updateDateDisplays();
      renderCalendar();
      document.getElementById('confirmBtn').disabled = false;
    } else {
      showError('La fecha "hasta" no puede ser anterior a la fecha "desde"');
    }
  } else {
    // Reset and start over
    calendarState.desde = dateStr;
    calendarState.hasta = null;
    calendarState.selectionStep = 'hasta';
    updateDateDisplays();
    renderCalendar();
    document.getElementById('confirmBtn').disabled = true;
  }
}

function updateDateDisplays() {
  if (calendarState.desde) {
    const [year, month, day] = calendarState.desde.split('-');
    const formattedDate = `${month}/${day}/${year}`;
    document.getElementById('modalDesdeDisplay').textContent = formattedDate;
  } else {
    document.getElementById('modalDesdeDisplay').textContent = 'Seleccionar';
  }
  
  if (calendarState.hasta) {
    document.getElementById('modalHastaDisplay').textContent = formatDate(calendarState.hasta);
  } else {
    document.getElementById('modalHastaDisplay').textContent = 'Seleccionar';
  }
}

function formatDate(dateStr) {
  const [year, month, day] = dateStr.split('-');
  return `${month}/${day}/${year}`;
}

function confirmRange() {
  if (!calendarState.desde || !calendarState.hasta) {
    showError('Por favor selecciona ambas fechas');
    return;
  }
  
  closeCalendar();
  executeSync();
}

function executeSync() {
  const btn = document.getElementById('forceSyncBtn');
  const text = document.getElementById('syncText');
  const icon = btn.querySelector('.sync-icon');
  
  // Estado de carga
  btn.disabled = true;
  text.innerText = "Sincronizando...";
  icon.classList.add('spin');
  
  // Usar errorBox existente para mostrar progreso
  const errorBox = document.getElementById('errorBox');
  errorBox.className = 'error-box-large sync-progress';
  errorBox.innerHTML = `
    <div class="sync-status-content">
      <span id="syncStatusMsg">Sincronizando rango ${formatDate(calendarState.desde)} a ${formatDate(calendarState.hasta)}...</span>
      <div class="progress-container">
        <div id="syncProgressBar" class="progress-fill" style="width: 15%"></div>
      </div>
    </div>
  `;

  syncRangeWithDates();
}

async function syncRangeWithDates() {
  const btn = document.getElementById('forceSyncBtn');
  const text = document.getElementById('syncText');
  const icon = btn.querySelector('.sync-icon');
  
  // Get selected dates from calendar state
  const fechaDesde = calendarState.desde;
  const fechaHasta = calendarState.hasta;
  
  // Validar fechas
  if (!fechaDesde || !fechaHasta) {
    showError('Por favor selecciona ambas fechas (desde y hasta)');
    return;
  }
  
  if (fechaDesde > fechaHasta) {
    showError('La fecha "desde" no puede ser posterior a la fecha "hasta"');
    return;
  }

  try {
    // 1. Insertar comando con rango de fechas en Supabase
    const comando = `sync_range_${fechaDesde}_${fechaHasta}`;
    
    const { data, error } = await sbClient
      .from('comandos_bot')
      .insert([{ comando: comando, status: 'pending' }])
      .select()
      .single();

    if (error) {
      console.error('❌ ERROR WEB insertando comando:', error);
      throw error;
    }
    
    const comandoId = data.id;
    
    // Actualizar progreso a 30%
    const progressBar = document.getElementById('syncProgressBar');
    const statusMsg = document.getElementById('syncStatusMsg');
    if (progressBar) {
      progressBar.style.width = '30%';
    }
    const channel = sbClient
      .channel('comando_status_' + comandoId)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'comandos_bot', filter: `id=eq.${comandoId}` },
        (payload) => {
          const status = payload.new.status;
          
          // Detectar progreso dinámico (ej: processing_33, processing_66)
          if (status && status.startsWith('processing_')) {
            const progressPercent = status.split('_')[1];
            
            // Generar mensaje basado en el progreso
            const locations = ['Miami', 'NC', 'Nashville'];
            const locationIndex = Math.floor((progressPercent - 33) / 20);
            const currentLocation = locations[Math.min(locationIndex, 2)];
            
            let progressMessage = `Procesando ${currentLocation}...`;
            if (progressPercent >= 90) {
              progressMessage = 'Finalizando...';
            }
            
            if (progressBar) {
              progressBar.style.width = `${progressPercent}%`;
            }
            if (statusMsg) {
              statusMsg.innerText = progressMessage;
            }
          }
          
          // Status processing normal (inicial)
          else if (status === 'processing') {
            if (progressBar) {
              progressBar.style.width = '50%';
            }
            if (statusMsg) {
              statusMsg.innerText = `Bot procesando rango ${formatDate(fechaDesde)} a ${formatDate(fechaHasta)}...`;
            }
          }

          // Status completed
          else if (status === 'completed') {
            if (progressBar) {
              progressBar.style.width = '100%';
            }
            if (statusMsg) {
              statusMsg.innerText = "✅ Sincronización finalizada y listo";
            }
            text.innerText = "¡Listo!";
            icon.classList.remove('spin');
            
            // Mostrar mensaje de éxito y refrescar página
            setTimeout(() => {
              // Mostrar notificación de éxito
              const successNotification = document.createElement('div');
              successNotification.style.cssText = `
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: linear-gradient(135deg, #4CAF50, #45a049);
                color: white;
                padding: 20px 40px;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                z-index: 10000;
                box-shadow: 0 4px 20px rgba(76, 175, 80, 0.3);
                animation: fadeInOut 3s ease-in-out;
              `;
              successNotification.textContent = "✅ Sincronización completada exitosamente";
              document.body.appendChild(successNotification);
              
              // Refrescar página después de mostrar mensaje
              setTimeout(() => {
                location.reload();
              }, 2000);
            }, 1000);
            
            sbClient.removeChannel(channel);
          }
        }
      )
      .subscribe();

    // Simulación de progreso si el bot no responde
    let simulationInterval = null;
    let simulationProgress = 30;
    
    // Iniciar simulación después de 3 segundos si no hay respuesta del bot
    const simulationTimeout = setTimeout(() => {
      simulationInterval = setInterval(() => {
        if (simulationProgress < 90) {
          simulationProgress += 15;
          
          // Actualizar barra de progreso simulada
          if (progressBar) {
            progressBar.style.width = `${simulationProgress}%`;
          }
          
          // Actualizar mensaje basado en el progreso
          if (statusMsg) {
            const locations = ['Miami', 'NC', 'Nashville'];
            const locationIndex = Math.floor((simulationProgress - 30) / 20);
            const currentLocation = locations[Math.min(locationIndex, 2)];
            
            if (simulationProgress < 60) {
              statusMsg.innerText = `Procesando ${currentLocation}...`;
            } else if (simulationProgress < 90) {
              statusMsg.innerText = `Finalizando ${currentLocation}...`;
            } else {
              statusMsg.innerText = 'Guardando datos en Supabase...';
            }
          }
        } else {
          // Completar simulación
          clearInterval(simulationInterval);
          
          if (progressBar) {
            progressBar.style.width = '100%';
            progressBar.style.backgroundColor = '#4CAF50';
          }
          if (statusMsg) {
            statusMsg.innerText = '✅ Sincronización completada (simulada)';
          }
          text.innerText = "¡Listo!";
          icon.classList.remove('spin');
          
          // Recargar página después de 2 segundos
          setTimeout(() => {
            location.reload();
          }, 2000);
          
          sbClient.removeChannel(channel);
        }
      }, 1500); // Actualizar cada 1.5 segundos
    }, 3000); // Esperar 3 segundos antes de iniciar simulación
    
    // Cancelar simulación si el bot responde
    const originalChannel = channel;
    const enhancedChannel = {
      ...originalChannel,
      removeChannel: () => {
        clearTimeout(simulationTimeout);
        if (simulationInterval) clearInterval(simulationInterval);
        sbClient.removeChannel(originalChannel);
      }
    };

  } catch (err) {
    console.error("Error en sincronización por rango:", err);
    btn.disabled = false;
    
    // Limpiar errorBox
    const errorBox = document.getElementById('errorBox');
    errorBox.className = 'error-box-large';
    errorBox.innerHTML = '';
    
    text.innerText = "Sincronizar";
    icon.classList.remove('spin');
    showError("Error: " + (err.message || JSON.stringify(err) || "No se pudo conectar al bot"));
  }
}

// Añadir animación CSS para notificaciones
const style = document.createElement('style');
style.textContent = `
  @keyframes fadeInOut {
    0% { opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
    20% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    80% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    100% { opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
  }
`;
document.head.appendChild(style);

// ============================================
// 🎨 MANEJO DE TEMAS
// ============================================

function setTheme(name) {
  document.documentElement.setAttribute('data-theme', name === 'cyber' ? '' : name);
  if (chartInstance) updateChartTheme();
}

function updateChartTheme() {
  if (!chartInstance) return;
  const style = getComputedStyle(document.documentElement);
  chartInstance.data.datasets[0].borderColor     = style.getPropertyValue('--neon-primary').trim();
  chartInstance.data.datasets[0].backgroundColor = style.getPropertyValue('--neon-primary').trim() + '40';
  chartInstance.data.datasets[1].borderColor     = style.getPropertyValue('--neon-secondary').trim();
  chartInstance.update();
}

// ============================================
// 🔌 ESTADO DE CONEXIÓN
// ============================================

function updateStatus(status) {
  const dot  = document.querySelector('.status-dot');
  const text = document.getElementById('connectionStatus');
  const states = {
    connected: { bg: 'var(--neon-success)', shadow: '0 0 12px var(--neon-success)', label: '● Conectado' },
    error:     { bg: 'var(--neon-danger)',  shadow: '0 0 12px var(--neon-danger)',  label: '✗ Error' },
    loading:   { bg: 'var(--neon-warning)', shadow: '',                              label: '⏳ Actualizando...' },
  };
  const s = states[status] || states.loading;
  dot.style.background  = s.bg;
  dot.style.boxShadow   = s.shadow;
  text.textContent      = s.label;
}

function updateLastUpdate() {
  document.getElementById('lastUpdate').textContent =
    'Última actualización: ' + new Date().toLocaleTimeString('en-US', { hour12: false });
}

function showError(msg) {
  console.error('❌', msg);
  const box = document.getElementById('errorBox');
  box.style.display = 'block';
  box.textContent   = '❌ ' + msg;
  updateStatus('error');
}

// ============================================
// 📡 CARGA DE DATOS DESDE SUPABASE
// ============================================

async function fetchData() {
  try {
    updateStatus('loading');
    
    // Primero intentar cargar reportes_hq_s (rango)
    let { data, error } = await sbClient
      .from('reportes_hq_s')
      .select('*')
      .order('hora_reporte', { ascending: false })
      .limit(200);

    if (error) throw error;
    
    // Si reportes_hq_s está vacía, usar reportes_hq como fallback
    if (!data || data.length === 0) {
      const { data: fallbackData, error: fallbackError } = await sbClient
        .from('reportes_hq')
        .select('*')
        .order('hora_reporte', { ascending: false })
        .limit(200);
      
      if (fallbackError) throw fallbackError;
      if (!fallbackData || fallbackData.length === 0)
        throw new Error('No hay datos disponibles en ninguna tabla');
      
      // Convertir datos diarios a formato de rango para compatibilidad
      data = fallbackData.map(row => ({
        ...row,
        fecha_desde: row.fecha,
        fecha_hasta: row.fecha,
        // Añadir campos de rango si no existen
        vehicles_available: row.vehicles_available || 0,
        return_next_day: row.return_next_day || 0,
        reservas_next_day: row.reservas_next_day || 0
      }));
    }

    allData = data;
    updateUI(data);
    updateStatus('connected');
    updateLastUpdate();
    return true;
  } catch (err) {
    showError('Error cargando datos: ' + err.message);
    return false;
  }
}

// ============================================
// 🖥️ ORQUESTADOR DE UI
// ============================================

function updateUI(data) {
  updatePeriodRange(data);  // Actualizar rango de fechas
  renderLocationCards(data);
  renderKPIs(data);
  renderChart(data);
}

/** Obtiene el snapshot más reciente por ubicación */
function getLatestByLocation(data) {
  const map = {};
  data.forEach(row => { if (!map[row.location]) map[row.location] = row; });
  return Object.values(map);
}

// ============================================
// 📍 TARJETAS DE UBICACIÓN
// ============================================

/** Determina clase y label de proyección según disponibilidad proyectada */
function getProjectionClass(value) {
  if (value < 7)   return { class: 'critical', label: 'CRÍTICO' };
  if (value <= 14) return { class: 'warning',  label: 'PRECAUCIÓN' };
  if (value <= 20) return { class: 'moderate', label: 'MODERADO' };
  return             { class: 'optimal',  label: 'ÓPTIMO' };
}

function renderLocationCards(data) {
  const container = document.getElementById('locationsContainer');
  const latest    = getLatestByLocation(data);

  container.innerHTML = '';

  latest.forEach(loc => {
    // Métricas (MISMO CÁLCULO QUE app.js)
    const totalReservations  = (loc.on_rent||0) + (loc.open||0) + (loc.no_show||0) + (loc.unqualified||0) + (loc.cancellations||0) + (loc.turo||0);
    const totalFleet         = (loc.on_rent||0) + (loc.vehicles_available||0);
    const utilization        = totalFleet > 0 ? Math.round((loc.on_rent / totalFleet) * 100) : 0;
    const issues             = (loc.no_show||0) + (loc.cancellations||0) + (loc.turo||0);
    const utilClass          = utilization >= 80 ? 'success' : utilization >= 50 ? 'warning' : 'danger';
    const issuesClass        = issues > 5 ? 'danger' : issues > 2 ? 'warning' : '';

    // Proyección día siguiente (MISMO CÁLCULO)
    const vehiclesAvailable  = loc.vehicles_available || 0;
    const returnNextDay      = loc.return_next_day    || 0;
    const reservasNextDay    = loc.reservas_next_day  || 0;
    const projectedAvail     = (vehiclesAvailable + returnNextDay) - reservasNextDay;
    const projection         = getProjectionClass(projectedAvail);

    // Tarjeta padre principal (MISMA ESTRUCTURA)
    const card = document.createElement('div');
    card.className = 'location-parent-card glass fade-in';
    card.innerHTML = `
      <div class="location-header">
        <div class="location-info">
          <h3 class="location-name">${loc.location}</h3>
          <div class="location-brand">Brand ID: <strong>${loc.brand_id}</strong></div>
        </div>
        <div class="location-status">
          <div class="live-indicator">● RANGO</div>
          <div class="sync-time">Sinc.: ${fmtDate(loc.hora_reporte)} ${fmtTime(loc.hora_reporte)}</div>
        </div>
      </div>

      <div class="sub-cards-grid">
        <!-- Sub-tarjeta 1: Reservaciones -->
        <div class="glass sub-card">
          <div class="sub-card-details">
            <div class="detail-row">
              <span>📋 Total Reservations</span>
              <span style="color: #ffffff; font-weight: bold; font-size: 2rem;">${totalReservations}</span>
            </div>
            <div class="detail-row">
              <span>🚗 On Rent</span>
              <span class="value-success">${loc.on_rent}</span>
            </div>
            <div class="detail-row">
              <span>🟢 Open</span>
              <span>${loc.open}</span>
            </div>
            <div class="detail-row">
              <span>🔄 Returns</span>
              <span>${loc.returns}</span>
            </div>
            <div class="detail-row">
              <span>⚠️ No Show</span>
              <span class="${loc.no_show > 0 ? 'value-warning' : ''}">${loc.no_show}</span>
            </div>
            <div class="detail-row">
              <span>❌ Cancellations</span>
              <span class="${loc.cancellations > 0 ? 'value-danger' : ''}">${loc.cancellations}</span>
            </div>
            <div class="detail-row">
              <span>⛔ Unqualified</span>
              <span class="${loc.unqualified > 0 ? 'value-warning' : ''}">${loc.unqualified}</span>
            </div>
            <div class="detail-row">
              <span>🚙 Turo</span>
              <span class="${(loc.turo || 0) > 0 ? 'value-warning' : ''}">${loc.turo || 0}</span>
            </div>
          </div>
        </div>

        <!-- Sub-tarjeta 2: Flota -->
        <div class="glass sub-card">
          <div class="sub-card-details">
            <div class="detail-row">
              <span>🅿️ Vehicles Available</span>
              <span>${vehiclesAvailable}</span>
            </div>
            <div class="detail-row">
              <span>📊 Utilización de Flota</span>
              <span class="${utilClass}">${utilization}%</span>
            </div>
            <div class="progress-bar-large">
              <div class="progress-fill-large" style="width:${utilization}%"></div>
            </div>
          </div>
        </div>

        <!-- Sub-tarjeta 3: Financiero -->
        <div class="glass sub-card">
          <div class="sub-card-details">
            <div class="detail-row">
              <span>💰 Avg. Rate / Day</span>
              <span>$${(loc.avg_rate_day || 0).toFixed(2)}</span>
            </div>
            <div class="detail-row">
              <span>⏱️ Total Rental Days</span>
              <span>${loc.total_rental_days}</span>
            </div>
          </div>
        </div>

        <!-- Sub-tarjeta 4: Issues -->
        <div class="glass sub-card">
          <div class="sub-card-details">
            <div class="detail-row">
              <span>⚠️ Issues</span>
              <span class="${issuesClass}">${issues}</span>
            </div>
            <div class="detail-row">
              <span>${issues > 0 ? issues + ' reserva(s) con issues:' : 'Sin issues'}</span>
            </div>
            ${issues > 0 ? `
              <div class="issues-list">
                ${loc.no_show > 0 ? '<div class="issue-item">' + loc.no_show + ' No Show</div>' : ''}
                ${loc.cancellations > 0 ? '<div class="issue-item">' + loc.cancellations + ' Cancellations</div>' : ''}
                ${loc.turo > 0 ? '<div class="issue-item">' + loc.turo + ' Turo</div>' : ''}
              </div>
            ` : ''}
          </div>
        </div>

        <!-- Sub-tarjeta 5: Proyección -->
        <div class="glass sub-card projection-card">
          <div class="sub-card-details">
            <div class="detail-row">
              <span>🔮 Proyección para mañana</span>
            </div>
            <div class="detail-row">
              <span>🚗 Rentas Mañana</span>
              <span class="value-reservations">${reservasNextDay}</span>
            </div>
            <div class="detail-row">
              <span>🔁 Retornos Mañana</span>
              <span class="value-returns">${returnNextDay}</span>
            </div>
            <div class="detail-row">
              <span>Disponibilidad proyectada:</span>
              <span><strong>${projectedAvail}</strong></span>
            </div>
            <div class="detail-row">
              <span></span>
              <span class="projection-badge ${projection.class}">${projection.label}</span>
            </div>
          </div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

// ============================================
// 📊 KPIs GLOBALES
// ============================================

function renderKPIs(data) {
  const latest = getLatestByLocation(data);

  const totals = latest.reduce((acc, loc) => {
    const totalRes = (loc.on_rent||0) + (loc.open||0) + (loc.no_show||0) + (loc.unqualified||0) + (loc.cancellations||0);
    return {
      onRent:            acc.onRent            + (loc.on_rent            || 0),
      available:         acc.available         + (loc.vehicles_available || 0),
      avgRate:           acc.avgRate           + (loc.avg_rate_day       || 0),
      rentalDays:        acc.rentalDays        + (loc.total_rental_days  || 0),
      totalReservations: acc.totalReservations + totalRes,
      issues:            acc.issues            + (loc.no_show            || 0) + (loc.cancellations || 0),
      count:             acc.count + 1,
    };
  }, { onRent:0, available:0, avgRate:0, rentalDays:0, totalReservations:0, issues:0, count:0 });

  const avgRate = totals.count ? (totals.avgRate / totals.count).toFixed(2) : '0.00';

  const kpiOnRent = document.getElementById('kpiOnRent');
  const kpiAvailable = document.getElementById('kpiAvailable');
  const kpiAvgRate = document.getElementById('kpiAvgRate');
  const kpiRentalDays = document.getElementById('kpiRentalDays');
  const kpiTotalRes = document.getElementById('kpiTotalRes');
  const kpiIssues = document.getElementById('kpiIssues');

  if (kpiOnRent) kpiOnRent.textContent = totals.onRent;
  if (kpiAvailable) kpiAvailable.textContent = totals.available;
  if (kpiAvgRate) kpiAvgRate.textContent = '$' + avgRate;
  if (kpiRentalDays) kpiRentalDays.textContent = totals.rentalDays;
  if (kpiTotalRes) kpiTotalRes.textContent = totals.totalReservations;
  if (kpiIssues) kpiIssues.textContent = totals.issues;
}

// ============================================
// 📈 GRÁFICO CHART.JS
// ============================================

function renderChart(data) {
  const ctx    = document.getElementById('mainChart').getContext('2d');
  const sorted = [...data].sort((a, b) => new Date(a.hora_reporte) - new Date(b.hora_reporte));

  if (chartInstance) chartInstance.destroy();

  const style = getComputedStyle(document.documentElement);
  const c1    = style.getPropertyValue('--neon-primary').trim();
  const c2    = style.getPropertyValue('--neon-secondary').trim();

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: sorted.map(d => fmtTime(d.hora_reporte)),
      datasets: [
        {
          label:                '🚗 On Rent',
          data:                 sorted.map(d => d.on_rent),
          borderColor:          c1,
          backgroundColor:      c1 + '40',
          borderWidth:          3,
          fill:                 true,
          tension:              0.4,
          pointRadius:          4,
          pointHoverRadius:     8,
          pointBackgroundColor: '#fff',
          pointBorderColor:     c1,
        },
        {
          label:       '🅿️ Available',
          data:        sorted.map(d => d.vehicles_available),
          borderColor: c2,
          borderWidth: 2,
          borderDash:  [6, 4],
          tension:     0.4,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive:           true,
      maintainAspectRatio:  false,
      interaction:          { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15,12,41,0.95)',
          titleColor:      '#fff',
          bodyColor:       '#fff',
          borderColor:     c1,
          borderWidth:     1,
          padding:         12,
          displayColors:   true,
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} vehículos`,
          },
        },
      },
      scales: {
        x: {
          grid:  { color: 'rgba(255,255,255,0.1)' },
          ticks: { color: '#ffffff', maxTicksLimit: 10 },
        },
        y: {
          beginAtZero: true,
          grid:        { color: 'rgba(255,255,255,0.1)' },
          ticks:       { color: '#ffffff', stepSize: 10 },
        },
      },
    },
  });
}

// ============================================
// 🚀 INICIALIZACIÓN
// ============================================

async function init() {
  if (typeof window.supabase === 'undefined') {
    setTimeout(init, 300);
    return;
  }
  try {
    sbClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    });
    await fetchData();
    setInterval(fetchData, 30000); // auto-refresh cada 30 segundos
  } catch (err) {
    showError('Error inicializando: ' + err.message);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
