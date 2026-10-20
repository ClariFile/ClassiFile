"""tools.final_eval on made-up documents: counted like tools.evaluate, run once, only with the frozen version."""
import csv
import json

import pytest

from classifile.reader import sha256_file
from test_matching import SUBJECTS, _add, _pdf
from tools import final_eval


def test_final_eval_counts_once_with_the_frozen_version(make_org, tmp_path, capsys):
    org, src = make_org(), tmp_path / "src"
    for subject in ("Algebra", "Networks"):
        for n in range(4):
            _add(org, src, subject, n)
    org.update_matching()
    org.set_auto_folders(True)
    version = org.catalog.latest_matcher()["version"]
    held = tmp_path / "held"
    held.mkdir()
    rows = []
    for subject, ns in (("Algebra", (20, 21)), ("Networks", (20,)), ("Poetry", (30, 31, 32))):
        for n in ns:
            path = held / f"{subject.lower()}-{n}.pdf"
            _pdf(path, SUBJECTS[subject], n)
            rows.append({"sha256": sha256_file(path), "family_id": f"{subject}{n}", "primary_label": subject,
                         "split": "final_evaluation"})
    labels = tmp_path / "splits.csv"
    with open(labels, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    catalog = org.catalog.path
    before = catalog.read_bytes()

    with pytest.raises(SystemExit, match="not the frozen version"):
        final_eval.measure(held, rows, catalog, frozen=version + 1)
    saved = final_eval.measure(held, rows, catalog, frozen=version)
    assert catalog.read_bytes() == before                           # the catalog is never changed
    docs = {d["label"]: d for d in saved["documents"]}
    assert len(saved["documents"]) == 6 and docs["Poetry"]["category"] is None    # a label with no category
    rows_ = final_eval.rows_of(json.loads(json.dumps(saved)))
    s = final_eval.evaluation.summary(rows_, saved["level"][1])
    assert s["known"] == 3 and s["first"] == 3 and s["top3"] == 3
    poetry = [r for r in rows_ if r["category"] == "(new) Poetry"]
    assert not any(final_eval.evaluation.filed(r, saved["level"][1]) for r in poetry)   # never forced in a folder
    made, pending, asked = final_eval.folders(saved, rows_, saved["level"][1])
    assert all(f["kind"] == "new subject" for f in made) and asked <= len(pending)

    out = tmp_path / "result.json"
    args = [str(held), "--labels", str(labels), "--out", str(out), "--catalog", str(catalog)]
    final_eval.FROZEN_VERSION, frozen = version, final_eval.FROZEN_VERSION
    final_eval.RECORD, record = tmp_path / "record.json", final_eval.RECORD     # never the real record
    measure, calls = final_eval.measure, []
    final_eval.measure = lambda *a, **k: calls.append(1) or measure(*a, **k)
    try:
        assert final_eval.main(args) == 0 and out.exists() and final_eval.RECORD.exists()
        with pytest.raises(SystemExit, match="already run"):  # once only
            final_eval.main(args)
        other = tmp_path / "another name.json"                  # another report name: a copy, never a second run
        assert final_eval.main(args[:4] + [str(other)] + args[5:]) == 0
        assert calls == [1] and json.loads(other.read_text(encoding="utf-8")) == json.loads(out.read_text(encoding="utf-8"))
    finally:
        final_eval.FROZEN_VERSION, final_eval.RECORD, final_eval.measure = frozen, record, measure
    capsys.readouterr()
    final_eval.main(["--report", str(out)])
    printed = capsys.readouterr().out
    assert "The owner's category first:" in printed and "<- in use" in printed and "not a promise" in printed
