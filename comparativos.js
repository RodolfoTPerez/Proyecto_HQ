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
          if (dataset.backgroundColor && !dataset.backgroundColor.includes('rgba')) {
            dataset.backgroundColor = style.getPropertyValue(colorVar).trim() + '70';
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
// 📡 CARGA DE DATOS
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
  renderOnRentChart(data);
  renderUtilizationChart(data);
  renderRevenueChart(data);
  renderIssuesChart(data);
  renderAvgRateChart(data);
  renderRadarChart(data);
  renderScatterChart(data);
  renderReturnsChart(data);
  renderCompositionChart(data);
  renderRankingRevenueChart(data);
  renderRankingUtilChart(data);
  renderAvailabilityChart(data);
}

// ============================================
// 🔧 UTILIDAD
// ============================================

function getLatestByLocation(data) {
  const map = {};
  data.forEach(row => { if (!map[row.location]) map[row.location] = row; });
  return Object.values(map);
}

function getChartColors() {
  const style = getComputedStyle(document.documentElement);
  return {
    primary: style.getPropertyValue('--neon-primary').trim(),
    secondary: style.getPropertyValue('--neon-secondary').trim(),
    success: style.getPropertyValue('--neon-success').trim(),
    warning: style.getPropertyValue('--neon-warning').trim(),
    danger: style.getPropertyValue('--neon-danger').trim(),
    accent: style.getPropertyValue('--neon-accent').trim()
  };
}

function getCommonOptions() {
  return {
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
        formatter: (value) => {
          if (Number.isInteger(value)) {
            return Math.round(value);
          } else {
            return Number(value).toFixed(2);
          }
        }
      },
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(15, 12, 41, 0.95)',
        titleColor: '#fff',
        bodyColor: '#fff',
        borderWidth: 1,
        padding: 8,
        titleFont: { size: 11 },
        bodyFont: { size: 10 }
      }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: '#ffffff', font: { size: 9 }, maxRotation: 45, minRotation: 45 }
      },
      y: {
        beginAtZero: true,
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: '#ffffff', font: { size: 9 } }
      }
    }
  };
}

// ============================================
// 📊 1. ON RENT POR UBICACIÓN
// ============================================

function renderOnRentChart(data) {
  const ctx = document.getElementById('onRentChart').getContext('2d');
  if (charts.onRent) charts.onRent.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  charts.onRent = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: latest.map(d => d.location),
      datasets: [{
        data: latest.map(d => d.on_rent || 0),
        backgroundColor: colors.primary + '70',
        borderColor: colors.primary,
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      ...getCommonOptions(),
      plugins: {
        ...getCommonOptions().plugins,
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `${ctx.parsed.y} vehículos` }
        }
      }
    }
  });
}

// ============================================
// 📊 2. UTILIZACIÓN % POR UBICACIÓN
// ============================================

function renderUtilizationChart(data) {
  const ctx = document.getElementById('utilizationChart').getContext('2d');
  if (charts.utilization) charts.utilization.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const utilizationData = latest.map(loc => {
    const total = (loc.on_rent || 0) + (loc.vehicles_available || 0);
    return total > 0 ? ((loc.on_rent || 0) / total) * 100 : 0;
  });
  
  charts.utilization = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: latest.map(d => d.location),
      datasets: [{
        data: utilizationData,
        backgroundColor: utilizationData.map(v => v >= 80 ? colors.success + '70' : v >= 50 ? colors.warning + '70' : colors.danger + '70'),
        borderColor: utilizationData.map(v => v >= 80 ? colors.success : v >= 50 ? colors.warning : colors.danger),
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      ...getCommonOptions(),
      scales: {
        ...getCommonOptions().scales,
        y: { ...getCommonOptions().scales.y, max: 100, ticks: { ...getCommonOptions().scales.y.ticks, callback: v => v + '%' } }
      },
      plugins: {
        ...getCommonOptions().plugins,
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `${ctx.parsed.y.toFixed(1)}% utilización` }
        }
      }
    }
  });
}

// ============================================
// 📊 3. REVENUE POR UBICACIÓN
// ============================================

