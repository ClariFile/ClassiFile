"""Read-only inventory of a folder -> CSV in data/.

Usage: python -m tools.inventory <folder> [--out data/inventory.csv] [--families] [--known <folder>...]

Files are opened read-only and parsed from memory; nothing is written into the scanned folder.
The output file is created exclusively and is never overwritten.
--families pre-fills family_id: files that look like the same material share one (see prefill_families), and
files in subfolders get the folder name as a suggested primary_label. --known names folders of files that are
already development data: a scanned file that looks like a version of one is marked in the notes column.
All of it is a suggestion for the owner to review.
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf

from classifile.evaluation import file_stem as _name_key   # one definition, shared with the evaluation
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
            row["_first_page"] = digest  # for grouping only; never written to the CSV
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


def prefill_families(rows, known=()):
    """Give every row a family_id. Files share a family when they have the same bytes, the same first-page text
    (PDF), or the same name apart from the extension and copy marks: the same material in another format or
    version. A family that includes a known (development) file is named DEV-n and noted. Only what scan() already
    collected is used. Rows that have a subfolder get its name as a suggested primary_label."""
    everything = list(rows) + list(known)
    parent = list(range(len(everything)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, r in enumerate(everything):
        for key in (("bytes", r["sha256"]), ("page", r.get("_first_page")), ("name", _name_key(r["file_name"]))):
            if key[1]:
                parent[find(i)] = find(seen.setdefault(key, i))
    families, n_new, n_dev = {}, 0, 0
    for i, r in enumerate(everything):
        families.setdefault(find(i), []).append(r)
    for members in families.values():
        dev = [r["file_name"] for r in members if any(r is k for k in known)]
        mine = [r for r in members if not any(r is k for k in known)]
        if not mine:
            continue
        if dev:
            n_dev += 1
            fid = f"DEV-{n_dev}"
        else:
            n_new += 1
            fid = f"F{n_new:03d}"
        for r in mine:
            r["family_id"] = fid
            if dev:
                r["notes"] = f"looks like a version of a development file ({', '.join(sorted(dev))}): joins development"
            elif len(mine) > 1:
                r["notes"] = f"{len(mine)} files look like the same material"
            folder = Path(r["relative_path"]).parent.as_posix()
            if folder != ".":
                r["primary_label"] = folder
    return rows


def write_csv(rows, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "x", newline="", encoding="utf-8-sig") as f:  # "x": never overwrite
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--families", action="store_true", help="pre-fill family_id (and labels from subfolders)")
    ap.add_argument("--known", nargs="*", default=[], type=Path, help="folders of files already in development")
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
    if a.families or a.known:
        known = []
        for k in a.known:
            refuse_final_eval(k)
            known += scan(k)
        prefill_families(rows, known)
    write_csv(rows, out)
    print(f"{len(rows)} files -> {out}")


if __name__ == "__main__":
    main()
