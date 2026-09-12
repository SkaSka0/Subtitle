# CONTRIBUTING — Panduan Kontribusi & Aturan untuk LLM/AI

> Dokumen ini berlaku untuk **developer maupun LLM/AI** yang diminta
> memodifikasi kode project. Untuk overview & cara pakai, lihat
> [`README.md`](./README.md). Untuk prioritas/status, lihat
> [`ROADMAP.md`](./ROADMAP.md). Untuk desain teknis, lihat
> [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## Sebelum Mengubah Kode — WAJIB

1. Baca dokumentasi project: `README.md` (overview), `ROADMAP.md`
   (prioritas & status), `ARCHITECTURE.md` (desain teknis) — sesuai bagian
   yang relevan dengan perubahan yang akan dilakukan.
2. Periksa struktur project (lihat `README.md` bagian Struktur Project).
3. Baca kode yang relevan.
4. Pahami schema/data existing (lihat `ARCHITECTURE.md` bagian Database).
5. Pertahankan behavior yang sudah bekerja.
6. Buat perubahan sekecil mungkin.
7. Lakukan syntax check.
8. Test fungsi yang terdampak (lihat `ROADMAP.md` bagian Testing Minimum).
9. Update `ROADMAP.md`/`ARCHITECTURE.md`/`CHANGELOG.md` jika status atau
   arsitektur berubah.

---

## Prinsip Desain & Pemeliharaan Kode

Bagian ini berisi aturan konkret yang lahir dari pengalaman nyata
memelihara project ini (lihat `CHANGELOG.md` untuk kasus yang melatari
tiap aturan). Berlaku untuk kode baru maupun saat menyentuh kode existing.

### 1. Satu fungsi, satu tanggung jawab

Setiap fungsi baru sebaiknya melakukan **satu tanggung jawab saja**.
Tanda-tanda sebuah fungsi sudah melakukan lebih dari satu hal:
- Nama fungsi butuh kata "dan" untuk dijelaskan (mis. "kirim request DAN
  parse response DAN validasi title").
- Docstring-nya berisi lebih dari satu kalimat yang menjelaskan hal
  yang tidak saling terkait langsung.
- Fungsi punya banyak lapis percabangan (nested if/try) yang menangani
  beberapa jenis masalah berbeda dalam satu badan fungsi.

Jika ini terjadi, pisahkan bagian yang berbeda tanggung jawabnya ke
fungsi terpisah (helper), dengan nama yang menjelaskan persis satu hal
yang dilakukan. Fungsi orkestrasi/pemanggil boleh tetap ada untuk
menyusun alur, tapi badannya sebaiknya berupa pemanggilan
helper-helper tersebut, bukan implementasi detailnya secara langsung.

Contoh penerapan di project ini: `scrape_title()` (lihat `CHANGELOG.md`
2026-09-13) dipecah menjadi `_send_scrape_request()`,
`_compute_retry_wait()`, `_parse_scrape_response()`,
`_target_status_failed()`, dan `_extract_valid_title()`.

**Catatan:** aturan ini berlaku wajib untuk fungsi/kode baru. Untuk kode
existing yang sudah melanggar prinsip ini, jangan langsung di-refactor
tanpa konfirmasi terlebih dahulu — tetap ikuti aturan "perubahan sekecil
mungkin" dan "jangan refactor besar jika perubahan kecil sudah cukup" di
bagian DILARANG.

### 2. Helper privat/internal diberi prefix underscore

Fungsi yang murni menjadi detail implementasi internal suatu fungsi lain
(bukan dipanggil dari luar module, bukan bagian dari alur utama seperti
`main()`/`process_files()`) diberi prefix `_` pada namanya, misalnya
`_send_scrape_request()`, `_extract_valid_title()`. Ini membedakan secara
visual mana fungsi yang merupakan "API" module (dipanggil dari file lain
atau dari alur utama) dan mana yang murni helper pendukung satu fungsi
tertentu.

### 3. Update semua referensi tekstual saat fungsi diubah/dihapus

Saat menghapus atau mengubah signature/perilaku suatu fungsi, cari seluruh
referensi ke nama fungsi tersebut di **seluruh file** (`grep nama_fungsi`),
bukan hanya di definisinya — termasuk yang muncul di docstring dan
komentar fungsi lain. Referensi tekstual yang tertinggal akan menjadi
dokumentasi yang menyesatkan bagi pembaca maupun LLM/AI berikutnya, karena
terlihat valid padahal sudah tidak akurat.

Kasus nyata yang melatari aturan ini: fungsi `is_processed()` berhenti
dipakai sejak perbaikan BUG #3 (2026-09-12), tetapi docstring
`get_processed_codes()` serta komentar di `initialize_database()` dan
`main()` masih menyebut nama fungsi tersebut seolah-olah masih aktif
dipanggil, sampai akhirnya ditemukan dan dibersihkan terpisah
(lihat `CHANGELOG.md` 2026-09-13).

### 4. Perubahan pada logic/percabangan wajib diverifikasi dengan test

Untuk perubahan yang menyentuh alur kontrol (percabangan, retry, kondisi
error/edge case), verifikasi dengan test tertulis **wajib**, bukan sekadar
membaca ulang kode secara manual. Test tidak harus menjadi bagian permanen
dari test suite project — test sementara/manual yang dijalankan sekali
untuk memverifikasi suatu perubahan sudah cukup, asal setiap skenario
penting (termasuk edge case yang mudah salah) tercakup.

Alasan: percabangan dengan banyak kondisi (mis. kapan harus `break`,
`continue`, atau lanjut tanpa aksi) sangat mudah salah diasumsikan hanya
dari membaca kode, terutama saat melakukan refactor/ekstraksi fungsi.
Contoh nyata: saat memecah `scrape_title()`, salah satu cabang
(`target_status` yang tidak bisa di-parse) sengaja **tidak** boleh
menghentikan proses, hanya mencatat warning — detail ini baru benar-benar
terverifikasi lewat test otomatis (lihat `CHANGELOG.md` 2026-09-13,
`test_scrape_title_refactor.py`), bukan dari membaca kode saja.

### 5. Konfigurasi yang terikat tier akun/environment sebaiknya di `.env`

Konstanta yang nilainya bergantung pada tier akun, versi API pihak
ketiga, atau properti environment lain (bukan properti logic project itu
sendiri) sebaiknya bisa dioverride lewat `.env`, dengan nilai default di
kode sebagai fallback jika variabel tidak diset. Contoh: rate limit
scraping (`MIN_SECONDS_PER_REQUEST`) terikat ke tier akun Firecrawl yang
sedang dipakai (free tier = 10 request/menit), sehingga bisa berbeda kalau
akun di-upgrade — ini properti akun/environment, bukan properti logic
kode.

Sebaliknya, konstanta yang murni properti behavior/logic kode (mis.
`SQLITE_MAX_VARIABLES` yang mengikuti batas teknis SQLite,
`NOT_FOUND_KEYWORDS` yang merupakan bagian dari logic deteksi) **tidak**
perlu dipindah ke `.env` — memindahkannya justru menambah risiko
misconfigurasi tanpa manfaat nyata.

---

## DILARANG

LLM/AI (dan developer) tidak boleh:
- menghapus data existing tanpa konfirmasi;
- menghapus database/JSON backup otomatis;
- melakukan re-scrape semua subtitle existing tanpa alasan;
- hard-code API key;
- memasukkan standard library ke `requirements.txt`;
- mengganti SQLite dengan database server tanpa alasan;
- menghapus retry/rate limit Firecrawl;
- mengubah source scraping secara diam-diam;
- mengubah format data existing tanpa migrasi;
- menyebut Linux `st_ctime` sebagai creation time secara pasti;
- melakukan refactor besar jika perubahan kecil sudah cukup.

## Jika Requirement Ambigu

1. Jelaskan trade-off.
2. Hindari keputusan yang berisiko data loss.
3. Prioritaskan kompatibilitas data existing.

## Mengubah Dokumentasi

Prinsip yang sama berlaku untuk dokumentasi seperti untuk kode:
- Jangan menghapus atau "memperbaiki diam-diam" informasi historis
  (misalnya status di `CHANGELOG.md` atau snapshot lama di `ROADMAP.md`)
  tanpa konfirmasi dari maintainer, meskipun terlihat tidak konsisten dengan
  kondisi repo saat ini. Catat inkonsistensi tersebut secara eksplisit,
  jangan langsung diubah.
- Perubahan struktur dokumentasi (menambah/memecah file) tetap harus
  mempertahankan seluruh isi yang sudah ada — hanya dipindahkan ke lokasi
  yang lebih sesuai, dilengkapi dengan tautan silang antar dokumen.
