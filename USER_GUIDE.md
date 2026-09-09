# MARKETIA — Guide d'utilisation

## 1. Objectif

MARKETIA collecte automatiquement des signaux commerciaux liés aux infrastructures IT : appels d'offres, événements d'entreprises, recrutements techniques et actualités publiques. Il calcule un score d'opportunité et génère un Excel prêt à exploiter.

## 2. Où trouver les résultats

Le fichier principal est :

`output/server_infra_radar.xlsx`

Le fichier d'alertes simplifié est :

`output/alerts.csv`

## 3. Lancer une collecte immédiatement

Dans GitHub :

1. Ouvrir le dépôt `USONDIG/MARKETIA`.
2. Cliquer sur `Actions`.
3. Sélectionner `MARKETIA Radar`.
4. Cliquer sur `Run workflow`.
5. Choisir la branche `main`.
6. Cliquer sur le bouton vert `Run workflow`.
7. Attendre que le run passe au vert.

Le workflow se lance également automatiquement quatre fois par jour.

## 4. Télécharger l'Excel

Une fois le run terminé :

1. Retourner dans l'onglet `Code` du dépôt.
2. Ouvrir le dossier `output`.
3. Cliquer sur `server_infra_radar.xlsx`.
4. Cliquer sur l'icône de téléchargement / `Download raw file`.
5. Ouvrir le fichier dans Excel.

## 5. Lire les onglets Excel

### Dashboard
Vue synthétique du nombre de leads et des priorités.

### Opportunities
Classement principal des comptes par score décroissant.

Colonnes clés :
- `priority` : CRITICAL, HOT, WARM, WATCH ou LOW
- `opportunity_score` : score global sur 100
- `infra_fit` : adéquation avec les marchés infrastructure
- `buying_intent` : force des signaux d'achat
- `timing` : caractère récent / urgent
- `company_name` : entreprise ou acheteur
- `top_signal` : signal le plus important

### Alerts
Uniquement les opportunités dont le score dépasse le seuil configuré.

### Events
Toutes les informations brutes collectées : appels d'offres, recrutements, actualités, événements BODACC.

### Signals
Détail des mots-clés et catégories détectées par MARKETIA.

### Runs
État de santé de chaque source de données.

## 6. Priorités commerciales

- `CRITICAL` : à traiter immédiatement
- `HOT` : très forte opportunité
- `WARM` : bon prospect à qualifier
- `WATCH` : signal intéressant mais encore faible
- `LOW` : faible priorité

Pour une première utilisation, commencer par l'onglet `Alerts`, puis les premières lignes de `Opportunities`.

## 7. Signaux surveillés

MARKETIA surveille notamment :

- serveurs / compute
- GPU / HPC / IA
- stockage / backup
- virtualisation / private cloud
- réseau datacenter
- datacenter / salles IT
- FinOps / cloud repatriation
- recrutements DevOps, SRE, Infrastructure, GPU, HPC, MLOps, Kubernetes, stockage, datacenter
- investissements et expansions
- nouvelles usines / nouveaux sites
- levées de fonds
- projets IA / cloud privé / infrastructure

## 8. Modifier un marché

Éditer `config.yaml`.

Chaque marché possède :
- `enabled`
- `label`
- `keywords`
- éventuellement des codes `cpv`
- `weight`

Pour désactiver un marché :

```yaml
gpu:
  enabled: false
```

Pour augmenter son importance, augmenter `weight`.

## 9. Modifier le seuil d'alerte

Dans `config.yaml` :

```yaml
alerts:
  minimum_score: 65
  hot_score: 80
  critical_score: 90
```

Baisser `minimum_score` vers 55-60 donnera plus de leads, mais davantage de bruit.

## 10. Sources actuellement actives

- BOAMP : marchés publics français
- BODACC : événements d'entreprises françaises
- TED : marchés publics européens
- Recherche Entreprises : enrichissement SIREN / NAF / établissements
- Arbeitnow : recrutements européens
- GDELT : actualités, projets, investissements et expansion

## 11. Routine recommandée

Chaque matin ou en fin de journée :

1. Télécharger le dernier Excel.
2. Ouvrir `Alerts`.
3. Trier par `opportunity_score` décroissant.
4. Traiter d'abord CRITICAL puis HOT.
5. Consulter `Signals` et `Events` pour comprendre pourquoi le compte est remonté.
6. Utiliser les URLs d'origine pour vérifier le signal avant prospection.

## 12. Interprétation importante

MARKETIA est un moteur de détection et de priorisation, pas une preuve automatique d'intention d'achat. Un score élevé signifie qu'il existe plusieurs indicateurs convergents. Toujours vérifier la source dans `Events` avant une action commerciale.
