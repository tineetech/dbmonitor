(function () {
  'use strict';
  var dbm = window.DBM;
  var match = window.location.pathname.match(/^\/backups\/(\d+)$/);
  var backupId = match ? Number(match[1]) : 0;

  function $(id) { return document.getElementById(id); }

  async function loadDetail() {
    try {
      var backup = await dbm.api('/api/v1/backups/' + backupId);
      $('backup-loading').classList.add('hidden');
      $('backup-content').classList.remove('hidden');
      $('detail-filename').textContent = backup.filename;
      $('detail-status').innerHTML = dbm.statusBadge(backup.status);
      $('detail-database').textContent = backup.database_name;
      $('detail-size').textContent = dbm.formatBytes(backup.file_size);
      $('detail-created').textContent = dbm.formatDateTime(backup.created_at);
      $('detail-requested').textContent = backup.requested_by || '-';
      $('detail-sha').textContent = backup.sha256 || '-';
      $('detail-exists').textContent = backup.file_exists ? 'Ya' : 'Tidak';
      $('detail-exists').className = 'mt-0.5 font-medium ' + (backup.file_exists ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400');
      var download = $('detail-download');
      if (backup.download_url) {
        download.setAttribute('href', backup.download_url);
      } else {
        download.classList.add('opacity-50', 'pointer-events-none');
      }
    } catch (err) {
      $('backup-loading').classList.add('hidden');
      var box = $('backup-error');
      box.textContent = 'Gagal memuat detail backup: ' + err.message;
      box.classList.remove('hidden');
    }
  }

  document.addEventListener('DOMContentLoaded', loadDetail);
})();
