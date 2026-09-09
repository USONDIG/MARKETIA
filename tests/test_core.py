from pathlib import Path

import yaml

from qualification import employee_info, is_service_naf
from signal_engine import detect_signals
from scoring import clamp


def load_config():
    return yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))


def test_config_has_enabled_markets():
    config = load_config()
    enabled = [m for m in config["markets"].values() if m.get("enabled", True)]
    assert enabled
    assert all("keywords" in market for market in enabled)


def test_signal_detection_for_gpu_tender():
    config = load_config()
    event = {
        "id": "demo",
        "siren": "123456789",
        "company_name": "Demo Infra",
        "source": "BOAMP",
        "event_type": "public_tender",
        "event_date": "2026-09-09",
        "title": "Acquisition de serveurs GPU NVIDIA pour plateforme IA",
        "content": "serveurs gpu nvidia h100 infrastructure de calcul",
        "raw": {"cpv": "30200000"},
    }
    signals = detect_signals(event, config)
    labels = {signal["label"] for signal in signals}
    assert "GPU / HPC / IA" in labels
    assert "Serveurs / Compute" in labels
    assert "Appel d'offres recent" in labels


def test_target_and_employee_qualification_rules():
    config = load_config()
    assert employee_info("12")["employee_min"] == 20
    assert employee_info("21")["employee_min"] == 50
    assert employee_info("42")["employee_min"] == 1000

    # Current target intentionally includes industry, commerce, services,
    # and public administration.
    assert is_service_naf("25.11Z", config)  # Industry
    assert is_service_naf("47.91A", config)  # Commerce
    assert is_service_naf("62.01Z", config)  # IT services
    assert is_service_naf("70.22Z", config)  # Consulting
    assert is_service_naf("84.11Z", config)  # Public administration


def test_clamp():
    assert clamp(-1) == 0
    assert clamp(42) == 42
    assert clamp(101) == 100
