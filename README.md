# Subtitle Metadata & Scraper

Tool Python CLI untuk memproses file subtitle `.vtt`, mengambil metadata/judul
melalui Firecrawl dari beberapa source, menyimpan metadata filesystem dan hasil
scraping ke SQLite, serta melewati subtitle yang sudah pernah diproses.

## Dokumentasi Project

Dokumentasi project ini dibagi menjadi beberapa file agar mudah dibaca sesuai
kebutuhan:

| File | Isi |
|---|---|
| `README.md` (dokumen ini) | Overview, struktur project, setup environment, cara pakai CLI |
| [`ROADMAP.md`](./ROADMAP.md) | Prioritas pengembangan, status terkini, testing minimum, definition of done |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Desain teknis: schema database, alur proses, aturan Firecrawl, sorting, format metadata |
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) | Aturan wajib/dilarang untuk developer maupun LLM/AI yang mengubah kode |
| [`CHANGELOG.md`](./CHANGELOG.md) | Riwayat perubahan project |
| [`sqlite_database_cheatsheet.md`](./sqlite_database_cheatsheet.md) | Referensi query SQLite untuk database `subtitles.db` |

**Sebelum mengubah kode**, baca `ROADMAP.md`, `ARCHITECTURE.md`, dan
`CONTRIBUTING.md` terlebih dahulu — lihat detail di `CONTRIBUTING.md`.

---

## Struktur Project

```text
subtitle-metadata/
├── subtitle_metadata.py
├── batch_add_extension.py
├── migrate_json_to_sqlite.py
├── export_pending_subtitles.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── ROADMAP.md
├── ARCHITECTURE.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── sqlite_database_cheatsheet.md
├── results.json           # backup data lama, lokal
├── .env                   # lokal, jangan commit
├── subtitles.db           # database lokal
└── .venv/                 # lokal, jangan commit
```

- `subtitle_metadata.py` — tool utama: scan folder `.vtt`, cek checkpoint
  SQLite, scraping title lewat Firecrawl untuk file yang belum diproses.
- `batch_add_extension.py` — tool terpisah untuk menambahkan ekstensi ke file
  yang belum memiliki ekstensi.
- `migrate_json_to_sqlite.py` — migrasi satu kali dari checkpoint JSON lama
  (`results.json`) ke SQLite (`subtitles.db`).
- `export_pending_subtitles.py` — mengekspor record SQLite dengan
  `downloaded = 0` ke JSON tanpa mengubah data SQLite.

---

## Setup

### Dependency

`requirements.txt`:

```text
requests
python-dotenv
send2trash
```

`sqlite3` **tidak** dimasukkan karena merupakan standard library Python
(begitu juga `argparse`, `json`, `os`, `sys`, `pathlib`, `datetime`, `shutil`,
`time`).

### Virtual Environment (uv)

Project menggunakan **uv** untuk pengelolaan virtual environment. Nama
virtual environment: `.venv/`.

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
project. Jangan memasang dependency project secara global jika dapat
dihindari.

### Environment dan Secret

Gunakan `.env` untuk API key. Contoh `.env.example`:

```env
FIRECRAWL_API_KEY=your_firecrawl_api_key_here
FIRECRAWL_SOURCES=https://source.com/{code}
```

`.env` asli tidak boleh di-commit. `.gitignore` minimal:

```text
.env
.venv/
__pycache__/
*.pyc
```

Jangan pernah hard-code API key ke source code.

---

## Cara Pakai

### `subtitle_metadata.py` — scraping utama

```bash
python subtitle_metadata.py -d ~/subtitle
```

Dengan database custom:

```bash
python subtitle_metadata.py -d ~/subtitle --db subtitles.db
```

Directory juga bisa ditulis positional (tetap didukung untuk kompatibilitas):

```bash
python subtitle_metadata.py ~/subtitle
```

Opsi lain:
- `-a` / `--all` — sertakan file tersembunyi.
- `-r` / `--reverse` — proses file dalam urutan terbalik.
- `-o` / `--output` — **legacy**, file JSON checkpoint lama; tidak lagi
  digunakan sebagai checkpoint (SQLite adalah checkpoint utama).

Detail alur proses dan aturan checkpoint ada di `ARCHITECTURE.md`.

### `migrate_json_to_sqlite.py` — migrasi satu kali

```bash
python migrate_json_to_sqlite.py results.json --db subtitles.db
```

Hanya dijalankan sekali untuk memindahkan checkpoint lama ke SQLite. Migrator
menolak berjalan jika database target sudah berisi data, untuk mencegah
duplikat.

### `export_pending_subtitles.py` — ekspor subtitle pending

```bash
python export_pending_subtitles.py --db subtitles.db --output pending_subtitles.json
```

Mengekspor seluruh record dengan `downloaded = 0` ke JSON tanpa mengubah data
di SQLite.

### `batch_add_extension.py` — tambah ekstensi file

```bash
python batch_add_extension.py -f ~/Documents/berkas -e txt
python batch_add_extension.py -f ~/Documents/berkas -e jpg -r
python batch_add_extension.py -f ~/Documents/berkas -e pdf -r --dry-run
```

Tool ini berdiri sendiri, terpisah dari logic Firecrawl (lihat aturan
pemisahan di `ARCHITECTURE.md`). Fitur yang tersedia: recursive (`-r`),
dry-run, konfirmasi (`-y`/`--yes`), duplicate handling (`--duplicate-action
skip|trash|move`), dan JSON history/log otomatis di `.history/`.

---

## Query Database

Untuk melihat isi `subtitles.db` langsung lewat SQLite CLI (cek status
scraping, cari duplikat, dsb.), lihat `sqlite_database_cheatsheet.md`.
