from app.services.clauses import split_clauses
from app.services.pdf import PageText


def test_numbered_headings_become_clauses_with_titles_and_pages() -> None:
    pages = [
        PageText(
            1,
            "SERVICES AGREEMENT\n\n1. Parties. This agreement is between A and B.\n"
            "2. Data Retention. Vendor keeps records for\n12 months after termination.",
        ),
        PageText(2, "3. KYC Updates. Vendor refreshes KYC every ten years.\nMore detail here."),
    ]

    clauses = split_clauses(pages)

    assert [(c.id, c.title, c.page) for c in clauses] == [
        ("c1", "1. Parties", 1),
        ("c2", "2. Data Retention", 1),
        ("c3", "3. KYC Updates", 2),
    ]
    assert clauses[1].text.endswith("12 months after termination."), "wrapped lines stay in clause"
    assert "More detail here." in clauses[2].text


def test_clause_section_and_article_headings_are_recognised() -> None:
    pages = [
        PageText(
            1, "Clause 1: Scope of work\nText.\nSection 2 - Fees\nText.\nARTICLE 3. Term\nText."
        )
    ]

    titles = [c.title for c in split_clauses(pages)]

    assert titles == ["Clause 1: Scope of work", "Section 2 - Fees", "ARTICLE 3. Term"]


def test_sub_numbered_headings_used_when_there_are_no_top_level_ones() -> None:
    pages = [PageText(1, "1.1 Confidentiality applies.\nDetail.\n1.2 Retention for five years.")]

    clauses = split_clauses(pages)

    assert [c.title for c in clauses] == [
        "1.1 Confidentiality applies",
        "1.2 Retention for five years",
    ]


def test_paragraph_fallback_for_unnumbered_contracts() -> None:
    para = "The vendor shall protect customer data and follow all applicable rules. " * 6
    pages = [PageText(1, f"{para}\n\n{para}"), PageText(2, para)]

    clauses = split_clauses(pages)

    assert len(clauses) == 3
    assert [c.page for c in clauses] == [1, 1, 2]
    assert clauses[0].title.endswith("…")


def test_clause_count_is_capped() -> None:
    text = "\n".join(f"{n}. Heading {n}. Body." for n in range(1, 41))
    assert len(split_clauses([PageText(1, text)], max_clauses=30)) == 30
