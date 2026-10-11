# ClassiFile status

2026-10-12 · decision record version 1.9

## Done

**CP0 Foundation**
- Environment baseline (docs/ENVIRONMENT.md), project skeleton with the isolated reader, GUI smoke test.
- Tools: inventory, family-based splits.

**CP1 First end-to-end slice**
- Import by drag-and-drop or file chooser.
- PDF extraction with observations and source locations, in a versioned extraction record.
- Rule-based candidate names with evidence (rules-6 since the name review).
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
- 212 automated tests.

## Development results so far

These counts describe development data only. They are not accuracy estimates.

- **Selective OCR (E8):** the adopted rule caught 139 of 160 units with content the native text misses.
- **Name review:** 21 of 34 development files had at least one good name in the top three; 76 suggested names
  were marked not good. The most common problems were subtopics (sections of a document rather than the
  whole), course or series names, fragments and generic or template words. The acceptable names are kept outside
  the repository.
- **OCR quality:** 40 OCR outputs were judged twice. First round: 4 good, 9 partly good, 27 bad. Second round,
  with PDFs showing only the regions OCR read: 5 good, 8 partly good, 27 bad (PDF 5, 8 and 16; slides 7 bad;
  text documents 4 bad). 25 of the 40 answers were the same in both rounds.

## Open

- **OCR quality.** Investigated on the same 40 items (57 pictures). The counts below are a proxy (distinct
  plausible words kept after the junk filter), on development data; they are not accuracy estimates.
  - The judging window misled in two ways, both corrected: PDFs showed the whole page instead of the regions
    OCR read (before the second round), and slides showed repeated logos that OCR never reads (after it).
  - The junk filter dropped some real lines, although none were marked in the judging: lines with a stray bar
    or dots, and slash-joined words. Fixed: 550 words kept (547 before).
  - Tried and not adopted: regrouping OCR words into rows. It kept no more words and, on a synthetic picture,
    attached junk to a real line so the line was dropped.
  - Resolution is not the cause: rendering at half or a third of the size reads about the same number of words.
  - What OCR really misses is text inside bordered boxes and table cells, light text on dark boxes, and text on
    gradient backgrounds. Formulas and label-free drawings stay poor whatever the setting.
  - PyMuPDF's OCR call has no layout setting. The installed Tesseract program has: in sparse-text mode it reads
    the boxed and table text the current pass misses, but reads some other pictures worse. No single setting
    wins (current 547 words, sparse 537, sparse with adaptive thresholding 589).
  - Candidate, built but off by default (`CLASSIFILE_OCR=extra`): keep the current pass, add two Tesseract passes
    and keep the best per picture. On the 57 pictures: 635 words kept (550 with one pass); a later pass won on
    22. Cost: about one more second per picture, and the Tesseract program itself, not only its language data.
    The pictures go to it on stdin and come back on stdout: no temporary files.
  - Waiting for the user's blind comparison on the same 40 items (`tools.label_window --compare`). The extra
    passes become the default only if the user prefers them; the decision record then needs a line in B3.
- **Name rules.** First round after the review done (rules-6), checked against the saved review with
  `tools.name_stats score`. Top-three names marked not good: 39 (76 under rules-5). Files with a good name in the
  top three: 21 of 34, unchanged; with a good name first: 19 (17). 14 of the names now shown were never judged.
  These counts describe development data and rules chosen on it; they are not accuracy estimates.
  - Changed: lines whose only evidence is repeating on some pages go under "More" (score unchanged, so no
    self-description is declared dominant); DOCX/ODT take only their first qualifying opening line; more generic
    words, bare codes, IP addresses, quoted data and academic ranks alone are rejected.
  - The user's ruling (2026-10-12): ClassiFile never decides, creates or changes a document's own title or
    name; it only suggests category names and files documents. A cover title is evidence for a category only.
  - No file has a category label from the user yet, so suggestions cannot be scored at category level. The
    second review round (`data\name_review_2.csv`, 74 names for 34 files) collects them: good marks, and a typed
    category name where none fits.
  - Left as they are: cover lines that are subtopics, file-name forms, and key-phrase fragments.
- **CP3** has not started.

## Next

1. OCR: the user's blind comparison of one pass against the extra passes, then adopt or drop them.
2. Names: the user's second review round, as category names; then rules from those marks. A trained name
   recogniser stays deferred by the decision record until it can be compared with the rules.
3. CP3 (after the user's go-ahead): scorer comparison (E2) and abstention baseline (E4) on development data,
   selected-category mode with permissions through the queue, "Belongs to" / "Also belongs to", primary
   replacement and edited-copy protection.
4. Later: CP4 automatic mode and discovery, CP5 quality gate and freeze. SummarEase is a separate project.
