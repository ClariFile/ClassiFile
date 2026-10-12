"""The owner's grouping of development files, read from the app's catalog (decision record G3, experiment E1).

Usage: python -m tools.grouping <folder>... [--catalog PATH]

Only the files in the given folders count (matched by SHA-256); everything else in the catalog is ignored. Prints:
  - the owner's categories and how many documents each holds;
  - for each filing, whether the category is a suggestion as it was shown, a near form of one, part of one, or a
    typed name, with the rank of that suggestion (1-3 are the names shown first; higher ranks are under "More");
  - candidate grouping policies against the owner's grouping: over-merging and fragmentation separately.
The policies here only pick one of the stored suggestions per document by where it was found; the documented
organizing policy (E1) is not built yet. Counts describe development data; they are not accuracy estimates.
The catalog is opened read-only. The output names files and categories: keep it out of tracked files.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

from classifile.analysis.candidates import name_key, top_names
from tools import refuse_final_eval

FORMATS = (".pdf", ".pptx", ".docx", ".odt")
REPEATED = ("template", "recurring", "running")
COVER = ("first_page", "first_page_ocr")


def words(name):
    """Words for the near-form check: case, punctuation, "and"/"&" and a plural "s" do not count."""
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w
            for w in re.findall(r"[a-z0-9+#]+", name.casefold()) if w != "and"]


def how_filed(category, suggestions):
    """(kind, rank): "as shown" | "near form" | "part of a suggestion" | "typed"; rank in the order shown."""
    shown = top_names(suggestions)
    ordered = shown + [s for s in suggestions if s not in shown]
    cat = words(category)
    for kind, same in (("as shown", lambda s: name_key(s["name"]) == name_key(category)),
                       ("near form", lambda s: words(s["name"]) == cat),
                       ("part of a suggestion", lambda s: bool(cat) and (set(cat) < set(words(s["name"]))
                                                                        or set(words(s["name"])) < set(cat)))):
        for rank, s in enumerate(ordered, 1):
            if same(s):
                return kind, rank
    return "typed", None


def with_source(sources):
    """A policy: the first suggestion (in the order shown) found in one of these places, else None."""
    def pick(suggestions):
        return next((name_key(s["name"]) for s in top_names(suggestions, len(suggestions))
                     if any(e["source"] in sources for e in s["evidence"])), None)
    return pick


POLICIES = {
    "top suggestion": lambda s: next((name_key(x["name"]) for x in top_names(s, 1)), None),
    "cover or opening line": with_source(COVER),
    "repeated line": with_source(REPEATED),
    "repeated line, else cover, else top": lambda s: (with_source(REPEATED)(s) or with_source(COVER)(s)
                                                       or POLICIES["top suggestion"](s)),
    "file name": with_source(("filename",)),
}


def shared_names(filed):
    """A bound, not a policy: documents are put together whenever they share any suggested name at all. No way of
    picking one suggestion per document can put more of the owner's pairs together than this does."""
    group, seen = {}, {}

    def find(x):
        while group.setdefault(x, x) != x:
            x = group[x]
        return x

    for name, _, suggestions in filed:
        for s in suggestions:
            group[find(name)] = find(seen.setdefault(name_key(s["name"]), name))
    return {name: find(name) for name, _, _ in filed}


def compare(own, policy):
    """Pairs of documents: own and policy map document -> group (policy: None = left pending)."""
    c = Counter()
    for a, b in combinations(sorted(own), 2):
        together = own[a] == own[b]
        pending = policy[a] is None or policy[b] is None
        merged = not pending and policy[a] == policy[b]
        c["owner together"] += together
        c["policy together"] += merged
        c["both together"] += together and merged
        c["over-merged"] += merged and not together
        c["fragmented: placed apart"] += together and not merged and not pending
        c["fragmented: left pending"] += together and pending
    return c


def load(folders, catalog):
    """[(file name, category or None, suggestions)] for the folders' files that are in the catalog, and the misses."""
    db = sqlite3.connect(f"file:{Path(catalog).as_posix()}?mode=ro", uri=True)
    rows, missing = [], []
    for folder in folders:
        refuse_final_eval(folder)
        for p in sorted(Path(folder).iterdir()):
            if p.suffix.lower() not in FORMATS:
                continue
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            r = db.execute(
                "SELECT e.analysis_json, (SELECT c.name FROM memberships m JOIN categories c ON c.id = m.category_id"
                " WHERE m.document_id = s.document_id AND m.role = 'primary' AND m.status = 'active')"
                " FROM snapshots s LEFT JOIN extractions e ON e.snapshot_id = s.id WHERE s.sha256 = ?", (sha,)).fetchone()
            if r is None:
                missing.append(p.name)
            else:
                rows.append((p.name, r[1], (json.loads(r[0]) if r[0] else {}).get("suggestions", [])))
    db.close()
    return rows, missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="+", type=Path)
    ap.add_argument("--catalog", type=Path,
                    default=Path(os.environ.get("CLASSIFILE_DATA_DIR") or Path(os.environ.get("LOCALAPPDATA", "")) / "ClassiFile")
                    / "catalog.sqlite3")
    a = ap.parse_args(argv)
    rows, missing = load(a.folders, a.catalog)
    filed = [r for r in rows if r[1]]
    print(f"{len(rows) + len(missing)} files; {len(filed)} filed, {len(rows) - len(filed)} waiting, "
          f"{len(missing)} not in the catalog")
    for name in [r[0] for r in rows if not r[1]] + missing:
        print(f"  not filed: {name}")
    sizes = Counter(r[1] for r in filed)
    print(f"\n{len(sizes)} categories; sizes: {dict(sorted(Counter(sizes.values()).items()))} (documents: categories)")
    for cat, n in sizes.most_common():
        print(f"  {n}  {cat}")
    print("\nHow each document was filed")
    kinds = Counter()
    for name, cat, suggestions in filed:
        kind, rank = how_filed(cat, suggestions)
        kinds[kind, "shown first" if rank and rank <= 3 else "under More" if rank else ""] += 1
        print(f"  {kind}{f' (rank {rank})' if rank else ''}: {name} -> {cat}")
    for (kind, where), n in sorted(kinds.items()):
        print(f"  {n:3}  {kind} {where}".rstrip())
    own = {name: name_key(cat) for name, cat, _ in filed}
    print("\nPolicies against this grouping (pairs of documents; development data, not accuracy)")
    policies = {label: {name: pick(s) for name, _, s in filed} for label, pick in POLICIES.items()}
    policies["any shared suggested name (a bound, not a policy)"] = shared_names(filed)
    for label, policy in policies.items():
        groups = Counter(g for g in policy.values() if g)
        c = compare(own, policy)
        share = lambda part, whole: f"{c[part]} of {c[whole]}" if c[whole] else "none to judge"
        print(f"  {label}: {len(groups)} groups, {sum(v is None for v in policy.values())} documents left pending\n"
              f"      over-merging: {c['over-merged']} pairs put together that the owner keeps apart"
              f" (pairs it puts together that the owner also does: {share('both together', 'policy together')})\n"
              f"      fragmentation: {c['fragmented: placed apart']} pairs placed apart and"
              f" {c['fragmented: left pending']} left pending, of the owner's {c['owner together']} pairs"
              f" (kept together: {share('both together', 'owner together')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
