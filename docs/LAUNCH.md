# ClassiFile v1: the finish line

2026-10-14, marked 2026-10-15 · the definition of done for ClassiFile v1. From now on ClassiFile gets only the
launch work below and bug fixes, until v1 is released. New features wait for v1.1.

**[Blocker]** must be done before v1 is released. **[v1.1]** can wait. Everything in sections 1 to 3 is a
blocker unless marked otherwise.

## 0. Before the freeze (found 2026-10-15)

- **[Blocker]** The owner decides the proposed changes to the decision record (`docs/STATUS.md`, "Proposed
  changes"): the update check (A7), the one evaluation (B4), "Check these", and the CP4 items not built (E1 policy,
  E5–E7 on their defaults). The freeze writes into the record, so it must say what the code does.
- **[Blocker]** "Update matching" once more, so the frozen version has learned the owner's last moves; then the
  owner answers "Check these" (2 documents on 2026-10-15).
- **[Blocker]** The CP5 report covers all of Part E: besides what `tools.evaluate` prints, incorrect creations,
  duplicate categories, over-merging and fragmentation (from `tools.group_eval --folders`), pending rate, and the
  four effort numbers (B2). One command for it, like `tools.evaluate`.
- **[Blocker]** Functional gate: an offline run with networking disabled, checked on the laptop.
- **[v1.1]** Balanced with "the nearest document is in the best folder" (on development data it files as many as
  Balanced and wrongly files fewer new subjects, 11 of 118 instead of 15). Only if the owner wants more automatic
  filing than Strict; it would need validation and a record change.
- **[v1.1]** E5–E7 run on their own data (name equivalence, instance identifiers, conflicting self-descriptions).

## 1. CP5: freeze, then the final evaluation once

1. **Freeze** (the record's CP5 and Part E). Write the frozen choices into the decision record:
   - the matcher: the matching version in use, with its preprocessing, vocabulary, category mapping and settings
     (updated once more first, so it has learned the owner's last moves);
   - the level for automatic filing (Strict) and the 3 confirmed documents it needs per category;
   - the folder rules: new folders at a similarity of 0.20, at least 3 documents each; questions for groups found
     at 0.15; a single document waits.
   - the update check (no more wrong automatic filings, no fewer right first, on the full evaluation) and
     "Check these" (another category ahead by at least 0.10);
   - From then on, matching does not update by itself during the evaluation.
2. **Run `data\final-eval` once**, with the frozen version, on a copy of the catalog.
   - The tool reads the folder, measures, and saves its result to a new file. It refuses a second run. It
     counts the same way as `tools.evaluate` (the same summary, levels and ranges).
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

## 4. Not in v1 [v1.1 or later]

- Summaries for the user (SummarEase is a separate project).
- Languages other than English.
- Merging categories, aliases, and undoing an "Also belongs to".
- LLMs, embeddings, or any online service.
- Linking versions of the same document.
- macOS and Linux installers.
- A cloud or multi-device catalog.

## Done when

- [ ] Section 0 blockers done: record changes decided, matching updated, Check these answered, the full
      CP5 report command, the offline check.
- [ ] Choices frozen in the record; final evaluation run once and reported.
- [ ] Installer built and checked on a clean machine; licence notices included.
- [ ] User README written.
- [ ] All tests pass, `tools.check_ui` passes, the privacy audit has 0 hits, and v1 is tagged.
