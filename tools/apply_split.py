"""Move the files of a split into their folders: development, validation and final evaluation.

Usage: python -m tools.apply_split data/splits.csv --from <folder>
           [--dev data/development] [--val data/validation] [--final data/final-eval]
       python -m tools.apply_split data/splits_2.csv --previous data/splits.csv     (a split made again)

Nothing moves unless every file still has the SHA-256 the split recorded and no destination name is taken.
Files are renamed into place, never copied over anything. After this, data/final-eval is not opened again until
the final evaluation (the other tools refuse it); validation stays apart from development.
With --previous, each file is taken from the folder the earlier split put it in, and a file that keeps its
split is not touched or read at all.
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FOLDERS = {"development": DATA / "development", "validation": DATA / "validation",
           "final_evaluation": DATA / "final-eval"}


def plan(rows, source, folders, previous=None):
    """[(from, to)] for every row, or raise ValueError naming what stops the move.
    previous: {relative_path: split} of the split applied before; rows that keep their split are left out."""
    moves = []
    for r in rows:
        if previous is not None:
            if r["relative_path"] not in previous:
                raise ValueError(f"not in the previous split: {r['relative_path']}")
            if previous[r["relative_path"]] == r["split"]:
                continue
            source = folders[previous[r["relative_path"]]]
        src = Path(source) / r["relative_path"]
        dest = Path(folders[r["split"]]) / r["relative_path"]
        if not src.is_file():
            raise ValueError(f"not found: {src}")
        if hashlib.sha256(src.read_bytes()).hexdigest() != r["sha256"]:
            raise ValueError(f"changed since the split was made: {src}")
        if dest.exists():
            raise ValueError(f"a file of that name is already at {dest}")
        moves.append((src, dest))
    if len({os.path.normcase(str(d)) for _, d in moves}) != len(moves):
        raise ValueError("two files would get the same destination")
    return moves


def apply(rows, source, folders, previous=None):
    moves = plan(rows, source, folders, previous)  # everything is checked before anything moves
    for src, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dest)  # on Windows a rename never replaces an existing file
    return Counter(r["split"] for r in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("splits", type=Path)
    ap.add_argument("--from", dest="source", type=Path)
    ap.add_argument("--previous", type=Path, help="the splits CSV applied before: files move between its folders")
    ap.add_argument("--dev", type=Path, default=FOLDERS["development"])
    ap.add_argument("--val", type=Path, default=FOLDERS["validation"])
    ap.add_argument("--final", type=Path, default=FOLDERS["final_evaluation"])
    a = ap.parse_args(argv)
    if bool(a.source) == bool(a.previous):
        sys.exit("Give --from <folder> for a first split, or --previous <splits.csv> for a split made again.")
    with open(a.splits, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    previous = None
    if a.previous:
        with open(a.previous, newline="", encoding="utf-8-sig") as f:
            previous = {r["relative_path"]: r["split"] for r in csv.DictReader(f)}
    try:
        counts = apply(rows, a.source, {"development": a.dev, "validation": a.val, "final_evaluation": a.final},
                       previous)
    except ValueError as e:
        sys.exit(f"Refusing: {e}. Nothing was moved.")
    changed = "" if previous is None else f" ({sum(previous[r['relative_path']] != r['split'] for r in rows)} changed folder)"
    print("now: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + changed)


if __name__ == "__main__":
    main()
