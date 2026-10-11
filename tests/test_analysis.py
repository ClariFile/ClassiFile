import pytest

from classifile.analysis.candidates import analyze, name_key
from classifile.reader import DocumentRecord, read_pdf
from conftest import EXPECT, SAMPLE


def _names(analysis):
    return [s.name for s in analysis.suggestions]


@pytest.fixture
def analyzed(samples):
    return lambda name: analyze(read_pdf(samples / name).record, name)


def test_powerpoint_boilerplate_title_is_not_a_candidate(analyzed):
    a = analyzed(SAMPLE["S2"])
    assert not [s for s in a.suggestions if any(e.source == "metadata_title" for e in s.evidence)]
    assert not [n for n in _names(a) if "PowerPoint" in n]


def test_cover_title_and_repeated_course_line_without_a_winner(analyzed):
    by_name = {s.name: s for s in analyzed(SAMPLE["S1"]).suggestions}
    adv, nde = by_name[EXPECT["S1.cover_title"]], by_name[EXPECT["S1.course_line"]]
    assert [(e.source, e.pages) for e in adv.evidence] == [("first_page", [1])]
    assert [(e.source, e.pages) for e in nde.evidence] == [("recurring", [2, 3, 24])]
    assert adv.score == nde.score  # comparable evidence; the analysis does not pick a winner


@pytest.mark.parametrize("sample", ["S4", "S2", "S3"])
def test_filename_instance_markers(analyzed, sample):
    a, marker = analyzed(SAMPLE[sample]), EXPECT[f"{sample}.marker"]
    assert {"text": marker, "source": "filename"} in a.instance_markers
    assert marker not in _names(a)


def test_filename_tokens_after_instance_removal(analyzed):
    for sample in ("S3", "S4"):
        assert EXPECT[f"{sample}.filename_name"] in _names(analyzed(SAMPLE[sample]))


def _record(first_page, recurring=(), metadata=None):
    return DocumentRecord(format="pdf", unit="page", unit_count=3, metadata=metadata or {}, template_lines=[],
                          recurring_lines=list(recurring), running_lines=[], first_page_lines=list(first_page))


def test_mentions_are_not_candidates():
    a = analyze(_record(["Database Systems", "Prerequisite: Discrete Mathematics", "See also Operating Systems",
                         "References", "Computer Networks", "Signal Processing"]), "notes.pdf")
    assert "Database Systems" in _names(a)
    for n in ("Discrete Mathematics", "Operating Systems", "Computer Networks", "Signal Processing"):
        assert not [x for x in _names(a) if n in x]
    assert len(a.mentions) == 5


def test_a_title_starting_with_reference_is_not_a_mention():
    assert "Reference Architectures" in _names(analyze(_record(["Reference Architectures"]), "x.pdf"))


@pytest.mark.parametrize("line", ["Lecture -9", "Lecture-9", "L-5", "6.3", "Week 3", "Page 1 of 9", "2024-07-07",
                                  "7 July 2024", "Invoice 10023"])
def test_instance_identifiers_alone_are_never_suggested(line):
    a = analyze(_record([line]), "x.pdf")
    assert a.suggestions == [] and a.instance_markers


def test_name_key_punctuation_is_significant():
    assert len({name_key("C"), name_key("C++"), name_key("C#")}) == 3
    assert name_key("Data  &  Networks") == name_key("data and networks")


@pytest.mark.parametrize("name, org", [
    ("Faculty of Applied Science", True), ("Northfield University of Studies", True),
    ("Riverside Technological University", True), ("Department of Chemistry", True),
    ("Database Systems", False), ("Network Planning and Design", False), ("School Management System", False),
])
def test_organisation_lines(name, org):
    from classifile.analysis.candidates import is_organisation_line
    assert is_organisation_line(name) is org


def test_organisation_lines_rank_after_other_candidates():
    a = analyze(_record(["Faculty of Applied Science", "Database Systems"],
                        recurring=[{"line": "Faculty of Applied Science", "pages": [2, 3]}]), "notes.pdf")
    names = [s.name for s in a.suggestions]
    assert names.index("Database Systems") < names.index("Faculty of Applied Science")


@pytest.mark.parametrize("name, shown", [
    ("ADVANCED ROUTING", "Advanced Routing"), ("OSI MODEL AND TCP/IP", "OSI Model and TCP/IP"),
    ("network planning and design", "Network Planning and Design"), ("Projects in C++", "Projects in C++"),
    ("IPv4 addressing", "IPv4 Addressing"), ("introduction to JavaScript", "Introduction to JavaScript"),
])
def test_title_case_keeps_acronyms_and_symbols(name, shown):
    from classifile.analysis.candidates import title_case
    assert title_case(name) == shown


def test_wrapped_cover_lines_are_joined_and_fragments_never_suggested():
    a = analyze(_record(["Department of Chemistry", "Chemistry is the collection of rules and",
                         "methods that describe matter", "Chemical Bonding", "Introduction to the"]),
                "handout 3,2024.pdf")
    names = [s.name for s in a.suggestions]
    assert not any(n.lower().endswith((" and", " the", ",")) or " is " in f" {n.lower()} " for n in names)
    assert names[0] == "Chemical Bonding" and names.index("Department of Chemistry") > 0


