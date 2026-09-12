# ROADMAP — Subtitle Metadata & Scraper

> Dokumen ini adalah sumber acuan utama untuk pengembangan project.
> Digunakan oleh developer maupun LLM/AI yang diminta memodifikasi kode project.
> Sebelum mengubah kode, baca dokumen ini dan pertahankan data serta behavior yang sudah stabil.

---

## 1. Tujuan Project

Tool Python CLI untuk memproses file subtitle `.vtt`, mengambil metadata/judul
melalui Firecrawl dari beberapa source, menyimpan metadata filesystem dan hasil
scraping, serta melewati subtitle yang sudah pernah diproses.

Arah pengembangan utama:
- mengganti JSON checkpoint dengan SQLite;
- mendukung recursive directory processing;
- menjaga agar subtitle existing tidak di-scrape ulang;
- tetap sederhana, mudah dipelihara, dan cocok untuk Linux/Arch Linux;
- menggunakan `uv` untuk mengelola virtual environment dan dependency Python.

---

## 2. Kondisi Saat Ini

### Baseline

Kode A dipilih sebagai baseline project. Kode B tidak digunakan.

Fitur Kode A yang sudah ada:
- Firecrawl API v2.
- Multiple scraping sources.
- Rate limiting.
- Retry.
- Checkpoint/resume berbasis JSON.
- Status `downloaded`.
- Timestamp proses.
- Metadata filesystem.
- Target file `.vtt`.
- Sorting berdasarkan waktu pembuatan file.
- Atomic JSON save.
- `.env` untuk API key.

### Metadata filesystem

Field yang digunakan:
- `file_created_at`
- `file_modified_at`
- `file_accessed_at`
- `file_size`

Timestamp proses scraping tetap terpisah.

### Catatan creation time

Gunakan `st_birthtime` jika tersedia. Pada platform yang tidak menyediakan
birth time dapat digunakan fallback `st_ctime`.

**Penting:** pada Linux, `st_ctime` adalah metadata change time, bukan selalu
creation time. Jangan menyebutnya sebagai creation time yang akurat tanpa
verifikasi.

---

## 3. Struktur Project Target

```text
subtitle-metadata/
├── subtitle_metadata.py
├── batch_add_extension.py
├── migrate_json_to_sqlite.py
├── export_pending_subtitles.py
├── requirements.txt
├── .env.example
├── .gitignore
├── ROADMAP.md
├── results.json           # backup data lama, lokal
├── .env                   # lokal, jangan commit
├── subtitles.db           # database lokal
└── .venv/                 # lokal, jangan commit
```

Nama `subtitle_metadata.py` dipilih sebagai nama yang paling sesuai dengan
fungsi Kode A saat ini.

`batch_add_extension.py` adalah tool terpisah untuk menambahkan ekstensi file.

`migrate_json_to_sqlite.py` digunakan untuk migrasi satu kali dari checkpoint
JSON lama ke SQLite.

---

## 4. Dependency dan Environment

`requirements.txt`:

```text
requests
python-dotenv
send2trash
```

`sqlite3` **tidak** dimasukkan karena merupakan standard library Python.

Standard library lain yang tidak perlu dimasukkan:
- `argparse`
- `json`
- `os`
- `sys`
- `pathlib`
- `datetime`
- `shutil`
- `time`
- `sqlite3`

### Virtual Environment

Project menggunakan **uv** untuk pengelolaan virtual environment.

Nama virtual environment:

```text
.venv/
```

Buat virtual environment:

```bash
uv venv
```

Aktifkan:

```bash
source .venv/bin/activate
```

Install dependency dari `requirements.txt`:

```bash
uv pip install -r requirements.txt
```

Jika dependency/project nantinya dipindahkan ke `pyproject.toml`, gunakan
workflow `uv sync` dan tetap gunakan `.venv` sebagai virtual environment
project.

Jangan memasang dependency project secara global jika dapat dihindari.

---

## 5. Environment dan Secret

Gunakan `.env` untuk API key.

`.env.example`:

```env
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
```

`.env` asli tidak boleh di-commit.

`.gitignore` minimal:

```text
.env
.venv/
__pycache__/
*.pyc
```

Jangan pernah hard-code API key ke source code.

---

## 6. Migrasi JSON → SQLite

### Status: MIGRASI DATA SELESAI

Data JSON existing telah berhasil dimigrasikan ke SQLite.

Jumlah data yang diverifikasi:

```text
JSON    : 330 record
SQLite  : 330 record
```

Tidak ditemukan duplicate berdasarkan `nama_file`.

Tujuan migrasi:

```text
results.json
     ↓ migrasi satu kali
subtitles.db
```

Migrator:
- membaca JSON lama;
- mempertahankan informasi penting;
- memasukkan data ke SQLite;
- menggunakan transaction agar migrasi dapat di-rollback jika gagal;
- tidak menghapus JSON;
- memverifikasi jumlah record sebelum dan sesudah migrasi;
- mempertahankan JSON sebagai backup selama masa transisi.

### Hasil Migrasi

```text
Record JSON       : 330
Record SQLite     : 330
Title kosong      : 0
Downloaded = true : 11 sebelum normalisasi
Downloaded = false: 319 sebelum normalisasi
```

Setelah migrasi, seluruh record existing dinormalisasi menjadi:

```text
downloaded = 1
```

Artinya seluruh 330 subtitle existing dianggap sudah diproses/downloaded
untuk kebutuhan checkpoint.

### Representasi `downloaded`

SQLite menggunakan:

```text
0 = false
1 = true
```

Kolom tetap menggunakan:

```sql
downloaded INTEGER NOT NULL DEFAULT 0
```

Tidak menggunakan tipe `BOOLEAN` karena SQLite merepresentasikan nilai boolean
secara praktis sebagai integer `0`/`1`.

### Aturan anti-rescrape

Data existing harus dikenali sebagai sudah diproses.

```text
001.vtt → sudah ada di DB → SKIP
002.vtt → sudah ada di DB → SKIP
003.vtt → belum ada → FIRECRAWL
```

**Jangan mengirim ulang data existing ke Firecrawl hanya karena storage berubah
dari JSON ke SQLite.**

### Backup

`results.json` **tidak dihapus** dan tetap dipertahankan sebagai backup selama
masa transisi.

---

## 7. Database

Gunakan **SQLite**.

Database target:

```text
subtitles.db
```

Alasan:
- tidak membutuhkan database server;
- tersedia melalui standard library;
- cocok untuk ratusan/ribuan subtitle;
- mendukung SQL;
- cocok sebagai checkpoint;
- mudah dibackup;
- baik untuk belajar database.

### Schema

Schema SQLite yang digunakan:

```sql
CREATE TABLE subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama_file TEXT NOT NULL,
    relative_path TEXT,
    title TEXT,
    downloaded INTEGER NOT NULL DEFAULT 0,
    file_created_at TEXT,
    file_modified_at TEXT,
    file_accessed_at TEXT,
    file_size INTEGER,
    scraped_at TEXT
);
```

Field tambahan tidak ditambahkan hanya untuk terlihat lengkap. Setiap field
harus mempunyai fungsi nyata.

Field yang dapat dipertimbangkan pada tahap berikutnya:
- `scrape_status`
- `scrape_error`
- checksum/hash file
- waktu update terakhir.

---

## 8. Identitas File

Checkpoint lama menggunakan nama file.

Hal ini cukup untuk satu direktori, tetapi tidak aman jika recursive:

```text
season1/ABC001.vtt
season2/ABC001.vtt
```

Keduanya harus dianggap file berbeda.

**Rekomendasi untuk tahap recursive:** gunakan `relative_path` sebagai identitas
file.

Contoh:

```text
season1/ABC001.vtt
season2/ABC001.vtt
```

Jangan menggunakan absolute path sebagai identitas utama karena dapat berubah
ketika folder project dipindahkan.

Saat ini data hasil migrasi legacy memiliki:

```text
relative_path = NULL
```

