from pathlib import Path

import yaml

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


def test_clamp():
    assert clamp(-1) == 0
    assert clamp(42) == 42
    assert clamp(101) == 100
