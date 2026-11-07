(function () {
  'use strict';
  var dbm = window.DBM;
  var WEEKDAYS = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'];

  function $(id) { return document.getElementById(id); }

  async function loadDatabaseOptions() {
    try {
      var data = await dbm.api('/api/v1/databases?per_page=100&sort=name&order=asc');
      var select = $('schedule-db');
      select.innerHTML = (data.databases || []).map(function (db) {
        return '<option value="' + dbm.escapeHtml(db.name) + '">' + dbm.escapeHtml(db.name) + '</option>';
      }).join('');
      if (!select.options.length) {
        select.innerHTML = '<option value="">Tidak ada database</option>';
      }
    } catch (err) {
      dbm.toast('Gagal memuat daftar database: ' + err.message, 'error');
    }
  }

  async function loadSchedules() {
    $('schedules-loading').classList.remove('hidden');
    $('schedules-empty').classList.add('hidden');
    try {
      var data = await dbm.api('/api/v1/schedules');
      renderRows(data.schedules || []);
    } catch (err) {
      dbm.toast('Gagal memuat jadwal: ' + err.message, 'error');
      $('schedules-loading').classList.add('hidden');
    }
  }

  function renderRows(schedules) {
    $('schedules-loading').classList.add('hidden');
    var tbody = $('schedule-rows');
    if (!schedules.length) { tbody.innerHTML = ''; $('schedules-empty').classList.remove('hidden'); return; }
    tbody.innerHTML = schedules.map(function (schedule) {
      var scheduleLabel = schedule.frequency === 'weekly'
        ? (WEEKDAYS[schedule.day_of_week || 0] + ' · ' + schedule.run_time)
        : ('Setiap hari · ' + schedule.run_time);
      return '<tr class="border-b border-slate-100 dark:border-slate-800">'
        + '<td class="py-3 pl-4 pr-4 font-medium">' + dbm.escapeHtml(schedule.database_name) + '</td>'
        + '<td class="py-3 pr-4">' + (schedule.frequency === 'weekly' ? 'Mingguan' : 'Harian') + '</td>'
        + '<td class="py-3 pr-4 text-xs text-slate-500">' + dbm.escapeHtml(scheduleLabel) + '</td>'
        + '<td class="py-3 pr-4 text-xs text-slate-500">' + dbm.formatDateTime(schedule.last_run_at) + '</td>'
        + '<td class="py-3 pr-4 text-xs text-slate-500">' + dbm.formatDateTime(schedule.next_run_at) + '</td>'
        + '<td class="py-3 pr-4">' + (schedule.enabled
            ? '<span class="inline-flex rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-300 px-2 py-0.5 text-[11px] font-medium">Aktif</span>'
            : '<span class="inline-flex rounded-full bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2 py-0.5 text-[11px] font-medium">Nonaktif</span>') + '</td>'
        + '<td class="py-3 pr-4 text-right whitespace-nowrap">'
        + '<button type="button" class="toggle-btn inline-flex rounded-md border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs hover:border-accent hover:text-accent mr-1" data-id="' + schedule.id + '" data-enabled="' + (schedule.enabled ? '1' : '0') + '">' + (schedule.enabled ? 'Nonaktifkan' : 'Aktifkan') + '</button>'
        + '<button type="button" class="delete-btn inline-flex rounded-md border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 px-3 py-1.5 text-xs hover:bg-red-50 dark:hover:bg-red-950/40" data-id="' + schedule.id + '">Hapus</button>'
        + '</td>'
        + '</tr>';
    }).join('');

    tbody.querySelectorAll('.toggle-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var id = Number(btn.getAttribute('data-id'));
        var enabled = btn.getAttribute('data-enabled') === '1';
        try {
          await dbm.api('/api/v1/schedules/' + id, { method: 'PUT', body: { enabled: !enabled } });
          dbm.toast('Jadwal diperbarui.', 'success');
          loadSchedules();
        } catch (err) {
          dbm.toast('Gagal mengubah jadwal: ' + err.message, 'error');
        }
      });
    });
    tbody.querySelectorAll('.delete-btn').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        var id = Number(btn.getAttribute('data-id'));
        var confirmed = await dbm.confirm({
          icon: 'warning',
          title: 'Hapus jadwal?',
          text: 'Jadwal #' + id + ' akan dihapus permanen.',
          confirmText: 'Ya, hapus',
          danger: true,
        });
        if (!confirmed) return;
        try {
          await dbm.api('/api/v1/schedules/' + id, { method: 'DELETE' });
          dbm.toast('Jadwal dihapus.', 'success');
          loadSchedules();
        } catch (err) {
          dbm.toast('Gagal menghapus jadwal: ' + err.message, 'error');
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var frequency = $('schedule-frequency');
    var weekdayRow = $('weekday-row');
    frequency.addEventListener('change', function () {
      weekdayRow.classList.toggle('hidden', frequency.value !== 'weekly');
    });
    $('refresh-schedules').addEventListener('click', loadSchedules);
    $('schedule-form').addEventListener('submit', async function (event) {
      event.preventDefault();
      var payload = {
        database_name: $('schedule-db').value,
        frequency: frequency.value,
        run_time: $('schedule-time').value,
        enabled: $('schedule-enabled').checked,
      };
      if (frequency.value === 'weekly') payload.day_of_week = Number($('schedule-weekday').value);
      try {
        await dbm.api('/api/v1/schedules', { method: 'POST', body: payload });
        dbm.toast('Jadwal dibuat.', 'success');
        loadSchedules();
      } catch (err) {
        dbm.toast('Gagal membuat jadwal: ' + err.message, 'error');
      }
    });
    loadDatabaseOptions();
    loadSchedules();
  });
})();