karena JSON lama belum memiliki informasi relative path.

---

## 9. Recursive Directory Processing

### Status: BELUM IMPLEMENTASI

Target:

```bash
python subtitle_metadata.py -d ~/subtitle --recursive
```

Perilaku:
- tanpa `--recursive`: hanya direktori target;
- dengan `--recursive`: scan direktori dan seluruh subfolder;
- hanya `.vtt`;
- relative path disimpan ke database;
- duplicate filename pada folder berbeda tetap aman.

Perhatikan file/folder tersembunyi dan buat behavior yang konsisten dengan tool
lain dalam project.

---

## 10. Alur Utama Target

```text
Start
  ↓
Load .env
  ↓
Open SQLite
  ↓
Scan target directory
  ↓
Filter .vtt
  ↓
Read filesystem metadata
  ↓
Check database
  ├── sudah diproses → SKIP
  └── belum diproses
          ↓
      Extract code
          ↓
      Firecrawl
          ↓
      Save/update SQLite
          ↓
      Next file
```

**Database check harus terjadi sebelum Firecrawl.**

Jangan membaca seluruh database ke memory hanya untuk melakukan checkpoint.
Gunakan query berdasarkan identitas file.

---

## 11. Processing Status

Jangan menyamakan:
- `scraped`
- `downloaded`

Contoh valid:

```text
scrape_status = success
downloaded = false
```

Jika status scraping ditambahkan, bedakan setidaknya:
- pending
- success
- failed

Error scraping sebaiknya dapat dilacak tanpa menganggap file berhasil.

---

## 12. Firecrawl

Endpoint saat ini:

```text
https://api.firecrawl.dev/v2/scrape
```

API key:

```text
FIRECRAWL_API_KEY
```

Pertahankan:
- retry;
- timeout;
- rate limiting;
- pengecekan status/error;
- not-found detection;
- ekstraksi title dari metadata/markdown.

Jangan menghapus rate limiting hanya untuk mempercepat scraping.

### Source saat ini

```text
https://123av.com/en/v/{code}
https://missav.ws/dm2/en/{code}
https://podjav.tv/movies/{code}/
```

Jangan menghapus/mengubah source secara diam-diam.

---

## 13. Sorting

Urutan default:

**oldest → newest**

berdasarkan filesystem creation timestamp yang tersedia.

Format tampilan:

```text
DD-MM-YYYY HH:MM:SS
```

Sorting harus menggunakan timestamp yang dapat dibandingkan secara benar,
bukan string tanggal lokal secara naif.

Jika timestamp sama:
1. relative path;
2. nama file sebagai tie-breaker bila diperlukan.

Nilai internal sorting tidak perlu disimpan sebagai field publik.

---

## 14. Metadata Filesystem

Target:
- `file_created_at`
- `file_modified_at`
- `file_accessed_at`
- `file_size`

Format tampilan timestamp:

```text
DD-MM-YYYY HH:MM:SS
```

Metadata filesystem dapat berubah setelah file dipindahkan, disalin, atau
dimodifikasi. Jangan menganggap metadata sebagai identitas file yang permanen.

Jika akurasi creation time Linux menjadi requirement penting, evaluasi `statx`
/ birth time sebelum menggunakan `st_ctime` sebagai klaim creation time.

---

## 15. `batch_add_extension.py`

Tool ini tetap terpisah.

Fitur yang sudah tersedia:
- tambah ekstensi;
- recursive `-r` / `--recursive`;
- dry-run;
- konfirmasi;
- `--yes`;
- duplicate handling;
- move duplicate;
- trash duplicate dengan `send2trash`;
- JSON history/log.

Jangan mencampurkan logic Firecrawl ke tool ini tanpa kebutuhan arsitektur
yang jelas.

---

## 16. Logging dan History

SQLite menjadi **source of truth** untuk data subtitle setelah checkpoint
dipindahkan sepenuhnya.

JSON tidak perlu ditulis ulang setiap checkpoint setelah migrasi selesai.

