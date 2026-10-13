import csv
import json
import math

import pymupdf
import pytest

from classifile import matching
from classifile.organizer import read_and_analyze

SUBJECTS = {  # made-up subjects: no real document is involved
    "Algebra": "matrix vector eigenvalue determinant linear algebra basis subspace",
    "Networks": "router packet switch subnet protocol ethernet gateway latency",
    "Poetry": "stanza rhyme verse sonnet metaphor meter couplet imagery",
}


def _pdf(path, words, n):
    """A two-page PDF about one subject; n varies the wording a little."""
    words = words.split()
    d = pymupdf.open()
    for page in range(2):
        picked = [words[(n + page + i) % len(words)] for i in range(6)]
        d.new_page().insert_text((72, 100), f"Notes {n}: " + " ".join(picked) + " explained in plain sentences.",
                                 fontsize=11)
    d.save(path)
    d.close()


def _add(org, folder, subject, n, file_it=True):
    folder.mkdir(exist_ok=True)
    path = folder / f"{subject.lower()}-{n}.pdf"
    _pdf(path, SUBJECTS[subject], n)
    doc, _ = org.record(path, *read_and_analyze(path))
    if file_it:
        cat = org.catalog.category_by_key(subject.casefold())
        org.file(doc, cat["id"] if cat else org.create_category(subject))
    return doc


def test_words_and_vectors():
    counts = matching.terms("C++ and C# are not C. Lecture 12, 2024: TCP/IP on x86. Matrix MATRIX")
    assert counts["c++"] == counts["c#"] == 1 and counts["matrix"] == 2      # case folded; + and # kept
    assert not {"c", "12", "2024"} & set(counts)                             # one letter and numbers are left out
    idf = matching.fit_idf([matching.terms("matrix algebra"), matching.terms("matrix router")])
    assert idf["algebra"] > idf["matrix"]                                    # rarer words weigh more
    v = matching.vector(matching.terms("matrix algebra algebra unseen"), idf)
    assert "unseen" not in v and math.isclose(sum(x * x for x in v.values()), 1.0)
    assert matching.vector(matching.terms("nothing known here"), idf) == {}
    assert math.isclose(matching.dot(v, v), 1.0) and matching.dot(v, {"router": 1.0}) == 0


def test_ranking_and_abstention():
    texts = {f"{s}{n}": " ".join(words.split()[n:n + 6]) for s, words in SUBJECTS.items() for n in range(3)}
    labels = {d: d[:-1] for d in texts}
    bundle = matching.train(texts, labels)
    assert json.loads(json.dumps(bundle)) == bundle                         # plain data: it is stored as JSON
    assert bundle["documents"] == {"Algebra": 3, "Networks": 3, "Poetry": 3}
    assert {bundle["representation"], bundle["scorer"]} == {matching.REPRESENTATION, matching.SCORER}
    blank = matching.train(texts | {"scan": ""}, labels | {"scan": "Poetry"})   # nothing could be read from it
    assert blank["documents"] == bundle["documents"] and blank["centroids"] == bundle["centroids"]
    assert blank["training"]["scan"] == "Poetry"                             # given, so not "filed since" for ever
    model = matching.Matcher(bundle)
    ranked = model.rank("the determinant of a matrix and its eigenvalue")
    assert ranked[0][0] == "Algebra" and model.good(ranked)
    assert all(0 <= score <= 1 for _, score in ranked)                       # similarities, never probabilities
    assert model.rank("zebra giraffe antelope") == [] and not model.good([])   # nothing known: abstain
    torn = model.rank("matrix determinant eigenvalue router packet switch")  # two subjects equally: no clear best
    assert matching.lead(torn) < matching.lead(ranked)
    bundle["settings"]["good_match"] = matching.lead(torn) + 0.01           # the level is a setting of the bundle
    assert not matching.Matcher(bundle).good(torn)


