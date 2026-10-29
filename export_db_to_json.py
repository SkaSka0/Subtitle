#!/usr/bin/env python3
"""
export_db_to_json.py

Mengekspor isi tabel `subtitles` dari SQLite ke file JSON, dengan opsi
filter status downloaded dan pengurutan. Database dibuka read-only: data
SQLite tidak diubah.

Contoh:
    python export_db_to_json.py
    python export_db_to_json.py --downloaded 0 -o pending_subtitles.json
    python export_db_to_json.py --sort-name asc
    python export_db_to_json.py --sort-downloaded asc --sort-name desc
    python export_db_to_json.py --sort-time desc --time-field scraped
    python export_db_to_json.py -d subtitles.db -o semua.json --sort-time asc

Jika beberapa flag sort dipakai sekaligus, PRIORITAS mengikuti urutan
penulisan di command line (flag pertama = kunci utama, berikutnya =
kunci tie-breaker).
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path("subtitles.db")
DEFAULT_OUTPUT = Path("subtitles_export.json")

COLUMNS = (
    "id, nama_file, relative_path, title, downloaded, "
    "file_created_at, file_modified_at, file_accessed_at, "
    "file_size, scraped_at"
)

# Kolom timestamp yang bisa dipilih untuk --sort-time.
TIME_FIELDS = {
    "created": "file_created_at",
    "modified": "file_modified_at",
    "accessed": "file_accessed_at",
    "scraped": "scraped_at",
}

# Urutan default jika tidak ada flag sort: oldest -> newest
# (sesuai ARCHITECTURE.md bagian 8).
DEFAULT_SORT = [("time", "asc")]


def log(message: str, level: str = "INFO") -> None:
    print(f"[{level}] {message}", flush=True)


class _SortAction(argparse.Action):
    """Mencatat flag sort sesuai urutan kemunculan di command line.

    Setiap flag menambahkan tuple (kunci, arah) ke `namespace.sort_order`,
    sehingga prioritas sorting = urutan penulisan flag.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        current = list(getattr(namespace, "sort_order", None) or [])
        key = self.dest  # "name" | "downloaded" | "time"
        # Jika flag yang sama ditulis dua kali, yang terakhir menang.
        current = [item for item in current if item[0] != key]
        current.append((key, values))
        namespace.sort_order = current


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mengekspor tabel subtitles dari SQLite ke JSON dengan opsi "
            "pengurutan (nama file, downloaded, waktu)."
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
    parser.add_argument(
        "--downloaded", choices=["0", "1", "all"], default="all",
        help=(
            "Filter berdasarkan status downloaded: 0 = hanya yang belum "
            "(pending), 1 = hanya yang sudah, all = semua (default)."
        ),
    )
    parser.add_argument(
        "--sort-name", dest="name", action=_SortAction,
        choices=["asc", "desc"], metavar="{asc,desc}",
        help="Urutkan berdasarkan nama file (A-Z / Z-A, case-insensitive).",
    )
    parser.add_argument(
        "--sort-downloaded", dest="downloaded", action=_SortAction,
        choices=["asc", "desc"], metavar="{asc,desc}",
        help=(
            "Urutkan berdasarkan status downloaded. "
            "asc = belum downloaded (0) dulu, desc = sudah downloaded (1) dulu."
        ),
    )
    parser.add_argument(
        "--sort-time", dest="time", action=_SortAction,
        choices=["asc", "desc"], metavar="{asc,desc}",
        help="Urutkan berdasarkan waktu (asc = terlama dulu, desc = terbaru dulu).",
    )
    parser.add_argument(
        "--time-field", choices=list(TIME_FIELDS), default="created",
        help=(
            "Kolom waktu yang dipakai untuk --sort-time: "
            "created (default), modified, accessed, atau scraped."
        ),
    )
    parser.set_defaults(sort_order=None)
    return parser.parse_args()


def validate_database(db_file: Path) -> None:
    if not db_file.exists():
        raise FileNotFoundError(f"Database tidak ditemukan: {db_file}")
    if not db_file.is_file():
        raise ValueError(f"Path database bukan sebuah file: {db_file}")


def _direction_sql(direction: str) -> str:
    """Mengubah 'asc'/'desc' menjadi keyword SQL yang aman (whitelist)."""
    return "DESC" if direction == "desc" else "ASC"


