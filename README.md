# LiterasiAI — Backend API

Mesin pencari & download ebook dan ejournal dengan klasifikasi AI.
Dibangun dengan **Python + Flask**.

---

## Sumber yang Didukung

| ID | Nama | Tipe | Bahasa | API |
|---|---|---|---|---|
| `doaj` | DOAJ | Jurnal | Multi | ✅ Resmi ✅ Generic |
| `pubmed` | PubMed Central | Jurnal | EN | ✅ Resmi |
| `arxiv` | arXiv | Preprint | EN | ✅ Resmi |
| `core` | CORE | Jurnal | Multi | ✅ Resmi ✅ Generic |
| `garuda` | Garuda Kemdikbud | Jurnal | ID | ⚠️ Scraping |
| `sinta` | SINTA Kemdikbud | Jurnal | ID | ⚠️ Scraping |
| `neliti` | Neliti | Jurnal | ID | ✅ Resmi ✅ Generic |
| `gutenberg` | Project Gutenberg | Buku | Multi | ✅ Resmi ✅ Generic |
| `openlibrary` | Open Library | Buku | Multi | ✅ Resmi ✅ Generic |
| `archive` | Internet Archive | Campuran | Multi | ✅ Resmi ✅ Generic |
| `openaccess` | Unpaywall | Jurnal | Multi | ✅ Resmi (lookup DOI) |
| `sciencedirect` | ScienceDirect | Jurnal | EN | ✅ Crossref (metadata) |
| `wiley` | Wiley Online Library | Jurnal | EN | ✅ Crossref (metadata) |
| `springerlink` | SpringerLink | Jurnal | EN | ✅ Crossref (metadata) |
| `emerald` | Emerald Insight | Jurnal | EN | ✅ Crossref (metadata) |
| `tandfonline` | Taylor & Francis Online | Jurnal | EN | ✅ Crossref (metadata) |

---

## Instalasi

```bash
# 1. Clone / copy proyek
cd literasiai

# 2. Buat virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 3. Install dependencies (Flask, requests, dll.)
pip install -r requirements.txt

# 4. Konfigurasi environment
cp .env.example .env
# Edit .env sesuai kebutuhan

# 5. Jalankan server
python run.py
```

Server berjalan di `http://localhost:5008`

---

## Endpoint API

### Pencarian

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/api/search?q=<query>` | Cari di semua sumber |
| GET | `/api/search?q=<query>&type=journal` | Hanya sumber jurnal |
| GET | `/api/search?q=<query>&type=book` | Hanya sumber buku |
| GET | `/api/search?q=<query>&sources=doaj,arxiv` | Sumber tertentu |
| GET | `/api/search/<source>?q=<query>` | Satu sumber spesifik |

**Parameter umum:**
- `q` (wajib): kata kunci pencarian
- `page` (opsional, default: 1): nomor halaman
- `page_size` (opsional, default: 10): jumlah hasil

### Lookup

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/api/lookup/doi?doi=<doi>` | Metadata + OA via DOI |
| GET | `/api/lookup/isbn?isbn=<isbn>` | Metadata buku via ISBN |
| GET | `/api/lookup/sources` | Daftar semua sumber |

### Download

| Method | Endpoint | Deskripsi |
|---|---|---|
| POST | `/api/download` | Download file (URL/DOI/ISBN) |
| GET | `/api/download/stream` | Stream file untuk di-download |
| POST | `/api/download/info` | Cek info file tanpa download |

Catatan keamanan download:
- Hanya URL `http`/`https` ke host publik yang diizinkan; IP private/loopback/link-local/metadata diblokir (SSRF).
- Redirect divalidasi ulang sebelum diikuti.
- `filename` custom tidak boleh mengandung path; file selalu ditulis di dalam folder `downloads/`.
- Field `filepath` pada respons bersifat relatif (`downloads/<nama-file>`), bukan path absolut server.

### Admin Download Methods (butuh auth)

