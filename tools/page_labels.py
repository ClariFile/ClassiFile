"""E8 page labels: per-page observations for the user to label, and the check of the suspected-unread rule.

Usage:
  python -m tools.page_labels make <folder>... [--out data/page_labels.csv]
  python -m tools.label_window [data/page_labels.csv]        (label units one at a time)
  python -m tools.page_labels check [data/page_labels.csv] [--answers other.answers.csv]

make: reads temporary copies with OCR on and writes one row per PDF page or slide, and per DOCX/ODT block that
holds a picture. Numbers only, never document text. Units with no non-repeated picture area are labelled "no"
automatically (label_source "auto"); the rest are for the user: does the unit carry meaningful content that
its native text misses (text or information inside pictures)?
The user's answers are appended to <name>.answers.csv (never rewritten; the latest answer per unit counts).
check: counts what the rule caught, missed and flagged needlessly, and the OCR time. Counts on development
data describe these files only; they are not accuracy estimates.
"""
import argparse
import csv
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from classifile.reader import READERS, read_document
from tools import refuse_final_eval

DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "page_labels.csv"
COLUMNS = ["file", "unit", "kind", "native_chars", "image_area", "nonrepeated_image_area", "suspected_unread",
           "suspect_rule", "ocr_status", "ocr_chars", "ocr_discarded_chars", "file_read_seconds", "unread_content", "label_source", "notes",
           "source"]
ANSWER_COLUMNS = ["file", "unit", "answer", "at"]


def observe(*folders):
    rows = []
    files = [(f, p) for f in folders for p in sorted(Path(f).rglob("*")) if p.suffix.lower() in READERS]
    with tempfile.TemporaryDirectory() as tmp:
        for i, (folder, src) in enumerate(files):
            copy = Path(tmp) / f"{i:04d}{src.suffix.lower()}"
            shutil.copyfile(src, copy)
            t = time.perf_counter()
            r = read_document(copy)
            seconds = round(time.perf_counter() - t, 2)
            rel = (Path(folder).name / src.relative_to(folder)).as_posix() if len(folders) > 1 else src.relative_to(folder).as_posix()
            if r.record is None:
                rows.append({"file": rel, "unit": "", "kind": f"read {r.status}: {r.reason}", "file_read_seconds": seconds,
                             "source": str(src)})
                continue
            for u in r.record.units:
                if u.kind in ("page", "slide", "hidden slide") or u.image_area:
                    auto = u.nonrepeated_image_area == 0  # nothing pictured that a page does not repeat
                    rows.append({"file": rel, "unit": u.index, "kind": u.kind, "native_chars": u.native_chars,
                                 "image_area": u.image_area, "nonrepeated_image_area": u.nonrepeated_image_area,
                                 "suspected_unread": int(u.suspected_unread), "suspect_rule": u.suspect_rule or "",
                                 "ocr_status": u.ocr_status or "",
                                 "ocr_chars": len("".join((u.ocr_text or "").split())),
                                 "ocr_discarded_chars": u.ocr_discarded_chars if u.ocr_discarded_chars is not None else "",
                                 "file_read_seconds": seconds,
                                 "unread_content": "no" if auto else "", "label_source": "auto" if auto else "",
                                 "source": str(src)})
    return rows


def answers_path(labels, kind=""):
    """<sheet>.answers.csv, or <sheet>.<kind>.answers.csv for a second question about the same units."""
    return Path(labels).with_name(Path(labels).stem + (f".{kind}" if kind else "") + ".answers.csv")


def read_rows(labels):
    with open(labels, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_answers(labels, path=None, kind=""):
    """{(file, unit): latest answer}."""
    path, latest = Path(path) if path else answers_path(labels, kind), {}
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for a in csv.DictReader(f):
                latest[(a["file"], a["unit"])] = a["answer"]
    return latest


def append_answer(labels, file, unit, answer, kind=""):
    """Append one answer and flush it to disk, so labelling can stop at any moment."""
    path = answers_path(labels, kind)
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ANSWER_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({"file": file, "unit": unit, "answer": answer,
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        f.flush()


def merged(rows, answers):
    """Rows with the user's latest yes/no answers applied; auto labels are kept as they are."""
    out = []
    for r in rows:
        r = dict(r)
        a = answers.get((r["file"], r["unit"]))
        if r.get("label_source") != "auto" and a in ("yes", "no"):
            r["unread_content"], r["label_source"] = a, "user"
        out.append(r)
    return out


def check(rows):
    label = lambda r: r["unread_content"].strip().casefold()
    flagged = lambda r: r["suspected_unread"] == "1"
    auto = [r for r in rows if r.get("label_source") == "auto"]
    user = [r for r in rows if r.get("label_source") != "auto" and label(r) in ("yes", "no")]
    yes = [r for r in user if label(r) == "yes"]
    caught = [r for r in yes if flagged(r)]
    ocr_units = [r for r in rows if r["ocr_status"] in ("done", "no_text")]
    seconds = {r["file"]: float(r["file_read_seconds"] or 0) for r in rows if r["ocr_status"]}
    return {
        "units": len(rows),
        "auto_labelled_no": len(auto),
        "auto_labelled_but_flagged": sum(1 for r in auto if flagged(r)),
        "user_labelled": len(user),
        "unlabelled": len(rows) - len(auto) - len(user),
        "with_unread_content": len(yes),
        "caught_by_rule": len(caught),
        "missed_by_rule": len(yes) - len(caught),                      # E8: meaningful content missed
        "flagged_without_unread_content": sum(1 for r in user if flagged(r) and label(r) == "no"),
        "caught_and_ocr_found_text": sum(1 for r in caught if r["ocr_status"] == "done"),
        "ocr_units": len(ocr_units),
        "read_seconds_of_files_with_ocr": round(sum(seconds.values()), 1),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("folders", nargs="+")
    mk.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ck = sub.add_parser("check")
    ck.add_argument("labels", type=Path, nargs="?", default=DEFAULT_OUT)
    ck.add_argument("--answers", type=Path, help="answers from another sheet of the same files (e.g. after a rule change)")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        folders, out = [Path(f).resolve() for f in a.folders], a.out.resolve()
        for folder in folders:
            if not folder.is_dir():
                sys.exit(f"Not a folder: {folder}")
            refuse_final_eval(folder)
            if out.is_relative_to(folder):
                sys.exit("Refusing: the output would be written inside a scanned folder.")
        if out.exists():
            sys.exit(f"Refusing to overwrite existing file: {out}. Choose another --out.")
        rows = observe(*folders)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "x", newline="", encoding="utf-8-sig") as f:  # "x": never overwrite
            w = csv.DictWriter(f, COLUMNS)
            w.writeheader()
            w.writerows(rows)
        todo = sum(1 for r in rows if not r.get("label_source"))
        print(f"{len(rows)} units -> {out} ({len(rows) - todo} labelled 'no' automatically, {todo} to label).")
        print("Label them with: python -m tools.label_window")
    else:
        refuse_final_eval(a.labels)
        result = check(merged(read_rows(a.labels), read_answers(a.labels, a.answers)))
        for k, v in result.items():
            print(f"{k}: {v}")
        print("Counts on development data; they describe these files, not accuracy in general.")


if __name__ == "__main__":
    main()
