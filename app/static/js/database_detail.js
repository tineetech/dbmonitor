(function () {
  'use strict';
  var dbm = window.DBM;
  var match = window.location.pathname.match(/^\/databases\/([^\/]+)$/);
  var dbName = match ? decodeURIComponent(match[1]) : '';
  var state = { page: 1, perPage: 10, search: '', totalPages: 1 };

  function $(id) { return document.getElementById(id); }

  async function loadDetail() {
    try {
      var detail = await dbm.api('/api/v1/databases/' + encodeURIComponent(dbName));
      $('detail-loading').classList.add('hidden');
      $('detail-content').classList.remove('hidden');
      $('db-title').textContent = detail.name;
      $('db-charset').textContent = 'Charset: ' + (detail.charset || '-') + ' · Collation: ' + (detail.collation || '-');
      $('stat-tables').textContent = dbm.formatNumber(detail.table_count);
      $('stat-data').textContent = dbm.formatBytes(detail.data_length);
      $('stat-index').textContent = dbm.formatBytes(detail.index_length);
      $('stat-total').textContent = dbm.formatBytes(detail.total_size);

      var warning = $('engine-warning');
      if (detail.has_non_transactional) {
        warning.textContent = 'Perhatian: database ini berisi tabel non-transaksional (' + detail.non_transactional_engines.join(', ') + '). Opsi --single-transaction tidak menjamin konsistensi snapshot untuk engine tersebut. Lakukan backup saat write dihentikan atau gunakan locking terkontrol.';
        warning.classList.remove('hidden');
      } else {
        warning.classList.add('hidden');
      }
    } catch (err) {
      $('detail-loading').classList.add('hidden');
      var box = $('detail-error');
      box.textContent = 'Gagal memuat detail database: ' + err.message;
      box.classList.remove('hidden');
    }
  }

  async function loadTables() {
    $('tables-loading').classList.remove('hidden');
    $('tables-empty').classList.add('hidden');
    var params = new URLSearchParams({ page: String(state.page), per_page: String(state.perPage) });
    if (state.search) params.set('search', state.search);
    try {
      var data = await dbm.api('/api/v1/databases/' + encodeURIComponent(dbName) + '/tables?' + params.toString());
      state.totalPages = data.total_pages || 1;
      $('tables-page-info').textContent = 'Halaman ' + state.page + ' / ' + state.totalPages;
      $('tables-prev').disabled = state.page <= 1;
      $('tables-next').disabled = state.page >= state.totalPages;
      $('tables-loading').classList.add('hidden');

      var tbody = $('table-rows');
      var rows = data.tables || [];
      if (!rows.length) { tbody.innerHTML = ''; $('tables-empty').classList.remove('hidden'); return; }
      tbody.innerHTML = rows.map(function (table) {
        return '<tr class="border-b border-slate-100 dark:border-slate-800">'
          + '<td class="py-2 pl-4 pr-4 font-medium">' + dbm.escapeHtml(table.table_name) + '</td>'
          + '<td class="py-2 pr-4 text-xs text-slate-500">' + dbm.escapeHtml(table.engine || '-') + '</td>'
          + '<td class="py-2 pr-4 text-right">' + (table.table_rows == null ? '-' : dbm.formatNumber(table.table_rows)) + '</td>'
          + '<td class="py-2 pr-4 text-right">' + dbm.formatBytes(table.data_length) + '</td>'
          + '<td class="py-2 pr-4 text-right">' + dbm.formatBytes(table.index_length) + '</td>'
          + '<td class="py-2 pr-4 text-right font-medium">' + dbm.formatBytes(table.total_size) + '</td>'
          + '<td class="py-2 pr-4 text-xs text-slate-500">' + dbm.escapeHtml(table.collation || '-') + '</td>'
          + '</tr>';
      }).join('');
    } catch (err) {
      $('tables-loading').classList.add('hidden');
      dbm.toast('Gagal memuat tabel: ' + err.message, 'error');
    }
  }

  async function startBackup() {
    var confirmed = await dbm.confirm({
      icon: 'question',
      title: 'Buat backup sekarang?',
      text: 'Backup database "' + dbName + '" berjalan di background worker; file .sql disimpan di server setelah terunduh.',
      confirmText: 'Ya, backup',
    });
    if (!confirmed) return;
    try {
      var created = await dbm.api('/api/v1/backups', { method: 'POST', body: { database_name: dbName } });
      dbm.toast('Job backup #' + created.job_id + ' dibuat', 'info');
      pollJob(created.job_id);
    } catch (err) {
      dbm.toast('Gagal membuat job backup: ' + err.message, 'error');
    }
  }

  function pollJob(jobId) {
    var attempts = 0;
    var timer = window.setInterval(async function () {
      attempts += 1;
      try {
        var job = await dbm.api('/api/v1/backups/jobs/' + jobId);
        if (job.status === 'success') {
          window.clearInterval(timer);
          dbm.toast('Backup berhasil: ' + (job.filename || ''), 'success');
          if (job.download_url) window.location.href = job.download_url;
        } else if (job.status === 'failed' || job.status === 'cancelled') {
          window.clearInterval(timer);
          dbm.toast('Backup gagal: ' + (job.error || 'unknown error'), 'error');
        } else if (attempts > 900) {
          window.clearInterval(timer);
          dbm.toast('Backup masih berjalan. Lihat status di Backup Manager.', 'info');
        }
      } catch (err) {
        window.clearInterval(timer);
        dbm.toast('Gagal memantau job: ' + err.message, 'error');
      }
    }, 2000);
  }

  var searchTimer = null;
  document.addEventListener('DOMContentLoaded', function () {
    $('backup-btn').addEventListener('click', startBackup);
    $('table-search').addEventListener('input', function (event) {
      state.search = event.target.value.trim();
      state.page = 1;
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(loadTables, 300);
    });
    $('tables-prev').addEventListener('click', function () { if (state.page > 1) { state.page -= 1; loadTables(); } });
    $('tables-next').addEventListener('click', function () { if (state.page < state.totalPages) { state.page += 1; loadTables(); } });
    loadDetail();
    loadTables();
  });
})();
