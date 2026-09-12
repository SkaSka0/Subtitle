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
