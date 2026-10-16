"""The final evaluation, run once with the frozen version (decision record CP5, 2.10; docs/LAUNCH.md section 1).

Usage: python -m tools.final_eval data\\final-eval --labels data\\splits_incoming_2.csv [--out data\\final_evaluation.json]
       python -m tools.final_eval --report data\\final_evaluation.json

Every file of the folder that the splits CSV lists as final_evaluation (matched by SHA-256) is read the way the app
reads it, in memory: nothing is imported, and the catalog (a temporary copy, removed afterwards) is not changed, so
matching cannot update during the run. The tool refuses unless the version in use is the frozen one. Each document
is then treated as a new arrival in the app at the level in use: filed by itself when its best category leads by
the level and holds 3 confirmed documents; otherwise it waits, and waiting documents no category matches become an
automatic new folder when they group as the app groups them (matching.FOLDER_LEVEL, FOLDER_MIN, a free name).
The counts are the ones tools.evaluate prints (classifile.evaluation: summary, levels, Wilson ranges).

A label that names no category is counted under the category the owner filed the development files of that label
in, when there is one; otherwise it is a new subject, and filing it in any existing category is wrong.
The result is saved to --out, created new; when that file exists the tool refuses to measure again. --report
prints from the saved file without reading any document. Nothing is tuned afterwards (docs/LAUNCH.md). The output
names categories: keep it out of tracked files. Counts on a small held-out set, not a promise of accuracy.
"""
import argparse
import csv
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from classifile import evaluation, matching
from classifile.analysis.candidates import analyze, name_key, top_names
from classifile.catalog.db import Catalog, default_data_dir
from classifile.organizer import Organizer
from classifile.reader import READERS, read_document, sha256_file
from tools.evaluate import pct

FROZEN_VERSION = 6      # the matching version frozen in record 2.10


def measure(folder, rows, catalog_path, frozen=FROZEN_VERSION, progress=lambda n, total: None):
    """The saved result: the model's facts and, per document, its label, the category that label means (or None
    for a new subject), how it was read, the categories ranked best first, and its top suggested names."""
    with tempfile.TemporaryDirectory(prefix="classifile-final-") as tmp:
        shutil.copyfile(catalog_path, Path(tmp) / "catalog.sqlite3")
        cat = Catalog(Path(tmp) / "catalog.sqlite3")
        try:
            org = Organizer(cat)
            used = org.matcher()
            if not used or used[0]["version"] != frozen:
                sys.exit(f"Refusing: the matching version in use is {used[0]['version'] if used else 'none'}, "
                         f"not the frozen version {frozen}.")
            row, model = used
            names = {c["id"]: c["name"] for c in cat.categories()}
            confirmed = Counter(names[c] for c in cat.explicit_labels().values() if c in names)
            filed = {r["sha256"]: names[c] for r in cat.all("SELECT document_id, sha256 FROM snapshots")
                     if (c := cat.explicit_labels().get(r["document_id"])) in names}
            level_name, level = org.auto_level(), org.check_level()
            settings = {"auto_folders": org.auto_folders(), "scope": "all" if org.auto_scope() is None else "selected"}
        finally:
            cat.close()
    by_key = {name_key(n): n for n in names.values()}
    means = {}
    for label in {r["primary_label"] for r in rows if r["split"] == "final_evaluation"}:
        went = Counter(filed[r["sha256"]] for r in rows if r["split"] == "development"
                       and r["primary_label"] == label and r["sha256"] in filed)
        means[label] = by_key.get(name_key(label)) or (went.most_common(1)[0][0] if went else None)
    wanted = {r["sha256"]: r for r in rows if r["split"] == "final_evaluation"}
    files = [p for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in READERS]
    documents = []
    for n, path in enumerate(files, 1):
        progress(n, len(files))
        mine = wanted.pop(sha256_file(path), None)
        if mine is None:
            continue                        # not a labelled final-evaluation file: left alone
        try:
            result = read_document(path)
            status = result.status
        except Exception:                   # a parser crash is an operational failure, counted, never evidence
            status = "failed"
        ok = status == "ok"
        text = matching.record_text(result.record) if ok else ""
        documents.append({
            "sha256": mine["sha256"], "family": mine.get("family_id", ""), "label": mine["primary_label"],
            "category": means[mine["primary_label"]], "read": status,
            "ranked": [(names[c], s) for c, s in model.rank(text) if c in names] if ok else [],
            "terms": matching.terms(text),
            "suggested": [{"name": s.name, "score": s.score} for s in top_names(analyze(result.record, path.name).suggestions)]
            if ok else []})
    return {"model": {k: row[k] for k in ("version", "documents", "categories")}
            | {"good_match": model.bundle["settings"]["good_match"]},
            "level": [level_name, level], "settings": settings, "confirmed": dict(confirmed),
            "bundle": {"documents": model.bundle["documents"], "idf": model.bundle["idf"]},
            "documents": documents, "labelled files not found": len(wanted)}


def rows_of(saved):
    """The documents as classifile.evaluation rows: the same summary and levels as tools.evaluate. A new subject's
    category is never a category name, so filing it anywhere counts as wrong."""
    trained = Counter(saved["confirmed"])
    return [{"doc": n, "category": d["category"] or f"(new) {d['label']}", "ranked": d["ranked"],
             "examples": trained[d["category"]] if d["category"] else 0,
             "confirmed": trained[d["ranked"][0][0]] if d["ranked"] else 0, "neighbours": []}
            for n, d in enumerate(saved["documents"])]


