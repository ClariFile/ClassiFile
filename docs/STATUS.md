# ClassiFile status

2026-10-08 · decision record version 1.9

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
- 196 automated tests.

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

- **OCR quality.** Most OCR output is unusable. The cause is not yet known; candidates are rendering resolution,
  small text, coloured or dark slide backgrounds, transparent pictures and page segmentation. Plan: measure these
  factors on the same 40 items, try one change at a time, and re-judge blind against the current results.
- **Name rules.** Improve the rules for the problem types found in the name review, then review again.
  The user's guidance for that round: lesson titles (one lesson inside a course) are too narrow; suggestions
  should be at the subject or course level, like the better names the user typed. Not changed yet.
- **CP3** has not started.

## Next

1. OCR investigation and a measured fix, judged on the same 40 items, then confirmed on a fresh sample.
2. Name-rule improvements, re-checked against the saved name review.
3. CP3 (after the user's go-ahead): scorer comparison (E2) and abstention baseline (E4) on development data,
   selected-category mode with permissions through the queue, "Belongs to" / "Also belongs to", primary
   replacement and edited-copy protection.
4. Later: CP4 automatic mode and discovery, CP5 quality gate and freeze. SummarEase is a separate project.
