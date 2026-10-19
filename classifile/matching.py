"""Matching a document to the existing categories by its content (decision record B4, CP3).

One word-level TF-IDF representation, fitted on the training documents only. Scores rank categories: they are
similarities, never probabilities, and are never shown to the user. Standard library only.
"""
import math
import re
from collections import Counter

from classifile.analysis.candidates import name_key

REPRESENTATION = "words-tfidf-1"   # bump when terms(), fit_idf() or vector() change: stored models are refitted
# Words of two or more characters starting with a letter; a trailing + or # is kept (C++ and C# are not C).
# Numbers alone are left out: page, lecture and invoice numbers say nothing about the subject.
TOKEN = re.compile(r"[a-z][a-z0-9]+[+#]*|[a-z][+#]+")


def terms(text):
    """{word: how often} for a document's full extracted text."""
    return Counter(TOKEN.findall(text.casefold()))


def fit_idf(documents):
    """{word: weight} from the training documents' terms(): rarer words weigh more."""
    n, df = len(documents), Counter(t for d in documents for t in d)
    return {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}


def vector(counts, idf):
    """A document as {word: weight}, length 1. Words the training documents never had are left out; an empty
    result means nothing in the document is known."""
    w = {t: (1 + math.log(c)) * idf[t] for t, c in counts.items() if t in idf}
    norm = math.sqrt(sum(x * x for x in w.values()))
    return {t: x / norm for t, x in w.items()} if norm else {}


def dot(a, b):
    """Cosine similarity of two vector() results: 0 (no word in common) to 1."""
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b[t] for t, x in a.items() if t in b)


class Centroids:
    """Nearest centroid: a category is the average of its documents' vectors; a document's score for it is its
    similarity to that average."""

    def __init__(self, vectors, labels):
        sums = {}
        for v, label in zip(vectors, labels):
            total = sums.setdefault(label, {})
            for t, x in v.items():
                total[t] = total.get(t, 0.0) + x
        self.centroids = {}
        for label, total in sums.items():
            norm = math.sqrt(sum(x * x for x in total.values()))
            self.centroids[label] = {t: x / norm for t, x in total.items()} if norm else {}

    def scores(self, x):
        """{category: similarity, 0 to 1}."""
        return {label: dot(x, c) for label, c in self.centroids.items()}


SCORER = "nearest-centroid-1"
# [Default] An existing category is a good match when it leads the second-best by at least this much (the global
# abstention baseline, E4). Chosen on development data; the user picks the level for automatic filing (Part E).
GOOD_MATCH = 0.02
# Automatic filing (decision record B2): a document is filed without a question when its best category's lead()
# is at least the level in use. The levels were fixed on development data before validation was measured; the
# user chose Strict. The level is a setting ("off" switches automatic filing off), and its changes are recorded.
LEVELS = {"very strict": 0.15, "strict": 0.10, "balanced": 0.06, "lenient": 0.03}
AUTO_DEFAULT = "strict"
AUTO_MIN_CONFIRMED = 3      # no automatic filing into a category with fewer documents the user confirmed
NEAR_TEXT = 0.9     # documents this similar count as versions of one another (a format twin, a revision)
GROUP_LEVEL = 0.15  # [Default] unmatched waiting documents this alike on average form a group (B2); see tools.group_eval
FOLDER_LEVEL = 0.20  # groups this alike become a folder by themselves (B2 "Automatic new folders", record 2.6)
FOLDER_MIN = 3       # and only groups of at least this many (record 2.7): pairs stay a question for the user
AUTO_UPDATE_EVERY = 10  # matching updates by itself after this many new confirmations or moves (A7, record 2.6)


def lead(ranked):
    """How far the best category is ahead of the second: the one number the abstention level is set on."""
    return ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.0) if ranked else 0.0


def train(texts, labels):
    """A model from {document id: text} and {document id: category id}: the bundle a validated version keeps
    (preprocessing, vectorizer, category mapping and decision settings; decision record B4), as plain data."""
    docs = sorted(d for d in labels if texts.get(d))
    counts = [terms(texts[d]) for d in docs]
    idf = fit_idf(counts)
    model = Centroids([vector(c, idf) for c in counts], [labels[d] for d in docs])
    return {"representation": REPRESENTATION, "scorer": SCORER,
            "idf": {t: round(x, 5) for t, x in idf.items()},
            "centroids": {c: {t: round(x, 5) for t, x in v.items()} for c, v in model.centroids.items()},
            "documents": dict(Counter(labels[d] for d in docs)),      # per category, for the reason shown
            "training": dict(labels),       # what it was given; a document without readable text teaches nothing
            "settings": {"good_match": GOOD_MATCH}}


