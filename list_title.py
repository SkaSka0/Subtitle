#!/usr/bin/env python3

import argparse
import html
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v2/scrape"

REQUEST_TIMEOUT = 60
MAX_RETRIES = 3

# Free tier Firecrawl: 10 requests/minute.
# Interval minimum antar request supaya TIDAK PERNAH menyentuh
# limit, alih-alih mengandalkan retry-after-429 (reaktif).
MIN_SECONDS_PER_REQUEST = 6.5

# Simpan checkpoint setiap N hasil sukses (bukan tiap 1 file)
# untuk mengurangi I/O berulang menulis seluruh JSON.
SAVE_EVERY = 5

SOURCES = []

NOT_FOUND_KEYWORDS = [
    "404",
    "page not found",
    "not found",
    "video not found",
    "doesn't exist",
]


# ============================================================
# Logging
# ============================================================

def log(message: str, level: str = "INFO") -> None:
    print(f"[{level}] {message}", flush=True)


# ============================================================
# Rate Limiter (throttle)
# ============================================================

class RateLimiter:
    """
    Memastikan jarak antar request Firecrawl selalu >=
    MIN_SECONDS_PER_REQUEST detik, dipanggil sebelum SETIAP
    request (termasuk saat pindah source / retry), bukan
    hanya sekali per file.
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self.last_request_time: float = 0.0

    def wait(self) -> None:
        elapsed = time.time() - self.last_request_time

        remaining = self.min_interval - elapsed

        if remaining > 0:
            log(
                f"Menunggu {remaining:.1f} detik "
                "(throttle rate limit)..."
            )
            time.sleep(remaining)

        self.last_request_time = time.time()


# ============================================================
# Markdown Parser
# ============================================================

def extract_markdown_title(markdown: str) -> str:
    """
    Mengambil heading pertama (# Judul) dari markdown Firecrawl.
    """

    for line in markdown.splitlines():
        line = line.strip()

        if line.startswith("#"):
            title = line.lstrip("#").strip()

            if title:
                return title

    return ""


# ============================================================
# Argument Parser
# ============================================================

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Mengambil nama file dari sebuah folder dan "
            "melakukan scraping title menggunakan Firecrawl."
        )
    )

    parser.add_argument(
        "directory",
        type=Path,
        help="Folder yang berisi file-file yang akan diproses",
    )

    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Sertakan file tersembunyi",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("results.json"),
        help="File JSON output/checkpoint (default: results.json)",
    )

    parser.add_argument(
        "-r",
        "--reverse",
        action="store_true",
        help="Proses file dalam urutan terbalik",
    )

    return parser.parse_args()


# ============================================================
# Directory Validation
# ============================================================

def validate_directory(directory: Path) -> None:
    """Memastikan path tersedia dan merupakan folder."""

    if not directory.exists():
        raise FileNotFoundError(
            f"Folder tidak ditemukan: {directory}"
        )

    if not directory.is_dir():
        raise NotADirectoryError(
            f"Path bukan sebuah folder: {directory}"
        )


# ============================================================
# File Handling
# ============================================================

def get_files(
    directory: Path,
    include_hidden: bool = False,
) -> list[Path]:
    """
    Mengambil file yang berada langsung di dalam folder.

    Tidak melakukan recursive scan.
    """

    files: list[Path] = []

    try:
        for entry in directory.iterdir():

            # Abaikan folder
            if not entry.is_file():
                continue

            # Abaikan hidden file jika --all tidak digunakan
            if not include_hidden and entry.name.startswith("."):
                continue

            files.append(entry)

    except PermissionError as exc:
        raise PermissionError(
            f"Tidak memiliki izin membaca folder: {directory}"
        ) from exc

    except OSError as exc:
        raise OSError(
            f"Gagal membaca folder '{directory}': {exc}"
        ) from exc

    return sorted(
        files,
        key=lambda file: file.name.lower(),
    )


def get_file_code(file: Path) -> str:
    """
    Mengambil nama file tanpa ekstensi.

    Contoh:

        ABC-123.mp4 -> ABC-123
        ABC-123.mkv -> ABC-123
        ABC-123     -> ABC-123
        .bashrc     -> .bashrc

    File tersembunyi seperti .bashrc dianggap tidak
    memiliki ekstensi.
    """

    if file.name.startswith(".") and file.name.count(".") == 1:
        return file.name

    return file.stem


# ============================================================
# Firecrawl
# ============================================================

def scrape_title(code: str, api_key: str, rate_limiter: RateLimiter) -> str:
    """
    Melakukan scraping title menggunakan Firecrawl.

    Source dicoba satu per satu.

    Jika mendapatkan HTTP 429, request akan di-retry
    sampai MAX_RETRIES.

    Retry-After digunakan jika tersedia.
    Jika tidak tersedia, digunakan exponential backoff.
    """

    lower_code = code.lower()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for source_template in SOURCES:

        target_url = source_template.format(
            code=lower_code
        )

        retry_count = 0

        while True:

            # Throttle SEBELUM setiap request (termasuk retry
            # dan pindah source), bukan hanya sekali per file.
            rate_limiter.wait()

            log(
                f"⏳ Meminta bantuan Firecrawl untuk menembus: "
                f"{target_url}"
            )

            payload = {
                "url": target_url,
                "formats": ["markdown"],
            }

            try:
                response = requests.post(
                    FIRECRAWL_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )

                log(
                    f"Status API Firecrawl: "
                    f"{response.status_code}"
                )

                # ==================================================
                # HTTP 429 - Rate Limit
                # ==================================================

                if response.status_code == 429:

                    if retry_count >= MAX_RETRIES:
                        log(
                            f"HTTP 429 masih terjadi setelah "
                            f"{MAX_RETRIES} kali retry. "
                            "Lanjut ke sumber berikutnya...",
                            "ERROR",
                        )
                        break

                    retry_count += 1

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    if retry_after:
                        try:
                            wait_time = float(retry_after)

                        except ValueError:
                            wait_time = 2 ** retry_count

                    else:
                        # Retry 1 -> 2 detik
                        # Retry 2 -> 4 detik
                        # Retry 3 -> 8 detik
                        wait_time = 2 ** retry_count

                    log(
                        f"Rate limit Firecrawl terkena. "
                        f"Retry {retry_count}/{MAX_RETRIES}. "
                        f"Menunggu {wait_time:g} detik...",
                        "ERROR",
                    )

                    time.sleep(wait_time)

                    # Reset jam throttle supaya wait() berikutnya
                    # tidak menambah delay ekstra di atas backoff ini.
                    rate_limiter.last_request_time = time.time()

                    continue

                # ==================================================
                # HTTP selain 200
                # ==================================================

                if response.status_code != 200:
                    log(
                        f"API Firecrawl gagal "
                        f"({response.status_code}). "
                        "Lanjut ke sumber berikutnya...",
                        "ERROR",
                    )
                    break

                # ==================================================
                # Parse JSON
                # ==================================================

                try:
                    json_data = response.json()

                except ValueError:
                    log(
                        "Response Firecrawl bukan JSON "
                        "yang valid.",
                        "ERROR",
                    )
                    break

                data = json_data.get("data", {})

                metadata = data.get("metadata", {})
                markdown = data.get("markdown", "")
                error = data.get("error")

                # ==================================================
                # Firecrawl Error
                # ==================================================

                if error:
                    log(
                        f"Firecrawl Error: {error}",
                        "ERROR",
                    )
                    break

                # ==================================================
                # Status Website Target
                # ==================================================

                target_status = (
                    metadata.get("statusCode")
                    or metadata.get("status_code")
                    or metadata.get("status")
                )

                if target_status:

                    log(
                        f"Status Website Target: "
                        f"{target_status}"
                    )

                    try:
                        if int(target_status) != 200:
                            log(
                                f"Website mengembalikan HTTP "
                                f"{target_status}. "
                                "Lanjut ke sumber berikutnya...",
                                "ERROR",
                            )
                            break

                    except (TypeError, ValueError):
                        log(
                            f"Status website tidak valid: "
                            f"{target_status}",
                            "ERROR",
                        )

                # ==================================================
                # Ambil Title
                # ==================================================

                scraped_title = (
                    metadata.get("ogTitle")
                    or metadata.get("og:title")
                    or metadata.get("title")
                )

                # Fallback ke Markdown
                if not scraped_title and markdown:
                    scraped_title = extract_markdown_title(
                        markdown
                    )

                # Tidak ada title
                if not scraped_title:
                    log(
                        "Metadata title tidak ditemukan. "
                        "Lanjut ke sumber berikutnya...",
                        "ERROR",
                    )
                    break

                title_lower = scraped_title.lower()
                markdown_lower = markdown.lower()

                # ==================================================
                # Deteksi halaman error dari title
                # ==================================================

                if any(
                    keyword in title_lower
                    for keyword in NOT_FOUND_KEYWORDS
                ):
                    log(
                        "Halaman 404 terdeteksi dari judul.",
                        "ERROR",
                    )
                    break

                # ==================================================
                # Deteksi halaman error dari Markdown
                # ==================================================

                if any(
                    keyword in markdown_lower
                    for keyword in NOT_FOUND_KEYWORDS
                ):
                    log(
                        "Halaman 404 terdeteksi dari isi halaman.",
                        "ERROR",
                    )
                    break

                # ==================================================
                # Decode HTML Entity
                # ==================================================

                decoded_title = html.unescape(
                    scraped_title
                ).strip()

                # ==================================================
                # Success
                # ==================================================

                log(
                    f"Judul ditemukan: {decoded_title}",
                    "SUCCESS",
                )

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

    log(
        f"Gagal menemukan judul untuk kode '{code}' "
        "dari semua sumber.",
        "ERROR",
    )

    return ""


# ============================================================
# JSON Checkpoint
# ============================================================

def load_results(
    output_file: Path,
) -> list[dict[str, str]]:
    """
    Membaca checkpoint dari file JSON.

    Jika file belum ada, mengembalikan list kosong.
    """

    if not output_file.exists():
        log(
            f"Checkpoint belum ada: {output_file}"
        )
        return []

    try:
        with output_file.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(
                f"Format checkpoint tidak valid: "
                f"{output_file}. "
                "Format harus berupa JSON array."
            )

        results: list[dict[str, str]] = []

        for item in data:

            if not isinstance(item, dict):
                continue

            nama_file = item.get("nama_file")
            title = item.get("title")

            if not isinstance(nama_file, str):
                continue

            if not isinstance(title, str):
                continue

            if not nama_file or not title:
                continue

            results.append(
                {
                    "nama_file": nama_file,
                    "title": title,
                }
            )

        # Pastikan checkpoint yang dimuat juga terurut
        results.sort(
            key=lambda item: item["nama_file"].lower()
        )

        log(
            f"Checkpoint ditemukan: "
            f"{len(results)} hasil sudah tersimpan."
        )

        return results

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"File checkpoint bukan JSON yang valid: "
            f"{output_file}"
        ) from exc

    except PermissionError as exc:
        raise PermissionError(
            f"Tidak memiliki izin membaca file: "
            f"{output_file}"
        ) from exc

    except OSError as exc:
        raise OSError(
            f"Gagal membaca checkpoint "
            f"'{output_file}': {exc}"
        ) from exc


def save_results(
    results: list[dict[str, str]],
    output_file: Path,
) -> None:
    """
    Menyimpan hasil scraping ke JSON.

    Hasil selalu diurutkan berdasarkan nama_file.

    Menggunakan temporary file dan atomic replace
    untuk menjaga checkpoint tetap aman.
    """

    if not results:
        return

    try:
        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ======================================================
        # Sort berdasarkan nama file
        # ======================================================

        sorted_results = sorted(
            results,
            key=lambda item: item["nama_file"].lower(),
        )

        # ======================================================
        # Temporary file
        # ======================================================

        temporary_file = output_file.with_suffix(
            output_file.suffix + ".tmp"
        )

        with temporary_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                sorted_results,
                file,
                ensure_ascii=False,
                indent=4,
            )

            file.write("\n")

            # Pastikan data ditulis ke filesystem
            file.flush()
            os.fsync(file.fileno())

        # ======================================================
        # Atomic replace
        # ======================================================

        temporary_file.replace(output_file)

    except PermissionError as exc:
        raise PermissionError(
            f"Tidak memiliki izin menulis file: "
            f"{output_file}"
        ) from exc

    except OSError as exc:
        raise OSError(
            f"Gagal menyimpan JSON '{output_file}': "
            f"{exc}"
        ) from exc


# ============================================================
# Processing
# ============================================================

def process_files(
    files: list[Path],
    output_file: Path,
    results: list[dict[str, str]],
    api_key: str,
    rate_limiter: RateLimiter,
) -> list[dict[str, str]]:
    """
    Memproses file satu per satu.

    File yang sudah ada di checkpoint akan dilewati.

    Checkpoint disimpan setiap SAVE_EVERY hasil sukses baru
    (dan selalu di akhir proses) untuk mengurangi I/O.
    """

    total = len(files)

    # ==========================================================
    # Buat set untuk lookup checkpoint
    # ==========================================================

    processed_files = {
        item["nama_file"]
        for item in results
    }

    skipped_count = 0
    success_count = 0
    failed_count = 0

    # Hitung hasil sukses BARU sejak checkpoint terakhir disimpan
    unsaved_since_checkpoint = 0

    for index, file in enumerate(files, start=1):

        code = get_file_code(file)

        # ======================================================
        # Resume
        # ======================================================

        if code in processed_files:

            log(
                f"[{index}/{total}] "
                f"{code} sudah ada di checkpoint. "
                "SKIP."
            )

            skipped_count += 1

            continue

        # ======================================================
        # Scrape
        # ======================================================

        log(
            f"===== [{index}/{total}] "
            f"Memproses: {code} ====="
        )

        title = scrape_title(code, api_key, rate_limiter)

        print()

        log(
            f"nama file : {code}"
        )

        log(
            f"title     : {title or '-'}"
        )

        print()

        # ======================================================
        # Berhasil
        # ======================================================

        if title:

            result = {
                "nama_file": code,
                "title": title,
            }

            results.append(result)

            processed_files.add(code)

            success_count += 1
            unsaved_since_checkpoint += 1

            # ==================================================
            # Simpan checkpoint setiap SAVE_EVERY hasil sukses
            # ==================================================

            if unsaved_since_checkpoint >= SAVE_EVERY:

                save_results(
                    results,
                    output_file,
                )

                log(
                    f"Checkpoint diperbarui. "
                    f"{len(results)} hasil tersimpan "
                    f"ke {output_file}",
                    "SUCCESS",
                )

                unsaved_since_checkpoint = 0

        # ======================================================
        # Gagal
        # ======================================================

        else:

            failed_count += 1

            log(
                f"'{code}' tidak mendapatkan title. "
                "Tidak dimasukkan ke checkpoint.",
                "ERROR",
            )

    # ==========================================================
    # Simpan sisa hasil yang belum sempat di-checkpoint
    # ==========================================================

    if unsaved_since_checkpoint > 0:

        save_results(
            results,
            output_file,
        )

        log(
            f"Checkpoint akhir disimpan. "
            f"{len(results)} hasil tersimpan "
            f"ke {output_file}",
            "SUCCESS",
        )

    # ==========================================================
    # Summary
    # ==========================================================

    print()

    log("========== SUMMARY ==========")
    log(f"Total file       : {total}")
    log(f"Sudah diproses   : {skipped_count}")
    log(f"Berhasil         : {success_count}")
    log(f"Gagal            : {failed_count}")
    log(f"Total checkpoint : {len(results)}")
    log("=============================")

    return results


# ============================================================
# Main
# ============================================================

def main() -> int:
    """Program entry point."""

    args = parse_arguments()

    try:

        # ======================================================
        # Load .env
        # ======================================================

        env_file = (
            Path(__file__).resolve().parent / ".env"
        )

        if not env_file.exists():

            log(
                f"File .env tidak ditemukan: {env_file}",
                "ERROR",
            )

            return 1

        load_dotenv(env_file)

        log(
            f"Memuat environment dari: {env_file}"
        )

        # ======================================================
        # Validate API key (sekali di awal, bukan per-file)
        # ======================================================

        api_key = os.getenv("FIRECRAWL_API_KEY")

        if not api_key:
            log(
                "Environment variable 'FIRECRAWL_API_KEY' "
                "tidak ditemukan!",
                "ERROR",
            )
            return 1

        # ======================================================
        # Validate SOURCES (guard: jangan diam-diam gagal semua)
        # ======================================================

        if not SOURCES:
            log(
                "SOURCES kosong. Tidak ada sumber untuk "
                "di-scrape. Isi daftar SOURCES terlebih dahulu.",
                "ERROR",
            )
            return 1

        # ======================================================
        # Validate directory
        # ======================================================

        validate_directory(args.directory)

        # ======================================================
        # Get files
        # ======================================================

        files = get_files(
            args.directory,
            include_hidden=args.all,
        )

        if not files:

            log(
                "Tidak ada file yang ditemukan di folder.",
                "ERROR",
            )

            return 1

        # ======================================================
        # Reverse
        # ======================================================

        if args.reverse:
            files.reverse()

        log(
            f"Ditemukan {len(files)} file "
            "yang akan diperiksa."
        )

        # ======================================================
        # Load checkpoint
        # ======================================================

        results = load_results(
            args.output
        )

        if results:

            checkpoint_names = {
                item["nama_file"]
                for item in results
            }

            already_processed = sum(
                1
                for file in files
                if get_file_code(file) in checkpoint_names
            )

            remaining = (
                len(files) - already_processed
            )

            log(
                f"Resume aktif: "
                f"{already_processed} file sudah ada "
                f"di checkpoint."
            )

            log(
                f"File yang perlu diproses: {remaining}"
            )

        else:

            log(
                "Tidak ada checkpoint. "
                "Memulai dari awal."
            )

        # ======================================================
        # Rate limiter (Firecrawl free tier: 10 req/menit)
        # ======================================================

        rate_limiter = RateLimiter(MIN_SECONDS_PER_REQUEST)

        # ======================================================
        # Process
        # ======================================================

        results = process_files(
            files,
            args.output,
            results,
            api_key,
            rate_limiter,
        )

        # ======================================================
        # Final
        # ======================================================

        if results:

            log(
                f"Semua proses selesai. "
                f"Total {len(results)} hasil tersimpan "
                f"di {args.output}",
                "SUCCESS",
            )

        else:

            log(
                "Semua proses selesai, tetapi tidak ada "
                "title yang berhasil ditemukan. "
                "File JSON tidak dibuat.",
                "ERROR",
            )

        return 0

    # ==========================================================
    # Ctrl+C
    # ==========================================================

    except KeyboardInterrupt:

        print()

        log(
            "Proses dibatalkan oleh pengguna.",
            "ERROR",
        )

        log(
            "Checkpoint terakhir tetap tersimpan.",
            "INFO",
        )

        return 130

    # ==========================================================
    # Errors
    # ==========================================================

    except FileNotFoundError as exc:

        log(
            str(exc),
            "ERROR",
        )

        return 1

    except NotADirectoryError as exc:

        log(
            str(exc),
            "ERROR",
        )

        return 1

    except PermissionError as exc:

        log(
            str(exc),
            "ERROR",
        )

        return 1

    except ValueError as exc:

        log(
            str(exc),
            "ERROR",
        )

        return 1

    except OSError as exc:

        log(
            str(exc),
            "ERROR",
        )

        return 1


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
