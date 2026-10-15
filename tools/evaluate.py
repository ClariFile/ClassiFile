"""The one evaluation of matching, as a report (classifile.evaluation; the app's update check measures the same way).

Usage: python -m tools.evaluate [--rules] [--outcomes] [--real-use] [--json FILE] [--catalog FILE]
       python -m tools.evaluate --set-families data\\splits_incoming_2.csv    (close the app first)

Reads a temporary copy of the app's catalog (removed afterwards); nothing in the app or its catalog changes. Each
family of the documents the user filed is held out in turn and a model is trained on the rest, its word weights
fitted inside the fold. There is no random step: the same catalog and code give the same report.
Prints: what was counted and what was left out, the model in use and the thresholds; the user's category first and
in the first three, overall and per category; automatic filing at every level (right / wrong / waiting); new
subjects (each category held out whole) wrongly filed; the "Check these" list. Each share has a simple 95% range.
--rules adds the safer filing rules tried against the one in use (a minimum similarity to the best folder; the
best folder among the document's nearest neighbours), at the level in use and at Balanced. Nothing is adopted here.
--outcomes adds, at every level: true positives (filed by itself, right), false positives (filed by itself, wrong;
new subjects forced into an existing folder counted apart), missed automation (it waited, its first choice right)
and correct waits, with precision and coverage per category; then each false positive with its likely causes,
each tested on the document itself (OCR text, template text, very little text, shared vocabulary, a broad folder).
--real-use adds every placement the app made by itself in the catalog and what became of it (kept untouched,
"Looks right" or moved), per category and per matching version.
--json saves the rows and the summary (created new, never overwritten).
--set-families records the owner's family ids from inventory or splits CSVs in the catalog itself, for the files the
catalog holds (rows of the final evaluation are skipped unread), so that this report and the app's update check
hold out the same families. It changes nothing else.
The output names categories: keep it out of tracked files. Counts describe the user's development documents; they
are not accuracy estimates. data/validation and data/final-eval are never read.
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
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


# The likely causes of a false positive (--outcomes). Each is a plain rule on the document and the fold that filed
# it, chosen before looking at the documents; a cause names what is likely, never a proof.
LITTLE_TEXT = 150       # words: a document this short gives matching little to go on
BROAD = 0.30            # a folder holding at least this share of the training documents is broad
SHARED_TOP = 0.75       # two folders whose centres are in the top quarter of folder pairs share much vocabulary
STANDING = 3            # a line found in this many documents is template text (headers, logos, cover wording)
OUTCOMES = (("right", "right (true positives)"), ("wrong", "wrong (false positives)"),
            ("missed", "missed automation"), ("wait", "correct waits"))


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
    parts = defaultdict(lambda: ["", "", []])   # document: [native text, OCR text, lines]; in memory, never printed
    for d, text, notes, ocr in cat.all(
            "SELECT s.document_id, u.text, u.notes, u.ocr_text FROM extraction_units u JOIN extractions e ON"
            " e.id = u.extraction_id JOIN snapshots s ON s.id = e.snapshot_id ORDER BY s.document_id, u.unit_index"):
        parts[d][0] += f"\n{text or ''}\n{notes or ''}"
        parts[d][1] += f"\n{ocr or ''}"
        parts[d][2] += [x for t in (text, notes, ocr) if t for x in t.splitlines() if line_key(x)]
    status = Counter(r[0] for r in cat.all("SELECT status FROM documents"))
    machine = cat.one("SELECT COUNT(*) FROM memberships WHERE role = 'primary' AND status = 'active'"
                      " AND provenance = 'machine-assigned'")[0]
    return {"names": names, "rows": rows, "unseen": unseen, "labels": labels, "counts": counts, "groups": groups,
            "level_name": org.auto_level(), "level": org.check_level(), "documents": sum(status.values()),
            "waiting": status.get("needs_decision", 0), "machine": machine, "examples": status.get("example", 0),
            "model": dict(used[0]) | {"bundle_json": None} if used else None,
            "check": evaluation.mismatches(rows), "parts": dict(parts), "real": real_use(cat)}


def line_key(line):
    """A line compared with others: case, spacing and numbers ignored; "" for a line of fewer than two words."""
    key = " ".join(re.sub(r"\d+", "#", line.casefold()).split())
    return key if len(matching.TOKEN.findall(key)) >= 2 else ""


def real_use(cat):
    """Every placement the app made by itself (memberships with their reason, auto_json) and what became of it:
    [{"doc", "category", "version", "new_folder", "at", "result", "now"}]. result: "kept untouched", "Looks right",
    "moved" or "moved after Looks right"; now: the document's category today."""
    out = []
    for m in cat.all("SELECT id, document_id, category_id, auto_json, status, created_at FROM memberships"
                     " WHERE auto_json IS NOT NULL AND role = 'primary' ORDER BY id"):
        auto = json.loads(m["auto_json"])
        looked = bool(cat.one("SELECT COUNT(*) FROM membership_events WHERE membership_id = ? AND event = 'confirmed'",
                              m["id"])[0])
        now = cat.active_primary(m["document_id"])
        result = ("Looks right" if looked else "kept untouched") if m["status"] == "active" else \
            "moved after Looks right" if looked else "moved"
        out.append({"doc": m["document_id"], "category": m["category_id"], "version": auto.get("version"),
                    "new_folder": bool(auto.get("new_folder")), "at": m["created_at"], "result": result,
                    "now": now["category_id"] if now else None})
    return out


