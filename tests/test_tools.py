import csv

import pytest

from tools import inventory, split
from conftest import SAMPLE  # noqa: E402


def test_inventory_is_read_only_and_never_overwrites(pdfs, tmp_path):
    (pdfs / "sub").mkdir()
    (pdfs / "sub" / "dup.pdf").write_bytes((pdfs / "S2.pdf").read_bytes())
    (pdfs / "notes.txt").write_text("x")
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in pdfs.rglob("*")}

    out = tmp_path / "out" / "inv.csv"
    inventory.main([str(pdfs), "--out", str(out)])
    assert {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in pdfs.rglob("*")} == before

    with open(out, newline="", encoding="utf-8-sig") as f:
        rows = {r["relative_path"]: r for r in csv.DictReader(f)}
    assert list(next(iter(rows.values()))) == inventory.COLUMNS
    assert rows["S2.pdf"]["pages"] == "3"
    assert rows["S4.pdf"]["pages"] == "3"
    assert rows["notes.txt"]["pages"] == ""
    assert rows["S2.pdf"]["exact_dup_group"] == rows["sub/dup.pdf"]["exact_dup_group"] != ""
    assert rows["S1.pdf"]["exact_dup_group"] == ""
    assert rows["S2.pdf"]["near_dup_hint"] == ""  # identical bytes are not "near" duplicates

    with pytest.raises(SystemExit):  # existing output is never overwritten
        inventory.main([str(pdfs), "--out", str(out)])
    with pytest.raises(SystemExit):  # never writes into the scanned folder
        inventory.main([str(pdfs), "--out", str(pdfs / "inv.csv")])
    assert not (pdfs / "inv.csv").exists()


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


def test_inventory_prefills_families_as_suggestions(tmp_path):
    import pymupdf

    def pdf(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 100), text)
        doc.save(path)
        doc.close()

    new, dev = tmp_path / "new", tmp_path / "dev"
    pdf(new / "Waves.pdf", "waves")
    (new / "Waves (2).pdf").write_bytes((new / "Waves.pdf").read_bytes())       # the same bytes
    pdf(new / "Physics" / "Optics notes.pdf", "optics")                          # a subfolder: a suggested label
    pdf(new / "Algebra copy.pdf", "another edition")                             # a development file's name
    pdf(new / "Sets.pdf", "sets")
    pdf(new / "9.pdf", "nine")
    pdf(dev / "algebra.pdf", "algebra")
    (dev / "9.docx").write_bytes(b"not a real document")                         # too short a name to mean anything
    out = tmp_path / "inv.csv"
    inventory.main([str(new), "--out", str(out), "--known", str(dev)])
    with open(out, newline="", encoding="utf-8-sig") as f:
        rows = {r["relative_path"]: r for r in csv.DictReader(f)}
    fam = {k: r["family_id"] for k, r in rows.items()}
    assert fam["Waves.pdf"] == fam["Waves (2).pdf"] and len(set(fam.values())) == 5 and all(fam.values())
    assert fam["Algebra copy.pdf"] == "DEV-1" and "algebra.pdf" in rows["Algebra copy.pdf"]["notes"]
    assert "joins development" in rows["Algebra copy.pdf"]["notes"] and fam["9.pdf"].startswith("F")
    assert rows["Physics/Optics notes.pdf"]["primary_label"] == "Physics" and rows["Sets.pdf"]["primary_label"] == ""
    assert list(next(iter(rows.values()))) == inventory.COLUMNS                  # nothing else is written


def test_shared_names_bound_puts_documents_with_any_common_suggestion_together():
    from tools import grouping

    s = lambda *names: [{"name": n, "evidence": [], "demoted": None} for n in names]
    filed = [("a", "X", s("Waves", "Optics")), ("b", "X", s("optics")), ("c", "Y", s("Sets")), ("d", "Y", s())]
    groups = grouping.shared_names(filed)
    assert groups["a"] == groups["b"] and len({groups["a"], groups["c"], groups["d"]}) == 3


