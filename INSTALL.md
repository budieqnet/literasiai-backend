# Tutorial Instalasi LiterasiAI di VPS (Ubuntu 22.04/24.04)

> Proyek ini adalah aplikasi **Flask** yang menggunakan **MySQL** sebagai database, **NVIDIA Nemotron** untuk klasifikasi, dan beberapa layanan pencarian akademik.
> Panduan di bawah mengasumsikan Anda sudah punya akses **root/sudo** ke VPS dan domain (opsional) yang sudah mengarah ke IP VPS.

---

## 1. Persiapan Sistem

```bash
# update & paket dasar
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip \
                    mysql-server nginx certbot python3-certbot-nginx \
                    git curl
```

### 1.1 MySQL – buat database & user

```bash
sudo mysql -u root <<'SQL'
CREATE DATABASE IF NOT EXISTS literasiai
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'budi'@'localhost' IDENTIFIED BY 'Budi@123';
GRANT ALL PRIVILEGES ON literasiai.* TO 'budi'@'localhost';
FLUSH PRIVILEGES;
SQL
```

> **Catatan** – Ganti password `Budi@123` dengan yang lebih kuat jika di‑produksi.

### 1.2 Import skema awal

```bash
# file SQL ada di repo: db/literasiai.sql
mysql -u budi -p'Budi@123' literasiai < db/literasiai.sql
```

---

## 2. Clone & Virtual‑env