Semua endpoint `/api/admin/download-methods` memerlukan `ADMIN_API_KEY`, dikirim sebagai
`Authorization: Bearer <key>` atau `X-Admin-Key: <key>`. Bila key belum diset, endpoint
menolak request dengan `503` (fail closed).

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/api/admin/download-methods` | Daftar semua method + settings |
| POST | `/api/admin/download-methods` | Tambah method |
| PUT/DELETE | `/api/admin/download-methods/<id>` | Update/hapus method |
| POST | `/api/admin/download-methods/<id>/toggle` | Enable/disable method |
| PUT | `/api/admin/download-methods/reorder` | Ubah prioritas |
| PUT | `/api/admin/download-methods/settings` | Update settings |
| POST | `/api/admin/download-methods/reset` | Reset ke default |

### Klasifikasi AI

| Method | Endpoint | Deskripsi |
|---|---|---|
| POST | `/api/classify` | Klasifikasi dokumen (NVIDIA Nemotron + fallback) |
| POST | `/api/classify/batch` | Klasifikasi multiple dokumen |
| GET | `/api/classify/categories` | Daftar kategori klasifikasi |

### Health Check

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/health` | Status aplikasi + database |
| GET | `/health?detailed=true` | Status database + semua sumber |

### Utilitas

| Method | Endpoint | Deskripsi |
|---|---|---|
| GET | `/` | Info API & daftar endpoint |

---

## Contoh Request

```bash
# Cari semua sumber
curl "http://localhost:5008/api/search?q=machine+learning&page_size=5"

# Cari hanya jurnal
curl "http://localhost:5008/api/search?q=hukum+perdata&type=journal"

# Cari di DOAJ dan arXiv saja
curl "http://localhost:5008/api/search?q=deep+learning&sources=doaj,arxiv"

# Cari di satu sumber
curl "http://localhost:5008/api/search/arxiv?q=transformer+model"

# Lookup DOI
curl "http://localhost:5008/api/lookup/doi?doi=10.1038/nature12373"

# Lookup ISBN
curl "http://localhost:5008/api/lookup/isbn?isbn=9780140449136"

# Download via DOI
curl -X POST "http://localhost:5008/api/download" \
  -H "Content-Type: application/json" \
  -d '{"doi": "10.1038/nature12373"}'

# Admin: daftar download methods (wajib auth)
curl "http://localhost:5008/api/admin/download-methods" \
  -H "Authorization: Bearer $ADMIN_API_KEY"

# Klasifikasi dokumen
curl -X POST "http://localhost:5008/api/classify" \
  -H "Content-Type: application/json" \
  -d '{"title": "Deep Learning for Image Recognition", "abstract": "..."}'

# Health check
curl "http://localhost:5008/health?detailed=true"
```

---

## Format Respons

### Dokumen (dari search/lookup)

```json
{
  "source":        "DOAJ",
  "doc_type":      "journal",
  "title":         "Judul Artikel",
  "authors":       ["Penulis A", "Penulis B"],
  "year":          "2023",
  "abstract":      "Ringkasan artikel...",
  "doi":           "10.xxxx/xxxxx",
  "url":           "https://...",
  "download_url":  "https://...",
  "pdf_url":       "https://...",
  "language":      "en",
  "subjects":      ["Informatika", "AI"],
  "publisher":     "Nama Penerbit",
  "identifier":    "id-unik",
  "thumbnail":     "https://...",
  "classification": null
}
```

### Klasifikasi

```json
{
  "title": "Deep Learning for Image Recognition",
  "category": "Computer Vision",
  "confidence": 0.85,
  "keywords": ["deep learning", "computer vision", "neural network"],
  "summary": "Klasifikasi berdasarkan CNN architecture untuk image recognition",
  "provider": "nvidia"
}
```

Klasifikasi memakai cache in-memory (default 24 jam, 2.048 entri) dengan kunci
model + prompt + isi dokumen, sehingga dokumen yang sama tidak memanggil API
berulang. Bila `NVIDIA_API_KEY`/`NVIDIA_API_KEYS` diisi lebih dari satu,
key dicoba bergantian saat terkena rate limit atau error autentikasi.
Jika API gagal total, endpoint otomatis memakai keyword fallback (`provider:
"fallback"`).

---

## Struktur Proyek

