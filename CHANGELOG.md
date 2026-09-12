# CHANGELOG — Subtitle Metadata & Scraper

> Riwayat perubahan project. Untuk overview & cara pakai, lihat
> [`README.md`](./README.md). Untuk prioritas/status, lihat
> [`ROADMAP.md`](./ROADMAP.md). Untuk desain teknis, lihat
> [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 2026-09-12 (lanjutan) — Restrukturisasi dokumentasi

`ROADMAP.md` sebelumnya berisi campuran overview project, desain teknis,
prioritas roadmap, aturan kontribusi, dan change log dalam satu file yang
sudah sangat panjang, sementara `README.md` belum ada. Dokumentasi dipecah
menjadi lima file agar lebih mudah dibaca sesuai kebutuhan, tanpa
menghilangkan isi apa pun — hanya dipindahkan ke lokasi yang lebih sesuai:

- **`README.md`** (baru) — tujuan project, struktur folder, setup
  environment (`uv`, `.env`), dan cara pakai keempat tool CLI.
- **`ROADMAP.md`** (dirampingkan) — prioritas P0–P5, testing minimum,
  definition of done, dan current state snapshot.
- **`ARCHITECTURE.md`** (baru) — baseline, schema & index database, identitas
  file, riwayat migrasi JSON→SQLite, alur utama, aturan Firecrawl, sorting,
  format metadata filesystem, recursive processing target, logging, backup.
- **`CONTRIBUTING.md`** (baru) — aturan wajib/dilarang untuk developer
  maupun LLM/AI sebelum mengubah kode.
- **`CHANGELOG.md`** (dokumen ini, baru) — riwayat perubahan lengkap.

Setiap dokumen baru diberi tautan silang ke dokumen lain di bagian atas,
supaya aturan "baca dokumentasi sebelum ubah kode" (lihat `CONTRIBUTING.md`)
tetap berlaku meskipun isinya sudah tidak dalam satu file.

Satu inkonsistensi ditemukan saat proses pemindahan: checklist
`.env.example`/`.gitignore` di ROADMAP masih menandai "belum dibuat",
padahal kedua file tersebut sudah ada di repo. Status ini **sengaja tidak
diubah** saat restrukturisasi (lihat catatan di `ROADMAP.md`) karena
mengoreksi status semacam ini bukan bagian dari permintaan pemecahan
dokumen — perlu diverifikasi dan diperbarui terpisah oleh maintainer.

## 2026-09-12 — Perbaikan bug hasil code review

Empat bug/optimisasi ditemukan lewat review menyeluruh terhadap seluruh
skrip di repo, kemudian diperbaiki satu per satu dengan prinsip perubahan
sekecil mungkin (tidak mengubah schema, source, CLI, maupun behavior
anti-rescrape).

- **`export_pending_subtitles.py` — bug sorting.** Query ekspor sebelumnya
  melakukan `ORDER BY file_created_at ASC` langsung pada kolom TEXT berformat
  `DD-MM-YYYY HH:MM:SS`, sehingga urutan yang dihasilkan salah secara
  kronologis (mengurutkan berdasarkan karakter hari, bukan tahun/bulan/hari).
  Diperbaiki dengan menyusun ulang komponen tanggal ke format
  `YYYY-MM-DD HH:MM:SS` memakai `substr()` sebelum diurutkan, mengikuti pola
  yang sudah didokumentasikan di `sqlite_database_cheatsheet.md` bagian 10.
  Baris dengan `file_created_at` kosong/NULL kini konsisten diletakkan di
  akhir hasil, bukan tercampur di awal. Diverifikasi dengan unit test
  menggunakan data yang sengaja dibuat rawan salah urut (15-12-2025 vs
  01-01-2026); hasil setelah perbaikan sudah benar secara kronologis.
- **`subtitle_metadata.py` — index tidak dibuat pada database baru.**
  `initialize_database()` sebelumnya hanya membuat tabel `subtitles` tanpa
  index, padahal `migrate_json_to_sqlite.py` sudah membuat
  `idx_subtitles_nama_file` dan `idx_subtitles_relative_path`. Jika
  `subtitle_metadata.py` dijalankan pertama kali pada database baru tanpa
  migrasi lebih dulu, pengecekan checkpoint akan melakukan full table scan
  yang makin lambat seiring data bertambah. Ditambahkan
  `CREATE INDEX IF NOT EXISTS` untuk kedua index tersebut di
  `initialize_database()`, sehingga database baru maupun hasil migrasi
  sekarang selalu punya index yang sama. Tidak mengubah data existing.
- **`subtitle_metadata.py` — query checkpoint dilakukan dua kali per file.**
  Sebelumnya `main()` memanggil `is_processed()` satu per satu untuk
  menghitung `existing_count` (hanya untuk log info), lalu `process_files()`
  memanggil `is_processed()` lagi untuk file yang sama saat memutuskan
  skip/proses — total dua query SQLite per file. Ditambahkan fungsi
  `get_processed_codes()` yang mengecek seluruh nama_file dari file yang
  sedang di-scan dalam satu (atau beberapa, dipecah otomatis per batas
  variabel SQLite) query `IN (...)`. Hasilnya berupa satu `set` yang dipakai
  ulang baik untuk log info maupun untuk skip logic di `process_files()`.
  Fungsi `is_processed()` individual tetap dipertahankan tanpa perubahan
  untuk kompatibilitas. Perbaikan ini tidak melanggar aturan "jangan membaca
  seluruh database ke memory hanya untuk checkpoint" karena cakupan query
  tetap dibatasi pada file-file dalam satu batch scan, bukan seluruh isi
  tabel `subtitles`.
- **`subtitle_metadata.py` — exception handling belum menangkap
  `sqlite3.Error`.** Blok exception di `main()` sebelumnya hanya menangkap
  `FileNotFoundError`, `NotADirectoryError`, `PermissionError`, `ValueError`,
  dan `OSError`. Error SQLite yang muncul di runtime setelah database
  berhasil dibuka (misalnya "database is locked" saat commit) tidak
  tertangkap dan akan crash dengan traceback mentah. Ditambahkan
  `sqlite3.Error` ke daftar exception yang ditangani, sehingga error jenis
  ini sekarang tampil sebagai pesan `[ERROR]` yang konsisten dengan error
  lain di aplikasi.

Verifikasi yang dilakukan sebelum perubahan dianggap selesai:
- syntax check (`python3 -m py_compile`) pada kedua file yang diubah;
- unit test untuk `get_processed_codes()` (batch check akurat, list kosong,
  chunking untuk >900 kode) dan untuk query sorting baru di
  `export_pending_subtitles.py`;
- test end-to-end skenario "campuran" (Test 3 di `ROADMAP.md`): file
  existing (`001`, `002`) tetap ter-skip tanpa memanggil Firecrawl, file
  baru (`003`) diproses dan tersimpan, total record di database bertambah
  sesuai ekspektasi tanpa duplikat.

Tidak ada perubahan pada schema tabel `subtitles`, argumen CLI, daftar
source scraping, retry/rate limiting Firecrawl, maupun format data existing.
`results.json` dan `subtitles.db` tidak disentuh/dihapus oleh perbaikan ini.

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
