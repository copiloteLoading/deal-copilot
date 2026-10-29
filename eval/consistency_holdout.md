# Test de cohérence : Muse Spark seul contre le modèle

10 contrats, réunions [2, 4], 20 points de test. Veto testé : celui de plus forte influence. Muse Spark : effort « low », 5 tirages.

| Mesure | Muse Spark seul | Modèle |
|---|---|---|
| **Stabilité** : écart moyen entre le plus haut et le plus bas de 5 tirages | 7 pts | 0 pts |
| Écart maximal sur 5 tirages | 20 pts | 0 pts |
| Points où le chiffre bouge d'au moins 10 pts sans nouvelle information | 20% | 0% |
| **Monotonie** : « contre » < aujourd'hui (moyenne des tirages) < « pour » | 35% | 100% |
| Ordre inversé (« contre » ≥ « pour ») | 5% | 0% |
| Effet moyen de « je suis contre » | -23 pts | -10 pts |
| Effet moyen de « je soutiens » | +0 pts | +7 pts |
| **« Et si ? »** : écart moyen entre deux formulations de la même hypothèse | 5 pts | 0 (par construction) |
| Écart maximal entre deux formulations | 18 pts | 0 |
| « Et si ? » dans le bon sens | 70% | 100% |

## Détail

| Contrat | Réunion | Muse Spark : 5 tirages | contre / pour | et si contre / et si pour (2 formulations) | Modèle : base, contre / pour |
|---|---|---|---|---|---|
| 01_modernisation_station_d_atterrissage_cap | 2 | 25% 30% 20% 24% 18% | 7% / 32% | 0% 3% / 35% 38% | 4%, 3% / 7% |
| 01_modernisation_station_d_atterrissage_cap | 4 | 81% 84% 70% 82% 80% | 8% / 78% | 0% 10% / 75% 78% | 42%, 21% / 55% |
| 02_array_cables_66_kv_ferme_des_brumes_780_ | 2 | 17% 18% 20% 12% 15% | 4% / 15% | 0% 7% / 35% 32% | 40%, 26% / 47% |
| 02_array_cables_66_kv_ferme_des_brumes_780_ | 4 | 8% 8% 8% 8% 8% | 7% / 7% | 1% 3% / 30% 17% | 11%, 6% / 21% |
| 03_orivale_edge_horizon_24 | 2 | 35% 18% 30% 38% 20% | 8% / 45% | 0% 3% / 65% 62% | 38%, 24% / 46% |
| 03_orivale_edge_horizon_24 | 4 | 78% 85% 85% 85% 85% | 10% / 85% | 0% 7% / 85% 85% | 55%, 37% / 65% |
| 04_liaison_fibre_abyssale_alizee_segment_va | 2 | 18% 25% 18% 22% 20% | 8% / 18% | 0% 4% / 38% 45% | 27%, 14% / 39% |
| 04_liaison_fibre_abyssale_alizee_segment_va | 4 | 12% 12% 12% 12% 12% | 7% / 12% | 0% 5% / 32% 22% | 11%, 6% / 23% |
| 05_retrofit_cooling_hexacube_valmea_free_co | 2 | 22% 28% 28% 20% 22% | 7% / 20% | 1% 5% / 18% 20% | 33%, 21% / 41% |
| 05_retrofit_cooling_hexacube_valmea_free_co | 4 | 15% 15% 18% 15% 15% | 5% / 15% | 0% 3% / 20% 12% | 29%, 20% / 35% |
| 06_cable_aurore_liaison_sous_marine_mirval_ | 2 | 15% 18% 15% 18% 15% | 7% / 15% | 0% 4% / 15% 15% | 8%, 7% / 9% |
| 06_cable_aurore_liaison_sous_marine_mirval_ | 4 | 72% 72% 72% 68% 72% | 8% / 68% | 0% 3% / 68% 68% | 50%, 46% / 51% |
| 07_cadre_reparation_cables_brume_2026_2031 | 2 | 30% 35% 28% 20% 32% | 5% / 20% | 0% 8% / 48% 60% | 36%, 22% / 44% |
| 07_cadre_reparation_cables_brume_2026_2031 | 4 | 8% 8% 7% 7% 10% | 5% / 8% | 2% 5% / 20% 18% | 8%, 4% / 16% |
| 08_anneau_fibre_clairval_cur_rhea | 2 | 20% 22% 18% 22% 22% | 8% / 22% | 0% 5% / 22% 20% | 28%, 17% / 33% |
| 08_anneau_fibre_clairval_cur_rhea | 4 | 68% 70% 65% 73% 75% | 7% / 78% | 0% 5% / 65% 70% | 60%, 48% / 63% |
| 09_sous_station_offshore_hydrogen_ready_des | 2 | 22% 18% 22% 22% 24% | 3% / 22% | 0% 4% / 25% 28% | 39%, 26% / 45% |
| 09_sous_station_offshore_hydrogen_ready_des | 4 | 12% 14% 12% 12% 15% | 5% / 12% | 2% 3% / 18% 15% | 28%, 18% / 34% |
| 10_novacentre_valtaneuse_nord_distributio | 2 | 22% 28% 22% 25% 25% | 5% / 25% | 0% 7% / 40% 58% | 44%, 26% / 54% |
| 10_novacentre_valtaneuse_nord_distributio | 4 | 12% 10% 12% 12% 12% | 6% / 10% | 0% 3% / 25% 18% | 12%, 5% / 22% |
