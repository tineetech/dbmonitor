(function () {
  'use strict';

  var form = document.getElementById('login-form');
  var errorBox = document.getElementById('login-error');
  var submit = document.getElementById('login-submit');

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove('hidden');
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    errorBox.classList.add('hidden');
    submit.disabled = true;
    submit.textContent = 'Signing in…';
    try {
      var response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken(),
          'Accept': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          username: document.getElementById('username').value.trim(),
          password: document.getElementById('password').value,
        }),
      });
      var data = null;
      var text = await response.text();
      if (text) {
        try { data = JSON.parse(text); } catch (err) { data = null; }
      }
      if (!response.ok) {
        showError((data && data.detail) ? data.detail : 'Login gagal. Coba lagi.');
        submit.disabled = false;
        submit.textContent = 'Sign in';
        return;
      }
      window.location.href = '/dashboard';
    } catch (err) {
      showError('Koneksi gagal. Periksa jaringan atau server.');
      submit.disabled = false;
      submit.textContent = 'Sign in';
    }
  });
})();
