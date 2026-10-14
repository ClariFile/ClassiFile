"""Grouping new subjects, tried on development data before it goes into the app (decision record B2, since 2.3).

Usage: python -m tools.group_eval [--families CSV...] [--level X] [--compare X...] [--out FILE]

Each of the owner's categories is held out in turn, as if the app had never seen that subject. The documents
that would then be waiting with no good match are: those of the held-out category that the remaining categories
do not match, and, as company, every other document that its own category does not match when its family is
held out too. Only these unmatched documents are grouped (classifile.matching.similar_groups); a group needs at
least two. For each held-out category the report says whether its documents come back as one group:
  kept together   all its unmatched documents are in one group, with no others;
  split apart     they are in several groups, or some are left alone;
  mixed           a group holds its documents together with documents of other categories;
  nothing to group  fewer than two of its documents are unmatched (the rest were taken for existing categories).
It then shows the groups, with their shared key words and the names suggested for their documents.
--compare prints the counts for several levels of similarity instead; --out also saves the report (created new).
--folders replays automatic new folders (B2, record 2.6) instead: every group at classifile.matching.FOLDER_LEVEL
becomes a folder, named by classifile.matching.group_name. Per held-out category it counts the folders created,
folders mixing subjects, folders made only of documents of a category the app already has (a second folder for a
known subject), and whether the held-out subject comes back in one folder or is split over several.
The output shows category names, suggested names and words from documents: keep it out of tracked files.
Counts describe development data. data/validation and data/final-eval are never read.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from classifile.catalog.db import default_data_dir
from classifile.analysis.candidates import name_key
from classifile.matching import FOLDER_LEVEL, FOLDER_MIN, GOOD_MATCH, GROUP_LEVEL, group_name, Centroids, fit_idf, lead, shared_words, similar_groups, vector
from tools.match_eval import csv_families, families, load


def unmatched(docs, train, test):
    """The documents of `test` (indexes) that no category matches well, for a model fitted on `train`."""
    idf = fit_idf([docs[i]["terms"] for i in train])
    model = Centroids([vector(docs[i]["terms"], idf) for i in train], [docs[i]["category"] for i in train])
    out = []
    for i in test:
        scores = model.scores(vector(docs[i]["terms"], idf))
        if lead(sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))) < GOOD_MATCH:
            out.append(i)
    return out


def waiting_without(docs, fam, category):
    """(its own unmatched documents, the other unmatched documents) when `category` is unknown to the app."""
    rest = [i for i, d in enumerate(docs) if d["category"] != category]
    own = unmatched(docs, rest, [i for i, d in enumerate(docs) if d["category"] == category])
    others = []
    for held in sorted({fam[i] for i in rest}):
        others += unmatched(docs, [i for i in rest if fam[i] != held], [i for i in rest if fam[i] == held])
    return own, others


def outcome(own, groups):
    """(verdict, [(own documents, other documents) per group that holds any of its own], left alone)."""
    mine = [(len([i for i in g if i in own]), len([i for i in g if i not in own])) for g in groups]
    mine = [m for m in mine if m[0]]
    alone = len(own) - sum(m[0] for m in mine)
    if len(own) < 2:
        return "nothing to group", mine, alone
    if any(others for _, others in mine):
        return "mixed", mine, alone
    return ("kept together" if len(mine) == 1 and not alone else "split apart"), mine, alone


def evaluate(docs, fam, level):
    """One row per category: its documents, the unmatched ones, the verdict and the groups formed."""
    idf = fit_idf([d["terms"] for d in docs])       # as in the app: every stored document counts for word weights
    vectors = [vector(d["terms"], idf) for d in docs]
    rows = []
    for category, n in Counter(d["category"] for d in docs).most_common():
        own, others = waiting_without(docs, fam, category)
        groups = similar_groups({i: vectors[i] for i in own + others}, level)
        verdict, mine, alone = outcome(own, groups)
        rows.append({"category": category, "documents": n, "unmatched": len(own), "company": len(others),
                     "verdict": verdict, "mine": mine, "alone": alone,
                     "groups": [{"own": [i for i in g if i in own], "others": [i for i in g if i not in own],
                                 "words": shared_words([vectors[i] for i in g])} for g in groups]})
    return rows


def report(docs, rows, level, out=print):
    out(f"Grouping at a similarity of {level}: {len(docs)} development documents, each category held out in turn")
    out("\nPer held-out category: documents / of them unmatched (the rest were taken for existing categories) -> result")
    for r in rows:
        shape = ", ".join(f"{a} together" + (f" with {b} from other categories" if b else "") for a, b in r["mine"])
        shape += (", " if shape else "") + f"{r['alone']} left alone" if r["alone"] else ""
        out(f"  {r['documents']:3} / {r['unmatched']:2}  {r['category'][:38]:38} {r['verdict']}" + (f": {shape}" if shape else ""))
    counts = Counter(r["verdict"] for r in rows)
    out("  " + "; ".join(f"{n} {v}" for v, n in counts.most_common()))
    out("\nThe groups (held-out category: its documents in the group, documents of other categories, key words, names)")
    for r in rows:
        for g in r["groups"]:
            if not g["own"]:
                continue
            members = g["own"] + g["others"]
            names = Counter(n for i in members for n in docs[i]["names"][:1])
            other = Counter(docs[i]["category"] for i in g["others"])
            out(f"  {r['category']}: {len(g['own'])} of its {r['unmatched']} unmatched"
                + (f" + {', '.join(f'{n} {c}' for c, n in other.items())}" if other else ""))
            out(f"      key words: {', '.join(g['words']) or '(none shared)'}")
            out(f"      suggested names: {'; '.join(n for n, _ in names.most_common(3)) or '(none)'}")


def replay(docs, fam, level=FOLDER_LEVEL, least=FOLDER_MIN):
    """Automatic new folders, each category held out in turn: one row per category with the folders the app would
    create, each {"own", "others", "kind", "name", "named"}. kind: "new subject" (only the held-out category's
    documents), "mixed" (several categories), "known subject" (only documents of one category the app has).
    named: "repeated" (suggested for several of its documents), "best" or None (no free name: stays a question).
    least: the fewest documents a folder is made for (smaller groups stay questions)."""
    rows = []
    for r in evaluate(docs, fam, level):
        taken = {name_key(d["category"]) for d in docs if d["category"] != r["category"]}
        folders = []
        for g in r["groups"]:
            members = g["own"] + g["others"]
            if len(members) < least:
                continue                        # a smaller group stays a question for the user
            cats = {docs[i]["category"] for i in members}
            kind = "mixed" if len(cats) > 1 else "new subject" if g["own"] else "known subject"
            name = group_name([docs[i]["suggested"] for i in members], taken)
            repeated = name and sum(name_key(name) in {name_key(s["name"]) for s in docs[i]["suggested"]}
                                    for i in members) > 1
            folders.append(g | {"kind": kind, "name": name, "named": name and ("repeated" if repeated else "best")})
        rows.append(r | {"folders": folders})
    return rows


def report_replay(docs, rows, level, out=print, least=FOLDER_MIN):
    out(f"Automatic new folders at a similarity of {level}, groups of at least {least}: {len(docs)} development documents, "
        f"{len(rows)} categories, each held out in turn")
    out("\nPer held-out category: documents / unmatched | folders: new subject, mixed, known subject | "
        "the held-out subject comes back as")
    known_groups = set()
    for r in rows:
        kinds = Counter(f["kind"] for f in r["folders"])
        own = [f for f in r["folders"] if f["own"]]
        shape = ("nothing to group" if r["unmatched"] < 2 else "no folder" if not own
                 else "one folder" if len(own) == 1 else f"split over {len(own)} folders")
        alone = r["unmatched"] - sum(len(f["own"]) for f in own)
        known_groups |= {frozenset(f["others"]) for f in r["folders"] if f["kind"] == "known subject"}
        out(f"  {r['documents']:3} / {r['unmatched']:2}  {r['category'][:34]:34} | {kinds['new subject']}, "
            f"{kinds['mixed']}, {kinds['known subject']} | {shape}" + (f", {alone} left waiting" if alone and own else ""))
    allf = [f for r in rows for f in r["folders"]]
    kinds = Counter(f["kind"] for f in allf)
    own = [len([f for f in r["folders"] if f["own"]]) for r in rows]
    out(f"\nTotal over the {len(rows)} rounds: {len(allf)} folders created: {kinds['new subject']} of the held-out "
        f"subject only, {kinds['mixed']} mixing subjects, {kinds['known subject']} of a subject the app already has "
        f"({len(known_groups)} distinct; the same documents are unmatched in most rounds)")
    out(f"Held-out subjects: {sum(n == 1 for n in own)} back as one folder, {sum(n > 1 for n in own)} split over "
        f"several, {sum(n == 0 and r['unmatched'] >= 2 for n, r in zip(own, rows))} with no folder, "
        f"{sum(r['unmatched'] < 2 for r in rows)} with fewer than two unmatched documents")
    named = Counter(f["named"] for f in allf)
    same = sum(bool(f["name"]) and name_key(f["name"]) == name_key(r["category"]) for r in rows for f in r["folders"] if f["kind"] == "new subject")
    out(f"Names: {named['repeated']} repeated across the folder's documents, {named['best']} the best suggestion, "
        f"{named[None]} with no free name (would stay a question); {same} of the {kinds['new subject']} new-subject "
        f"folders named as the owner's folder")
    out("\nThe folders (held-out category: kind, documents, name, key words)")
    for r in rows:
        for f in r["folders"]:
            other = Counter(docs[i]["category"] for i in f["others"])
            out(f"  {r['category'][:30]}: {f['kind']}, {len(f['own'])} own"
                + (f" + {', '.join(f'{n} {c}' for c, n in other.items())}" if other else "")
                + f" | {f['name'] or '(no free name)'} ({f['named']}) | {', '.join(f['words']) or '(none shared)'}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--families", nargs="*", default=[], type=Path, help="CSVs with sha256 and family_id")
    ap.add_argument("--level", type=float, default=GROUP_LEVEL)
    ap.add_argument("--compare", nargs="*", type=float, help="print the counts at these levels instead")
    ap.add_argument("--folders", action="store_true", help="replay automatic new folders instead (record 2.6)")
    ap.add_argument("--least", type=int, default=FOLDER_MIN, help="with --folders: the fewest documents per folder")
    ap.add_argument("--out", type=Path, help="also save the report here (never overwritten)")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    a = ap.parse_args(argv)
    if a.out and a.out.exists():
        sys.exit(f"Refusing to overwrite existing file: {a.out}")
    docs = load(a.catalog)
    fam = families(docs, csv_families(a.families))
    for level in a.compare or ():
        rows = evaluate(docs, fam, level)
        counts = Counter(r["verdict"] for r in rows)
        grouped = sum(m[0] for r in rows for m in r["mine"])
        strangers = sum(m[1] for r in rows for m in r["mine"])
        print(f"level {level}: " + "; ".join(f"{n} {v}" for v, n in counts.most_common())
              + f" | own documents grouped {grouped} of {sum(r['unmatched'] for r in rows)} unmatched,"
              f" with {strangers} documents of other categories in their groups")
    if a.compare:
        return 0
    lines = []
    if a.folders:
        level = FOLDER_LEVEL if a.level == GROUP_LEVEL else a.level
        report_replay(docs, replay(docs, fam, level, a.least), level, lines.append, a.least)
    else:
        report(docs, evaluate(docs, fam, a.level), a.level, lines.append)
    print("\n".join(lines))
    if a.out:
        with open(a.out, "x", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
