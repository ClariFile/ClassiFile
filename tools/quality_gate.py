"""Part E's quality-gate report for CP5, as one command (decision record Part E; docs/LAUNCH.md section 0).

Usage: python -m tools.quality_gate [--out FILE] [--catalog FILE]

Puts together, from a temporary copy of the app's catalog (nothing in the app or its catalog changes):
  - the one evaluation (tools.evaluate with --outcomes and --real-use): the user's category first and in the first
    three, automatic filing at every level, true and false positives with their likely causes, new subjects
    wrongly filed, and what became of the app's own placements;
  - the replay of automatic new folders (tools.group_eval --folders), each category held out in turn, with the
    owner's family ids from the catalog;
  - a summary of every Part E item at the level in use: incorrect assignments, incorrect creations, duplicate
    categories, over-merging and fragmentation, pending rate, and the four effort numbers (B2).
Deterministic: the same catalog and code give the same report. --out also saves it (created new, never
overwritten). The output names categories and words from documents: keep it out of tracked files. Counts describe
the user's development documents; they are not accuracy estimates. data/validation and data/final-eval are never
read.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from classifile import evaluation, matching
from classifile.catalog.db import Catalog, default_data_dir
from classifile.organizer import Organizer
from tools import evaluate, group_eval
from tools.match_eval import families, load


def questions(m):
    """(pending documents, distinct questions) at the level in use, as the app would ask them: each waiting
    document is a question, except that waiting documents no category matches well are asked together when they
    group at matching.GROUP_LEVEL (B2), one question per group."""
    waiting = [r for r in m["rows"] if not evaluation.filed(r, m["level"])]
    unmatched = [r["doc"] for r in waiting if matching.lead(r["ranked"]) < matching.GOOD_MATCH and m["counts"].get(r["doc"])]
    idf = matching.fit_idf([m["counts"][d] for d in sorted(m["labels"]) if m["counts"].get(d)])
    groups = matching.similar_groups({d: matching.vector(m["counts"][d], idf) for d in unmatched}, matching.GROUP_LEVEL)
    return len(waiting), len(waiting) - sum(map(len, groups)) + len(groups)


def summary(m, replay, out=print):
    """The Part E items at the level in use, each with where it comes from."""
    level, rows, unseen = m["level"], m["rows"], m["unseen"]
    s, u = evaluation.summary(rows, level), evaluation.summary(unseen, level)
    folders = [f for r in replay for f in r["folders"]]
    mixed = sum(f["kind"] == "mixed" for f in folders)
    known = sum(f["kind"] == "known subject" for f in folders)
    split = sum(len([f for f in r["folders"] if f["own"]]) > 1 for r in replay)
    left = sum(r["unmatched"] - sum(len(f["own"]) for f in r["folders"] if f["own"]) for r in replay
               if any(f["own"] for f in r["folders"]))
    pending, asked = questions(m)
    moved = sum(x["result"].startswith("moved") for x in m["real"])
    out(f"\nPart E summary at the level in use ({m['level_name']}, lead >= {level}); {s['documents']} documents")
    out(f"  incorrect assignments (filed by itself, wrong):      {evaluate.pct(s['wrong'], s['right'] + s['wrong'])}")
    out(f"  new subjects forced into an existing folder:         {evaluate.pct(u['right'] + u['wrong'], len(unseen))}")
    out(f"  incorrect creations (replay: folders mixing subjects): {mixed} of {len(folders)} folders created")
    out(f"  duplicate categories (replay: a second folder for a subject the app has): {known}")
    out(f"  over-merging (replay: folders mixing subjects):      {mixed}")
    out(f"  fragmentation (replay: held-out subjects split over several folders): {split} of {len(replay)}; "
        f"their documents left waiting beside a folder: {left}")
    out(f"  pending rate (waiting for the user):                 {evaluate.pct(pending, s['documents'])}")
    out(f"  effort: {pending} pending documents; {asked} distinct questions; "
        f"{pending / asked if asked else 0:.2f} documents resolved per decision; later corrections (the app's own "
        f"placements the user moved, real use): {moved} of {len(m['real'])}")
    out("  Later corrections reveal discovered errors only, not every error (B2). Counts on development data, not "
        "accuracy estimates.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="also save the report here (never overwritten)")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    a = ap.parse_args(argv)
    if a.out and a.out.exists():
        sys.exit(f"Refusing to overwrite existing file: {a.out}")
    if not a.catalog.exists():
        sys.exit(f"No catalog at {a.catalog}")
    with tempfile.TemporaryDirectory(prefix="classifile-gate-") as tmp:
        copy = Path(tmp) / "catalog.sqlite3"
        shutil.copyfile(a.catalog, copy)
        cat = Catalog(copy)
        try:
            m = evaluate.measure(Organizer(cat))
            known = cat.family_labels()
        finally:
            cat.close()
        docs = load(copy)
    replay = group_eval.replay(docs, families(docs, known))
    lines = []
    evaluate.report(m, out=lines.append, outcomes=True, real=True)
    lines.append("")
    group_eval.report_replay(docs, replay, matching.FOLDER_LEVEL, lines.append)
    summary(m, replay, lines.append)
    print("\n".join(lines))
    if a.out:
        with open(a.out, "x", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
