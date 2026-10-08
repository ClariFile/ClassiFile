import signal
import sys
from pathlib import Path

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

APP_USER_MODEL_ID = "ClariFile.ClassiFile"
# ponytail: icons are read from the source tree; installer packaging (F) will bundle them as resources.
ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons" / "classifile"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def icon_files():
    return [ICON_DIR / "png" / f"classifile-{s}.png" for s in ICON_SIZES]


def app_icon():
    icon = QIcon()
    for size, path in zip(ICON_SIZES, icon_files()):
        icon.addFile(str(path), QSize(size, size))
    return icon


def set_app_user_model_id():
    """Windows groups taskbar buttons (and picks their icon) by this ID; without it they show Python's icon."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def make_app(argv):
    """The QApplication with the ClassiFile identity: taskbar ID first, then one icon for every window and dialog."""
    set_app_user_model_id()  # must precede the first window
    app = QApplication(argv)
    app.setApplicationName("ClassiFile")
    app.setWindowIcon(app_icon())
    quit_on_sigint(app)
    return app


def quit_on_sigint(app):
    """Make Ctrl+C in the terminal close the windows (running their cleanup) and quit, without a traceback."""
    def handler(*_):
        app.closeAllWindows()
        app.quit()

    signal.signal(signal.SIGINT, handler)
    # Python only runs signal handlers when it gets control; the Qt loop must wake it periodically.
    timer = QTimer(app)
    timer.timeout.connect(lambda: None)
    timer.start(200)