class Matcher:
    """A trained bundle, ready to rank the categories for a document's text."""

    def __init__(self, bundle):
        self.bundle = bundle
        self.model = Centroids([], [])
        self.model.centroids = bundle["centroids"]

    def rank(self, text):
        """[(category id, similarity)], best first. Empty when the text has no word the model knows."""
        return self.rank_counts(terms(text))

    def rank_counts(self, counts):
        """rank() for a document whose terms() are at hand."""
        x = vector(counts, self.bundle["idf"])
        return sorted(self.model.scores(x).items(), key=lambda kv: (-kv[1], kv[0])) if x else []

    def key_words(self, counts, category, n=4):
        """The words a document (its terms()) shares most with a category, heaviest first: the reason a card
        gives. Words found in more than a third of the training documents ("the", a template's standing words)
        say nothing about a subject and are left out (docs/archive/ACCURACY_ROUND.md, section 5)."""
        idf, centroid = self.bundle["idf"], self.model.centroids.get(category, {})
        total = sum(self.bundle["documents"].values())
        floor = math.log((1 + total) / (1 + total / 3)) + 1
        shared = {t: x * centroid[t] for t, x in vector(counts, idf).items() if t in centroid and idf[t] >= floor}
        return [t for t, _ in sorted(shared.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]

    def good(self, ranked):
        """Is the best of these a good match (else: abstain, and suggest a new name)?"""
        return bool(ranked) and lead(ranked) >= self.bundle["settings"]["good_match"]


def record_text(record):
    """A freshly read document's full text, put together as the catalog stores it (Catalog.texts)."""
    return "\n".join(t for u in record.units for t in (u.text, u.notes, u.ocr_text) if t)


def group_vectors(counts, bundle):
    """Waiting documents ({id: terms()}) as vectors for grouping. Word weights come from the model's documents and
    these documents together, so a word the model never saw (a new subject's own vocabulary) counts, and counts
    for much."""
    n, known = sum(bundle["documents"].values()), bundle["idf"]
    df = Counter(t for c in counts.values() for t in c)
    seen = lambda t: (1 + n) / math.exp(known[t] - 1) - 1 if t in known else 0     # fit_idf(), turned round
    idf = {t: math.log((1 + n + len(counts)) / (1 + df[t] + seen(t))) + 1 for t in df}
    return {d: vector(c, idf) for d, c in counts.items()}


def similar_groups(vectors, level):
    """Groups of at least two among {document id: vector}, for waiting documents that match no existing category
    (decision record B2: the narrow exception to the clustering deferral). Each document starts alone; the two
    groups whose documents are most alike on average are joined, again and again, while that average similarity
    is at least `level`. Returns lists of ids, largest first; documents left alone are not returned."""
    groups = [[d] for d in sorted(vectors)]
    sim = {(a, b): dot(vectors[a], vectors[b]) for a in vectors for b in vectors if a < b}
    between = lambda g, h: sum(sim[min(a, b), max(a, b)] for a in g for b in h) / (len(g) * len(h))
    while len(groups) > 1:      # ponytail: every pair of groups each round; fine for the tens of documents waiting
        score, i, j = max((between(g, h), i, j) for i, g in enumerate(groups) for j, h in enumerate(groups) if i < j)
        if score < level:
            break
        groups[i] += groups.pop(j)
    return sorted((sorted(g) for g in groups if len(g) > 1), key=lambda g: (-len(g), g))


def shared_words(vectors, n=6):
    """The words that say what a group's documents have in common: in most of them, heaviest first."""
    need = max(2, -(-len(vectors) * 3 // 5))        # at least 60% of the documents, and never fewer than two
    weight, seen = Counter(), Counter()
    for v in vectors:
        for t, x in v.items():
            weight[t] += x
            seen[t] += 1
    return [t for t, _ in sorted(weight.items(), key=lambda kv: (-kv[1], kv[0])) if seen[t] >= need][:n]


def group_name(suggested, taken):
    """The name for a folder the app creates for a group (B2, record 2.6): a name suggested for several of the
    group's documents (for the most documents first), otherwise the best suggested name. suggested: per document,
    its top suggestions ({"name", "score"}), best first; taken: name_key()s of the existing categories, never
    reused or merged into (B1). None when no name is free: the group stays a question."""
    docs, score, name = Counter(), Counter(), {}
    for mine in suggested:
        for s in {name_key(s["name"]): s for s in mine}.values():
            k = name_key(s["name"])
            docs[k] += 1
            score[k] = max(score[k], s["score"])
            name.setdefault(k, s["name"])
    ranked = sorted(docs, key=lambda k: (-(docs[k] > 1) * docs[k], -score[k], k))
    return next((name[k] for k in ranked if k not in taken), None)
