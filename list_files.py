#!/usr/bin/env python3

import argparse
import html
import json
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

# Simpan checkpoint setiap N hasil sukses, bukan tiap 1 file,
# untuk mengurangi I/O berulang menulis seluruh JSON.
SAVE_EVERY = 5

SOURCES = [
    "https://123av.com/en/v/{code}",
    "https://missav.ws/dm2/en/{code}",
    "https://podjav.tv/movies/{code}/",
]

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
    """Format: dd-mm-yyyy jam:menit:detik, mis. 22-08-2026 14:05:09."""
    return datetime.now().strftime("%d-%m-%Y %H:%M:%S")


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
        description="Mengambil nama file dari sebuah folder dan "
        "melakukan scraping title menggunakan Firecrawl."
    )
    parser.add_argument(
        "directory", type=Path,
        help="Folder yang berisi file-file yang akan diproses",
    )
    parser.add_argument(
        "-a", "--all", action="store_true",
        help="Sertakan file tersembunyi",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("results.json"),
        help="File JSON output/checkpoint (default: results.json)",
    )
    parser.add_argument(
        "-r", "--reverse", action="store_true",
        help="Proses file dalam urutan terbalik",
    )
    return parser.parse_args()


def validate_directory(directory: Path) -> None:
    if not directory.exists():
        raise FileNotFoundError(f"Folder tidak ditemukan: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Path bukan sebuah folder: {directory}")


def get_files(directory: Path, include_hidden: bool = False) -> list[Path]:
    """Mengambil file yang berada langsung di dalam folder (tidak recursive)."""
    files: list[Path] = []
    try:
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            if not include_hidden and entry.name.startswith("."):
                continue
            files.append(entry)
    except PermissionError as exc:
        raise PermissionError(f"Tidak memiliki izin membaca folder: {directory}") from exc
    except OSError as exc:
        raise OSError(f"Gagal membaca folder '{directory}': {exc}") from exc

    return sorted(files, key=lambda file: file.name.lower())


def get_file_code(file: Path) -> str:
    """Nama file tanpa ekstensi. File tersembunyi (mis. .bashrc)
    dianggap tidak memiliki ekstensi."""
    if file.name.startswith(".") and file.name.count(".") == 1:
        return file.name
    return file.stem


def scrape_title(code: str, api_key: str, rate_limiter: RateLimiter) -> str:
    """Mencoba tiap source di SOURCES satu per satu lewat Firecrawl.
    Retry hingga MAX_RETRIES pada HTTP 429, mengikuti Retry-After
    jika tersedia, jika tidak pakai exponential backoff."""

    lower_code = code.lower()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for source_template in SOURCES:
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
                        log(f"HTTP 429 masih terjadi setelah {MAX_RETRIES} kali retry. "
                            "Lanjut ke sumber berikutnya...", "ERROR")
                        break

                    retry_count += 1
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            wait_time = 2 ** retry_count
                    else:
                        wait_time = 2 ** retry_count  # 2s, 4s, 8s

                    log(f"Rate limit Firecrawl terkena. Retry {retry_count}/{MAX_RETRIES}. "
                        f"Menunggu {wait_time:g} detik...", "ERROR")
                    time.sleep(wait_time)

                    # Reset jam throttle supaya wait() berikutnya tidak
                    # menambah delay ekstra di atas backoff ini.
                    rate_limiter.last_request_time = time.time()
                    continue

                if response.status_code != 200:
                    log(f"API Firecrawl gagal ({response.status_code}). "
                        "Lanjut ke sumber berikutnya...", "ERROR")
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
                            log(f"Website mengembalikan HTTP {target_status}. "
                                "Lanjut ke sumber berikutnya...", "ERROR")
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
                    log("Metadata title tidak ditemukan. "
                        "Lanjut ke sumber berikutnya...", "ERROR")
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
                log("Request ke Firecrawl timeout. "
                    "Lanjut ke sumber berikutnya...", "ERROR")
                break
            except requests.ConnectionError as exc:
                log(f"Gagal terhubung ke Firecrawl: {exc}. "
                    "Lanjut ke sumber berikutnya...", "ERROR")
                break
            except requests.RequestException as exc:
                log(f"Request ke Firecrawl gagal: {exc}. "
                    "Lanjut ke sumber berikutnya...", "ERROR")
                break
            except Exception as exc:
                log(f"Terjadi error tidak terduga: {exc}. "
                    "Lanjut ke sumber berikutnya...", "ERROR")
                break

    log(f"Gagal menemukan judul untuk kode '{code}' dari semua sumber.", "ERROR")
    return ""


def load_results(output_file: Path) -> list[dict[str, str]]:
    """Membaca checkpoint dari file JSON. Mengembalikan list kosong jika belum ada."""
    if not output_file.exists():
        log(f"Checkpoint belum ada: {output_file}")
        return []

    try:
        with output_file.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(
                f"Format checkpoint tidak valid: {output_file}. "
                "Format harus berupa JSON array."
            )

        results: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            nama_file = item.get("nama_file")
            title = item.get("title")
            if not isinstance(nama_file, str) or not isinstance(title, str):
                continue
            if not nama_file or not title:
                continue

            downloaded = item.get("downloaded", False)
            if not isinstance(downloaded, bool):
                downloaded = False

            timestamp = item.get("timestamp", "")
            if not isinstance(timestamp, str):
                timestamp = ""

            results.append({
                "nama_file": nama_file,
                "title": title,
                "downloaded": downloaded,
                "timestamp": timestamp,
            })

        results.sort(key=lambda item: item["nama_file"].lower())
        log(f"Checkpoint ditemukan: {len(results)} hasil sudah tersimpan.")
        return results

    except json.JSONDecodeError as exc:
        raise ValueError(f"File checkpoint bukan JSON yang valid: {output_file}") from exc
    except PermissionError as exc:
        raise PermissionError(f"Tidak memiliki izin membaca file: {output_file}") from exc
    except OSError as exc:
        raise OSError(f"Gagal membaca checkpoint '{output_file}': {exc}") from exc


