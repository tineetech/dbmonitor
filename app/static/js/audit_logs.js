(function () {
  'use strict';
  var dbm = window.DBM;
  var state = { page: 1, perPage: 15, search: '', status: '', totalPages: 1 };

  function $(id) { return document.getElementById(id); }

  async function loadAudit() {
    $('audit-loading').classList.remove('hidden');
    $('audit-empty').classList.add('hidden');
    var params = new URLSearchParams({ page: String(state.page), per_page: String(state.perPage) });
    if (state.search) params.set('search', state.search);
    if (state.status) params.set('status', state.status);
    try {
      var data = await dbm.api('/api/v1/audit-logs?' + params.toString());
      state.totalPages = data.total_pages || 1;
      $('page-info').textContent = 'Halaman ' + state.page + ' / ' + state.totalPages;
      $('prev-page').disabled = state.page <= 1;
      $('next-page').disabled = state.page >= state.totalPages;
      $('audit-loading').classList.add('hidden');

      var tbody = $('audit-rows');
      var rows = data.logs || [];
      if (!rows.length) { tbody.innerHTML = ''; $('audit-empty').classList.remove('hidden'); return; }
      tbody.innerHTML = rows.map(function (log) {
        var target = log.database_name || log.filename || '-';
        return '<tr class="border-b border-slate-100 dark:border-slate-800 align-top">'
          + '<td class="py-2 pl-4 pr-4 text-xs text-slate-500 whitespace-nowrap">' + dbm.formatDateTime(log.created_at) + '</td>'
          + '<td class="py-2 pr-4">' + dbm.escapeHtml(log.actor) + '</td>'
          + '<td class="py-2 pr-4 font-mono text-xs">' + dbm.escapeHtml(log.action) + '</td>'
          + '<td class="py-2 pr-4 text-xs text-slate-500 max-w-[180px] truncate" title="' + dbm.escapeHtml(target) + '">' + dbm.escapeHtml(target) + '</td>'
          + '<td class="py-2 pr-4 text-xs text-slate-500">' + dbm.escapeHtml(log.ip_address || '-') + '</td>'
          + '<td class="py-2 pr-4">' + dbm.statusBadge(log.status) + '</td>'
          + '<td class="py-2 pr-4 text-xs text-slate-500 max-w-[280px]">' + dbm.escapeHtml(log.detail || '-') + '</td>'
          + '</tr>';
      }).join('');
    } catch (err) {
      dbm.toast('Gagal memuat audit log: ' + err.message, 'error');
      $('audit-loading').classList.add('hidden');
    }
  }

  var searchTimer = null;
  document.addEventListener('DOMContentLoaded', function () {
    $('audit-search').addEventListener('input', function (event) {
      state.search = event.target.value.trim();
      state.page = 1;
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(loadAudit, 300);
    });
    $('audit-status').addEventListener('change', function (event) { state.status = event.target.value; state.page = 1; loadAudit(); });
    $('prev-page').addEventListener('click', function () { if (state.page > 1) { state.page -= 1; loadAudit(); } });
    $('next-page').addEventListener('click', function () { if (state.page < state.totalPages) { state.page += 1; loadAudit(); } });
    loadAudit();
  });
})();
