# Les leçons des contrats passés aident-elles Muse Spark à prévoir ?

Validation croisée : les contrats de chaque jeu sont prévus avec les leçons tirées de l'autre jeu. Probabilité = moyenne de 3 tirages. Score de Brier : plus bas = meilleur. Gain = Brier sans leçons − Brier avec ; intervalle à 90 % par bootstrap sur les contrats.

| Jeu prévu | Leçons utilisées | Brier sans leçons | Brier avec leçons | Gain | Intervalle à 90 % |
|---|---|---|---|---|---|
| dev (40 prévisions) | 30 | 0.179 | 0.155 | +0.024 | [+0.005 ; +0.044] |
| holdout (40 prévisions) | 30 | 0.186 | 0.171 | +0.015 | [-0.001 ; +0.034] |
| les deux (80 prévisions) | 60 | 0.182 | 0.163 | +0.020 | [+0.007 ; +0.033] |

Par réunion (les deux jeux) :

| Réunion | Sans leçons | Avec leçons |
|---|---|---|
| 1 | 0.279 | 0.253 |
| 2 | 0.273 | 0.258 |
| 3 | 0.143 | 0.110 |
| 4 | 0.035 | 0.031 |

## Est-ce plus qu'un simple décalage ?

Les leçons font monter les probabilités de 2,9 pts en moyenne. Contrôles sur les 80 prévisions :

| | Brier | AUC (séparation signés / non signés) |
|---|---|---|
| Sans leçons | 0,182 | 0,83 |
| Sans leçons + le même décalage moyen (+2,9 pts) | 0,177 | 0,83 |
| Sans leçons + le meilleur décalage constant, choisi en connaissant les issues (+11 pts) | 0,171 | 0,83 |
| **Avec leçons** | **0,163** | **0,86** |

- Les leçons battent même le meilleur décalage constant choisi après coup : elles apportent de l'information, pas seulement un niveau.
- La séparation progresse surtout en début de parcours : AUC 0,31 → 0,42 à la réunion 1, 0,45 → 0,52 à la réunion 2 (1,00 dans les deux cas aux réunions 3 et 4).
- Le gain vient surtout des contrats signés (Brier −0,058), reconnus plus tôt (ex. 33 % → 57 % à la réunion 3) ; les contrats non signés perdent un peu (+0,006).

Limites : 2 × 10 contrats ; les deux jeux et les leçons sont écrits par le même modèle (style et intrigues proches, ce qui peut flatter le résultat) ; la phrase du commercial sur ce qui a fait la différence est l'explication de l'issue gardée dans la vérité cachée.
