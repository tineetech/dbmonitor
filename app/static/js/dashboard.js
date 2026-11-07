(function () {
  'use strict';
  var dbm = window.DBM;
  var state = { dbChart: null, activityChart: null };

  function $(id) { return document.getElementById(id); }

  async function loadDashboard() {
    try {
      var data = await dbm.api('/api/v1/dashboard/overview');
      render(data);
    } catch (err) {
      var box = $('dashboard-error');
      box.textContent = 'Gagal memuat dashboard: ' + err.message;
      box.classList.remove('hidden');
      $('dashboard-loading').classList.add('hidden');
    }
  }

  function render(data) {
    var totals = data.totals || {};
    $('dashboard-loading').classList.add('hidden');
    $('dashboard-content').classList.remove('hidden');

    $('stat-databases').textContent = dbm.formatNumber(totals.databases);
    $('stat-tables').textContent = dbm.formatNumber(totals.tables);
    $('stat-dbsize').textContent = 'Estimasi ' + dbm.formatBytes(totals.database_bytes);
    $('stat-backups').textContent = dbm.formatNumber(totals.backup_files);
    $('stat-backupsize').textContent = dbm.formatBytes(totals.backup_bytes) + ' total';

    var storage = data.storage || {};
    var disk = storage.disk || {};
    var percent = Number(disk.percent || 0);
    $('stat-disk').textContent = percent.toFixed(1) + '%';
    $('stat-diskdetail').textContent = dbm.formatBytes(disk.used) + ' terpakai dari ' + dbm.formatBytes(disk.total);
    $('storage-percent').textContent = percent.toFixed(1) + '%';
    var bar = $('storage-bar');
    bar.style.width = Math.min(percent, 100) + '%';
    bar.className = 'h-full transition-all ' + (storage.level === 'critical' ? 'bg-red-500' : storage.level === 'warning' ? 'bg-amber-500' : 'bg-accent');
    $('storage-detail').textContent = 'Bebas ' + dbm.formatBytes(disk.free) + ' · tingkat: ' + (storage.level || 'ok');

    var bs = storage.backup_storage || {};
    $('backup-storage-size').textContent = dbm.formatBytes(bs.total_bytes);
    $('backup-storage-count').textContent = dbm.formatNumber(bs.file_count || 0);
    $('last-backup-name').textContent = (data.last_backup && data.last_backup.filename) ? data.last_backup.filename : 'Belum ada backup';
    $('last-backup-name').title = (data.last_backup && data.last_backup.filename) ? data.last_backup.filename : '';

    renderJobs(data.recent_jobs || []);
    renderAudit(data.recent_audit || []);
    renderDbChart(data.databases || []);
    renderActivityChart(data.backup_activity || []);
  }

  function renderJobs(jobs) {
    var tbody = $('recent-jobs');
    var empty = $('recent-jobs-empty');
    if (!jobs.length) { empty.classList.remove('hidden'); tbody.innerHTML = ''; return; }
    empty.classList.add('hidden');
    tbody.innerHTML = jobs.map(function (job) {
      return '<tr class="border-b border-slate-100 dark:border-slate-800">'
        + '<td class="py-2 pr-4 font-medium text-slate-700 dark:text-slate-200">' + dbm.escapeHtml(job.database_name) + '</td>'
        + '<td class="py-2 pr-4">' + dbm.statusBadge(job.status) + '</td>'
        + '<td class="py-2 pr-4 text-slate-500 dark:text-slate-400">' + dbm.escapeHtml(job.requested_by) + '</td>'
        + '<td class="py-2 text-slate-500 dark:text-slate-400">' + dbm.formatDateTime(job.created_at) + '</td>'
        + '</tr>';
    }).join('');
  }

  function renderAudit(entries) {
    var list = $('recent-audit');
    if (!entries.length) { list.innerHTML = '<li class="text-slate-400">Belum ada aktivitas.</li>'; return; }
    list.innerHTML = entries.map(function (entry) {
      return '<li class="flex items-center justify-between gap-2">'
        + '<span class="text-slate-600 dark:text-slate-300 truncate">' + dbm.escapeHtml(entry.action) + ' · ' + dbm.escapeHtml(entry.actor) + '</span>'
        + '<span class="text-slate-400 whitespace-nowrap">' + dbm.formatDateTime(entry.created_at) + '</span>'
        + '</li>';
    }).join('');
  }

  function renderDbChart(databases) {
    var ctx = $('chart-databases');
    var empty = $('chart-empty');
    var top = databases.slice(0, 8);
    if (!top.length) { ctx.classList.add('hidden'); empty.classList.remove('hidden'); return; }
    ctx.classList.remove('hidden');
    empty.classList.add('hidden');
    var labels = top.map(function (item) { return item.name; });
    var values = top.map(function (item) { return Math.round((item.total_size || 0) / 1024 / 1024); });
    if (state.dbChart) state.dbChart.destroy();
    state.dbChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: ['#2563eb', '#0ea5e9', '#14b8a6', '#f59e0b', '#ef4444', '#8b5cf6', '#10b981', '#64748b'],
        }],
      },
      options: {
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } } },
      },
    });
  }

  function renderActivityChart(activity) {
    var ctx = $('chart-activity');
    var labels = activity.map(function (point) { return point.date.slice(5); });
    var values = activity.map(function (point) { return point.count; });
    if (state.activityChart) state.activityChart.destroy();
    state.activityChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Backup sukses',
          data: values,
          backgroundColor: '#2563eb',
          borderRadius: 4,
        }],
      },
      options: {
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 1, precision: 0 } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  async function loadQuickDatabases() {
    var select = $('quick-db');
    var button = $('quick-backup-btn');
    if (!select || !button) return;
    try {
      var data = await dbm.api('/api/v1/databases?per_page=100&sort=name&order=asc');
      var options = (data.databases || []).map(function (db) {
        return '<option value="' + dbm.escapeHtml(db.name) + '">' + dbm.escapeHtml(db.name) + ' · ' + dbm.formatBytes(db.total_size) + '</option>';
      });
      select.innerHTML = options.length ? options.join('') : '<option value="">Tidak ada database</option>';
      button.disabled = !options.length;
    } catch (err) {
      select.innerHTML = '<option value="">Gagal memuat database</option>';
      button.disabled = true;
    }
  }

  function setQuickStatus(message, tone) {
    var el = $('quick-status');
    if (!el) return;
    el.textContent = message;
    el.className = 'mt-2 text-xs ' + (tone === 'error' ? 'text-red-500' : tone === 'success' ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400');
  }

  async function startQuickBackup() {
    var select = $('quick-db');
    var button = $('quick-backup-btn');
    var databaseName = select ? select.value : '';
    if (!databaseName) return;
    var confirmed = await dbm.confirm({
      icon: 'question',
      title: 'Buat backup sekarang?',
      text: 'Backup database "' + databaseName + '" akan dibuat dan langsung diunduh. File sementara di server dihapus otomatis setelah download selesai.',
      confirmText: 'Ya, backup',
    });
    if (!confirmed) return;
    button.disabled = true;
    select.disabled = true;
    setQuickStatus('Membuat job backup untuk ' + databaseName + '');
    try {
      var created = await dbm.api('/api/v1/backups', { method: 'POST', body: { database_name: databaseName, ephemeral: true } });
      setQuickStatus('Backup berjalan (job #' + created.job_id + ')');
      pollQuickJob(created.job_id, databaseName);
    } catch (err) {
      setQuickStatus('Gagal membuat job backup: ' + err.message, 'error');
      button.disabled = false;
      select.disabled = false;
    }
  }

  function pollQuickJob(jobId, databaseName) {
    var button = $('quick-backup-btn');
    var select = $('quick-db');
    var attempts = 0;
    var timer = window.setInterval(async function () {
      attempts += 1;
      try {
        var job = await dbm.api('/api/v1/backups/jobs/' + jobId);
        if (job.status === 'success') {
          window.clearInterval(timer);
          setQuickStatus('Backup berhasil: ' + (job.filename || '') + ' — download dimulai; file akan dihapus dari server setelah terkirim.', 'success');
          dbm.toast('Backup berhasil: ' + (job.filename || ''), 'success');
          if (job.download_url) window.location.href = job.download_url;
          button.disabled = false;
          select.disabled = false;
        } else if (job.status === 'failed' || job.status === 'cancelled') {
          window.clearInterval(timer);
          setQuickStatus('Backup gagal: ' + (job.error || 'unknown error'), 'error');
          dbm.toast('Backup gagal: ' + (job.error || 'unknown error'), 'error');
          button.disabled = false;
          select.disabled = false;
        } else if (attempts > 900) {
          window.clearInterval(timer);
          setQuickStatus('Backup masih berjalan (job #' + jobId + '). Pantau di Backup Manager.', 'info');
          button.disabled = false;
          select.disabled = false;
        } else {
          setQuickStatus('Backup ' + databaseName + ' berjalan (job #' + jobId + ', status: ' + job.status + ')');
        }
      } catch (err) {
        window.clearInterval(timer);
        setQuickStatus('Gagal memantau job: ' + err.message, 'error');
        button.disabled = false;
        select.disabled = false;
      }
    }, 2000);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var button = $('quick-backup-btn');
    if (button) button.addEventListener('click', startQuickBackup);
    loadDashboard();
    loadQuickDatabases();
  });
})();
