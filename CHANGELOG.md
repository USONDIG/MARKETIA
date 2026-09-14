# Changelog

Toutes les évolutions significatives de MARKETIA sont documentées dans ce fichier à partir du 14 septembre 2026.

Le format suit l'esprit de Keep a Changelog et les versions utilisent une numérotation `MAJOR.MINOR.PATCH`.

## [Unreleased]

### Added
- À compléter à chaque évolution avant publication.

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
- Recherche de profils LinkedIn à partir des résultats publics du web, sans dépendre du crawl direct des pages LinkedIn.
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
