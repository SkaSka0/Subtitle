#!/usr/bin/env python3

import argparse
import html
import sqlite3
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/scrape"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

# Free tier Firecrawl: 10 requests/menit. Interval minimum antar
# request supaya tidak pernah menyentuh limit (proaktif, bukan
# reaktif lewat retry-after-429).
MIN_SECONDS_PER_REQUEST = 6.5

SOURCES_ENV_VAR = "FIRECRAWL_SOURCES"

NOT_FOUND_KEYWORDS = [
    "404",
    "page not found",
    "not found",
    "video not found",
    "doesn't exist",
]


def log(message: str, level: str = "INFO") -> None:
    print(f"[{level}] {message}", flush=True)


def current_timestamp() -> str:
    """Waktu saat data berhasil diproses: dd-mm-yyyy HH:MM:SS."""
    return datetime.now().strftime("%d-%m-%Y %H:%M:%S")


def format_file_timestamp(timestamp: float) -> str:
    """Format timestamp filesystem menjadi dd-mm-yyyy HH:MM:SS."""
    return datetime.fromtimestamp(timestamp).strftime("%d-%m-%Y %H:%M:%S")


def get_file_created_timestamp(file: Path) -> float:
    """
    Mengambil creation/birth time file jika filesystem/OS menyediakannya.

    - Windows: st_ctime adalah creation time.
    - macOS/BSD: st_birthtime tersedia.
    - Linux/filesystem yang mengekspos birth time: st_birthtime dapat digunakan.
    - Jika birth time tidak tersedia, st_ctime digunakan sebagai fallback.
      Pada Linux, st_ctime adalah waktu perubahan metadata/inode, BUKAN
      selalu waktu file dibuat.
    """
    stat = file.stat()

    birthtime = getattr(stat, "st_birthtime", None)
    if birthtime is not None:
        return float(birthtime)

    # Windows menggunakan st_ctime sebagai creation time.
    if os.name == "nt":
        return float(stat.st_ctime)

    # Fallback untuk OS/filesystem yang tidak mengekspos birth time.
    return float(stat.st_ctime)


def get_file_metadata(file: Path) -> dict:
    """Mengambil metadata filesystem subtitle .vtt."""
    stat = file.stat()
    created_timestamp = get_file_created_timestamp(file)

    return {
        "file_created_at": format_file_timestamp(created_timestamp),
        "file_modified_at": format_file_timestamp(stat.st_mtime),
        "file_accessed_at": format_file_timestamp(stat.st_atime),
        "file_size": stat.st_size,
    }


class RateLimiter:
    """Menjaga jarak antar request Firecrawl >= min_interval detik.
    Dipanggil sebelum setiap request (termasuk retry / ganti source),
    bukan hanya sekali per file."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self.last_request_time: float = 0.0

    def wait(self) -> None:
        remaining = self.min_interval - (time.time() - self.last_request_time)
        if remaining > 0:
            log(f"Menunggu {remaining:.1f} detik (throttle rate limit)...")
            time.sleep(remaining)
        self.last_request_time = time.time()


def extract_markdown_title(markdown: str) -> str:
    """Mengambil heading pertama (# Judul) dari markdown Firecrawl."""
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title:
                return title
    return ""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mengambil nama file subtitle .vtt dan melakukan scraping title "
        "menggunakan Firecrawl, dengan SQLite sebagai checkpoint."
    )
    parser.add_argument(
        "directory", nargs="?", type=Path,
        help="Folder yang berisi file-file subtitle .vtt yang akan diproses",
    )
    parser.add_argument(
        "-d", "--directory", dest="directory_option", type=Path,
        help="Folder target yang berisi file-file subtitle .vtt",
    )
    parser.add_argument(
        "-a", "--all", action="store_true",
        help="Sertakan file tersembunyi",
    )
    parser.add_argument(
        "--db", type=Path, default=Path("subtitles.db"),
        help="File SQLite checkpoint (default: subtitles.db)",
    )
    parser.add_argument(
        "-r", "--reverse", action="store_true",
        help="Proses file dalam urutan terbalik",
    )
    parser.add_argument(
        "-o", "--output", type=Path,
        help="[Legacy] File JSON checkpoint lama; tidak digunakan lagi sebagai checkpoint.",
    )
    args = parser.parse_args()

    if args.directory is not None and args.directory_option is not None:
        parser.error("Tentukan directory sekali saja, bukan positional dan --directory sekaligus.")

    args.directory = args.directory_option or args.directory
    if args.directory is None:
        parser.error("directory wajib diisi (contoh: python subtitle_metadata.py -d ~/subtitle)")

    if args.output is not None:
        log(
            "Option -o/--output sudah tidak digunakan sebagai checkpoint. "
            "SQLite tetap digunakan sebagai storage utama.",
            "WARNING",
        )

    return args


