# Résultats de l'évaluation

10 contrats fictifs générés par Muse Spark (4 signés, 4 perdus, 2 retardés), 40 prévisions (une par réunion). Issue = 1 si signé, 0 sinon.
Les réponses du commercial aux questions sont simulées avec la vérité cachée.

## Score de Brier (plus bas = meilleur ; 0,25 = toujours répondre 50 %)

| Méthode | Toutes réunions | Réunions 1-2 | Dernière réunion |
|---|---|---|---|
| Muse Spark seul | 0.178 | 0.264 | 0.034 |
| Modèle seul (sans question) | 0.243 | 0.309 | 0.115 |
| Hybride : modèle + 2 questions (valeur de l'information) | 0.255 | 0.373 | 0.055 |
| Modèle + 2 questions choisies par Muse Spark seul | 0.260 | 0.366 | 0.066 |
| Modèle + 2 questions au hasard | 0.245 | 0.329 | 0.079 |

## Extraction des signaux (Muse Spark)

| | Précision | Rappel | Acteurs retrouvés |
|---|---|---|---|
| Position exacte | 80% | 74% | 94% |
| Conditionnel = neutre | 89% | 83% | 94% |

## Utilité des questions

| Questions | Positions justes | Incertitude (écart-type) | Part de veto interrogés |
|---|---|---|---|
| Aucune | 75% | 0.231 | — |
| Valeur de l'information (hybride) | 80% | 0.190 | 100% |
| Choisies par Muse Spark seul | 78% | 0.192 | 98% |
| Au hasard | 80% | 0.221 | 51% |

## Détection des contrats non signés (alerte si probabilité < 30%)

| Méthode | Contrats non signés repérés | Réunion de la première alerte (moyenne) | Fausses alertes sur des contrats signés |
|---|---|---|---|
| Muse Spark seul | 6 / 6 | 1.7 | 4 |
| Modèle seul (sans question) | 6 / 6 | 3.2 | 3 |
| Hybride : modèle + 2 questions (valeur de l'information) | 6 / 6 | 2.8 | 4 |

## Détail par contrat

| Contrat | Issue | Muse Spark seul | Modèle seul | Hybride |
|---|---|---|---|---|
| 01_modernisation_station_d_atterrissage_cap | signed | 22% → 25% → 38% → 81% | 32% → 4% → 23% → 42% | 33% → 2% → 30% → 63% |
| 02_array_cables_66_kv_ferme_des_brumes_780_ | lost | 25% → 17% → 12% → 8% | 34% → 40% → 19% → 11% | 35% → 46% → 13% → 4% |
| 03_orivale_edge_horizon_24 | signed | 22% → 35% → 60% → 78% | 32% → 38% → 42% → 55% | 23% → 15% → 35% → 65% |
| 04_liaison_fibre_abyssale_alizee_segment_va | lost | 35% → 18% → 18% → 12% | 42% → 27% → 17% → 11% | 44% → 19% → 8% → 5% |
| 05_retrofit_cooling_hexacube_valmea_free_co | delayed | 25% → 22% → 15% → 15% | 32% → 33% → 32% → 29% | 38% → 43% → 30% → 21% |
| 06_cable_aurore_liaison_sous_marine_mirval_ | signed | 35% → 15% → 35% → 72% | 42% → 8% → 22% → 50% | 44% → 7% → 27% → 68% |
| 07_cadre_reparation_cables_brume_2026_2031 | lost | 38% → 30% → 15% → 8% | 42% → 36% → 18% → 8% | 48% → 39% → 13% → 3% |
| 08_anneau_fibre_clairval_cur_rhea | signed | 35% → 20% → 38% → 68% | 28% → 28% → 32% → 60% | 18% → 15% → 27% → 67% |
| 09_sous_station_offshore_hydrogen_ready_des | delayed | 35% → 22% → 15% → 12% | 41% → 39% → 35% → 28% | 51% → 44% → 28% → 17% |
| 10_novacentre_valtaneuse_nord_distributio | lost | 24% → 22% → 20% → 12% | 41% → 44% → 27% → 12% | 43% → 47% → 16% → 3% |