def test_check_asks_only_for_what_changed_and_never_trains_on_it():
    texts = {f"{s}{n}": " ".join(words.split()[n:n + 6]) for s, words in SUBJECTS.items() for n in range(3)}
    labels = {d: d[:-1] for d in texts}
    previous = matching.train({d: t for d, t in texts.items() if not d.startswith("Poetry")},
                              {d: c for d, c in labels.items() if c != "Poetry"})
    found = matching.check(texts, labels, previous)
    assert found == {"documents": 3, "new": 3, "previous": 0}               # a subject the old model never saw
    texts["twin"], labels["twin"] = texts["Poetry0"], "Poetry"              # a version of a document
    alone = {d: t for d, t in texts.items() if not d.startswith("Poetry") or d in ("Poetry0", "twin")}
    found = matching.check(alone, {d: labels[d] for d in alone}, previous)
    assert found == {"documents": 2, "new": 0, "previous": 0}               # its twin did not teach the answer


def test_update_matching_is_versioned_and_keeps_the_previous_version_if_the_new_one_is_worse(
        make_org, tmp_path, monkeypatch):
    org, src = make_org(), tmp_path / "src"
    with pytest.raises(ValueError, match="at least two categories"):
        org.update_matching()
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    waiting = _add(org, src, "Networks", 7, file_it=False)
    cats = {c["name"]: c["id"] for c in org.catalog.categories()}
    assert org.matches(waiting, set(cats.values())) == [] and org.matching_status() == {"since": 6}   # no model yet

    first = org.update_matching()
    assert first == {"outcome": "updated", "version": 1, "documents": 6, "categories": 2, "check": None}
    assert org.matches(waiting, set(cats.values()))[0] == (cats["Networks"], 3)   # best first, with its documents
    assert cats["Networks"] not in dict(org.matches(waiting, {cats["Algebra"]}))   # a deleted one is never offered
    assert org.update_matching()["outcome"] == "up to date" and org.catalog.active_matcher()["version"] == 1
    status = org.matching_status()
    assert (status["version"], status["documents"], status["categories"], status["since"]) == (1, 6, 2, 0)

    org.file(waiting, cats["Networks"])                                     # the user's own filing: a new example
    assert org.matching_status()["since"] == 1
    second = org.update_matching()
    assert second["outcome"] == "updated" and second["version"] == 2
    assert second["check"] == {"documents": 1, "new": 1, "previous": 1}
    assert [r["status"] for r in org.catalog.all("SELECT status FROM matchers ORDER BY version")] == \
        ["previous", "active"]

    poem = _add(org, src, "Poetry", 1)
    monkeypatch.setattr(matching, "check", lambda *a: {"documents": 1, "new": 0, "previous": 1})
    third = org.update_matching()
    assert third["outcome"] == "kept previous" and third["version"] == 2
    assert [r["status"] for r in org.catalog.all("SELECT status FROM matchers ORDER BY version")] == \
        ["previous", "active", "rejected"]
    assert org.matching_status()["version"] == 2 and org.matching_status()["since"] == 1
    assert org.catalog.explicit_labels()[poem] == org.catalog.category_by_key("poetry")["id"]

    again = make_org()                                                      # after a restart the model is still there
    assert again.matcher()[0]["version"] == 2


def test_a_model_this_version_cannot_read_is_not_used(make_org, tmp_path):
    org, src = make_org(), tmp_path / "src"
    for n in range(2):
        _add(org, src, "Algebra", n)
        _add(org, src, "Poetry", n)
    org.update_matching()
    bundle = json.loads(org.catalog.active_matcher()["bundle_json"]) | {"representation": "older"}
    org.catalog.run("UPDATE matchers SET bundle_json = ?", json.dumps(bundle))
    again = make_org()
    assert again.matcher() is None and again.matching_status() == {"since": 4}
    assert again.update_matching()["outcome"] == "updated"                  # retrained, not compared with the old one