```bash
cd /opt
sudo git clone https://github.com/<user>/literasiai.git   # ganti URL repo Anda
sudo chown -R $USER:$USER literasiai
cd literasiai

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> `requirements.txt` sudah berisi Flask, mysql‑connector, requests, cachetools, dll.

---

## 3. Konfigurasi Environment (`.env`)

Salin contoh dan isi nilai‑nilai rahasia:

```bash
cp .env.example .env
nano .env
```

**Isi minimal yang wajib diisi**

| Variabel | Contoh / Keterangan |
|----------|----------------------|
| `SECRET_KEY` | `openssl rand -hex 32` |
| `FLASK_ENV` | `production` |
| `FLASK_DEBUG` | `0` |
| `MYSQL_HOST` | `localhost` |
| `MYSQL_PORT` | `3306` |
| `MYSQL_USER` | `budi` |
| `MYSQL_PASSWORD` | `Budi@123` |
| `MYSQL_DATABASE` | `literasiai` |
| `NVIDIA_API_KEY` | `sk‑xxxxxxxxxxxxxxxxxxxxxxxx` (dapat dari https://integrate.api.nvidia.com) |
| `NVIDIA_API_KEY_1` … `NVIDIA_API_KEY_3` | (opsional, untuk rotasi key) |
| `ADMIN_API_KEY` | `super‑secret‑admin‑key` (digunakan endpoint `/api/admin/*`) |
| `LOG_LEVEL` | `INFO` |

Simpan & keluar (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## 4. Tes Jalankan Secara Manual

```bash
source venv/bin/activate
python run.py
```

Buka browser `http://<IP‑VPS>:5000` – seharusnya muncul halaman utama / health‑check.

> Jika ada error koneksi MySQL / NVIDIA, periksa log di terminal dan pastikan `.env` benar.

---

## 5. Systemd Service (auto‑start & restart)

Buat file `/etc/systemd/system/literasiai.service` :

```ini
[Unit]
Description=LiterasiAI Flask App
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/literasiai
Environment="PATH=/opt/literasiai/venv/bin"
ExecStart=/opt/literasiai/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 run:app
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> **Catatan** – `run:app` mengacu pada `app = create_app()` di `run.py`.
> Pastikan user `www-data` punya akses baca ke folder proyek (`chown -R www-data:www-data /opt/literasiai`).

Aktifkan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now literasiai
sudo systemctl status literasiai   # cek apakah running
```

---

## 6. Nginx Reverse‑Proxy (+ HTTPS via Let's Encrypt)

### 6.1 Konfigurasi site

```bash
sudo tee /etc/nginx/sites-available/literasiai <<'NGINX'
server {
    listen 80;
    server_name api.literasiai.id;          # ganti dengan domain Anda

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    # optional: static files (jika ada)
    # location /static/ { alias /opt/literasiai/static/; }
}
NGINX
```

Aktifkan & test:

```bash
sudo ln -s /etc/nginx/sites-available/literasiai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 6.2 SSL (Let's Encrypt)

```bash
sudo certbot --nginx -d api.literasiai.id   # ikuti prompt, pilih redirect HTTP→HTTPS
```

Certbot akan otomatis memperbarui konfigurasi Nginx dan menambahkan sertifikat.

---

## 7. Firewall (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

---

## 8. Verifikasi Endpoint Utama

| Endpoint | Deskripsi | Contoh `curl` |
|----------|-----------|---------------|
| `GET /api/health` | Health‑check (DB, NVIDIA, sources) | `curl https://api.literasiai.id/api/health` |
| `POST /api/classify` | Klasifikasi dokumen | `curl -X POST -H "Content-Type: application/json" -d '{"title":"Test","abstract":"..."}' https://api.literasiai.id/api/classify` |
| `POST /api/search` | Pencarian multi‑source | `curl -X POST -H "Content-Type: application/json" -d '{"query":"machine learning","sources":["arxiv","pubmed"]}' https://api.literasiai.id/api/search` |
| `GET /api/admin/download-methods` | (butuh header `X-Admin-Key`) | `curl -H "X-Admin-Key: $ADMIN_API_KEY" https://api.literasiai.id/api/admin/download-methods` |

Semua harus mengembalikan **JSON** dengan status `200`.

---

## 9. (Opsional) Monitoring & Logrotate

```bash
# logrotate untuk gunicorn / flask
sudo tee /etc/logrotate.d/literasiai <<'LR'
/opt/literasiai/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload literasiai > /dev/null 2>&1 || true
    endscript
}
LR
```

Pastikan folder log ada:

```bash
mkdir -p /opt/literasiai/logs
chown www-data:www-data /opt/literasiai/logs
```

---

## 10. Backup Rutin (Database)

```bash
# Contoh cron harian jam 02:30
(crontab -l 2>/dev/null; echo "30 2 * * * mysqldump -u budi -p'Budi@123' literasiai | gzip > /opt/backups/literasiai_$(date +\%F).sql.gz") | crontab -
mkdir -p /opt/backups
```

---

## 11. Checklist Sebelum Go‑Live

- [ ] `.env` berisi **semua** secret (NVIDIA, ADMIN, DB, SECRET_KEY).
- [ ] Database `literasiai` sudah ter‑import & user `budi` bisa akses.
- [ ] Service `literasiai` **active (running)**.
- [ ] Nginx **running**, SSL valid (`certbot certificates`).
- [ ] Endpoint `/api/health` mengembalikan `"status":"ok"`.
- [ ] Firewall hanya membuka 22, 80, 443.
- [ ] Backup DB otomatis terpasang.

---

### 🎉 Selesai!

Aplikasi LiterasiAI sekarang berjalan di VPS, diakses via HTTPS, dan siap melayani pencarian & klasifikasi dokumen akademik.

Jika butuh penyesuaian (mis. tambah source baru, ubah kategori klasifikasi, dsb.) cukup edit kode di `/opt/literasiai`, lalu `sudo systemctl restart literasiai`.

---

**Referensi Cepat**

| File Penting | Fungsi |
|--------------|--------|
| `run.py` | Entry‑point Flask (`create_app()`) |
| `app/services/nvidia.py` | Klasifikasi via NVIDIA Nemotron |
| `app/services/database.py` | Koneksi & CRUD MySQL |
| `config/settings.py` | Semua konfigurasi via `Config` class |
| `db/literasiai.sql` | Skema awal database |
| `requirements.txt` | Dependencies Python |

Selamat mencoba! 🚀