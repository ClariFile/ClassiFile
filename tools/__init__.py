"""Development tools. None of them reads data/final-eval/ (the held-out final evaluation, decision record B4)."""
import sys
from pathlib import Path

FINAL_EVAL = Path(__file__).resolve().parent.parent / "data" / "final-eval"


def refuse_final_eval(path):
    """Exit if path is the held-out folder, inside it, or a parent a recursive scan would reach it from."""
    p = Path(path).resolve()
    if p.is_relative_to(FINAL_EVAL) or FINAL_EVAL.is_relative_to(p):
        sys.exit("Refusing: data/final-eval is held out for the final evaluation and is not read until approved.")