function renderRevenueChart(data) {
  const ctx = document.getElementById('revenueChart').getContext('2d');
  if (charts.revenue) charts.revenue.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const revenueData = latest.map(loc => (loc.total_rental_days || 0) * (loc.avg_rate_day || 0));
  
  charts.revenue = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: latest.map(d => d.location),
      datasets: [{
        data: revenueData,
        backgroundColor: colors.secondary + '70',
        borderColor: colors.secondary,
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      ...getCommonOptions(),
      plugins: {
        ...getCommonOptions().plugins,
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `$${ctx.parsed.y.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` }
        }
      }
    }
  });
}

// ============================================
// 📊 4. ISSUES RATE POR UBICACIÓN
// ============================================

function renderIssuesChart(data) {
  const ctx = document.getElementById('issuesChart').getContext('2d');
  if (charts.issues) charts.issues.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const issuesData = latest.map(loc => {
    const totalIssues = (loc.no_show || 0) + (loc.cancellations || 0) + (loc.unqualified || 0);
    const totalRes = loc.total_reservations || 0;
    return totalRes > 0 ? (totalIssues / totalRes) * 100 : 0;
  });
  
  charts.issues = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: latest.map(d => d.location),
      datasets: [{
        data: issuesData,
        backgroundColor: issuesData.map(v => v > 15 ? colors.danger + '70' : v > 10 ? colors.warning + '70' : colors.success + '70'),
        borderColor: issuesData.map(v => v > 15 ? colors.danger : v > 10 ? colors.warning : colors.success),
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      ...getCommonOptions(),
      scales: {
        ...getCommonOptions().scales,
        y: { ...getCommonOptions().scales.y, max: 100, ticks: { ...getCommonOptions().scales.y.ticks, callback: v => v + '%' } }
      },
      plugins: {
        ...getCommonOptions().plugins,
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `${ctx.parsed.y.toFixed(1)}% issues` }
        }
      }
    }
  });
}

// ============================================
// 📊 5. AVG RATE/DAY POR UBICACIÓN
// ============================================

function renderAvgRateChart(data) {
  const ctx = document.getElementById('avgRateChart').getContext('2d');
  if (charts.avgRate) charts.avgRate.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  charts.avgRate = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: latest.map(d => d.location),
      datasets: [{
        data: latest.map(d => d.avg_rate_day || 0),
        backgroundColor: colors.accent + '70',
        borderColor: colors.accent,
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      ...getCommonOptions(),
      plugins: {
        ...getCommonOptions().plugins,
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `$${ctx.parsed.y.toFixed(2)}/día` }
        }
      }
    }
  });
}

// ============================================
// 📊 6. RADAR DE PERFORMANCE
// ============================================

function renderRadarChart(data) {
  const ctx = document.getElementById('radarChart').getContext('2d');
  if (charts.radar) charts.radar.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const metrics = ['On Rent', 'Utilización %', 'Revenue', 'Avg Rate', 'Issues Rate'];
  const datasets = latest.slice(0, 3).map((loc, i) => {
    const total = (loc.on_rent || 0) + (loc.vehicles_available || 0);
    const utilization = total > 0 ? ((loc.on_rent || 0) / total) * 100 : 0;
    const revenue = (loc.total_rental_days || 0) * (loc.avg_rate_day || 0);
    const totalIssues = (loc.no_show || 0) + (loc.cancellations || 0) + (loc.unqualified || 0);
    const totalRes = loc.total_reservations || 0;
    const issuesRate = totalRes > 0 ? (totalIssues / totalRes) * 100 : 0;
    
    const color = [colors.primary, colors.secondary, colors.accent][i];
    return {
      label: loc.location,
      data: [
        (loc.on_rent || 0) / 50 * 100,
        utilization,
        revenue / 10000 * 100,
        (loc.avg_rate_day || 0) / 50 * 100,
        100 - issuesRate
      ],
      borderColor: color,
      backgroundColor: color + '30',
      borderWidth: 2,
      pointBackgroundColor: color
    };
  });
  
  charts.radar = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: metrics,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { 
          display: true, 
          position: 'bottom',
          labels: { color: 'var(--text-muted)', font: { size: 9 }, usePointStyle: true }
        }
      },
      scales: {
        r: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255,255,255,0.1)' },
          angleLines: { color: 'rgba(255,255,255,0.1)' },
          pointLabels: { color: 'var(--text-muted)', font: { size: 9 } },
          ticks: { display: false }
        }
      }
    }
  });
}

