# Les questions du copilote améliorent-elles la prévision de Muse Spark ?

Réponses du commercial simulées avec la vérité cachée, ajoutées au dossier comme dans le produit ; Muse Spark relit tout et donne sa probabilité. Score de Brier : plus bas = meilleur. Gain = Brier sans question − Brier avec ; intervalle à 90 % par bootstrap sur les contrats.

## Jeu dev (10 contrats, 40 prévisions)

| Questions | Brier | Gain | Intervalle à 90 % |
|---|---|---|---|
| Aucune question (Muse Spark seul) | 0.178 | — | — |
| Questions du copilote (valeur de l'information) | 0.172 | +0.006 | [-0.014 ; +0.024] |
| Questions choisies par Muse Spark seul | 0.174 | +0.003 | [-0.007 ; +0.013] |
| Questions au hasard | 0.173 | +0.004 | [-0.012 ; +0.019] |

## Jeu holdout (10 contrats, 40 prévisions)

| Questions | Brier | Gain | Intervalle à 90 % |
|---|---|---|---|
| Aucune question (Muse Spark seul) | 0.178 | — | — |
| Questions du copilote (valeur de l'information) | 0.189 | -0.011 | [-0.024 ; +0.001] |
| Questions choisies par Muse Spark seul | 0.187 | -0.009 | [-0.024 ; +0.005] |
| Questions au hasard | 0.182 | -0.004 | [-0.012 ; +0.004] |

## Jeu dev + holdout (20 contrats, 80 prévisions)

| Questions | Brier | Gain | Intervalle à 90 % |
|---|---|---|---|
| Aucune question (Muse Spark seul) | 0.178 | — | — |
| Questions du copilote (valeur de l'information) | 0.180 | -0.003 | [-0.014 ; +0.010] |
| Questions choisies par Muse Spark seul | 0.181 | -0.003 | [-0.011 ; +0.006] |
| Questions au hasard | 0.178 | +0.000 | [-0.008 ; +0.009] |
