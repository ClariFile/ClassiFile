"""The one evaluation of matching: every number about it is measured this way (from 2026-10-15), by
tools.evaluate and by the app's update check (Organizer.update_matching).

Each family of documents (a document with its versions and format twins) is held out in turn. A model is trained
the way matching.train() trains one, on the other families only: the word weights (fit_idf) are fitted inside each
fold, never on the documents asked. The held-out documents are then ranked as the app ranks a waiting document.
There is no random step: the same catalog and code always give the same numbers.

Only the user's explicit choices are the truth and the training (A7); placements the app made by itself are
neither. Counts describe the user's own documents; they are not accuracy estimates, and scores are similarities,
never probabilities. Standard library only.
"""
import math
import re
from collections import Counter
from pathlib import Path

from classifile import matching

NEIGHBOURS = 5      # the nearest training documents kept per row (the safer-filing rules tried in tools.evaluate)
# "Check these": a filed document is listed when, held out, another folder leads its own by at least this much,
# the margin at which the app would file it there by itself at Strict.
CHECK_MARGIN = matching.LEVELS["strict"]


def file_stem(file_name):
    """The name without its extension, copy marks ("(2)", "copy", "converted"), case and punctuation; "" when
    too little is left to mean anything. The same stem is the same material in another format or version."""
    stem = re.sub(r"(\s*\(\d+\)|[\s_-]*copy|[\s_-]*converted)+$", "", Path(file_name).stem.casefold())
    key = " ".join(re.findall(r"[a-z0-9]+", stem))
    return key if len(key) >= 4 and re.search(r"[a-z]", key) else ""


def families(counts, files):
    """{document id: family id} for the documents of counts ({id: matching.terms()}). files: {id: (sha256, file
    name, the owner's family id or "")}. Documents are one family when the owner says so, or when they have the
    same bytes, the same file_stem(), or nearly the same text (matching.NEAR_TEXT). The family id is its smallest
    document id."""
    docs = sorted(counts)
    parent = {d: d for d in docs}

    def find(d):
        while parent[d] != d:
            parent[d] = parent[parent[d]]
            d = parent[d]
        return d

    def join(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    seen = {}
    for d in docs:
        sha, name, owner = files.get(d, ("", "", ""))
        for key in (("owner", owner), ("bytes", sha), ("name", file_stem(name))):
            if key[1]:
                join(d, seen.setdefault(key, d))
    idf = matching.fit_idf([counts[d] for d in docs])     # for finding versions only: no model sees these vectors
    vectors = {d: matching.vector(counts[d], idf) for d in docs}
    for i, a in enumerate(docs):
        for b in docs[:i]:
            if vectors[a] and matching.dot(vectors[a], vectors[b]) >= matching.NEAR_TEXT:
                join(a, b)
    return {d: find(d) for d in docs}


def evaluate(counts, labels, groups, training=None, live=None):
    """One row per document of labels ({id: the user's category}), held out with its group (groups: {id: group};
    the families, or each document's category to make every document a new subject).
    training: what the models learn from, {id: category} (default: labels); an earlier version's training replays
    that version on the same questions. live: the categories that may be named (default: any).
    A row: doc, category, examples (training documents of its category in the fold), ranked ([(category,
    similarity)], best first; empty when nothing in the document is known), confirmed (training documents of the
    best category in the fold) and neighbours (the categories of the NEIGHBOURS most similar training
    documents, nearest first)."""
    learn = {d: c for d, c in (labels if training is None else training).items() if counts.get(d)}
    rows = []
    for g in sorted({groups[d] for d in labels}, key=str):
        fold = sorted(d for d in learn if groups.get(d) != g)
        idf = matching.fit_idf([counts[d] for d in fold])
        vectors = [matching.vector(counts[d], idf) for d in fold]
        model = matching.Centroids(vectors, [learn[d] for d in fold])
        held = Counter(learn[d] for d in fold)
        for d in sorted(d for d in labels if groups[d] == g):
            x = matching.vector(counts.get(d, {}), idf)
            scores = model.scores(x) if x else {}
            ranked = sorted(((c, s) for c, s in scores.items() if live is None or c in live),
                            key=lambda kv: (-kv[1], kv[0]))
            near = sorted(((-matching.dot(x, v), learn[e]) for e, v in zip(fold, vectors)))[:NEIGHBOURS] if x else []
            rows.append({"doc": d, "category": labels[d], "examples": held[labels[d]], "ranked": ranked,
                         "confirmed": held[ranked[0][0]] if ranked else 0, "neighbours": [c for _, c in near]})
    return rows


def filed(row, level, rule=None):
    """Would the app file this document by itself at this level (lead over the second, and enough confirmed
    documents in the best category: matching.AUTO_MIN_CONFIRMED)? rule: a further condition to try."""
    return (bool(row["ranked"]) and matching.lead(row["ranked"]) >= level
            and row["confirmed"] >= matching.AUTO_MIN_CONFIRMED and (rule is None or rule(row)))


def summary(rows, level, rule=None):
    """{"documents", "known" (those whose category the fold had), "first", "top3" (of known), "right", "wrong",
    "waiting" (automatic filing at level; filing a document whose category the fold did not have is wrong)}."""
    known = [r for r in rows if r["examples"]]
    out = {"documents": len(rows), "known": len(known),
           "first": sum(r["ranked"][0][0] == r["category"] for r in known if r["ranked"]),
           "top3": sum(r["category"] in [c for c, _ in r["ranked"][:3]] for r in known),
           "right": 0, "wrong": 0}
    for r in rows:
        if filed(r, level, rule):
            out["right" if r["ranked"][0][0] == r["category"] else "wrong"] += 1
    out["waiting"] = len(rows) - out["right"] - out["wrong"]
    return out


def no_worse(new, old):
    """The update check (record A7): a new version replaces the one in use only if, on the same evaluation,
    it files no more documents wrongly at the level in use and puts the user's category first no less often."""
    return new["wrong"] <= old["wrong"] and new["first"] >= old["first"]


def mismatches(rows, margin=CHECK_MARGIN):
    """"Check these": [{"doc", "category" (where it is filed), "other" (the folder its content matches), "margin"}]
    for documents whose own category could be measured and that another category leads by at least margin."""
    out = []
    for r in rows:
        own = dict(r["ranked"]).get(r["category"])
        if r["examples"] and own is not None and r["ranked"][0][0] != r["category"] \
                and r["ranked"][0][1] - own >= margin:
            out.append({"doc": r["doc"], "category": r["category"], "other": r["ranked"][0][0],
                        "margin": round(r["ranked"][0][1] - own, 3)})
    return sorted(out, key=lambda m: (-m["margin"], m["doc"]))


def wilson(k, n, z=1.96):
    """A simple 95% range (Wilson score interval) for k of n, as fractions. It describes how much a count of this
    size could move by chance, nothing more."""
    if not n:
        return 0.0, 1.0
    p, d = k / n, 1 + z * z / n
    centre, half = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)
