"""CP0 GUI smoke test: drop or choose files, run a dummy background job per file, cancel.

Run: .venv\\Scripts\\python -m classifile.app.smoke
"""
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget,
)

from classifile.app import make_app

JOB_SECONDS = 3.0


class Bridge(QObject):
    # Emitted from worker threads; Qt queues delivery to the GUI thread.
    status = Signal(int, str)


class SmokeWindow(QWidget):
    def __init__(self, job_seconds=JOB_SECONDS):
        super().__init__()
        self.job_seconds = job_seconds
        self.setWindowTitle("ClassiFile — CP0 smoke test")
        self.setAcceptDrops(True)
        self.resize(700, 400)

        self.list = QListWidget()
        self.statuses = []
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.cancel_event = threading.Event()
        self.bridge = Bridge()
        self.bridge.status.connect(self._set_status)

        choose = QPushButton("Add files…")
        choose.clicked.connect(self._choose)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancel)
        self.ticker = QLabel()  # proves the event loop stays alive
        buttons = QHBoxLayout()
        for w in (choose, cancel, self.ticker):
            buttons.addWidget(w)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Drop files here, or use Add files…"))
        layout.addWidget(self.list)
        layout.addLayout(buttons)
        self.startTimer(100)

    def timerEvent(self, _):
        self.ticker.setText(time.strftime("UI alive %H:%M:%S"))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def _choose(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose files")
        self.add_paths(paths)

    def add_paths(self, paths):
        for p in paths:
            row = len(self.statuses)
            self.statuses.append("queued")
            self.list.addItem(f"[queued] {Path(p).resolve()}")
            self.pool.submit(self._job, row, self.cancel_event)

    def _job(self, row, cancel):
        self.bridge.status.emit(row, "running")
        deadline = time.monotonic() + self.job_seconds
        while time.monotonic() < deadline:
            if cancel.is_set():
                self.bridge.status.emit(row, "cancelled")
                return
            time.sleep(0.05)
        self.bridge.status.emit(row, "done")

    def cancel(self):
        self.cancel_event.set()
        self.cancel_event = threading.Event()  # later additions run normally

    def _set_status(self, row, status):
        self.statuses[row] = status
        item = self.list.item(row)
        item.setText(f"[{status}] " + item.text().split("] ", 1)[1])

    def closeEvent(self, e):
        self.cancel()
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(e)


def main():
    app = make_app(sys.argv)
    w = SmokeWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
