from contact_search import _extract_name, _is_blocked, _role_class_for_title, _role_matches


def test_linkedin_is_blocked_from_automated_fetch():
    assert _is_blocked("https://www.linkedin.com/in/jane-doe")
    assert not _is_blocked("https://www.example.com/team/jane-doe")


def test_role_classification():
    assert _role_class_for_title("IT Procurement Manager") == "BUYER"
    assert _role_class_for_title("DSI / CIO") == "DECISION_MAKER"
    assert _role_class_for_title("Head of Infrastructure") == "TECHNICAL_INFLUENCER"


def test_public_evidence_must_match_role():
    text = "Jane Doe, Head of Infrastructure at Example Corp"
    assert _role_matches(text, "Head of Infrastructure", "TECHNICAL_INFLUENCER")


def test_extract_person_name_from_public_result():
    name = _extract_name(
        "Jane Doe - Head of Infrastructure | Example Corp",
        "Jane Doe leads infrastructure operations at Example Corp.",
        "Example Corp",
        "Head of Infrastructure",
    )
    assert name == "Jane Doe"