```
literasiai/
├── run.py                    # Entry point
├── literasiai.spec           # PyInstaller spec
├── requirements.txt
├── .env.example
├── config/
│   ├── settings.py           # Konfigurasi terpusat
│   ├── setting_sumber.json   # ★ Konfigurasi sumber data (JSON)
│   └── download_methods.json # Konfigurasi pipeline download
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── routes/
│   │   ├── search.py         # Endpoint pencarian
│   │   ├── lookup.py         # Endpoint DOI/ISBN lookup
│   │   ├── download.py       # Endpoint download file
│   │   ├── classify.py      # Endpoint klasifikasi AI
│   │   ├── admin_download.py # Admin download methods API
│   │   └── health.py         # Health check
│   ├── services/
│   │   ├── __init__.py       # Expose SOURCE_MAP via registry
│   │   ├── registry.py       # ★ SourceRegistry (load setting_sumber.json)
│   │   ├── database.py       # MySQL auto-save + dedup pencarian
│   │   ├── handlers/
│   │   │   ├── __init__.py   # Daftar handler
│   │   │   ├── generic_json.py # ★ Generic JSON API handler
│   │   │   └── subscription.py # ★ Crossref handler (5 publisher berlangganan)
│   │   ├── doaj.py           # Custom: DOAJ
│   │   ├── pubmed.py         # Custom: PubMed Central
│   │   ├── arxiv.py          # Custom: arXiv
│   │   ├── core_ac.py        # Custom: CORE
│   │   ├── garuda.py         # Custom: Garuda (scraping)
│   │   ├── sinta.py          # Custom: SINTA (scraping)
│   │   ├── neliti.py         # Custom: Neliti
│   │   ├── gutenberg.py      # Custom: Project Gutenberg
│   │   ├── openlibrary.py    # Custom: Open Library
│   │   ├── archive_org.py    # Custom: Internet Archive
│   │   └── openaccess.py     # Custom: Unpaywall (DOI → OA)
│   └── utils/
│       ├── http.py           # HTTP helper
│       ├── security.py       # SSRF guard + sanitasi filename
│       ├── auth.py           # Auth endpoint admin
│       ├── normalizer.py     # Format dokumen seragam
│       └── logging.py        # Structured logging
├── downloads/                # Folder download (auto-created)
└── tests/
    └── test_services.py      # Uji koneksi & fitur
```

---

## Environment Variables

```bash
FLASK_ENV=development          # development | production
FLASK_DEBUG=0                  # 1 | 0 (default 0; jangan aktifkan di production)
SECRET_KEY=<your-secret>       # Secret key untuk sesi
ADMIN_API_KEY=<random-key>     # Wajib untuk /api/admin/download-methods
CACHE_TTL=600                  # Cache TTL dalam detik
CORE_API_KEY=                 # API key untuk CORE (opsional)
NVIDIA_API_KEY=               # API key NVIDIA Build (untuk klasifikasi AI)
# NVIDIA_API_KEYS=key1,key2,key3   # opsional: rotasi beberapa key (atau NVIDIA_API_KEY_1..3)
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_TIMEOUT=60
NVIDIA_MAX_RETRIES=2
NVIDIA_CACHE_ENABLED=1         # 1 = cache klasifikasi aktif
NVIDIA_CACHE_TTL=86400         # TTL cache klasifikasi (detik)
NVIDIA_CACHE_SIZE=2048         # maksimum entri cache klasifikasi
LOG_LEVEL=INFO               # DEBUG | INFO | WARNING | ERROR

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=budi
MYSQL_PASSWORD=Budi@123
MYSQL_DATABASE=literasiai
MYSQL_CONNECT_TIMEOUT=5
```

---

## Uji Koneksi & Fitur

```bash
# Uji semua sumber
python tests/test_services.py

# Unit test classifier (tanpa memanggil API)
python tests/test_classifier.py

# Uji akurasi classifier (memanggil API NVIDIA, butuh NVIDIA_API_KEY)
python tests/test_classifier_accuracy.py

# Benchmark beberapa model pada dataset 120 sampel (memanggil API NVIDIA)
python tests/benchmark_classifier.py --limit 20 --delay 2

# Bandingkan dua hasil benchmark
python tests/compare_benchmarks.py

# Regresi perbaikan data (filter/extract, Gutenberg, normalisasi)
python tests/test_data_fixes.py

# Regresi keamanan (auth admin, SSRF, path traversal, debug)
python tests/test_security.py

# Unit + integrasi database (membuat DB sementara literasiai_test_*)
python tests/test_database.py

# Jalankan server
python run.py
```

