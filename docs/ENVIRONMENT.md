# Environment baseline (CP0)

Collected 2026-10-08 with read-only commands (`py -0p`, `Get-CimInstance`, `Get-PSDrive`). Nothing was installed system-wide.

| Item | Value |
|---|---|
| Machine | Micro-Star International GS65 Stealth 9SE (matches the target laptop in A1) |
| OS | Microsoft Windows 11 Home Single Language, version 10.0.26300 (build 26300) |
| CPU | Intel Core i7-9750H @ 2.60 GHz, 6 cores / 12 logical processors |
| RAM | 17,014,226,944 bytes (≈15.8 GiB, "16 GB") |
| Free disk on C: (project drive) | 143,336,710,144 bytes (≈133.5 GiB) |
| GPU (informational) | NVIDIA GeForce RTX 2060, driver 32.0.16.1714; Intel UHD Graphics 630, driver 26.20.100.7584 |

## Python

| Version | Path |
|---|---|
| 3.12.1 (default for `py`) | `C:\Python312\python.exe` |
| 3.10 | `C:\Python310\python.exe` |
| 3.9 | `%LOCALAPPDATA%\Programs\Python\Python39\python.exe` |

A 3.11+ interpreter exists. The project venv (`.venv`) uses Python 3.12.1.

## Session type

The Claude Code session runs natively on Windows (Git Bash / MSYS2 shell, `MINGW64_NT-10.0-26300`), not inside WSL. The app runs as a native Windows process.

## Project location

`C:\Projects\ClassiFile` (moved from a folder in the user's Downloads on 2026-10-08; venv recreated). This is not inside a OneDrive or other cloud-synced folder.

## Installed packages (venv only)

PyMuPDF 1.28.2, PySide6 6.11.2, pytest 9.1.1 (pinned in `requirements.txt` / `requirements-dev.txt`). PySide6 imports and creates a `QApplication` on this machine.

## OCR

Tesseract 5.5.3 (UB Mannheim build) in `C:\Program Files\Tesseract-OCR`, installed by the user on 2026-10-08. 124 language files, including `eng` and `mya`. User PATH and `TESSDATA_PREFIX` point to it; PyMuPDF 1.28.2 finds the language data and OCR works (verified).