def test_apply_split_moves_everything_or_nothing(tmp_path, monkeypatch):
    import hashlib

    from tools import apply_split

    monkeypatch.setattr(apply_split, "JOURNAL", tmp_path / "journal.json")     # never the real data folder

    src = tmp_path / "incoming"
    src.mkdir()
    rows = []
    for name, split in (("a.pdf", "development"), ("b.pdf", "validation"), ("c.pdf", "final_evaluation")):
        (src / name).write_bytes(name.encode())
        rows.append({"relative_path": name, "sha256": hashlib.sha256(name.encode()).hexdigest(), "split": split})
    folders = {k: tmp_path / k for k in ("development", "validation", "final_evaluation")}
    (folders["final_evaluation"]).mkdir()
    (folders["final_evaluation"] / "c.pdf").write_bytes(b"already here")
    with pytest.raises(ValueError, match="already at"):
        apply_split.apply(rows, src, folders)
    (folders["final_evaluation"] / "c.pdf").unlink()
    (src / "b.pdf").write_bytes(b"edited")
    with pytest.raises(ValueError, match="changed since"):
        apply_split.apply(rows, src, folders)
    assert sorted(p.name for p in src.iterdir()) == ["a.pdf", "b.pdf", "c.pdf"]   # nothing moved either time
    (src / "b.pdf").write_bytes(b"b.pdf")
    counts = apply_split.apply(rows, src, folders)
    assert counts == {"development": 1, "validation": 1, "final_evaluation": 1} and list(src.iterdir()) == []
    assert [(folders[r["split"]] / r["relative_path"]).read_bytes() for r in rows] == [b"a.pdf", b"b.pdf", b"c.pdf"]

    # a split made again: files move between the split folders; one that keeps its split is not even read
    previous = {r["relative_path"]: r["split"] for r in rows}
    again = [{**rows[0], "split": "final_evaluation"}, {**rows[1], "sha256": "not checked"},
             {**rows[2], "split": "development"}]
    counts = apply_split.apply(again, None, folders, previous)
    assert counts == {"development": 1, "validation": 1, "final_evaluation": 1}
    assert [(folders[r["split"]] / r["relative_path"]).read_bytes() for r in again] == [b"a.pdf", b"b.pdf", b"c.pdf"]
    assert sum(len(list(f.iterdir())) for f in folders.values()) == 3
    with pytest.raises(ValueError, match="not in the previous split"):
        apply_split.apply(again, None, folders, {})


def test_apply_split_puts_every_file_back_when_a_move_fails_or_the_run_stops(tmp_path, monkeypatch):
    import hashlib

    from tools import apply_split

    monkeypatch.setattr(apply_split, "JOURNAL", tmp_path / "journal.json")
    src = tmp_path / "incoming"
    src.mkdir()
    rows = []
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (src / name).write_bytes(name.encode())
        rows.append({"relative_path": name, "sha256": hashlib.sha256(name.encode()).hexdigest(),
                     "split": "development"})
    folders = {k: tmp_path / k for k in ("development", "validation", "final_evaluation")}
    for n in range(3):                                  # a failure at each move: all back, no journal left
        with pytest.raises(ValueError, match="every file was put back"):
            apply_split.apply(rows, src, folders, _fail_at=n)
        assert sorted(p.name for p in src.iterdir()) == ["a.pdf", "b.pdf", "c.pdf"]
        assert not (tmp_path / "journal.json").exists()
    moves = apply_split.plan(rows, src, folders)        # the run stopped after one move: its journal stays
    (tmp_path / "journal.json").write_text(__import__("json").dumps([[str(s), str(d)] for s, d in moves]))
    folders["development"].mkdir(exist_ok=True)
    (src / "a.pdf").rename(folders["development"] / "a.pdf")
    with pytest.raises(ValueError, match="--recover"):
        apply_split.apply(rows, src, folders)            # nothing more moves until it is put back
    assert apply_split.recover() == []
    assert sorted(p.name for p in src.iterdir()) == ["a.pdf", "b.pdf", "c.pdf"]
    assert not (tmp_path / "journal.json").exists()


