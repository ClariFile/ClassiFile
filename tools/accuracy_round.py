"""Accuracy round on development data: does a change to the representation beat the matcher in use?

Usage: python -m tools.accuracy_round [--families CSV...] [--only NAME...] [--out FILE]
       python -m tools.accuracy_round --validation FOLDER --labels CSV --variant NAME [--out FILE]

The first form reads the filed documents of the app's catalog (a temporary copy, removed afterwards) and runs the
same family-grouped test as E2 (tools.match_eval) with nearest centroid, once per variant. A variant changes one
thing in how a document is turned into weighted words:
  head x2/x3/x5       extra weight for titles, headings and the first page;
  chars 0.3/0.5       character 3- to 5-grams beside the words, as that share of the similarity;
  bigrams             word pairs beside the words;
  ocr x0.5, no ocr    less or no weight for OCR text;
  no template         repeated template lines (headers, footers, running lines) left out;
  ocr x0.5, no template   both;
  not in half / a third   words found in more than that share of the training documents left out (tried because
                          the key words showed matches resting on "the", "of" and a cover page's standing words);
and the combinations named in VARIANTS. Per variant it prints: the owner's category first and in the first three;
filed right and wrong at Strict (the best category's lead over the second, classifile.matching.LEVELS), which is
not a like-for-like level once the representation changes, so also the most filed right while at most one is
filed wrong; new subjects (each category held out whole) filed at Strict; and the same per category. It prints
which categories are taken for which (a confusion table), key words a card could give as its reason, what the
categories with fewer than five documents would gain from more documents or from merging, and saves nothing but
--out (created new).
The second form measures one variant and the matcher in use, together, once, on the validation files listed in the
splits CSV: read in memory, nothing imported. --out is created new and the tool refuses when it exists.
Nothing here changes the app or its catalog. The output names categories and words from documents: keep it out of
tracked files. Counts describe development (or validation) data; data/final-eval is never read.
"""
import argparse
import csv
import json
import math
import random
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from classifile.analysis.candidates import name_key
from classifile.catalog.db import Catalog, default_data_dir
from classifile.matching import LEVELS, TOKEN, Centroids, fit_idf, lead
from classifile.reader import READERS, read_document, sha256_file
from tools import refuse_final_eval
from tools.match_eval import csv_families, families, hits, right_within, trade_off

STRICT = LEVELS["strict"]
SMALL = 5           # categories with fewer documents than this are looked at one by one
# What a variant changes; everything not named keeps the value of the matcher in use.
PLAIN = {"head": 1.0, "ocr": 1.0, "template": 1.0, "bigrams": False, "chars": 0.0, "common": 1.0}
VARIANTS = {
    "in use": {},
    "head x2": {"head": 2.0}, "head x3": {"head": 3.0}, "head x5": {"head": 5.0},
    "chars 0.3": {"chars": 0.3}, "chars 0.5": {"chars": 0.5},
    "bigrams": {"bigrams": True},
    "ocr x0.5": {"ocr": 0.5}, "no ocr": {"ocr": 0.0},
    "no template": {"template": 0.0},
    "ocr x0.5, no template": {"ocr": 0.5, "template": 0.0},
    "head x2, no template": {"head": 2.0, "template": 0.0},
    "head x3, no template": {"head": 3.0, "template": 0.0},
    "head x2, chars 0.3": {"head": 2.0, "chars": 0.3},
    "head x2, chars 0.3, no template": {"head": 2.0, "chars": 0.3, "template": 0.0},
    "not in half": {"common": 0.5}, "not in a third": {"common": 1 / 3},
    "head x3, ocr x0.5": {"head": 3.0, "ocr": 0.5},
    "head x3, ocr x0.5, not in half": {"head": 3.0, "ocr": 0.5, "common": 0.5},
    "head x3, ocr x0.5, not in a third": {"head": 3.0, "ocr": 0.5, "common": 1 / 3},
}


# -- a document as parts: what is the head, what is OCR, what is a repeated template line ------------------------
def _line_key(line):
    return re.sub(r"\d", "#", " ".join(line.split()).casefold())     # digits as #, as the reader keys them


