"""Move the files of a split into their folders: development, validation and final evaluation.

Usage: python -m tools.apply_split data/splits.csv --from <folder>
           [--dev data/development] [--val data/validation] [--final data/final-eval]

Nothing moves unless every file still has the SHA-256 the split recorded and no destination name is taken.
Files are renamed into place, never copied over anything. After this, data/final-eval is not opened again until
the final evaluation (the other tools refuse it); validation stays apart from development.
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


def plan(rows, source, folders):
    """[(from, to)] for every row, or raise ValueError naming what stops the move."""
    moves = []
    for r in rows:
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


def apply(rows, source, folders):
    moves = plan(rows, source, folders)  # everything is checked before anything moves
    for src, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dest)  # on Windows a rename never replaces an existing file
    return Counter(r["split"] for r in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("splits", type=Path)
    ap.add_argument("--from", dest="source", type=Path, required=True)
    ap.add_argument("--dev", type=Path, default=FOLDERS["development"])
    ap.add_argument("--val", type=Path, default=FOLDERS["validation"])
    ap.add_argument("--final", type=Path, default=FOLDERS["final_evaluation"])
    a = ap.parse_args(argv)
    with open(a.splits, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    try:
        counts = apply(rows, a.source, {"development": a.dev, "validation": a.val, "final_evaluation": a.final})
    except ValueError as e:
        sys.exit(f"Refusing: {e}. Nothing was moved.")
    print("moved: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
