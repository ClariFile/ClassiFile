"""Read-only inventory of a folder -> CSV in data/.

Usage: python -m tools.inventory <folder> [--out data/inventory.csv]

Files are opened read-only and parsed from memory; nothing is written into the scanned folder.
The output file is created exclusively and is never overwritten.
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

from tools import refuse_final_eval

COLUMNS = [
    "relative_path", "file_name", "extension", "size", "sha256", "pages",
    "exact_dup_group", "near_dup_hint", "primary_label", "family_id", "notes",
]
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "inventory.csv"


def _pdf_facts(data):
    """(page count, first-page text digest) or ("", "") if unreadable. Text never leaves this function."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            first = " ".join(doc[0].get_text().split()).lower() if doc.page_count else ""
            digest = hashlib.sha256(first.encode()).hexdigest() if first else ""
            return doc.page_count, digest
    except Exception:
        return "", ""


def scan(folder):
    folder = Path(folder).resolve()
    rows, first_page = [], {}
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath, name)
            with open(path, "rb") as f:
                data = f.read()
            ext = path.suffix.lower()
            pages, digest = _pdf_facts(data) if ext == ".pdf" else ("", "")
            row = dict.fromkeys(COLUMNS, "")
            row.update(
                relative_path=path.relative_to(folder).as_posix(), file_name=name, extension=ext,
                size=len(data), sha256=hashlib.sha256(data).hexdigest(), pages=pages,
            )
            rows.append(row)
            first_page[row["relative_path"]] = digest

    _group(rows, lambda r: r["sha256"], "exact_dup_group", "D")
    # Near-duplicate hint: same first-page text but different bytes. A suggestion only.
    _group(rows, lambda r: first_page[r["relative_path"]], "near_dup_hint", "N",
           distinct=lambda members: len({r["sha256"] for r in members}) > 1)
    return rows


def _group(rows, key, column, prefix, distinct=lambda members: True):
    groups = defaultdict(list)
    for r in rows:
        if key(r):
            groups[key(r)].append(r)
    n = 0
    for members in groups.values():
        if len(members) > 1 and distinct(members):
            n += 1
            for r in members:
                r[column] = f"{prefix}{n}"


def write_csv(rows, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", newline="", encoding="utf-8-sig") as f:  # "x": never overwrite
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    folder, out = Path(a.folder).resolve(), a.out.resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    refuse_final_eval(folder)
    if out.is_relative_to(folder):
        sys.exit("Refusing: the output would be written inside the scanned folder.")
    if out.exists():
        sys.exit(f"Refusing to overwrite existing file: {out}. Choose another --out.")
    rows = scan(folder)
    write_csv(rows, out)
    print(f"{len(rows)} files -> {out}")


if __name__ == "__main__":
    main()
