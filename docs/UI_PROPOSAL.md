# ClassiFile interface: proposal for the next pass

2026-10-12 · the proposal as written before any change. Phases 1, 2 and 3 have since been built: section 9 says
what phase 1 did and measured, and `docs/STATUS.md` what phases 2 and 3 did. Phases 4 and 5 are not started.

**The short version.** The app is slow and forgetful in one specific way: whenever anything changes, it throws
away the whole window's contents and builds them again. That, not the toolkit, is what makes it feel rough.
Fix that first (Phase 1), keep PySide6 and Qt Widgets, and add motion only afterwards, sparingly.

**How this was measured.** A made-up catalog of 200 documents (140 filed in 30 categories, 60 waiting), the real
window at 1536×864 drawn off-screen with the real fonts, on this laptop. Times include the layout and painting a
change causes. They describe this machine and this catalog; they are not promises. "Observed" means I ran it or
read it in the code; "suspected" means I expect it but did not test it.

---

## 1. The main problems

| # | Problem | Evidence | Status |
|---|---------|----------|--------|
| 1 | **Every document read rebuilds the whole window twice.** Once when reading starts, once when it ends. | `MainWindow._read_done` calls `refresh()` in both branches (`main.py:876`). Importing 20 documents while on "Needs your decision" caused **41 rebuilds; the window was busy for 27.3 of the 27.5 seconds**, 0.67 s at a time. | observed |
| 2 | **A rebuild forgets what you were doing in a card.** | With a card's choices open and text typed, one `refresh()` closed the panel, emptied the field and dropped the cursor. The scroll position survived. | observed |
| 3 | **The decision page is the expensive one.** | One rebuild: **525 ms and 336 database queries** for 60 cards. `DecisionPage.show_items` deletes and recreates every card (`decision.py:292`); each card asks the database for the category list itself (`decision.py:141`). Building one card alone costs 2.3 ms. | observed |
| 4 | **The sidebar is rebuilt with one query per category.** | `_fill_categories` (`main.py:584`): 31 queries, 21 ms at 30 categories, plus one row per document under every category. It also lost its scroll position on every click; that was patched today by putting the position back after the rebuild. | observed |
| 5 | **Notices check the disk for every waiting document on every rebuild.** | `_show_notices` (`main.py:648`): 61 queries and 60 file checks, 14 ms. | observed |
| 6 | **Search rebuilds the list on every key, and only looks at file names.** | `main.py:208` → `_fill_list`: 2 queries and a full rebuild, about 18 ms per key at 200 documents. Not felt at this size; it grows with the library. No Ctrl+F; Esc does not clear it; no result count while searching; an empty list instead of a "nothing found" message; no search on the decision page. | observed |
| 7 | **The page preview is drawn again on every resize step, on the interface thread, and nothing is kept.** | `Preview.resizeEvent` → `show_page` (`widgets.py`). Dragging the divider 20 steps drew the page 19 times. One drawing costs 7 ms (median) to 45 ms at panel width, and **38 ms (median), 101 ms (9 in 10), 125 ms (worst)** at full-window width, over 105 pages of the 14 development PDFs. Paging back draws the page again. | observed |
| 8 | **Motion is ad hoc.** | Two animations with their own numbers (`main.py:237`, `Toast`). The details panel slides by moving a widget its layout owns, which is the pattern to avoid. Nothing animates on close; the toast's timer ignores the mouse; no "reduce motion". | observed |
| 9 | **Half a design system.** | Spacing and six colours are named once in `widgets.py`. Text sizes are not: 18 separate `font-size` values in three files (12, 13, 14, 15, 16, 20, 22, 32). Corner radii: 14 uses of five values (4, 6, 8, 10, 12). | observed |
| 10 | **Screen readers hear symbols.** | No widget has an accessible name (0 uses of `setAccessibleName`); ☰, +, ⋯, ✕, ‹ and › are announced as characters. No keyboard shortcuts are defined (0 `QShortcut`). | observed |
| 11 | **Cards do not adapt to narrow space.** | A card needs 357 px; at 1024 px wide with details open the list has 376 px. It fits by 3 px, and a fourth button (when the suggestion is an existing category) forces sideways scrolling. | observed |
| 12 | **A document that couldn't be read can only be removed.** | The reading code already retries when the same file is imported again (`organizer.record`); there is no button for it. | observed |
| 13 | **Looking up one document loads all of them.** | `document_row` (`main.py:512`) reads every document to find one; details and "Open" call it on each selection. | suspected to matter beyond a few hundred documents; not measured |
| 14 | **Light theme is untested.** | Colours come from the system palette, so it probably works; nobody has looked. | suspected |

