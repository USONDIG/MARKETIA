from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd

from database import connect

THEME_META = {
    "Renouvellement / changement d'infrastructure": {
        "angle": "Positionner un audit de l'existant puis une trajectoire de renouvellement serveurs, stockage, réseau et migration.",
        "roles": "DSI / CIO, Head of Infrastructure, IT Operations Manager, IT Procurement Manager",
    },
    "Achat de nouveaux serveurs / compute": {
        "angle": "Positionner une offre serveurs / compute dimensionnée au projet, avec intégration, migration et support.",
        "roles": "Head of Infrastructure, Systems Manager, Datacenter Manager, IT Procurement Manager",
    },
    "Extension de capacité": {
        "angle": "Qualifier les besoins de capacité supplémentaires et proposer une extension compute, stockage et réseau évolutive.",
        "roles": "Head of Infrastructure, IT Operations Manager, Platform Engineering Manager, IT Procurement Manager",
    },
    "GPU / IA / HPC": {
        "angle": "Positionner une architecture GPU/HPC complète : compute accéléré, réseau rapide, stockage et services d'intégration.",
        "roles": "Head of AI Infrastructure, HPC Manager, MLOps Lead, CTO, IT Procurement Manager",
    },
    "Stockage / sauvegarde / PRA": {
        "angle": "Positionner stockage, sauvegarde immuable, PRA et services de migration / sécurisation des données.",
        "roles": "Storage Manager, Backup Manager, Infrastructure Manager, IT Procurement Manager",
    },
    "Réseau / datacenter": {
        "angle": "Positionner switching datacenter, réseau haute performance et accompagnement d'architecture / migration.",
        "roles": "Network Manager, Head of Network, Datacenter Network Architect, IT Procurement Manager",
    },
    "Virtualisation / cloud privé / HCI": {
        "angle": "Positionner une plateforme de virtualisation / cloud privé / HCI avec migration et services d'exploitation.",
        "roles": "Cloud Infrastructure Manager, Virtualization Manager, Platform Engineering Manager, DSI / CIO",
    },
    "Migration / rapatriement cloud": {
        "angle": "Qualifier les coûts et contraintes cloud puis proposer une architecture hybride ou un rapatriement vers infrastructure privée.",
        "roles": "Head of Cloud, FinOps Lead, Cloud Infrastructure Manager, DSI / CIO",
    },
    "Modernisation datacenter / salle IT": {
        "angle": "Positionner une modernisation de salle IT / datacenter incluant compute, stockage, réseau et exploitation.",
        "roles": "Datacenter Manager, Head of Infrastructure, IT Operations Manager, IT Procurement Manager",
    },
    "Support / maintenance / services managés": {
        "angle": "Proposer support, maintenance, services managés et accompagnement opérationnel sur l'infrastructure concernée.",
        "roles": "IT Operations Manager, Infrastructure Manager, DSI / CIO, IT Procurement Manager",
    },
    "Renfort de compétences / recrutement IT": {
        "angle": "Approcher le compte sur les besoins de compétences et de support projet autour de l'infrastructure détectée.",
        "roles": "IT Operations Manager, Head of Infrastructure, Platform Engineering Manager, DSI / CIO",
    },
    "Projet de transformation / nouveau site": {
        "angle": "Qualifier le calendrier du nouveau site / programme de transformation et positionner l'infrastructure dès la phase de conception.",
        "roles": "DSI / CIO, Head of Infrastructure, IT Operations Manager, IT Procurement Manager",
    },
    "Appel d'offres / achat imminent": {
        "angle": "Traiter le compte en priorité : identifier le périmètre, le calendrier, les décideurs et la procédure d'achat.",
        "roles": "IT Procurement Manager, Directeur achats IT, DSI / CIO, Head of Infrastructure",
    },
}


def _entity_key(siren: Any, company_name: Any) -> str:
    if siren and str(siren).strip() and str(siren).lower() != "nan":
        return str(siren).strip()
    return f"NAME::{str(company_name or '').strip().lower()}"


