# CHANGELOG — Subtitle Metadata & Scraper

> Riwayat perubahan project. Untuk overview & cara pakai, lihat
> [`README.md`](./README.md). Untuk prioritas/status, lihat
> [`ROADMAP.md`](./ROADMAP.md). Untuk desain teknis, lihat
> [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 2026-09-13 (lanjutan) — Aturan baru di CONTRIBUTING.md

Ditambahkan section baru **"Prinsip Desain & Pemeliharaan Kode"** di
`CONTRIBUTING.md`, berisi lima aturan konkret yang lahir dari pengalaman
menangani `subtitle_metadata.py` pada tanggal yang sama:

1. **Satu fungsi, satu tanggung jawab** — dasar dari refactor
   `scrape_title()` (lihat entri di bawah).
2. **Helper privat/internal diberi prefix underscore** — konvensi yang
   baru diperkenalkan lewat helper `_send_scrape_request()`,
   `_compute_retry_wait()`, `_parse_scrape_response()`,
   `_target_status_failed()`, `_extract_valid_title()`.
3. **Update semua referensi tekstual saat fungsi diubah/dihapus** —
   ditulis langsung dari kasus nyata `is_processed()` yang sudah
   dihapus penggunaannya sejak BUG #3 tetapi docstring/komentar
   fungsi lain masih menyebutnya (baru dibersihkan terpisah, lihat
   entri "Pembersihan dead code" di bawah).
4. **Perubahan logic/percabangan wajib diverifikasi dengan test** —
   ditulis dari pengalaman refactor `scrape_title()`, di mana satu
   detail perilaku halus (`_target_status_failed()` yang sengaja tidak
   boleh menghentikan proses saat status tidak valid) baru benar-benar
   terverifikasi lewat test otomatis, bukan dari membaca kode saja.
5. **Config yang terikat tier akun/environment sebaiknya di `.env`** —
   dari diskusi soal `MIN_SECONDS_PER_REQUEST` yang nilainya terikat ke
   tier akun Firecrawl (belum dieksekusi, baru didokumentasikan sebagai
   aturan untuk perubahan konfigurasi berikutnya).

Aturan #1 secara eksplisit menyatakan hanya wajib untuk kode **baru**;
kode existing yang belum sesuai tidak langsung di-refactor tanpa
konfirmasi, mengikuti aturan "perubahan sekecil mungkin" yang sudah ada
sebelumnya di `CONTRIBUTING.md`.

Tidak ada perubahan pada kode (`.py`), schema, maupun CLI dari entri ini.

## 2026-09-13 (lanjutan) — Refactor scrape_title() menjadi fungsi-fungsi kecil

`scrape_title()` sebelumnya menangani banyak tanggung jawab sekaligus dalam
satu badan fungsi: loop antar source, loop retry HTTP 429, eksekusi request,
parsing response, deteksi halaman 404, dan ekstraksi title. Dipecah menjadi
lima helper privat (prefix `_`), masing-masing satu tanggung jawab:

- `_send_scrape_request(target_url, headers)` — mengirim satu request ke
  Firecrawl; menangani timeout/connection error/exception lain dan
  mengembalikan `None` jika request gagal total.
- `_compute_retry_wait(response, retry_count)` — menghitung waktu tunggu
  retry (mengikuti `Retry-After` atau exponential backoff).
- `_parse_scrape_response(response)` — parsing body JSON, mengembalikan
  `None` jika bukan JSON valid.
- `_target_status_failed(target_status)` — menilai apakah status HTTP
  website target menunjukkan kegagalan. Mempertahankan perilaku asli:
  jika `target_status` tidak bisa di-parse sebagai integer, ini **bukan**
  dianggap kegagalan (hanya di-log sebagai warning, tidak menghentikan
  proses source saat ini).
- `_extract_valid_title(metadata, markdown)` — mengambil title dari
  metadata/markdown lalu memvalidasi terhadap `NOT_FOUND_KEYWORDS`.

`scrape_title()` sekarang murni orkestrasi (loop source → loop retry →
panggil helper), dari sebelumnya satu fungsi besar bercabang dalam menjadi
enam statement inti per iterasi.

**Ini murni ekstraksi, bukan perubahan logic.** Urutan pengecekan, pesan
log, dan keputusan `break`/`continue`/`return` untuk setiap kasus dijaga
identik dengan versi sebelumnya — termasuk detail halus seperti
`_target_status_failed()` yang sengaja tidak menghentikan proses saat
statusnya tidak valid (perilaku asli yang mudah salah kalau di-refactor
ceroboh).

Verifikasi yang dilakukan:
- `python3 -m py_compile` — lolos;
- test verifikasi manual (`test_scrape_title_refactor.py`, tidak menjadi
  bagian permanen test suite) meng-cover 10 skenario: sukses di source
  pertama, 404 terdeteksi dari title, 404 terdeteksi dari isi markdown,
  429 lalu retry sukses di source yang sama, 429 exhausted lalu pindah
  source, timeout lalu pindah source, JSON tidak valid lalu pindah source,
  `target_status` tidak valid tidak menghentikan proses, semua source gagal
  mengembalikan string kosong, dan HTML entity/whitespace pada title
  di-decode & di-strip dengan benar. Seluruh 10 skenario lulus.

Tidak ada perubahan pada retry/rate-limit Firecrawl, daftar source, format
data yang disimpan ke SQLite, maupun CLI. Perubahan hanya pada struktur
internal `scrape_title()`.

## 2026-09-13 — Pembersihan dead code

- **`subtitle_metadata.py` — fungsi `is_processed()` dihapus.** Sejak
  perbaikan BUG #3 (lihat entri 2026-09-12), `process_files()` sudah beralih
  memakai `already_processed` (hasil `get_processed_codes()`) untuk keputusan
  skip per file, sehingga `is_processed()` tidak lagi dipanggil dari mana pun
  di file ini. Docstring `get_processed_codes()` sebelumnya juga masih
  menyebut "dipertahankan sebagai fungsi terpisah (dipakai saat memproses
  satu file dalam `process_files()`)" — pernyataan ini sudah tidak akurat dan
  ikut diperbaiki. Sisa referensi ke nama `is_processed()` di komentar
  `initialize_database()` dan `main()` juga dibersihkan.

  Tidak ada perubahan behavior: alur checkpoint tetap sama persis (satu
  batch query `IN (...)` sebelum Firecrawl, lihat `get_processed_codes()`),
  hanya menghapus fungsi yang sudah tidak terpakai beserta dokumentasi yang
  menyesatkan. Diverifikasi dengan `python3 -m py_compile` dan pencarian
  referensi (`grep`) untuk memastikan tidak ada pemanggil `is_processed()`
  yang tertinggal.

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

  > **Catatan (2026-09-13):** `is_processed()` yang disebut "tetap
  > dipertahankan untuk kompatibilitas" di atas ternyata sudah tidak
  > dipanggil dari mana pun setelah perbaikan ini — lihat entri
  > 2026-09-13 di atas untuk penghapusannya.
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