**Before and after.** "After" numbers are from small prototypes outside the app, or simple arithmetic; Phase 1
must repeat the measurement with the same script and report real ones.

| What | Now (measured) | After (prototype or expected) |
|------|----------------|-------------------------------|
| 20 imports while on the decision page | 41 rebuilds, 27.3 s busy | 20 single-card additions; about 2.3 ms each to build (measured for one card) |
| One rebuild of the decision page | 525 ms, 336 queries | no full rebuild in normal use |
| Sidebar counts | 15.9 ms, one query per category | 0.4 ms, one query for all (measured) |
| One search key | 18 ms, 2 queries, list rebuilt | 0.2 ms with a filter over the existing rows (measured; the first key 8 ms) |
| Preview while resizing | 7 to 125 ms per step | 0.1 to 0.5 ms per step by scaling the picture already drawn (measured), one real drawing at the end |
| Typed text, open panel and focus in a card after a background read | lost | kept |

---

## 2. Technology: stay with PySide6, Qt Widgets and QSS

| | Keep Qt Widgets + QSS | Widgets + a theme or component library | Qt Quick / QML | Web page in a desktop shell |
|---|---|---|---|---|
| Look | Good enough for a quiet tool; no shadows or blur without effort | A ready-made look, but someone else's; fights our own QSS | The most polished native result | Anything is possible |
| Animation | Sizes, positions and opacity animate well; hover and colour changes in QSS cannot | Same engine underneath | Built for it | Built for it |
| Accessibility | Works with Windows screen readers; we must name our icon buttons | Depends on the library; custom-drawn controls are often unnamed | Works, but every control needs roles and names by hand | Good if the page is written carefully |
| Effort and risk | None to migrate. Phase 1 is a refactor of what exists | Low to adopt, real risk of restyling everything twice | **A rewrite** of about 2,650 lines of interface and its 24 window tests | **A rewrite**, plus a bridge between Python and the page |
| Offline | Yes | Yes | Yes | Yes, but a browser engine arrives with "no network" to enforce |
| Start-up | **0.8 s to a shown window** (measured, off-screen) | About the same | Similar or a little slower (not measured) | Slower; an engine starts first (not measured) |
| Memory | **96 MB** main process (measured) | About the same | Somewhat more (not measured) | Typically a few hundred MB (not measured) |
| Packaged size | The parts we use are about **41 MB** of the 641 MB installed (measured) | Plus the library | Plus about **78 MB** of Quick/QML files (measured) | Plus about **342 MB** for Qt's browser engine (measured), or a separate runtime |
| Licence (repository is AGPL-3.0) | LGPL, compatible | Varies: MIT and BSD are fine; some popular ones are GPL-3.0 for non-commercial use only, which needs reading before use | LGPL, compatible | MIT or LGPL parts, compatible; more notices to carry |
| Maintenance | One language, one styling file | A dependency that can stall; upgrades can change the look | Two languages (Python and QML) | Three (Python, HTML/CSS, JavaScript) and a build step |

**Recommendation: no migration.** None of the measured problems comes from the toolkit. Start-up, memory and
size are fine, and the slowness is our own rebuild-everything code, which would be just as slow in QML. A theme
library would add a dependency to solve a problem (a consistent look) that one token file solves.

**When to reconsider:** for a specific visual or interaction requirement that Widgets cannot reasonably deliver,
or a performance limit measured after optimization. Phase 4 is a natural review point, not a mandatory wait.
Then show the limitation, build one screen (the decision page) in QML as a prototype, and compare it against
the improved Widgets version before deciding.

**The strongest argument against this recommendation.** Qt Widgets has a ceiling. Stylesheets cannot animate
hover or state changes, soft shadows and fluid reflow are laborious, and every card animation must be written by
hand. If you later want a noticeably more modern feel, QML gives it natively, and each month spent polishing
Widgets makes that rewrite more expensive. Staying is the right call only if "clean, spacious and restrained" is
really the goal, as you wrote.

---

## 3. Sketches

**Library (All documents, a category, Recently added)**

```
┌ ClassiFile ───────┐  Physics · 7                                      [ Add documents ]
│ All documents     │
│ Needs decision  4 │  [ Search Physics…                     ]   3 of 7    [Newest ▾] [Details]
│ Recently added    │  ───────────────────────────────────────────────────────────────────
│                   │  Name                              Category              Date added
│ CATEGORIES      + │  ▪ Lecture 3 Waves.pptx            Physics               2026-10-12
│ [Find category… ] │  ▪ Lecture 4 Optics.pptx           Physics               2026-10-12
│ Algebra         3 │  ▪ Problem set 2.pdf               Physics               2026-10-12
│ Physics         7 │
│ Statistics      9 │        (no match:)  Nothing here matches "xyz".  [ Clear search ]
│ ⚙ Settings        │
└───────────────────┘
```

