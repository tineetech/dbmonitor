(function () {
  'use strict';
  var dbm = window.DBM;

  function $(id) { return document.getElementById(id); }

  async function loadSettings() {
    try {
      var data = await dbm.api('/api/v1/settings');
      $('storage-warn').value = data.storage_warn_pct;
      $('storage-critical').value = data.storage_critical_pct;
      $('retention-days').value = data.retention_days;
      $('max-concurrent').value = data.max_concurrent_backups;
      $('conn-host').textContent = data.connection.host;
      $('conn-port').textContent = data.connection.port;
      $('conn-db').textContent = data.connection.database;
      $('conn-user').textContent = data.connection.username;
      $('bk-dir').textContent = data.backup.backup_dir;
      $('bk-dump').textContent = data.backup.dump_binary || 'Tidak ditemukan — set MYSQL_DUMP_PATH di .env';
    } catch (err) {
      dbm.toast('Gagal memuat pengaturan: ' + err.message, 'error');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    $('settings-form').addEventListener('submit', async function (event) {
      event.preventDefault();
      var payload = {
        storage_warn_pct: Number($('storage-warn').value),
        storage_critical_pct: Number($('storage-critical').value),
        retention_days: Number($('retention-days').value),
        max_concurrent_backups: Number($('max-concurrent').value),
      };
      try {
        await dbm.api('/api/v1/settings', { method: 'POST', body: payload });
        dbm.toast('Pengaturan tersimpan.', 'success');
      } catch (err) {
        dbm.toast('Gagal menyimpan: ' + err.message, 'error');
      }
    });
    loadSettings();
  });
})();
