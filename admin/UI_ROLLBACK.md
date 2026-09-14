# MARKETIA UI rollback

Version de référence avant la refonte Dashboard / Radar / Ciblage :

`f61c2761e643c5599450f96cac95136a52fc7d57`

Cette révision correspond à l'état de `main` avant la mise en production de la nouvelle interface unifiée du 14 septembre 2026.

Pour revenir à l'ancienne interface, restaurer les fichiers d'administration depuis ce commit, en particulier `admin/marketia_admin.py`, `admin/dashboard_view.py` et `admin/radar_view.py`, puis retirer les modules UI v2/v3 ajoutés après ce point si souhaité.

Les données et le moteur de collecte/scoring ne font pas partie de cette refonte UI et ne doivent pas être réinitialisés lors d'un rollback d'interface.
