"""OCR quality pass: a fixed random sample of OCR'd units for the user to judge good / partly / bad.

Usage:
  python -m tools.ocr_quality make [sheet.csv] [--n 40] [--seed 2026] [--out data/ocr_quality.csv]
  python -m tools.label_window --quality [data/ocr_quality.csv]
  python -m tools.ocr_quality check [data/ocr_quality.csv]

make: samples units where OCR ran (status done or no_text) from a page_labels sheet. Numbers only.
The window shows each unit's pictures and the text OCR read, with the lines the junk filter drops greyed out.
Answers: G good, P partly, B bad (how well OCR read the picture's text), and optionally D: the greyed (dropped)
lines contained real text. check counts them. Counts on development data only; not accuracy estimates.
"""
import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

from tools import refuse_final_eval
from tools.page_labels import read_answers, read_rows

DATA = Path(__file__).resolve().parent.parent / "data"
DEFAULT_SHEET = DATA / "page_labels_e8filter.csv"
DEFAULT_OUT = DATA / "ocr_quality.csv"
COLUMNS = ["file", "unit", "kind", "ocr_status", "ocr_chars", "ocr_discarded_chars", "source"]
DROPPED = "dropped"   # answers kind for the D key


def sample(rows, n, seed):
    pool = [r for r in rows if r.get("ocr_status") in ("done", "no_text")]
    picked = random.Random(seed).sample(pool, min(n, len(pool)))
    order = {id(r): i for i, r in enumerate(rows)}
    return sorted(picked, key=lambda r: order[id(r)])  # sheet order: each document is read once in the window


def check(rows, answers, dropped):
    fmt = lambda r: r["file"].rsplit(".", 1)[-1].lower()
    judged = [r for r in rows if answers.get((r["file"], r["unit"])) in ("good", "partly", "bad")]
    out = {"sampled": len(rows), "judged": len(judged)}
    out.update({k: v for k, v in Counter(answers[(r["file"], r["unit"])] for r in judged).items()})
    for f in sorted({fmt(r) for r in judged}):
        c = Counter(answers[(r["file"], r["unit"])] for r in judged if fmt(r) == f)
        out[f"by_format_{f}"] = dict(c)
    filtered = [r for r in judged if int(r["ocr_discarded_chars"] or 0) > 0]
    out["judged_with_dropped_lines"] = len(filtered)
    out["dropped_lines_had_real_text"] = sum(1 for r in filtered if dropped.get((r["file"], r["unit"])) == "yes")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("sheet", type=Path, nargs="?", default=DEFAULT_SHEET)
    mk.add_argument("--n", type=int, default=40)
    mk.add_argument("--seed", type=int, default=2026)
    mk.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ck = sub.add_parser("check")
    ck.add_argument("labels", type=Path, nargs="?", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    if a.cmd == "make":
        refuse_final_eval(a.sheet)
        rows = read_rows(a.sheet)
        for r in rows:
            if r.get("source"):
                refuse_final_eval(r["source"])
        if a.out.exists():
            sys.exit(f"Refusing to overwrite existing file: {a.out}. Choose another --out.")
        picked = sample(rows, a.n, a.seed)
        with open(a.out, "x", newline="", encoding="utf-8-sig") as f:  # "x": never overwrite
            w = csv.DictWriter(f, COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(picked)
        print(f"{len(picked)} OCR'd units sampled (seed {a.seed}) -> {a.out}")
        print("Judge them with: python -m tools.label_window --quality")
    else:
        refuse_final_eval(a.labels)
        result = check(read_rows(a.labels), read_answers(a.labels), read_answers(a.labels, kind=DROPPED))
        for k, v in result.items():
            print(f"{k}: {v}")
        print("Counts on development data; they describe these files, not accuracy in general.")


if __name__ == "__main__":
    main()
