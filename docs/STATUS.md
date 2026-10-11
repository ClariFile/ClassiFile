# ClassiFile status

2026-10-11 · decision record version 1.9

## Done

**CP0 Foundation**
- Environment baseline (docs/ENVIRONMENT.md), project skeleton with the isolated reader, GUI smoke test.
- Tools: inventory, family-based splits.

**CP1 First end-to-end slice**
- Import by drag-and-drop or file chooser.
- PDF extraction with observations and source locations, in a versioned extraction record.
- Rule-based candidate names with evidence (rules-5).
- Two-step filing: the user picks or types a category; filing happens only on the button or Enter.
- Verified copies: temporary name, hash check, publish without overwriting, catalog record.
- SQLite catalog; reopening the app shows the same state. Startup repairs half-done filings.

**CP2 Formats and OCR**
- Native extraction for PPTX, DOCX and ODT, with the Python standard library.
- Selective OCR (any non-repeated picture of at least 5% of its page or slide), with a junk filter and counts.
- Worker processes with per-file timeouts.
- Hidden internal summary record.
- Layout (lines, blocks, positions, sizes) kept in the extraction record for SummarEase later.
- E8 page-label check on development data.

**Since CP2**
- Remove from ClassiFile for waiting documents; Locate file… for originals that moved, checked by hash.
- Changing the output folder moves copies safely; edited copies stay and are flagged.
- Interface redesign: sidebar views, document list, a "Needs your decision" page with one primary action per
  question, group items, a details panel on request, notices and toasts, Settings, responsive breakpoints.
- Spacing pass: one shared spacing system; checked at 1024, 1100, 1280 and 1536 px wide, and at 125% and 150%
  scaling.
- Labelling windows for the E8 page labels, the OCR quality check and the name review.
- Dropdowns and disclosure arrows share the control style; the layout was checked at 1920×1080.
- Tests refer to development files by neutral IDs through a local map in `data\` and skip when it is absent.
- 197 automated tests.

## Development results so far

These counts describe development data only. They are not accuracy estimates.

- **Selective OCR (E8):** the adopted rule caught 139 of 160 units with content the native text misses.
- **Name review:** 21 of 34 development files had at least one good name in the top three; 76 suggested names
  were marked not good. The most common problems were subtopics (sections of a document rather than the
  whole), course or series names, fragments and generic or template words. The acceptable names are kept outside
  the repository.
- **OCR quality:** of 40 OCR outputs judged, 4 were good, 9 partly good and 27 bad. The junk filter dropped no
  real text in the sample, so the problem is the recognition itself.

## Open

- **OCR quality.** Investigated on the same 40 items (57 pictures). The counts below are a proxy (distinct
  plausible words kept after the junk filter), on development data; they are not accuracy estimates.
  - The first judgments are not a reliable baseline. For PDFs the window showed the whole page instead of the
    regions OCR read, the 40 answers took about two minutes in total, and several pictures marked bad were read
    almost word for word. The window now shows only the OCR'd regions; the 40 items need judging again.
  - Resolution is not the cause: rendering at half or a third of the size reads about the same number of words.
  - What OCR really misses is text inside bordered boxes and table cells, light text on dark boxes, and text on
    gradient backgrounds. Formulas and label-free drawings stay poor whatever the setting.
  - PyMuPDF's OCR call has no layout setting. The installed Tesseract program has: in sparse-text mode it reads
    the boxed and table text the current pass misses, but reads some other pictures worse. No single setting
    wins (current 547 words, sparse 537, sparse with adaptive thresholding 589).
  - Candidate, not adopted: keep the current pass, add two Tesseract passes and keep the best per picture:
    632 words (current 547); a later pass won on 23 of 57 pictures. Cost: two extra program launches per
    picture, about half a second each, and the app would need the Tesseract program, not only its language data.
- **Name rules.** Improve the rules for the problem types found in the name review, then review again.
  The user's guidance for that round: lesson titles (one lesson inside a course) are too narrow; suggestions
  should be at the subject or course level, like the better names the user typed. Not changed yet.
- **CP3** has not started.

## Next

1. OCR: judge the 40 items again in the corrected window; then the user decides whether the extra-pass
   candidate is worth its cost. If so, build it and judge it blind against the current results.
2. Name-rule improvements, re-checked against the saved name review.
3. CP3 (after the user's go-ahead): scorer comparison (E2) and abstention baseline (E4) on development data,
   selected-category mode with permissions through the queue, "Belongs to" / "Also belongs to", primary
   replacement and edited-copy protection.
4. Later: CP4 automatic mode and discovery, CP5 quality gate and freeze. SummarEase is a separate project.
