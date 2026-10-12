import csv

import pytest

from tools import inventory, split
from conftest import EXPECT, SAMPLE  # noqa: E402


def test_inventory_is_read_only_and_never_overwrites(samples, tmp_path):
    (samples / "sub").mkdir()
    (samples / "sub" / "dup.pdf").write_bytes((samples / SAMPLE["S2"]).read_bytes())
    (samples / "notes.txt").write_text("x")
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in samples.rglob("*")}

    out = tmp_path / "out" / "inv.csv"
    inventory.main([str(samples), "--out", str(out)])
    assert {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in samples.rglob("*")} == before

    with open(out, newline="", encoding="utf-8-sig") as f:
        rows = {r["relative_path"]: r for r in csv.DictReader(f)}
    assert list(next(iter(rows.values()))) == inventory.COLUMNS
    assert rows[SAMPLE["S2"]]["pages"] == "17"
    assert rows[SAMPLE["S4"]]["pages"] == "25"
    assert rows["notes.txt"]["pages"] == ""
    assert rows[SAMPLE["S2"]]["exact_dup_group"] == rows["sub/dup.pdf"]["exact_dup_group"] != ""
    assert rows[SAMPLE["S1"]]["exact_dup_group"] == ""
    assert rows[SAMPLE["S2"]]["near_dup_hint"] == ""  # identical bytes are not "near" duplicates

    with pytest.raises(SystemExit):  # existing output is never overwritten
        inventory.main([str(samples), "--out", str(out)])
    with pytest.raises(SystemExit):  # never writes into the scanned folder
        inventory.main([str(samples), "--out", str(samples / "inv.csv")])
    assert not (samples / "inv.csv").exists()


def _rows(n_families, labels=("A", "B")):
    return [
        {"relative_path": f"f{i}-{j}.pdf", "sha256": f"h{i}-{j}", "family_id": f"F{i}",
         "primary_label": labels[i % len(labels)]}
        for i in range(n_families) for j in range(2)
    ]


def test_split_keeps_families_whole_and_is_deterministic():
    rows = _rows(20)
    a = split.assign(rows, (0.6, 0.2, 0.2), seed=1)
    assert a == split.assign(rows, (0.6, 0.2, 0.2), seed=1)
    assert set(a) == {r["family_id"] for r in rows}
    counts = {s: list(a.values()).count(s) for s in split.SPLITS}
    assert counts == {"development": 12, "validation": 4, "final_evaluation": 4}
    for label in "AB":  # each label reaches every split
        assert {a[r["family_id"]] for r in rows if r["primary_label"] == label} == set(split.SPLITS)


@pytest.mark.parametrize("mutate", [
    lambda rows: rows[0].update(family_id=""),
    lambda rows: rows[0].update(sha256=rows[2]["sha256"]),  # same bytes in two families
])
def test_split_refuses_bad_inventory(mutate):
    rows = _rows(5)
    mutate(rows)
    with pytest.raises(split.SplitError):
        split.assign(rows, (0.6, 0.2, 0.2))


def test_split_cli_never_modifies_inventory(tmp_path):
    inv = tmp_path / "inv.csv"
    with open(inv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["relative_path", "sha256", "family_id", "primary_label"])
        w.writeheader()
        w.writerows(_rows(6))
    before = inv.read_bytes()
    out = tmp_path / "splits.csv"
    split.main([str(inv), "--dev", ".5", "--val", ".25", "--final", ".25", "--out", str(out)])
    assert inv.read_bytes() == before
    with open(out, newline="", encoding="utf-8-sig") as f:
        assert len(list(csv.DictReader(f))) == 12
    with pytest.raises(SystemExit):
        split.main([str(inv), "--dev", ".5", "--val", ".25", "--final", ".25", "--out", str(out)])


