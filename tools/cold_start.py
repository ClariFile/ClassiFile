"""A new user's first days, simulated on the user's development documents (report only; nothing in the app changes).

Usage: python -m tools.cold_start [--shuffle SEED] [--out FILE] [--catalog FILE]

The library starts empty and the documents the user filed arrive one at a time, in the order they were imported
(--shuffle: in a fixed random order instead). Each one is handled as the app handles it: filed by itself when the
model in use puts a category ahead of the second by the Strict lead and that category holds 3 documents the user
confirmed; otherwise the user decides (the user's own category is the answer), helped when the card already shows
that category among the three it offers. Placements the app makes by itself never train (A7) and are not reviewed
in the simulation. Matching is first trained as soon as two categories exist (in the app: one press of "Update
matching"), then again after every 10 decisions, as the app does by itself (record 2.6); every update is kept.
Variants, each from the same empty start:
  as today                 the app as it is;
  a. existing folders      "Learn from my existing folders": the user's folder tree already holds the first 3
                           (or the first half) of each category's documents, as examples the user organized;
  b. key words             a few words per folder as a starting example until the folder holds 3 confirmed
                           documents: the folder's name, or (an upper bound no user can reach) the 5 words that
                           best describe the folder's documents; with the 3-document rule kept, or relaxed for
                           folders that have key words.
Per folder: the user's decisions before the first document is filed into it by itself. The output names categories
and words: keep it out of tracked files. Counts describe development data; they are not accuracy estimates.
data/validation and data/final-eval are never read.
"""
import argparse
import random
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from classifile import matching
from classifile.catalog.db import Catalog, default_data_dir

STRICT = matching.LEVELS["strict"]


def simulate(order, texts, truth, seeds=(), words=None, relaxed=False):
    """One run. order: document ids in arrival order; truth: {id: category}; seeds: documents the user's existing
    folders already hold; words: {category: key-word text} used as an example until it holds 3 confirmed
    documents; relaxed: a folder with key words may be filed into by itself before then.
    Returns {"steps": [(doc, what)], "before": {category: decisions before its first automatic filing, or None}}.
    what: "auto right", "auto wrong", "auto new" (wrong: its category did not exist yet), "card" (the user's category among the three offered), "picked" (chosen from
    the list), "new" (a category the library did not have)."""
    words = words or {}
    labels = {d: truth[d] for d in seeds}
    model, since, steps = None, 0, []
    decided, before = Counter(), {}

    def train():
        extra = {f"kw:{c}": w for c, w in words.items() if list(labels.values()).count(c) < matching.AUTO_MIN_CONFIRMED}
        return matching.Matcher(matching.train(texts | extra, labels | {k: k[3:] for k in extra}))

    if len(set(labels.values()) | set(words)) >= 2:
        model = train()
    for d in order:
        if d in labels:
            continue
        ranked = model.rank(texts[d]) if model else []
        best = ranked[0][0] if ranked else None
        held = list(labels.values()).count(best)
        if ranked and matching.lead(ranked) >= STRICT and (held >= matching.AUTO_MIN_CONFIRMED
                                                           or (relaxed and best in words)):
            steps.append((d, "auto right" if best == truth[d] else "auto wrong" if truth[d] in labels.values()
                          else "auto new"))
            before.setdefault(best, decided[best])
            continue
        c = truth[d]
        offered = [x for x, _ in ranked[:3]] if model and model.good(ranked) else []
        steps.append((d, "card" if c in offered else "picked" if c in labels.values() else "new"))
        labels[d], since = c, since + 1
        decided[c] += 1
        if (model is None and len(set(labels.values()) | set(words)) >= 2) or since >= matching.AUTO_UPDATE_EVERY:
            model, since = train(), 0
    return {"steps": steps, "before": {c: before.get(c) for c in sorted(set(truth.values()))}, "decided": decided}


def best_words(texts, truth, n=5):
    """{category: its n heaviest words in a model trained on all the documents}: an upper bound for key words."""
    bundle = matching.train(texts, truth)
    return {c: " ".join(t for t, _ in sorted(v.items(), key=lambda kv: (-kv[1], kv[0]))[:n])
            for c, v in bundle["centroids"].items()}


