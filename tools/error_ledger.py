"""The private error ledger (designImp2, "Better categorization"): one row per document the user filed, as the one
evaluation sees it, with a first reason code for each mistake, to choose the one experiment worth trying next.

Usage: python -m tools.error_ledger [--catalog FILE] [--out data\\error_ledger.csv] [--names data\\error_ledger_names.csv]

Reads a temporary copy of the app's catalog (removed afterwards); nothing in the app or its catalog changes. Each
family is held out in turn, exactly as tools.evaluate and the app's update check do (classifile.evaluation).
Documents get neutral ids (D1, D2...); families too (F1...). --names writes the map from those ids to file names in a
separate file, for the owner to look a document up. Both files are created new, never overwritten, and hold category
names: keep them in data\\ (not tracked), never in tracked files or messages.

Columns: id, category, outcome at the level in use (right / wrong / missed / wait, evaluation.outcome), rank of
the user's category, first three, lead (best over second; a similarity, never a probability), examples of the
user's category in the fold, family, family size, unread units (pictures nothing read), model version, reason.
The reason is a first guess from plain rules, chosen before looking at the documents, for the owner to correct:
  incomplete extraction   the document has units nothing has read (Catalog.unread_units)
  unfamiliar subject      its category had fewer than matching.AUTO_MIN_CONFIRMED other examples in the fold
  shared family           its family has documents in another category (inferred by name or text)
  to review               none of these: mixed subject, template vocabulary, ambiguous scope or poor name are
                          for the owner to judge
Right placements and correct waits get no reason. Counts describe the user's own documents; they are not accuracy
estimates. data\\validation and data\\final-eval are never read.
"""
import argparse
import csv
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from classifile import evaluation, matching
from classifile.catalog.db import Catalog, default_data_dir
from classifile.organizer import Organizer


def ledger(org):
    """[row dicts] for the catalog the organizer reads, and {neutral id: file name}."""
    counts, labels, groups = org.evaluation_inputs()
    names = {c["id"]: c["name"] for c in org.catalog.all("SELECT id, name FROM categories")}
    files = {r["document_id"]: r["file_name"] for r in org.catalog.all("SELECT document_id, file_name FROM snapshots")}
    rows = evaluation.evaluate(counts, labels, groups)
    level, unread = org.check_level(), org.catalog.unread_units()
    active = org.catalog.active_matcher()
    family_ids, family_size = {}, Counter(groups[d] for d in labels)
    family_cats = {}
    for d in labels:
        family_cats.setdefault(groups[d], set()).add(labels[d])
    out, ids = [], {}
    for n, r in enumerate(sorted(rows, key=lambda r: (names.get(r["category"], ""), files.get(r["doc"], ""))), 1):
        d = r["doc"]
        ids[f"D{n}"] = files.get(d, "")
        fam = family_ids.setdefault(groups[d], f"F{len(family_ids) + 1}")
        what = evaluation.outcome(r, level)
        ranked = [c for c, _ in r["ranked"]]
        reason = "" if what in ("right", "wait") else (
            "incomplete extraction" if d in unread else
            "unfamiliar subject" if r["examples"] < matching.AUTO_MIN_CONFIRMED else
            "shared family" if len(family_cats[groups[d]]) > 1 else "to review")
        out.append({"id": f"D{n}", "category": names.get(r["category"], "?"), "outcome": what,
                    "rank": ranked.index(r["category"]) + 1 if r["category"] in ranked else "",
                    "first_three": " | ".join(names.get(c, "?") for c in ranked[:3]),
                    "lead": f"{matching.lead(r['ranked']):.3f}" if r["ranked"] else "",
                    "examples": r["examples"], "family": fam, "family_size": family_size[groups[d]],
                    "unread_units": len(unread.get(d, ())), "model_version": active["version"] if active else "",
                    "reason": reason})
    return out, ids


def write_new(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", newline="", encoding="utf-8") as f:      # "x": never over an existing file
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    ap.add_argument("--out", type=Path, default=Path("data") / "error_ledger.csv")
    ap.add_argument("--names", type=Path, help="also write the neutral ids' file names here (local only)")
    a = ap.parse_args(argv)
    for p in filter(None, (a.out, a.names)):
        if p.exists():
            sys.exit(f"Refusing to overwrite existing file: {p}")
    if not a.catalog.exists():
        sys.exit(f"No catalog at {a.catalog}")
    with tempfile.TemporaryDirectory(prefix="classifile-ledger-") as tmp:
        shutil.copyfile(a.catalog, Path(tmp) / "catalog.sqlite3")
        cat = Catalog(Path(tmp) / "catalog.sqlite3")
        try:
            rows, ids = ledger(Organizer(cat))
        finally:
            cat.close()
    write_new(a.out, rows, list(rows[0]) if rows else ["id"])
    if a.names:
        write_new(a.names, [{"id": k, "file_name": v} for k, v in ids.items()], ["id", "file_name"])
    tally = Counter(r["outcome"] for r in rows)
    reasons = Counter(r["reason"] for r in rows if r["reason"])
    print(f"{len(rows)} documents: " + ", ".join(f"{tally[k]} {k}" for k in ("right", "wrong", "missed", "wait")))
    print("Reasons (first guesses): " + (", ".join(f"{n} {k}" for k, n in reasons.most_common()) or "none"))
    print(f"Written: {a.out}" + (f" and {a.names}" if a.names else "") + " (category names: keep them local)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