// ============================================
// 📊 7. SCATTER: UTILIZACIÓN VS REVENUE
// ============================================

function renderScatterChart(data) {
  const ctx = document.getElementById('scatterChart').getContext('2d');
  if (charts.scatter) charts.scatter.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const scatterData = latest.map(loc => {
    const total = (loc.on_rent || 0) + (loc.vehicles_available || 0);
    const utilization = total > 0 ? ((loc.on_rent || 0) / total) * 100 : 0;
    const revenue = (loc.total_rental_days || 0) * (loc.avg_rate_day || 0);
    return { x: utilization, y: revenue, location: loc.location };
  });
  
  charts.scatter = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [{
        data: scatterData,
        backgroundColor: colors.primary + '80',
        borderColor: colors.primary,
        borderWidth: 2,
        pointRadius: 8,
        pointHoverRadius: 12
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15, 12, 41, 0.95)',
          titleColor: '#fff',
          bodyColor: '#fff',
          borderWidth: 1,
          padding: 8,
          callbacks: {
            label: ctx => `${ctx.raw.location}: ${ctx.parsed.x.toFixed(1)}% util, $${ctx.parsed.y.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: 'Utilización %', color: '#ffffff', font: { size: 9 } },
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 9 } }
        },
        y: {
          title: { display: true, text: 'Revenue ($)', color: '#ffffff', font: { size: 9 } },
          grid: { color: 'rgba(255,255,255,0.05)' },
          ticks: { color: '#ffffff', font: { size: 9 } }
        }
      }
    }
  });
}

// ============================================
// 📊 8. RETURNS VS ON RENT
// ============================================

function renderReturnsChart(data) {
  const ctx = document.getElementById('returnsChart').getContext('2d');
  if (charts.returns) charts.returns.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  charts.returns = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: latest.map(d => d.location),
      datasets: [
        {
          label: 'On Rent',
          data: latest.map(d => d.on_rent || 0),
          backgroundColor: colors.primary + '70',
          borderColor: colors.primary,
          borderWidth: 1.5,
          borderRadius: 4
        },
        {
          label: 'Returns',
          data: latest.map(d => d.returns || 0),
          backgroundColor: colors.secondary + '70',
          borderColor: colors.secondary,
          borderWidth: 1.5,
          borderRadius: 4
        }
      ]
    },
    options: {
      ...getCommonOptions(),
      plugins: {
        legend: { 
          display: true, 
          position: 'bottom',
          labels: { color: 'var(--text-muted)', font: { size: 9 }, usePointStyle: true }
        },
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}` }
        }
      }
    }
  });
}

// ============================================
// 📊 9. COMPOSICIÓN DE RESERVAS
// ============================================