def test_validation_is_measured_once_without_importing_anything(make_org, tmp_path, capsys):
    from classifile.reader import sha256_file
    from tools import match_validation

    org, src, val = make_org(), tmp_path / "src", tmp_path / "validation"
    rows = []
    for n in range(3):
        for subject in ("Algebra", "Networks"):
            _add(org, src, subject, n)
    stray = _add(org, src, "Algebra", 5)                              # the owner filed "Matrices" files in Algebra
    rows.append({"sha256": org.catalog.document(stray)["sha256"], "primary_label": "Matrices", "split": "development"})
    org.update_matching()
    val.mkdir()
    for name, subject, label in (("a.pdf", "Algebra", "algebra"), ("b.pdf", "Networks", "Networks"),
                                 ("c.pdf", "Algebra", "Matrices"), ("d.pdf", "Poetry", "Poetry")):
        _pdf(val / name, SUBJECTS[subject], 9)
        rows.append({"sha256": sha256_file(val / name), "primary_label": label, "split": "validation"})
    _pdf(val / "unlabelled.pdf", SUBJECTS["Poetry"], 4)               # not in the splits file: left alone
    rows.append({"sha256": "0" * 64, "primary_label": "Algebra", "split": "validation"})   # listed, not there
    before = (len(org.catalog.all_documents()), sorted(p.name for p in val.iterdir()))

    saved = match_validation.measure(val, rows, org.catalog.path)
    assert (len(org.catalog.all_documents()), sorted(p.name for p in val.iterdir())) == before   # nothing imported
    assert saved["model"]["version"] == 1 and saved["labelled files not found"] == 1
    got = {d["label"]: d for d in saved["documents"]}
    assert set(got) == {"algebra", "Networks", "Matrices", "Poetry"}
    assert got["algebra"]["category"] == "Algebra" and got["algebra"]["ranked"][0][0] == "Algebra"
    assert got["Matrices"]["category"] == "Algebra" and not got["Matrices"]["named"]   # where its files went
    assert got["Poetry"]["category"] is None                         # no such category: nothing can be right
    assert all(d["read"] == "ok" and not set(d) & {"file_name", "path", "text"} for d in saved["documents"])
    match_validation.report(saved)
    text = capsys.readouterr().out
    assert "  3 /   3 /   4  all" in text and "  2 /   2 /   2  labels that name a category" in text
    assert "no category of this name: counted as Algebra" in text and "nothing can be right" in text
    assert "file everything    4 /   1 /   0" in text                 # the unknown subject is the wrong one

    out = tmp_path / "result.json"
    args = [str(val), "--labels", str(tmp_path / "splits.csv"), "--out", str(out), "--catalog", str(org.catalog.path)]
    with open(tmp_path / "splits.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sha256", "primary_label", "split"])
        w.writeheader()
        w.writerows(rows)
    assert match_validation.main(args) == 0 and json.loads(out.read_text(encoding="utf-8")) == json.loads(
        json.dumps(saved))
    with pytest.raises(SystemExit, match="already measured"):        # never a second look
        match_validation.main(args)
    assert match_validation.main(["--report", str(out)]) == 0        # printing again reads no document


def test_match_eval_holds_families_out_and_counts_new_subjects():
    from tools import match_eval

    docs = [{"id": f"{s}{n}", "sha": f"{s}{n}", "file_name": f"{s} part {n}.pdf", "category": s,
             "terms": matching.terms(" ".join(words.split()[n:n + 6]))}
            for s, words in SUBJECTS.items() for n in range(3)]
    docs.append(docs[0] | {"id": "twin", "sha": "other bytes", "file_name": "Algebra part 0 (2).pdf"})
    fam = match_eval.families(docs, {"Poetry0": "F1", "Poetry1": "F1"})
    assert fam[-1] == fam[0] and fam[6] == fam[7] and len(set(fam)) == 8   # a copy and a listed family stay together
    rows = match_eval.hold_out(docs, fam)
    assert len(rows) == 10 and set(rows[0]["ranked"]) == set(match_eval.SCORERS)
    by_id = {d["id"]: i for i, d in enumerate(docs)}
    assert all(r["examples"] == sum(d["category"] == r["category"] and fam[i] != fam[by_id[r["doc"]]]
                                    for i, d in enumerate(docs)) for r in rows)   # its own family never trains
    assert sorted(r["examples"] for r in rows) == [1, 1, 2, 2, 2, 2, 2, 2, 3, 3]
    assert match_eval.hits(rows, "nearest centroid", 1) == 10
    assert match_eval.right_within(rows, "nearest centroid", matching.lead, 0)[0] == 10
    unseen = match_eval.hold_out(docs, [d["category"] for d in docs])
    assert all(r["examples"] == 0 and r["category"] not in dict(r["ranked"]["nearest centroid"]) for r in unseen)
    assert match_eval.trade_off(unseen, "nearest centroid", 0.0, matching.lead) == (0, 0, 10, 0)   # all false familiar
    lines = []
    match_eval.report(rows, lines.append)
    match_eval.report_new_subjects(rows, unseen, lines.append)
    text = "\n".join(lines)
    assert "10 documents, 8 families, 3 categories" in text and "file everything" in text
    assert "%" not in text                                                 # counts, never percentages


