"""The one evaluation of matching, as a report (classifile.evaluation; the app's update check measures the same way).

Usage: python -m tools.evaluate [--rules] [--json FILE] [--catalog FILE]
       python -m tools.evaluate --set-families data\\splits_incoming_2.csv    (close the app first)

Reads a temporary copy of the app's catalog (removed afterwards); nothing in the app or its catalog changes. Each
family of the documents the user filed is held out in turn and a model is trained on the rest, its word weights
fitted inside the fold. There is no random step: the same catalog and code give the same report.
Prints: what was counted and what was left out, the model in use and the thresholds; the user's category first and
in the first three, overall and per category; automatic filing at every level (right / wrong / waiting); new
subjects (each category held out whole) wrongly filed; the "Check these" list. Each share has a simple 95% range.
--rules adds the safer filing rules tried against the one in use (a minimum similarity to the best folder; the
best folder among the document's nearest neighbours), at the level in use and at Balanced. Nothing is adopted here.
--json saves the rows and the summary (created new, never overwritten).
--set-families records the owner's family ids from inventory or splits CSVs in the catalog itself, for the files the
catalog holds (rows of the final evaluation are skipped unread), so that this report and the app's update check
hold out the same families. It changes nothing else.
The output names categories: keep it out of tracked files. Counts describe the user's development documents; they
are not accuracy estimates. data/validation and data/final-eval are never read.
"""
import argparse
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from classifile import evaluation, matching
from classifile.catalog.db import Catalog, default_data_dir
from classifile.organizer import Organizer
from tools.match_eval import csv_families

RULES = {   # the safer filing rules tried (item 3 of the owner's 2026-10-15 instruction); each adds to the one in use
    "in use (lead only)": None,
    **{f"a. best similarity >= {m:.2f}": (lambda m: lambda r: r["ranked"][0][1] >= m)(m)
       for m in (0.20, 0.25, 0.30, 0.35)},
    **{f"b. {j} of the {k} nearest in the best folder": (lambda k, j: lambda r: r["neighbours"][:k].count(
        r["ranked"][0][0]) >= j)(k, j) for k, j in ((1, 1), (3, 1), (3, 2), (5, 3))},
}


def pct(k, n):
    lo, hi = evaluation.wilson(k, n)
    return f"{k:3} of {n:3} ({100 * k / n if n else 0:3.0f}%, range {100 * lo:.0f}-{100 * hi:.0f}%)"


def measure(org):
    """Everything the report prints, as plain data."""
    counts, labels, groups = org.evaluation_inputs()
    cat = org.catalog
    names = {c["id"]: c["name"] for c in cat.all("SELECT id, name FROM categories")}
    live = {c["id"] for c in cat.categories()}
    rows = evaluation.evaluate(counts, labels, groups, live=live)
    unseen = evaluation.evaluate(counts, labels, {d: c for d, c in labels.items()}, live=live)
    used = org.matcher()
    status = Counter(r[0] for r in cat.all("SELECT status FROM documents"))
    machine = cat.one("SELECT COUNT(*) FROM memberships WHERE role = 'primary' AND status = 'active'"
                      " AND provenance = 'machine-assigned'")[0]
    return {"names": names, "rows": rows, "unseen": unseen, "labels": labels, "counts": counts, "groups": groups,
            "level_name": org.auto_level(), "level": org.check_level(), "documents": sum(status.values()),
            "waiting": status.get("needs_decision", 0), "machine": machine,
            "model": dict(used[0]) | {"bundle_json": None} if used else None,
            "check": evaluation.mismatches(rows)}


