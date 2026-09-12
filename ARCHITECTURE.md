# ARCHITECTURE — Subtitle Metadata & Scraper

> Dokumen desain teknis: schema database, alur proses, aturan Firecrawl,
> sorting, dan format metadata. Untuk overview & cara pakai, lihat
> [`README.md`](./README.md). Untuk prioritas/status pengembangan, lihat
> [`ROADMAP.md`](./ROADMAP.md). Untuk aturan wajib/dilarang sebelum mengubah
> kode, lihat [`CONTRIBUTING.md`](./CONTRIBUTING.md).

---

## 1. Baseline dan Filosofi

Kode A dipilih sebagai baseline project. Kode B tidak digunakan.

Fitur Kode A yang sudah ada:
- Firecrawl API v2.
- Multiple scraping sources.
- Rate limiting.
- Retry.
- Checkpoint/resume berbasis JSON (sekarang SQLite, lihat bagian 4).
- Status `downloaded`.
- Timestamp proses.
- Metadata filesystem.
- Target file `.vtt`.
- Sorting berdasarkan waktu pembuatan file.
- Atomic JSON save.
- `.env` untuk API key.

Arah pengembangan utama:
- mengganti JSON checkpoint dengan SQLite;
- mendukung recursive directory processing;
- menjaga agar subtitle existing tidak di-scrape ulang;
- tetap sederhana, mudah dipelihara, dan cocok untuk Linux/Arch Linux;
- menggunakan `uv` untuk mengelola virtual environment dan dependency Python.

---

## 2. Database

Gunakan **SQLite**. Database target: `subtitles.db`.

Alasan:
- tidak membutuhkan database server;
- tersedia melalui standard library;
- cocok untuk ratusan/ribuan subtitle;
- mendukung SQL;
- cocok sebagai checkpoint;
- mudah dibackup;
- baik untuk belajar database.

### Schema

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

### Index aktif

```sql
CREATE INDEX IF NOT EXISTS idx_subtitles_nama_file
ON subtitles(nama_file);

CREATE INDEX IF NOT EXISTS idx_subtitles_relative_path
ON subtitles(relative_path);
```

Index ini dibuat baik oleh `migrate_json_to_sqlite.py` maupun oleh
`subtitle_metadata.py` (`initialize_database()`), sehingga database baru yang
dibuat langsung lewat `subtitle_metadata.py` tanpa migrasi lebih dulu tetap
memiliki index yang sama (lihat `CHANGELOG.md` 2026-09-12).

### Representasi `downloaded`

SQLite menggunakan:

```text
0 = false
1 = true
```

Kolom tetap menggunakan `INTEGER NOT NULL DEFAULT 0`. Tidak menggunakan tipe
`BOOLEAN` karena SQLite merepresentasikan nilai boolean secara praktis sebagai
integer `0`/`1`.

### Query database

Untuk contoh query (SELECT, filter, backup, dsb.) lihat
`sqlite_database_cheatsheet.md`.

---

## 3. Identitas File

Checkpoint lama menggunakan nama file. Ini cukup untuk satu direktori, tetapi
tidak aman jika recursive:

```text
season1/ABC001.vtt
season2/ABC001.vtt
```

Keduanya harus dianggap file berbeda.

**Rekomendasi untuk tahap recursive:** gunakan `relative_path` sebagai
identitas file. Jangan menggunakan absolute path sebagai identitas utama
karena dapat berubah ketika folder project dipindahkan.

Saat ini data hasil migrasi legacy memiliki `relative_path = NULL` karena
JSON lama belum memiliki informasi relative path. Checkpoint aktif saat ini
masih menggunakan `nama_file`.

---

## 4. Migrasi JSON → SQLite

### Status: MIGRASI DATA SELESAI

Data JSON existing telah berhasil dimigrasikan ke SQLite.

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

Migrator (`migrate_json_to_sqlite.py`):
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

Setelah migrasi, seluruh record existing dinormalisasi menjadi
`downloaded = 1`. Artinya seluruh 330 subtitle existing dianggap sudah
diproses/downloaded untuk kebutuhan checkpoint.

### Aturan anti-rescrape

Data existing harus dikenali sebagai sudah diproses.

```text
001.vtt → sudah ada di DB → SKIP
002.vtt → sudah ada di DB → SKIP
003.vtt → belum ada → FIRECRAWL
```

**Jangan mengirim ulang data existing ke Firecrawl hanya karena storage
berubah dari JSON ke SQLite.**

### Backup

`results.json` **tidak dihapus** dan tetap dipertahankan sebagai backup
selama masa transisi (lihat bagian 8).

---

## 5. Alur Utama

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

