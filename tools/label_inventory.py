"""Fill in the primary_label column of an inventory, one file at a time (instead of a spreadsheet program).

Usage: python -m tools.label_inventory [data/inventory_incoming.csv] [--folder data/incoming] [--catalog PATH]
       python -m tools.label_inventory [data/inventory_incoming.csv] --splits data/splits_incoming.csv [--only LABEL]

Shows the file's name, its pages (a picture of each page, drawn for the owner to look at: no text is taken from
the file and nothing about it is stored) and a category field listing the categories in ClassiFile's catalog and
the labels given so far, with counts; type to filter, or type a new name and choose its "Create category" row.
"Open file" opens the file in its default program.
Enter or "Save & next" writes the label into the inventory CSV at once, so labelling can stop and continue later;
it starts at the first file without a label. Only the primary_label column changes. The CSV as it was before the
first label is kept beside it as <name>.before-labels.csv. The catalog is opened read-only; data/final-eval is
refused as a folder.

After a split the files are in the split's folders: --splits finds each file where the split put it, and --only
shows just the files the split recorded under one label, to give them other labels (it starts at the first file
that still has that label). This shows the owner pages of validation and final-evaluation files too: labels are
the owner's to give. The split itself is not redone here.
"""
import argparse
import csv
import os
import shutil
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from classifile.app import make_app
from classifile.app.widgets import GROUP, PAD, STYLE, CategoryPicker, ElidedLabel, Preview, box
from classifile.catalog.db import default_data_dir
from tools import refuse_final_eval
from tools.apply_split import FOLDERS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SHEET = ROOT / "data" / "inventory_incoming.csv"
DEFAULT_FOLDER = ROOT / "data" / "incoming"


def catalog_categories(path):
    """{category name: documents in it} from ClassiFile's catalog (read-only); {} when there is none."""
    if not Path(path).is_file():
        return {}
    db = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        live = "WHERE c.deleted_at IS NULL" if any(
            r[1] == "deleted_at" for r in db.execute("PRAGMA table_info(categories)")) else ""
        return dict(db.execute("SELECT c.name, COUNT(m.id) FROM categories c LEFT JOIN memberships m"
                               f" ON m.category_id = c.id AND m.status = 'active' {live} GROUP BY c.id"))
    finally:
        db.close()


def read_sheet(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames), list(reader)


