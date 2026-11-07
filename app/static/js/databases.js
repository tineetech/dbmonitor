(function () {
  'use strict';
  var dbm = window.DBM;
  var state = { page: 1, perPage: 10, search: '', sort: 'total_size', order: 'desc', totalPages: 1 };

  function $(id) { return document.getElementById(id); }

  async function loadDatabases() {
    $('databases-loading').classList.remove('hidden');
    $('databases-empty').classList.add('hidden');
    var params = new URLSearchParams({
      page: String(state.page),
      per_page: String(state.perPage),
      sort: state.sort,
      order: state.order,
    });
    if (state.search) params.set('search', state.search);
    try {
      var data = await dbm.api('/api/v1/databases?' + params.toString());
      renderRows(data);
    } catch (err) {
      dbm.toast('Gagal memuat daftar database: ' + err.message, 'error');
      $('databases-loading').classList.add('hidden');
    }
  }

  function renderRows(data) {
    state.totalPages = data.total_pages || 1;
    $('db-total').textContent = dbm.formatNumber(data.total || 0);
    $('page-info').textContent = 'Halaman ' + state.page + ' / ' + state.totalPages;
    $('prev-page').disabled = state.page <= 1;
    $('next-page').disabled = state.page >= state.totalPages;
    $('databases-loading').classList.add('hidden');

    var tbody = $('database-rows');
    var rows = data.databases || [];
    if (!rows.length) {
      tbody.innerHTML = '';
      $('databases-empty').classList.remove('hidden');
      return;
    }
    tbody.innerHTML = rows.map(function (db) {
      return '<tr class="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">'
        + '<td class="py-3 pl-4 pr-4"><a class="font-medium text-navy-800 dark:text-slate-100 hover:text-accent" href="/databases/' + encodeURIComponent(db.name) + '">' + dbm.escapeHtml(db.name) + '</a></td>'
        + '<td class="py-3 pr-4 text-right">' + dbm.formatNumber(db.table_count) + '</td>'
        + '<td class="py-3 pr-4 text-right">' + dbm.formatBytes(db.data_length) + '</td>'
        + '<td class="py-3 pr-4 text-right">' + dbm.formatBytes(db.index_length) + '</td>'
        + '<td class="py-3 pr-4 text-right font-medium">' + dbm.formatBytes(db.total_size) + '</td>'
        + '<td class="py-3 pr-4 text-xs text-slate-500">' + dbm.escapeHtml(db.charset || '-') + '</td>'
        + '<td class="py-3 pr-4 text-right whitespace-nowrap"><a class="inline-flex rounded-md border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs hover:border-accent hover:text-accent" href="/databases/' + encodeURIComponent(db.name) + '">Detail</a> '
        + '<button type="button" class="backup-btn inline-flex rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600" data-db="' + dbm.escapeHtml(db.name) + '">Backup</button></td>'
        + '</tr>';
    }).join('');

    tbody.querySelectorAll('.backup-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { startBackup(btn.getAttribute('data-db')); });
    });
  }

  async function startBackup(databaseName) {
    var confirmed = await dbm.confirm({
      icon: 'question',
      title: 'Buat backup sekarang?',
      text: 'Backup database "' + databaseName + '" berjalan di background worker; file .sql disimpan di server dan bisa diunduh lagi dari Backup Manager.',
      confirmText: 'Ya, backup',
    });
    if (!confirmed) return;
    try {
      var created = await dbm.api('/api/v1/backups', { method: 'POST', body: { database_name: databaseName } });
      dbm.toast('Job backup #' + created.job_id + ' dibuat untuk ' + databaseName, 'info');
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
          dbm.toast('Backup masih berjalan. Pantau di halaman Backup Manager.', 'info');
        }
      } catch (err) {
        window.clearInterval(timer);
        dbm.toast('Gagal memantau job: ' + err.message, 'error');
      }
    }, 2000);
  }

  var searchTimer = null;
  document.addEventListener('DOMContentLoaded', function () {
    $('db-search').addEventListener('input', function (event) {
      state.search = event.target.value.trim();
      state.page = 1;
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(loadDatabases, 300);
    });
    $('prev-page').addEventListener('click', function () { if (state.page > 1) { state.page -= 1; loadDatabases(); } });
    $('next-page').addEventListener('click', function () { if (state.page < state.totalPages) { state.page += 1; loadDatabases(); } });
    document.querySelectorAll('[data-sort]').forEach(function (th) {
      th.addEventListener('click', function () {
        var sort = th.getAttribute('data-sort');
        if (state.sort === sort) {
          state.order = state.order === 'desc' ? 'asc' : 'desc';
        } else {
          state.sort = sort;
          state.order = 'desc';
        }
        loadDatabases();
      });
    });
    loadDatabases();
  });
})();