def parts(units, first_lines, repeated):
    """{"body", "head", "ocr", "template"} texts of one document. units: dicts with kind, title, text, notes and
    ocr_text, in order; first_lines: the first page's or the opening lines; repeated: the template lines (on at
    least half the pages) and running lines (headers and footers) the reader found. The head is counted again on
    top of the body; template lines are apart."""
    known = {_line_key(r["line"]) for r in repeated if r.get("line")}
    body, template, head, ocr = [], [], list(first_lines), []
    for u in units:
        for line in (u["text"] or "").splitlines():
            (template if _line_key(line) in known else body).append(line)
        if u["notes"]:
            body.append(u["notes"])
        if u["title"]:
            head.append(u["title"])
        if u["kind"] in ("heading", "title"):
            head.append(u["text"] or "")
        if u["ocr_text"]:
            ocr.append(u["ocr_text"])
    return {"body": "\n".join(body), "head": "\n".join(head), "ocr": "\n".join(ocr), "template": "\n".join(template)}


def words(text, bigrams=False):
    """Word counts as the matcher counts them, with pairs of neighbouring words on a line when asked."""
    out = Counter()
    for line in text.casefold().splitlines():
        tokens = TOKEN.findall(line)
        out.update(tokens)
        if bigrams:
            out.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))
    return out


def chargrams(text):
    """Counts of the 3- to 5-letter pieces of each word (with its edges marked): close for a misread or cut word."""
    out = Counter()
    for token, n in Counter(TOKEN.findall(text.casefold())).items():
        padded = f"<{token}>"
        for size in (3, 4, 5):
            for i in range(len(padded) - size + 1):
                out[padded[i:i + size]] += n
    return out


def counts(doc, spec):
    """(weighted word counts, weighted character-piece counts or None) of a document under a variant."""
    spec = PLAIN | spec
    weights = (("body", 1.0), ("template", spec["template"]), ("ocr", spec["ocr"]), ("head", spec["head"] - 1.0))
    out = []
    for count in ((lambda t: words(t, spec["bigrams"])), chargrams if spec["chars"] else None):
        if count is None:
            out.append(None)
            continue
        total = Counter()
        for part, weight in weights:
            if weight > 0:
                for t, c in count(doc["parts"][part]).items():
                    total[t] += c * weight
        out.append(total)
    return out


def weigh(counted, idf):
    """classifile.matching.vector for counts that may be fractions (a part given less weight)."""
    w = {t: (1 + math.log(c) if c >= 1 else c) * idf[t] for t, c in counted.items() if t in idf and c > 0}
    norm = math.sqrt(sum(x * x for x in w.values()))
    return {t: x / norm for t, x in w.items()} if norm else {}


def vectors(train, test, share, common=1.0):
    """Vectors of the training and the test documents from their (word counts, character counts): the word
    weights fitted on the training documents only; with characters, the two kinds side by side, the characters as
    `share` of the similarity. common: words in more than this share of the training documents are left out."""
    out = [dict() for _ in train + test]
    for kind, scale in ((0, math.sqrt(1 - share)), (1, math.sqrt(share))):
        if not scale or train[0][kind] is None:
            continue
        idf = fit_idf([c[kind] for c in train])
        if common < 1:
            floor = math.log((1 + len(train)) / (1 + common * len(train))) + 1
            idf = {t: x for t, x in idf.items() if x >= floor}
        for vector, c in zip(out, train + test):
            for t, x in weigh(c[kind], idf).items():
                vector[(kind, t)] = x * scale
    return out[:len(train)], out[len(train):]


# -- the test: each family held out in turn; each category held out whole ----------------------------------------
def hold_out(docs, groups, counted, share, common=1.0):
    """One row per document, held out with its group: its category, the examples its category had, and the
    categories ranked best first by nearest centroid."""
    rows = []
    for held in sorted(set(groups), key=str):
        train = [i for i in range(len(docs)) if groups[i] != held]
        test = [i for i in range(len(docs)) if groups[i] == held]
        labels = [docs[i]["category"] for i in train]
        v_train, v_test = vectors([counted[i] for i in train], [counted[i] for i in test], share, common)
        model = Centroids(v_train, labels)
        for i, x in zip(test, v_test):
            ranked = sorted(model.scores(x).items(), key=lambda kv: (-kv[1], kv[0])) if x else []
            rows.append({"doc": i, "category": docs[i]["category"], "family": held,
                         "examples": labels.count(docs[i]["category"]), "ranked": {"v": ranked}, "x": x,
                         "centroid": model.centroids.get(ranked[0][0]) if ranked else None})
    return rows


def measure(docs, fam, spec):
    counted = [counts(d, spec) for d in docs]
    share, common = (PLAIN | spec)["chars"], (PLAIN | spec)["common"]
    return (hold_out(docs, fam, counted, share, common),
            hold_out(docs, [d["category"] for d in docs], counted, share, common))