def write_sheet(path, columns, rows):
    """The whole sheet again, through a temporary file, so a stop in the middle leaves the last saved one."""
    backup = Path(path).with_suffix(".before-labels.csv")
    if not backup.exists():
        shutil.copyfile(path, backup)  # once: the sheet as it was before any label
    temp = Path(path).with_suffix(".saving.csv")
    with open(temp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    os.replace(temp, path)


def split_paths(splits, only=None, folders=FOLDERS):
    """{relative_path: where the split put the file}, for every row or just those recorded under one label."""
    with open(splits, newline="", encoding="utf-8-sig") as f:
        return {r["relative_path"]: Path(folders[r["split"]]) / r["relative_path"] for r in csv.DictReader(f)
                if only is None or r["primary_label"].strip() == only}


class LabelInventoryWindow(QWidget):
    def __init__(self, sheet, folder, categories=None, paths=None, redo=None):
        """paths: {relative_path: where the file is now}; given, only those files are shown. redo: the label
        being replaced, so a file that still has it counts as not done."""
        super().__init__()
        self.sheet, self.folder, self.paths, self.redo = Path(sheet), Path(folder), paths, redo
        self.columns, self.all_rows = read_sheet(self.sheet)
        self.rows = [r for r in self.all_rows if paths is None or r["relative_path"] in paths]  # the ones shown
        self.categories = dict(categories or {})
        self.recent = []  # labels given in this session, latest first
        self.setWindowTitle("ClassiFile — inventory labels")
        self.setStyleSheet(STYLE)
        self.resize(1100, 720)
        self.preview = Preview(expandable=False)
        self.progress = QLabel()
        self.progress.setObjectName("secondary")
        self.name = ElidedLabel()
        self.name.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.facts = QLabel()
        self.facts.setObjectName("secondary")
        self.facts.setWordWrap(True)
        self.open_button = QPushButton("Open file")
        self.open_button.clicked.connect(self.open_file)
        self.picker = CategoryPicker()
        self.picker.PROMPT = "Type to find a category, or type a new name"
        self.picker.field.setPlaceholderText(self.picker.PROMPT)
        self.picker.changed.connect(self._update)
        self.picker.activated.connect(self.save)
        self.save_button = QPushButton("Save && next")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save)
        self.back_button = QPushButton("Back")
        self.back_button.clicked.connect(lambda: self.show_row(self.at - 1))
        self.skip_button = QPushButton("Skip")
        self.skip_button.clicked.connect(lambda: self.show_row(self.at + 1))
        head = box(QHBoxLayout(), spacing=GROUP)
        head.addWidget(self.name, 1)
        head.addWidget(self.open_button)
        buttons = box(QHBoxLayout())
        for b in (self.back_button, self.skip_button):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.save_button)
        v = box(QVBoxLayout(), spacing=GROUP)
        v.addWidget(self.progress)
        v.addLayout(head)
        v.addWidget(self.facts)
        v.addWidget(self.picker)
        v.addStretch(1)
        v.addLayout(buttons)
        h = box(QHBoxLayout(self), PAD, PAD)
        h.addWidget(self.preview, 3)            # the pages on the left, the question on the right
        h.addLayout(v, 2)
        self.show_row(self._next_open(0))

    def _open(self, row):
        return row["primary_label"].strip() in ("", self.redo)

    def _next_open(self, start, otherwise=None):
        return next((i for i in range(start, len(self.rows)) if self._open(self.rows[i])),
                    len(self.rows) if otherwise is None else otherwise)

    def path(self, row):
        return Path(self.paths[row["relative_path"]]) if self.paths else self.folder / row["relative_path"]

    def open_path(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_file(self):
        """The file opens in its default program, for the owner to look at. Nothing here reads it."""
        if self.at < len(self.rows):
            self.open_path(self.path(self.rows[self.at]))

    def _choices(self):
        given = Counter(r["primary_label"].strip() for r in self.all_rows if r["primary_label"].strip())
        names = {n.casefold(): n for n in list(self.categories) + list(given)}  # one spelling per name
        return [(n, n, self.categories.get(n, 0) + given.get(n, 0)) for n in names.values()]

    def show_row(self, index):
        self.at = max(0, min(len(self.rows), index))
        done = sum(not self._open(r) for r in self.rows)
        self.progress.setText(f"{len(self.rows) - done} of {len(self.rows)} still labelled {self.redo}" if self.redo
                              else f"{done} of {len(self.rows)} labelled")
        finished = self.at >= len(self.rows)
        for w in (self.open_button, self.picker, self.skip_button, self.save_button):
            w.setEnabled(not finished)
        self.back_button.setEnabled(self.at > 0)
        self.picker.set_choices(self._choices(), recent=self.recent)
        if finished:
            self.name.setText("That was the last file.")
            self.facts.setText("Close the window, or go back to change a label.")
            self.picker.field.clear()
            self.preview.show_document(None)
            return
        r = self.rows[self.at]
        self.name.setText(r["file_name"])
        self.preview.show_document(self.path(r))
        family = [x["file_name"] for x in self.all_rows if x["family_id"] and x["family_id"] == r["family_id"] and x is not r]
        facts = [f"File {self.at + 1} of {len(self.rows)}"] + ([f"{r['pages']} page" + ("" if r["pages"] == "1" else "s")] if r.get("pages") else [])
        if family:
            facts.append("same family as " + ", ".join(family[:3]) + (f" and {len(family) - 3} more" if len(family) > 3 else ""))
        self.facts.setText(" · ".join(facts) + (f"\n{r['notes']}" if r.get("notes") else ""))
        self.picker.field.setText(r["primary_label"].strip())  # a file labelled before shows its label, chosen
        self.picker.field.selectAll()
        self.picker.field.setFocus()

    def _update(self):
        self.save_button.setEnabled(self.at < len(self.rows) and bool(self.picker.current()))

    def save(self):
        choice = self.picker.current()
        if not choice or self.at >= len(self.rows):
            return
        label = choice[2]
        self.rows[self.at]["primary_label"] = label
        write_sheet(self.sheet, self.columns, self.all_rows)  # at once: stopping loses nothing
        self.recent = [label] + [x for x in self.recent if x != label][:4]
        self.show_row(self._next_open(self.at + 1, self.at + 1))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sheet", nargs="?", type=Path, default=DEFAULT_SHEET)
    ap.add_argument("--folder", type=Path, default=DEFAULT_FOLDER, help="the folder the inventory was made from")
    ap.add_argument("--catalog", type=Path, default=default_data_dir() / "catalog.sqlite3")
    ap.add_argument("--splits", type=Path, help="a split that was applied: each file is shown from its split's folder")
    ap.add_argument("--only", metavar="LABEL", help="with --splits: only the files the split recorded under this label")
    a = ap.parse_args(argv)
    if not a.sheet.is_file():
        sys.exit(f"No inventory at {a.sheet}. Make one with tools.inventory first.")
    if a.only and not a.splits:
        sys.exit("--only needs --splits.")
    paths = split_paths(a.splits, a.only) if a.splits else None
    if a.splits and not paths:
        sys.exit(f"No file in {a.splits}" + (f" was recorded under the label {a.only}." if a.only else "."))
    if not a.splits:
        refuse_final_eval(a.folder)
    app = make_app(sys.argv[:1])
    w = LabelInventoryWindow(a.sheet, a.folder, catalog_categories(a.catalog), paths, a.only)
    w.show()
    code = app.exec()
    w.preview.close_pdf()
    sys.exit(code)


if __name__ == "__main__":
    main()
