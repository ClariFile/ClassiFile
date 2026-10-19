> Archived (2026-10-19): finished; kept as history. Current state: docs\STATUS.md.

# Accuracy round: can the matcher be made better without more documents?

2026-10-13 · a report for the owner. Nothing in the app was changed. Counts describe development data (and, in
section 4, validation data); they are not accuracy estimates. Categories are named by their size here; the report
with their names is local (`data\accuracy_round.txt`). `data\final-eval` was not read.

**The short answer.** No single change clearly beats the matcher in use. One combination is a little better and
not worse anywhere on validation. What moves the numbers far more is how many documents a folder holds.

## 1. How it was measured

The same test as E2 (`tools.accuracy_round`): the 83 filed development documents (78 families, 11 categories since
the owner made one more), each family held out in turn, nearest centroid, the vocabulary fitted on the rest. 81
documents have a category with other families. "Strict" is the level in use for automatic filing (the best
category leads the second by 0.10). Because a change to the representation also changes what a lead of 0.10
means, the table adds the most documents filed right while at most one is filed wrong, at whatever level that is.
"New subjects" holds each category out whole: all 83 documents are then of a subject never seen, and filing any
of them is wrong.

## 2. One change at a time

| Change | Right first (of 81) | In the first three | Filed right / wrong at Strict | New subjects filed (of 83) | Filed right with at most 1 wrong |
|---|---|---|---|---|---|
| **In use** | 64 | 77 | 43 / 2 | 3 | 34 |
| a. Titles, headings, first page ×2 | 64 | 77 | 45 / 2 | 3 | 35 |
| a. ×3 | 64 | 77 | 45 / 2 | 3 | 35 |
| a. ×5 | 64 | 77 | 45 / 2 | 3 | 37 |
| b. Character 3- to 5-grams, 30% of the similarity | 63 | 77 | 40 / 2 | 2 | 33 |
| b. 50% | 61 | 76 | 39 / 2 | 2 | 33 |
| c. Word pairs | 63 | 78 | 39 / 2 | 2 | 36 |
| d. OCR text at half weight | 65 | 77 | 44 / 2 | 3 | 35 |
| d. No OCR text | 64 | 76 | 45 / 2 | 3 | 39 |
| d. Template lines left out | 63 | 76 | 44 / 2 | 4 | 32 |
| d. OCR at half weight, template lines left out | 63 | 76 | 45 / 3 | 4 | 33 |
| f. Words found in more than half of the documents left out | 67 | 76 | 47 / 3 | 6 | 36 |
| f. More than a third | 67 | 77 | 44 / 4 | 7 | 35 |

- **a, c and d move one or two documents either way.** That is within what a different handful of documents
  would change.
- **b (character n-grams) is slightly worse** and several times slower.
- **f was not on the list.** The key words (section 5) showed matches resting on "the", "of" and the standing
  words of a cover page, so leaving very common words out was tried. It puts the right category first for 3
  more documents, and takes new subjects for known ones a little more often (6 or 7 of 83 instead of 3).

## 3. Combinations

| Combination | Right first | In the first three | Filed right / wrong at Strict | New subjects filed | Filed right with at most 1 wrong |
|---|---|---|---|---|---|
| In use | 64 | 77 | 43 / 2 | 3 | 34 |
| Head ×3, OCR at half weight | 65 | 77 | 45 / 2 | 3 | 37 |
| **Head ×3, OCR at half weight, common words (over half) left out** | 67 | 76 | 49 / 2 | 5 | 38 |
| Head ×3, OCR at half weight, common words (over a third) left out | 67 | 77 | 47 / 3 | 6 | 36 |
| Head ×2, template lines left out | 62 | 76 | 45 / 2 | 3 | 32 |
| Head ×2, character n-grams 30% | 62 | 76 | 40 / 2 | 2 | 36 |

**Recommended: head ×3, OCR at half weight, words found in more than half of the documents left out.** Against
the matcher in use: 3 more documents right first, 6 more filed right at Strict with the same 2 wrong, 1 fewer in
the first three, and 2 more new-subject documents filed (5 of 83). A small and mixed gain, not a clear one.

Per category, in use → recommended (first / in the first three / filed right at Strict / filed wrong):

| Category (documents) | In use | Recommended |
|---|---|---|
| 30 | 27 / 30 / 23 / 1 | 27 / 30 / 22 / 1 |
| 11 | 8 / 11 / 0 / 0 | 8 / 11 / 4 / 0 |
| 10 | 9 / 10 / 8 / 0 | 9 / 10 / 9 / 0 |
| 8 | 6 / 8 / 5 / 0 | 7 / 7 / 5 / 0 |
| 7 | 6 / 6 / 5 / 0 | 6 / 6 / 5 / 0 |
| 6 | 3 / 6 / 0 / 0 | 4 / 6 / 1 / 0 |
| 4 | 2 / 3 / 1 / 0 | 3 / 3 / 2 / 0 |
| 3 | 1 / 1 / 0 / 0 | 1 / 1 / 0 / 0 |
| 2 | 2 / 2 / 1 / 0 | 2 / 2 / 1 / 0 |
| 1 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| 1 | 0 / 0 / 0 / 1 | 0 / 0 / 0 / 1 |

The two single-document categories cannot be found when their only document is held out.

## 4. Validation, measured once

The rule was set before looking: adopt the combination only if, on validation, it is at least as good as the
matcher in use on "right first" and on "wrong at Strict", and better on one of them. Both were trained on the 83
development documents (11 categories) and asked for the 23 validation documents in one run
(`data\validation_accuracy_round.json`, local; the tool refuses a second run).

