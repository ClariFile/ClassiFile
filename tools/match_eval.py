"""E2 and E4 on development data: which scorer matches documents to the owner's categories best, and when to abstain.

Usage: python -m tools.match_eval [--families CSV...] [--growth] [--json FILE]

Reads the filed documents of the app's catalog (a temporary copy of it, removed afterwards): their stored text and
the category the owner chose. Each family of documents is held out in turn (leave one family out); the TF-IDF
vocabulary and every scorer are fitted on the other families only, then asked for the held-out documents.
Scorers (word TF-IDF, decision record B4): nearest centroid, k nearest neighbours (k = 1, 3, 5) and logistic
regression (L2; C = 1, 10, 100).
Families: the family_id of the given CSVs (matched by SHA-256), else files with the same name apart from the
extension and copy marks, the same bytes, or nearly the same text.
Prints, per scorer: how often the owner's category came first and in the first three, for documents whose category
has other documents (a category whose only family is held out cannot be found: the right answer there is to
abstain, counted separately); the same by how many examples the category had; the abstention trade-off of one
global level (E4), on the best score or on its lead over the second; and, with each whole category held out, how
many documents of a subject never seen would be filed at those levels (false familiar).
--growth repeats the first part with a quarter and a half of the other families.
--json saves every held-out document's ranked scores (created new, never overwritten).
The output names categories: keep it out of tracked files. Counts describe development data; they are not accuracy
estimates. data/validation and data/final-eval are never read.
"""
import argparse
import csv
import json
import math
import random
import shutil
import sys
import tempfile
from collections import Counter
from operator import mul
from pathlib import Path

from classifile.analysis.candidates import top_names
from classifile.catalog.db import Catalog, default_data_dir
from classifile.matching import GOOD_MATCH, LEVELS, Centroids, dot, fit_idf, lead, terms, vector
from tools.inventory import _name_key

NEAR_TEXT = 0.9     # documents this similar count as one family (a version or a format twin)
CHOSEN = "nearest centroid"     # the primary scorer (E2); its confidence is the best category's lead over the second
# The levels of that lead for automatic filing (classifile.matching.LEVELS: fixed on development data before
# validation was measured), and filing everything for comparison.
STRICTNESS = tuple(LEVELS.items()) + (("file everything", 0.0),)
BANDS = ((1, 3, "1 to 3"), (4, 9, "4 to 9"), (10, 10 ** 9, "10 or more"))   # examples of the category


def load(catalog_path):
    """[{id, sha, file_name, category, terms, names, suggested}] for the documents whose category the owner chose
    (names: the category names suggested for the document, best first; suggested: the same with their scores)."""
    with tempfile.TemporaryDirectory(prefix="classifile-eval-") as tmp:
        shutil.copyfile(catalog_path, Path(tmp) / "catalog.sqlite3")
        cat = Catalog(Path(tmp) / "catalog.sqlite3")
        try:
            labels, texts = cat.explicit_labels(), cat.texts()
            cats = {c["id"]: c["name"] for c in cat.categories()}
            files = {r["document_id"]: r for r in cat.all("SELECT document_id, sha256, file_name FROM snapshots")}
            suggested = {d: top_names((cat.analysis(d) or {}).get("suggestions", [])) for d in labels}
        finally:
            cat.close()
    return [{"id": d, "sha": files[d]["sha256"], "file_name": files[d]["file_name"], "category": cats[labels[d]],
             "terms": terms(texts.get(d, "")), "names": [s["name"] for s in suggested[d]], "suggested": suggested[d]}
            for d in sorted(labels)]


def csv_families(paths):
    """{sha256: family id} from inventory or splits CSVs; rows of the final evaluation are skipped unread."""
    out = {}
    for n, path in enumerate(paths):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("family_id") and r.get("split") != "final_evaluation":
                    out[r["sha256"]] = f"{n}:{r['family_id']}"
    return out


