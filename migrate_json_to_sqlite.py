#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys
from pathlib import Path


DEFAULT_DB = Path("subtitles.db")


SCHEMA = """
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
);

CREATE INDEX IF NOT EXISTS idx_subtitles_nama_file
ON subtitles(nama_file);

CREATE INDEX IF NOT EXISTS idx_subtitles_relative_path
ON subtitles(relative_path);
"""


def log(message: str, level: str = "INFO") -> None:
    print(f"[{level}] {message}", flush=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrasi checkpoint JSON subtitle ke SQLite."
    )

    parser.add_argument(
        "json_file",
        type=Path,
        help="File JSON checkpoint lama, misalnya results.json",
    )

    parser.add_argument(
        "-d",
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Database SQLite tujuan (default: subtitles.db)",
    )

    return parser.parse_args()


def load_json(json_file: Path) -> list[dict]:
    """Membaca JSON checkpoint tanpa membuang field kosong."""

    if not json_file.exists():
        raise FileNotFoundError(
            f"File JSON tidak ditemukan: {json_file}"
        )

    if not json_file.is_file():
        raise ValueError(
            f"Path bukan file: {json_file}"
        )

    try:
        with json_file.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON tidak valid: {json_file} "
            f"(baris {exc.lineno}, kolom {exc.colno})"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Gagal membaca JSON '{json_file}': {exc}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError(
            "Format JSON tidak valid. Root harus berupa JSON array."
        )

    return data


def normalize_record(item: object, index: int) -> dict:
    """
    Mengubah satu record JSON menjadi bentuk yang aman untuk SQLite.

    Field kosong TIDAK dibuang.
    """

    if not isinstance(item, dict):
        raise ValueError(
            f"Record JSON #{index} bukan object/dictionary."
        )

    nama_file = item.get("nama_file")

    if not isinstance(nama_file, str) or not nama_file:
        raise ValueError(
            f"Record JSON #{index} tidak memiliki 'nama_file' "
            "yang valid."
        )

    title = item.get("title")

    if title is not None and not isinstance(title, str):
        title = str(title)

    downloaded = item.get("downloaded", False)

    if isinstance(downloaded, bool):
        downloaded_value = 1 if downloaded else 0
    else:
        # Data lama yang tidak valid tidak boleh membuat migrasi
        # diam-diam salah. Gunakan default aman false.
        downloaded_value = 0

    timestamp = item.get("timestamp", "")
    if not isinstance(timestamp, str):
        timestamp = ""

    file_created_at = item.get("file_created_at", "")
    if not isinstance(file_created_at, str):
        file_created_at = ""

    file_modified_at = item.get("file_modified_at", "")
    if not isinstance(file_modified_at, str):
        file_modified_at = ""

    file_accessed_at = item.get("file_accessed_at", "")
    if not isinstance(file_accessed_at, str):
        file_accessed_at = ""

    file_size = item.get("file_size", 0)

    if (
        not isinstance(file_size, int)
        or isinstance(file_size, bool)
        or file_size < 0
    ):
        file_size = 0

    return {
        "nama_file": nama_file,
        # Recursive processing belum P1.
        # Karena JSON lama tidak menyimpan relative path,
        # nilainya NULL.
        "relative_path": None,
        "title": title,
        "downloaded": downloaded_value,
        "file_created_at": file_created_at,
        "file_modified_at": file_modified_at,
        "file_accessed_at": file_accessed_at,
        "file_size": file_size,
        # timestamp dari JSON lama menjadi scraped_at.
        "scraped_at": timestamp,
    }


def database_has_data(connection: sqlite3.Connection) -> bool:
    """Memastikan database target tidak sudah berisi data."""

    row = connection.execute(
        "SELECT COUNT(*) FROM subtitles"
    ).fetchone()

    return bool(row and row[0] > 0)


def create_database(connection: sqlite3.Connection) -> None:
    """Membuat schema SQLite."""

    connection.executescript(SCHEMA)


