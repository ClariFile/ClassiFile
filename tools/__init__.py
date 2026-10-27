"""Development tools. None of them reads the held-out folders (data/final-eval, data/validation, data/final-check;
decision record B4) except the owner-authorized one-shot measurements (tools.final_eval, once, with the frozen
version, record 2.10; tools.match_validation and accuracy_round --validation, on validation, once); the inventory
labelling window shows their files to the owner when a split is named (tools.label_inventory)."""
import os
import sqlite3
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FINAL_EVAL = DATA / "final-eval"


def _canonical(path):
    """The path as the file system knows it: absolute, links and junctions resolved, case folded on Windows."""
    return Path(os.path.normcase(os.path.realpath(path)))


def held_out(path, allow=()):
    """The name of the held-out folder path is, is inside, or is a parent of (a recursive scan would reach it),
    else None. allow: names an owner-authorized measurement may read (e.g. "validation")."""
    p = _canonical(path)
    for name, folder in {"final-eval": FINAL_EVAL, "validation": DATA / "validation",
                         "final-check": DATA / "final-check"}.items():
        f = _canonical(folder)
        if name not in allow and (p.is_relative_to(f) or f.is_relative_to(p)):
            return name
    return None


def refuse_final_eval(path, allow=()):
    """Exit if path is a held-out folder (final-eval, validation, final-check), inside one, or a parent a recursive
    scan would reach one from. The one guard for every tool (designImp3 ticket 9)."""
    name = held_out(path, allow)
    if name:
        sys.exit(f"Refusing: data/{name} is held out (decision record B4) and is not read by this tool.")


def catalog_snapshot(catalog_path, dest):
    """A consistent copy of a catalog that may be open in the app, in dest (a new file in a folder of the caller's
    own, e.g. a TemporaryDirectory): SQLite's backup API over a read-only connection. Unlike a byte copy it never
    catches a write half-done, and the catalog itself is never written."""
    src = sqlite3.connect(Path(catalog_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    return Path(dest)


def once(record, out, measure, already):
    """A held-out measurement that runs once, whatever the report is called. record: its one fixed file. It is
    reserved before any document is read, so a run that stopped part-way also counts as the run. Later runs
    read nothing: with an out path that is free, they save a copy of the recorded result there (an export);
    otherwise they exit with `already`. Returns the result."""
    import json
    from datetime import datetime, timezone

    record = Path(record)
    if record.exists():
        saved = json.loads(record.read_text(encoding="utf-8"))
        if saved.get("reserved"):
            sys.exit(f"{already} It was started on {saved['reserved']} and did not finish; it is not run again.")
        if out is None or Path(out).exists() or Path(out).resolve() == record.resolve():
            sys.exit(f"{already} ({record}) Print it with --report; it is not run twice.")
        with open(out, "x", encoding="utf-8") as f:     # an export of the recorded result: nothing is measured
            json.dump(saved, f)
        print(f"Saved a copy of the recorded result to {out}; nothing was measured again.")
        return saved
    record.parent.mkdir(parents=True, exist_ok=True)
    with open(record, "x", encoding="utf-8") as f:      # reserved before the first document is read
        json.dump({"reserved": datetime.now(timezone.utc).isoformat(timespec="seconds")}, f)
    saved = measure()
    record.write_text(json.dumps(saved), encoding="utf-8")
    if out is not None and Path(out).resolve() != record.resolve():
        with open(out, "x", encoding="utf-8") as f:
            json.dump(saved, f)
    return saved