def variants(order, texts, truth, names):
    first = {}
    for d in order:
        first.setdefault(truth[d], []).append(d)
    three = [d for ds in first.values() for d in ds[:3]]
    half = [d for ds in first.values() for d in ds[:len(ds) // 2]]
    by_name = {c: names[c] for c in set(truth.values())}
    upper = best_words(texts, truth)
    return {
        "as today": simulate(order, texts, truth),
        "a. existing folders hold 3 per folder": simulate(order, texts, truth, three),
        "a. existing folders hold half of each": simulate(order, texts, truth, half),
        "b. folder name as key words, 3-document rule kept": simulate(order, texts, truth, words=by_name),
        "b. folder name as key words, rule relaxed": simulate(order, texts, truth, words=by_name, relaxed=True),
        "b. 5 best words (upper bound), rule kept": simulate(order, texts, truth, words=upper),
        "b. 5 best words (upper bound), rule relaxed": simulate(order, texts, truth, words=upper, relaxed=True),
    }


def report(runs, truth, names, out=print):
    out(f"A new user's first days: {len(truth)} documents in {len(set(truth.values()))} folders, arriving one at a "
        "time; automatic filing at Strict")
    out("\nvariant                                             arriving | decisions: card / picked / new | filed by "
        "itself: right / wrong (its folder did not exist yet) | decisions before the first filing by itself")
    for name, r in runs.items():
        k = Counter(w for _, w in r["steps"])
        dec = k["card"] + k["picked"] + k["new"]
        auto = [i for i, (_, w) in enumerate(r["steps"]) if w.startswith("auto")]
        first = sum(1 for _, w in r["steps"][:auto[0]] if not w.startswith("auto")) if auto else None
        out(f"  {name:50} {len(r['steps']):8} | {dec:3}: {k['card']:3} / {k['picked']:3} / {k['new']:3}      | "
            f"{k['auto right']:3} / {k['auto wrong'] + k['auto new']:2} ({k['auto new']:2})"
            f"                             | {first if first is not None else 'never'}")
    out("\nPer folder: the user's decisions on its documents before the first one filed into it by itself "
        "('never': it never was; documents already in existing folders are not decisions)")
    keys = list(runs)
    out("  folder (documents)                       " + " | ".join(f"{i}" for i in range(len(keys))))
    for i, k in enumerate(keys):
        out(f"    {i} = {k}")
    for c, n in Counter(truth.values()).most_common():
        cells = [runs[k]["before"][c] for k in keys]
        out(f"  {names.get(c, c)[:34]:34} ({n:3}) " + " | ".join(f"{'never' if x is None else x:>5}" for x in cells))
    out("\nCounts on development data in one arrival order; they are not accuracy estimates.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--shuffle", type=int, help="a fixed random arrival order instead of the import order")
    ap.add_argument("--out", type=Path, help="also save the report here (never overwritten)")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    a = ap.parse_args(argv)
    if a.out and a.out.exists():
        sys.exit(f"Refusing to overwrite existing file: {a.out}")
    with tempfile.TemporaryDirectory(prefix="classifile-cold-") as tmp:
        shutil.copyfile(a.catalog, Path(tmp) / "catalog.sqlite3")
        cat = Catalog(Path(tmp) / "catalog.sqlite3")
        try:
            truth, texts = cat.explicit_labels(), cat.texts()
            names = {c["id"]: c["name"] for c in cat.all("SELECT id, name FROM categories")}
            order = [r[0] for r in cat.all("SELECT d.id FROM documents d JOIN snapshots s ON s.document_id = d.id"
                                           " ORDER BY d.created_at, s.id")]
        finally:
            cat.close()
    truth = {d: c for d, c in truth.items() if texts.get(d)}
    order = [d for d in dict.fromkeys(order) if d in truth]
    if a.shuffle is not None:
        random.Random(a.shuffle).shuffle(order)
    lines = []
    report(variants(order, texts, truth, names), truth, names, lines.append)
    print("\n".join(lines))
    if a.out:
        with open(a.out, "x", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
