# ClassiFile v1: the finish line

2026-10-14 · the definition of done for ClassiFile v1. From now on ClassiFile gets only the launch work below
and bug fixes, until v1 is released. New features wait for v1.1.

## 1. CP5: freeze, then the final evaluation once

1. **Freeze** (the record's CP5 and Part E). Write the frozen choices into the decision record:
   - the matcher: the matching version in use, with its preprocessing, vocabulary, category mapping and settings;
   - the level for automatic filing (Strict) and the 3 confirmed documents it needs per category;
   - the folder rules: new folders at a similarity of 0.20, at least 3 documents each; questions for groups found
     at 0.15; a single document waits.
   - From then on, matching does not update by itself during the evaluation.
2. **Run `data\final-eval` once**, with the frozen version, on a copy of the catalog.
   - The tool reads the folder, measures, and saves its result to a new file. It refuses a second run.
   - Nothing is tuned afterwards. If a bug is found, it is fixed and reported, and the number stays as measured.
3. **Report**:
   - right first, and in the first three;
   - filed automatically, right and wrong;
   - left waiting;
   - new folders created, any that mix subjects, and any second folder for a subject that already has one;
   - documents per decision.
   These are counts on a small held-out set, not a promise of accuracy.

## 2. A Windows installer

- One installer, built with PyInstaller (or a similar tool) and an installer script (for example Inno Setup).
- It bundles:
  - Python and the dependencies (PyMuPDF, PySide6);
  - Tesseract and its English data, so OCR works without a separate install;
  - the ClassiFile icons;
  - the licence notices: ClassiFile's AGPL-3.0 (with a link to the source), Tesseract's Apache-2.0, and the
    notices of PySide6 (LGPL) and PyMuPDF (AGPL).
- It installs per user and needs no internet connection after download. Uninstalling leaves the user's
  documents, copies and catalog in place.
- Checked on a clean Windows 11 machine: install, first run, import, OCR, filing, uninstall.
- No other new features.

## 3. A user README

- Install and first run: choosing the output folder, adding documents.
- How filing works:
  - matching with your folders;
  - Strict automatic filing and the 3 confirmed documents it needs;
  - "Filed automatically" and "Looks right";
  - new folders of 3 or more documents, and Rename;
  - learning from your confirmations.
- How to correct it: Move to…, Rename, Delete category, Also belongs to…, Remove from ClassiFile, Retry.
- What never happens: originals are never changed, moved or deleted; nothing is sent over the internet.
- Known limitations:
  - OCR misses text in tables, bordered boxes and on dark or gradient backgrounds;
  - English only;
  - folder names are usually typed by you: subject names are rarely written in the documents;
  - small folders (one or two documents) are rarely matched until they hold about five.

## 4. Not in v1

- Summaries for the user (SummarEase is a separate project).
- Languages other than English.
- Merging categories, aliases, and undoing an "Also belongs to".
- LLMs, embeddings, or any online service.
- Linking versions of the same document.
- macOS and Linux installers.
- A cloud or multi-device catalog.

## Done when

- [ ] Choices frozen in the record; final evaluation run once and reported.
- [ ] Installer built and checked on a clean machine; licence notices included.
- [ ] User README written.
- [ ] All tests pass, `tools.check_ui` passes, the privacy audit has 0 hits, and v1 is tagged.