Sejak perbaikan 2026-09-12 (lihat `CHANGELOG.md`), pengecekan checkpoint
untuk satu batch scan dilakukan lewat satu query `IN (...)` (dipecah otomatis
sesuai batas variabel SQLite) atas `nama_file` dari file yang sedang di-scan
di folder target — bukan membaca seluruh tabel `subtitles`. Ini tetap sejalan
dengan aturan di atas karena cakupan query dibatasi pada jumlah file dalam
satu run, bukan seluruh isi database.

---

## 6. Processing Status

Jangan menyamakan `scraped` dengan `downloaded`.

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

## 7. Firecrawl

Endpoint saat ini:

```text
https://api.firecrawl.dev/v2/scrape
```

API key: `FIRECRAWL_API_KEY` (lihat `README.md` untuk setup `.env`).

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

## 8. Sorting

Urutan default: **oldest → newest**, berdasarkan filesystem creation
timestamp yang tersedia.

Format tampilan:

```text
DD-MM-YYYY HH:MM:SS
```

Sorting harus menggunakan timestamp yang dapat dibandingkan secara benar,
bukan string tanggal lokal secara naif.

Jika timestamp sama, tie-breaker:
1. relative path;
2. nama file.

Nilai internal sorting tidak perlu disimpan sebagai field publik.

**Catatan (2026-09-12):** field `file_created_at` disimpan sebagai TEXT
`DD-MM-YYYY HH:MM:SS`, sehingga `ORDER BY` langsung pada kolom ini di SQL
akan mengurutkan berdasarkan karakter pertama (hari), bukan secara
kronologis. Query yang butuh urutan kronologis harus menyusun ulang
komponennya ke format `YYYY-MM-DD HH:MM:SS` terlebih dahulu memakai
`substr()` (lihat `sqlite_database_cheatsheet.md` bagian 10 dan
`export_pending_subtitles.py`), bukan mengurutkan string apa adanya.

---

## 9. Metadata Filesystem

Field yang digunakan:
- `file_created_at`
- `file_modified_at`
- `file_accessed_at`
- `file_size`

Format tampilan timestamp: `DD-MM-YYYY HH:MM:SS`. Timestamp proses scraping
(`scraped_at`) tetap terpisah dari metadata filesystem.

Metadata filesystem dapat berubah setelah file dipindahkan, disalin, atau
dimodifikasi. Jangan menganggap metadata sebagai identitas file yang
permanen.

### Catatan creation time

Gunakan `st_birthtime` jika tersedia. Pada platform yang tidak menyediakan
birth time dapat digunakan fallback `st_ctime`.

**Penting:** pada Linux, `st_ctime` adalah metadata change time, bukan selalu
creation time. Jangan menyebutnya sebagai creation time yang akurat tanpa
verifikasi. Jika akurasi creation time Linux menjadi requirement penting,
evaluasi `statx` / birth time sebelum menggunakan `st_ctime` sebagai klaim
creation time.

---

## 10. Recursive Directory Processing

### Status: BELUM IMPLEMENTASI

Target:

```bash
python subtitle_metadata.py -d ~/subtitle --recursive
```

Perilaku target:
- tanpa `--recursive`: hanya direktori target;
- dengan `--recursive`: scan direktori dan seluruh subfolder;
- hanya `.vtt`;
- relative path disimpan ke database;
- duplicate filename pada folder berbeda tetap aman (lihat bagian 3 —
  Identitas File).

Perhatikan file/folder tersembunyi dan buat behavior yang konsisten dengan
tool lain dalam project.

---

## 11. Logging dan History

SQLite menjadi **source of truth** untuk data subtitle setelah checkpoint
dipindahkan sepenuhnya. JSON tidak perlu ditulis ulang setiap checkpoint
setelah migrasi selesai. Selama masa transisi, `results.json` tetap
dipertahankan sebagai backup.

Log operasional tetap dapat digunakan untuk:
- error;
- statistik run;
- debugging;
- audit aktivitas rename (lihat `.history/` di `batch_add_extension.py`).

---

## 12. Backup

Database: `subtitles.db`. Backup dapat dibuat sederhana. Target opsional:

```text
backup/
└── subtitles_YYYYMMDD_HHMMSS.db
```

Selama masa transisi, `results.json` tetap dipertahankan sebagai backup hasil
migrasi.

Jangan menambahkan backup otomatis sebelum kebutuhan tersebut jelas.

---

## 13. Batas Antar Tools

`batch_add_extension.py` tetap terpisah dari `subtitle_metadata.py`. Jangan
mencampurkan logic Firecrawl ke tool ini tanpa kebutuhan arsitektur yang
jelas. Fitur yang sudah tersedia di dalamnya: tambah ekstensi, recursive
(`-r`/`--recursive`), dry-run, konfirmasi, `--yes`, duplicate handling (move
atau trash via `send2trash`), dan JSON history/log — lihat `README.md` untuk
cara pakai.
