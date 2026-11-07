# DB Monitor & Backup Manager

Aplikasi web administrasi terpusat untuk **monitoring database MySQL/MariaDB** dan **manajemen backup**.

Fungsi inti:

- Menemukan & menampilkan seluruh database non-sistem yang dapat diakses (ukuran, jumlah tabel, metadata tabel).
- Memilih satu database lalu **Backup & Download** — dump `.sql` dibuat oleh worker persisten, diverifikasi (exit code, ukuran, SHA-256), disimpan di server, lalu diunduh otomatis.
- **Backup Manager** untuk mencari, memfilter, dan mengunduh ulang backup lama (streaming, anti path traversal).
- Storage monitoring, database growth, scheduled backup, retention, audit log, dan authentication admin.

Stack: Python 3.11+ · FastAPI · SQLAlchemy · PyMySQL · Jinja2 · Tailwind CSS (CDN) · Vanilla JS · Chart.js · SweetAlert2 (CDN) · Uvicorn · mysqldump/mariadb-dump. Dev: Windows + XAMPP. Production: Ubuntu + Nginx + systemd.

---

## 1. Prasyarat

- Python 3.11+
- MySQL/MariaDB (XAMPP di Windows) beserta `mysqldump.exe`
- Koneksi internet (Tailwind CSS dan Chart.js dimuat dari CDN)

## 2. Setup (Windows + XAMPP)

```powershell
cd dbmonitor
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2.1 Konfigurasi `.env`

Salin `.env.example` menjadi `.env`, lalu sesuaikan. Jangan commit `.env`.

```dotenv
APP_ENV=development
APP_DEBUG=true
APP_SECRET_KEY=<hasil: python -c "import secrets; print(secrets.token_urlsafe(48))">

DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=db_monitor_app
DB_USERNAME=db_monitor
DB_PASSWORD=<password kuat>

MYSQL_DUMP_PATH=C:\xampp\mysql\bin\mysqldump.exe
BACKUP_DIR=storage/backups
BACKUP_RETENTION_DAYS=30
BACKUP_TIMEOUT_SECONDS=3600
MAX_CONCURRENT_BACKUPS=1

SESSION_COOKIE_SECURE=false
SESSION_EXPIRE_MINUTES=480

SHOW_SYSTEM_DATABASES=false
STORAGE_WARN_PCT=70
STORAGE_CRITICAL_PCT=85
MONITORING_REFRESH_SECONDS=60
APP_TIMEZONE_OFFSET_HOURS=7
```

### 2.2 Siapkan database aplikasi & akun MySQL dedicated

Jalankan sebagai admin MySQL (contoh; ganti password):

```sql
CREATE DATABASE IF NOT EXISTS db_monitor_app CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'db_monitor'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
CREATE USER IF NOT EXISTS 'db_monitor'@'127.0.0.1' IDENTIFIED BY 'GANTI_PASSWORD';

-- Metadata aplikasi (jobs, audit, schedule, dst.)
GRANT ALL PRIVILEGES ON db_monitor_app.* TO 'db_monitor'@'localhost';
GRANT ALL PRIVILEGES ON db_monitor_app.* TO 'db_monitor'@'127.0.0.1';

-- Read-only terhadap database target + izin minimum untuk dump
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES ON *.* TO 'db_monitor'@'localhost';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES ON *.* TO 'db_monitor'@'127.0.0.1';

-- Database terisolasi untuk uji restore
CREATE DATABASE IF NOT EXISTS db_monitor_restore_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON db_monitor_restore_test.* TO 'db_monitor'@'localhost';
GRANT ALL PRIVILEGES ON db_monitor_restore_test.* TO 'db_monitor'@'127.0.0.1';
FLUSH PRIVILEGES;
```

Aplikasi **tidak** memakai akun root secara default.

### 2.3 Buat akun admin

```powershell
.\venv\Scripts\python.exe -m scripts.create_admin --username admin
```

Password minimal 12 karakter, disimpan sebagai hash Argon2.

## 3. Menjalankan aplikasi

Butuh tiga proses (jalankan di terminal terpisah):

```powershell
# 1) Web app
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) Backup worker (menjalankan job dump)
.\venv\Scripts\p  

