import os
import shutil

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from office_fixtures import make_pptx  # noqa: E402
from tools import page_labels  # noqa: E402
from tools.label_window import LabelWindow  # noqa: E402
from conftest import EXPECT, SAMPLE  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def sheet(samples, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    shutil.copyfile(samples / SAMPLE["S4"], src / "L-2.pdf")
    make_pptx(src / "deck.pptx")
    out = tmp_path / "labels.csv"
    page_labels.main(["make", str(src), "--out", str(out)])
    return out


def _visible_text(w):
    return " ".join([l.text() for l in w.findChildren(QLabel)] + [w.text.toPlainText()]).casefold()


def test_keys_save_each_answer_and_resume(app, sheet):
    rows = page_labels.read_rows(sheet)
    todo = [r for r in rows if r["label_source"] != "auto"]
    assert 0 < len(todo) < len(rows)  # auto-labelled units are never shown
    w = LabelWindow(sheet)
    assert [(r["file"], r["unit"]) for r in w.queue] == [(r["file"], r["unit"]) for r in todo]
    QTest.keyClick(w, Qt.Key_Y)
    QTest.keyClick(w, Qt.Key_S)
    QTest.keyClick(w, Qt.Key_N)
    QTest.keyClick(w, Qt.Key_Backspace)  # back to the third unit and answer it again
    QTest.keyClick(w, Qt.Key_Y)
    w.close()
    answers = page_labels.read_answers(sheet)
    first, second, third = ((r["file"], r["unit"]) for r in todo[:3])
    assert (answers[first], answers[second], answers[third]) == ("yes", "skip", "yes")  # latest answer wins
    w2 = LabelWindow(sheet)           # resume: unanswered units first, the skipped one last
    assert (w2.queue[0]["file"], w2.queue[0]["unit"]) == (todo[3]["file"], todo[3]["unit"])
    assert (w2.queue[-1]["file"], w2.queue[-1]["unit"]) == second
    w2.close()


def test_window_never_shows_the_rule_or_ocr(app, sheet):
    w = LabelWindow(sheet)
    for _ in range(len(w.queue)):
        shown = _visible_text(w)
        assert "suspect" not in shown and "ocr" not in shown and "flag" not in shown
        assert w.pictures.count() >= 1   # the page, or the unit's pictures
        QTest.keyClick(w, Qt.Key_S)
    assert "done" in _visible_text(w)
    w.close()


def test_window_refuses_final_eval_sources(app, sheet, monkeypatch):
    import tools
    monkeypatch.setattr(tools, "FINAL_EVAL", sheet.parent / "src")
    with pytest.raises(SystemExit, match="held out"):
        LabelWindow(sheet)


def _pump(app, until, timeout=120):
    import time
    end = time.monotonic() + timeout
    while not until() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.05)
    assert until()


@pytest.mark.ocr
def test_quality_pass_shows_ocr_with_dropped_lines_and_saves_answers(app, tmp_path):
    import random

    import pymupdf

    from office_fixtures import IMAGE_TEXT
    from classifile.organizer import read_and_analyze
    from classifile.worker import WorkerPool
    from tools import ocr_quality

    src = tmp_path / "src"
    src.mkdir()
    doc = pymupdf.open()                                   # page 1: words only inside a picture
    page = doc.new_page(width=600, height=200)
    page.insert_image(page.rect, stream=IMAGE_TEXT)
    rng = random.Random(7)                                 # page 2: a noise "photo" (OCR junk)
    photo = pymupdf.Pixmap(pymupdf.csRGB, 800, 600, bytes(rng.getrandbits(8) for _ in range(800 * 600 * 3)), False)
    doc.new_page().insert_image(pymupdf.Rect(72, 72, 472, 372), pixmap=photo)
    doc.save(src / "scan.pdf")
    sheet, sample = tmp_path / "labels.csv", tmp_path / "quality.csv"
    page_labels.main(["make", str(src), "--out", str(sheet)])
    ocr_quality.main(["make", str(sheet), "--n", "40", "--out", str(sample)])
    assert len(page_labels.read_rows(sample)) == 2

    w = LabelWindow(sample, "quality", workers=WorkerPool(read_and_analyze, size=1))
    try:
        _pump(app, lambda: not w._loading() and w.pictures.count() > 0)
        shown = w.text.toHtml().casefold()
        assert "diagram" in shown and "legend" in shown and "suspect" not in shown
        QTest.keyClick(w, Qt.Key_G)
        _pump(app, lambda: not w._loading() and w.pictures.count() > 0)
        assert "line-through" in w.text.toHtml()           # the photo's junk is shown greyed out
        assert w.pictures.itemAt(0).widget().pixmap().height() < 600   # the OCR'd region, not the whole page
        QTest.keyClick(w, Qt.Key_D)
        QTest.keyClick(w, Qt.Key_B)
    finally:
        w.close()
    result = ocr_quality.check(page_labels.read_rows(sample), page_labels.read_answers(sample),
                               page_labels.read_answers(sample, kind=ocr_quality.DROPPED))
    assert (result["judged"], result.get("good"), result.get("bad")) == (2, 1, 1)
    assert result["dropped_lines_had_real_text"] == 1


