"""Development tools. None of them reads data/final-eval/ (the held-out final evaluation, decision record B4)
except tools.final_eval, once, with the frozen version (record 2.10); the inventory labelling window shows its
files to the owner when a split is named (tools.label_inventory)."""
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FINAL_EVAL = DATA / "final-eval"


def refuse_final_eval(path):
    """Exit if path is the held-out folder, inside it, or a parent a recursive scan would reach it from."""
    p = Path(path).resolve()
    if p.is_relative_to(FINAL_EVAL) or FINAL_EVAL.is_relative_to(p):
        sys.exit("Refusing: data/final-eval is held out for the final evaluation and is not read until approved.")


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