def test_file_labels_files_only_waiting_development_rows(make_org, tmp_path):
    from classifile.organizer import read_and_analyze
    from tools.file_labels import file_labels
    from tools.measure_ui import make_pdf

    org, src, rows = make_org(), tmp_path / "src", []
    src.mkdir()
    for n, (label, split_name) in enumerate((("Algebra", "development"), ("Algebra", "development"),
                                             ("Optics", "development"), ("Optics", "validation"),
                                             ("Optics", "final_evaluation"))):
        make_pdf(src / f"doc{n}.pdf", f"Made-up title {n}")
        doc, _ = org.record(src / f"doc{n}.pdf", *read_and_analyze(src / f"doc{n}.pdf"))
        rows.append({"sha256": org.catalog.document(doc)["sha256"], "primary_label": label, "split": split_name,
                     "id": doc})
    elsewhere = org.create_category("Elsewhere")
    org.file(rows[1]["id"], elsewhere)                              # the owner filed this one already
    rows.append({"sha256": "0" * 64, "primary_label": "Algebra", "split": "development"})   # never imported
    done = file_labels(org, rows)
    assert done == {"filed": 2, "categories created": 2, "already filed (left as it is)": 1, "not in the catalog": 1}
    placed = {r["id"]: org.catalog.document_row(r["id"]) for r in rows[:5]}
    assert [placed[r["id"]]["category"] for r in rows[:5]] == ["Algebra", "Elsewhere", "Optics", None, None]
    assert all(org.catalog.active_primary(r["id"])["provenance"] == "user-confirmed" for r in rows[:3])
    copy = placed[rows[0]["id"]]["copy_path"]                       # a verified copy, like any filing
    assert (org.output_root / "Algebra" / "doc0.pdf").samefile(copy)
    assert file_labels(org, rows) == {"already filed (left as it is)": 3, "not in the catalog": 1}   # nothing twice


def test_offline_check_runs_the_app_end_to_end_with_the_network_refused(tmp_path, capsys):
    import pymupdf
    from tools import offline_check
    words = {"a": "matrix vector eigenvalue determinant linear algebra basis subspace",
             "b": "router packet switch subnet protocol ethernet gateway latency"}
    src = tmp_path / "src"
    src.mkdir()
    for n in range(4):
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), " ".join([words["ab"[n % 2]]] * 3), fontsize=11)
        d.save(src / f"doc{n}.pdf")
        d.close()
    before = {p.name: p.read_bytes() for p in src.iterdir()}
    assert offline_check.main([str(src)]) == 0
    out = capsys.readouterr().out
    assert "Network attempts: 0" in out and "PASS" in out
    assert {p.name: p.read_bytes() for p in src.iterdir()} == before         # the originals are only read


def test_offline_guard_refuses_and_records_network_attempts_in_child_processes(tmp_path):
    import os
    import subprocess
    import sys
    from tools import offline_check
    (tmp_path / "sitecustomize.py").write_text(offline_check.GUARD, encoding="utf-8")
    log = tmp_path / "attempts.log"
    env = os.environ | {"PYTHONPATH": str(tmp_path), "CLASSIFILE_OFFLINE_LOG": str(log)}
    probe = ("import socket\ntry:\n    socket.create_connection(('192.0.2.1', 9), timeout=1)\nexcept OSError as e:\n"
             "    print(e)\n")
    out = subprocess.run([sys.executable, "-c", probe], env=env, capture_output=True, text=True).stdout
    assert "refused by the offline check" in out and log.read_text(encoding="utf-8").split() == ["create_connection"]


def test_screenshots_render_a_made_up_library(tmp_path):
    from tools import screenshots
    assert screenshots.main([str(tmp_path / "shots"), "--size", "1024x640", "--views", "decide,settings"]) == 0
    assert sorted(p.name for p in (tmp_path / "shots").iterdir()) == ["decide.png", "settings.png"]


def test_error_ledger_uses_neutral_ids_and_never_overwrites(make_org, filed_pdf, tmp_path, capsys):
    """designImp2: the private error ledger. Neutral ids in the ledger; file names only in the separate map."""
    import csv

    from tools import error_ledger

    org = make_org()
    for cat, texts in {"Garden": ("compost soil seedling", "mulch pruning hedge", "tomato greenhouse soil"),
                       "Travel": ("hotel booking passport", "flight luggage visa", "train ticket hotel")}.items():
        for n, words in enumerate(texts):
            filed_pdf(org, f"{cat.lower()}-{n}.pdf", words, cat)
    path = org.catalog.path
    org.catalog.close()
    out, names = tmp_path / "ledger.csv", tmp_path / "names.csv"
    assert error_ledger.main(["--catalog", str(path), "--out", str(out), "--names", str(names)]) == 0
    rows = list(csv.DictReader(open(out, encoding="utf-8")))
    assert len(rows) == 6 and [r["id"] for r in rows] == [f"D{n}" for n in range(1, 7)]
    assert not any(".pdf" in v for r in rows for v in r.values())          # no file names in the ledger
    assert {r["file_name"] for r in csv.DictReader(open(names, encoding="utf-8"))} == {
        f"{c}-{n}.pdf" for c in ("garden", "travel") for n in range(3)}
    assert all(r["outcome"] in ("right", "wrong", "missed", "wait") for r in rows)
    with pytest.raises(SystemExit):
        error_ledger.main(["--catalog", str(path), "--out", str(out)])    # never over an existing file
