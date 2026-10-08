"""Name-suggestion checks on development files (counts only; never prints names or document text).

Usage:
  python -m tools.name_stats read <folder>... --cache <file.pkl>   read copies once (OCR on) and cache the records
  python -m tools.name_stats count --cache <file.pkl>               count problems in each file's top three names

The cache holds extracted text: keep it in an ignored folder such as data\\ or test-output\\. It is a pickle
written by this tool and only ever read back by it; never point --cache at a file from anywhere else.
"""
import argparse
import pickle
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

from classifile.analysis.candidates import analyze, is_organisation_line, top_names
from classifile.reader import READERS, read_document
from tools import refuse_final_eval

HONORIFIC = re.compile(r"^(dr|prof|professor|mr|mrs|ms|miss|daw|u|sir|madam)\.?\s", re.I)
INSTANCE_WORD = re.compile(r"\b(lecture|chapter|week|lab|unit|part)\b\W*\d", re.I)
GENERIC = {"outline", "contents", "table of contents", "introduction", "summary", "conclusion", "conclusions",
           "references", "exercises", "exercise", "quiz", "quizzes", "questions", "answers", "agenda", "objectives"}


def unbalanced(name):
    pairs = (("(", ")"), ("[", "]"), ("{", "}"))
    return any(name.count(a) != name.count(b) for a, b in pairs) or name.count('"') % 2 == 1


def problems(name, author):
    p = []
    if HONORIFIC.match(name) or (author and author.casefold() in name.casefold()):
        p.append("person")
    if unbalanced(name):
        p.append("unbalanced brackets or quotes")
    if INSTANCE_WORD.search(name):
        p.append("instance word with a number")
    if name.strip(" .:").casefold() in GENERIC:
        p.append("generic section word")
    if is_organisation_line(name):
        p.append("institution line")
    return p


def count(records):
    c = Counter()
    for file_name, rec in records:
        top = top_names(analyze(rec, file_name).suggestions) if rec else []
        c["files"] += 1
        c["files with suggestions"] += bool(top)
        author = str(rec.metadata.get("author") or "").strip() if rec else ""
        bad_file = False
        for s in top:
            for kind in problems(s.name, author):
                c[f"top-3 names: {kind}"] += 1
                bad_file = True
        c["files with any problem in the top three"] += bad_file
        c["top-3 names"] += len(top)
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    rd = sub.add_parser("read")
    rd.add_argument("folders", nargs="+")
    rd.add_argument("--cache", type=Path, required=True)
    ct = sub.add_parser("count")
    ct.add_argument("--cache", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "read":
        records = []
        with tempfile.TemporaryDirectory() as tmp:
            for folder in a.folders:
                refuse_final_eval(folder)
            files = [p for f in a.folders for p in sorted(Path(f).rglob("*")) if p.suffix.lower() in READERS]
            for i, src in enumerate(files):
                copy = Path(tmp) / f"{i:04d}{src.suffix.lower()}"
                shutil.copyfile(src, copy)
                records.append((src.name, read_document(copy).record))
        a.cache.parent.mkdir(parents=True, exist_ok=True)
        a.cache.write_bytes(pickle.dumps(records))
        print(f"{len(records)} records cached")
    else:
        for k, v in sorted(count(pickle.loads(a.cache.read_bytes())).items()):
            print(f"{k}: {v}")


if __name__ == "__main__":
    sys.exit(main())