| | Right first | In the first three | Filed at Strict | Of those wrong | Waiting |
|---|---|---|---|---|---|
| In use | 19 | 23 | 14 | 0 | 9 |
| Recommended | 20 | 23 | 14 | 0 | 9 |

The rule is met, by one document. (The earlier validation figure of 21 right first was with 10 categories; the
owner has since split one two-document folder off the largest, and both of its validation documents now have to
be told apart from it.)

## 5. Which folders are taken for which

Documents whose category did not come first (17 in use, 15 with the recommended combination), by size of folder:

| The owner's folder → taken for | In use | Recommended |
|---|---|---|
| 11 → 6 | 3 | 3 |
| 8 → 30 | 2 | 1 |
| 4 → 30 | 2 | 1 |
| 6 → 30 | 2 | 1 |
| every other pair | 1 each | 1 each |

- The largest folder draws documents from the smaller ones: it has seen the most general words.
- The 11- and 6-document folders share a cover page's standing words (the same institution's template), and three
  documents go the wrong way between them whatever the representation.

**A better reason on the cards (change e).** The words a document shares most with its best folder are a good
reason when common words are left out: for example "ip, router, network, traffic" or "memory, cache, processor",
instead of "the, of, and". For a wrong match the shared words turn vague ("current, good, potential"), which is
itself a warning. It changes no filing decision. Recommended: show two to four such words after "Similar to N
documents in …".

## 6. Folders with fewer than 5 documents

Five folders: 4, 3, 2, 1 and 1 documents.

**More documents help most.** Taking a larger folder and letting it keep only k of its documents:

| Folder (documents) | k = 1 | k = 2 | k = 3 | k = 5 |
|---|---|---|---|---|
| 30 | 9 of 90 right first | 35 | 54 | 74 |
| 11 | 0 of 33 | 2 | 6 | 17 |
| 10 | 10 of 30 | 22 | 25 | 27 |
| 8 | 13 of 24 | 16 | 15 | 18 |

A folder with one or two documents is rarely found; from about five it mostly is. No change to the representation
comes near this.

**Merging helps on paper only.** Putting a small folder into the folder its documents are most taken for raises
"right first" from 64 to 65 or 66, because those documents then count as right in the big folder. Nothing is
matched better; a distinction the owner made is lost. It is worth it only where the owner sees the small folder
as part of the larger one anyway (one single-document folder reads like a lesson of the 7-document folder).

**Advice per folder:** add documents to the 4-, 3- and 2-document folders until each has five or more; leave the
two single-document folders as they are, or move their document if it belongs elsewhere. Automatic filing
already waits for 3 confirmed documents, so small folders cause questions, not wrong filings.

## 7. Small local embeddings (not added; no new dependency in this round)

Worth a test later, not now. They could help exactly where words fail: folders that share a template, and
subjects described in different words. They would not fix folders with one or two documents. Approximate install
sizes, from memory and not measured here:
- a small sentence model run with ONNX Runtime: about 150 to 200 MB (the runtime, a tokenizer, NumPy and a model
  of about 90 MB, or about 25 MB if quantized);
- the same model through PyTorch: about 700 MB to 1 GB.
The record defers additional representations (F, E3), so this needs the owner's decision first.

## 8. What I recommend

1. Adopt the recommended combination (a new model version through "Update matching", checked against the one in
   use as always). The gain is small; nothing measured got worse on validation.
2. Add the key-word reason to the cards.
3. Add documents to the three small folders. This is the change that matters.
4. Leave embeddings for a later round.

## 9. Checked on new files (2026-10-14): not adopted; the matcher was retrained instead

The owner imported 33 new files (none is a byte copy of a file in any split) and ran the app at Strict: 21 were
filed automatically and 12 waited. The owner kept 20 of the 21, moved 1, and filed the 12. 5 of the 33 are of a
subject the owner made a new folder for, so 28 have a category that existed before.

These files came after section 8, so they test it fairly. Both representations were trained on the 83 earlier
documents (11 categories) and asked about the 33:

| | Right first (of 28 whose category existed) | Filed at Strict: right / wrong | New-subject files filed (of 5) |
|---|---|---|---|
| In use | 28 | 20 / 1 | 1 |
| Recommended combination | 28 | 19 / 1 | 1 |

- **No gain.** The matcher in use already put the owner's category first for all 28 known files. The one wrong
  filing is a new-subject file taken for the largest folder (lead 0.109, just over Strict). The other four
  new-subject files waited, as they should.
- **The 8 known files that waited** had leads from 0.06 to 0.10, all with the right category first.
- **The same comparison on all 116 documents** (families held out in turn, as in section 2): the combination puts
  3 more first (97 against 94 of 114), but at Strict it files 5 wrong against 3, and takes 9 of 116 new-subject
  documents for known folders against 5. That is worse on exactly what Strict protects.
- **Decision for the matcher:** recommendation 1 (section 8) is withdrawn. The representation stays as it is.

**What did help: learning from the 33.** "Update matching" (the app's own check, done with the app closed and a
copy of the catalog kept) trained version 3 on 116 documents in 12 categories. Each of the 33 was asked of a
version trained without it: the owner's category first for 32, against 28 for version 2. Most of the gain is the
new folder, which version 2 could not know. Version 2 is kept as the previous version.

These counts describe development data and the owner's own run. They are not accuracy estimates.

## 10. Since 2026-10-15

Every number about matching now comes from one evaluation (`tools.evaluate`, `docs/STATUS.md`); the tables above
came from `tools.accuracy_round` and are kept as history, not to be compared one to one. Matching version 4 (118
documents) replaced version 3 on 2026-10-14. The safer filing rules tried on 2026-10-15 (a minimum similarity; the
best folder among the nearest documents) are in `docs/STATUS.md`; none was adopted.