def summary(rows, unseen):
    """(first, in the first three, documents whose category exists, filed right at Strict, filed wrong at Strict,
    new subjects filed at Strict, most filed right while at most one is filed wrong)."""
    known = [r for r in rows if r["examples"]]
    right, wrong, familiar, _ = trade_off(rows, "v", STRICT, lead)
    return (hits(known, "v", 1), hits(known, "v", 3), len(known), right, wrong + familiar,
            len(unseen) - trade_off(unseen, "v", STRICT, lead)[3], right_within(rows, "v", lead, 1)[0])


def per_category(rows, unseen):
    """{category: (documents, first, in the first three, filed right, filed wrong, as a new subject: filed)}."""
    out = {}
    for cat, n in Counter(r["category"] for r in rows).most_common():
        mine = [r for r in rows if r["category"] == cat]
        right, wrong, familiar, _ = trade_off(mine, "v", STRICT, lead)
        gone = [r for r in unseen if r["category"] == cat]
        out[cat] = (n, hits(mine, "v", 1), hits(mine, "v", 3), right, wrong + familiar,
                    len(gone) - trade_off(gone, "v", STRICT, lead)[3])
    return out


def confusions(rows):
    """[(owner's category, category it was taken for, documents)], most first; right answers are left out."""
    taken = Counter((r["category"], r["ranked"]["v"][0][0]) for r in rows
                    if r["ranked"]["v"] and r["ranked"]["v"][0][0] != r["category"])
    return [(a, b, n) for (a, b), n in taken.most_common()]