def test_automatic_filing_only_when_clear_and_never_as_the_users_label(make_org, tmp_path):
    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    for n in range(2):
        _add(org, src, "Poetry", n)                                    # only two confirmed documents
    clear, small = _add(org, src, "Networks", 7, False), _add(org, src, "Poetry", 6, False)
    _pdf(src / "torn.pdf", "matrix router vector packet eigenvalue switch", 0)    # two subjects at once
    torn = org.record(src / "torn.pdf", *read_and_analyze(src / "torn.pdf"))[0]
    cats = {c["name"]: c["id"] for c in org.catalog.categories()}
    assert org.auto_level() == "strict" and org.file_automatically(clear) is None   # nothing learned yet
    org.update_matching()

    assert org.auto_choice(small) is None                              # its category holds too few confirmed ones
    assert org.matches(small, set(cats.values()))[0][0] == cats["Poetry"]   # it waits, with the best three
    assert org.auto_choice(torn) is None and org.file_automatically(torn) is None   # no clear best: it waits
    assert org.file_automatically(clear) == cats["Networks"]
    row = org.catalog.document_row(clear)
    assert (row["status"], row["category"], row["provenance"]) == ("filed", "Networks", "machine-assigned")
    assert json.loads(row["auto_json"]) == {"version": 1, "level": 0.10, "documents": 3}
    assert (org.output_root / "Networks" / "networks-7.pdf").samefile(row["copy_path"])   # a verified copy as usual
    assert clear not in org.catalog.explicit_labels()                  # not the user's label:
    assert org.matching_status()["since"] == 0 and org.update_matching()["outcome"] == "up to date"   # never trains
    assert org.file_automatically(clear) is None                       # filed already

    org.move(clear, cats["Algebra"])                                   # the user's move is a label
    assert org.catalog.explicit_labels()[clear] == cats["Algebra"]
    assert org.catalog.document_row(clear)["provenance"] == "user-corrected"

    org.set_auto_level("off")
    again = _add(org, src, "Networks", 8, False)
    assert org.auto_choice(again) is None                              # switched off: everything waits
    org.set_auto_level("off")                                          # no change: nothing recorded
    org.set_auto_level("lenient")
    assert org.file_automatically(again) == cats["Networks"]
    assert [(r["key"], r["value"]) for r in org.catalog.all("SELECT key, value FROM setting_changes ORDER BY id")] \
        == [("auto_level", "off"), ("auto_level", "lenient")]          # every change is on record
    with pytest.raises(ValueError):
        org.set_auto_level("reckless")


