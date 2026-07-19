#!/usr/bin/env python3
"""
batch_add_extension.py

Skrip untuk menambahkan ekstensi ke file-file yang belum memiliki ekstensi
di dalam sebuah folder (opsional secara rekursif).

Contoh penggunaan:
    python batch_add_extension.py -f ~/Documents/berkas -e txt
    python batch_add_extension.py -f ~/Documents/berkas -e jpg -r
    python batch_add_extension.py -f ~/Documents/berkas -e pdf -r --dry-run
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


def unique_destination(dest: Path) -> Path:
    """
    Kalau path 'dest' sudah ada, cari nama alternatif dengan menambahkan
    ' (1)', ' (2)', dst di belakang nama (sebelum ekstensi kalau ada).
    """
    if not dest.exists():
        return dest

    counter = 1
    while True:
        candidate = dest.with_name(f"{dest.stem} ({counter}){dest.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def rel_path(p: Path, base: Path) -> str:
    """Path relatif terhadap folder target, untuk tampilan yang ringkas."""
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def truncate_middle(s: str, max_len: int) -> str:
    """
    Pangkas bagian TENGAH string kalau lebih panjang dari max_len,
    supaya nama file (bagian akhir) tetap terlihat jelas.
    Contoh: 'folder/sangat/panjang/sekali/file.txt' -> 'folder/san...ali/file.txt'
    """
    if max_len <= 3 or len(s) <= max_len:
        return s

    keep = max_len - 3  # ruang untuk "..."
    head = (keep + 1) // 2
    tail = keep - head
    return f"{s[:head]}...{s[-tail:]}" if tail > 0 else f"{s[:head]}..."


def get_max_path_len(override: int = None) -> int:
    """
    Menentukan panjang maksimum path yang ditampilkan, berdasarkan lebar
    terminal saat ini (kecuali user menentukan sendiri lewat --max-path-len).
    """
    if override:
        return override

    term_width = shutil.get_terminal_size(fallback=(100, 24)).columns
    # Sisakan ruang untuk indentasi, panah "->"/"=>", dan margin kanan
    max_len = (term_width - 20) // 2
    return max(15, min(60, max_len))


def has_extension(filename: str) -> bool:
    """Cek apakah nama file sudah memiliki ekstensi (mengandung titik)."""
    return "." in Path(filename).name


def collect_files(folder: Path, recursive: bool):
    """
    Mengumpulkan daftar file di dalam folder.
    File dan folder tersembunyi (nama diawali titik, misal '.cache' atau
    '.bashrc') akan dilewati sepenuhnya dan tidak ikut diproses.
    """
    if not recursive:
        return [
            p for p in folder.iterdir()
            if p.is_file() and not p.name.startswith(".")
        ]

    files = []
    for root, dirnames, filenames in os.walk(folder):
        # Buang folder tersembunyi dari daftar dirnames agar os.walk
        # tidak masuk ke dalamnya
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for filename in filenames:
            if filename.startswith("."):
                continue
            files.append(Path(root) / filename)

    return files


def build_plan(files, extension: str):
    """
    Membangun rencana rename: list of tuple (file_lama, file_baru, status).
    status: 'ok', 'skip_has_ext', atau 'skip_exists'
    """
    plan = []
    for file_path in files:
        if has_extension(file_path.name):
            plan.append((file_path, None, "skip_has_ext"))
            continue

        new_path = file_path.with_name(f"{file_path.name}.{extension}")

        if new_path.exists():
            plan.append((file_path, new_path, "skip_exists"))
            continue

        plan.append((file_path, new_path, "ok"))

    return plan


def print_plan(plan, folder: Path, max_len: int):
    """Menampilkan daftar file yang akan diubah beserta nama barunya."""
    to_rename = [item for item in plan if item[2] == "ok"]
    skipped = [item for item in plan if item[2] != "ok"]

    def fmt(p: Path) -> str:
        return truncate_middle(rel_path(p, folder), max_len)

    print("=== Daftar file yang AKAN diubah ===")
    if not to_rename:
        print("(tidak ada file yang perlu diubah)")
    else:
        for old_path, new_path, _ in to_rename:
            print(f"  {fmt(old_path)}  ->  {fmt(new_path)}")

    if skipped:
        duplikat = [item for item in skipped if item[2] == "skip_exists"]
        if duplikat:
            print("\n=== Daftar file yang DILEWATI (duplikat) ===")
            for old_path, new_path, _ in duplikat:
                print(f"  {fmt(old_path)} => {fmt(new_path)}")

    print()


def handle_duplicates(duplikat_items, folder: Path, action: str, duplicate_folder_name: str, dry_run: bool, max_len: int):
    """
    Memproses file-file yang dilewati karena duplikat, sesuai 'action':
    - 'skip'  : tidak melakukan apa-apa (dibiarkan di tempat).
    - 'trash' : pindahkan ke trash sistem (butuh library send2trash).
    - 'move'  : pindahkan ke satu folder khusus di dalam 'folder'.

    Mengembalikan (jumlah_berhasil, jumlah_gagal, daftar_record_aksi).
    """
    if action == "skip" or not duplikat_items:
        return 0, 0, []

    def fmt(p: Path) -> str:
        return truncate_middle(rel_path(p, folder), max_len)

    berhasil = 0
    gagal = 0
    records = []

    if action == "trash":
        try:
            from send2trash import send2trash
        except ImportError:
            print(
                "\n[ERROR] Library 'send2trash' belum terinstal, tidak bisa "
                "memindahkan file ke trash.\n"
                "Install dulu dengan: pip install send2trash --break-system-packages\n"
                "File duplikat dibiarkan di tempat (tidak diproses).",
                file=sys.stderr
            )
            return 0, len(duplikat_items), []

        print("\n=== Memindahkan file duplikat ke trash ===")
        for old_path, _new_path, _status in duplikat_items:
            if dry_run:
                print(f"  [DRY-RUN] {fmt(old_path)} -> (trash)")
                berhasil += 1
                continue
            try:
                send2trash(str(old_path))
                print(f"  [TRASH] {fmt(old_path)}")
                berhasil += 1
                records.append({
                    "type": "duplicate_trash",
                    "from": str(old_path),
                    "to": None,
                    "status": "success",
                    "error": None,
                })
            except Exception as e:
                print(f"  [GAGAL] {fmt(old_path)}: {e}", file=sys.stderr)
                gagal += 1
                records.append({
                    "type": "duplicate_trash",
                    "from": str(old_path),
                    "to": None,
                    "status": "failed",
                    "error": str(e),
                })

    elif action == "move":
        duplicate_dir = folder / duplicate_folder_name
        print(f"\n=== Memindahkan file duplikat ke folder '{duplicate_folder_name}' ===")

        if not dry_run:
            duplicate_dir.mkdir(parents=True, exist_ok=True)

        for old_path, _new_path, _status in duplikat_items:
            target = unique_destination(duplicate_dir / old_path.name)
            target_display = truncate_middle(f"{duplicate_folder_name}/{target.name}", max_len)
            if dry_run:
                print(f"  [DRY-RUN] {fmt(old_path)} -> {target_display}")
                berhasil += 1
                continue
            try:
                shutil.move(str(old_path), str(target))
                print(f"  [PINDAH] {fmt(old_path)} -> {target_display}")
                berhasil += 1
                records.append({
                    "type": "duplicate_move",
                    "from": str(old_path),
                    "to": str(target),
                    "status": "success",
                    "error": None,
                })
            except OSError as e:
                print(f"  [GAGAL] {fmt(old_path)}: {e}", file=sys.stderr)
                gagal += 1
                records.append({
                    "type": "duplicate_move",
                    "from": str(old_path),
                    "to": str(target),
                    "status": "failed",
                    "error": str(e),
                })

    return berhasil, gagal, records


def write_log(folder: Path, args, actions: list, summary: dict) -> Path:
    """
    Menulis manifest/log hasil eksekusi ke folder/.history/ dalam format JSON,
    satu file per eksekusi dengan nama berdasarkan timestamp.
    """
    history_dir = folder / ".history"
    history_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now()
    log_path = history_dir / f"batch_rename_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"

    data = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "command": {
            "folder": str(folder),
            "extension": args.extension.lstrip(".").strip(),
            "recursive": args.recursive,
            "duplicate_action": args.duplicate_action,
            "duplicate_folder": args.duplicate_folder,
        },
        "actions": actions,
        "summary": summary,
    }

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return log_path


def main():
    parser = argparse.ArgumentParser(
        description="Menambahkan ekstensi ke file yang belum memiliki ekstensi."
    )
    parser.add_argument(
        "-f", "--folder",
        required=True,
        type=str,
        help="Path folder yang berisi file-file yang akan diproses."
    )
    parser.add_argument(
        "-e", "--extension",
        required=True,
        type=str,
        help="Ekstensi target yang akan ditambahkan (tanpa titik, misal: 'txt')."
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Jalankan secara rekursif ke semua subfolder."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hanya menampilkan rencana rename tanpa benar-benar mengubah nama file."
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Langsung eksekusi tanpa perlu konfirmasi manual."
    )
    parser.add_argument(
        "--duplicate-action",
        choices=["skip", "trash", "move"],
        default="skip",
        help=(
            "Perlakuan untuk file yang dilewati karena nama duplikat sudah ada: "
            "'skip' (biarkan, default), 'trash' (pindah ke trash sistem, "
            "butuh library 'send2trash'), 'move' (pindah ke folder khusus)."
        )
    )
    parser.add_argument(
        "--duplicate-folder",
        type=str,
        default="_duplikat",
        help=(
            "Nama folder khusus untuk menampung file duplikat saat "
            "--duplicate-action=move. Folder ini dibuat otomatis di dalam "
            "folder target (-f). Default: '_duplikat'."
        )
    )
    parser.add_argument(
        "--max-path-len",
        type=int,
        default=None,
        help=(
            "Panjang maksimum path yang ditampilkan di terminal sebelum "
            "dipangkas dengan '...'. Default: menyesuaikan lebar terminal "
            "secara otomatis."
        )
    )

    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    extension = args.extension.lstrip(".").strip()

    if not extension:
        print("Error: ekstensi tidak boleh kosong.", file=sys.stderr)
        sys.exit(1)

    if not folder.exists() or not folder.is_dir():
        print(f"Error: folder '{folder}' tidak ditemukan atau bukan direktori.", file=sys.stderr)
        sys.exit(1)

    files = collect_files(folder, args.recursive)

    if not files:
        print(f"Tidak ada file ditemukan di '{folder}'.")
        return

    plan = build_plan(files, extension)
    max_len = get_max_path_len(args.max_path_len)
    print_plan(plan, folder, max_len)

    to_rename = [item for item in plan if item[2] == "ok"]
    duplikat_items = [item for item in plan if item[2] == "skip_exists"]
    total_skip_has_ext = len([item for item in plan if item[2] == "skip_has_ext"])

    if args.duplicate_action != "skip" and duplikat_items:
        aksi_label = "trash" if args.duplicate_action == "trash" else f"folder '{args.duplicate_folder}'"
        print(f"({len(duplikat_items)} file duplikat akan diproses ke {aksi_label})")

    if not to_rename and not (args.duplicate_action != "skip" and duplikat_items):
        print("Tidak ada file yang perlu diproses.")
        return

    if args.dry_run:
        handle_duplicates(duplikat_items, folder, args.duplicate_action, args.duplicate_folder, dry_run=True, max_len=max_len)
        print("\n(Mode dry-run: tidak ada perubahan nyata yang dilakukan)")
        return

    if not args.yes:
        total_aksi = len(to_rename) + (len(duplikat_items) if args.duplicate_action != "skip" else 0)
        jawaban = input(f"Lanjutkan proses {total_aksi} file di atas? [y/N] ").strip().lower()
        if jawaban not in ("y", "yes"):
            print("Dibatalkan.")
            return

    total_renamed = 0
    rename_records = []
    for old_path, new_path, _ in to_rename:
        try:
            old_path.rename(new_path)
            print(f"[RENAME] {truncate_middle(rel_path(old_path, folder), max_len)} -> {truncate_middle(rel_path(new_path, folder), max_len)}")
            total_renamed += 1
            rename_records.append({
                "type": "rename",
                "from": str(old_path),
                "to": str(new_path),
                "status": "success",
                "error": None,
            })
        except OSError as e:
            print(f"[GAGAL] {old_path}: {e}", file=sys.stderr)
            rename_records.append({
                "type": "rename",
                "from": str(old_path),
                "to": str(new_path),
                "status": "failed",
                "error": str(e),
            })

    dup_berhasil, dup_gagal, dup_records = handle_duplicates(
        duplikat_items, folder, args.duplicate_action, args.duplicate_folder, dry_run=False, max_len=max_len
    )

    print("\n--- Ringkasan ---")
    print(f"Total file diperiksa      : {len(files)}")
    print(f"Total di-rename           : {total_renamed}")
    print(f"Total dilewati (ekstensi) : {total_skip_has_ext}")
    if args.duplicate_action == "skip":
        print(f"Total dilewati (duplikat) : {len(duplikat_items)}")
    else:
        print(f"Total duplikat diproses   : {dup_berhasil}")
        if dup_gagal:
            print(f"Total duplikat gagal      : {dup_gagal}")

    all_actions = rename_records + dup_records
    if all_actions:
        summary = {
            "total_scanned": len(files),
            "total_renamed": total_renamed,
            "total_skipped_has_ext": total_skip_has_ext,
            "total_duplicate_processed": dup_berhasil,
            "total_duplicate_failed": dup_gagal,
        }
        log_path = write_log(folder, args, all_actions, summary)
        print(f"\nManifest/log disimpan di: {log_path}")


if __name__ == "__main__":
    main()