def validate_directory(directory: Path) -> None:
    if not directory.exists():
        raise FileNotFoundError(f"Folder tidak ditemukan: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path bukan sebuah folder: {directory}")


def get_files(directory: Path, include_hidden: bool = False) -> list[Path]:
    """Mengambil file .vtt yang berada langsung di dalam folder (tidak recursive)."""
    files: list[Path] = []
    try:
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            if not include_hidden and entry.name.startswith("."):
                continue
            if entry.suffix.lower() != ".vtt":
                continue
            files.append(entry)
    except PermissionError as exc:
        raise PermissionError(f"Tidak memiliki izin membaca folder: {directory}") from exc
    except OSError as exc:
        raise OSError(f"Gagal membaca folder '{directory}': {exc}") from exc

    # Urutan awal tetap berdasarkan nama file. Sorting database dilakukan
    # terpisah jika dibutuhkan oleh query/reporting.
    return sorted(files, key=lambda file: file.name.lower())


def get_file_code(file: Path) -> str:
    """Nama file tanpa ekstensi. File tersembunyi (mis. .bashrc)
    dianggap tidak memiliki ekstensi."""
    if file.name.startswith(".") and file.name.count(".") == 1:
        return file.name
    return file.stem


def scrape_title(
    code: str,
    api_key: str,
    sources: list[str],
    rate_limiter: RateLimiter,
) -> str:
    """Mencoba tiap source satu per satu lewat Firecrawl.
    Retry hingga MAX_RETRIES pada HTTP 429, mengikuti Retry-After
    jika tersedia, jika tidak pakai exponential backoff."""

    lower_code = code.lower()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for source_template in sources:
        target_url = source_template.format(code=lower_code)
        retry_count = 0

        while True:
            # Throttle sebelum setiap request (termasuk retry & pindah source).
            rate_limiter.wait()
            log(f"⏳ Meminta bantuan Firecrawl untuk menembus: {target_url}")
            payload = {"url": target_url, "formats": ["markdown"]}

            try:
                response = requests.post(
                    FIRECRAWL_API_URL, headers=headers, json=payload,
                    timeout=REQUEST_TIMEOUT,
                )
                log(f"Status API Firecrawl: {response.status_code}")

                if response.status_code == 429:
                    if retry_count >= MAX_RETRIES:
                        log(
                            f"HTTP 429 masih terjadi setelah {MAX_RETRIES} kali retry. "
                            "Lanjut ke sumber berikutnya...",
                            "ERROR",
                        )
                        break

                    retry_count += 1
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            wait_time = 2 ** retry_count
                    else:
                        wait_time = 2 ** retry_count

                    log(
                        f"Rate limit Firecrawl terkena. Retry {retry_count}/{MAX_RETRIES}. "
                        f"Menunggu {wait_time:g} detik...",
                        "ERROR",
                    )
                    time.sleep(wait_time)

                    # Reset jam throttle supaya wait() berikutnya tidak
                    # menambah delay ekstra di atas backoff ini.
                    rate_limiter.last_request_time = time.time()
                    continue

                if response.status_code != 200:
                    log(
                        f"API Firecrawl gagal ({response.status_code}). "
                        "Lanjut ke sumber berikutnya...",
                        "ERROR",
                    )
                    break

                try:
                    json_data = response.json()
                except ValueError:
                    log("Response Firecrawl bukan JSON yang valid.", "ERROR")
                    break

                data = json_data.get("data", {})
                metadata = data.get("metadata", {})
                markdown = data.get("markdown", "")
                error = data.get("error")

                if error:
                    log(f"Firecrawl Error: {error}", "ERROR")
                    break

                target_status = (
                    metadata.get("statusCode")
                    or metadata.get("status_code")
                    or metadata.get("status")
                )
                if target_status:
                    log(f"Status Website Target: {target_status}")
                    try:
                        if int(target_status) != 200:
                            log(
                                f"Website mengembalikan HTTP {target_status}. "
                                "Lanjut ke sumber berikutnya...",
                                "ERROR",
                            )
                            break
                    except (TypeError, ValueError):
                        log(f"Status website tidak valid: {target_status}", "ERROR")

                scraped_title = (
                    metadata.get("ogTitle")
                    or metadata.get("og:title")
                    or metadata.get("title")
                )
                if not scraped_title and markdown:
                    scraped_title = extract_markdown_title(markdown)

                if not scraped_title:
                    log(
                        "Metadata title tidak ditemukan. "
                        "Lanjut ke sumber berikutnya...",
                        "ERROR",
                    )
                    break

                title_lower = scraped_title.lower()
                markdown_lower = markdown.lower()

                if any(keyword in title_lower for keyword in NOT_FOUND_KEYWORDS):
                    log("Halaman 404 terdeteksi dari judul.", "ERROR")
                    break

                if any(keyword in markdown_lower for keyword in NOT_FOUND_KEYWORDS):
                    log("Halaman 404 terdeteksi dari isi halaman.", "ERROR")
                    break

                decoded_title = html.unescape(scraped_title).strip()
                log(f"Judul ditemukan: {decoded_title}", "SUCCESS")
                return decoded_title

            except requests.Timeout:
                log(
                    "Request ke Firecrawl timeout. "
                    "Lanjut ke sumber berikutnya...",
                    "ERROR",
                )
                break
            except requests.ConnectionError as exc:
                log(
                    f"Gagal terhubung ke Firecrawl: {exc}. "
                    "Lanjut ke sumber berikutnya...",
                    "ERROR",
                )
                break
            except requests.RequestException as exc:
                log(
                    f"Request ke Firecrawl gagal: {exc}. "
                    "Lanjut ke sumber berikutnya...",
                    "ERROR",
                )
                break
            except Exception as exc:
                log(
                    f"Terjadi error tidak terduga: {exc}. "
                    "Lanjut ke sumber berikutnya...",
                    "ERROR",
                )
                break

    log(f"Gagal menemukan judul untuk kode '{code}' dari semua sumber.", "ERROR")
    return ""