def _name_clause(direction: str) -> str:
    return f"nama_file COLLATE NOCASE {_direction_sql(direction)}"


def _downloaded_clause(direction: str) -> str:
    return f"downloaded {_direction_sql(direction)}"


def _time_clause(direction: str, column: str) -> str:
    """Clause sorting kronologis untuk kolom TEXT 'DD-MM-YYYY HH:MM:SS'.

    Komponen disusun ulang sementara menjadi 'YYYY-MM-DD HH:MM:SS' agar
    urutan alfabetis = urutan kronologis (lihat ARCHITECTURE.md bagian 8
    dan sqlite_database_cheatsheet.md bagian 10). Nilai kosong/NULL selalu
    diletakkan di akhir, baik asc maupun desc.
    """
    null_last = (
        f"CASE WHEN {column} IS NULL OR {column} = '' THEN 1 ELSE 0 END ASC"
    )
    chronological = (
        f"substr({column}, 7, 4) || '-' || "
        f"substr({column}, 4, 2) || '-' || "
        f"substr({column}, 1, 2) || ' ' || "
        f"substr({column}, 12, 8) {_direction_sql(direction)}"
    )
    return f"{null_last}, {chronological}"


def build_order_by(sort_order: list[tuple[str, str]], time_field: str) -> str:
    """Menyusun klausa ORDER BY dari daftar (kunci, arah).

    Hanya string dari whitelist di atas yang masuk ke SQL; tidak ada input
    user yang disisipkan langsung. Tie-breaker tetap: relative_path,
    nama_file, id.
    """
    time_column = TIME_FIELDS[time_field]
    builders = {
        "name": _name_clause,
        "downloaded": _downloaded_clause,
        "time": lambda direction: _time_clause(direction, time_column),
    }

    clauses = [builders[key](direction) for key, direction in sort_order]
    clauses += [
        "relative_path ASC",
        "nama_file COLLATE NOCASE ASC",
        "id ASC",
    ]
    return ",\n            ".join(clauses)


def _build_where(downloaded: str) -> tuple[str, tuple]:
    """Menyusun klausa WHERE dan parameternya dari nilai --downloaded.

    Nilai filter dikirim sebagai parameter SQL (?), bukan disisipkan ke
    string query.
    """
    if downloaded == "all":
        return "", ()
    return "WHERE downloaded = ?", (int(downloaded),)


def fetch_rows(db_file: Path, order_by: str, downloaded: str = "all") -> list[dict]:
    """Membaca record subtitles (read-only) sesuai filter dan ORDER BY."""
    where_sql, params = _build_where(downloaded)
    query = f"""
        SELECT {COLUMNS}
        FROM subtitles
        {where_sql}
        ORDER BY
            {order_by}
    """
    uri = f"{db_file.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise RuntimeError(f"Gagal membaca database '{db_file}': {exc}") from exc

    return [dict(row) for row in rows]


def write_json_atomic(records: list[dict], output_file: Path) -> None:
    """Menulis JSON secara atomic (tulis ke .tmp lalu replace)."""
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = output_file.with_suffix(output_file.suffix + ".tmp")
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=4)
            file.write("\n")
            file.flush()
        temporary_file.replace(output_file)
    except OSError as exc:
        raise OSError(f"Gagal menyimpan JSON '{output_file}': {exc}") from exc


def describe_sort(sort_order: list[tuple[str, str]], time_field: str) -> str:
    labels = {"name": "nama_file", "downloaded": "downloaded", "time": f"waktu({time_field})"}
    return " -> ".join(f"{labels[key]} {direction}" for key, direction in sort_order)


def main() -> int:
    args = parse_arguments()
    sort_order = args.sort_order or DEFAULT_SORT

    try:
        validate_database(args.db)
        order_by = build_order_by(sort_order, args.time_field)
        records = fetch_rows(args.db, order_by, args.downloaded)
        write_json_atomic(records, args.output)

        log(f"Database        : {args.db}")
        filter_label = "semua" if args.downloaded == "all" else f"downloaded = {args.downloaded}"
        log(f"Filter          : {filter_label}")
        log(f"Urutan          : {describe_sort(sort_order, args.time_field)}")
        log(f"Record diekspor : {len(records)}")
        log(f"JSON dibuat     : {args.output}", "SUCCESS")
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        log(str(exc), "ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