**Decision page**

```
Needs your decision · 4                      [ Search these documents… ]      [ Add documents ]

⋯  ▪ Lecture 5 Sampling.pdf                                        ┌ Details ────────────── ✕ ┐
   Suggested category: Statistics                                  │  ┌──────────────────┐    │
   [ File in Statistics ]  [ Choose another… ]  [ Details ]        │  │   page picture   │    │
                                                                   │  └──────────────────┘    │
⋯  ▪ Tutorial 3.docx                                               │   ‹  Page 1 of 12  ›     │
   Suggested new category: Thermal Expansion · Only one suggestion │  Waiting for a decision  │
   [ Choose category… ]  [ Details ]                               │  › File locations        │
   ┌───────────────────────────────────────────────┐               │  › Why this category?    │
   │ [ Search categories, or type a new name     ] │               └──────────────────────────┘
   │   Statistics · 9                              │
   │   New: Thermal Expansion  (on the cover)      │      "Leave pending" and "Remove" move
   │   None of these fit — type my own             │      into the ⋯ menu: one main action,
   │ [ File ]                                      │      one alternative, one way to look.
   └───────────────────────────────────────────────┘
```

**Search.** One field per page, always in the same place. Its grey text names what it searches ("Search
Physics…", "Search all documents…", "Search these documents…"). It matches file name and category.
Ctrl+F puts the cursor there. Esc clears the text first; a second Esc closes details. Next to it, "3 of 7" while
a search is active. Changing view clears the search, so no hidden text ever filters a page.

**Details.** Beside the content on wide windows; over it on narrow ones. On the decision page it stays beside
the cards (so the buttons stay reachable), and cards stack their buttons when the space is short.

---

## 4. Tokens and motion

One module (`classifile/app/tokens.py`), imported by the style sheet and the widgets. Nothing else may contain a
size, colour or duration.

| Group | Values |
|-------|--------|
| Spacing (kept) | 8 related · 16 group · 20 panel · 24 page and section |
| Text | 12 caption · 13 secondary · 14 body · 16 heading · 22 page title (15, 20 and 32 go) |
| Weights | 400 text · 600 headings, file names and primary buttons |
| Radii | 4 rows and list items · 6 controls · 8 panels and cards · 10 tags (12 goes) |
| Sizes | controls 36 high · rows 44 · icons 16 in text and 20 for files |
| Colour | teal `#0D9488` accent and focus · `#0F766E` primary button, `#115E59` pressed/hover · amber `#D97706` waiting · red `#DC2626` errors · violet `#6C47FF` SummarEase only · everything else from the system palette plus three named greys (border, hairline, tint) |
| Focus | the border turns teal (white on a primary button); no control changes size |
| Appearance | System (default), Light, Dark, in Settings. Qt 6.11 can read and set this without any library (checked) |

| Motion | Value |
|--------|-------|
| Durations | fast 140 ms · standard 180 ms · panel 200 ms · leaving 150 ms |
| Easing | ease-out when something arrives, ease-in when it leaves |
| Details panel | 200 ms open, 150 ms close, by animating the divider's sizes (never a widget's position); clicking again mid-way reverses from where it is |
| Disclosures | 140 ms height |
| Toast | 180 ms in, 150 ms out; the timer pauses while the mouse is over it |
| Filed card | collapses in 150 ms, then the list settles once |
| Never | hover animations, page transitions, bounce, staggered lists, anything per search key |
| Rules | one running animation per target; a new request retargets it instead of queueing; with motion off every duration is 0 |
| Reduce motion | Settings: Follow Windows (default), On, Off. Windows' setting can be read (checked) |

---

## 5. Backlog

**Essential now**
- Stop rebuilding: update one row or one card by document or group ID; keep typed text, open panels, focus and
  scroll. One refresh per document read, not two.
- List and categories as a model with a filter over it; counts from one query.
- Search: file name and category, scope in the grey text, Ctrl+F, Esc, result count, "nothing found" state,
  cleared on view change, present on the decision page.
- Preview: scale while resizing, draw once afterwards, keep recently drawn pages.
- Accessible names and tooltips for every icon button.

