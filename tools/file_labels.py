"""File waiting development documents in the categories the owner's labels name.

Usage: python -m tools.file_labels data\\splits.csv

Reads a splits CSV (tools.split) and uses only its development rows: validation and final-evaluation rows are
never looked at, and nothing is imported. A development row counts when its file (matched by SHA-256) is already
in the app's catalog and still waiting for a decision. It is filed the normal way (a verified copy, the placement
recorded as user-confirmed: the label is the owner's) in the category named by primary_label, which is created
when the catalog has none of that name. Documents that are already filed stay where the owner put them.
Prints counts only. Close the app first; set CLASSIFILE_DATA_DIR to use another catalog.
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from classifile.analysis.candidates import name_key
from classifile.catalog.db import Catalog
from classifile.copies.engine import CopyError
from classifile.organizer import Organizer


def file_labels(org, rows):
    """rows: dicts with sha256, primary_label and split. Returns a Counter of outcomes."""
    done = Counter()
    for r in rows:
        if r["split"] != "development":
            continue
        snap = org.catalog.snapshot_by_hash(r["sha256"])
        label = " ".join(r["primary_label"].split())
        if snap is None or not label:
            done["not in the catalog" if snap is None else "no label"] += 1
            continue
        doc = org.catalog.document(snap["document_id"])
        if doc["status"] != "needs_decision":
            done["already filed (left as it is)" if doc["status"] == "filed" else "could not be read"] += 1
            continue
        cat = org.catalog.category_by_key(name_key(label))
        if cat is None:
            done["categories created"] += 1
        try:
            org.file(doc["id"], cat["id"] if cat else org.create_category(label))
            done["filed"] += 1
        except (CopyError, ValueError):
            done["could not be filed (still waiting, with the reason on its card)"] += 1
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("splits", type=Path)
    a = ap.parse_args(argv)
    with open(a.splits, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    from classifile.app.main import catalog_lock
    from classifile.catalog.db import default_data_dir

    path = default_data_dir() / "catalog.sqlite3"
    lock = catalog_lock(path)                   # the app's own lock: never alongside an open ClassiFile
    if lock is None:
        print("ClassiFile is open. Close it, then run this again.")
        return 1
    catalog = Catalog(path)
    try:
        done = file_labels(Organizer(catalog), rows)
    finally:
        catalog.close()
        lock.unlock()
    for outcome, n in sorted(done.items()):
        print(f"{n:4}  {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
