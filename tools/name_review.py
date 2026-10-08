"""Name review: the top three suggested names of each development file, judged one file at a time.

Usage:
  python -m tools.name_review make <folder>... [--out data/name_review.csv]
  python -m tools.label_window --names [data/name_review.csv]
  python -m tools.name_review check [data/name_review.csv] [--save data/acceptable_names.csv]

make: reads temporary copies as the app does (OCR on) and writes one row per suggested name (rank 1 to 3) with its
plain reason and the first page where it appears. Names only; never other document text.
check: how many files get at least one good name in their top three, good names by rank, and the acceptable names
per file (the good ones plus any better name typed in the window). Counts on development data only.
--save writes the acceptable names (file, name, kind good|better) to a new file; it never overwrites. They contain
file names, so they stay in data/ (not tracked).
"""
import argparse
import csv
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from classifile.analysis.candidates import analyze, name_key, top_names
from classifile.app.reasons import first_page, reason_text
from classifile.reader import READERS, read_document
from tools import refuse_final_eval
from tools.page_labels import read_answers, read_rows

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "name_review.csv"
COLUMNS = ["file", "unit", "kind", "name", "reason", "page", "source"]
TOP = 3
FILE_ANSWER = "file"     # answers unit for the whole file: "skip"
BETTER = "better"        # answers unit for a better name typed by the user


def _page_of(name, suggestion, record):
    page = first_page([{"source": e.source, "pages": e.pages} for e in suggestion.evidence])
    if page is None:  # file name or key phrase: the first page whose text mentions it
        key = name_key(name)
        page = next((u.index for u in record.units
                     if key in name_key(" ".join(t for t in (u.text, u.ocr_text) if t))), None)
    return page or ""


def suggest(*folders):
    rows = []
    files = [(f, p) for f in folders for p in sorted(Path(f).rglob("*")) if p.suffix.lower() in READERS]
    with tempfile.TemporaryDirectory() as tmp:
        for i, (folder, src) in enumerate(files):
            copy = Path(tmp) / f"{i:04d}{src.suffix.lower()}"
            shutil.copyfile(src, copy)
            result = read_document(copy)
            # Analysed under the original file name, so file-name evidence is the user's, not the copy's.
            analysis = analyze(result.record, src.name) if result.status == "ok" else None
            rel = (Path(folder).name / src.relative_to(folder)).as_posix() if len(folders) > 1 else src.relative_to(folder).as_posix()
            top = top_names(analysis.suggestions, TOP) if analysis else []
            if not top:
                rows.append({"file": rel, "unit": 0, "kind": "no suggestion", "name": "", "reason": "", "page": "",
                             "source": str(src)})
            for rank, s in enumerate(top, 1):
                evidence = [{"source": e.source, "pages": e.pages} for e in s.evidence]
                rows.append({"file": rel, "unit": rank, "kind": "name", "name": s.name,
                             "reason": reason_text(evidence, analysis.unit), "page": _page_of(s.name, s, result.record),
                             "source": str(src)})
    return rows


def check(rows, answers):
    by_file = defaultdict(list)
    for r in rows:
        if r["kind"] == "name":
            by_file[r["file"]].append(r)
    reviewed = [f for f, rs in by_file.items() if any(answers.get((f, r["unit"])) in ("good", "bad") for r in rs)]
    acceptable = {}
    for f in reviewed:
        names = [r["name"] for r in by_file[f] if answers.get((f, r["unit"])) == "good"]
        better = (answers.get((f, BETTER)) or "").strip()
        acceptable[f] = names + ([better] if better and better not in names else [])
    good = {f: [r for r in by_file[f] if answers.get((f, r["unit"])) == "good"] for f in reviewed}
    return {
        "files": len({r["file"] for r in rows}),
        "files_without_suggestions": sum(1 for r in rows if r["kind"] == "no suggestion"),
        "files_reviewed": len(reviewed),
        "files_skipped": sum(1 for f in by_file if answers.get((f, FILE_ANSWER)) == "skip" and f not in reviewed),
        "files_with_a_good_name_in_top3": sum(1 for f in reviewed if good[f]),
        "good_by_rank": {rank: sum(1 for f in reviewed for r in good[f] if r["unit"] == str(rank))
                         for rank in range(1, TOP + 1)},
        "better_names_typed": sum(1 for f in reviewed if (answers.get((f, BETTER)) or "").strip()),
    }, acceptable


def save_acceptable(path, acceptable, answers):
    with open(path, "x", newline="", encoding="utf-8-sig") as f:  # "x": never overwrite
        w = csv.writer(f)
        w.writerow(["file", "name", "kind"])
        for file, names in sorted(acceptable.items()):
            better = (answers.get((file, BETTER)) or "").strip()
            for name in names:
                w.writerow([file, name, "better" if name == better else "good"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("folders", nargs="+")
    mk.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ck = sub.add_parser("check")
    ck.add_argument("labels", type=Path, nargs="?", default=DEFAULT_OUT)
    ck.add_argument("--save", type=Path, help="write the acceptable names to this new CSV")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        folders = [Path(f).resolve() for f in a.folders]
        for folder in folders:
            if not folder.is_dir():
                sys.exit(f"Not a folder: {folder}")
            refuse_final_eval(folder)
        if a.out.exists():
            sys.exit(f"Refusing to overwrite existing file: {a.out}. Choose another --out.")
        rows = suggest(*folders)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "x", newline="", encoding="utf-8-sig") as f:  # "x": never overwrite
            w = csv.DictWriter(f, COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(f"{sum(r['kind'] == 'name' for r in rows)} names for {len({r['file'] for r in rows})} files -> {a.out}")
        print("Review them with: python -m tools.label_window --names")
    else:
        refuse_final_eval(a.labels)
        result, acceptable = check(read_rows(a.labels), read_answers(a.labels))
        for k, v in result.items():
            print(f"{k}: {v}")
        print(f"files with acceptable names: {sum(1 for v in acceptable.values() if v)}")
        if a.save:
            save_acceptable(a.save, acceptable, read_answers(a.labels))
            print(f"acceptable names -> {a.save}")
        print("Counts on development data; they describe these files, not accuracy in general.")


if __name__ == "__main__":
    main()
