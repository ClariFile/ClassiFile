# ClassiFile status

2026-10-12 · decision record version 1.9

## Done

**CP0 Foundation**
- Environment baseline (docs/ENVIRONMENT.md), project skeleton with the isolated reader, GUI smoke test.
- Tools: inventory, family-based splits.

**CP1 First end-to-end slice**
- Import by drag-and-drop or file chooser.
- PDF extraction with observations and source locations, in a versioned extraction record.
- Rule-based candidate names with evidence (rules-7 since the name reviews).
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
- **OCR comparison:** blind, one pass against extra passes on the same 40 items: 4 extra, 3 current, 33 same.
- **Second name review:** 34 files, 80 names marked not good, 7 skipped, none good, 3 category names typed.

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
  - Extra passes through the Tesseract program (sparse-text layout, best result per picture) were built and
    judged blind by the user on the 40 items: 4 better with them, 3 better without, 33 no difference. Not
    adopted and removed; they also cost about one more second per picture.
  - Speed, same words kept: the OCR result is no longer compressed before it is read back, the photo check
    samples fewer pixels, and a picture shown again in a document is read once. Reading the 18 sampled files:
    about 98 s before, 80 s now. The app reads four documents at once (was two).
  - Not taken: OCR at 200 dpi instead of 300 would bring those files to about 59 s and keep about 1% fewer
    words. The user keeps 300 dpi (2026-10-12): recognition quality is the bigger problem.
- **Category names.** The user's ruling (2026-10-12): ClassiFile never decides, creates or changes a document's
  own title or name; it only suggests category names and files documents.
  - rules-6, from the first review: lines whose only evidence is repeating on some pages go under "More" (score
    unchanged, so no self-description is declared dominant); DOCX/ODT take only their first qualifying opening
    line; generic words, bare codes, IP addresses, quoted data and academic ranks alone are rejected.
  - Second review (rules-6 names, asked as category names): all 34 files reviewed, no suggested name marked
    good, three category names typed. The first review had marked 21 of largely the same names good, so the
    marks cannot say which level a category should have.
  - rules-7, from the typed names: a numbered list on the cover is the document's contents, not its name; a
    title that exists only inside a picture on the cover is suggested (cleaned OCR text, less weight). Of the
    four files with a typed category, two now show it or its near form in the top three (none before).
  - Against the first review, as a regression check only: 32 top-three names marked not good (76 under rules-5),
    20 of 34 files with a name once marked good (21), 17 names never judged. Development data; not accuracy.
  - What would settle the level: the user's own grouping of the development files (decision record G3), which
    does not exist yet. Filing them in the app with the categories the user wants would provide it.
- **CP3** has not started.

## Next

1. Categories: the user files the 34 development files in the app with the categories they would use (G3).
   Name rules and OCR stay frozen meanwhile.
2. Then a report on those 34 files only: the user's categories and their sizes; per filing, whether a suggestion
   was used as it was, in a near form, or a typed name, with the rank used; the candidate organizing policies
   (E1) against the grouping, over-merging and fragmentation separately. No rule changes before discussing it.
3. CP3 (after the user's go-ahead): scorer comparison (E2) and abstention baseline (E4) on development data,
   selected-category mode with permissions through the queue, "Belongs to" / "Also belongs to", primary
   replacement and edited-copy protection.
4. Later: CP4 automatic mode and discovery, CP5 quality gate and freeze. SummarEase is a separate project.