Selama masa transisi, `results.json` tetap dipertahankan sebagai backup.

Log operasional tetap dapat digunakan untuk:
- error;
- statistik run;
- debugging;
- audit aktivitas rename.

---

## 17. Backup

Database:

```text
subtitles.db
```

Backup dapat dibuat sederhana.

Target opsional:

```text
backup/
└── subtitles_YYYYMMDD_HHMMSS.db
```

Selama masa transisi:

```text
results.json
```

tetap dipertahankan sebagai backup hasil migrasi.

Jangan menambahkan backup otomatis sebelum kebutuhan tersebut jelas.

---

## 18. CLI Target

Contoh penggunaan:

```bash
python subtitle_metadata.py -d ~/subtitle
```

Recursive:

```bash
python subtitle_metadata.py -d ~/subtitle --recursive
```

Jika database dapat dikonfigurasi:

```bash
python subtitle_metadata.py -d ~/subtitle --db subtitles.db
```

Pertahankan compatibility dengan option lama sebisa mungkin.

---

## 19. Testing Minimum

### Test 1 — file baru

```text
001.vtt
```

Expected:

```text
scan → DB check → belum ada → Firecrawl → SQLite
```

### Test 2 — file existing

Jalankan lagi.

Expected:

```text
scan → DB check → SKIP
```

Tidak boleh memanggil Firecrawl.

### Test 3 — campuran

Jika `001` dan `002` sudah ada dan `003` baru:

```text
001 → SKIP
002 → SKIP
003 → Firecrawl
```

### Test 4 — recursive

```text
root/001.vtt
root/a/002.vtt
root/a/b/003.vtt
```

Dengan `--recursive`, ketiganya ditemukan.

### Test 5 — duplicate filename

```text
a/001.vtt
b/001.vtt
```

Harus dianggap dua file berbeda berdasarkan relative path.

### Test 6 — migrasi

Status:

```text
JSON    : 330 record
SQLite  : 330 record
```

Expected:
- jumlah record sama;
- tidak ada data hilang;
- tidak ada duplicate `nama_file` pada data existing;
- `results.json` tetap tersedia.

### Test 7 — Firecrawl failure

Jika scraping gagal:
- jangan tandai sebagai sukses;
- simpan error/status jika tersedia;
- jangan merusak database;
- lanjutkan file berikutnya jika aman.

---

# 20. Aturan untuk LLM / AI

## WAJIB

Sebelum mengubah kode:
1. baca `ROADMAP.md`;
2. periksa struktur project;
3. baca kode yang relevan;
4. pahami schema/data existing;
5. pertahankan behavior yang sudah bekerja;
6. buat perubahan sekecil mungkin;
7. lakukan syntax check;
8. test fungsi yang terdampak;
9. update ROADMAP jika status/arsitektur berubah.

## DILARANG

LLM/AI tidak boleh:
- menghapus data existing tanpa konfirmasi;
- menghapus database/JSON backup otomatis;
- melakukan re-scrape semua subtitle existing tanpa alasan;
- hard-code API key;
- memasukkan standard library ke requirements.txt;
- mengganti SQLite dengan database server tanpa alasan;
- menghapus retry/rate limit Firecrawl;
- mengubah source scraping secara diam-diam;
- mengubah format data existing tanpa migrasi;
- menyebut Linux `st_ctime` sebagai creation time secara pasti;
- melakukan refactor besar jika perubahan kecil sudah cukup.

Jika requirement ambigu:
1. jelaskan trade-off;
2. hindari keputusan yang berisiko data loss;
3. prioritaskan kompatibilitas data existing.

---

# 21. Prioritas Roadmap

## P0 — Stabilitas & Keamanan

- [x] Kode A dipilih sebagai baseline.
- [x] Target `.vtt`.
- [x] Metadata filesystem ditambahkan.
- [x] `.env` untuk API key.
- [ ] `.env.example`.
- [ ] `.gitignore`.
- [x] Dependency awal ditentukan.
- [x] `uv` digunakan untuk virtual environment.
- [x] `.venv/` digunakan sebagai virtual environment directory.

