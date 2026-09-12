# SQLite Database Cheatsheet — SubtitleHarvester

> Cheatsheet untuk database SQLite project **SubtitleHarvester**.
>
> Database utama project:
>
> ```text
> subtitles.db
> ```
>
> Schema aktif:
>
> ```sql
> CREATE TABLE subtitles (
>     id INTEGER PRIMARY KEY AUTOINCREMENT,
>     nama_file TEXT NOT NULL,
>     relative_path TEXT,
>     title TEXT,
>     downloaded INTEGER NOT NULL DEFAULT 0,
>     file_created_at TEXT,
>     file_modified_at TEXT,
>     file_accessed_at TEXT,
>     file_size INTEGER,
>     scraped_at TEXT
> );
> ```
>
> Project menggunakan SQLite sebagai checkpoint utama. `downloaded` menggunakan
> `0 = false` dan `1 = true`. Jangan menghapus database atau `results.json`
> backup secara sembarangan.

---

## Daftar Isi

1. [Membuka Database](#1-membuka-database)
2. [Perintah SQLite CLI](#2-perintah-sqlite-cli)
3. [Melihat Struktur Database](#3-melihat-struktur-database)
4. [SELECT — Membaca Data](#4-select--membaca-data)
5. [Perintah yang Sering Dipakai di Project](#5-perintah-yang-sering-dipakai-di-project)
6. [INSERT — Menambah Data](#6-insert--menambah-data)
7. [UPDATE — Mengubah Data](#7-update--mengubah-data)
8. [DELETE — Menghapus Data](#8-delete--menghapus-data)
9. [WHERE — Filter Data](#9-where--filter-data)
10. [ORDER BY — Mengurutkan Data](#10-order-by--mengurutkan-data)
11. [LIMIT dan OFFSET](#11-limit-dan-offset)
12. [COUNT, MIN, MAX, AVG, SUM](#12-count-min-max-avg-sum)
13. [GROUP BY dan HAVING](#13-group-by-dan-having)
14. [LIKE dan Pencarian](#14-like-dan-pencarian)
15. [NULL](#15-null)
16. [DISTINCT dan Duplicate Check](#16-distinct-dan-duplicate-check)
17. [JOIN](#17-join)
18. [CASE](#18-case)
19. [Subquery](#19-subquery)
20. [Transaction](#20-transaction)
21. [Index](#21-index)
22. [ALTER TABLE](#22-alter-table)
23. [Backup dan Restore](#23-backup-dan-restore)
24. [Maintenance dan Pemeriksaan Database](#24-maintenance-dan-pemeriksaan-database)
25. [Export dan Import](#25-export-dan-import)
26. [SQLite CLI yang Berguna](#26-sqlite-cli-yang-berguna)
27. [Contoh Query Praktis](#27-contoh-query-praktis)
28. [Perintah Berisiko](#28-perintah-berisiko)
29. [Quick Reference](#29-quick-reference)

---

# 1. Membuka Database

Dari terminal:

```bash
sqlite3 subtitles.db
```

Membuka database dengan path tertentu:

```bash
sqlite3 /path/to/subtitles.db
```

Jika database belum ada, `sqlite3` dapat membuat file database baru. Karena itu,
pastikan nama/path database benar sebelum menjalankan perintah.

Keluar dari SQLite:

```sql
.quit
```

atau:

```text
Ctrl+D
```

---

# 2. Perintah SQLite CLI

Perintah yang diawali `.` adalah perintah khusus SQLite CLI, bukan SQL.

## Melihat semua tabel

```sql
.tables
```

## Melihat schema semua object

```sql
.schema
```

## Melihat schema tabel `subtitles`

```sql
.schema subtitles
```

## Melihat bantuan

```sql
.help
```

## Melihat database yang sedang dibuka

```sql
.databases
```

## Keluar

```sql
.quit
```

---

# 3. Melihat Struktur Database

## Melihat schema tabel

```sql
SELECT sql
FROM sqlite_master
WHERE type = 'table'
  AND name = 'subtitles';
```

Penjelasan: mengambil SQL yang digunakan untuk membuat tabel `subtitles`.

## Melihat daftar kolom

```sql
PRAGMA table_info(subtitles);
```

Penjelasan: menampilkan nama kolom, tipe data, apakah `NOT NULL`, default value,
dan informasi primary key.

## Melihat semua object database

```sql
SELECT type, name, tbl_name
FROM sqlite_master
ORDER BY type, name;
```

Penjelasan: berguna ketika database sudah memiliki index, view, atau object lain.

---

# 4. SELECT — Membaca Data

## Semua data

```sql
SELECT *
FROM subtitles;
```

Penjelasan: mengambil seluruh kolom dan seluruh record.

> Untuk database besar, hindari `SELECT *` jika hanya membutuhkan beberapa kolom.

## Kolom tertentu

```sql
SELECT id, nama_file, title
FROM subtitles;
```

## Beberapa metadata

```sql
SELECT
    id,
    nama_file,
    title,
    downloaded,
    file_size,
    scraped_at
FROM subtitles;
```

## Satu record berdasarkan ID

```sql
SELECT *
FROM subtitles
WHERE id = 1;
```

---

# 5. Perintah yang Sering Dipakai di Project

Bagian ini berisi query yang paling relevan dengan workflow SubtitleHarvester.

## 5.1 Jumlah seluruh subtitle

```sql
SELECT COUNT(*) AS total
FROM subtitles;
```

Penjelasan: menghitung jumlah seluruh record.

## 5.2 Melihat satu data paling baru

Jika yang dimaksud "paling baru" adalah record yang terakhir masuk ke SQLite:

```sql
SELECT *
FROM subtitles
ORDER BY id DESC
LIMIT 1;
```

Penjelasan:
- `ORDER BY id DESC` = ID terbesar lebih dahulu.
- `LIMIT 1` = hanya satu record.

## 5.3 Melihat 10 data paling baru

```sql
SELECT *
FROM subtitles
ORDER BY id DESC
LIMIT 10;
```

## 5.4 Melihat subtitle yang belum downloaded

```sql
SELECT *
FROM subtitles
WHERE downloaded = 0;
```

## 5.5 Menghitung subtitle yang belum downloaded

```sql
SELECT COUNT(*) AS pending
FROM subtitles
WHERE downloaded = 0;
```

## 5.6 Melihat subtitle yang sudah downloaded

```sql
SELECT *
FROM subtitles
WHERE downloaded = 1;
```

## 5.7 Melihat file dan title saja

```sql
SELECT nama_file, title
FROM subtitles
ORDER BY id DESC;
```

## 5.8 Mencari file tertentu

```sql
SELECT *
FROM subtitles
WHERE nama_file = 'ABC001';
```

## 5.9 Mengecek apakah file sudah ada

```sql
SELECT 1
FROM subtitles
WHERE nama_file = 'ABC001'
LIMIT 1;
```

Ini sejalan dengan prinsip checkpoint project: database diperiksa sebelum
Firecrawl sehingga subtitle yang sudah diproses dapat di-skip.

## 5.10 Melihat record berdasarkan status

```sql
SELECT
    id,
    nama_file,
    title,
    downloaded
FROM subtitles
ORDER BY downloaded ASC, id DESC;
```

Dengan query ini, `downloaded = 0` muncul lebih dahulu.

---

# 6. INSERT — Menambah Data

## Insert sederhana

```sql
INSERT INTO subtitles (nama_file, title)
VALUES ('ABC001', 'Example Title');
```

Kolom lain akan menggunakan `NULL` atau default value sesuai schema.

## Insert lengkap

```sql
INSERT INTO subtitles (
    nama_file,
    relative_path,
    title,
    downloaded,
    file_created_at,
    file_modified_at,
    file_accessed_at,
    file_size,
    scraped_at
)
VALUES (
    'ABC001',
    NULL,
    'Example Title',
    0,
    '12-09-2026 20:00:00',
    '12-09-2026 20:00:00',
    '12-09-2026 20:00:00',
    123456,
    '12-09-2026 20:05:00'
);
```

> Hati-hati melakukan `INSERT` manual ke database production/project. Bisa
> menyebabkan duplicate checkpoint atau data yang tidak konsisten.

## Melihat ID record setelah INSERT

SQLite dapat menggunakan:

```sql
SELECT last_insert_rowid();
```

---

# 7. UPDATE — Mengubah Data

## Mengubah satu title

```sql
UPDATE subtitles
SET title = 'Judul Baru'
WHERE id = 1;
```

## Menandai satu subtitle sebagai downloaded

```sql
UPDATE subtitles
SET downloaded = 1
WHERE id = 1;
```

## Menandai satu subtitle sebagai belum downloaded

```sql
UPDATE subtitles
SET downloaded = 0
WHERE id = 1;
```

## Mengubah berdasarkan nama file

```sql
UPDATE subtitles
SET downloaded = 1
WHERE nama_file = 'ABC001';
```

## Update beberapa kolom

```sql
UPDATE subtitles
SET
    title = 'Judul Baru',
    downloaded = 1
WHERE id = 1;
```

> **Selalu gunakan `WHERE`** kecuali memang sengaja ingin mengubah seluruh tabel.

Sebelum menjalankan `UPDATE`, cek targetnya terlebih dahulu:

```sql
SELECT *
FROM subtitles
WHERE id = 1;
```

---

# 8. DELETE — Menghapus Data

## Menghapus satu record berdasarkan ID

```sql
DELETE FROM subtitles
WHERE id = 1;
```

## Menghapus berdasarkan nama file

```sql
DELETE FROM subtitles
WHERE nama_file = 'ABC001';
```

## Menghapus semua record yang downloaded = 0

```sql
DELETE FROM subtitles
WHERE downloaded = 0;
```

> **BERBAHAYA:** jangan menjalankan `DELETE` tanpa memahami targetnya.

Untuk melihat target sebelum menghapus:

```sql
SELECT *
FROM subtitles
WHERE downloaded = 0;
```

## Menghapus seluruh isi tabel

```sql
DELETE FROM subtitles;
```

Ini menghapus seluruh record tetapi mempertahankan tabel.

> Jangan gunakan ini pada database project tanpa backup dan alasan yang jelas.

---

# 9. WHERE — Filter Data

## Sama dengan

```sql
SELECT *
FROM subtitles
WHERE downloaded = 0;
```

## Tidak sama

```sql
SELECT *
FROM subtitles
WHERE downloaded != 1;
```

## Lebih besar

```sql
SELECT *
FROM subtitles
WHERE id > 300;
```

## Lebih kecil

```sql
SELECT *
FROM subtitles
WHERE id < 100;
```

## Range

```sql
SELECT *
FROM subtitles
WHERE id BETWEEN 100 AND 200;
```

## Beberapa nilai

```sql
SELECT *
FROM subtitles
WHERE downloaded IN (0, 1);
```

## Kondisi AND

```sql
SELECT *
FROM subtitles
WHERE downloaded = 0
  AND file_size > 100000;
```

## Kondisi OR

```sql
SELECT *
FROM subtitles
WHERE nama_file = 'ABC001'
   OR nama_file = 'ABC002';
```

## NOT

```sql
SELECT *
FROM subtitles
WHERE NOT downloaded = 1;
```

---

# 10. ORDER BY — Mengurutkan Data

## ID kecil → besar

```sql
SELECT *
FROM subtitles
ORDER BY id ASC;
```

## ID besar → kecil

```sql
SELECT *
FROM subtitles
ORDER BY id DESC;
```

## Nama file A → Z

```sql
SELECT *
FROM subtitles
ORDER BY nama_file ASC;
```

## Nama file Z → A

```sql
SELECT *
FROM subtitles
ORDER BY nama_file DESC;
```

## Urut berdasarkan ukuran file

```sql
SELECT nama_file, file_size
FROM subtitles
ORDER BY file_size DESC;
```

## Urut berdasarkan status kemudian ID

```sql
SELECT *
FROM subtitles
ORDER BY downloaded ASC, id DESC;
```

### Catatan penting tentang timestamp project

Field timestamp project disimpan sebagai text dengan format:

```text
DD-MM-YYYY HH:MM:SS
```

Format tersebut **tidak aman untuk langsung diurutkan secara alfabetis** sebagai
tanggal.

Contoh yang tidak direkomendasikan:

```sql
SELECT *
FROM subtitles
ORDER BY file_created_at DESC;
```

Jika ingin mengurutkan `file_created_at` secara kronologis di SQLite, ubah
sementara komponennya ke format `YYYY-MM-DD HH:MM:SS`:

```sql
SELECT *
FROM subtitles
ORDER BY
    substr(file_created_at, 7, 4) || '-' ||
    substr(file_created_at, 4, 2) || '-' ||
    substr(file_created_at, 1, 2) || ' ' ||
    substr(file_created_at, 12, 8) DESC;
```

Penjelasan:
- `substr(..., 7, 4)` mengambil tahun.
- `substr(..., 4, 2)` mengambil bulan.
- `substr(..., 1, 2)` mengambil hari.
- hasilnya disusun menjadi format yang dapat dibandingkan secara kronologis.

---

# 11. LIMIT dan OFFSET

## 5 record pertama

```sql
SELECT *
FROM subtitles
LIMIT 5;
```

## 5 record terbaru

```sql
SELECT *
FROM subtitles
ORDER BY id DESC
LIMIT 5;
```

## Pagination

```sql
SELECT *
FROM subtitles
ORDER BY id ASC
LIMIT 20 OFFSET 0;
```

Halaman kedua:

```sql
SELECT *
FROM subtitles
ORDER BY id ASC
LIMIT 20 OFFSET 20;
```

Halaman ketiga:

```sql
SELECT *
FROM subtitles
ORDER BY id ASC
LIMIT 20 OFFSET 40;
```

---

# 12. COUNT, MIN, MAX, AVG, SUM

## COUNT

```sql
SELECT COUNT(*)
FROM subtitles;
```

## COUNT dengan alias

```sql
SELECT COUNT(*) AS total_subtitles
FROM subtitles;
```

## Jumlah pending

```sql
SELECT COUNT(*) AS pending
FROM subtitles
WHERE downloaded = 0;
```

## Ukuran file terbesar

```sql
SELECT MAX(file_size) AS largest_file
FROM subtitles;
```

## Ukuran file terkecil

```sql
SELECT MIN(file_size) AS smallest_file
FROM subtitles;
```

## Rata-rata ukuran file

```sql
SELECT AVG(file_size) AS average_file_size
FROM subtitles;
```

## Total ukuran seluruh file

```sql
SELECT SUM(file_size) AS total_file_size
FROM subtitles;
```

---

# 13. GROUP BY dan HAVING

## Jumlah berdasarkan downloaded

```sql
SELECT
    downloaded,
    COUNT(*) AS total
FROM subtitles
GROUP BY downloaded;
```

Hasilnya akan menunjukkan jumlah record untuk `0` dan `1`.

## Hanya kelompok dengan jumlah tertentu

```sql
SELECT
    downloaded,
    COUNT(*) AS total
FROM subtitles
GROUP BY downloaded
HAVING COUNT(*) > 10;
```

`HAVING` digunakan untuk memfilter hasil setelah `GROUP BY`.

---

# 14. LIKE dan Pencarian

## Nama file mengandung teks

```sql
SELECT *
FROM subtitles
WHERE nama_file LIKE '%ABC%';
```

## Title mengandung teks

```sql
SELECT *
FROM subtitles
WHERE title LIKE '%example%';
```

## Dimulai dengan teks

```sql
SELECT *
FROM subtitles
WHERE nama_file LIKE 'ABC%';
```

## Diakhiri dengan teks

```sql
SELECT *
FROM subtitles
WHERE nama_file LIKE '%001';
```

## Case-insensitive sederhana

SQLite `LIKE` umumnya case-insensitive untuk karakter ASCII:

```sql
SELECT *
FROM subtitles
WHERE title LIKE '%example%';
```

---

# 15. NULL

`NULL` berarti tidak memiliki nilai, bukan string kosong.

## Mencari relative_path yang NULL

```sql
SELECT *
FROM subtitles
WHERE relative_path IS NULL;
```

## Mencari relative_path yang sudah ada

```sql
SELECT *
FROM subtitles
WHERE relative_path IS NOT NULL;
```

## Jangan gunakan ini untuk NULL

```sql
SELECT *
FROM subtitles
WHERE relative_path = NULL;
```

Gunakan:

```sql
SELECT *
FROM subtitles
WHERE relative_path IS NULL;
```

Pada data hasil migrasi legacy, `relative_path` memang `NULL` karena JSON lama
belum mempunyai informasi tersebut.

---

# 16. DISTINCT dan Duplicate Check

## Nilai downloaded yang tersedia

```sql
SELECT DISTINCT downloaded
FROM subtitles;
```

## Daftar nama file unik

```sql
SELECT DISTINCT nama_file
FROM subtitles;
```

## Mencari duplicate nama_file

```sql
SELECT
    nama_file,
    COUNT(*) AS jumlah
FROM subtitles
GROUP BY nama_file
HAVING COUNT(*) > 1;
```

Jika query tidak menghasilkan baris, berarti tidak ditemukan duplicate berdasarkan
`nama_file`.

## Mencari duplicate title

```sql
SELECT
    title,
    COUNT(*) AS jumlah
FROM subtitles
GROUP BY title
HAVING COUNT(*) > 1;
```

> Duplicate title belum tentu merupakan masalah. Berbeda dengan identitas file,
> beberapa file dapat secara sah mempunyai title yang sama.

---

# 17. JOIN

Schema saat ini hanya mempunyai satu tabel utama, jadi `JOIN` belum diperlukan
untuk workflow aktif. Namun ini penting dipahami untuk pengembangan database.

Contoh jika nanti terdapat tabel `sources`:

```sql
SELECT
    subtitles.nama_file,
    subtitles.title,
    sources.name
FROM subtitles
JOIN sources
    ON subtitles.id = sources.subtitle_id;
```

`JOIN` menggabungkan data dari beberapa tabel berdasarkan hubungan antar-kolom.

---

# 18. CASE

## Menampilkan status sebagai teks

```sql
SELECT
    nama_file,
    title,
    CASE
        WHEN downloaded = 1 THEN 'Downloaded'
        WHEN downloaded = 0 THEN 'Pending'
        ELSE 'Unknown'
    END AS status
FROM subtitles;
```

## Menghitung status sekaligus

```sql
SELECT
    CASE
        WHEN downloaded = 1 THEN 'Downloaded'
        ELSE 'Pending'
    END AS status,
    COUNT(*) AS total
FROM subtitles
GROUP BY status;
```

---

# 19. Subquery

## Mencari record dengan ID terbesar

```sql
SELECT *
FROM subtitles
WHERE id = (
    SELECT MAX(id)
    FROM subtitles
);
```

## Mencari file dengan ukuran terbesar

```sql
SELECT *
FROM subtitles
WHERE file_size = (
    SELECT MAX(file_size)
    FROM subtitles
);
```

## Mencari record yang title-nya sama dengan title record tertentu

```sql
SELECT *
FROM subtitles
WHERE title = (
    SELECT title
    FROM subtitles
    WHERE id = 1
);
```

---

# 20. Transaction

Transaction berguna agar beberapa perubahan dapat dianggap sebagai satu unit.

## Memulai transaction

```sql
BEGIN TRANSACTION;
```

Lakukan perubahan:

```sql
UPDATE subtitles
SET downloaded = 1
WHERE id = 1;
```

Jika sudah yakin:

```sql
COMMIT;
```

Jika ingin membatalkan:

```sql
ROLLBACK;
```

## Contoh aman

```sql
BEGIN TRANSACTION;

UPDATE subtitles
SET downloaded = 1
WHERE id = 1;

UPDATE subtitles
SET downloaded = 1
WHERE id = 2;

COMMIT;
```

Jika terjadi masalah sebelum `COMMIT`:

```sql
ROLLBACK;
```

### Pola aman untuk perubahan manual

Sebelum:

```sql
SELECT *
FROM subtitles
WHERE id IN (1, 2);
```

Kemudian:

```sql
BEGIN TRANSACTION;

UPDATE subtitles
SET downloaded = 1
WHERE id IN (1, 2);

SELECT *
FROM subtitles
WHERE id IN (1, 2);

COMMIT;
```

---

# 21. Index

Index mempercepat pencarian pada kolom tertentu, terutama ketika database
bertambah besar.

## Melihat index

```sql
SELECT name, tbl_name, sql
FROM sqlite_master
WHERE type = 'index';
```

## Membuat index nama file

```sql
CREATE INDEX idx_subtitles_nama_file
ON subtitles(nama_file);
```

## Membuat index downloaded

```sql
CREATE INDEX idx_subtitles_downloaded
ON subtitles(downloaded);
```

## Membuat index gabungan

```sql
CREATE INDEX idx_subtitles_downloaded_id
ON subtitles(downloaded, id);
```

## Menghapus index

```sql
DROP INDEX idx_subtitles_nama_file;
```

> Roadmap project menyebut index database sebagai bagian robustness yang belum
> ditetapkan final. Jangan menambahkan index secara sembarangan hanya karena
> terlihat lebih lengkap.

---

# 22. ALTER TABLE

## Menambah kolom

Contoh:

```sql
ALTER TABLE subtitles
ADD COLUMN scrape_status TEXT;
```

> Ini mengubah schema. Jangan lakukan pada database project tanpa kebutuhan
> yang jelas dan verifikasi compatibility.

## Melihat schema setelah perubahan

```sql
.schema subtitles
```

SQLite memiliki keterbatasan tertentu pada `ALTER TABLE`. Untuk perubahan schema
yang kompleks, biasanya diperlukan pembuatan tabel baru dan migrasi data.

---

# 23. Backup dan Restore

## 23.1 Backup menggunakan SQLite CLI

Di dalam SQLite:

```sql
.backup 'backup/subtitles_backup.db'
```

Ini adalah cara yang praktis untuk membuat backup database SQLite.

## 23.2 Backup melalui shell

```bash
sqlite3 subtitles.db ".backup 'subtitles_backup.db'"
```

## 23.3 Dump database menjadi SQL

```bash
sqlite3 subtitles.db ".dump" > subtitles_backup.sql
```

## 23.4 Restore dari dump SQL

Buat database baru:

```bash
sqlite3 subtitles_restored.db < subtitles_backup.sql
```

## 23.5 Export schema saja

```bash
sqlite3 subtitles.db ".schema" > subtitles_schema.sql
```

### Catatan project

Roadmap menetapkan `subtitles.db` sebagai database utama dan `results.json`
sebagai backup selama masa transisi. Backup SQLite otomatis belum ditambahkan
sebagai behavior project.

---

# 24. Maintenance dan Pemeriksaan Database

## Mengecek integritas database

```sql
PRAGMA integrity_check;
```

Jika sehat, biasanya menghasilkan:

```text
ok
```

## Quick check

```sql
PRAGMA quick_check;
```

## Melihat ukuran page

```sql
PRAGMA page_count;
```

## Melihat ukuran page dalam byte

```sql
PRAGMA page_size;
```

## Melihat journal mode

```sql
PRAGMA journal_mode;
```

## Melihat foreign key setting

```sql
PRAGMA foreign_keys;
```

## Vacuum

```sql
VACUUM;
```

`VACUUM` dapat merapikan file database dan mengambil kembali ruang kosong setelah
banyak data dihapus.

> Jangan menjalankan maintenance berat tanpa alasan pada database yang sedang
> digunakan proses lain.

---

# 25. Export dan Import

## Export CSV melalui SQLite CLI

Aktifkan header:

```sql
.headers on
```

Set mode CSV:

```sql
.mode csv
```

Kemudian:

```sql
.once subtitles.csv
SELECT *
FROM subtitles;
```

`/ .once` akan mengarahkan output query berikutnya ke file.

Kembali ke output terminal:

```sql
.output stdout
```

## Export CSV hanya kolom tertentu

```sql
.headers on
.mode csv
.once subtitles.csv

SELECT
    id,
    nama_file,
    title,
    downloaded,
    scraped_at
FROM subtitles;
```

## Import CSV

Contoh umum:

```sql
.mode csv
.import subtitles.csv subtitles
```

> Import langsung ke tabel existing harus dilakukan dengan sangat hati-hati.
> Struktur CSV harus sesuai dengan schema target.

## Export pending subtitle

Workflow project memiliki utility khusus:

```text
export_pending_subtitles.py
```

Utility tersebut digunakan untuk mengekspor record SQLite dengan:

```sql
downloaded = 0
```

ke JSON tanpa mengubah data SQLite.

Gunakan `--help` untuk melihat sintaks CLI yang tersedia pada versi script lokal:

```bash
python export_pending_subtitles.py --help
```

---

# 26. SQLite CLI yang Berguna

## Tampilkan header

```sql
.headers on
```

## Sembunyikan header

```sql
.headers off
```

## Mode tabel

```sql
.mode table
```

## Mode column

```sql
.mode column
```

## Mode box

```sql
.mode box
```

## Atur lebar kolom

```sql
.width 5 30 60
```

## Tampilkan query yang dijalankan

```sql
.echo on
```

Matikan:

```sql
.echo off
```

## Simpan output query ke file

```sql
.output result.txt
```

Kembalikan ke terminal:

```sql
.output stdout
```

## Menjalankan file SQL

Dari shell:

```bash
sqlite3 subtitles.db < query.sql
```

Atau dari dalam SQLite:

```sql
.read query.sql
```

---

# 27. Contoh Query Praktis

## 27.1 Dashboard singkat database

```sql
SELECT COUNT(*) AS total
FROM subtitles;

SELECT COUNT(*) AS downloaded
FROM subtitles
WHERE downloaded = 1;

SELECT COUNT(*) AS pending
FROM subtitles
WHERE downloaded = 0;
```

## 27.2 Semua pending, terbaru lebih dahulu

```sql
SELECT
    id,
    nama_file,
    title,
    file_size,
    scraped_at
FROM subtitles
WHERE downloaded = 0
ORDER BY id DESC;
```

## 27.3 Semua data, terbaru lebih dahulu

```sql
SELECT
    id,
    nama_file,
    title,
    downloaded,
    scraped_at
FROM subtitles
ORDER BY id DESC;
```

## 27.4 Satu record terbaru

```sql
SELECT
    id,
    nama_file,
    title,
    downloaded,
    scraped_at
FROM subtitles
ORDER BY id DESC
LIMIT 1;
```

## 27.5 10 record terbaru

```sql
SELECT
    id,
    nama_file,
    title,
    downloaded,
    scraped_at
FROM subtitles
ORDER BY id DESC
LIMIT 10;
```

## 27.6 Mencari title

```sql
SELECT
    id,
    nama_file,
    title
FROM subtitles
WHERE title LIKE '%keyword%';
```

## 27.7 Mencari nama file

```sql
SELECT
    id,
    nama_file,
    title
FROM subtitles
WHERE nama_file LIKE '%ABC%';
```

## 27.8 Melihat record terbesar

```sql
SELECT
    id,
    nama_file,
    file_size
FROM subtitles
WHERE file_size IS NOT NULL
ORDER BY file_size DESC
LIMIT 10;
```

## 27.9 Statistik status

```sql
SELECT
    downloaded,
    COUNT(*) AS total
FROM subtitles
GROUP BY downloaded
ORDER BY downloaded;
```

## 27.10 Cek duplicate nama file

```sql
SELECT
    nama_file,
    COUNT(*) AS jumlah
FROM subtitles
GROUP BY nama_file
HAVING COUNT(*) > 1;
```

## 27.11 Melihat record tanpa title

```sql
SELECT *
FROM subtitles
WHERE title IS NULL
   OR title = '';
```

## 27.12 Melihat record tanpa relative path

```sql
SELECT
    id,
    nama_file,
    title
FROM subtitles
WHERE relative_path IS NULL;
```

## 27.13 Melihat data berdasarkan rentang ID

```sql
SELECT *
FROM subtitles
WHERE id BETWEEN 300 AND 350
ORDER BY id;
```

---

# 28. Perintah Berisiko

## Jangan sembarangan menjalankan

```sql
DELETE FROM subtitles;
```

Menghapus seluruh record.

## Sangat berbahaya

```sql
DROP TABLE subtitles;
```

Menghapus tabel beserta seluruh datanya.

## Sangat berbahaya

```sql
DROP TABLE IF EXISTS subtitles;
```

Tetap menghapus tabel jika tabel tersebut ada.

## Berisiko

```sql
UPDATE subtitles
SET downloaded = 1;
```

Mengubah seluruh record.

## Berisiko

```sql
DELETE FROM subtitles
WHERE downloaded = 0;
```

Menghapus seluruh pending record.

### Pola aman

Sebelum:

```sql
SELECT *
FROM subtitles
WHERE downloaded = 0;
```

Jika memang yakin:

```sql
BEGIN TRANSACTION;

DELETE FROM subtitles
WHERE downloaded = 0;

-- Periksa hasil jika diperlukan.
SELECT COUNT(*)
FROM subtitles;

-- Jika benar:
COMMIT;
```

Jika berubah pikiran:

```sql
ROLLBACK;
```

> Untuk operasi destruktif, backup terlebih dahulu.

---

# 29. Quick Reference

## Buka database

```bash
sqlite3 subtitles.db
```

## Lihat tabel

```sql
.tables
```

## Lihat schema

```sql
.schema subtitles
```

## Lihat struktur kolom

```sql
PRAGMA table_info(subtitles);
```

## Hitung data

```sql
SELECT COUNT(*) FROM subtitles;
```

## Satu data terbaru

```sql
SELECT *
FROM subtitles
ORDER BY id DESC
LIMIT 1;
```

## 10 data terbaru

```sql
SELECT *
FROM subtitles
ORDER BY id DESC
LIMIT 10;
```

## Pending

```sql
SELECT *
FROM subtitles
WHERE downloaded = 0;
```

## Jumlah pending

```sql
SELECT COUNT(*)
FROM subtitles
WHERE downloaded = 0;
```

## Sudah downloaded

```sql
SELECT *
FROM subtitles
WHERE downloaded = 1;
```

## Cari file

```sql
SELECT *
FROM subtitles
WHERE nama_file = 'ABC001';
```

## Cari title

```sql
SELECT *
FROM subtitles
WHERE title LIKE '%keyword%';
```

## Cek duplicate

```sql
SELECT
    nama_file,
    COUNT(*) AS jumlah
FROM subtitles
GROUP BY nama_file
HAVING COUNT(*) > 1;
```

## Backup

```sql
.backup 'backup/subtitles_backup.db'
```

## Integrity check

```sql
PRAGMA integrity_check;
```

## Keluar

```sql
.quit
```

---

# Catatan Khusus SubtitleHarvester

## Schema saat ini

```text
subtitles
├── id
├── nama_file
├── relative_path
├── title
├── downloaded
├── file_created_at
├── file_modified_at
├── file_accessed_at
├── file_size
└── scraped_at
```

## Arti `downloaded`

```text
0 = false
1 = true
```

## Database aktif

```text
subtitles.db
```

## Backup legacy

```text
results.json
```

## Prinsip checkpoint

```text
Scan .vtt
    ↓
Read filesystem metadata
    ↓
Query SQLite
    ├── sudah ada → SKIP
    └── belum ada
            ↓
        Extract code
            ↓
        Firecrawl
            ↓
        INSERT SQLite
```

Database harus diperiksa **sebelum Firecrawl**.

## Identitas file saat ini

Checkpoint aktif saat ini masih menggunakan `nama_file`.

Untuk recursive processing, roadmap menetapkan `relative_path` sebagai identitas
yang direkomendasikan agar file seperti:

```text
season1/ABC001.vtt
season2/ABC001.vtt
```

dapat dianggap sebagai dua file berbeda.

## Jangan lupa

- Jangan hapus `subtitles.db` secara otomatis.
- Jangan hapus `results.json` backup selama masa transisi.
- Jangan re-scrape seluruh subtitle existing hanya karena storage menggunakan
  SQLite.
- Jangan mengubah schema tanpa alasan yang jelas.
- Jangan menyamakan `scraped` dengan `downloaded`.
- Jangan menganggap `st_ctime` di Linux sebagai creation time yang akurat.
- Untuk perubahan data penting, backup dan gunakan transaction.
