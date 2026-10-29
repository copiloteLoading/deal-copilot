# Résultats de l'évaluation

10 contrats fictifs générés par Muse Spark (4 signés, 4 perdus, 2 retardés), 40 prévisions (une par réunion). Issue = 1 si signé, 0 sinon.
Les réponses du commercial aux questions sont simulées avec la vérité cachée.

## Score de Brier (plus bas = meilleur ; 0,25 = toujours répondre 50 %)

| Méthode | Toutes réunions | Réunions 1-2 | Dernière réunion |
|---|---|---|---|
| Muse Spark seul | 0.178 | 0.264 | 0.034 |
| Modèle seul (sans question) | 0.263 | 0.310 | 0.161 |
| Hybride : modèle + 2 questions (valeur de l'information) | 0.281 | 0.381 | 0.103 |
| Modèle + 2 questions choisies par Muse Spark seul | 0.289 | 0.377 | 0.117 |
| Modèle + 2 questions au hasard | 0.267 | 0.334 | 0.124 |

## Extraction des signaux (Muse Spark)

| | Précision | Rappel | Acteurs retrouvés |
|---|---|---|---|
| Position exacte | 80% | 74% | 94% |
| Conditionnel = neutre | 89% | 83% | 94% |

## Utilité des questions

| Questions | Positions justes | Incertitude (écart-type) | Part de veto interrogés |
|---|---|---|---|
| Aucune | 72% | 0.208 | — |
| Valeur de l'information (hybride) | 78% | 0.167 | 100% |
| Choisies par Muse Spark seul | 76% | 0.170 | 98% |
| Au hasard | 80% | 0.199 | 51% |

## Détection des contrats non signés (alerte si probabilité < 30%)

| Méthode | Contrats non signés repérés | Réunion de la première alerte (moyenne) | Fausses alertes sur des contrats signés |
|---|---|---|---|
| Muse Spark seul | 6 / 6 | 1.7 | 4 |
| Modèle seul (sans question) | 6 / 6 | 2.7 | 4 |
| Hybride : modèle + 2 questions (valeur de l'information) | 6 / 6 | 2.8 | 4 |

## Détail par contrat

| Contrat | Issue | Muse Spark seul | Modèle seul | Hybride |
|---|---|---|---|---|
| 01_modernisation_station_d_atterrissage_cap | signed | 22% → 25% → 38% → 81% | 30% → 2% → 17% → 33% | 31% → 1% → 23% → 46% |
| 02_array_cables_66_kv_ferme_des_brumes_780_ | lost | 25% → 17% → 12% → 8% | 31% → 36% → 11% → 6% | 32% → 41% → 6% → 2% |
| 03_orivale_edge_horizon_24 | signed | 22% → 35% → 60% → 78% | 30% → 34% → 37% → 46% | 16% → 6% → 25% → 50% |
| 04_liaison_fibre_abyssale_alizee_segment_va | lost | 35% → 18% → 18% → 12% | 37% → 19% → 9% → 6% | 38% → 10% → 5% → 3% |
| 05_retrofit_cooling_hexacube_valmea_free_co | delayed | 25% → 22% → 15% → 15% | 30% → 31% → 31% → 27% | 34% → 37% → 23% → 13% |
| 06_cable_aurore_liaison_sous_marine_mirval_ | signed | 35% → 15% → 35% → 72% | 37% → 5% → 18% → 39% | 38% → 5% → 23% → 52% |
| 07_cadre_reparation_cables_brume_2026_2031 | lost | 38% → 30% → 15% → 8% | 37% → 33% → 11% → 3% | 42% → 35% → 6% → 1% |
| 08_anneau_fibre_clairval_cur_rhea | signed | 35% → 20% → 38% → 68% | 25% → 26% → 19% → 42% | 11% → 8% → 13% → 52% |
| 09_sous_station_offshore_hydrogen_ready_des | delayed | 35% → 22% → 15% → 12% | 36% → 35% → 33% → 27% | 42% → 39% → 21% → 10% |
| 10_novacentre_valtaneuse_nord_distributio | lost | 24% → 22% → 20% → 12% | 39% → 42% → 18% → 4% | 41% → 44% → 7% → 1% |
