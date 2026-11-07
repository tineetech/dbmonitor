(function () {
  'use strict';

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  async function api(path, options) {
    var opts = options || {};
    var method = (opts.method || 'GET').toUpperCase();
    var headers = Object.assign({ 'Accept': 'application/json' }, opts.headers || {});
    if (method !== 'GET' && method !== 'HEAD') {
      headers['X-CSRF-Token'] = csrfToken();
    }
    if (opts.body && typeof opts.body !== 'string') {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    var response;
    try {
      response = await fetch(path, Object.assign({}, opts, { method: method, headers: headers, credentials: 'same-origin' }));
    } catch (err) {
      throw new Error('Network error. Check your connection.');
    }
    if (response.status === 401) {
      window.location.href = '/login';
      throw new Error('Not authenticated');
    }
    var data = null;
    var text = await response.text();
    if (text) {
      try { data = JSON.parse(text); } catch (err) { data = null; }
    }
    if (!response.ok) {
      var detail = (data && data.detail) ? data.detail : ('Request failed (' + response.status + ')');
      var error = new Error(typeof detail === 'string' ? detail : 'Request failed');
      error.status = response.status;
      error.payload = data;
      throw error;
    }
    return data;
  }

  function isDark() {
    return document.documentElement.classList.contains('dark');
  }

  function toast(message, type) {
    var tone = type || 'info';
    var icon = tone === 'error' ? 'error' : tone === 'success' ? 'success' : 'info';
    if (window.Swal) {
      window.Swal.fire({
        toast: true,
        position: 'top-end',
        icon: icon,
        title: message,
        showConfirmButton: false,
        timer: tone === 'error' ? 6000 : 4500,
        timerProgressBar: true,
        background: isDark() ? '#0f172a' : '#ffffff',
        color: isDark() ? '#e2e8f0' : '#1e293b',
      });
      return;
    }
    var container = document.getElementById('toast-container');
    if (!container) return;
    var el = document.createElement('div');
    var toneClasses = {
      success: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
      error: 'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200',
      info: 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200',
    }[tone];
    el.className = 'rounded-lg border px-4 py-3 text-sm shadow-sm ' + (toneClasses || '');
    el.textContent = message;
    container.appendChild(el);
    window.setTimeout(function () { el.remove(); }, 5000);
  }

  function confirmAction(options) {
    var opts = options || {};
    if (!window.Swal) {
      return Promise.resolve(window.confirm(opts.text || opts.title || 'Lanjutkan?'));
    }
    return window.Swal.fire({
      icon: opts.icon || 'question',
      title: opts.title || 'Konfirmasi',
      text: opts.text || '',
      showCancelButton: true,
      confirmButtonText: opts.confirmText || 'Ya, lanjutkan',
      cancelButtonText: opts.cancelText || 'Batal',
      confirmButtonColor: opts.danger ? '#dc2626' : '#2563eb',
      cancelButtonColor: '#64748b',
      reverseButtons: true,
      focusCancel: true,
      background: isDark() ? '#0f172a' : '#ffffff',
      color: isDark() ? '#e2e8f0' : '#1e293b',
    }).then(function (result) { return !!result.isConfirmed; });
  }

  function formatBytes(bytes) {
    var n = Number(bytes || 0);
    if (!isFinite(n) || n < 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
    return n.toFixed(i === 0 ? 0 : 2) + ' ' + units[i];
  }

  function formatNumber(value) {
    return new Intl.NumberFormat('id-ID').format(Number(value || 0));
  }

  function parseServerDate(value) {
    var text = String(value == null ? '' : value);
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(text)) {
      return new Date(text + '+07:00');
    }
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?$/.test(text)) {
      return new Date(text.replace(' ', 'T') + '+07:00');
    }
    return new Date(text);
  }

  function formatDateTime(value) {
    if (!value) return '-';
    var date = parseServerDate(value);
    if (isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat('id-ID', {
      timeZone: 'Asia/Jakarta',
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      timeZoneName: 'short',
    }).format(date);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function statusBadge(status) {
    var map = {
      success: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
      pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
      processing: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
      failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
      cancelled: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
    };
    var cls = map[status] || 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300';
    return '<span class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ' + cls + '">' + escapeHtml(status || 'unknown') + '</span>';
  }

  function initSidebar() {
    var toggle = document.getElementById('sidebar-toggle');
    var sidebar = document.getElementById('sidebar');
    var backdrop = document.getElementById('sidebar-backdrop');
    if (!toggle || !sidebar) return;
    toggle.addEventListener('click', function () {
      sidebar.classList.toggle('-translate-x-full');
      if (backdrop) backdrop.classList.toggle('hidden');
    });
    if (backdrop) {
      backdrop.addEventListener('click', function () {
        sidebar.classList.add('-translate-x-full');
        backdrop.classList.add('hidden');
      });
    }
  }

  function initTheme() {
    var stored = null;
    try { stored = window.localStorage.getItem('dbmonitor-theme'); } catch (err) { stored = null; }
    if (stored === 'dark') document.documentElement.classList.add('dark');
    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.addEventListener('click', function () {
        var isDark = document.documentElement.classList.toggle('dark');
        try { window.localStorage.setItem('dbmonitor-theme', isDark ? 'dark' : 'light'); } catch (err) { /* ignore */ }
      });
    }
  }

  async function refreshMysqlStatus() {
    var dot = document.getElementById('mysql-status-dot');
    var text = document.getElementById('mysql-status-text');
    if (!dot || !text) return;
    try {
      var data = await api('/api/v1/monitoring/health');
      var connected = data && data.mysql && data.mysql.connected;
      dot.className = 'h-2 w-2 rounded-full ' + (connected ? 'bg-emerald-500' : 'bg-red-500');
      text.textContent = connected ? 'MySQL: connected' : 'MySQL: disconnected';
      text.title = connected && data.mysql.version ? ('MariaDB/MySQL ' + data.mysql.version) : '';
    } catch (err) {
      dot.className = 'h-2 w-2 rounded-full bg-red-500';
      text.textContent = 'MySQL: disconnected';
    }
  }

  function initLogout() {
    var button = document.getElementById('logout-btn');
    if (!button) return;
    button.addEventListener('click', async function () {
      try {
        await api('/api/v1/auth/logout', { method: 'POST' });
      } catch (err) {
        /* proceed to redirect regardless */
      }
      window.location.href = '/login';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTheme();
    initSidebar();
    initLogout();
    refreshMysqlStatus();
    window.setInterval(refreshMysqlStatus, 60000);
  });

  window.DBM = {
    api: api,
    toast: toast,
    confirm: confirmAction,
    formatBytes: formatBytes,
    formatNumber: formatNumber,
    formatDateTime: formatDateTime,
    escapeHtml: escapeHtml,
    statusBadge: statusBadge,
  };
})();