## P1 — Migrasi Database

- [x] Tentukan schema SQLite final.
- [x] Buat database initialization.
- [x] Buat migrator JSON → SQLite.
- [x] Verifikasi 300+ data existing.
- [x] Ubah checkpoint JSON → SQLite.
- [x] Pastikan existing subtitle tidak di-Firecrawl ulang setelah checkpoint SQLite aktif.
- [x] Simpan JSON sebagai backup selama masa transisi.
- [x] Verifikasi tidak ada duplicate `nama_file` pada data existing.
- [x] Normalisasi `downloaded = 1` untuk seluruh 330 record existing.

### P1 Status

**Migrasi data selesai.**

Database berisi:

```text
330 record
```

Seluruh record existing saat ini:

```text
downloaded = 1
```

`subtitle_metadata.py` sekarang menggunakan SQLite sebagai checkpoint aktif,
sehingga P1 selesai.

---

## P2 — Recursive Processing

- [ ] Tambahkan `--recursive`.
- [ ] Simpan relative path.
- [ ] Amankan duplicate filename antar-folder.
- [ ] Test nested directory.

## P3 — Robustness

- [ ] Scrape status.
- [ ] Error tracking.
- [ ] Index database yang tepat.
- [ ] Handling file dipindah/rename.
- [ ] Handling file berubah.
- [ ] Recovery ketika program berhenti di tengah proses.

## P4 — Maintenance

- [ ] Backup SQLite.
- [ ] Statistik scraping.
- [ ] CLI reporting.
- [ ] Database maintenance.
- [x] Export record `downloaded = 0` dari SQLite ke JSON melalui `export_pending_subtitles.py`.
- [ ] README final.
- [ ] Dokumentasi penggunaan.

## P5 — Optional / Future

- [ ] Manual re-scrape.
- [ ] Update metadata ketika file berubah.
- [ ] Export SQLite → JSON/CSV.
- [ ] Search/query CLI.
- [ ] Parallelism yang tetap aman terhadap rate limit.
- [ ] Automated tests lebih lengkap.

---

# 22. Definition of Done

Perubahan dianggap selesai jika:
- kode dapat dijalankan;
- data existing tidak rusak;
- subtitle existing tidak di-Firecrawl ulang tanpa alasan;
- dependency terdokumentasi;
- syntax check berhasil;
- fitur terdampak telah diuji;
- behavior penting terdokumentasi;
- ROADMAP diperbarui jika diperlukan.

Untuk P1 migrasi database, tambahan kriteria:
- schema SQLite tersedia;
- database initialization tersedia;
- migrator JSON → SQLite tersedia;
- jumlah data hasil migrasi terverifikasi;
- JSON backup tetap tersedia;
- checkpoint utama telah menggunakan SQLite;
- existing subtitle terbukti di-skip sebelum Firecrawl.

---

# 23. Current State Snapshot

**Per 2026-09-12**

| Komponen | Status |
|---|---|
| Python | Ada pada system Arch Linux |
| Package/environment manager | `uv` |
| Virtual environment | `.venv/` |
| Baseline | Kode A |
| Target file | `.vtt` |
| Scraper | Firecrawl API v2 |
| Storage lama | JSON |
| Storage target | SQLite |
| Existing data | 332 subtitle |
| Checkpoint lama | JSON |
| Checkpoint target | SQLite |
| Migrator JSON → SQLite | Selesai |
| Database initialization | Selesai |
| Data verification | 330 JSON = 330 SQLite |
| Duplicate `nama_file` | Tidak ditemukan |
| Existing `downloaded` | Semua `1` |
| JSON backup | `results.json` dipertahankan |
| SQLite database | `subtitles.db` |
| Checkpoint `subtitle_metadata.py` | SQLite aktif |
| Anti-rescrape via SQLite | Sudah diuji sebelum Firecrawl |
| Recursive scraper | Belum |
| Relative path | Belum digunakan sebagai identitas aktif |
| Filesystem metadata | Sudah diimplementasikan |
| API secret | `.env` |
| Dependency | `requests`, `python-dotenv`, `send2trash` |
| `.env.example` | Belum dibuat |
| `.gitignore` | Belum dibuat |
| Export pending subtitle ke JSON | Selesai dan sudah diuji |