def test_grouping_unmatched_documents_and_their_shared_words():
    texts = {f"{s}{n}": " ".join(words.split()[n:n + 6]) for s, words in SUBJECTS.items() for n in range(3)}
    texts["alone"] = "zebra giraffe antelope savanna"
    idf = matching.fit_idf([matching.terms(t) for t in texts.values()])
    vectors = {d: matching.vector(matching.terms(t), idf) for d, t in texts.items()}
    groups = matching.similar_groups(vectors, matching.GROUP_LEVEL)
    assert sorted(map(tuple, groups)) == [tuple(f"{s}{n}" for n in range(3)) for s in sorted(SUBJECTS)]
    assert "alone" not in sum(groups, [])                              # a group needs at least two documents
    words = matching.shared_words([vectors[d] for d in ("Poetry0", "Poetry1", "Poetry2")])
    assert words and set(words) <= set(SUBJECTS["Poetry"].split())     # what they have in common
    assert matching.similar_groups(vectors, 1.1) == [] and matching.similar_groups({}, 0.1) == []


def test_group_eval_says_whether_a_held_out_category_comes_back_as_one_group():
    from tools import group_eval

    assert group_eval.outcome([1, 2, 3], [[1, 2, 3], [8, 9]]) == ("kept together", [(3, 0)], 0)
    assert group_eval.outcome([1, 2, 3], [[1, 2], [8, 9]]) == ("split apart", [(2, 0)], 1)
    assert group_eval.outcome([1, 2, 3], [[1, 2, 9]]) == ("mixed", [(2, 1)], 1)
    assert group_eval.outcome([1], [[1, 9]])[0] == "nothing to group"       # fewer than two unmatched documents
    docs = [{"id": f"{s}{n}", "sha": f"{s}{n}", "file_name": f"{s} part {n}.pdf", "category": s, "names": [f"{s} {n}"],
             "terms": matching.terms(" ".join(words.split()[n:n + 6]))}
            for s, words in SUBJECTS.items() for n in range(3)]
    rows = group_eval.evaluate(docs, list(range(len(docs))), matching.GROUP_LEVEL)
    assert [(r["documents"], r["unmatched"], r["verdict"]) for r in rows] == [(3, 3, "kept together")] * 3
    assert all(set(r["groups"][0]["words"]) <= set(SUBJECTS[r["category"]].split()) for r in rows)
    lines = []
    group_eval.report(docs, rows, matching.GROUP_LEVEL, lines.append)
    assert "3 kept together" in "\n".join(lines) and "key words: " in "\n".join(lines)


def test_looks_right_selected_categories_and_new_subject_groups(make_org, tmp_path):
    org, src = make_org(), tmp_path / "src"
    for n in range(3):
        _add(org, src, "Algebra", n)
        _add(org, src, "Networks", n)
    org.update_matching()
    cats = {c["name"]: c["id"] for c in org.catalog.categories()}

    org.set_auto_scope({cats["Algebra"]})                              # selected-category mode: only Algebra
    assert org.auto_scope() == {cats["Algebra"]}
    net, alg = _add(org, src, "Networks", 7, False), _add(org, src, "Algebra", 8, False)
    assert org.auto_choice(net) is None                                # its best category is not a ticked one
    assert org.matches(net, set(cats.values()))[0][0] == cats["Networks"]   # still compared with every category
    assert org.file_automatically(alg) == cats["Algebra"]
    org.set_auto_scope(None)
    assert org.auto_scope() is None and org.file_automatically(net) == cats["Networks"]
    assert [r["value"] for r in org.catalog.all("SELECT value FROM setting_changes WHERE key = 'auto_scope'"
                                                " ORDER BY id")] == ["selected", "all"]

    assert alg not in org.catalog.explicit_labels()
    assert org.confirm([alg, net]) == 2 and org.confirm([alg]) == 0   # "Looks right": the user's confirmation
    assert org.catalog.document_row(alg)["provenance"] == "user-confirmed"
    assert org.catalog.explicit_labels()[alg] == cats["Algebra"] and org.matching_status()["since"] == 2
    events = [r[0] for r in org.catalog.all("SELECT event FROM membership_events e JOIN memberships m ON"
                                            " m.id = e.membership_id WHERE m.document_id = ? ORDER BY e.id", alg)]
    assert events == ["created", "confirmed"]

    poems = [_add(org, src, "Poetry", n, False) for n in range(3)]     # a subject no category matches
    _pdf(src / "zoo.pdf", "zebra giraffe antelope savanna migration herd", 1)
    zoo = org.record(src / "zoo.pdf", *read_and_analyze(src / "zoo.pdf"))[0]
    assert all(org.matches(d, set(cats.values())) == [] for d in poems + [zoo])
    (ids, words), = org.new_subject_groups(poems + [zoo])
    assert sorted(ids) == sorted(poems) and words and set(words) <= set(SUBJECTS["Poetry"].split())
    assert org.new_subject_groups([zoo]) == []                         # a group needs two documents
    assert org.catalog.categories() == [c for c in org.catalog.categories() if c["name"] != "Poetry"]   # none made
    assert all(org.catalog.document(d)["status"] == "needs_decision" for d in poems)   # a question, nothing filed