def causes(m, d, wrong, exclude, level):
    """The likely causes of one false positive: document d filed by itself in `wrong` by a model trained without
    `exclude` (its family, or its whole category for a new subject). OCR text and template text are tested by
    taking them away: the cause is named only when the document then no longer goes to that folder."""
    labels, counts = m["labels"], m["counts"]
    fold = sorted(x for x in labels if x not in exclude and counts.get(x))
    idf = matching.fit_idf([counts[x] for x in fold])
    model = matching.Centroids([matching.vector(counts[x], idf) for x in fold], [labels[x] for x in fold])

    def still(text):
        x = matching.vector(matching.terms(text), idf)
        ranked = sorted(model.scores(x).items(), key=lambda kv: (-kv[1], kv[0])) if x else []
        return bool(ranked) and ranked[0][0] == wrong and matching.lead(ranked) >= level

    native, ocr, lines = m["parts"].get(d, ("", "", []))
    words, out = sum(counts[d].values()) or 1, []
    ocr_words = sum(matching.terms(ocr).values())
    if ocr_words >= 0.2 * words and not still(native):
        out.append(f"OCR text ({ocr_words / words:.0%} of its words; without them it is not filed there)")
    seen = Counter(line_key(x) for x in lines)
    standing = {k for k in seen if seen[k] >= 2 or m["line_docs"][k] >= STANDING}
    kept = "\n".join(x for x in lines if line_key(x) not in standing)
    share = 1 - sum(matching.terms(kept).values()) / words
    if share >= 0.1 and not still(kept):
        out.append(f"template text (lines repeated on its pages or found in {STANDING}+ documents: {share:.0%} of "
                   "its words; without them it is not filed there)")
    if words < LITTLE_TEXT:
        out.append(f"very little text ({words} words)")
    centre = Counter()
    for x in labels:
        if labels[x] == labels[d] and counts.get(x):
            centre.update(matching.vector(counts[x], idf))
    norm = sum(v * v for v in centre.values()) ** 0.5 or 1
    sim = matching.dot({t: v / norm for t, v in centre.items()}, model.centroids[wrong])
    cs = sorted(model.centroids)
    pairs = sorted(matching.dot(model.centroids[a], model.centroids[b]) for i, a in enumerate(cs) for b in cs[:i])
    if pairs and sim >= pairs[int(SHARED_TOP * (len(pairs) - 1))]:
        out.append(f"shared vocabulary with the folder it went to (their centres at {sim:.2f}, in the top quarter "
                   "of folder pairs)")
    held = sum(labels[x] == wrong for x in fold) / len(fold)
    if held >= BROAD:
        out.append(f"a broad folder (it holds {held:.0%} of the training documents)")
    return out or ["no clear cause found"]


