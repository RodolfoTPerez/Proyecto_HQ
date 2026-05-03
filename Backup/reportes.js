// ============================================
// 🔑 CONFIGURACIÓN SUPABASE
// ============================================
const SUPABASE_URL = 'https://xtvopaehirznzeyuanwc.supabase.co';
const SUPABASE_KEY = 'sb_publishable_LCKuoYEaj6uJ4SOTUkHKwA_CYXZYOjf';

// Register ChartDataLabels plugin
Chart.register(ChartDataLabels);

let sbClient = null;
let allData = [];
let charts = {};

// ============================================
// 📅 UTILIDADES DE FECHA Y HORA
// ============================================

function fmtTime(ts) {
  return new Date(ts).toISOString().substring(11, 16);
}

function fmtDate(ts) {
  const d = new Date(ts);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${mm}/${dd}/${d.getFullYear()}`;
}

function getHoursDiff(ts1, ts2) {
  const diff = new Date(ts1) - new Date(ts2);
  return diff / (1000 * 60 * 60);
}

// ============================================
// 🎨 MANEJO DE TEMAS
// ============================================

function setTheme(name) {
  document.documentElement.setAttribute('data-theme', name === 'cyber' ? '' : name);
  updateAllChartThemes();
}

function updateAllChartThemes() {
  Object.values(charts).forEach(chart => {
    if (chart) {
      const style = getComputedStyle(document.documentElement);
      chart.data.datasets.forEach((dataset, i) => {
        if (dataset.borderColor) {
          const colorVar = i === 0 ? '--neon-primary' : '--neon-secondary';
          dataset.borderColor = style.getPropertyValue(colorVar).trim();
          if (dataset.backgroundColor) {
            dataset.backgroundColor = style.getPropertyValue(colorVar).trim() + '40';
          }
        }
      });
      chart.update();
    }
  });
}

// ============================================
// 🔌 ESTADO DE CONEXIÓN
// ============================================

function updateStatus(status) {
  const dot = document.querySelector('.status-dot');
  const text = document.getElementById('connectionStatus');
  const states = {
    connected: { bg: 'var(--neon-success)', shadow: '0 0 12px var(--neon-success)', label: '● Conectado' },
    error: { bg: 'var(--neon-danger)', shadow: '0 0 12px var(--neon-danger)', label: '✗ Error' },
    loading: { bg: 'var(--neon-warning)', shadow: '', label: '⏳ Actualizando...' },
  };
  const s = states[status] || states.loading;
  dot.style.background = s.bg;
  dot.style.boxShadow = s.shadow;
  text.textContent = s.label;
}

function updateLastUpdate() {
  document.getElementById('lastUpdate').textContent =
    'Última actualización: ' + new Date().toLocaleTimeString('en-US', { hour12: false });
}

function showError(msg) {
  console.error('❌', msg);
  const box = document.getElementById('errorBox');
  box.style.display = 'block';
  box.textContent = '❌ ' + msg;
  updateStatus('error');
}

// ============================================
// 📡 CARGA DE DATOS DESDE SUPABASE
// ============================================

async function fetchData() {
  try {
    updateStatus('loading');
    const { data, error } = await sbClient
      .from('reportes_hq')
      .select('*')
      .order('hora_reporte', { ascending: false })
      .limit(500);

    if (error) throw error;
    if (!data || data.length === 0)
      throw new Error('La tabla reportes_hq está vacía o no tienes permisos de lectura');

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
  renderAbsorptionReport(data);
  renderUtilizationReport(data);
  renderRevenueReport(data);
  renderReservationsReturnsReport(data);
  renderIssuesRateReport(data);
  renderProjectionReport(data);
  renderRateTrendReport(data);
}

// ============================================
// 📊 REPORTE 1: VELOCIDAD DE ABSORCIÓN
// ============================================

function renderAbsorptionReport(data) {
  const container = document.getElementById('absorptionDetails');
  const locations = [...new Set(data.map(d => d.location))];
  
  const absorptionData = locations.map(loc => {
    const locData = data.filter(d => d.location === loc).sort((a, b) => new Date(a.hora_reporte) - new Date(b.hora_reporte));
    
    if (locData.length < 2) return { location: loc, rate: 0, details: 'Insuficiente datos' };
    
    const first = locData[0];
    const last = locData[locData.length - 1];
    const hoursDiff = getHoursDiff(last.hora_reporte, first.hora_reporte);
    
    if (hoursDiff <= 0) return { location: loc, rate: 0, details: 'Rango de tiempo inválido' };
    
    const openChange = (first.open || 0) - (last.open || 0);
    const rate = openChange / hoursDiff;
    
    return {
      location: loc,
      rate: rate.toFixed(2),
      firstOpen: first.open || 0,
      lastOpen: last.open || 0,
      hoursDiff: hoursDiff.toFixed(1),
      details: `${first.open || 0} → ${last.open || 0} en ${hoursDiff.toFixed(1)}h`
    };
  });

  container.innerHTML = absorptionData.map(item => `
    <div class="glass kpi-card">
      <div class="label">${item.location}</div>
      <div class="value">${item.rate} reservas/hora</div>
      <div class="desc">${item.details}</div>
    </div>
  `).join('');

  // Gráfico
  const ctx = document.getElementById('absorptionChart').getContext('2d');
  if (charts.absorption) charts.absorption.destroy();
  
  const style = getComputedStyle(document.documentElement);
  const c1 = style.getPropertyValue('--neon-primary').trim();
  
  charts.absorption = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: absorptionData.map(d => d.location),
      datasets: [{
        label: 'Reservas/Hora',
        data: absorptionData.map(d => parseFloat(d.rate)),
        backgroundColor: c1 + '70',
        borderColor: c1,
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        datalabels: {
          anchor: 'center',
          align: 'center',
          color: '#ffffff',
          font: {
            weight: 'bold',
            size: 12
          },
          formatter: (value) => Math.round(value)
        },
        legend: { display: false },
        tooltip: {
          enabled: false
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#ffffff', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 11 } }
        }
      }
    }
  });
}

// ============================================
// 📊 REPORTE 2: EFICIENCIA DE UTILIZACIÓN
// ============================================

function renderUtilizationReport(data) {
  const container = document.getElementById('utilizationDetails');
  const latest = getLatestByLocation(data);
  
  const utilizationData = latest.map(loc => {
    const totalFleet = (loc.on_rent || 0) + (loc.vehicles_available || 0);
    const utilization = totalFleet > 0 ? ((loc.on_rent || 0) / totalFleet) * 100 : 0;
    const status = utilization >= 80 ? 'success' : utilization >= 50 ? 'warning' : 'danger';
    
    return {
      location: loc.location,
      utilization: utilization.toFixed(1),
      onRent: loc.on_rent || 0,
      available: loc.vehicles_available || 0,
      totalFleet: totalFleet,
      status: status
    };
  });

  container.innerHTML = utilizationData.map(item => `
    <div class="glass kpi-card">
      <div class="label">${item.location}</div>
      <div class="value ${item.status}">${item.utilization}%</div>
      <div class="desc">${item.onRent}/${item.totalFleet} flota utilizada</div>
    </div>
  `).join('');

  // Gráfico
  const ctx = document.getElementById('utilizationChart').getContext('2d');
  if (charts.utilization) charts.utilization.destroy();
  
  const style = getComputedStyle(document.documentElement);
  const c1 = style.getPropertyValue('--neon-primary').trim();
  const c2 = style.getPropertyValue('--neon-secondary').trim();
  
  charts.utilization = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: utilizationData.map(d => d.location),
      datasets: [{
        label: 'Utilización %',
        data: utilizationData.map(d => parseFloat(d.utilization)),
        backgroundColor: utilizationData.map(d => {
          if (d.status === 'success') return 'rgba(0, 255, 157, 0.7)';
          if (d.status === 'warning') return 'rgba(255, 190, 0, 0.7)';
          return 'rgba(255, 0, 60, 0.7)';
        }),
        borderColor: utilizationData.map(d => {
          if (d.status === 'success') return 'var(--neon-success)';
          if (d.status === 'warning') return 'var(--neon-warning)';
          return 'var(--neon-danger)';
        }),
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        datalabels: {
          anchor: 'center',
          align: 'center',
          color: '#ffffff',
          font: {
            weight: 'bold',
            size: 12
          },
          formatter: (value) => Math.round(value)
        },
        legend: { display: false },
        tooltip: {
          enabled: false
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#ffffff', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 11 }, callback: v => v + '%' }
        }
      }
    }
  });
}

// ============================================
// 📊 REPORTE 3: REVENUE ESTIMADO
// ============================================

function renderRevenueReport(data) {
  const container = document.getElementById('revenueDetails');
  const latest = getLatestByLocation(data);
  
  const revenueData = latest.map(loc => {
    const revenue = (loc.total_rental_days || 0) * (loc.avg_rate_day || 0);
    return {
      location: loc.location,
      revenue: revenue.toFixed(2),
      rentalDays: loc.total_rental_days || 0,
      avgRate: loc.avg_rate_day || 0
    };
  });

  const totalRevenue = revenueData.reduce((sum, d) => sum + parseFloat(d.revenue), 0);
  const topLocation = revenueData.reduce((max, d) => parseFloat(d.revenue) > parseFloat(max.revenue) ? d : max, revenueData[0]);

  document.getElementById('totalRevenue').textContent = '$' + totalRevenue.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  document.getElementById('topRevenueLocation').textContent = topLocation ? topLocation.location : '--';

  container.innerHTML = revenueData.map(item => `
    <div class="glass kpi-card">
      <div class="label">${item.location}</div>
      <div class="value">$${parseFloat(item.revenue).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
      <div class="desc">${item.rentalDays} días × $${item.avgRate.toFixed(2)}/día</div>
    </div>
  `).join('');

  // Gráfico
  const ctx = document.getElementById('revenueChart').getContext('2d');
  if (charts.revenue) charts.revenue.destroy();
  
  const style = getComputedStyle(document.documentElement);
  const c1 = style.getPropertyValue('--neon-primary').trim();
  
  charts.revenue = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: revenueData.map(d => d.location),
      datasets: [{
        label: 'Revenue ($)',
        data: revenueData.map(d => parseFloat(d.revenue)),
        backgroundColor: c1 + '70',
        borderColor: c1,
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        datalabels: {
          anchor: 'center',
          align: 'center',
          color: '#ffffff',
          font: {
            weight: 'bold',
            size: 12
          },
          formatter: (value) => Math.round(value)
        },
        legend: { display: false },
        tooltip: {
          enabled: false
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#ffffff', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 11 }, callback: v => '$' + v.toLocaleString() }
        }
      }
    }
  });
}

// ============================================
// 📊 REPORTE 4: COMPARACIÓN RESERVAS VS RETORNOS
// ============================================

function renderReservationsReturnsReport(data) {
  const container = document.getElementById('balanceDetails');
  const latest = getLatestByLocation(data);
  
  const balanceData = latest.map(loc => {
    const balance = (loc.on_rent || 0) - (loc.returns || 0);
    const status = balance > 0 ? 'success' : balance < 0 ? 'danger' : '';
    
    return {
      location: loc.location,
      onRent: loc.on_rent || 0,
      returns: loc.returns || 0,
      balance: balance,
      status: status
    };
  });

  container.innerHTML = balanceData.map(item => `
    <div class="glass kpi-card">
      <div class="label">${item.location}</div>
      <div class="value ${item.status}">${item.balance > 0 ? '+' : ''}${item.balance}</div>
      <div class="desc">Rentas: ${item.onRent} | Retornos: ${item.returns}</div>
    </div>
  `).join('');

  // Gráfico
  const ctx = document.getElementById('reservationsReturnsChart').getContext('2d');
  if (charts.reservationsReturns) charts.reservationsReturns.destroy();
  
  const style = getComputedStyle(document.documentElement);
  const c1 = style.getPropertyValue('--neon-primary').trim();
  const c2 = style.getPropertyValue('--neon-secondary').trim();
  
  charts.reservationsReturns = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: balanceData.map(d => d.location),
      datasets: [
        {
          label: 'On Rent',
          data: balanceData.map(d => d.onRent),
          backgroundColor: c1 + '70',
          borderColor: c1,
          borderWidth: 1.5,
          borderRadius: 4,
          borderSkipped: false
        },
        {
          label: 'Returns',
          data: balanceData.map(d => d.returns),
          backgroundColor: c2 + '70',
          borderColor: c2,
          borderWidth: 1.5,
          borderRadius: 4,
          borderSkipped: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        datalabels: {
          anchor: 'center',
          align: 'center',
          color: '#ffffff',
          font: {
            weight: 'bold',
            size: 12
          },
          formatter: (value) => Math.round(value)
        },
        legend: { display: false },
        tooltip: {
          enabled: false
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#ffffff', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 11 } }
        }
      }
    }
  });
}

// ============================================
// 📊 REPORTE 5: TASA DE PROBLEMAS
// ============================================

function renderIssuesRateReport(data) {
  const container = document.getElementById('issuesDetails');
  const latest = getLatestByLocation(data);
  
  const issuesData = latest.map(loc => {
    const totalIssues = (loc.no_show || 0) + (loc.cancellations || 0) + (loc.unqualified || 0);
    const totalRes = loc.total_reservations || 0;
    const rate = totalRes > 0 ? (totalIssues / totalRes) * 100 : 0;
    const status = rate > 15 ? 'danger' : rate > 10 ? 'warning' : '';
    
    return {
      location: loc.location,
      rate: rate.toFixed(1),
      totalIssues: totalIssues,
      totalRes: totalRes,
      noShow: loc.no_show || 0,
      cancellations: loc.cancellations || 0,
      unqualified: loc.unqualified || 0,
      status: status
    };
  });

  container.innerHTML = issuesData.map(item => `
    <div class="glass kpi-card">
      <div class="label">${item.location}</div>
      <div class="value ${item.status}">${item.rate}%</div>
      <div class="desc">Issues: ${item.totalIssues}/${item.totalRes} (NS: ${item.noShow}, C: ${item.cancellations}, UQ: ${item.unqualified})</div>
    </div>
  `).join('');

  // Gráfico
  const ctx = document.getElementById('issuesRateChart').getContext('2d');
  if (charts.issuesRate) charts.issuesRate.destroy();
  
  const style = getComputedStyle(document.documentElement);
  const c1 = style.getPropertyValue('--neon-primary').trim();
  const c2 = style.getPropertyValue('--neon-danger').trim();
  
  charts.issuesRate = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: issuesData.map(d => d.location),
      datasets: [{
        label: 'Tasa de Problemas %',
        data: issuesData.map(d => parseFloat(d.rate)),
        backgroundColor: issuesData.map(d => {
          if (d.status === 'danger') return 'rgba(255, 0, 60, 0.7)';
          if (d.status === 'warning') return 'rgba(255, 190, 0, 0.7)';
          return 'rgba(0, 255, 157, 0.7)';
        }),
        borderColor: issuesData.map(d => {
          if (d.status === 'danger') return 'var(--neon-danger)';
          if (d.status === 'warning') return 'var(--neon-warning)';
          return 'var(--neon-success)';
        }),
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        datalabels: {
          anchor: 'center',
          align: 'center',
          color: '#ffffff',
          font: {
            weight: 'bold',
            size: 12
          },
          formatter: (value) => Math.round(value)
        },
        legend: { display: false },
        tooltip: {
          enabled: false
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#ffffff', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 11 }, callback: v => v + '%' }
        }
      }
    }
  });
}

// ============================================
// 📊 REPORTE 6: PROYECCIÓN DISPONIBILIDAD MAÑANA
// ============================================

function renderProjectionReport(data) {
  const container = document.getElementById('projectionDetails');
  const latest = getLatestByLocation(data);
  
  const projectionData = latest.map(loc => {
    const projected = (loc.vehicles_available || 0) + (loc.return_next_day || 0) - (loc.reservas_next_day || 0);
    const status = projected < 7 ? 'danger' : projected <= 14 ? 'warning' : projected <= 20 ? 'moderate' : 'success';
    const statusLabel = projected < 7 ? 'CRÍTICO' : projected <= 14 ? 'PRECAUCIÓN' : projected <= 20 ? 'MODERADO' : 'ÓPTIMO';
    
    return {
      location: loc.location,
      projected: projected,
      available: loc.vehicles_available || 0,
      returnsNext: loc.return_next_day || 0,
      reservasNext: loc.reservas_next_day || 0,
      status: status,
      statusLabel: statusLabel
    };
  });

  container.innerHTML = projectionData.map(item => `
    <div class="glass kpi-card">
      <div class="label">${item.location}</div>
      <div class="value ${item.status}">${item.projected}</div>
      <div class="desc">${item.statusLabel} (Disp: ${item.available} + Ret: ${item.returnsNext} - Res: ${item.reservasNext})</div>
    </div>
  `).join('');

  // Gráfico
  const ctx = document.getElementById('projectionChart').getContext('2d');
  if (charts.projection) charts.projection.destroy();
  
  const style = getComputedStyle(document.documentElement);
  const c1 = style.getPropertyValue('--neon-primary').trim();
  
  charts.projection = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: projectionData.map(d => d.location),
      datasets: [{
        label: 'Disponibilidad Proyectada',
        data: projectionData.map(d => d.projected),
        backgroundColor: projectionData.map(d => {
          if (d.status === 'danger') return 'rgba(255, 0, 60, 0.7)';
          if (d.status === 'warning') return 'rgba(255, 190, 0, 0.7)';
          if (d.status === 'moderate') return 'rgba(188, 19, 254, 0.7)';
          return 'rgba(0, 255, 157, 0.7)';
        }),
        borderColor: projectionData.map(d => {
          if (d.status === 'danger') return 'var(--neon-danger)';
          if (d.status === 'warning') return 'var(--neon-warning)';
          if (d.status === 'moderate') return 'var(--neon-secondary)';
          return 'var(--neon-success)';
        }),
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        datalabels: {
          anchor: 'center',
          align: 'center',
          color: '#ffffff',
          font: {
            weight: 'bold',
            size: 12
          },
          formatter: (value) => Math.round(value)
        },
        legend: { display: false },
        tooltip: {
          enabled: false
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#ffffff', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 11 } }
        }
      }
    }
  });
}

// ============================================
// 📊 REPORTE 7: TENDENCIA AVG_RATE_DAY
// ============================================

function renderRateTrendReport(data) {
  const container = document.getElementById('rateDetails');
  const locations = [...new Set(data.map(d => d.location))];
  
  const rateData = locations.map(loc => {
    const locData = data.filter(d => d.location === loc).sort((a, b) => new Date(a.hora_reporte) - new Date(b.hora_reporte));
    
    if (locData.length < 2) {
      return {
        location: loc,
        firstRate: 0,
        lastRate: 0,
        change: 0,
        trend: 'stable'
      };
    }
    
    const first = locData[0];
    const last = locData[locData.length - 1];
    const change = ((last.avg_rate_day || 0) - (first.avg_rate_day || 0));
    const trend = change > 0 ? 'success' : change < 0 ? 'danger' : '';
    
    return {
      location: loc,
      firstRate: first.avg_rate_day || 0,
      lastRate: last.avg_rate_day || 0,
      change: change.toFixed(2),
      trend: trend
    };
  });

  container.innerHTML = rateData.map(item => `
    <div class="glass kpi-card">
      <div class="label">${item.location}</div>
      <div class="value ${item.trend}">${item.change > 0 ? '+' : ''}$${item.change}</div>
      <div class="desc">$${item.firstRate.toFixed(2)} → $${item.lastRate.toFixed(2)}</div>
    </div>
  `).join('');

  // Gráfico de líneas por ubicación
  const ctx = document.getElementById('rateTrendChart').getContext('2d');
  if (charts.rateTrend) charts.rateTrend.destroy();
  
  const style = getComputedStyle(document.documentElement);
  const colors = [
    style.getPropertyValue('--neon-primary').trim(),
    style.getPropertyValue('--neon-secondary').trim(),
    style.getPropertyValue('--neon-success').trim(),
    style.getPropertyValue('--neon-warning').trim(),
    style.getPropertyValue('--neon-danger').trim()
  ];
  
  const datasets = locations.map((loc, i) => {
    const locData = data.filter(d => d.location === loc).sort((a, b) => new Date(a.hora_reporte) - new Date(b.hora_reporte));
    return {
      label: loc,
      data: locData.map(d => d.avg_rate_day || 0),
      borderColor: colors[i % colors.length],
      backgroundColor: colors[i % colors.length] + '20',
      borderWidth: 2,
      tension: 0.4,
      fill: false
    };
  });
  
  const allTimes = [...new Set(data.map(d => fmtTime(d.hora_reporte)))].sort();
  
  charts.rateTrend = new Chart(ctx, {
    type: 'line',
    data: {
      labels: allTimes,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { 
          display: true, 
          position: 'top',
          labels: { color: 'var(--text-muted)', font: { size: 11 }, usePointStyle: true, pointStyle: 'circle' }
        },
        tooltip: {
          backgroundColor: 'rgba(15, 12, 41, 0.95)',
          titleColor: '#fff',
          bodyColor: '#fff',
          borderWidth: 1,
          padding: 10,
          callbacks: {
            label: ctx => `${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 10 }, maxTicksLimit: 8 }
        },
        y: {
          beginAtZero: false,
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 11 }, callback: v => '$' + v.toFixed(2) }
        }
      }
    }
  });
}

// ============================================
// 🔧 UTILIDAD: OBTENER ÚLTIMO POR UBICACIÓN
// ============================================

function getLatestByLocation(data) {
  const map = {};
  data.forEach(row => { if (!map[row.location]) map[row.location] = row; });
  return Object.values(map);
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
    setInterval(fetchData, 30000);
  } catch (err) {
    showError('Error inicializando: ' + err.message);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