def families(docs, known):
    """A family number per document (see the module text)."""
    parent = list(range(len(docs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen = {}
    for i, d in enumerate(docs):
        for key in (("csv", known.get(d["sha"])), ("name", _name_key(d["file_name"])), ("bytes", d["sha"])):
            if key[1]:
                parent[find(i)] = find(seen.setdefault(key, i))
    idf = fit_idf([d["terms"] for d in docs])       # for grouping only: no scorer sees these vectors
    vectors = [vector(d["terms"], idf) for d in docs]
    for i in range(len(docs)):
        for j in range(i):
            if dot(vectors[i], vectors[j]) >= NEAR_TEXT:
                parent[find(i)] = find(j)
    return [find(i) for i in range(len(docs))]


# -- the scorers: each is fit(K, vectors, labels) -> scores(x, sims) -> {category: score} -----------------------
def centroid(K, vectors, labels):
    model = Centroids(vectors, labels)
    return lambda x, sims: model.scores(x)


def neighbours(k):
    def fit(K, vectors, labels):
        def scores(x, sims):
            ranked = sorted(zip(sims, labels), reverse=True)
            out = {}
            for s, label in ranked:                 # every category: its nearest document, as a tie-break
                out.setdefault(label, s * 1e-6)
            for s, label in ranked[:k]:             # the k nearest vote with their similarity
                out[label] += s
            return out
        return scores
    return fit


def logistic(C, steps=300):
    """Multinomial logistic regression with an L2 penalty (strength 1/C, as scikit-learn counts it; the intercepts
    are penalized too), fitted in its dual form: the weights are a combination of the training vectors, so only
    their similarities K are needed. Accelerated gradient descent, `steps` steps."""
    def fit(K, vectors, labels):
        classes, n = sorted(set(labels)), len(labels)
        lam = 1.0 / (C * n)
        smooth = 0.5 * (max(sum(row) for row in K) + n) / n + lam      # the "+ n": the intercept
        rate, kappa = 1.0 / smooth, math.sqrt(smooth / lam)
        push = (kappa - 1) / (kappa + 1)
        Y = [[1.0 if label == c else 0.0 for label in labels] for c in classes]
        A = [[0.0] * (n + 1) for _ in classes]                         # per class: n weights, then the intercept
        ahead, rows = [a[:] for a in A], [row + [1.0] for row in K]
        for _ in range(steps):
            P = _softmax([[sum(map(mul, row, a)) for row in rows] for a in ahead])
            for k in range(len(classes)):
                G = [(p - y) / n for p, y in zip(P[k], Y[k])]
                G.append(sum(G))
                new = [a * (1 - rate * lam) - rate * g for a, g in zip(ahead[k], G)]
                ahead[k] = [x + push * (x - old) for x, old in zip(new, A[k])]
                A[k] = new

        def scores(x, sims):
            f = [[sum(map(mul, sims + [1.0], a))] for a in A]
            return {c: p[0] for c, p in zip(classes, _softmax(f))}
        return scores
    return fit


def _softmax(F):
    """F: one list per class. Returns the same shape."""
    out = [[0.0] * len(F[0]) for _ in F]
    for i in range(len(F[0])):
        top = max(f[i] for f in F)
        e = [math.exp(f[i] - top) for f in F]
        total = sum(e)
        for k in range(len(F)):
            out[k][i] = e[k] / total
    return out


SCORERS = {"nearest centroid": centroid, "kNN k=1": neighbours(1), "kNN k=3": neighbours(3), "kNN k=5": neighbours(5),
           "logistic C=1": logistic(1), "logistic C=10": logistic(10), "logistic C=100": logistic(100)}


def hold_out(docs, fam, scorers=SCORERS, share=1.0, seed=0):
    """Each group of documents is held out in turn (fam: a group per document; families, or categories to make
    every document a new subject). One row per document: its category, how many training examples that category
    had, and each scorer's categories ranked best first with their scores. share < 1: only that share of the
    other groups trains."""
    rng, rows = random.Random(seed), []
    for held in sorted(set(fam)):
        others = sorted(set(fam) - {held})
        if share < 1:
            others = rng.sample(others, max(1, round(len(others) * share)))
        train = [i for i in range(len(docs)) if fam[i] in others]
        idf = fit_idf([docs[i]["terms"] for i in train])
        vectors = [vector(docs[i]["terms"], idf) for i in train]
        labels = [docs[i]["category"] for i in train]
        K = [[0.0] * len(train) for _ in train]
        for a in range(len(train)):
            for b in range(a + 1):
                K[a][b] = K[b][a] = dot(vectors[a], vectors[b])
        fitted = {name: fit(K, vectors, labels) for name, fit in scorers.items()}
        for i in (i for i in range(len(docs)) if fam[i] == held):
            x = vector(docs[i]["terms"], idf)
            sims = [dot(x, v) for v in vectors]
            rows.append({"doc": docs[i]["id"], "category": docs[i]["category"], "family": held,
                         "examples": labels.count(docs[i]["category"]),
                         "ranked": {name: sorted(s(x, sims).items(), key=lambda kv: (-kv[1], kv[0]))
                                    for name, s in fitted.items()}})
    return rows


def hits(rows, name, top):
    return sum(r["category"] in [c for c, _ in r["ranked"][name][:top]] for r in rows)


CONFIDENCE = {   # one number per document that a single global level is set on (E4)
    "best score": lambda ranked: ranked[0][1],
    "best minus second": lead,
}


def trade_off(rows, name, level, confidence=CONFIDENCE["best score"]):
    """(right, wrong, new subjects taken for a known category, waiting) when documents whose confidence is at
    least `level` are filed in their best category and everything else waits for the owner."""
    c = Counter()
    for r in rows:
        ranked = r["ranked"][name]
        if not ranked or confidence(ranked) < level:
            c["waiting"] += 1
        elif ranked[0][0] == r["category"]:
            c["right"] += 1
        else:
            c["wrong" if r["examples"] else "false familiar"] += 1
    return c["right"], c["wrong"], c["false familiar"], c["waiting"]


def right_within(rows, name, confidence, allowed):
    """(documents filed right, the level) at the most lenient level that files at most `allowed` documents wrong
    (a new subject taken for a known category counts as wrong)."""
    best = (0, None)
    for level in sorted({confidence(r["ranked"][name]) for r in rows if r["ranked"][name]}, reverse=True):
        right, wrong, familiar, _ = trade_off(rows, name, level, confidence)
        if wrong + familiar > allowed:
            break
        best = (right, level)
    return best


def report(rows, out=print):
    known = [r for r in rows if r["examples"]]
    out(f"{len(rows)} documents, {len({r['family'] for r in rows})} families, "
        f"{len({r['category'] for r in rows})} categories; {len(known)} documents whose category has other "
        f"families, {len(rows) - len(known)} that are a new subject when held out")
    out("\nThe owner's category first / in the first three (documents whose category has other families)")
    for name in rows[0]["ranked"]:
        out(f"  {name:18} {hits(known, name, 1):3} / {hits(known, name, 3):3} of {len(known)}")
    out("\nBy how many examples the category had (first / first three / documents)")
    for name in rows[0]["ranked"]:
        parts = []
        for low, high, label in BANDS:
            band = [r for r in known if low <= r["examples"] <= high]
            parts.append(f"{label}: {hits(band, name, 1)}/{hits(band, name, 3)}/{len(band)}")
        out(f"  {name:18} " + "   ".join(parts))
    out("\nPer category (first / first three / documents), by scorer")
    for cat, n in Counter(r["category"] for r in rows).most_common():
        mine = [r for r in rows if r["category"] == cat]
        cells = "  ".join(f"{hits(mine, name, 1)}/{hits(mine, name, 3)}" for name in rows[0]["ranked"])
        out(f"  {n:3}  {cat[:38]:38} {cells}")
    out("     columns: " + ", ".join(rows[0]["ranked"]))
    out("\nAbstention, one global level (E4): documents filed right while at most 0 / 1 / 2 / 3 / 5 are filed wrong")
    for name in rows[0]["ranked"]:
        for kind, confidence in CONFIDENCE.items():
            cells = " / ".join(f"{right_within(rows, name, confidence, n)[0]:2}" for n in (0, 1, 2, 3, 5))
            out(f"  {name:18} {kind:18} {cells}")


def report_new_subjects(rows, unseen, out=print):
    """unseen: hold_out() rows with whole categories held out, so no document's category can be found."""
    out(f"\nNew subjects: each category held out whole ({len(unseen)} documents; filing any of them is wrong)."
        "\nFiled at the levels above (at most 0 / 1 / 2 / 3 / 5 wrong among the families)")
    for name in rows[0]["ranked"]:
        for kind, confidence in CONFIDENCE.items():
            cells = []
            for n in (0, 1, 2, 3, 5):
                level = right_within(rows, name, confidence, n)[1]
                filed = len(unseen) - trade_off(unseen, name, level, confidence)[3] if level is not None else 0
                cells.append(f"{filed:3}")
            out(f"  {name:18} {kind:18} {' / '.join(cells)}")
    if CHOSEN not in rows[0]["ranked"]:
        return
    out(f"\n{CHOSEN}, by the best category's lead over the second: filed right / wrong / waiting, and how many"
        f" of the {len(unseen)} documents of a subject never seen would be filed")
    for label, level in STRICTNESS:
        right, wrong, familiar, waiting = trade_off(rows, CHOSEN, level, lead)
        filed = len(unseen) - trade_off(unseen, CHOSEN, level, lead)[3]
        out(f"  {label:16} (lead >= {level:4}) {right:3} / {wrong + familiar:3} / {waiting:3}     {filed:3}")
    known = [r for r in rows if r["examples"]]
    shown = [r for r in known if lead(r["ranked"][CHOSEN]) >= GOOD_MATCH]
    out(f"Cards at the good-match level (lead >= {GOOD_MATCH}): of {len(known)} documents whose category exists, "
        f"{len(shown)} show three categories ({hits(shown, CHOSEN, 3)} with the owner's among them, "
        f"{hits(shown, CHOSEN, 1)} with it first); of the {len(unseen)} of a subject never seen, "
        f"{sum(lead(r['ranked'][CHOSEN]) < GOOD_MATCH for r in unseen)} get a suggested new name")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--families", nargs="*", default=[], type=Path, help="CSVs with sha256 and family_id")
    ap.add_argument("--growth", action="store_true", help="also with a quarter and a half of the other families")
    ap.add_argument("--json", type=Path, help="save every document's ranked scores here (never overwritten)")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    a = ap.parse_args(argv)
    if a.json and a.json.exists():
        sys.exit(f"Refusing to overwrite existing file: {a.json}")
    docs = load(a.catalog)
    fam = families(docs, csv_families(a.families))
    rows = hold_out(docs, fam)
    unseen = hold_out(docs, [d["category"] for d in docs])
    report(rows)
    report_new_subjects(rows, unseen)
    for share in (0.25, 0.5) if a.growth else ():
        print(f"\n=== a growing catalog: {int(share * 100)}% of the other families train ===")
        report(hold_out(docs, fam, share=share))
    if a.json:
        with open(a.json, "x", encoding="utf-8") as f:
            json.dump({"families": rows, "new subjects": unseen}, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
