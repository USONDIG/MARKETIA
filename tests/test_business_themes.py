from business_themes import _infer


class Row(dict):
    def __getitem__(self, key):
        return self.get(key)


def test_tender_server_need_is_purchase_or_server():
    rows = [
        Row(signal_type="market", label="Serveurs / Compute", event_type="public_tender", title="Achat de serveurs rack", source="TED"),
        Row(signal_type="market", label="Stockage / Backup", event_type="public_tender", title="Serveurs et stockage", source="TED"),
    ]
    result = _infer(rows)
    assert result["business_theme"] in {"Appel d'offres / achat imminent", "Achat de nouveaux serveurs / compute"}
    assert result["theme_confidence"] >= 60
    assert result["recommended_angle"]
    assert result["likely_contact_roles"]


def test_job_signal_maps_to_people_need():
    rows = [
        Row(signal_type="job", label="Infrastructure Engineer", event_type="job", title="Senior Infrastructure Engineer", source="Arbeitnow"),
    ]
    result = _infer(rows)
    assert result["business_theme"] == "Renfort de compétences / recrutement IT"


def test_expansion_plus_infra_detects_capacity_theme():
    rows = [
        Row(signal_type="web_expansion", label="Expansion", event_type="news", title="New facility expansion", source="GDELT"),
        Row(signal_type="market", label="Serveurs / Compute", event_type="news", title="New server infrastructure", source="GDELT"),
    ]
    result = _infer(rows)
    themes = {result["business_theme"], *[x.strip() for x in result["business_theme_secondary"].split(",") if x.strip()]}
    assert "Extension de capacité" in themes or "Projet de transformation / nouveau site" in themes