# 3) Scheduler worker (jadwal, snapshot growth, retention)
.\venv\Scripts\python.exe -m app.workers.scheduler_worker
```

Buka <http://127.0.0.1:8000> lalu login.

> Tanpa backup worker, job backup akan tetap `pending`. Tanpa scheduler worker, jadwal & snapshot tidak berjalan.

## 4. Alur backup (sesuai PRD)

1. `POST /api/v1/backups` `{"database_name": "..."}` → `202` dengan `job_id` + `poll_url`.
2. Frontend polling `GET /api/v1/backups/jobs/{id}`.
3. Worker mengklaim job, menjalankan `mysqldump` dengan argument list (`shell=False`), `--single-transaction --quick --routines --triggers --events --hex-blob --default-character-set=utf8mb4 --result-file=<file>`.
4. Kredensial diberikan melalui **defaults-file sementara** (permision ketat, dihapus setelah dipakai) — tidak pernah di argumen CLI.
5. Verifikasi: exit code 0, file ada, ukuran > 0, SHA-256 dihitung.
6. Saat `success`, response polling memuat `filename`, `file_size`, `checksum`, dan `download_url`; frontend langsung memicu download.
7. File tetap tersimpan di server (`BACKUP_DIR`), bisa diunduh ulang dari Backup Manager.
8. **Quick Backup di Dashboard** mengirim `{"database_name": "...", "ephemeral": true}`. File dibuat sementara hanya untuk diunduh, lalu **dihapus otomatis dari server segera setelah download selesai**; backup ephemeral tidak muncul di Backup Manager, tidak dihitung di statistik/storage, dan jika tidak pernah diunduh akan dibersihkan scheduler setelah `EPHEMERAL_TTL_MINUTES` (default 15 menit). Backup dari halaman Databases/Backup Manager tetap persisten sesuai PRD.

Catatan konsistensi: `--single-transaction` menjamin snapshot untuk engine transaksional (InnoDB). Untuk MyISAM/engine non-transaksional, UI menampilkan peringatan bahwa konsistensi tidak dijamin.

## 5. Uji restore terisolasi

```powershell
# Default memakai akun aplikasi
.\venv\Scripts\python.exe -m scripts.restore_test

