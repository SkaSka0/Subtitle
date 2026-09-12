# ROADMAP — Subtitle Metadata & Scraper

> Dokumen prioritas pengembangan, status terkini, testing minimum, dan
> definition of done. Untuk overview & cara pakai, lihat
> [`README.md`](./README.md). Untuk desain teknis (schema, alur, aturan
> Firecrawl/sorting/metadata), lihat [`ARCHITECTURE.md`](./ARCHITECTURE.md).
> Untuk aturan wajib/dilarang sebelum mengubah kode, lihat
> [`CONTRIBUTING.md`](./CONTRIBUTING.md). Untuk riwayat perubahan, lihat
> [`CHANGELOG.md`](./CHANGELOG.md).
>
> Sebelum mengubah kode, baca dokumen ini beserta `ARCHITECTURE.md` dan
> `CONTRIBUTING.md`, lalu pertahankan data serta behavior yang sudah stabil.

---

## 1. Prioritas Roadmap

### P0 — Stabilitas & Keamanan

- [x] Kode A dipilih sebagai baseline.
- [x] Target `.vtt`.
- [x] Metadata filesystem ditambahkan.
- [x] `.env` untuk API key.
- [x] `.env.example`.
- [x] `.gitignore`.
- [x] Dependency awal ditentukan.
- [x] `uv` digunakan untuk virtual environment.
- [x] `.venv/` digunakan sebagai virtual environment directory.

> **Catatan:** file `.env.example` dan `.gitignore` sudah tersedia di repo,
> tetapi checklist ini belum ditandai selesai secara resmi di ROADMAP versi
> sebelumnya. Perlu diverifikasi dan ditandai `[x]` pada update berikutnya
> jika memang sudah final.

### P1 — Migrasi Database

- [x] Tentukan schema SQLite final.
- [x] Buat database initialization.
- [x] Buat migrator JSON → SQLite.
- [x] Verifikasi 300+ data existing.
- [x] Ubah checkpoint JSON → SQLite.
- [x] Pastikan existing subtitle tidak di-Firecrawl ulang setelah checkpoint SQLite aktif.
- [x] Simpan JSON sebagai backup selama masa transisi.
- [x] Verifikasi tidak ada duplicate `nama_file` pada data existing.
- [x] Normalisasi `downloaded = 1` untuk seluruh 330 record existing.

**Status P1:** Migrasi data selesai. Database berisi 330 record, seluruh
record existing saat ini `downloaded = 1`. `subtitle_metadata.py` sekarang
menggunakan SQLite sebagai checkpoint aktif, sehingga P1 selesai. Detail
schema dan proses migrasi ada di `ARCHITECTURE.md` bagian 2 dan 4.

### P2 — Recursive Processing

- [ ] Tambahkan `--recursive`.
- [ ] Simpan relative path.
- [ ] Amankan duplicate filename antar-folder.
- [ ] Test nested directory.

Spesifikasi target perilaku ada di `ARCHITECTURE.md` bagian 10.

### P3 — Robustness

- [ ] Scrape status.
- [ ] Error tracking.
- [x] Index database yang tepat (`nama_file`, `relative_path` — dibuat
      konsisten di `migrate_json_to_sqlite.py` maupun `subtitle_metadata.py`).
- [ ] Handling file dipindah/rename.
- [ ] Handling file berubah.
- [ ] Recovery ketika program berhenti di tengah proses.

### P4 — Maintenance

- [ ] Backup SQLite.
- [ ] Statistik scraping.
- [ ] CLI reporting.
- [ ] Database maintenance.
- [x] Export record `downloaded = 0` dari SQLite ke JSON melalui `export_pending_subtitles.py`.
- [x] README final.
- [x] Dokumentasi penggunaan (dipecah menjadi README, ROADMAP, ARCHITECTURE, CONTRIBUTING, CHANGELOG).

### P5 — Optional / Future