def _add(scores: dict[str, float], evidence: dict[str, list[str]], theme: str, points: float, reason: str) -> None:
    scores[theme] += points
    if reason and reason not in evidence[theme]:
        evidence[theme].append(reason)


def _infer(rows: list[Any]) -> dict[str, Any]:
    scores: dict[str, float] = defaultdict(float)
    evidence: dict[str, list[str]] = defaultdict(list)
    source_set: set[str] = set()
    signal_count = 0

    for row in rows:
        signal_count += 1
        signal_type = str(row["signal_type"] or "").lower()
        label = str(row["label"] or "")
        event_type = str(row["event_type"] or "").lower()
        title = str(row["title"] or "")
        source = str(row["source"] or "")
        source_set.add(source)
        text = f"{label} {title}".lower()

        if event_type == "public_tender" or "appel d'offres" in text or "tender" in text:
            _add(scores, evidence, "Appel d'offres / achat imminent", 34, f"appel d'offres détecté via {source}")
        if any(k in text for k in ["serveur", "server", "compute node", "rack server", "blade"]):
            _add(scores, evidence, "Achat de nouveaux serveurs / compute", 28, "signal serveurs / compute")
        if any(k in text for k in ["gpu", "hpc", "cuda", "nvidia", "accelerator", "accélérateur", "machine learning", "intelligence artificielle", "artificial intelligence"]):
            _add(scores, evidence, "GPU / IA / HPC", 30, "signal GPU / IA / HPC")
        if any(k in text for k in ["stockage", "storage", "backup", "sauvegarde", "disaster recovery", "pra", "san", "nas"]):
            _add(scores, evidence, "Stockage / sauvegarde / PRA", 27, "signal stockage / sauvegarde")
        if any(k in text for k in ["network", "réseau", "reseau", "ethernet", "infiniband", "100gbe", "400gbe", "switch"]):
            _add(scores, evidence, "Réseau / datacenter", 24, "signal réseau datacenter")
        if any(k in text for k in ["virtualisation", "virtualization", "vmware", "proxmox", "hyper-v", "hyperconverged", "hci", "private cloud", "cloud privé", "cloud prive"]):
            _add(scores, evidence, "Virtualisation / cloud privé / HCI", 26, "signal virtualisation / cloud privé")
        if any(k in text for k in ["finops", "cloud repatriation", "rapatriement cloud", "cloud cost", "coût cloud", "cout cloud", "hybrid cloud", "cloud hybride"]):
            _add(scores, evidence, "Migration / rapatriement cloud", 30, "signal FinOps / cloud hybride / rapatriement")
        if any(k in text for k in ["datacenter", "data center", "centre de données", "centre de donnees", "salle informatique", "salle it"]):
            _add(scores, evidence, "Modernisation datacenter / salle IT", 24, "signal datacenter / salle IT")
        if any(k in text for k in ["support", "maintenance", "managed service", "msp", "exploitation", "infogérance", "infogerance"]):
            _add(scores, evidence, "Support / maintenance / services managés", 28, "signal support / maintenance / exploitation")
        if signal_type == "job" or any(k in text for k in ["devops", "site reliability", "sre", "infrastructure engineer", "platform engineer", "sysadmin", "system administrator", "network engineer", "cloud architect", "datacenter engineer", "hpc engineer", "mlops"]):
            _add(scores, evidence, "Renfort de compétences / recrutement IT", 26, "recrutement d'un profil infrastructure / opérations")
        if signal_type == "web_expansion" or any(k in text for k in ["new site", "new facility", "new office", "new factory", "nouveau site", "nouvelle usine", "expansion", "investment", "investissement"]):
            _add(scores, evidence, "Projet de transformation / nouveau site", 28, "expansion / nouveau site / investissement")
            _add(scores, evidence, "Extension de capacité", 18, "croissance ou extension détectée")
        if any(k in text for k in ["replace", "replacement", "renew", "refresh", "modernisation", "modernization", "migration", "remplacement", "renouvellement", "upgrade"]):
            _add(scores, evidence, "Renouvellement / changement d'infrastructure", 30, "renouvellement / migration / modernisation détecté")

    # Cross-signal bonuses: stronger interpretation when several independent clues agree.
    if scores["Projet de transformation / nouveau site"] > 0 and any(scores[t] > 0 for t in [
        "Achat de nouveaux serveurs / compute", "Stockage / sauvegarde / PRA", "Réseau / datacenter", "Modernisation datacenter / salle IT"
    ]):
        _add(scores, evidence, "Extension de capacité", 20, "expansion croisée avec un besoin infrastructure")
    if scores["Appel d'offres / achat imminent"] > 0 and any(scores[t] > 0 for t in [
        "Achat de nouveaux serveurs / compute", "GPU / IA / HPC", "Stockage / sauvegarde / PRA", "Réseau / datacenter", "Virtualisation / cloud privé / HCI"
    ]):
        _add(scores, evidence, "Appel d'offres / achat imminent", 12, "périmètre infrastructure explicite dans l'achat")
    if scores["Renfort de compétences / recrutement IT"] > 0 and any(scores[t] > 0 for t in [
        "Achat de nouveaux serveurs / compute", "GPU / IA / HPC", "Stockage / sauvegarde / PRA", "Virtualisation / cloud privé / HCI", "Réseau / datacenter"
    ]):
        _add(scores, evidence, "Renfort de compétences / recrutement IT", 10, "recrutement cohérent avec le projet infrastructure détecté")

    ranked = sorted(((theme, value) for theme, value in scores.items() if value > 0), key=lambda item: item[1], reverse=True)
    if not ranked:
        return {
            "business_theme": "Besoin infrastructure à qualifier",
            "business_theme_secondary": "",
            "theme_confidence": 25,
            "theme_reason": "Signal commercial détecté mais besoin précis encore insuffisamment documenté.",
            "recommended_angle": "Qualifier le contexte, l'infrastructure actuelle, les projets en cours et le calendrier d'achat.",
            "likely_contact_roles": "DSI / CIO, Head of Infrastructure, IT Procurement Manager",
        }

    primary, primary_score = ranked[0]
    secondaries = [theme for theme, value in ranked[1:3] if value >= max(18, primary_score * 0.35)]
    confidence = min(96, round(42 + min(primary_score, 45) * 0.8 + min(signal_count, 8) * 2 + min(len(source_set), 3) * 3))
    reasons = evidence[primary][:3]
    reason = "; ".join(reasons)
    if len(source_set) >= 2:
        reason += f"; signaux croisés sur {len(source_set)} sources"
    meta = THEME_META.get(primary, {})
    return {
        "business_theme": primary,
        "business_theme_secondary": ", ".join(secondaries),
        "theme_confidence": confidence,
        "theme_reason": reason or "Plusieurs signaux convergents.",
        "recommended_angle": meta.get("angle", "Qualifier le besoin et le calendrier avec le client."),
        "likely_contact_roles": meta.get("roles", "DSI / CIO, Head of Infrastructure, IT Procurement Manager"),
    }


def build_theme_map() -> dict[str, dict[str, Any]]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT e.siren, e.company_name, e.event_type, e.title, e.source,
                   s.signal_type, s.label
            FROM signals s
            JOIN events e ON e.id = s.event_id
            ORDER BY COALESCE(e.event_date, e.collected_at) DESC
            """
        ).fetchall()

    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[_entity_key(row["siren"], row["company_name"])].append(row)
    return {key: _infer(entity_rows) for key, entity_rows in grouped.items()}


def add_business_theme_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    theme_map = build_theme_map()
    out = df.copy()
    inferred = []
    for _, row in out.iterrows():
        key = _entity_key(row.get("siren"), row.get("company_name"))
        inferred.append(theme_map.get(key) or _infer([]))
    for column in [
        "business_theme", "business_theme_secondary", "theme_confidence",
        "theme_reason", "recommended_angle", "likely_contact_roles",
    ]:
        out[column] = [item[column] for item in inferred]
    return out
