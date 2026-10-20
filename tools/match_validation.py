"""The matcher measured once on the validation files (decision record B4: validation is for operating choices).

Usage: python -m tools.match_validation data\\validation --labels data\\splits.csv [--out data\\validation_matching.json]
       python -m tools.match_validation --report data\\validation_matching.json

Every file of the folder that the splits CSV lists as validation (matched by SHA-256) is read the way the app
reads it, in memory: nothing is imported, and the catalog (a temporary copy, removed afterwards) is not changed.
The model in use (Settings, "Update matching") ranks the owner's categories for each; the result is saved to
--out, which is created new. When that file exists the tool refuses to measure again: looking at validation
repeatedly turns it into development data. --report prints from the saved file without reading any document.

Prints, per label: how often the owner's category came first, and in the first three; what the cards would show
at the model's "good match" level; and, for the strictness levels fixed on development data (tools.match_eval),
how many documents automatic filing would file, how many of those wrongly, and how many would wait.
A label that names no category is counted under the category the owner filed the development files of that label
in, when there is one, and is listed apart. The output names categories: keep it out of tracked files.
Counts describe these validation files; data/final-eval is never read.
"""
import argparse
import csv
import json
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from classifile.analysis.candidates import name_key
from classifile.catalog.db import Catalog, default_data_dir
from classifile.matching import lead, record_text
from classifile.organizer import Organizer
from classifile.reader import READERS, read_document, sha256_file
from tools import DATA, once, refuse_final_eval
from tools.match_eval import STRICTNESS

RECORD = DATA / "validation_matching.json"   # the one record of the measurement, whatever --out says


def measure(folder, rows, catalog_path, progress=lambda n, total: None):
    """The saved result: the model's facts and, per validation document, its label, the category that label
    means, and the categories ranked best first with their scores."""
    refuse_final_eval(folder)
    with tempfile.TemporaryDirectory(prefix="classifile-validation-") as tmp:
        shutil.copyfile(catalog_path, Path(tmp) / "catalog.sqlite3")
        cat = Catalog(Path(tmp) / "catalog.sqlite3")
        try:
            used = Organizer(cat).matcher()
            if not used:
                sys.exit("No matching model yet: use Update matching in the app's Settings first.")
            row, model = used
            names = {c["id"]: c["name"] for c in cat.categories()}
            by_key = {name_key(n): n for n in names.values()}
            labels = cat.explicit_labels()
            filed = {r["sha256"]: names[labels[r["document_id"]]] for r in cat.all(
                "SELECT document_id, sha256 FROM snapshots") if r["document_id"] in labels}
        finally:
            cat.close()
    means = {}      # label -> the category it means: one of that name, else where its development files went
    for label in {r["primary_label"] for r in rows if r["split"] == "validation"}:
        went = Counter(filed[r["sha256"]] for r in rows if r["split"] == "development"
                       and r["primary_label"] == label and r["sha256"] in filed)
        means[label] = by_key.get(name_key(label)) or (went.most_common(1)[0][0] if went else None)
    wanted = {r["sha256"]: r for r in rows if r["split"] == "validation"}
    files = [p for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in READERS]
    documents = []
    for n, path in enumerate(files, 1):
        progress(n, len(files))
        mine = wanted.pop(sha256_file(path), None)
        if mine is None:
            continue                        # not a labelled validation file: left alone
        try:
            result = read_document(path)
            status = result.status
        except Exception:                   # a parser crash is an operational failure, counted, never evidence
            status = "failed"
        ranked = model.rank(record_text(result.record)) if status == "ok" else []
        documents.append({"sha256": mine["sha256"], "label": mine["primary_label"],
                          "category": means[mine["primary_label"]], "named": name_key(mine["primary_label"]) in by_key,
                          "read": status, "ranked": [(names[c], s) for c, s in ranked if c in names]})
    return {"model": {k: row[k] for k in ("version", "documents", "categories")}
            | {"good_match": model.bundle["settings"]["good_match"]},
            "documents": documents, "labelled files not found": len(wanted)}


def report(saved, out=print):
    docs, model = saved["documents"], saved["model"]
    out(f"Model version {model['version']} ({model['documents']} documents, {model['categories']} categories); "
        f"{len(docs)} validation documents" + (f"; {saved['labelled files not found']} labelled files not found"
                                               if saved["labelled files not found"] else ""))
    first = lambda d: bool(d["ranked"]) and d["ranked"][0][0] == d["category"]
    three = lambda d: d["category"] in [c for c, _ in d["ranked"][:3]]
    out("\nThe owner's category first / in the first three / documents, per label")
    for label, n in Counter(d["label"] for d in docs).most_common():
        mine = [d for d in docs if d["label"] == label]
        note = "" if mine[0]["named"] else (f"   (no category of this name: counted as {mine[0]['category']})"
                                           if mine[0]["category"] else "   (no such category: nothing can be right)")
        out(f"  {sum(map(first, mine)):3} / {sum(map(three, mine)):3} / {n:3}  {label}{note}")
    out(f"  {sum(map(first, docs)):3} / {sum(map(three, docs)):3} / {len(docs):3}  all")
    named = [d for d in docs if d["named"]]
    out(f"  {sum(map(first, named)):3} / {sum(map(three, named)):3} / {len(named):3}  labels that name a category")
    shown = [d for d in docs if d["ranked"] and lead(d["ranked"]) >= model["good_match"]]
    out(f"\nCards at the good-match level: {len(shown)} of {len(docs)} would show three categories "
        f"({sum(map(three, shown))} with the owner's among them, {sum(map(first, shown))} with it first); "
        f"{len(docs) - len(shown)} would show a suggested new name "
        f"({sum(map(three, [d for d in docs if d not in shown]))} of them had the owner's category in the first three)")
    out("\nAutomatic filing at the levels fixed on development data: filed / of those wrong / waiting")
    for name, level in STRICTNESS:
        filed = [d for d in docs if d["ranked"] and lead(d["ranked"]) >= level]
        out(f"  {name:16} {len(filed):3} / {len(filed) - sum(map(first, filed)):3} / {len(docs) - len(filed):3}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", nargs="?", type=Path)
    ap.add_argument("--labels", type=Path, help="the splits CSV with sha256, primary_label and split")
    ap.add_argument("--out", type=Path, help="also save the result here (the record stays data/validation_matching"
                                             ".json; a later run only copies it)")
    ap.add_argument("--report", type=Path, help="print from a saved result; no document is read")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    a = ap.parse_args(argv)
    if a.report:
        report(json.loads(a.report.read_text(encoding="utf-8")))
        return 0
    if not a.folder or not a.labels:
        ap.error("give the validation folder and --labels, or --report")
    with open(a.labels, newline="", encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["split"] != "final_evaluation"]

    def run():
        saved = measure(a.folder, rows, a.catalog, lambda n, total: print(f"\rreading {n} of {total}", end="",
                                                                          flush=True))
        print()
        return saved
    report(once(RECORD, a.out, run, "Validation was already measured."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
