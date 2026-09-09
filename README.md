# MARKETIA — Infrastructure Opportunity Radar

Radar commercial autonome pour détecter les entreprises françaises et les marchés européens susceptibles d'investir dans des serveurs, GPU, stockage, réseau, virtualisation, private cloud et infrastructure datacenter.

## Principe

Le pipeline collecte des sources publiques, normalise les événements, détecte les signaux d'achat, calcule trois scores (`infra_fit`, `buying_intent`, `timing`) puis génère automatiquement `output/server_infra_radar.xlsx`.

## Sources

- BOAMP : marchés publics français
- TED : marchés publics européens
- BODACC : événements d'entreprises françaises
- API Recherche d'Entreprises : enrichissement par SIREN / raison sociale

## Ajouter un secteur ou un marché

Tout se fait dans `config.yaml`. Aucun changement de code n'est nécessaire.

```yaml
sectors:
  - id: robotics
    enabled: true
    label: Robotique
    keywords: [robotique, robotics, autonomous robot]
    weight: 15

markets:
  backup:
    enabled: true
    keywords: [backup, sauvegarde, disaster recovery, immutable backup]
    weight: 25
```

## Automatisation

Le workflow `.github/workflows/radar.yml` s'exécute automatiquement quatre fois par jour et peut aussi être lancé manuellement depuis GitHub Actions.

## Sorties

- `data/radar.db` : base SQLite persistante
- `output/server_infra_radar.xlsx` : cockpit Excel
- `output/alerts.csv` : opportunités au-dessus du seuil d'alerte

## Exécution locale

```bash
python -m pip install -r requirements.txt
python main.py
```

Le projet n'utilise volontairement aucun service payant ni clé API obligatoire dans sa version de base.
