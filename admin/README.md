# MARKETIA — Console d'administration

Cette interface permet d'éditer graphiquement `config.yaml` sans modifier le code à la main.

## Fonctions

- connexion par identifiant / mot de passe
- dashboard MARKETIA natif
- état des derniers runs GitHub Actions
- statut visuel : en attente / en cours / réussi / échoué
- bouton pour actualiser l'état des runs
- bouton pour lancer MARKETIA immédiatement
- relance d'un run terminé depuis l'interface
- seuil minimum d'employés
- familles d'activité et divisions NAF
- pays de siège ciblés
- activation / désactivation des secteurs
- poids des secteurs
- activation / désactivation des marchés
- poids des marchés
- seuils WARM / HOT / CRITICAL
- pondération Infra Fit / Buying Intent / Timing
- enregistrement direct dans `config.yaml`

Chaque enregistrement crée un commit GitHub sur `main`. Le workflow MARKETIA est déjà configuré pour se relancer automatiquement lorsqu'un changement touche `config.yaml`.

## Hébergement recommandé : Streamlit Community Cloud

1. Ouvrir https://share.streamlit.io
2. Se connecter avec GitHub.
3. Cliquer sur **Create app**.
4. Repository : `USONDIG/MARKETIA`
5. Branch : `main`
6. Main file path : `admin/marketia_admin.py`
7. Dans **Advanced settings > Secrets**, ajouter :

```toml
admin_username = "mon_identifiant"
admin_password = "mon_mot_de_passe_long_et_unique"
github_token = "github_pat_xxxxxxxxxxxxxxxxx"
```

8. Déployer l'application.

## Token GitHub recommandé

Créer un **fine-grained personal access token** limité au dépôt `USONDIG/MARKETIA` avec les permissions suivantes :

- Repository permissions > Contents : Read and write
- Repository permissions > Actions : Read and write

`Contents` permet à la console d'enregistrer `config.yaml`. `Actions` permet d'afficher l'état des runs, de lancer MARKETIA immédiatement et de relancer un run depuis Streamlit.

Ne jamais mettre le token, le login ou le mot de passe dans GitHub. Ils doivent rester uniquement dans les Secrets Streamlit.

## Ciblage actuellement autorisé

Le filtre minimum reste fixé à 50 salariés. Les familles autorisées incluent désormais :

- Industrie (NAF 05-39)
- Commerce (45-47)
- Services / tertiaire
- Administration publique (84)

La console permet de modifier cette sélection graphiquement.