def report(m, rules=False, out=print):
    rows, unseen, labels, names = m["rows"], m["unseen"], m["labels"], m["names"]
    level = m["level"]
    known = [r for r in rows if r["examples"]]
    alone = Counter(r["category"] for r in rows if not r["examples"])
    unread = [d for d in labels if not m["counts"].get(d)]
    fams = len({m["groups"][d] for d in labels})
    out("ClassiFile matching evaluation (classifile.evaluation): each family held out in turn, word weights fitted "
        "inside each fold;\nno random step, so the same catalog gives the same numbers. Counts describe the user's "
        "own documents; not accuracy estimates.")
    out("\nModel and thresholds")
    if m["model"]:
        out(f"  Version in use: {m['model']['version']} ({m['model']['documents']} documents, "
            f"{m['model']['categories']} categories, trained {m['model']['created_at']})")
    else:
        out("  No model in use yet")
    out(f"  Method: {matching.REPRESENTATION}, {matching.SCORER} (the evaluation retrains it inside each fold)")
    out(f"  Automatic filing level in use: {m['level_name']} (lead >= {level}); levels: "
        + ", ".join(f"{k} {v}" for k, v in matching.LEVELS.items()))
    out(f"  A category needs {matching.AUTO_MIN_CONFIRMED} confirmed documents before automatic filing; good match "
        f"for cards: lead >= {matching.GOOD_MATCH}; versions: text similarity >= {matching.NEAR_TEXT}; new folders: "
        f"{matching.FOLDER_MIN}+ documents at {matching.FOLDER_LEVEL}; Check these: another folder ahead by "
        f">= {evaluation.CHECK_MARGIN}")
    out("\nWhat is counted")
    out(f"  {m['documents']} documents in the catalog: {len(labels)} filed by the user (the truth and the training),"
        f" {m['machine']} filed by the app and not yet confirmed (left out: never the truth, A7), "
        f"{m['waiting']} waiting (left out)")
    out(f"  {len(labels)} documents in {fams} families, {len(set(labels.values()))} categories")
    out(f"  {len(known)} of {len(labels)} have a category that keeps other families when theirs is held out: the "
        "denominator for 'first' and 'in the first three'.")
    if alone:
        out(f"  Left out of it: {sum(alone.values())} document(s) whose category has no other family (a folder of one"
            " family cannot be found when that family is held out): "
            + ", ".join(f"{names.get(c, c)} ({n})" for c, n in alone.most_common())
            + ". They still count in automatic filing, where filing them anywhere is wrong.")
    if unread:
        out(f"  {len(unread)} document(s) without readable text: they teach nothing and always wait.")
    s = evaluation.summary(rows, level)
    out("\nThe user's category")
    out(f"  first:                 {pct(s['first'], s['known'])}")
    out(f"  in the first three:    {pct(s['top3'], s['known'])}")
    out("\nAutomatic filing at each level (all {} documents; wrong = filed in another category)".format(len(rows)))
    out("  level         lead   right  wrong  waiting   wrong among those filed           new subjects wrongly filed")
    for name, lv in matching.LEVELS.items():
        a, u = evaluation.summary(rows, lv), evaluation.summary(unseen, lv)
        mark = " <- in use" if lv == level else ""
        out(f"  {name:12} {lv:5}   {a['right']:5}  {a['wrong']:5}  {a['waiting']:7}   "
            f"{pct(a['wrong'], a['right'] + a['wrong']):32}  {pct(u['right'] + u['wrong'], len(unseen))}{mark}")
    out(f"  New subjects: each category held out whole, so none of the {len(unseen)} documents has its category; "
        "filing any of them is wrong.")
    out(f"\nPer category (level in use, lead >= {level}): documents | first / in the first three (of those countable)"
        " | filed right / wrong | waiting")
    for c, n in Counter(labels.values()).most_common():
        mine = [r for r in rows if r["category"] == c]
        p = evaluation.summary(mine, level)
        out(f"  {names.get(c, c)[:38]:38} {n:3} | {p['first']:3} / {p['top3']:3} of {p['known']:3} | "
            f"{p['right']:3} / {p['wrong']:2} | {p['waiting']:3}")
    out(f"\nCheck these: {len(m['check'])} filed document(s) whose content matches another folder by "
        f">= {evaluation.CHECK_MARGIN}")
    for x in m["check"]:
        out(f"  {x['doc'][:8]}  filed in {names.get(x['category'], '?')}, matches {names.get(x['other'], '?')} "
            f"(ahead by {x['margin']:.3f})")
    if rules:
        for lv in sorted({level, matching.LEVELS["balanced"]}, reverse=True):
            out(f"\nSafer filing rules at lead >= {lv}{' (the level in use)' if lv == level else ''}, each added to it")
            out("  rule                                       filed right  wrong  waiting | new subjects wrongly filed")
            for name, rule in RULES.items():
                a, u = evaluation.summary(rows, lv, rule), evaluation.summary(unseen, lv, rule)
                out(f"  {name:42} {a['right']:11}  {a['wrong']:5}  {a['waiting']:7} | {u['right'] + u['wrong']:3} "
                    f"of {len(unseen)}")
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", action="store_true", help="also try the safer filing rules")
    ap.add_argument("--json", type=Path, help="save rows and summary here (never overwritten)")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    ap.add_argument("--set-families", nargs="+", type=Path, metavar="CSV", help="record the owner's family ids")
    a = ap.parse_args(argv)
    if a.set_families:
        cat = Catalog(a.catalog)
        try:
            held = {r[0] for r in cat.all("SELECT sha256 FROM snapshots")}
            families = {sha: f for sha, f in csv_families(a.set_families).items() if sha in held}
            cat.set_family_labels(families)
        finally:
            cat.close()
        print(f"Recorded the family ids of {len(families)} of the catalog's {len(held)} files.")
        return 0
    if a.json and a.json.exists():
        sys.exit(f"Refusing to overwrite existing file: {a.json}")
    if not a.catalog.exists():
        sys.exit(f"No catalog at {a.catalog}")
    with tempfile.TemporaryDirectory(prefix="classifile-evaluate-") as tmp:
        shutil.copyfile(a.catalog, Path(tmp) / "catalog.sqlite3")
        cat = Catalog(Path(tmp) / "catalog.sqlite3")
        try:
            m = measure(Organizer(cat))
        finally:
            cat.close()
    s = report(m, a.rules)
    if a.json:
        with open(a.json, "x", encoding="utf-8") as f:
            json.dump({"summary": s, "rows": m["rows"], "new subjects": m["unseen"], "check": m["check"]}, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
