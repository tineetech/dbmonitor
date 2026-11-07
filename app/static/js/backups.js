(function () {
  'use strict';
  var dbm = window.DBM;
  var state = { page: 1, perPage: 10, search: '', status: '', database: '', from: '', to: '', sort: 'created_at', order: 'desc', totalPages: 1 };
  var isSuperAdmin = false;

  function $(id) { return document.getElementById(id); }

  async function loadCurrentUser() {
    try {
      var me = await dbm.api('/api/v1/auth/me');
      isSuperAdmin = !!(me && me.role === 'super_admin');
    } catch (err) {
      isSuperAdmin = false;
    }
  }

  async function deleteBackup(backupId, filename) {
    var confirmed = await dbm.confirm({
      title: 'Hapus backup?',
      text: 'File "' + filename + '" akan dihapus permanen dari server beserta datanya. Tindakan ini tidak bisa dibatalkan.',
      confirmText: 'Hapus',
      danger: true,
    });
    if (!confirmed) return;
    try {
      await dbm.api('/api/v1/backups/' + backupId, { method: 'DELETE' });
      dbm.toast('Backup dihapus.', 'success');
      loadBackups();
    } catch (err) {
      dbm.toast('Gagal menghapus backup: ' + err.message, 'error');
    }
  }

  function queryString() {
    var params = new URLSearchParams({
      page: String(state.page),
      per_page: String(state.perPage),
      sort: state.sort,
      order: state.order,
    });
    if (state.search) params.set('search', state.search);
    if (state.status) params.set('status', state.status);
    if (state.database) params.set('database_name', state.database);
    if (state.from) params.set('date_from', state.from);
    if (state.to) params.set('date_to', state.to);
    return params.toString(); 
  }

  async function loadBackups() {
    $('backups-loading').classList.remove('hidden');
    $('backups-empty').classList.add('hidden');
    try {
      var data = await dbm.api('/api/v1/backups?' + queryString());
      renderRows(data);
    } catch (err) {
      dbm.toast('Gagal memuat backup: ' + err.message, 'error');
      $('backups-loading').classList.add('hidden');
    }
  }

  function renderRows(data) {
    state.totalPages = data.total_pages || 1;
    $('page-info').textContent = 'Halaman ' + state.page + ' / ' + state.totalPages;
    $('prev-page').disabled = state.page <= 1;
    $('next-page').disabled = state.page >= state.totalPages;
    $('backups-loading').classList.add('hidden');

    var tbody = $('backup-rows');
    var rows = data.backups || [];
    if (!rows.length) { tbody.innerHTML = ''; $('backups-empty').classList.remove('hidden'); return; }
    tbody.innerHTML = rows.map(function (backup) {
      var shortChecksum = backup.sha256 ? String(backup.sha256).slice(0, 12) + '…' : '-';
      return '<tr class="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">'
        + '<td class="py-3 pl-4 pr-4"><a class="font-medium text-navy-800 dark:text-slate-100 hover:text-accent break-all" title="' + dbm.escapeHtml(backup.filename) + '" href="/backups/' + backup.id + '">' + dbm.escapeHtml(backup.filename) + '</a></td>'
        + '<td class="py-3 pr-4 text-slate-600 dark:text-slate-300">' + dbm.escapeHtml(backup.database_name) + '</td>'
        + '<td class="py-3 pr-4 text-right">' + dbm.formatBytes(backup.file_size) + '</td>'
        + '<td class="py-3 pr-4 text-xs text-slate-500">' + dbm.formatDateTime(backup.created_at) + '</td>'
        + '<td class="py-3 pr-4">' + dbm.statusBadge(backup.status) + '</td>'
        + '<td class="py-3 pr-4 font-mono text-[11px] text-slate-500" title="' + dbm.escapeHtml(backup.sha256 || '') + '">' + dbm.escapeHtml(shortChecksum) + '</td>'
        + '<td class="py-3 pr-4 text-right whitespace-nowrap">'
        + '<a class="inline-flex rounded-md border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs hover:border-accent hover:text-accent mr-1" href="/backups/' + backup.id + '">Detail</a>'
        + (backup.file_exists
            ? '<a class="inline-flex rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600" href="/api/v1/backups/' + backup.id + '/download">Download</a>'
            : '<span class="inline-flex rounded-md bg-slate-200 dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-400">File hilang</span>')
        + (isSuperAdmin
            ? '<button type="button" data-delete-id="' + backup.id + '" data-filename="' + dbm.escapeHtml(backup.filename) + '" class="inline-flex rounded-md border border-red-200 dark:border-red-800 px-3 py-1.5 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 ml-1">Hapus</button>'
            : '')
        + '</td>'
        + '</tr>';
    }).join('');
  }

  async function loadDatabaseOptions() {
    try {
      var data = await dbm.api('/api/v1/databases?per_page=100&sort=name&order=asc');
      var select = $('backup-database');
      var seen = {};
      (data.databases || []).forEach(function (db) {
        if (!db || !db.name || seen[db.name]) return;
        seen[db.name] = true;
        var option = document.createElement('option');
        option.value = db.name;
        option.textContent = db.name;
        select.appendChild(option);
      });
    } catch (err) {
      /* keep only 'Semua database' when the list is unavailable */
    }
  }

  var searchTimer = null;
  document.addEventListener('DOMContentLoaded', function () {
    $('backup-search').addEventListener('input', function (event) {
      state.search = event.target.value.trim();
      state.page = 1;
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(loadBackups, 300);
    });
    $('backup-status').addEventListener('change', function (event) { state.status = event.target.value; state.page = 1; loadBackups(); });
    $('backup-database').addEventListener('change', function (event) { state.database = event.target.value; state.page = 1; loadBackups(); });
    $('backup-from').addEventListener('change', function (event) { state.from = event.target.value; state.page = 1; loadBackups(); });
    $('backup-to').addEventListener('change', function (event) { state.to = event.target.value; state.page = 1; loadBackups(); });
    $('prev-page').addEventListener('click', function () { if (state.page > 1) { state.page -= 1; loadBackups(); } });
    $('next-page').addEventListener('click', function () { if (state.page < state.totalPages) { state.page += 1; loadBackups(); } });
    document.querySelectorAll('[data-sort]').forEach(function (th) {
      th.addEventListener('click', function () {
        var sort = th.getAttribute('data-sort');
        if (state.sort === sort) {
          state.order = state.order === 'desc' ? 'asc' : 'desc';
        } else {
          state.sort = sort;
          state.order = 'desc';
        }
        loadBackups();
      });
    });
    $('backup-rows').addEventListener('click', function (event) {
      var button = event.target.closest('[data-delete-id]');
      if (!button) return;
      deleteBackup(button.getAttribute('data-delete-id'), button.getAttribute('data-filename'));
    });
    loadDatabaseOptions();
    loadCurrentUser().then(loadBackups);
  });
})();