@pytest.mark.parametrize("line", ["Hooke's law,", "Laws of motion and", "Chemistry is the study of matter",
                                  "Circuits are networks of components", "Introduction to the"])
def test_fragments_and_sentences_are_rejected(line):
    assert analyze(_record([line]), "x.pdf").suggestions == []


def test_short_names_preferred_over_long_ones_with_equal_evidence():
    a = analyze(_record(["Notes on the Behaviour of Charged Particles in Uniform Magnetic Fields", "Magnetic Fields"]), "x.pdf")
    assert a.suggestions[0].name == "Magnetic Fields"


def test_keyphrase_fallback_when_nothing_on_the_cover_qualifies():
    from classifile.reader import UnitRecord
    text = ("Kirchhoff's current law states that charge is conserved at every junction of an electric circuit. "
            "The electric circuit analysis uses Kirchhoff's voltage law around each loop of the electric circuit.")
    rec = _record(["Chemistry is the collection of rules and"])
    rec.units = [UnitRecord(index=1, kind="page", text=text, native_chars=len(text), text_area=None, image_area=None,
                            nonrepeated_image_area=None, suspected_unread=False, suspect_rule=None)]
    a = analyze(rec, "handout 3,2024.pdf")
    assert a.suggestions and all(e.source == "keyphrase" for s in a.suggestions for e in s.evidence)
    assert any("electric circuit" in s.name.casefold() for s in a.suggestions)


def _top(a):
    from classifile.analysis.candidates import top_names
    return [s.name for s in top_names(a.suggestions)]


def test_people_never_in_the_top_three():
    rec = _record(["Electric Circuits", "Dr. Aye Aye Mon", "Presented by", "Mya Mya", "Ko Ko Aung", "Lecturer"],
                  metadata={"author": "Aung Aung"})
    rec.recurring_lines = [{"line": "Aung Aung", "pages": [2, 3]}, {"line": "U Ba Hla", "pages": [2, 3]}]
    a = analyze(rec, "x.pdf")
    assert _top(a) == ["Electric Circuits"]                        # people only appear under "More"
    more = {s.name: s.demoted for s in a.suggestions}
    assert more["Dr. Aye Aye Mon"] == more["Ko Ko Aung"] == "person"  # honorific; next to "Lecturer"
    assert more["Presented by Mya Mya"] == "person"                 # the wrapped "Presented by" line
    assert more["Aung Aung"] == "person" and more["U Ba Hla"] == "person"  # author metadata; honorific U
    assert "Lecturer" not in more                                  # a role word alone is a label, not a name


def test_institution_lines_go_under_more():
    a = analyze(_record(["Faculty of Applied Computing", "Signal Representation"]), "L3-2 Signal Representation.pdf")
    assert _top(a) == ["Signal Representation"]
    assert any(s.name == "Faculty of Applied Computing" and s.demoted == "institution" for s in a.suggestions)


@pytest.mark.parametrize("line", ["Lecture (5", "Chapter (12)", "Week-3", "Lab 2", "Unit [4]", "Part 1"])
def test_instance_words_with_numbers_in_any_form(line):
    a = analyze(_record([line]), "x.pdf")
    assert a.suggestions == [] and a.instance_markers


@pytest.mark.parametrize("line", ['Network "Security', "Routing (Static", "Subnetting]", "Outline", "Introduction",
                                  "Summary", "References", "Quizzes", "Objectives", "Table of Contents"])
def test_unbalanced_and_generic_lines_are_rejected(line):
    assert analyze(_record([line]), "x.pdf").suggestions == []


def test_lines_that_only_repeat_go_under_more_with_their_score():
    rec = _record(["Signal Representation"], recurring=[{"line": "Sampling Theorem", "pages": [4, 9]}])
    a = analyze(rec, "x.pdf")
    assert _top(a) == ["Signal Representation"]
    (rep,) = [s for s in a.suggestions if s.name == "Sampling Theorem"]
    assert rep.demoted == "repeated" and rep.score == a.suggestions[0].score  # shown under "More"; no winner picked


def test_a_text_document_takes_only_its_first_opening_line():
    rec = _record(["Database Notes", "Types of Keys", "Normal Forms"])
    rec.unit = "block"                                              # DOCX/ODT: no cover page
    assert _names(analyze(rec, "x.docx")) == ["Database Notes"]


@pytest.mark.parametrize("line", ["Example", "Solution", "Expected Output", "■ Example", "Associate Professor",
                                  "ABC-1234", "PC1 – 10.0.0.5", '"Alpha,Beta,Gamma"'])
def test_generic_words_ranks_codes_and_data_are_rejected(line):
    assert analyze(_record([line]), "x.pdf").suggestions == []
    assert analyze(_record([]), "ABC-1234_L2.pdf").suggestions == []  # only a code is left after trimming
