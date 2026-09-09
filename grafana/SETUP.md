# MARKETIA — Connexion Grafana Cloud

## Architecture

MARKETIA génère automatiquement les flux suivants :

- `output/grafana/dashboard_stats.json`
- `output/grafana/opportunities.json`
- `output/grafana/events.json`
- `output/grafana/signals.json`
- `output/grafana/runs.json`
- `output/grafana/priority_summary.json`
- `output/grafana/source_summary.json`
- `output/grafana/country_summary.json`
- `output/grafana/market_summary.json`

Les fichiers courants `output/server_infra_radar.xlsx` et `output/alerts.csv` sont conservés.
Chaque run crée aussi un snapshot dans `output/history/YYYYMMDDTHHMMSSZ/`.

## 1. Créer Grafana Cloud

Créer un compte Grafana Cloud Free, ouvrir l'instance Grafana puis aller dans **Connections > Add new connection**.

Rechercher **Infinity** et ajouter/configurer la source Infinity.

## 2. URLs des flux MARKETIA

Base publique :

`https://raw.githubusercontent.com/USONDIG/MARKETIA/main/output/grafana/`

Exemples :

- `https://raw.githubusercontent.com/USONDIG/MARKETIA/main/output/grafana/dashboard_stats.json`
- `https://raw.githubusercontent.com/USONDIG/MARKETIA/main/output/grafana/opportunities.json`
- `https://raw.githubusercontent.com/USONDIG/MARKETIA/main/output/grafana/signals.json`
- `https://raw.githubusercontent.com/USONDIG/MARKETIA/main/output/grafana/events.json`

## 3. Importer le dashboard

Dans Grafana :

1. Dashboards > New > Import.
2. Importer `grafana/marketia-dashboard.json`.
3. Lorsque Grafana demande la datasource `DS_INFINITY`, choisir la datasource Infinity créée précédemment.
4. Enregistrer.

## 4. Si un panneau demande une correction de datasource

Ouvrir le panneau > Edit > Query et vérifier :

- Type : JSON
- Parser : Backend / JSONata ou Default selon la version Infinity
- Source : URL
- Method : GET
- URL : le fichier `raw.githubusercontent.com` correspondant

Le JSON MARKETIA est volontairement un tableau plat pour réduire la configuration nécessaire.

## 5. Historique

La configuration par défaut est :

```yaml
history:
  enabled: true
  retention_days: 30
  archive_excel: true
```

Modifier `retention_days` dans `config.yaml` pour changer la durée de conservation.

Attention : conserver quatre fichiers Excel par jour pendant de longues périodes peut faire grossir fortement le dépôt Git. Pour une conservation longue durée, conserver les JSON/CSV et réduire ou désactiver `archive_excel`.

## 6. Flux recommandés pour les panneaux

- KPI : `dashboard_stats.json`
- Top comptes : `opportunities.json`
- Signaux récents : `signals.json`
- Feed événements : `events.json`
- Répartition priorités : `priority_summary.json`
- Répartition marchés : `market_summary.json`
- Répartition géographique : `country_summary.json`
- Santé pipeline : `runs.json`

## 7. Mise à jour

MARKETIA s'exécute quatre fois par jour. Les fichiers JSON sont réécrits à chaque run et Grafana les relit à chaque rafraîchissement de dashboard.