@pytest.mark.ocr
def test_page_labels_make_and_check(samples, tmp_path):
    from tools import page_labels

    out = tmp_path / "labels.csv"
    page_labels.main(["make", str(samples), "--out", str(out)])
    with pytest.raises(SystemExit):
        page_labels.main(["make", str(samples), "--out", str(out)])  # never overwrites
    rows = page_labels.read_rows(out)
    assert set(rows[0]) == set(page_labels.COLUMNS)
    l2 = [r for r in rows if r["file"] == SAMPLE["S4"]]
    assert len(l2) == 25 and l2[7]["suspected_unread"] == "1" and l2[7]["ocr_status"] == "done"
    for r in rows:  # "no" filled automatically exactly where nothing non-repeated is pictured
        assert (r["label_source"] == "auto") == (r["nonrepeated_image_area"] in ("0", "0.0"))
        assert r["unread_content"] == ("no" if r["label_source"] == "auto" else "")
    # The user answers: pages 8 and 20 yes (both caught by the E8 rule); a skip, then a changed answer.
    assert l2[7]["label_source"] == "" and l2[19]["label_source"] == ""
    for unit, answer in (("8", "yes"), ("20", "skip"), ("20", "no"), ("20", "yes")):
        page_labels.append_answer(out, SAMPLE["S4"], unit, answer)
    result = page_labels.check(page_labels.merged(rows, page_labels.read_answers(out)))
    assert (result["user_labelled"], result["caught_by_rule"], result["missed_by_rule"]) == (2, 2, 0)
    assert result["auto_labelled_no"] == sum(r["label_source"] == "auto" for r in rows)
    assert result["auto_labelled_but_flagged"] == 0 and result["caught_and_ocr_found_text"] == 2


def test_tools_refuse_final_eval(tmp_path, monkeypatch):
    import tools
    from tools import inventory, page_labels

    held_out = tmp_path / "data" / "final-eval"
    held_out.mkdir(parents=True)
    monkeypatch.setattr(tools, "FINAL_EVAL", held_out)
    for args in (["make", str(held_out)], ["make", str(tmp_path / "data")], ["check", str(held_out / "x.csv")]):
        with pytest.raises(SystemExit, match="held out"):
            page_labels.main(args + (["--out", str(tmp_path / "o.csv")] if args[0] == "make" else []))
    with pytest.raises(SystemExit, match="held out"):
        inventory.main([str(held_out), "--out", str(tmp_path / "inv.csv")])


def test_audit_terms_matching(tmp_path):
    from tools import audit_terms
    terms = tmp_path / "terms.txt"
    terms.write_text("# comment\nSecret Title\nre:AB-[0-9]+\n\n", encoding="utf-8")
    patterns = audit_terms.load_terms(terms)
    assert [label for label, _ in patterns] == ["Secret Title", "re:AB-[0-9]+"]
    assert audit_terms.hits("a secret title here", patterns) == ["Secret Title"]   # case-insensitive
    assert audit_terms.hits("code AB-12", patterns) == ["re:AB-[0-9]+"]
    assert audit_terms.hits("nothing to see", patterns) == []


def test_name_stats_scores_top_names_against_a_saved_review(tmp_path):
    from classifile.reader import DocumentRecord
    from tools import name_stats

    rec = DocumentRecord(format="pdf", unit="page", unit_count=3, metadata={}, template_lines=[], recurring_lines=[],
                         running_lines=[],
                         first_page_lines=["Signal Representation", "Sampling Theorem", "Fourier Series"])
    good, bad = tmp_path / "good.csv", tmp_path / "bad.csv"
    good.write_text("file,name,kind\nfolder/x.pdf,signal representation,good\n", encoding="utf-8-sig")
    bad.write_text("file,rank,name,reason,type\nx.pdf,2,Sampling Theorem,on the cover,subtopic\n", encoding="utf-8-sig")
    c = name_stats.score([("x.pdf", rec)], name_stats.judged(good), name_stats.judged(bad))
    assert c["files with a good name first"] == c["top-3 names: good"] == 1
    assert c["top-3 names: not good"] == c["top-3 names: never judged"] == 1


def test_grouping_names_how_a_document_was_filed_and_compares_pairs():
    from tools import grouping

    ev = lambda src: [{"source": src, "pages": [1]}]
    suggestions = [{"name": "Signal Processing", "evidence": ev("first_page"), "demoted": None},
                   {"name": "Dr. Example", "evidence": ev("first_page"), "demoted": "person"},
                   {"name": "Sampling Theorems", "evidence": ev("recurring"), "demoted": None}]
    assert grouping.how_filed("signal  processing", suggestions) == ("as shown", 1)
    assert grouping.how_filed("Sampling theorem", suggestions) == ("near form", 2)   # shown before the person's name
    assert grouping.how_filed("Sampling", suggestions) == ("part of a suggestion", 2)
    assert grouping.how_filed("Filter Design", suggestions) == ("typed", None)
    assert grouping.POLICIES["repeated line"](suggestions) == "sampling theorems"
    assert grouping.POLICIES["file name"](suggestions) is None
    own = {"a": 1, "b": 1, "c": 2, "d": 2}
    c = grouping.compare(own, {"a": "x", "b": "y", "c": "x", "d": None})
    assert (c["owner together"], c["over-merged"]) == (2, 1)                        # a with c
    assert (c["fragmented: placed apart"], c["fragmented: left pending"]) == (1, 1)  # a|b apart; d pending
