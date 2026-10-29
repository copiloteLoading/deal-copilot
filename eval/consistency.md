# Test de cohérence : Muse Spark seul contre le modèle

10 contrats, réunions [2, 4], 20 points de test. Veto testé : celui de plus forte influence. Muse Spark : effort « low », 5 tirages.

| Mesure | Muse Spark seul | Modèle |
|---|---|---|
| **Stabilité** : écart moyen entre le plus haut et le plus bas de 5 tirages | 6 pts | 0 pts |
| Écart maximal sur 5 tirages | 12 pts | 0 pts |
| Points où le chiffre bouge d'au moins 10 pts sans nouvelle information | 15% | 0% |
| **Monotonie** : « contre » < aujourd'hui (moyenne des tirages) < « pour » | 45% | 100% |
| Ordre inversé (« contre » ≥ « pour ») | 0% | 0% |
| Effet moyen de « je suis contre » | -25 pts | -8 pts |
| Effet moyen de « je soutiens » | -1 pts | +5 pts |
| **« Et si ? »** : écart moyen entre deux formulations de la même hypothèse | 7 pts | 0 (par construction) |
| Écart maximal entre deux formulations | 22 pts | 0 |
| « Et si ? » dans le bon sens | 70% | 100% |

## Détail

| Contrat | Réunion | Muse Spark : 5 tirages | contre / pour | et si contre / et si pour (2 formulations) | Modèle : base, contre / pour |
|---|---|---|---|---|---|
| 01_cable_sous_marin_aurore_liaison_brume_va | 2 | 20% 30% 18% 22% 25% | 14% / 18% | 0% 6% / 62% 72% | 12%, 7% / 21% |
| 01_cable_sous_marin_aurore_liaison_brume_va | 4 | 84% 82% 85% 85% 85% | 15% / 83% | 2% 18% / 86% 87% | 62%, 42% / 69% |
| 02_cable_d_export_225_kv_parc_des_dunes_bla | 2 | 32% 30% 30% 35% 32% | 5% / 35% | 0% 5% / 30% 34% | 41%, 36% / 42% |
| 02_cable_d_export_225_kv_parc_des_dunes_bla | 4 | 28% 20% 18% 25% 18% | 7% / 18% | 0% 4% / 16% 18% | 28%, 24% / 29% |
| 03_celestia_merival_42mw_power_et_cooling | 2 | 18% 18% 18% 18% 18% | 4% / 20% | 0% 3% / 22% 43% | 11%, 7% / 13% |
| 03_celestia_merival_42mw_power_et_cooling | 4 | 68% 65% 65% 68% 68% | 8% / 55% | 0% 7% / 62% 68% | 48%, 41% / 50% |
| 04_liaison_sous_marine_lumen_cap_des_aigret | 2 | 30% 28% 38% 30% 28% | 8% / 38% | 0% 4% / 60% 60% | 34%, 22% / 41% |
| 04_liaison_sous_marine_lumen_cap_des_aigret | 4 | 12% 18% 12% 12% 15% | 7% / 12% | 0% 3% / 18% 38% | 6%, 3% / 11% |
| 05_sous_station_haute_mer_des_brumes | 2 | 18% 20% 30% 22% 27% | 5% / 20% | 0% 2% / 30% 18% | 45%, 40% / 46% |
| 05_sous_station_haute_mer_des_brumes | 4 | 18% 12% 12% 10% 18% | 3% / 11% | 0% 2% / 8% 18% | 36%, 24% / 41% |
| 06_dorsale_fibre_val_d_orbelle | 2 | 24% 22% 18% 20% 22% | 8% / 14% | 0% 8% / 30% 45% | 12%, 6% / 21% |
| 06_dorsale_fibre_val_d_orbelle | 4 | 84% 80% 78% 80% 80% | 10% / 82% | 0% 18% / 78% 78% | 49%, 35% / 54% |
| 07_campus_ossonet_val_d_aubray_stockage_on_ | 2 | 15% 15% 15% 15% 18% | 7% / 15% | 0% 6% / 55% 38% | 36%, 24% / 43% |
| 07_campus_ossonet_val_d_aubray_stockage_on_ | 4 | 12% 14% 12% 12% 10% | 5% / 12% | 0% 2% / 62% 65% | 35%, 23% / 42% |
| 08_cadre_septennal_reparation_et_maintenanc | 2 | 38% 38% 34% 38% 35% | 7% / 42% | 0% 3% / 38% 60% | 53%, 47% / 55% |
| 08_cadre_septennal_reparation_et_maintenanc | 4 | 83% 85% 78% 78% 85% | 8% / 85% | 0% 4% / 81% 83% | 61%, 54% / 62% |
| 09_ferme_pilote_eole_flottante_de_valbrise | 2 | 28% 35% 32% 28% 30% | 6% / 25% | 0% 5% / 18% 28% | 20%, 15% / 22% |
| 09_ferme_pilote_eole_flottante_de_valbrise | 4 | 20% 18% 18% 20% 25% | 7% / 25% | 0% 3% / 30% 18% | 9%, 7% / 10% |
| 10_liaison_sous_marine_saravelle_90_kv | 2 | 18% 15% 18% 18% 15% | 4% / 20% | 0% 3% / 35% 38% | 23%, 11% / 34% |
| 10_liaison_sous_marine_saravelle_90_kv | 4 | 7% 7% 6% 6% 7% | 5% / 8% | 0% 3% / 12% 28% | 8%, 4% / 14% |