def report_outcomes(m, out=print):
    """--outcomes: true and false positives at every level, per category, then the causes of each false positive."""
    rows, unseen, names, labels, groups = m["rows"], m["unseen"], m["names"], m["labels"], m["groups"]
    m["line_docs"] = Counter(k for d in sorted(m["parts"]) for k in {line_key(x) for x in m["parts"][d][2]})
    first_wrong = {}
    for name, lv in sorted(matching.LEVELS.items(), key=lambda kv: kv[1]):    # Lenient first: ends at the strictest
        got = {r["doc"]: evaluation.outcome(r, lv) for r in rows}
        forced = [r for r in unseen if evaluation.filed(r, lv)]
        n = Counter(got.values())
        mark = " (the level in use)" if lv == m["level"] else ""
        out(f"\nOutcomes at {name} (lead >= {lv}){mark}, all {len(rows)} documents, each family held out")
        out("  " + "; ".join(f"{label} {n[k]}" for k, label in OUTCOMES))
        out(f"  new subjects forced into an existing folder (each category held out whole): {len(forced)} of "
            f"{len(unseen)}, counted apart")
        out(f"  precision (right among those filed): {pct(n['right'], n['right'] + n['wrong'])}")
        out(f"  coverage (right among all documents): {pct(n['right'], len(rows))}")
        out("  category                               docs | right missed waits | wrong: out / in | new subjects in |"
            " precision | coverage")
        into = Counter(r["ranked"][0][0] for r in rows if got[r["doc"]] == "wrong")
        forced_in = Counter(r["ranked"][0][0] for r in forced)
        for c, k in Counter(labels.values()).most_common():
            g = Counter(got[r["doc"]] for r in rows if r["category"] == c)
            filed_in = g["right"] + into[c]
            precision = f"{100 * g['right'] / filed_in:4.0f}%" if filed_in else "   -"
            out(f"  {names.get(c, c)[:38]:38} {k:4} | {g['right']:5} {g['missed']:6} {g['wait']:5} | "
                f"{g['wrong']:5} / {into[c]:2} | {forced_in[c]:15} | {precision:>9} | {100 * g['right'] / k:7.0f}%")
        for r in rows:
            if got[r["doc"]] == "wrong":
                first_wrong[("known", r["doc"])] = (name, lv, r)
        for r in forced:
            first_wrong[("new", r["doc"])] = (name, lv, r)
    out("\nFalse positives and their likely causes (each document once, at the strictest level that files it wrongly)")
    if not first_wrong:
        out("  none")
    tally = Counter()
    for (kind, d), (name, lv, r) in sorted(first_wrong.items(), key=lambda kv: (-kv[1][1], kv[0])):
        exclude = {x for x in labels if (groups[x] == groups[d] if kind == "known" else labels[x] == labels[d])}
        found = causes(m, d, r["ranked"][0][0], exclude, lv)
        tally.update(f.split(" (")[0] for f in found)
        out(f"  {'new subject' if kind == 'new' else 'known subject'}  {d[:8]}  belongs to "
            f"{names.get(r['category'], '?')}, filed in {names.get(r['ranked'][0][0], '?')} from {name}: "
            + "; ".join(found))
    if first_wrong:
        out(f"  Causes over these {len(first_wrong)} (a document may have several): "
            + "; ".join(f"{k} {n}" for k, n in tally.most_common()))


def report_real_use(m, out=print):
    """--real-use: every automatic placement in the catalog and what became of it."""
    real, names = m["real"], m["names"]
    results = ("kept untouched", "Looks right", "moved", "moved after Looks right")
    out(f"\nAutomatic placements in real use: {len(real)} (from the catalog; what the user did with each)")
    if not real:
        return
    out("  " + "; ".join(f"{k} {sum(x['result'] == k for x in real)}" for k in results))
    for key, title in (("category", "folder it was placed in"), ("version", "matching version")):
        out(f"  per {title}: " + " | ".join(results))
        for v in sorted({x[key] for x in real}, key=str):
            mine = [x for x in real if x[key] == v]
            label = names.get(v, v) if key == "category" else f"version {v}"
            out(f"    {str(label)[:38]:38} {len(mine):3}: "
                + " | ".join(str(sum(x["result"] == k for x in mine)) for k in results))
    for x in real:
        if x["result"].startswith("moved"):
            out(f"  moved: {x['doc'][:8]} placed in {names.get(x['category'], '?')} by version {x['version']}"
                f"{' (new folder)' if x['new_folder'] else ''}, now in {names.get(x['now'], 'no category')}")


def report(m, rules=False, out=print, outcomes=False, real=False):
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
    examples = m.get("examples", 0)
    out(f"  {m['documents']} documents in the catalog: {len(labels)} filed by the user"
        + (f" or kept as examples from the user's folders ({examples} of them)" if examples else "")
        + " (the truth and the training),"
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
    if outcomes:
        report_outcomes(m, out)
    if real:
        report_real_use(m, out)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", action="store_true", help="also try the safer filing rules")
    ap.add_argument("--outcomes", action="store_true", help="true and false positives per level, with causes")
    ap.add_argument("--real-use", action="store_true", help="what became of the app's own placements")
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
    s = report(m, a.rules, outcomes=a.outcomes, real=a.real_use)
    if a.json:
        with open(a.json, "x", encoding="utf-8") as f:
            json.dump({"summary": s, "rows": m["rows"], "new subjects": m["unseen"], "check": m["check"]}, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