def key_words(row, n=5):
    """The words a document shares most with its best category: what a card could give as its reason."""
    if not row["x"] or not row["centroid"]:
        return []
    shared = {t: x * row["centroid"][t] for t, x in row["x"].items() if t in row["centroid"] and t[0] == 0}
    return [t[1] for t, _ in sorted(shared.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def with_fewer(docs, fam, category, k, repeats=3):
    """How often a category's documents come first when it holds only k other documents (several random picks)."""
    counted, first, asked = [counts(d, {}) for d in docs], 0, 0
    mine = [i for i, d in enumerate(docs) if d["category"] == category]
    for seed in range(repeats):
        rng = random.Random(seed)
        for i in mine:
            others = [j for j in mine if fam[j] != fam[i]]
            if len(others) < k:
                continue
            keep = set(rng.sample(others, k))
            train = [j for j in range(len(docs)) if fam[j] != fam[i] and (docs[j]["category"] != category or j in keep)]
            v_train, v_test = vectors([counted[j] for j in train], [counted[i]], 0.0)
            scores = Centroids(v_train, [docs[j]["category"] for j in train]).scores(v_test[0])
            first += max(scores, key=lambda c: (scores[c], c)) == category
            asked += 1
    return first, asked


# -- loading -----------------------------------------------------------------------------------------------------
def load(catalog_path):
    """[{id, sha, file_name, category, parts}] for the documents whose category the owner chose."""
    with tempfile.TemporaryDirectory(prefix="classifile-accuracy-") as tmp:
        shutil.copyfile(catalog_path, Path(tmp) / "catalog.sqlite3")
        cat = Catalog(Path(tmp) / "catalog.sqlite3")
        try:
            labels = cat.explicit_labels()
            names = {c["id"]: c["name"] for c in cat.categories()}
            units = {}
            for r in cat.all("SELECT s.document_id, u.kind, u.title, u.text, u.notes, u.ocr_text FROM extraction_units u"
                             " JOIN extractions e ON e.id = u.extraction_id JOIN snapshots s ON s.id = e.snapshot_id"
                             " ORDER BY s.document_id, u.unit_index"):
                units.setdefault(r["document_id"], []).append(dict(r))
            docs = []
            for r in cat.all("SELECT s.document_id, s.sha256, s.file_name, e.first_page_lines_json,"
                             " e.template_lines_json, e.recurring_lines_json, e.running_lines_json FROM snapshots s"
                             " JOIN extractions e ON e.snapshot_id = s.id ORDER BY s.document_id"):
                if r["document_id"] not in labels:
                    continue
                repeated = [x for k in ("template", "running") for x in json.loads(r[f"{k}_lines_json"] or "[]")]
                docs.append({"id": r["document_id"], "sha": r["sha256"], "file_name": r["file_name"],
                             "category": names[labels[r["document_id"]]],
                             "parts": parts(units.get(r["document_id"], []),
                                            json.loads(r["first_page_lines_json"] or "[]"), repeated)})
        finally:
            cat.close()
    return docs


def record_parts(record):
    """parts() for a document just read (a validation file), as the catalog would have stored it."""
    units = [{"kind": u.kind, "title": u.title, "text": u.text, "notes": u.notes, "ocr_text": u.ocr_text}
             for u in record.units]
    return parts(units, record.first_page_lines, record.template_lines + record.running_lines)


# -- reports -----------------------------------------------------------------------------------------------------
def report(docs, fam, names, out=print):
    results = {}
    out(f"{len(docs)} development documents, {len(set(fam))} families, "
        f"{len({d['category'] for d in docs})} categories; nearest centroid; Strict is a lead of {STRICT}")
    out("\nPer variant: first / in the first three (of the documents whose category exists) | at Strict: filed right"
        " / wrong | new subjects filed at Strict | most filed right with at most 1 wrong")
    for name in names:
        rows, unseen = results[name] = measure(docs, fam, VARIANTS[name])
        first, three, known, right, wrong, familiar, best = summary(rows, unseen)
        out(f"  {name:32} {first:3} / {three:3} of {known} | {right:3} / {wrong:2} | {familiar:3} of {len(unseen)} | {best:3}")
    for name in names:
        rows, unseen = results[name]
        out(f"\n{name}, per category: documents | first / in the first three | filed right / wrong at Strict |"
            " filed at Strict when held out as a new subject")
        for cat, (n, first, three, right, wrong, gone) in per_category(rows, unseen).items():
            out(f"  {cat[:38]:38} {n:3} | {first:3} / {three:3} | {right:3} / {wrong:2} | {gone:3}")
    for name in ("in use", names[-1]):
        out(f"\nTaken for another category ({name}): the owner's category -> what it was taken for, documents")
        for a, b, n in confusions(results[name][0]):
            out(f"  {n:2}  {a} -> {b}")
    rows = results["in use"][0]
    out("\nKey words a card could give as its reason: the words a document shares most with its best category,"
        " as they are / without the words found in more than a third of the documents")
    rare = hold_out(docs, fam, [counts(d, {}) for d in docs], 0.0, 1 / 3)   # the same ranking question, rarer words
    filtered = {r["doc"]: r for r in rare}
    for cat in dict(Counter(r["category"] for r in rows).most_common()):
        for r in [r for r in rows if r["category"] == cat and r["ranked"]["v"]][:2]:
            best = r["ranked"]["v"][0][0]
            again = filtered[r["doc"]] | {"centroid": None}
            if again["x"]:      # the words it shares with the same category, common words left out
                share_with = Centroids([x["x"] for x in rare if x["category"] == best and x["doc"] != r["doc"]],
                                       [best] * sum(x["category"] == best and x["doc"] != r["doc"] for x in rare))
                again = again | {"centroid": share_with.centroids.get(best)}
            out(f"  {cat[:26]:26} -> {best[:26]:26} {'right' if best == cat else 'WRONG':5}  {', '.join(key_words(r))}"
                f"  /  {', '.join(key_words(again)) or '(none)'}")
    small = [c for c, n in Counter(d["category"] for d in docs).items() if n < SMALL]
    sizes = Counter(d["category"] for d in docs)
    out(f"\nCategories with fewer than {SMALL} documents: " + ", ".join(f"{c} ({sizes[c]})" for c in small))
    out("More documents: how often a larger category's documents come first when it holds only k others")
    for cat in [c for c, n in sizes.most_common() if n >= 8]:
        cells = "   ".join("k={}: {} of {}".format(k, *with_fewer(docs, fam, cat, k)) for k in (1, 2, 3, 5))
        out(f"  {cat[:38]:38} {cells}")
    out("Merging: each small category put into the category its documents are most taken for, one at a time"
        " (first / in the first three, all documents; in use: "
        f"{hits(rows, 'v', 1)} / {hits(rows, 'v', 3)})")
    for cat in small:
        mine = [r for r in results["in use"][1] if r["category"] == cat and r["ranked"]["v"]]   # held out whole
        if not mine:
            continue
        target = Counter(r["ranked"]["v"][0][0] for r in mine).most_common(1)[0][0]
        merged = [d | {"category": target if d["category"] == cat else d["category"]} for d in docs]
        again = hold_out(merged, fam, [counts(d, {}) for d in merged], 0.0)
        out(f"  {cat} ({sizes[cat]}) into {target}: {hits(again, 'v', 1)} / {hits(again, 'v', 3)}"
            f"   (its own documents then first: {hits([r for r in again if docs[r['doc']]['category'] == cat], 'v', 1)}"
            f" of {sizes[cat]})")
    return results


def validate(folder, rows, catalog_path, variant, progress=lambda n, total: None):
    """The matcher in use and one variant, both trained on the filed documents, asked for every labelled
    validation file: {"variants": {name: [per document: label, the category it means, ranked]}}."""
    refuse_final_eval(folder)
    docs = load(catalog_path)
    by_key = {name_key(d["category"]): d["category"] for d in docs}
    wanted = {r["sha256"]: r for r in rows if r["split"] == "validation"}
    files, read = [p for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in READERS], []
    for n, path in enumerate(files, 1):
        progress(n, len(files))
        mine = wanted.pop(sha256_file(path), None)
        if mine is None:
            continue
        try:
            result = read_document(path)
            ok = result.status == "ok"
        except Exception:
            ok = False
        read.append((mine, {"parts": record_parts(result.record)} if ok else None))
    saved = {"documents": len(docs), "categories": len(by_key), "labelled files not found": len(wanted), "variants": {}}
    for name in ("in use", variant):
        spec = VARIANTS[name]
        v_train, v_test = vectors([counts(d, spec) for d in docs], [counts(d, spec) for _, d in read if d],
                                  (PLAIN | spec)["chars"], (PLAIN | spec)["common"])
        model, tested = Centroids(v_train, [d["category"] for d in docs]), iter(v_test)
        out = []
        for mine, d in read:
            x = next(tested) if d else {}
            ranked = sorted(model.scores(x).items(), key=lambda kv: (-kv[1], kv[0])) if x else []
            out.append({"sha256": mine["sha256"], "label": mine["primary_label"],
                        "category": by_key.get(name_key(mine["primary_label"])), "ranked": ranked})
        saved["variants"][name] = out
    return saved


def report_validation(saved, out=print):
    out(f"Trained on {saved['documents']} filed documents in {saved['categories']} categories")
    for name, docs in saved["variants"].items():
        first = lambda d: bool(d["ranked"]) and d["ranked"][0][0] == d["category"]
        three = lambda d: d["category"] in [c for c, _ in d["ranked"][:3]]
        filed = [d for d in docs if d["ranked"] and lead(d["ranked"]) >= STRICT]
        out(f"\n{name}: the owner's category first {sum(map(first, docs))}, in the first three "
            f"{sum(map(three, docs))}, of {len(docs)}; at Strict filed {len(filed)}, of those wrong "
            f"{len(filed) - sum(map(first, filed))}, waiting {len(docs) - len(filed)}")
        for label, n in Counter(d["label"] for d in docs).most_common():
            mine = [d for d in docs if d["label"] == label]
            note = "" if mine[0]["category"] else "   (no category of this name: nothing can be right)"
            out(f"  {sum(map(first, mine)):3} / {sum(map(three, mine)):3} / {n:3}  {label}{note}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--families", nargs="*", default=[], type=Path, help="CSVs with sha256 and family_id")
    ap.add_argument("--only", nargs="*", help="these variants only (the one in use is always measured)")
    ap.add_argument("--validation", type=Path, help="the validation folder: measure --variant there, once")
    ap.add_argument("--labels", type=Path, help="the splits CSV, for --validation")
    ap.add_argument("--variant", help="the variant to measure on validation")
    ap.add_argument("--out", type=Path, help="save the report (or the validation result) here; never overwritten")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    a = ap.parse_args(argv)
    if a.out and a.out.exists():
        sys.exit(f"Refusing: {a.out} exists. Validation is measured once; a report is never overwritten.")
    lines = []
    say = lambda text: (print(text), lines.append(text))
    if a.validation:
        if not a.labels or a.variant not in VARIANTS or not a.out:
            ap.error("--validation needs --labels, a --variant from VARIANTS, and --out")
        with open(a.labels, newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if r["split"] != "final_evaluation"]
        saved = validate(a.validation, rows, a.catalog, a.variant,
                         lambda n, total: print(f"\rreading {n} of {total}", end="", flush=True))
        print()
        with open(a.out, "x", encoding="utf-8") as f:
            json.dump(saved, f)
        report_validation(saved)
        return 0
    docs = load(a.catalog)
    fam = families([d | {"terms": words("\n".join(d["parts"][p] for p in ("body", "template", "ocr")))} for d in docs],
                   csv_families(a.families))
    names = ["in use"] + [n for n in VARIANTS if n != "in use" and (not a.only or n in a.only)]
    report(docs, fam, names, say)
    if a.out:
        with open(a.out, "x", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