def test_name_review_window_one_file_per_screen(app, samples, tmp_path):
    from tools import name_review
    from tools.label_window import NameReviewWindow

    src = tmp_path / "src"
    src.mkdir()
    for n in (SAMPLE["S1"], SAMPLE["S4"]):
        shutil.copyfile(samples / n, src / n)
    sheet = tmp_path / "names.csv"
    name_review.main(["make", str(src), "--out", str(sheet)])
    rows = page_labels.read_rows(sheet)
    cst = [r for r in rows if r["file"] == SAMPLE["S1"]]
    assert [r["unit"] for r in cst] == ["1", "2", "3"] and cst[0]["name"] == EXPECT["S1.cover_title"]
    assert cst[0]["reason"] == "on the cover" and cst[0]["page"] == "1"
    assert cst[1]["reason"].startswith("repeated on pages") and int(cst[1]["page"]) > 1

    w = NameReviewWindow(sheet)
    w.show()
    assert w.progress.text().startswith("File 1 of 2") and SAMPLE["S1"] in w.progress.text()
    assert "Press 1, 2 or 3" in w.help.text() and w.names.count() == 3
    assert "on the cover (page 1)" in w.names.item(0).text()
    w.names.itemClicked.emit(w.names.item(1))                      # a name jumps to its first page
    assert w.page_label.text() == f"Page {cst[1]['page']} of 38"
    QTest.keyClick(w, Qt.Key_PageDown)
    assert w.page_label.text() == f"Page {int(cst[1]['page']) + 1} of 38"
    QTest.keyClick(w, Qt.Key_1)
    assert "✓ good" in w.names.item(0).text()
    QTest.keyClick(w, Qt.Key_1)                                    # pressing again unmarks
    assert "✓" not in w.names.item(0).text()
    QTest.keyClick(w, Qt.Key_1)
    QTest.keyClick(w, Qt.Key_Return)                               # Enter saves: 1 good, 2 and 3 not good
    assert w.progress.text().startswith("File 2 of 2")
    QTest.keyClick(w, Qt.Key_0)                                    # none of file 2's names is good
    assert w.progress.text().startswith("Done: 2 of 2")
    QTest.keyClick(w, Qt.Key_Backspace)                            # back: the answers are shown and editable
    assert w.progress.text().startswith("File 2 of 2") and all("✗ not good" in w.names.item(i).text()
                                                               for i in range(w.names.count()))
    w.better.setFocus()
    w.better.setText("Layered Network Models")
    QTest.keyClick(w.better, Qt.Key_Return)
    QTest.keyClick(w, Qt.Key_Backspace)
    QTest.keyClick(w, Qt.Key_Backspace)
    assert w.progress.text().startswith("File 1 of 2") and "✓ good" in w.names.item(0).text()
    assert "✗ not good" in w.names.item(1).text()
    w.close()

    result, acceptable = name_review.check(rows, page_labels.read_answers(sheet))
    assert result["files_reviewed"] == 2 and result["files_with_a_good_name_in_top3"] == 1
    assert result["good_by_rank"] == {1: 1, 2: 0, 3: 0} and result["better_names_typed"] == 1
    assert acceptable == {SAMPLE["S1"]: [EXPECT["S1.cover_title"]], SAMPLE["S4"]: ["Layered Network Models"]}
    saved = tmp_path / "acceptable.csv"
    name_review.save_acceptable(saved, acceptable, page_labels.read_answers(sheet))
    assert saved.read_text(encoding="utf-8-sig").splitlines() == [
        "file,name,kind", f"{SAMPLE['S1']},{EXPECT['S1.cover_title']},good",
        f"{SAMPLE['S4']},Layered Network Models,better"]
    with pytest.raises(FileExistsError):                           # never overwrites
        name_review.save_acceptable(saved, acceptable, {})


def test_quality_and_label_windows_show_item_number_and_answer(app, sheet):
    w = LabelWindow(sheet)
    first = w.queue[0]
    assert w.header.text().startswith(f"Item 1 of {len(w.todo)}") and w.note.text() == "Your answer: not answered yet"
    QTest.keyClick(w, Qt.Key_N)
    assert w.header.text().startswith(f"Item 2 of {len(w.todo)}")
    QTest.keyClick(w, Qt.Key_Backspace)
    assert w.queue[w.pos] is first and w.note.text() == "Your answer: no"
    w.close()


def test_quality_pass_hides_repeated_slide_pictures(tmp_path):
    from types import SimpleNamespace

    from tools.label_window import Sources

    deck = tmp_path / "deck.pptx"
    make_pptx(deck)
    units = [SimpleNamespace(pictures=["logo", f"p{i}"]) for i in range(4)]   # the logo sits on every slide
    s = Sources()
    try:
        s.records[str(deck)] = SimpleNamespace(units=units)
        assert len(s.pictures(str(deck), units[0])) == 2                       # E8 pass: every picture
        assert len(s.pictures(str(deck), units[0], ocr_only=True)) == 1       # quality pass: OCR never reads the logo
    finally:
        s.close()
