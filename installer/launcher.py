"""The installed app's entry point (installer/classifile.spec). freeze_support() lets the reader's worker processes
(classifile.worker, started with "spawn") run inside the frozen app instead of opening a second window.

ClassiFile.exe --self-test REPORT FILE...  reads each file in a worker process, OCR included, and writes counts to
REPORT (a new file; never overwritten): how each read went, its units and how many characters OCR read. It shows
no document text. A check of the installed app (docs/INSTALLER_TEST.md)."""
import multiprocessing
import sys


def self_test(report, files):
    from classifile import __version__
    from classifile.organizer import read_and_analyze
    from classifile.reader.ocr import tessdata
    from classifile.worker import Worker
    lines = [f"ClassiFile {__version__}", f"OCR language data: {'found' if tessdata() else 'MISSING'}"]
    worker = Worker(read_and_analyze)
    try:
        for n, path in enumerate(files, 1):
            result = worker.run(path)[0]
            units = result.record.units if result.record else []
            ocr = sum(len(u.ocr_text or "") for u in units)
            lines.append(f"file {n}: {result.status}; {len(units)} units; {ocr} characters read by OCR")
    finally:
        worker.stop()
    ok = all(" ok;" in x for x in lines[2:]) and tessdata() is not None and len(lines) > 2
    lines.append("PASS" if ok else "FAIL")
    with open(report, "x", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 2 and sys.argv[1] == "--self-test":
        sys.exit(self_test(sys.argv[2], sys.argv[3:]))
    from classifile.app.main import main
    main()
