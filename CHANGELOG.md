# Changelog

Toutes les évolutions significatives de MARKETIA sont documentées dans ce fichier à partir du 14 septembre 2026.

Le format suit l'esprit de Keep a Changelog et les versions utilisent une numérotation `MAJOR.MINOR.PATCH`.

## [Unreleased]

### Added
- À compléter à chaque évolution avant publication.

## [1.4.0] - 2026-09-14

### Added
- Point de rollback `backup/pre-contact-enrichment-20260914` avant l'évolution du moteur Contacts.
- Paramétrage explicite de la recherche de contacts dans `config.yaml`.

### Changed
- Profondeur de recherche portée à 20 entreprises par run.
- Jusqu'à 4 rôles prioritaires sont recherchés par entreprise.
- Jusqu'à 6 résultats publics sont analysés par requête.
- Budget de recherche Contacts porté à 240 secondes.
- Timeout réseau porté à 6 secondes et circuit breaker à 8 échecs consécutifs.
- La recherche multi-moteurs publics conserve le fallback DuckDuckGo / Bing déjà introduit en version 1.3.0.

### Data quality
- MARKETIA ne génère pas d'adresse email supposée : seules les coordonnées professionnelles présentes dans une source publique accessible sont conservées.

## [1.3.0] - 2026-09-14

### Added
- Moteur de recherche public de secours pour la découverte de contacts : Bing prend le relais quand DuckDuckGo est indisponible, renvoie un 403 ou expire.
- Tests unitaires du parseur Bing et du mécanisme de fallback.

### Changed
- La phase Contacts conserve les mêmes règles de qualification, de rôle, de confiance et d'extraction de coordonnées professionnelles publiques, mais n'est plus dépendante d'un seul fournisseur de recherche.
- Les logs Contacts affichent désormais aussi le nombre de profils LinkedIn détectés.

### Security / Privacy
- MARKETIA ne génère pas d'adresse email supposée et ne marque pas comme confirmée une coordonnée qui n'a pas été explicitement publiée par une source professionnelle publique accessible.

## [1.2.0] - 2026-09-14

### Added
- Nouvelle interface Streamlit homogène organisée en trois espaces : Dashboard, Radar / Discovery et Ciblage.
- Filtres partagés entre Dashboard et Radar pour le pays, l'effectif, le secteur, le besoin probable et la recherche texte.
- Filtres dynamiques avec suppression des options sans résultat et affichage des volumes disponibles.
- Fiche entreprise commune avec besoin probable, confiance, score, angle commercial, contacts, signaux et preuves.
- Page Ciblage regroupant entreprises recherchées, besoins, signaux surveillés, sources et priorisation.
- Tableau de contacts exploitables dans le Dashboard.

### Changed
- Les réglages Secteurs, Marchés, Scoring et Avancé sont regroupés dans la page Ciblage.
- La base SQLite `data/radar.db` n'est plus publiée automatiquement dans GitHub ; les flux JSON, Excel et historiques restent mis à jour.

### Fixed
- Synchronisation des vues Dashboard et Radar.
- Persistance GitHub des sorties sans dépasser la limite de taille de fichier liée à SQLite.
- Limitation du temps de recherche de contacts et circuit breaker en cas d'indisponibilité du moteur de recherche.

## [1.1.0] - 2026-09-10

### Added
- Inférence des besoins commerciaux probables par entreprise.
- Recherche de profils LinkedIn à partir des résultats publics du web.
- Intégration des contacts dans les fiches Radar et Dashboard.
- Filtres Radar dépendants des données réellement présentes.

### Changed
- Dashboard enrichi avec besoin probable, justification, fonctions à cibler et contacts.

## [1.0.0] - 2026-09-01

### Added
- Pipeline MARKETIA : collecte de sources publiques, événements, signaux, enrichissement entreprises, Discovery, qualification, scoring et exports.
- Sources BOAMP, BODACC, TED, Recherche Entreprises, Arbeitnow et GDELT.
- Scoring infrastructure / intention d'achat / timing.
- Exports Excel et JSON pour Streamlit / Grafana.
- Automatisation GitHub Actions.
