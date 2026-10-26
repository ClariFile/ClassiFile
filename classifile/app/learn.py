"""'Learn from my existing folders' (decision record 2.9): the user's organized folder, shown as proposed categories
before anything is read. Each subfolder can be unticked or renamed; nothing is moved, copied or changed."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from classifile.analysis.candidates import name_key
from classifile.app.widgets import DIALOG_MIN, GROUP, LEARN_LIST_MAX, PANEL, RELATED, box


class LearnDialog(QDialog):
    """found: [(subfolder, [files])] from Organizer.scan_folder; existing: {name_key: category name}. After Learn,
    chosen() gives [(name, subfolder, files)] for the ticked folders with a name."""

    def __init__(self, parent, root, found, existing):
        super().__init__(parent)
        self.setWindowTitle("Learn from my existing folders")
        self.setModal(True)
        self.setMinimumWidth(DIALOG_MIN + 160)
        self.found, self.existing, self.rows = found, existing, []
        heading = QLabel("Learn from my existing folders")
        heading.setObjectName("heading")
        about = QLabel(f"Each folder in {root.name} becomes a category, and its documents become examples ClassiFile "
                       "learns from, also the ones in folders inside it. Your files are only read: nothing is "
                       "moved, copied or changed. Untick folders "
                       "that aren't a subject, such as “New folder” or “Downloads”, and rename "
                       "any category.")
        about.setObjectName("secondary")
        about.setWordWrap(True)
        about.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(GROUP)
        grid.setVerticalSpacing(RELATED)
        for head, col in (("Folder", 0), ("Category name", 1), ("Documents", 2)):
            label = QLabel(head)
            label.setObjectName("secondary")
            grid.addWidget(label, 0, col)
        for i, (sub, files) in enumerate(found, start=1):
            tick = QCheckBox(sub.name)
            tick.setChecked(True)
            tick.setToolTip(str(sub))
            name = QLineEdit(sub.name)
            name.setAccessibleName(f"Category name for {sub.name}")
            count = QLabel(str(len(files)))
            note = QLabel()
            note.setObjectName("secondary")
            grid.addWidget(tick, 2 * i - 1, 0)
            grid.addWidget(name, 2 * i - 1, 1)
            grid.addWidget(count, 2 * i - 1, 2, Qt.AlignRight)
            grid.addWidget(note, 2 * i, 1, 1, 2)
            tick.toggled.connect(self._update)
            name.textChanged.connect(self._update)
            self.rows.append((tick, name, note, sub, files))
        grid.setColumnStretch(1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(grid_host)
        scroll.setMaximumHeight(LEARN_LIST_MAX)
        self.learn = QPushButton()
        self.learn.setObjectName("primary")
        self.learn.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons = box(QHBoxLayout())
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.learn)
        v = box(QVBoxLayout(self), PANEL, GROUP)
        v.addWidget(heading)
        v.addWidget(about)
        v.addWidget(scroll, 1)
        v.addLayout(buttons)
        self._update()

    def _update(self):
        n = 0
        for tick, name, note, sub, files in self.rows:
            name.setEnabled(tick.isChecked())
            key = name_key(" ".join(name.text().split()))
            nested = sum(f.parent != sub for f in files)
            inside = (f"{nested} of the {len(files)} are in folders inside it." if nested else "")
            text = ("" if not tick.isChecked() else "Type a category name, or untick this folder." if not key
                    else " ".join(filter(None, [f"Adds to your category “{self.existing[key]}”."
                                                if key in self.existing else "", inside])))
            note.setText(text)
            note.setVisible(bool(text))
            n += len(files) if tick.isChecked() and key else 0
        self.learn.setText(f"Learn from {n} document{'s' if n != 1 else ''}")
        self.learn.setEnabled(n > 0)

    def chosen(self):
        return [(" ".join(name.text().split()), sub, files) for tick, name, _, sub, files in self.rows
                if tick.isChecked() and name.text().strip()]
