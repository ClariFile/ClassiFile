# CLAUDE.md — ClassiFile (offline document categorizer)

You are implementing ClassiFile, an offline desktop document categorizer in Python 3.11+ (package `classifile`). It is part of the ClariFile suite; the summarizer is a separate project, SummarEase. The project owner makes all requirement decisions.

## Authoritative record

@DECISION_RECORD.md

The record above is authoritative.
- If a task, an older file (claude-handoff/, legacy_prototype/) or your own idea conflicts with it, follow the record and tell the user about the conflict.
- Never edit DECISION_RECORD.md yourself. Propose changes to the user instead.

## Non-negotiable rules

1. **Never touch the user's source files.**
   - Never modify, move, rename or delete a source file, or change its metadata.
   - Open sources read-only, and never call save or timestamp functions on them.
   - Never create side files next to them.
2. **Never overwrite an existing file anywhere.** Output copies go through the verified-copy procedure: temporary name → hash check → publish without overwriting → catalog record.
3. **Never insert summaries, tags or OCR text into any document**, original or copy.
4. **Be careful with deletions.**
   - Never delete a file the app did not create and record.
   - Never delete or overwrite an app copy whose hash has changed (the user may have edited it).
   - Ask before deleting any file the user put in the project folder (for example under `data\`), even an exact duplicate.
5. **No network calls at runtime.** Install dependencies during setup only, with the user's approval.
6. **No LLMs, embeddings, clustering or extra ML libraries** unless the record allows them for the current checkpoint.
7. **Report results honestly.** Never present similarity scores or confidences as probabilities, and never claim accuracy from the six sample PDFs.
8. **No document text in logs** or error messages.
9. **Keep the reader isolated.** The reader package (classifile/reader) must not import anything from other classifile packages.

## Working style

- Work one checkpoint at a time, from the current CHECKPOINT_*_PROMPT.md file.
  - Stop at each stop point and report.
  - Never start the next checkpoint without the user's go-ahead.
- Ask before adding any dependency the checkpoint prompt does not list.
- Write tests alongside code, and run the full suite before reporting.
- If git is available, commit after each completed step with a clear message.
- The target is a native Windows desktop app. Keep paths and file operations cross-platform.
- Keep the interface minimal: categories, documents, minimal status, decision prompts.

## Fixtures and references

- **Sample PDFs.** The six development PDFs live in claude-handoff/samples/ (if present).
  - Treat them as read-only fixtures, and verify their SHA-256 against claude-handoff/samples/inventory.csv.
  - Never write into that folder. Tests copy the fixtures to a temporary directory first.
- **legacy_prototype/ is reference only.** Do not reuse its:
  - mandatory LLM provider path;
  - fixed taxonomy;
  - OCR-on-any-image rule;
  - sort=True extraction;
  - hard-link-only publication;
  - per-file sidecars.

## Commands

Run from the project folder (Windows, Python 3.11+; the venv uses 3.12).

- Setup: `py -3.12 -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements-dev.txt`
- Run the app: `.venv\Scripts\python -m classifile.app` (catalog in `%LOCALAPPDATA%\ClassiFile`; set `CLASSIFILE_DATA_DIR` to use another data folder)
- GUI smoke test (CP0): `.venv\Scripts\python -m classifile.app.smoke`
- Tests: `.venv\Scripts\python -m pytest -q` (temp files go to `test-output\`, recreated on each run)
- Inventory: `.venv\Scripts\python -m tools.inventory <folder> [--out data\inventory.csv] [--families] [--known <folder>...]` (family IDs are suggestions for the owner to review)
- Splits: `.venv\Scripts\python -m tools.split data\inventory.csv --dev P --val P --final P [--seed N] [--out data\splits.csv]`
- E8 page labels: `.venv\Scripts\python -m tools.page_labels make <folder>... [--out data\page_labels.csv]`, then `... check [data\page_labels.csv]`
- Labelling windows: `.venv\Scripts\python -m tools.label_window` (E8), `... --quality` (OCR quality; sample with `tools.ocr_quality make`, count with `tools.ocr_quality check`)
- Name review: `.venv\Scripts\python -m tools.name_review make <folder>...`, label with `tools.label_window --names`, count with `tools.name_review check`
- The owner's grouping of development files, from the catalog (read-only): `.venv\Scripts\python -m tools.grouping <folder>...` (prints file and category names: keep the output local)
- Inventory labels, one file at a time: `.venv\Scripts\python -m tools.label_inventory [data\inventory_incoming.csv] [--folder data\incoming]`
- Labels again after a split (files shown from their split folders, for the owner): `.venv\Scripts\python -m tools.label_inventory --splits data\splits_incoming.csv [--only "<label>"]`
- Window renders for layout checks: `.venv\Scripts\python -m tools.render_window [--size 1536x864] [--scale 1.25] [--out data] [--theme light|dark|both]` (PNGs per theme, `render-<theme>-*.png`: eleven views, or five scaled views with `--scale`)
- OCR needs Tesseract (`C:\Program Files\Tesseract-OCR`, or `TESSDATA_PREFIX`). Tests run OCR only when marked `ocr`; others set `CLASSIFILE_OCR=off`.
- Apply a split: `.venv\Scripts\python -m tools.apply_split data\splits.csv --from <folder>` (moves the files into `data\development`, `data\validation` and `data\final-eval`; all or nothing). A split made again: `... data\splits_2.csv --previous data\splits.csv` (only files that change folder are touched)
- Matching (CP3). The model is updated on request (Settings, "Update matching") and by itself after every 10 confirmations or moves (record 2.6); versioned, and the previous version is kept if the new one does worse.
  - E2 and E4 on development data: `.venv\Scripts\python -m tools.match_eval [--families <csv>...] [--growth] [--json FILE]` (reads a copy of the catalog; prints category names: keep the output local)
  - Validation, measured once: `.venv\Scripts\python -m tools.match_validation data\validation --labels data\splits_incoming_2.csv` (refuses a second run; `--report data\validation_matching.json` prints the saved result)
  - Accuracy round, one change to the representation at a time: `.venv\Scripts\python -m tools.accuracy_round [--families <csv>...] [--only <variant>...] [--out FILE]`; one variant on validation, once: `... --validation data\validation --labels data\splits_incoming_2.csv --variant "<name>" --out FILE` (changes nothing in the app; prints category names and words from documents: keep the output local)
  - Grouping new subjects on development data: `.venv\Scripts\python -m tools.group_eval [--families <csv>...] [--level X] [--compare X...] [--out FILE]`; the replay of automatic new folders (record 2.6): `... --folders` (prints category names and words from documents: keep the output local)
  - File waiting development documents from the owner's labels: `.venv\Scripts\python -m tools.file_labels data\splits_incoming_2.csv` (development rows only; close the app first)
- Interface timings on a made-up catalog: `.venv\Scripts\python -m tools.measure_ui [--json FILE]`
- Interface acceptance checks (four window sizes, 100/125/150%): `.venv\Scripts\python -m tools.check_ui`
- `data\final-eval\` is the held-out final evaluation: never open, read or test against it until the user says so. The tools refuse it.
- `data\validation\` is kept apart: not for building or tuning. Development data is `data\development`, `data\real-samples` and the six samples.

The sample fixtures actually live in `document-organizer-claude-handoff/claude-handoff/samples/` (not tracked).

## Privacy of tracked files

- Never put the user's name or user-folder path, real file names (the user's or the six samples'), course codes, people, institutions or titles copied from documents in tracked files or commit messages.
- Tests refer to development files by neutral IDs (S1–S6) and take content-based expectations from the local map `data\fixtures.json`; they skip when it is absent.
- Before every push: `.venv\Scripts\python -m tools.audit_terms --range origin/main..main` (terms in the local `data\audit_terms.txt`). Push only with 0 hits; never force-push.

## Licensing

PyMuPDF is AGPL, and this repository is public, so ClassiFile is licensed under AGPL-3.0 (`LICENSE`).