def migrate(
    json_records: list[dict],
    connection: sqlite3.Connection,
) -> int:
    """
    Migrasi seluruh record dalam satu transaction.

    Tidak menggunakan INSERT OR IGNORE karena duplicate dari JSON
    tidak boleh diam-diam hilang.
    """

    normalized_records = []

    for index, item in enumerate(json_records, start=1):
        normalized_records.append(
            normalize_record(item, index)
        )

    insert_sql = """
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
            :nama_file,
            :relative_path,
            :title,
            :downloaded,
            :file_created_at,
            :file_modified_at,
            :file_accessed_at,
            :file_size,
            :scraped_at
        )
    """

    connection.execute("BEGIN")

    try:
        connection.executemany(
            insert_sql,
            normalized_records,
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return len(normalized_records)


def verify_counts(
    json_count: int,
    connection: sqlite3.Connection,
) -> bool:
    """Memastikan jumlah record JSON dan SQLite sama."""

    row = connection.execute(
        "SELECT COUNT(*) FROM subtitles"
    ).fetchone()

    sqlite_count = row[0] if row else 0

    log(f"Jumlah record JSON    : {json_count}")
    log(f"Jumlah record SQLite  : {sqlite_count}")

    if json_count != sqlite_count:
        log(
            "Jumlah record tidak sama!",
            "ERROR",
        )
        return False

    log(
        "Jumlah record JSON dan SQLite sama.",
        "SUCCESS",
    )

    return True


def print_summary(
    json_records: list[dict],
    connection: sqlite3.Connection,
) -> None:
    """Menampilkan statistik migrasi."""

    total = len(json_records)

    empty_title = sum(
        1
        for item in json_records
        if not item.get("title")
    )

    downloaded = sum(
        1
        for item in json_records
        if item.get("downloaded") is True
    )

    row = connection.execute(
        "SELECT COUNT(*) FROM subtitles"
    ).fetchone()

    sqlite_count = row[0] if row else 0

    print()
    log("MIGRATION SUMMARY")
    log(f"Record JSON           : {total}")
    log(f"Record SQLite         : {sqlite_count}")
    log(f"Title kosong          : {empty_title}")
    log(f"Downloaded = true     : {downloaded}")
    log(f"Downloaded = false    : {total - downloaded}")
    print()


def main() -> int:
    args = parse_arguments()

    connection = None

    try:
        log(f"Membaca JSON: {args.json_file}")

        json_records = load_json(args.json_file)

        log(
            f"Ditemukan {len(json_records)} record di JSON."
        )

        if not json_records:
            log(
                "JSON kosong. Tidak ada migrasi yang dilakukan.",
                "ERROR",
            )
            return 1

        # Jangan membuat/mengubah database sebelum JSON berhasil
        # dibaca dan divalidasi secara keseluruhan.
        args.db.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        connection = sqlite3.connect(args.db)

        # Foreign key siap digunakan jika schema berkembang nanti.
        connection.execute("PRAGMA foreign_keys = ON")

        create_database(connection)

        if database_has_data(connection):
            log(
                f"Database '{args.db}' sudah berisi data.",
                "ERROR",
            )
            log(
                "Migrasi dibatalkan untuk mencegah duplicate atau "
                "perubahan data existing.",
                "ERROR",
            )
            return 1

        log("Database target masih kosong.")
        log("Memulai transaction migrasi...")

        migrated_count = migrate(
            json_records,
            connection,
        )

        log(
            f"{migrated_count} record berhasil dimasukkan ke SQLite.",
            "SUCCESS",
        )

        if not verify_counts(
            len(json_records),
            connection,
        ):
            return 1

        print_summary(
            json_records,
            connection,
        )

        log(
            f"Migrasi selesai: {args.db}",
            "SUCCESS",
        )

        log(
            f"JSON asli TIDAK dihapus: {args.json_file}",
            "INFO",
        )

        return 0

    except KeyboardInterrupt:
        print()
        log(
            "Migrasi dibatalkan oleh pengguna.",
            "ERROR",
        )

        if connection is not None:
            connection.rollback()

        return 130

    except (
        FileNotFoundError,
        ValueError,
        OSError,
        sqlite3.Error,
    ) as exc:
        if connection is not None:
            connection.rollback()

        log(str(exc), "ERROR")
        log(
            "Tidak ada penghapusan terhadap file JSON sumber.",
            "INFO",
        )

        return 1

    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
