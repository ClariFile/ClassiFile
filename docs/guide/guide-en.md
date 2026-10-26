# ClassiFile user guide

ClassiFile puts copies of your documents into folders by what they say. It does it by itself when it is sure, and
asks you when it isn't. Your own files are never changed, and nothing goes on the internet.

## 1. The first start

- A short tour explains the basics. You can see it again from **Help**.
- ClassiFile asks for an **output folder**. This is where it puts the organized copies. Choose an empty folder, for
  example `Documents\ClassiFile`.

## 2. Start with what you already have

If you already keep documents in folders (one folder for each subject), ClassiFile can learn from them first.

1. Press **Learn from my existing folders…** (in the tour, on the start page, or in **Settings**).
2. Choose the folder that holds your subject folders.
3. ClassiFile shows each folder with how many documents it holds.
   - **Untick** folders that are not a subject, such as "New folder" or "Downloads".
   - **Rename** a category if you want a different name.
4. Press **Learn from … documents**.

Your files are only read. Nothing is moved, copied or changed. You can forget a folder later in **Settings**.

## 3. Add documents

Drop files on the window, or press **Add documents**. ClassiFile reads PDF, PowerPoint (PPTX), Word (DOCX) and
OpenDocument (ODT) files.

After reading, each document either:
- **is filed by itself**, when one category clearly fits and already holds 3 documents you confirmed; or
- **waits for you** in **Needs your decision**.

While documents are being read, **Stop** (beside "Reading 3 of 12…") lets the ones being read finish and leaves the
rest unread. They are counted as "not read (stopped)", not as problems; add them again later.

## 4. Needs your decision

Each waiting document shows the categories that fit best, and why.

- Press **File in …** to accept the first choice.
- Press another category name to choose it instead.
- Press **Choose another…** to pick any category, or type a new name.
- Press **Details** to see the document's pages.

"Best match: compared with 5 examples in Garden; shares compost, soil" means ClassiFile compared the document with
the 5 documents you put in Garden, taken together, and found those words in common. The other choices say
"Weaker match", and "no words in common" when they share none.

If some pictures in a document couldn't be read, its card says on which pages. ClassiFile never files such a
document by itself, because the unread part might be what it is about. Look at the pages in **Details** and choose,
or try **⋯ → Read again**.

When several documents look like one new subject, they are shown together. Type one name for all of them.

## 5. Filed automatically

This page lists what ClassiFile filed by itself, with the reason.

- If it is right, press **Looks right**. ClassiFile learns from that.
- If it is wrong, press **Move to…** and choose the right category.

## 6. Moving and renaming

- **Move to…** (right-click a document) puts it in another category. The new copy is made first; the old copy is
  removed only if you didn't change it.
- **Rename** and **Delete** a category from its right-click menu. Only empty categories can be deleted.

## 7. New folders

When at least three waiting documents share a subject that none of your categories covers, ClassiFile can make a
new folder for them and name it. It is marked "New". Rename it if you like. You can switch this off in **Settings**.

## 8. Check these

Sometimes a filed document reads much more like another category. It appears under **Check these**, at the top of
**Needs your decision**. Press **Keep here** or **Move to…**. Nothing moves unless you choose.

## 9. Settings

- **Automatic filing:** how sure ClassiFile must be before it files by itself. **Strict** is the default. "Off"
  means it always asks.
- **Learning:** learn from your folders, or update now. Each folder you learned from says how many of its files
  couldn't be read or were already in ClassiFile; **Details…** names them and can try the unreadable ones again.
- **Output folder**, **Appearance** (light or dark) and **When closing**.
- **Advanced:** version numbers and the learning log, useful when you report a problem; **Back up the catalog…**
  and **Restore a backup…** (section 12).
- The **☰** at the top of the sidebar hides it; the **☰** before the page title brings it back.

## 10. What never happens

- Your original files are never changed, moved, renamed or deleted.
- Nothing is written into any document.
- Nothing is sent over the internet.

## 11. Good to know

- ClassiFile works best with English documents for now.
- It needs about 3 documents in a category before it files there by itself, and works better with 5 or more.
- Photos (JPG, PNG) can't be added yet.

## 12. Installing, updating and removing

- **Windows protected your PC:** when you run the setup file, Windows may show this blue SmartScreen box, because
  ClassiFile is new. Click **More info**, then **Run anyway**.
- **Updates:** **Help → Check for updates** opens the download page in your browser. ClassiFile never checks by
  itself.
- **Uninstall:** Windows **Settings → Apps → Installed apps** → ClassiFile → **⋯ → Uninstall**. Your original files,
  the organized copies in your output folder and ClassiFile's catalog (`%LOCALAPPDATA%\ClassiFile`) stay.

### Backing up what ClassiFile has learned

Your categories, your choices and what matching learned are kept in ClassiFile's catalog, not in your documents.
Copies in your output folder alone don't bring them back.

- **Back up:** **Settings → Advanced → Back up the catalog…** saves it to a new file you choose, for example on a USB
  stick or in your usual backups. It can be done while ClassiFile is open.
- **Restore:** **Settings → Advanced → Restore a backup…** checks the file first, then switches to it the next time
  ClassiFile opens. The catalog in use until then is kept beside it ("catalog before restore …"), never deleted.
  Your documents and the copies in your output folder are not touched; a copy you changed since the backup is
  flagged, never overwritten.

## 13. Reporting a problem

**Help → Copy problem report…** shows a short report first: version numbers, counts, settings and the last problems.
It has no file names and nothing from your documents. Press **Copy** and paste it into a message. Never send your
documents themselves.
