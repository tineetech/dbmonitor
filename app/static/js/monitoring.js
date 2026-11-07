(function () {
  'use strict';
  var dbm = window.DBM;
  var growthChart = null;
  var hostChart = null;

  function $(id) { return document.getElementById(id); }

  async function loadStorage() {
    try {
      var data = await dbm.api('/api/v1/monitoring/storage');
      $('storage-loading').classList.add('hidden');
      $('storage-content').classList.remove('hidden');
      var disk = data.disk || {};
      var percent = Number(disk.percent || 0);
      $('st-percent').textContent = percent.toFixed(1) + '%';
      $('st-total').textContent = dbm.formatBytes(disk.total);
      $('st-used').textContent = dbm.formatBytes(disk.used);
      $('st-free').textContent = dbm.formatBytes(disk.free);
      var bar = $('st-bar');
      bar.style.width = Math.min(percent, 100) + '%';
      bar.className = 'h-full transition-all ' + (data.level === 'critical' ? 'bg-red-500' : data.level === 'warning' ? 'bg-amber-500' : 'bg-accent');
      var level = $('st-level');
      var label = (data.level || 'ok').toUpperCase();
      level.textContent = label;
      level.className = 'mt-1 inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium '
        + (data.level === 'critical' ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
          : data.level === 'warning' ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
          : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300');
      var bs = data.backup_storage || {};
      $('bs-size').textContent = dbm.formatBytes(bs.total_bytes);
      $('bs-count').textContent = dbm.formatNumber(bs.file_count || 0);
      $('bs-missing').textContent = dbm.formatNumber(bs.missing_files || 0);
      $('bs-dir').textContent = bs.backup_dir || '';
      var host = data.host || {};
      var ram = host.ram || {};
      var cpu = host.cpu || {};
      var ramPercent = Number(ram.percent || 0);
      $('ram-percent').textContent = ramPercent.toFixed(1) + '%';
      $('ram-total').textContent = dbm.formatBytes(ram.total);
      $('ram-used').textContent = dbm.formatBytes(ram.used);
      var ramBar = $('ram-bar');
      ramBar.style.width = Math.min(ramPercent, 100) + '%';
      ramBar.className = 'h-full transition-all ' + (ramPercent >= 85 ? 'bg-red-500' : ramPercent >= 70 ? 'bg-amber-500' : 'bg-accent');
      $('cpu-percent').textContent = Number(cpu.percent || 0).toFixed(1) + '%';
      $('cpu-count').textContent = cpu.count != null ? String(cpu.count) : '-';
      var loads = [cpu.load_avg_1m, cpu.load_avg_5m, cpu.load_avg_15m];
      $('cpu-load').textContent = loads.every(function (v) { return v == null; }) ? '-' : loads.map(function (v) { return v == null ? '-' : Number(v).toFixed(2); }).join(' / ');
      $('st-warn').textContent = data.warn_pct;
      $('st-critical').textContent = data.critical_pct;
    } catch (err) {
      $('storage-loading').classList.add('hidden');
      var box = $('monitoring-error');
      box.textContent = 'Gagal memuat storage: ' + err.message;
      box.classList.remove('hidden');
    }
  }

  async function loadGrowth() {
    try {
      var data = await dbm.api('/api/v1/monitoring/growth?limit=30');
      var series = (data.series || []).filter(function (item) { return item.points && item.points.length; });
      var empty = $('growth-empty');
      var ctx = $('chart-growth');
      if (!series.length) {
        ctx.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
      }
      ctx.classList.remove('hidden');
      empty.classList.add('hidden');

      var allLabels = [];
      series.forEach(function (item) {
        item.points.forEach(function (point) {
          var label = point.captured_at ? point.captured_at.slice(0, 16).replace('T', ' ') : '';
          if (allLabels.indexOf(label) === -1) allLabels.push(label);
        });
      });
      allLabels.sort();

      var colors = ['#2563eb', '#0ea5e9', '#14b8a6', '#f59e0b', '#ef4444', '#8b5cf6', '#10b981', '#64748b'];
      var datasets = series.slice(0, 8).map(function (item, index) {
        var map = {};
        item.points.forEach(function (point) {
          var label = point.captured_at ? point.captured_at.slice(0, 16).replace('T', ' ') : '';
          map[label] = Math.round((point.total_bytes || 0) / 1024 / 1024);
        });
        return {
          label: item.database_name,
          data: allLabels.map(function (label) { return map[label] != null ? map[label] : null; }),
          borderColor: colors[index % colors.length],
          backgroundColor: colors[index % colors.length],
          tension: 0.3,
          spanGaps: true,
        };
      });

      if (growthChart) growthChart.destroy();
      growthChart = new Chart(ctx, {
        type: 'line',
        data: { labels: allLabels.map(function (label) { return label.slice(5); }), datasets: datasets },
        options: {
          scales: { y: { beginAtZero: true, title: { display: true, text: 'Ukuran (MB)' } } },
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } },
        },
      });
    } catch (err) {
      var box = $('monitoring-error');
      box.textContent = 'Gagal memuat growth: ' + err.message;
      box.classList.remove('hidden');
    }
  }

  async function loadHostHistory() {
    try {
      var data = await dbm.api('/api/v1/monitoring/host-history?limit=168');
      var points = data.points || [];
      var empty = $('host-empty');
      var ctx = $('chart-host');
      if (!points.length) {
        ctx.classList.add('hidden');
        empty.classList.remove('hidden');
        return;
      }
      ctx.classList.remove('hidden');
      empty.classList.add('hidden');
      var labels = points.map(function (point) {
        return point.captured_at ? point.captured_at.slice(0, 16).replace('T', ' ') : '';
      });
      if (hostChart) hostChart.destroy();
      hostChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels.map(function (label) { return label.slice(5); }),
          datasets: [
            {
              label: 'RAM (%)',
              data: points.map(function (point) { return Number(point.ram_percent || 0); }),
              borderColor: '#2563eb',
              backgroundColor: '#2563eb',
              tension: 0.3,
              spanGaps: true,
            },
            {
              label: 'CPU (%)',
              data: points.map(function (point) { return Number(point.cpu_percent || 0); }),
              borderColor: '#f59e0b',
              backgroundColor: '#f59e0b',
              tension: 0.3,
              spanGaps: true,
            },
          ],
        },
        options: {
          scales: { y: { min: 0, max: 100, title: { display: true, text: '%' } } },
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } },
        },
      });
    } catch (err) {
      var box = $('monitoring-error');
      box.textContent = 'Gagal memuat host resources: ' + err.message;
      box.classList.remove('hidden');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    $('refresh-monitoring').addEventListener('click', function () { loadStorage(); loadGrowth(); loadHostHistory(); });
    $('capture-snapshot').addEventListener('click', async function () {
      try {
        var result = await dbm.api('/api/v1/monitoring/snapshot', { method: 'POST' });
        dbm.toast('Snapshot tersimpan (' + result.inserted + ' database).', 'success');
        loadGrowth();
        loadHostHistory();
      } catch (err) {
        dbm.toast('Gagal capture snapshot: ' + err.message, 'error');
      }
    });
    loadStorage();
    loadGrowth();
    loadHostHistory();
  });
})();