def save_results(results: list[dict[str, str]], output_file: Path) -> None:
    """Menyimpan hasil scraping ke JSON (terurut, atomic replace via temp file)."""
    if not results:
        return

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        sorted_results = sorted(results, key=lambda item: item["nama_file"].lower())

        temporary_file = output_file.with_suffix(output_file.suffix + ".tmp")
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(sorted_results, file, ensure_ascii=False, indent=4)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        temporary_file.replace(output_file)

    except PermissionError as exc:
        raise PermissionError(f"Tidak memiliki izin menulis file: {output_file}") from exc
    except OSError as exc:
        raise OSError(f"Gagal menyimpan JSON '{output_file}': {exc}") from exc


def process_files(
    files: list[Path],
    output_file: Path,
    results: list[dict[str, str]],
    api_key: str,
    rate_limiter: RateLimiter,
) -> list[dict[str, str]]:
    """Memproses file satu per satu, skip yang sudah ada di checkpoint.
    Checkpoint disimpan tiap SAVE_EVERY hasil sukses baru (dan di akhir)."""

    total = len(files)
    processed_files = {item["nama_file"] for item in results}

    skipped_count = success_count = failed_count = 0
    unsaved_since_checkpoint = 0

    for index, file in enumerate(files, start=1):
        code = get_file_code(file)

        if code in processed_files:
            log(f"[{index}/{total}] {code} sudah ada di checkpoint. SKIP.")
            skipped_count += 1
            continue

        log(f"===== [{index}/{total}] Memproses: {code} =====")
        title = scrape_title(code, api_key, rate_limiter)

        print()
        log(f"nama file : {code}")
        log(f"title     : {title or '-'}")
        print()

        if title:
            results.append({
                "nama_file": code,
                "title": title,
                "downloaded": False,
                "timestamp": current_timestamp(),
            })
            processed_files.add(code)
            success_count += 1
            unsaved_since_checkpoint += 1

            if unsaved_since_checkpoint >= SAVE_EVERY:
                save_results(results, output_file)
                log(f"Checkpoint diperbarui. {len(results)} hasil tersimpan "
                    f"ke {output_file}", "SUCCESS")
                unsaved_since_checkpoint = 0
        else:
            failed_count += 1
            log(f"'{code}' tidak mendapatkan title. "
                "Tidak dimasukkan ke checkpoint.", "ERROR")

    if unsaved_since_checkpoint > 0:
        save_results(results, output_file)
        log(f"Checkpoint akhir disimpan. {len(results)} hasil tersimpan "
            f"ke {output_file}", "SUCCESS")

    print()
    log("SUMMARY")
    log(f"Total file       : {total}")
    log(f"Sudah diproses   : {skipped_count}")
    log(f"Berhasil         : {success_count}")
    log(f"Gagal            : {failed_count}")
    log(f"Total checkpoint : {len(results)}")

    return results


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
            log("Environment variable 'FIRECRAWL_API_KEY' tidak ditemukan!", "ERROR")
            return 1

        if not SOURCES:
            log("SOURCES kosong. Tidak ada sumber untuk di-scrape. "
                "Isi daftar SOURCES terlebih dahulu.", "ERROR")
            return 1

        validate_directory(args.directory)
        files = get_files(args.directory, include_hidden=args.all)

        if not files:
            log("Tidak ada file yang ditemukan di folder.", "ERROR")
            return 1

        if args.reverse:
            files.reverse()

        log(f"Ditemukan {len(files)} file yang akan diperiksa.")

        results = load_results(args.output)
        if results:
            checkpoint_names = {item["nama_file"] for item in results}
            already_processed = sum(
                1 for file in files if get_file_code(file) in checkpoint_names
            )
            log(f"Resume aktif: {already_processed} file sudah ada di checkpoint.")
            log(f"File yang perlu diproses: {len(files) - already_processed}")
        else:
            log("Tidak ada checkpoint. Memulai dari awal.")

        rate_limiter = RateLimiter(MIN_SECONDS_PER_REQUEST)
        results = process_files(files, args.output, results, api_key, rate_limiter)

        if results:
            log(f"Semua proses selesai. Total {len(results)} hasil tersimpan "
                f"di {args.output}", "SUCCESS")
        else:
            log("Semua proses selesai, tetapi tidak ada title yang berhasil "
                "ditemukan. File JSON tidak dibuat.", "ERROR")

        return 0

    except KeyboardInterrupt:
        print()
        log("Proses dibatalkan oleh pengguna.", "ERROR")
        log("Checkpoint terakhir tetap tersimpan.", "INFO")
        return 130

    except (FileNotFoundError, NotADirectoryError, PermissionError, ValueError, OSError) as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