**Useful next**
- The token module; Light / Dark / System.
- Cards and action rows that stack when narrow; "Leave pending" and "Remove" into the ⋯ menu.
- The motion module and Reduce motion; details, disclosure, toast and card motion.
- Retry for documents that couldn't be read.
- "Find category…" above the sidebar list when there are more than 10 categories.
- First-use, empty, nothing-found and missing-original states written and checked.

**Defer**
- Filter chips; search inside documents; density settings; the SummarEase entry.
- Drawing pages on a background thread (see "Where I disagree").
- Any toolkit change.

**Where I disagree with the brief**
- **Debounce.** With a filter over existing rows a key costs 0.2 ms. A delay would only make typing feel late. I
  would add none, and add one only if a measurement on a large library asks for it.
- **Drawing pages off the interface thread.** Scaling, drawing once and keeping pages removes almost all of the
  cost. A drawing thread adds real complexity (PyMuPDF documents must not be shared between threads; stale
  results must be discarded). I would do it last and only if a drawing above about 50 ms still happens in normal
  use, which today is the full-window view only.
- **Wrapping action groups.** Qt has no wrapping layout; owning one is about 80 lines to maintain. A row that
  becomes a column below one width is simpler and enough.
- **A second search box in the sidebar** is clutter until there are many categories. Showing it only above 10,
  as you wrote, is right; below that it should not exist.

---

## 6. Phases

Each phase ships on its own with all tests passing, and adds tests for what it changes.

1. **Responsiveness and search.** Problems 1 to 6 and 13. In-place updates keyed by ID; model and filter for the
   list and the sidebar; search as specified; a measuring tool in `tools/` that reproduces the table above.
   Done when: 20 imports cause no full rebuild; a draft survives them; the timings are reported next to today's.
2. **Preview.** Problem 7. Scale, draw once, keep pages. Done when a 20-step resize draws the page once.
3. **Tokens, appearance, accessibility.** Problems 9, 10, 11 and 14. Done when no size or colour literal remains
   outside the token module, both themes are checked at every acceptance size, and every button has a name.
4. **Motion.** Problem 8. The module, Reduce motion, and the five animations. Done when rapid clicks never queue
   and motion off makes every change instant.
5. **Supporting features.** Problem 12, the sidebar find field, and the written states.

---

## 7. Acceptance checks

Run at the end of every phase that touches the window.

- Sizes: 1024×640, 1280×720, 1536×864, 1920×1080 maximized; and 125% and 150% scaling. Nothing clipped, no
  sideways scrolling, no button narrower than its text.
- A 120-character file name: ends in "…", full name on hover, layout unchanged.
- 60 categories: sidebar scrolls and keeps its place; "Find category…" filters without changing the open view,
  and clearing it restores what was expanded.
- Type in a decision card while 20 documents import: the text, the open panel, the cursor and the scroll
  position are all unchanged when the import ends.
- Click Details ten times quickly: the panel ends open or closed to match the last click, with no backlog.
- Keyboard only: reach and operate every action (file, choose, move, rename, delete, details, search, settings)
  without the mouse; focus is always visible.
- Reduce motion on: every change is instant.
- Light and dark: all of the above in both.

---

## 8. Decisions (the owner's, 2026-10-12)

1. **Sidebar.** Categories show their names with counts beside them. The documents under each category, and the
   expand arrows, go; documents are in the main list.
2. **Reduce motion.** The default follows Windows. The owner will switch Windows' animation effects on.
3. **Card actions.** "Leave pending" and "Remove from ClassiFile" move into the ⋯ menu. A card keeps one main
   button, "Choose another…" and "Details", and those two must look as clean as the main button.
4. **Decision page on narrow windows.** Details stay beside the cards; the cards stack their buttons.
5. **Technology.** PySide6, Qt Widgets and QSS stay for the planned improvements. Priorities: consistent
   styling, responsive layouts and fixing the stalls, with Qt's own animation tools for smooth transitions.
   QML is reconsidered if a specific visual or interaction requirement turns up that this stack cannot reasonably
   deliver, or a performance limit is measured after optimization. Phase 4 can be a review point; it is not a
   mandatory wait. Before any migration is proposed, the limitation is shown and a small QML prototype is
   compared against the improved Widgets implementation.
6. **Decision cards, full width (2026-10-13).** A card is as wide as the page: its number in the list, its name
   and suggestion at the left, its buttons at the right. With details open beside the page the buttons go under
   the suggestion. "Details" on a card opens and closes that document's details.
