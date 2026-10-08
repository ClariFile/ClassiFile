import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from classifile.app.smoke import SmokeWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pump(app, until, timeout=5):
    end = time.monotonic() + timeout
    while not until() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_jobs_run_in_background_and_cancel(app, tmp_path):
    w = SmokeWindow(job_seconds=0.3)
    t0 = time.monotonic()
    w.add_paths([str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")])
    assert time.monotonic() - t0 < 0.2  # add_paths does not block on the jobs
    assert str(tmp_path / "a.pdf") in w.list.item(0).text()
    _pump(app, lambda: w.statuses == ["done", "done"])
    assert w.statuses == ["done", "done"]

    w.job_seconds = 30
    w.add_paths([str(tmp_path / "c.pdf")])
    _pump(app, lambda: w.statuses[2] == "running")
    w.cancel()
    _pump(app, lambda: w.statuses[2] == "cancelled")
    assert w.statuses[2] == "cancelled"
    w.close()


def test_ctrl_c_closes_windows_and_quits(app, tmp_path):
    import signal

    from PySide6.QtCore import QTimer

    from classifile.app import quit_on_sigint

    original = signal.getsignal(signal.SIGINT)
    try:
        quit_on_sigint(app)
        w = SmokeWindow(job_seconds=30)
        w.show()
        w.add_paths([str(tmp_path / "a.pdf")])
        QTimer.singleShot(200, lambda: signal.raise_signal(signal.SIGINT))
        QTimer.singleShot(5000, app.quit)  # safety net so a failure can't hang the suite
        app.exec()
        assert not w.isVisible()
        _pump(app, lambda: w.statuses[0] == "cancelled")  # closeEvent cancelled the running job
        assert w.statuses[0] == "cancelled"
    finally:
        signal.signal(signal.SIGINT, original)
