from contacts import MARKET_ROLE_MAP, ROLE_LIBRARY


def test_contact_role_library_covers_core_buying_roles():
    assert "buyer" in ROLE_LIBRARY
    assert "decision_maker" in ROLE_LIBRARY
    assert "technical_influencer" in ROLE_LIBRARY
    assert any("Procurement" in role or "achats" in role for role in ROLE_LIBRARY["buyer"])


def test_contact_role_library_covers_markets():
    expected = {
        "Serveurs / Compute",
        "GPU / HPC / IA",
        "Stockage / Backup",
        "Virtualisation / Private Cloud",
        "Reseau Datacenter",
        "Datacenter / Salle IT",
        "FinOps / Cloud Repatriation",
    }
    assert expected.issubset(MARKET_ROLE_MAP.keys())
