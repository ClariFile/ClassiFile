"""Move the files of a split into their folders: development, validation and final evaluation.

Usage: python -m tools.apply_split data/splits.csv --from <folder>
           [--dev data/development] [--val data/validation] [--final data/final-eval]
       python -m tools.apply_split data/splits_2.csv --previous data/splits.csv     (a split made again)
       python -m tools.apply_split --recover     (after a run that stopped: every file back where it was)

Nothing moves unless every file still has the SHA-256 the split recorded and no destination name is taken.
Files are renamed into place, never copied over anything. After this, data/final-eval is not opened again until
the final evaluation (the other tools refuse it); validation stays apart from development.
With --previous, each file is taken from the folder the earlier split put it in, and a file that keeps its
split is not touched or read at all.
All or nothing: the moves are written to a journal (data/apply_split.journal.json) before the first one. A move
that fails puts every file moved so far back, and the journal goes. If the run itself stops (power, a crash), the
journal stays: every later run refuses until --recover has put the files back. Putting back never overwrites
anything; a file that cannot go back is named, and the journal is kept.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FOLDERS = {"development": DATA / "development", "validation": DATA / "validation",
           "final_evaluation": DATA / "final-eval"}
JOURNAL = DATA / "apply_split.journal.json"


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


def put_back(moves):
    """Undo moves, last first: each file goes back only while its old place is free. Returns what could not."""
    stuck = []
    for src, dest in reversed(moves):
        src, dest = Path(src), Path(dest)
        if dest.is_file() and not src.exists():
            try:
                os.rename(dest, src)
            except OSError:
                stuck.append(dest)
        elif dest.exists():
            stuck.append(dest)      # its old place is taken: left where it is, never overwritten
    return stuck


def recover(journal=None):
    """After a run that stopped: every file its journal names goes back. Returns what could not."""
    journal = journal or JOURNAL
    if not Path(journal).exists():
        return []
    stuck = put_back(json.loads(Path(journal).read_text(encoding="utf-8")))
    if not stuck:
        Path(journal).unlink()
    return stuck


def apply(rows, source, folders, previous=None, journal=None, _fail_at=None):
    journal = journal or JOURNAL
    if Path(journal).exists():
        raise ValueError("an earlier run stopped part-way; run tools.apply_split --recover first")
    moves = plan(rows, source, folders, previous)  # everything is checked before anything moves
    Path(journal).parent.mkdir(parents=True, exist_ok=True)
    Path(journal).write_text(json.dumps([[str(s), str(d)] for s, d in moves]), encoding="utf-8")
    done = []
    try:
        for n, (src, dest) in enumerate(moves):
            if n == _fail_at:
                raise PermissionError("test hook")
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dest)  # on Windows a rename never replaces an existing file
            done.append((src, dest))
    except OSError as e:
        stuck = put_back(done)
        if stuck:                   # the journal stays, so --recover can finish later
            raise ValueError(f"moving {src} failed ({type(e).__name__}), and these could not go back yet: "
                             + ", ".join(map(str, stuck)) + "; run tools.apply_split --recover") from None
        Path(journal).unlink()
        raise ValueError(f"moving {src} failed ({type(e).__name__}); every file was put back") from None
    Path(journal).unlink()
    return Counter(r["split"] for r in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("splits", type=Path, nargs="?")
    ap.add_argument("--from", dest="source", type=Path)
    ap.add_argument("--recover", action="store_true", help="put back the files of a run that stopped part-way")
    ap.add_argument("--previous", type=Path, help="the splits CSV applied before: files move between its folders")
    ap.add_argument("--dev", type=Path, default=FOLDERS["development"])
    ap.add_argument("--val", type=Path, default=FOLDERS["validation"])
    ap.add_argument("--final", type=Path, default=FOLDERS["final_evaluation"])
    a = ap.parse_args(argv)
    if a.recover:
        stuck = recover()
        sys.exit(("Could not put back: " + ", ".join(map(str, stuck))) if stuck else print("Every file is back.")
                 or 0)
    if a.splits is None or bool(a.source) == bool(a.previous):
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