---

## Konfigurasi Download Methods

File `config/download_methods.json` adalah **source of truth** untuk pipeline download:

- **Daftar metode** — 10 sumber (Unpaywall, Open Library, arXiv, DOAJ, CORE, PubMed, Gutenberg, Internet Archive, Crossref, Direct URL) masing-masing dengan `id`, `name`, `enabled`, `priority`, dan `config`
- **Prioritas berantai** — Diurutkan dari priority 1–10. Jika metode 1 gagal, sistem fallback ke metode berikutnya secara otomatis
- **Pengaturan global** — `max_file_size_mb`, `chunk_size_kb`, `timeout_seconds`, `retry_attempts`, `cache_ttl_seconds`
- **Kontrol admin** — `allow_add_method`, `allow_edit_method`, `allow_delete_method`, `allow_toggle_enabled`; endpoint admin dilindungi `ADMIN_API_KEY`

### Menambah Sumber Download Baru

Tidak cukup hanya edit JSON. Ada **3 lapisan** yang perlu diubah:

1. **Config** — Tambah entry method baru di `config/download_methods.json`
2. **Service** — Buat file `app/services/<sumber>.py` (lihat pola di bawah)
3. **Routing** — Tambah dispatch logic di `app/routes/download.py:_resolve_by_doi()` jika sumber baru berbasis DOI

### Pola Service File

Semua file service di `app/services/` mengikuti pola seragam:

```
search(query, page=1, page_size=10) → dict
```

**Return dict:**
```json
{
  "source":    "Nama Sumber",
  "total":     integer,
  "page":      1,
  "page_size": 10,
  "results":   [{...}],   // Array dokumen via make_document()
  "error":     null
}
```

Yang membedakan tiap service hanyalah:
- **API endpoint** dan cara parsing respons (arXiv pake XML, lainnya JSON)
- **Parameter query** (arXiv → `search_query`, Gutendex → `search`, CORE → `q`)
- **Auth** (CORE butuh API key, sumber lain publik)

Untuk mengetahui struktur respons API suatu sumber, baca dokumentasi resminya:

| Sumber | Dokumentasi API |
|---|---|
| DOAJ | `https://doaj.org/api/v3/docs` |
| arXiv | `https://info.arxiv.org/help/api/index.html` |
| PubMed | `https://www.ncbi.nlm.nih.gov/books/NBK25501/` |
| Open Library | `https://openlibrary.org/dev/docs/api/search` |
| CORE | `https://api.core.ac.uk/docs/v3` |
| Gutendex (Gutenberg) | `https://gutendex.com/` |

Atau langsung `curl` endpoint untuk lihat respons mentahnya:

```bash
curl -s "https://gutendex.com/books?search=python&page=1" | python -m json.tool
```

---

---

## Konfigurasi Sumber Data (`setting_sumber.json`)

File `config/setting_sumber.json` adalah **source of truth** untuk semua sumber ebook/ejournal.

### Yang bisa dilakukan via JSON (tanpa Python):

| Aksi | Cara |
|------|------|
| Nonaktifkan sumber | Set `"enabled": false` |
| Ubah nama/deskripsi | Edit `name` / `description` |
| Ubah tipe konten | Edit `type` (journal/book/preprint/mixed) |
| Ubah base URL | Edit `config.base_url` |
| Ubah parameter API | Edit `config.params` |
| Ubah field mapping | Edit `response_mapping.fields` |

### Menambah Sumber Baru (JSON API)

Cukup tambah entry baru di `setting_sumber.json` dengan `"handler": "generic_json"`:

```json
{
  "id": "sumber_baru",
  "name": "Nama Sumber Baru",
  "type": "journal",
  "language": "en",
  "enabled": true,
  "handler": "generic_json",
  "config": {
    "base_url": "https://api.sumber.com/v1",
    "search_endpoint": "/search?q={query}",
    "params": { "page": "page", "size": "page_size" }
  },
  "response_mapping": {
    "results_path": "data.items",
    "total_path": "data.total",
    "fields": {
      "title": "title",
      "authors": { "path": "authors", "extract": "name" },
      "year": "year",
      "doi": "doi",
      "doc_type": { "static": "journal" },
      "source_name": { "static": "Sumber Baru" }
    }
  }
}
```