### Next Step yang disarankan

> **Jangan melakukan refactor besar pada `subtitle_metadata.py`.**
>
> P1 — migrasi checkpoint JSON → SQLite — sudah selesai. `subtitle_metadata.py`
> sekarang menggunakan SQLite sebagai checkpoint utama dan melakukan database
> check sebelum Firecrawl.
>
> Alur aktif:
>
> ```text
> Scan .vtt
>    ↓
> Read filesystem metadata
>    ↓
> Query SQLite
>    ├── sudah ada → SKIP
>    └── belum ada
>            ↓
>        Extract code
>            ↓
>        Firecrawl
>            ↓
>        INSERT SQLite
> ```
>
> `results.json` jangan dihapus selama masa transisi dan tetap dipertahankan
> sebagai backup.
>
> Tahap berikutnya adalah recursive processing dan penggunaan `relative_path`
> sebagai identitas aktif.
---

# 24. Change Log

## 2026-09-06

- Kode A ditetapkan sebagai baseline.
- Kode B tidak digunakan.
- Target scraper ditetapkan `.vtt`.
- Metadata filesystem ditambahkan.
- Sorting diarahkan oldest → newest berdasarkan creation timestamp yang tersedia.
- Dependency awal: `requests`, `python-dotenv`, `send2trash`.
- `uv` digunakan sebagai environment/dependency manager project.
- Virtual environment project menggunakan `.venv/`.
- `.env` digunakan untuk `FIRECRAWL_API_KEY`.
- Diputuskan untuk beralih dari JSON checkpoint ke SQLite.
- Existing data berjumlah 300+ subtitle dan harus dipertahankan.
- Recursive processing ditetapkan sebagai pengembangan berikutnya.
- `.gitignore` menggunakan `.venv/` untuk mengecualikan virtual environment.
- Schema SQLite ditetapkan dengan tabel `subtitles`.
- Database `subtitles.db` berhasil dibuat.
- Migrator `migrate_json_to_sqlite.py` dibuat untuk migrasi JSON → SQLite.
- Migrasi berhasil dilakukan dari `results.json` ke `subtitles.db`.
- Hasil migrasi diverifikasi: **330 record JSON = 330 record SQLite**.
- Tidak ditemukan duplicate `nama_file` pada data existing.
- Tidak ditemukan title kosong pada hasil migrasi.
- `results.json` asli tidak dihapus dan tetap dipertahankan sebagai backup.
- Diputuskan bahwa `downloaded` pada SQLite menggunakan `INTEGER` dengan konvensi `0 = false` dan `1 = true`.
- Seluruh **330 record existing** dinormalisasi menjadi `downloaded = 1`.
- Checkpoint `subtitle_metadata.py` dipindahkan dari JSON ke SQLite; SQLite sekarang menjadi checkpoint utama.
- Database check dilakukan sebelum Firecrawl; test workflow membuktikan subtitle existing di-skip tanpa memanggil scraper.
- Record baru di-commit segera setelah scraping sukses agar checkpoint yang sudah tersimpan tetap aman jika proses berhenti di tengah jalan.
- `--db` tersedia dengan default `subtitles.db`; positional directory lama tetap didukung dan `-d/--directory` ditambahkan sesuai CLI target.
- Opsi `-o/--output` dipertahankan sebagai legacy, tetapi tidak lagi digunakan sebagai checkpoint dan tidak menulis ulang JSON.
- `export_pending_subtitles.py` dibuat sebagai utility terpisah untuk mengekspor record SQLite dengan `downloaded = 0` ke JSON.
- Export pending subtitle diuji dan berjalan dengan baik tanpa mengubah data di SQLite.
- Jumlah data SQLite bertambah menjadi **332 record** setelah pengujian workflow scraper.