def test_accuracy_round_variants_change_one_thing_and_are_measured_the_same_way():
    from tools import accuracy_round as ar

    units = [{"kind": "page", "title": None, "text": "Tides and Harbours\nCourse 12 page 1\nthe moon pulls the sea",
              "notes": None, "ocr_text": "harbour chart"},
             {"kind": "heading", "title": "Spring tides", "text": "Course 12 page 2\nspring tides are higher",
              "notes": "say this slowly", "ocr_text": None}]
    p = ar.parts(units, ["Tides and Harbours"], [{"line": "course ## page #", "pages": [1, 2]}])
    assert p["template"].splitlines() == ["Course 12 page 1", "Course 12 page 2"]   # repeated lines, numbers apart
    assert "Course" not in p["body"] and "say this slowly" in p["body"]
    assert p["ocr"] == "harbour chart" and "Tides and Harbours" in p["head"] and "Spring tides" in p["head"]
    doc = {"parts": p}
    plain, _ = ar.counts(doc, {})
    assert plain == ar.words("\n".join(p[k] for k in ("body", "template", "ocr")))   # as the matcher in use counts
    assert ar.counts(doc, {"head": 3.0})[0]["harbours"] == plain["harbours"] + 2      # the head counts three times
    assert "course" not in ar.counts(doc, {"template": 0.0})[0]
    assert ar.counts(doc, {"ocr": 0.5})[0]["chart"] == 0.5
    assert ar.counts(doc, {"bigrams": True})[0]["spring tides"] == 1                  # pairs of neighbouring words
    pieces = ar.counts(doc, {"chars": 0.3})[1]
    assert pieces["<tid"] == plain["tides"] and pieces["harbo"] == plain["harbours"] + plain["harbour"]
    idf = matching.fit_idf([plain])
    assert ar.weigh(plain, idf) == matching.vector(plain, idf)             # whole counts: the same vector
    assert all(x > 0 for x in ar.weigh(ar.counts(doc, {"ocr": 0.25})[0], idf).values())   # a fraction never turns negative

    docs = [{"id": f"{s}{n}", "sha": f"{s}{n}", "file_name": f"{s} {n}.pdf", "category": s,
             "parts": {"body": " ".join(text.split()[n:n + 6]), "head": text.split()[n], "ocr": "", "template": ""}}
            for s, text in SUBJECTS.items() for n in range(3)]
    fam = list(range(len(docs)))
    for name in ("in use", "head x2", "bigrams", "chars 0.3", "no template"):
        rows, unseen = ar.measure(docs, fam, ar.VARIANTS[name])
        first, three, known, right, wrong, familiar, best = ar.summary(rows, unseen)
        assert (first, three, known) == (9, 9, 9) and wrong == 0, name   # made-up subjects are easy for every variant
        assert all(r["examples"] == 0 for r in unseen)
    assert ar.confusions(rows) == [] and set(ar.per_category(rows, unseen)) == set(SUBJECTS)
    assert set(ar.key_words(rows[0])) <= set(SUBJECTS[rows[0]["category"]].split())
    lines = []
    ar.report(docs, fam, ["in use", "head x2"], lines.append)
    assert "%" not in "\n".join(lines) and "Categories with fewer than 5 documents" in "\n".join(lines)