- [ ] Manual re-scrape.
- [ ] Update metadata ketika file berubah.
- [ ] Export SQLite → JSON/CSV.
- [ ] Search/query CLI.
- [ ] Parallelism yang tetap aman terhadap rate limit.
- [ ] Automated tests lebih lengkap.

---

## 2. Testing Minimum

### Test 1 — file baru

```text
001.vtt
```

Expected: `scan → DB check → belum ada → Firecrawl → SQLite`.

### Test 2 — file existing

Jalankan lagi. Expected: `scan → DB check → SKIP`. Tidak boleh memanggil
Firecrawl.

### Test 3 — campuran

Jika `001` dan `002` sudah ada dan `003` baru:

```text
001 → SKIP
002 → SKIP
003 → Firecrawl
```

**Status (2026-09-12):** diuji ulang setelah perbaikan batch checkpoint
query (lihat `CHANGELOG.md`) — hasil tetap sesuai ekspektasi: `001` dan `002`
di-skip tanpa memanggil Firecrawl, hanya `003` yang diproses dan disimpan,
tidak ada duplikat.

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

```text
JSON    : 330 record
SQLite  : 330 record
```

Expected: jumlah record sama, tidak ada data hilang, tidak ada duplicate
`nama_file` pada data existing, `results.json` tetap tersedia.

### Test 7 — Firecrawl failure

Jika scraping gagal:
- jangan tandai sebagai sukses;
- simpan error/status jika tersedia;
- jangan merusak database;
- lanjutkan file berikutnya jika aman.

---

## 3. Definition of Done

Perubahan dianggap selesai jika:
- kode dapat dijalankan;
- data existing tidak rusak;
- subtitle existing tidak di-Firecrawl ulang tanpa alasan;
- dependency terdokumentasi;
- syntax check berhasil;
- fitur terdampak telah diuji;
- behavior penting terdokumentasi;
- dokumentasi (`ROADMAP.md`/`ARCHITECTURE.md`/`CHANGELOG.md`) diperbarui jika
  diperlukan.

Untuk P1 migrasi database, tambahan kriteria:
- schema SQLite tersedia;
- database initialization tersedia;
- migrator JSON → SQLite tersedia;
- jumlah data hasil migrasi terverifikasi;
- JSON backup tetap tersedia;
- checkpoint utama telah menggunakan SQLite;
- existing subtitle terbukti di-skip sebelum Firecrawl.

---

## 4. Current State Snapshot

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
| Index SQLite (`nama_file`, `relative_path`) | Konsisten di migrator & `subtitle_metadata.py` |
| Sorting `export_pending_subtitles.py` | Diperbaiki agar kronologis, bukan string biasa |
| Batch checkpoint query di `subtitle_metadata.py` | Diperbaiki (satu query per batch, bukan per file) |
| Dokumentasi project | Dipecah: README, ROADMAP, ARCHITECTURE, CONTRIBUTING, CHANGELOG |

> **Catatan:** baris `.env.example`/`.gitignore` di tabel ini sengaja
> dipertahankan sama seperti ROADMAP versi sebelumnya ("Belum dibuat"),
> meskipun kedua file tersebut sudah ada di repo saat ini. Ini kemungkinan
> snapshot yang belum diperbarui di dokumen asli — perlu dikonfirmasi dan
> diperbaiki oleh maintainer project, bukan diubah diam-diam saat
> restrukturisasi dokumentasi.

### Next Step yang Disarankan

**Jangan melakukan refactor besar pada `subtitle_metadata.py`.**

P1 — migrasi checkpoint JSON → SQLite — sudah selesai. `subtitle_metadata.py`
sekarang menggunakan SQLite sebagai checkpoint utama dan melakukan database
check sebelum Firecrawl (alur lengkap ada di `ARCHITECTURE.md` bagian 5).

`results.json` jangan dihapus selama masa transisi dan tetap dipertahankan
sebagai backup.

Tahap berikutnya adalah recursive processing (P2) dan penggunaan
`relative_path` sebagai identitas aktif.