# Jika dump mengandung DEFINER (view/trigger/routine), gunakan akun ber-privilege:
$env:RESTORE_TEST_DB_USERNAME="root"
$env:RESTORE_TEST_DB_PASSWORD="-"   # "-" berarti password kosong (XAMPP default)
.\venv\Scripts\python.exe -m scripts.restore_test --backup-id 1
```

Script membuat `db_monitor_restore_test`, mengimpor dump, menghitung tabel, lalu menghapus database uji (kecuali `--keep`).

## 6. Keamanan (end-to-end)

- Password admin: Argon2 (`argon2-cffi`).
- Session: cookie bertanda tangan (itsdangerous), `HttpOnly`, `SameSite=Lax`, `Secure` di production, expiry `SESSION_EXPIRE_MINUTES`.
- CSRF: token per sesi, wajib pada semua request mutasi (`X-CSRF-Token`).
- Rate limit login: 5 percobaan gagal / 5 menit per IP+username.
- Semua endpoint API operasional wajib autentikasi; halaman redirect ke `/login`.
- `subprocess` memakai argument list + `shell=False`; tanpa string command.
- Password MySQL tidak pernah masuk argv, log, atau response; password aplikasi tidak ditampilkan di UI.
- Nama database divalidasi terhadap daftar database yang benar-benar ada (cegah injeksi/path traversal).
- Download: path di-resolve dan dipastikan berada di `BACKUP_DIR`; streaming response.
- Direktori backup tidak pernah diekspos sebagai static/route.
- Security headers: CSP (`default-src 'self'`) dengan allowlist CDN (`cdn.tailwindcss.com`, `cdn.jsdelivr.net`), X-Frame-Options DENY, nosniff, no-store.
- Aset UI (Tailwind CSS & Chart.js) dimuat dari CDN, jadi halaman memerlukan koneksi internet; tidak ada `node_modules`/build npm. Jika ingin full offline, ganti ke file statis lokal dan sesuaikan CSP.
- Role `viewer`: dashboard, quick download (ephemeral), serta halaman All Backups + detail + download file backup persistent; halaman/API lain ditolak.
- Audit log mencatat aksi penting tanpa secret.

## 7. Production (Ubuntu VPS)

- Deploy ke `/opt/db-monitor`, buat venv, lalu `pip install -r requirements.txt`.
- `.env` production: `APP_DEBUG=false`, `SESSION_COOKIE_SECURE=true`, `BACKUP_DIR=/var/backups/db-monitor`, dump binary Linux (`/usr/bin/mysqldump` atau `mariadb-dump`).
- Contoh unit systemd: `deploy/db-monitor.service`, `deploy/db-monitor-worker.service`, `deploy/db-monitor-scheduler.service`.
- Contoh reverse proxy HTTPS + streaming download: `deploy/nginx.conf.example`.
- Jalankan service sebagai user dedicated (bukan root); batasi akses jaringan (VPN/IP allowlist) bila memungkinkan.

## 8. API (prefix `/api/v1`)

| Method | Endpoint | Fungsi |
| --- | --- | --- |
| POST | `/auth/login` | Login (set cookie) |
| POST | `/auth/logout` | Logout |
| GET | `/auth/me` | Info user aktif |
| GET | `/dashboard/overview` | Statistik dashboard + chart data |
| GET | `/databases` | Daftar database (search/sort/pagination) |
| GET | `/databases/{name}` | Detail database |
| GET | `/databases/{name}/tables` | Metadata tabel (pagination) |
| POST | `/backups` | Buat job backup |
| GET | `/backups` | Daftar file backup |
| GET | `/backups/jobs/{id}` | Status job (polling) |
| GET | `/backups/{id}` | Detail file backup |
| GET | `/backups/{id}/download` | Download streaming |
| GET | `/monitoring/storage` | Kapasitas disk & backup storage |
| GET | `/monitoring/growth` | Tren ukuran database |
| GET | `/monitoring/health` | Status koneksi MySQL |
| POST | `/monitoring/snapshot` | Rekam snapshot ukuran |
| GET/POST | `/schedules` | Lihat/buat jadwal |
| PUT/DELETE | `/schedules/{id}` | Ubah/hapus jadwal |
| GET/POST | `/settings` | Lihat/ubah pengaturan aplikasi |
| GET | `/audit-logs` | Riwayat audit |

## 9. Struktur project

```
app/
  main.py            # FastAPI app + security headers + exception handlers
  config.py          # environment-based settings
  database.py        # SQLAlchemy engine/session
  dependencies.py    # auth, CSRF
  security.py        # Argon2, session signing, rate limiter
  models/            # admin_users, backup_jobs, backups, audit_logs, snapshots, schedules, app_settings
  schemas/           # pydantic request models
  routers/           # pages + api (auth, dashboard, databases, backups, monitoring, schedules, settings, audit)
  services/          # mysql, backup, storage, scheduler, audit
  workers/           # backup_worker, scheduler_worker
  templates/         # Jinja2
  static/            # js (Tailwind & Chart.js via CDN)
scripts/
  create_admin.py
  restore_test.py
deploy/              # contoh systemd + nginx
storage/backups/     # BACKUP_DIR
storage/logs/
```

## 10. Catatan operasional

- Backup berjalan di proses worker terpisah; jika worker restart, job `processing` yang menggantung ditandai `failed` agar tidak menyesatkan.
- Retention (default 30 hari, dapat diubah di Settings) hanya menghapus file yang tercatat milik aplikasi dan berada di `BACKUP_DIR`.
- `TABLE_ROWS` InnoDB adalah estimasi; aplikasi tidak menjalankan `COUNT(*)` otomatis.
- Semua timestamp disimpan dalam waktu lokal aplikasi (WIB / UTC+7, atur lewat APP_TIMEZONE_OFFSET_HOURS); tampilan selalu diformat ke Asia/Jakarta (WIB). Untuk menggeser data lama dari UTC ke WIB, jalankan sekali python -m scripts.migrate_timestamps_wib --apply.