Sumber dengan tipe `"handler": "generic_json"` otomatis diproses oleh `handlers/generic_json.py` — tanpa perlu membuat file Python baru.

### Menambah Sumber dengan Parsing Kustom

Untuk sumber dengan format respons kompleks (XML, HTML scraping, multi-step API), buat handler kustom:

1. Buat file `app/services/<sumber>.py` dengan fungsi `search(query, page, page_size)`
2. Daftarkan di `app/services/registry.py` di dictionary `CUSTOM_HANDLER_MAP`
3. Di `setting_sumber.json`, set `"handler": "custom_<sumber>"`

### Konten Grup

Pengelompokan sumber dikontrol di `setting_sumber.json`:

```json
"content_groups": {
  "journal": ["doaj", "pubmed", "arxiv", "core", "garuda", "sinta", "neliti",
              "sciencedirect", "wiley", "springerlink", "emerald", "tandfonline"],
  "book": ["gutenberg", "openlibrary", "archive"],
  "all": ["doaj", "pubmed", "arxiv", "core", "garuda", "sinta", "neliti",
          "gutenberg", "openlibrary", "archive",
          "sciencedirect", "wiley", "springerlink", "emerald", "tandfonline"]
}
```

---

## Kompilasi Executable (PyInstaller)

Proyek dapat dikompilasi menjadi executable Linux dengan PyInstaller.

### Build

```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller literasiai.spec
```

Hasil: `dist/literasiai/` — folder berisi executable + semua dependencies.

### Struktur Output

```
dist/literasiai/
├── literasiai              # Executable (~12MB)
├── _internal/              # Library & dependencies
│   └── config/
│       ├── setting_sumber.json   # Konfigurasi sumber (bawaan)
│       └── download_methods.json # Konfigurasi download (bawaan)
```

### Runtime Config

Config dibaca dengan prioritas:
1. File di direktori yang **sama dengan executable** (external) — untuk diedit kapan saja
2. File di `_internal/config/` (bawaan) — fallback default

```bash
# Copy config ke folder executable untuk diedit runtime
mkdir -p dist/literasiai/config
cp config/setting_sumber.json dist/literasiai/config/
cp config/download_methods.json dist/literasiai/config/
cp .env dist/literasiai/
```

### Multi-platform

Build untuk OS lain harus dilakukan di OS target masing-masing:
- **Windows**: `pyinstaller literasiai.spec` di Windows
- **macOS**: `pyinstaller literasiai.spec` di macOS
- **Linux**: `pyinstaller literasiai.spec` di Linux (current)

---

## Fitur Utama

- **Konfigurasi Sumber via JSON** — Tambah/nonaktifkan 16 sumber cukup edit `setting_sumber.json`, tanpa Python
- **Generic JSON Handler** — Sumber JSON API baru bisa ditambah via JSON config saja
- **Subscription Handler** — 5 publisher berlangganan via Crossref API (metadata-only)
- **Penyimpanan MySQL** — Hasil pencarian otomatis disimpan ke database dengan deduplikasi
- **Pencarian Paralel** — Semua sumber dijalankan concurrently via ThreadPoolExecutor
- **Cache In-Memory** — TTLCache 256 item, 600 detik TTL
- **Normalisasi Dokumen** — Skema unified untuk semua sumber
- **Download Streaming** — Support file sampai 500MB
- **Download Methods** — Prioritas berantai via `config/download_methods.json`
- **Klasifikasi AI** — NVIDIA Nemotron via NIM + keyword-based fallback
- **Cache Klasifikasi** — TTLCache berbasis model + prompt + isi dokumen (default 24 jam, 2.048 entri)
- **Multi-Key NVIDIA** — Rotasi `NVIDIA_API_KEYS` atau `NVIDIA_API_KEY_1..3` saat rate limit/error
- **Health Check** — Monitoring status database dan semua sumber
- **Executable Build** — Kompilasi ke binary via PyInstaller
- **Structured Logging** — Debugging production-ready

---

## Langkah Selanjutnya (Roadmap)

- [ ] Tambah autentikasi JWT
- [x] Integrasi database MySQL untuk penyimpanan koleksi
- [ ] Task queue Celery untuk batch download
- [ ] Redis cache untuk multi-instance deployment