7. **Order (2026-10-13).** CP3 (matching documents to the existing categories) is built before phases 2 and 3.
   Both phases stay queued, with decisions 3 and 4, for after CP3.

---

## 10. Phases 4 and 5 as built (2026-10-14)

- **Phase 4 (motion).**
  - Settings, "Motion": Follow Windows (default), Reduce motion, Full motion.
  - The details panel, a row's choices and the toast were already animated. A filed row now folds away in 150 ms
    while the rows around it keep their places.
  - Rapid clicks never queue (checked: Details ten times). With reduced motion every change is instant (checked by
    `tools.check_ui`, now through the setting).
- **Phase 5.**
  - "Retry" on a document that couldn't be read: the original is read again.
  - "Find category…" above the sidebar's list from 11 categories. It filters by name, says "No category matches …"
    when nothing does, and never changes the open view.
  - The first-use, empty, nothing-found and missing-original states were written in phases 1 to 3.

## 9. Phase 1 as built (2026-10-12)

**What changed**
- **Nothing is rebuilt.** `refresh()` still brings the window in line with the catalog, but in place: decision
  cards are kept while their question is unchanged (`DecisionPage.show_items`), and the document list and the
  sidebar are models that change only the rows that differ (`classifile/app/models.py`). What is typed, opened,
  focused, selected or scrolled to stays.
- **One refresh per document read**, not two; a refresh is five queries whatever the size of the catalog. When
  many reads end together they are taken one per turn of the event loop, so the mouse and keyboard are answered
  in between. A background read no longer looks on disk for every waiting original.
- **Sidebar (decision 1):** category names with counts; no documents under them and no arrows.
- **Search:** one field per page, also on the decision page. It matches file name and category, shows
  "3 of 7" while active, says "Nothing here matches …" with a Clear search button, is cleared when the view
  changes, and reads nothing from the catalog. Ctrl+F puts the cursor in it; Esc clears it, a second Esc closes
  details. No debounce.
- Looking up one document is one query (`Catalog.document_row`).
- Two small things found by the checks and fixed: the list's columns now follow the list's own width (with
  details beside it at 1280 the list used to scroll sideways), and Esc in a card's field leaves the keyboard on
  that card.

**Measured** with `tools.measure_ui`, the same script on the code before and after (200 documents, 60 waiting,
30 categories, 1536×864 off-screen, this laptop; not promises):

| What | Before | After |
|------|--------|-------|
| 20 imports while on the decision page | 2,806 cards built; interface busy 32.0 s of 32.7 s; longest stall 26.0 s | 20 cards built; busy 0.5 s of 0.9 s; longest stall 42 ms |
| Refresh, "Needs your decision" | 510.6 ms, 336 statements | 10.2 ms, 5 statements |
| Refresh, All documents | 57.7 ms, 99 statements | 8.9 ms, 5 statements |
| Refresh, a category | 46.1 ms, 99 statements | 11.0 ms, 5 statements |
| Sidebar | 20.4 ms, 31 statements | 0.4 ms, 2 statements |
| One search key, median of 9 | 16.2 ms, 2 statements | 0.8 ms, none |
| One search key, slowest | 24.8 ms | 19.3 ms (the key that halves the list: it is drawn again once) |
| Text, open panel, cursor and scroll in a card during the imports | lost | kept |

Where this differs from the "after" column of section 1: a search key that changes the list costs one redraw
(about 19 ms), not 0.2 ms; and adding one card costs about 10 ms, not 2.3 ms, because showing it the first
time costs more than building it.

**Acceptance checks** (`tools.check_ui`; 100%, 125% and 150% scaling)
- Pass at every scaling: 1280×720, 1536×864 and 1920×1080 (nothing clipped, no sideways scrolling, buttons
  fit, 120-character names end in "…" with the full name on hover); 60 categories scroll and keep their
  place; Details clicked ten times ends matching the last click; typing in a card while 20 documents import;
  keyboard reach of the search, both lists, details, opening, categories and decision cards.
- **Fails at every scaling: 1024×640, decision page with details beside it** scrolls sideways by 16 pixels.
  This is problem 11, unchanged by this phase; decisions 3 and 4 (phase 3) remove it.
- Not checked by the script: the menu key on a row (it cannot be pressed off-screen); whether focus can be
  seen (the two lists draw no focus mark of their own); light theme. Not built yet: "Find category…" (phase
  5), Reduce motion (phase 4).

**Decisions 2 to 4** belong to later phases as planned: Reduce motion (phase 4), the ⋯ menu and stacked buttons
(phase 3). Decision 5 (stay on Widgets) holds: nothing measured here points at the toolkit.
