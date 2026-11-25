from linked_pubs.grounding import locate_quote

TEXT = "Background:  Vitamin D deficiency is common.\nThe PRI for iron is 16 mg/day in women aged 18–50 years."


def test_exact_match_maps_to_source_offsets():
    m = locate_quote("Vitamin D deficiency is common", TEXT)
    assert m is not None and m.score == 1.0
    assert TEXT[m.start:m.end] == "Vitamin D deficiency is common"


def test_tolerates_case_whitespace_and_dashes():
    m = locate_quote("the PRI for iron is 16 mg/day in women aged 18-50   years", TEXT)
    assert m is not None and m.score == 1.0
    assert TEXT[m.start:m.end].startswith("The PRI")
    assert TEXT[m.start:m.end].endswith("years")


def test_fuzzy_match_small_difference():
    m = locate_quote("The PRI for iron is 16 mg per day in women aged 18-50 years", TEXT)
    assert m is not None and 0.9 <= m.score < 1.0


def test_rejects_invented_quote():
    assert locate_quote("Zinc intake above 40 mg/day is toxic", TEXT) is None


def test_rejects_changed_number():
    # A wrong number in a long quote can still pass fuzzy matching; a short one must not.
    assert locate_quote("16 mg/day", TEXT) is not None
    assert locate_quote("61 mg/day", TEXT) is None
