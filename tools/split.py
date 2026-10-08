"""Assign whole document families to development / validation / final evaluation.

Usage: python -m tools.split data/inventory.csv --dev 0.6 --val 0.2 --final 0.2 [--seed N] [--out data/splits.csv]

The proportions are required on purpose: agree them with the project owner before running on real data.
The inventory is never modified; the splits CSV is created exclusively and never overwritten.
"""
import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

SPLITS = ("development", "validation", "final_evaluation")
DEFAULT_SEED = 20261007
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "splits.csv"
OUT_COLUMNS = ["relative_path", "sha256", "family_id", "primary_label", "split"]


class SplitError(ValueError):
    pass


def assign(rows, proportions, seed=DEFAULT_SEED):
    """Return {family_id: split}. Raises SplitError on invalid input."""
    if len(proportions) != 3 or any(p < 0 for p in proportions) or abs(sum(proportions) - 1) > 1e-9:
        raise SplitError("Proportions must be three non-negative numbers summing to 1.")
    missing = [r["relative_path"] for r in rows if not r.get("family_id", "").strip()]
    if missing:
        raise SplitError(f"{len(missing)} row(s) lack a family_id, e.g. {missing[0]}")

    families = defaultdict(list)
    for r in rows:
        families[r["family_id"].strip()].append(r)

    # Identical bytes in two families would leak the same content across splits.
    by_hash = defaultdict(set)
    for fam, members in families.items():
        for r in members:
            by_hash[r["sha256"]].add(fam)
    leaks = sorted(sorted(f) for f in by_hash.values() if len(f) > 1)
    if leaks:
        raise SplitError(f"Identical files belong to different families: {leaks[0]}")

    # Stratum = the family's most common primary_label (blank is its own stratum).
    strata = defaultdict(list)
    for fam, members in families.items():
        labels = Counter(r.get("primary_label", "").strip() for r in members)
        label = sorted(labels.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        strata[label].append(fam)

    rng = random.Random(seed)
    order = []
    for label in sorted(strata):
        fams = sorted(strata[label])
        rng.shuffle(fams)
        order += fams

    # ponytail: sequential largest-deficit apportionment over families taken stratum by stratum;
    # approximate stratification, fine for tens of families. Upgrade to per-stratum quotas if strata get large.
    counts = dict.fromkeys(SPLITS, 0)
    result = {}
    for i, fam in enumerate(order, 1):
        split = max(SPLITS, key=lambda s: proportions[SPLITS.index(s)] * i - counts[s])
        counts[split] += 1
        result[fam] = split
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("inventory", type=Path)
    ap.add_argument("--dev", type=float, required=True)
    ap.add_argument("--val", type=float, required=True)
    ap.add_argument("--final", type=float, required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    if a.out.exists():
        sys.exit(f"Refusing to overwrite existing file: {a.out}. Choose another --out.")
    with open(a.inventory, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    try:
        fam_split = assign(rows, (a.dev, a.val, a.final), a.seed)
    except SplitError as e:
        sys.exit(f"Refusing: {e}")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "x", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "split": fam_split[r["family_id"].strip()]})
    summary = Counter(fam_split.values())
    print(f"seed={a.seed} families: " + ", ".join(f"{s}={summary[s]}" for s in SPLITS) + f" -> {a.out}")


if __name__ == "__main__":
    main()