function renderCompositionChart(data) {
  const ctx = document.getElementById('compositionChart').getContext('2d');
  if (charts.composition) charts.composition.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  charts.composition = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: latest.map(d => d.location),
      datasets: [
        {
          label: 'On Rent',
          data: latest.map(d => d.on_rent || 0),
          backgroundColor: colors.primary + '80',
          borderWidth: 0
        },
        {
          label: 'Open',
          data: latest.map(d => d.open || 0),
          backgroundColor: colors.success + '80',
          borderWidth: 0
        },
        {
          label: 'No Show',
          data: latest.map(d => d.no_show || 0),
          backgroundColor: colors.warning + '80',
          borderWidth: 0
        },
        {
          label: 'Cancellations',
          data: latest.map(d => d.cancellations || 0),
          backgroundColor: colors.danger + '80',
          borderWidth: 0
        }
      ]
    },
    options: {
      ...getCommonOptions(),
      scales: {
        x: { ...getCommonOptions().scales.x, stacked: true },
        y: { ...getCommonOptions().scales.y, stacked: true }
      },
      plugins: {
        legend: { 
          display: true, 
          position: 'bottom',
          labels: { color: 'var(--text-muted)', font: { size: 8 }, usePointStyle: true }
        },
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y}` }
        }
      }
    }
  });
}

// ============================================
// 📊 10. RANKING REVENUE
// ============================================

function renderRankingRevenueChart(data) {
  const ctx = document.getElementById('rankingRevenueChart').getContext('2d');
  if (charts.rankingRevenue) charts.rankingRevenue.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const revenueData = latest.map(loc => ({
    location: loc.location,
    revenue: (loc.total_rental_days || 0) * (loc.avg_rate_day || 0)
  })).sort((a, b) => b.revenue - a.revenue);
  
  charts.rankingRevenue = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: revenueData.map(d => d.location),
      datasets: [{
        data: revenueData.map(d => d.revenue),
        backgroundColor: colors.secondary + '70',
        borderColor: colors.secondary,
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      ...getCommonOptions(),
      indexAxis: 'y',
      plugins: {
        ...getCommonOptions().plugins,
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `$${ctx.parsed.x.toLocaleString('en-US', { maximumFractionDigits: 0 })}` }
        }
      }
    }
  });
}

// ============================================
// 📊 11. RANKING UTILIZACIÓN
// ============================================

function renderRankingUtilChart(data) {
  const ctx = document.getElementById('rankingUtilChart').getContext('2d');
  if (charts.rankingUtil) charts.rankingUtil.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const utilData = latest.map(loc => {
    const total = (loc.on_rent || 0) + (loc.vehicles_available || 0);
    return {
      location: loc.location,
      utilization: total > 0 ? ((loc.on_rent || 0) / total) * 100 : 0
    };
  }).sort((a, b) => b.utilization - a.utilization);
  
  charts.rankingUtil = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: utilData.map(d => d.location),
      datasets: [{
        data: utilData.map(d => d.utilization),
        backgroundColor: utilData.map(d => d.utilization >= 80 ? colors.success + '70' : d.utilization >= 50 ? colors.warning + '70' : colors.danger + '70'),
        borderColor: utilData.map(d => d.utilization >= 80 ? colors.success : d.utilization >= 50 ? colors.warning : colors.danger),
        borderWidth: 1.5,
        borderRadius: 4
      }]
    },
    options: {
      ...getCommonOptions(),
      indexAxis: 'y',
      scales: {
        x: { ...getCommonOptions().scales.x, max: 100, ticks: { ...getCommonOptions().scales.x.ticks, callback: v => v + '%' } }
      },
      plugins: {
        ...getCommonOptions().plugins,
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `${ctx.parsed.x.toFixed(1)}%` }
        }
      }
    }
  });
}

// ============================================
// 📊 12. DISPONIBILIDAD HOY VS MAÑANA
// ============================================

function renderAvailabilityChart(data) {
  const ctx = document.getElementById('availabilityChart').getContext('2d');
  if (charts.availability) charts.availability.destroy();
  
  const latest = getLatestByLocation(data);
  const colors = getChartColors();
  
  const projectedData = latest.map(loc => {
    const projected = (loc.vehicles_available || 0) + (loc.return_next_day || 0) - (loc.reservas_next_day || 0);
    return {
      location: loc.location,
      current: loc.vehicles_available || 0,
      projected: projected
    };
  });
  
  charts.availability = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: projectedData.map(d => d.location),
      datasets: [
        {
          label: 'Hoy',
          data: projectedData.map(d => d.current),
          backgroundColor: colors.primary + '70',
          borderColor: colors.primary,
          borderWidth: 1.5,
          borderRadius: 4
        },
        {
          label: 'Mañana',
          data: projectedData.map(d => d.projected),
          backgroundColor: colors.secondary + '70',
          borderColor: colors.secondary,
          borderWidth: 1.5,
          borderRadius: 4
        }
      ]
    },
    options: {
      ...getCommonOptions(),
      plugins: {
        legend: { 
          display: true, 
          position: 'bottom',
          labels: { color: 'var(--text-muted)', font: { size: 9 }, usePointStyle: true }
        },
        tooltip: {
          ...getCommonOptions().plugins.tooltip,
          callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y} vehículos` }
        }
      }
    }
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
