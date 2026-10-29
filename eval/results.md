# Résultats de l'évaluation

10 contrats fictifs générés par Muse Spark (4 signés, 4 perdus, 2 retardés), 40 prévisions (une par réunion). Issue = 1 si signé, 0 sinon.
Les réponses du commercial aux questions sont simulées avec la vérité cachée.

## Score de Brier (plus bas = meilleur ; 0,25 = toujours répondre 50 %)

| Méthode | Toutes réunions | Réunions 1-2 | Dernière réunion |
|---|---|---|---|
| Muse Spark seul | 0.178 | 0.272 | 0.037 |
| Modèle seul (sans question) | 0.240 | 0.308 | 0.117 |
| Hybride : modèle + 2 questions (valeur de l'information) | 0.231 | 0.347 | 0.054 |
| Modèle + 2 questions choisies par Muse Spark seul | 0.226 | 0.333 | 0.066 |
| Modèle + 2 questions au hasard | 0.229 | 0.316 | 0.089 |

## Extraction des signaux (Muse Spark)

| | Précision | Rappel | Acteurs retrouvés |
|---|---|---|---|
| Position exacte | 88% | 83% | 94% |
| Conditionnel = neutre | 92% | 86% | 94% |

## Utilité des questions

| Questions | Positions justes | Incertitude (écart-type) | Part de veto interrogés |
|---|---|---|---|
| Aucune | 72% | 0.225 | — |
| Valeur de l'information (hybride) | 79% | 0.172 | 98% |
| Choisies par Muse Spark seul | 79% | 0.179 | 94% |
| Au hasard | 77% | 0.205 | 45% |

## Détection des contrats non signés (alerte si probabilité < 30%)

| Méthode | Contrats non signés repérés | Réunion de la première alerte (moyenne) | Fausses alertes sur des contrats signés |
|---|---|---|---|
| Muse Spark seul | 6 / 6 | 1.5 | 3 |
| Modèle seul (sans question) | 4 / 6 | 2.8 | 3 |
| Hybride : modèle + 2 questions (valeur de l'information) | 6 / 6 | 2.3 | 3 |

## Détail par contrat

| Contrat | Issue | Muse Spark seul | Modèle seul | Hybride |
|---|---|---|---|---|
| 01_cable_sous_marin_aurore_liaison_brume_va | signed | 12% → 20% → 78% → 84% | 22% → 12% → 29% → 62% | 12% → 6% → 35% → 75% |
| 02_cable_d_export_225_kv_parc_des_dunes_bla | lost | 27% → 32% → 35% → 28% | 36% → 41% → 37% → 28% | 38% → 43% → 39% → 18% |
| 03_celestia_merival_42mw_power_et_cooling | signed | 18% → 18% → 68% → 68% | 33% → 11% → 26% → 48% | 17% → 3% → 25% → 55% |
| 04_liaison_sous_marine_lumen_cap_des_aigret | lost | 33% → 30% → 15% → 12% | 38% → 34% → 17% → 6% | 44% → 38% → 9% → 1% |
| 05_sous_station_haute_mer_des_brumes | delayed | 18% → 18% → 15% → 18% | 48% → 45% → 39% → 36% | 49% → 45% → 28% → 17% |
| 06_dorsale_fibre_val_d_orbelle | signed | 27% → 24% → 30% → 84% | 18% → 12% → 28% → 49% | 9% → 6% → 39% → 64% |
| 07_campus_ossonet_val_d_aubray_stockage_on_ | lost | 18% → 15% → 15% → 12% | 37% → 36% → 39% → 35% | 26% → 22% → 14% → 9% |
| 08_cadre_septennal_reparation_et_maintenanc | signed | 35% → 38% → 35% → 83% | 52% → 53% → 61% → 61% | 57% → 61% → 67% → 72% |
| 09_ferme_pilote_eole_flottante_de_valbrise | delayed | 32% → 28% → 15% → 20% | 41% → 20% → 12% → 9% | 55% → 13% → 5% → 3% |
| 10_liaison_sous_marine_saravelle_90_kv | lost | 25% → 18% → 12% → 7% | 35% → 23% → 22% → 8% | 25% → 6% → 4% → 1% |