def folders(saved, rows, level):
    """What happens to the documents that wait at this level: the automatic new folders the app would create
    (groups at FOLDER_LEVEL of at least FOLDER_MIN documents no category matches, each with a free name), and the
    questions left (waiting documents; those no category matches asked together when they group at GROUP_LEVEL)."""
    docs = saved["documents"]
    waiting = [r["doc"] for r in rows if not evaluation.filed(r, level)]
    unmatched = [n for n in waiting if docs[n]["terms"] and not (
        docs[n]["ranked"] and matching.lead(docs[n]["ranked"]) >= saved["model"]["good_match"])]
    made, taken = [], {name_key(n) for n in saved["confirmed"]}
    on = saved["settings"]["auto_folders"] and saved["settings"]["scope"] == "all"
    vectors = matching.group_vectors({n: docs[n]["terms"] for n in unmatched}, saved["bundle"])
    for ids in [g for g in matching.similar_groups(vectors, matching.FOLDER_LEVEL)
                if len(g) >= matching.FOLDER_MIN] if on and len(unmatched) >= matching.FOLDER_MIN else []:
        name = matching.group_name([docs[n]["suggested"] for n in ids], taken)
        if name:
            taken.add(name_key(name))
            labels = {docs[n]["label"] for n in ids}
            kind = ("mixed" if len(labels) > 1 else "known subject" if docs[ids[0]]["category"] else "new subject")
            made.append({"documents": ids, "labels": sorted(labels), "kind": kind})
    in_folder = {n for f in made for n in f["documents"]}
    pending = [n for n in waiting if n not in in_folder]
    left = [n for n in unmatched if n not in in_folder]
    grouped = matching.similar_groups({n: vectors[n] for n in left}, matching.GROUP_LEVEL) if len(left) > 1 else []
    asked = len(pending) - sum(map(len, grouped)) + len(grouped)
    return made, pending, asked


def report(saved, out=print):
    docs, model = saved["documents"], saved["model"]
    level_name, level = saved["level"]
    rows = rows_of(saved)
    out(f"Final evaluation, once. Model version {model['version']} ({model['documents']} documents, "
        f"{model['categories']} categories), frozen; level in use {level_name} (lead >= {level}); "
        f"automatic new folders {'on' if saved['settings']['auto_folders'] else 'off'}, "
        f"filing into {saved['settings']['scope']} categories")
    failed = [d for d in docs if d["read"] != "ok"]
    out(f"{len(docs)} documents in {len({d['family'] for d in docs})} families"
        + (f"; {len(failed)} could not be read (they wait)" if failed else "")
        + (f"; {saved['labelled files not found']} labelled files not found" if saved["labelled files not found"] else ""))
    new = Counter(d["label"] for d in docs if not d["category"])
    if new:
        out(f"New subjects (a label with no category): {sum(new.values())} documents")
    s = evaluation.summary(rows, level)
    out(f"\nThe owner's category first:       {pct(s['first'], s['known'])}   (documents whose category exists)")
    out(f"In the first three:               {pct(s['top3'], s['known'])}")
    out("\nPer label: first / in the first three / documents")
    for label, n in Counter(d["label"] for d in docs).most_common():
        mine = [r for r, d in zip(rows, docs) if d["label"] == label]
        k = evaluation.summary(mine, level)
        note = "" if docs[mine[0]["doc"]]["category"] else "   (new subject)"
        out(f"  {k['first']:3} / {k['top3']:3} / {n:3}  {label}{note}")
    out("\nAutomatic filing at every level: right / wrong / waiting (wrong includes new subjects forced into a folder)")
    for name, lv in sorted(matching.LEVELS.items(), key=lambda kv: -kv[1]):
        k = evaluation.summary(rows, lv)
        forced = sum(evaluation.filed(r, lv) for r, d in zip(rows, docs) if not d["category"])
        mark = "   <- in use" if lv == level else ""
        out(f"  {name:12} {k['right']:3} / {k['wrong']:3} / {k['waiting']:3}   new subjects forced: {forced}{mark}")
    made, pending, asked = folders(saved, rows, level)
    out(f"\nAt the level in use ({level_name}):")
    out(f"  filed automatically right:      {s['right']}")
    out(f"  filed automatically wrong:      {s['wrong']}   precision {pct(s['right'], s['right'] + s['wrong'])}")
    out(f"  new folders created:            {len(made)}   mixing subjects {sum(f['kind'] == 'mixed' for f in made)}; "
        f"a second folder for a subject the app has {sum(f['kind'] == 'known subject' for f in made)}")
    for f in made:
        out(f"    {len(f['documents'])} documents, {f['kind']}: {', '.join(f['labels'])}")
    out(f"  left waiting for the owner:     {pct(len(pending), len(docs))}")
    out(f"  distinct questions:             {asked}; documents per decision {len(pending) / asked if asked else 0:.2f}")
    out("\nCounts on a small held-out set, not a promise of accuracy. Similarities are never probabilities.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", nargs="?", type=Path)
    ap.add_argument("--labels", type=Path, help="the splits CSV with sha256, family_id, primary_label and split")
    ap.add_argument("--out", type=Path, default=Path("data") / "final_evaluation.json")
    ap.add_argument("--report", type=Path, help="print from a saved result; no document is read")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    a = ap.parse_args(argv)
    if a.report:
        report(json.loads(a.report.read_text(encoding="utf-8")))
        return 0
    if not a.folder or not a.labels:
        ap.error("give the final-evaluation folder and --labels, or --report")
    if a.out.exists():
        sys.exit(f"The final evaluation was already run ({a.out}). Print it with --report; it is not run twice.")
    with open(a.labels, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    saved = measure(a.folder, rows, a.catalog, FROZEN_VERSION, progress=lambda n, t: print(f"\rreading {n} of {t}", end="", flush=True))
    print()
    with open(a.out, "x", encoding="utf-8") as f:
        json.dump(saved, f)
    report(saved)
    return 0


if __name__ == "__main__":
    sys.exit(main())