def initialize_database(connection: sqlite3.Connection) -> None:
    """Membuat schema SQLite jika belum tersedia tanpa mengubah data existing."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS subtitles (
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
        )
        """
    )
    connection.commit()


def open_database(database_file: Path) -> sqlite3.Connection:
    """Membuka SQLite dan memastikan schema tersedia."""
    try:
        database_file.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_file)
        connection.row_factory = sqlite3.Row
        initialize_database(connection)
        return connection
    except sqlite3.Error as exc:
        raise OSError(f"Gagal membuka database '{database_file}': {exc}") from exc


def is_processed(connection: sqlite3.Connection, nama_file: str) -> bool:
    """Mengecek checkpoint SQLite sebelum Firecrawl."""
    row = connection.execute(
        "SELECT 1 FROM subtitles WHERE nama_file = ? LIMIT 1",
        (nama_file,),
    ).fetchone()
    return row is not None


def insert_result(
    connection: sqlite3.Connection,
    nama_file: str,
    title: str,
    file_metadata: dict,
) -> None:
    """Menyimpan hasil scraping yang sukses ke SQLite."""
    try:
        connection.execute(
            """
            INSERT INTO subtitles (
                nama_file, relative_path, title, downloaded,
                file_created_at, file_modified_at, file_accessed_at,
                file_size, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nama_file,
                None,
                title,
                0,
                file_metadata["file_created_at"],
                file_metadata["file_modified_at"],
                file_metadata["file_accessed_at"],
                file_metadata["file_size"],
                current_timestamp(),
            ),
        )
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        raise OSError(f"Gagal menyimpan '{nama_file}' ke SQLite: {exc}") from exc


def get_database_count(connection: sqlite3.Connection) -> int:
    """Mengambil jumlah record subtitle dari database."""
    row = connection.execute("SELECT COUNT(*) AS count FROM subtitles").fetchone()
    return int(row["count"])


def process_files(
    files: list[Path],
    connection: sqlite3.Connection,
    api_key: str,
    rate_limiter: RateLimiter,
    sources: list[str],
) -> tuple[int, int, int]:
    """Memproses file satu per satu dengan SQLite sebagai checkpoint utama.

    Database selalu diperiksa sebelum Firecrawl. Record baru langsung di-commit
    setelah scraping sukses sehingga hasil yang sudah tersimpan tetap aman jika
    proses berhenti di tengah jalan.
    """

    total = len(files)
    skipped_count = success_count = failed_count = 0

    for index, file in enumerate(files, start=1):
        code = get_file_code(file)

        if is_processed(connection, code):
            log(f"[{index}/{total}] {code} sudah ada di SQLite. SKIP.")
            skipped_count += 1
            continue

        log(f"===== [{index}/{total}] Memproses: {code} =====")

        try:
            file_metadata = get_file_metadata(file)
        except (OSError, PermissionError) as exc:
            failed_count += 1
            log(
                f"Gagal membaca metadata filesystem '{file.name}': {exc}",
                "ERROR",
            )
            continue

        title = scrape_title(code, api_key, sources, rate_limiter)

        print()
        log(f"nama file        : {code}")
        log(f"title            : {title or '-'}")
        log(f"file created at  : {file_metadata['file_created_at']}")
        log(f"file modified at : {file_metadata['file_modified_at']}")
        log(f"file accessed at : {file_metadata['file_accessed_at']}")
        log(f"file size        : {file_metadata['file_size']} bytes")
        print()

        if title:
            try:
                insert_result(connection, code, title, file_metadata)
            except OSError as exc:
                failed_count += 1
                log(str(exc), "ERROR")
                continue

            success_count += 1
            log(
                f"Checkpoint SQLite diperbarui. {get_database_count(connection)} "
                "record tersimpan.",
                "SUCCESS",
            )
        else:
            failed_count += 1
            log(
                f"'{code}' tidak mendapatkan title. "
                "Tidak dimasukkan ke SQLite.",
                "ERROR",
            )

    print()
    log("SUMMARY")
    log(f"Total file       : {total}")
    log(f"Sudah diproses   : {skipped_count}")
    log(f"Berhasil         : {success_count}")
    log(f"Gagal            : {failed_count}")
    log(f"Total checkpoint : {get_database_count(connection)}")

    return skipped_count, success_count, failed_count


def main() -> int:
    args = parse_arguments()

    try:
        env_file = Path(__file__).resolve().parent / ".env"
        if not env_file.exists():
            log(f"File .env tidak ditemukan: {env_file}", "ERROR")
            return 1

        load_dotenv(env_file)
        log(f"Memuat environment dari: {env_file}")

        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            log(
                "Environment variable 'FIRECRAWL_API_KEY' tidak ditemukan!",
                "ERROR",
            )
            return 1

        sources = [
            source.strip()
            for source in os.getenv(SOURCES_ENV_VAR, "").split(",")
            if source.strip()
        ]
        if not sources:
            log(
                f"Environment variable '{SOURCES_ENV_VAR}' tidak ditemukan atau kosong. "
                f"Isi dengan daftar source yang dipisahkan koma.",
                "ERROR",
            )
            return 1

        validate_directory(args.directory)
        files = get_files(args.directory, include_hidden=args.all)

        if not files:
            log("Tidak ada file subtitle .vtt yang ditemukan di folder.", "ERROR")
            return 1

        if args.reverse:
            files.reverse()

        log(f"Ditemukan {len(files)} file subtitle .vtt yang akan diperiksa.")

        connection = open_database(args.db)
        try:
            database_count = get_database_count(connection)
            log(f"SQLite checkpoint aktif: {args.db}")
            log(f"Record yang sudah tersimpan: {database_count}")

            existing_count = sum(
                1 for file in files if is_processed(connection, get_file_code(file))
            )
            log(f"File target yang sudah ada di SQLite: {existing_count}")
            log(f"File yang perlu diperiksa: {len(files) - existing_count}")

            rate_limiter = RateLimiter(MIN_SECONDS_PER_REQUEST)
            process_files(files, connection, api_key, rate_limiter, sources)
            final_count = get_database_count(connection)
        finally:
            connection.close()

        log(
            f"Semua proses selesai. Total {final_count} record tersimpan di {args.db}",
            "SUCCESS",
        )
        return 0

    except KeyboardInterrupt:
        print()
        log("Proses dibatalkan oleh pengguna.", "ERROR")
        log("Record yang sudah di-commit ke SQLite tetap tersimpan.", "INFO")
        return 130

    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        ValueError,
        OSError,
    ) as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
