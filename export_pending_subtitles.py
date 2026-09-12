#!/usr/bin/env python3

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path("subtitles.db")
DEFAULT_OUTPUT = Path("pending_subtitles.json")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mengekspor data subtitle yang belum downloaded "
            "(downloaded = 0) dari SQLite ke file JSON."
        )
    )
    parser.add_argument(
        "-d", "--db", type=Path, default=DEFAULT_DB,
        help=f"File SQLite database (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"File JSON output (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def validate_database(db_file: Path) -> None:
    if not db_file.exists():
        raise FileNotFoundError(f"Database tidak ditemukan: {db_file}")
    if not db_file.is_file():
        raise ValueError(f"Path database bukan sebuah file: {db_file}")


def export_pending_subtitles(db_file: Path, output_file: Path) -> int:
    # PERBAIKAN: file_created_at disimpan sebagai TEXT dengan format
    # 'DD-MM-YYYY HH:MM:SS'. ORDER BY langsung pada string ini akan
    # mengurutkan berdasarkan karakter pertama (hari), bukan secara
    # kronologis (tahun -> bulan -> hari -> jam), sehingga hasilnya
    # bisa salah urutan (mis. '01-01-2026' muncul sebelum
    # '15-12-2025' meskipun 2025 lebih lama).
    #
    # Susun ulang komponennya sementara menjadi 'YYYY-MM-DD HH:MM:SS'
    # (dapat dibandingkan secara alfabetis dengan benar) memakai
    # substr(), sama seperti pola yang didokumentasikan di
    # sqlite_database_cheatsheet.md bagian 10. Ini hanya mengubah
    # urutan tampilan pada saat query, tidak mengubah nilai yang
    # tersimpan di SQLite.
    #
    # Baris dengan file_created_at kosong/NULL diletakkan di akhir
    # (bukan tercampur di awal akibat string kosong "" < digit).
    query = """
        SELECT
            id,
            nama_file,
            relative_path,
            title,
            downloaded,
            file_created_at,
            file_modified_at,
            file_accessed_at,
            file_size,
            scraped_at
        FROM subtitles
        WHERE downloaded = 0
        ORDER BY
            CASE
                WHEN file_created_at IS NULL OR file_created_at = '' THEN 1
                ELSE 0
            END ASC,
            substr(file_created_at, 7, 4) || '-' ||
            substr(file_created_at, 4, 2) || '-' ||
            substr(file_created_at, 1, 2) || ' ' ||
            substr(file_created_at, 12, 8) ASC,
            relative_path ASC,
            nama_file ASC,
            id ASC
    """

    try:
        with sqlite3.connect(db_file) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query).fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Gagal membaca database '{db_file}': {exc}") from exc

    results = [dict(row) for row in rows]

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = output_file.with_suffix(output_file.suffix + ".tmp")
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(results, file, ensure_ascii=False, indent=4)
            file.write("\n")
            file.flush()
        temporary_file.replace(output_file)
    except OSError as exc:
        raise OSError(f"Gagal menyimpan JSON '{output_file}': {exc}") from exc

    return len(results)


def main() -> int:
    args = parse_arguments()
    try:
        validate_database(args.db)
        count = export_pending_subtitles(args.db, args.output)
        print(f"[INFO] Database        : {args.db}")
        print(f"[INFO] Filter          : downloaded = 0")
        print(f"[INFO] Data ditemukan  : {count}")
        print(f"[SUCCESS] JSON dibuat : {args.output}")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
