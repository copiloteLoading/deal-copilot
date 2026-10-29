# CLAUDE.md : contexte du projet deal-copilot

Ce fichier donne à Claude Code tout le contexte du projet. Lis-le en entier avant toute action. Réponds en français.

Dernière mise à jour : mercredi 28 octobre 2026, après l'audit du projet (voir section 9).

## 1. Le contexte

- **Événement** : Meta Global AI Developer Hackathon (Cerebral Valley), en ligne. Développement du 27 octobre au 4 novembre 2026. **Rendu le 4 novembre à 21h ET, soit le jeudi 5 novembre à 3h, heure de Paris.** Objectif interne : rendre le mercredi 4 avant 23h, heure de Paris.
- **Participant** : solo, catégorie **Indie Developer**. Étudiant ingénieur télécom à l'IMT Atlantique (traitement du signal, processus stochastiques), en alternance dans l'industrie des télécoms, en contact direct avec des équipes commerciales.
- **Machine** : Windows, PowerShell, Python dans un environnement virtuel `.venv`.
- **Sujet du hackathon visé** : « Build for Your World » (un problème vécu de première main).

### Règles du hackathon (à respecter strictement)
- Dépôt **public**. Uniquement du travail réalisé pendant l'événement, identifiable comme tel.
- Le projet **doit utiliser les modèles de Meta** (Meta Model API et/ou modèles open weights).
- Vidéo de démo de **3 minutes** et **produit en ligne** que les juges peuvent tester.
- **Anti-projets à éviter** : RAG basique, chatbot simple, tout ce qui est politique ou lié à la guerre, conseil médical, coaching sportif, etc.
- Disqualification si on utilise du code, des données ou des ressources sur lesquels on n'a pas de droits.

### Grille du jury
| Critère | Poids | Ce qu'ils regardent |
|---|---|---|
| Impact | 30 % | Potentiel réel, qui en profite, utilisable pour de vrai |
| Usage des outils IA de Meta | 25 % | Créatif, au-delà d'une intégration basique, qui surprend Meta |
| Profondeur technique et exécution | 20 % | Ingénierie solide et soignée |
| Démo | 25 % | Fonctionne, impressionne, tient en direct, vidéo agréable |

Prix bonus visés : Best Agentic Use-Case, Best Build on Meta Open Weight Models (si le temps le permet).

## 2. Le projet

**Un copilote personnel et confidentiel, piloté par la voix, pour les commerciaux qui négocient des contrats d'infrastructure de plusieurs années** (câbles sous-marins, éolien en mer, data centers).

**Le problème** : ces ventes durent des années et impliquent des dizaines d'interlocuteurs (opérateurs, consortium, financeurs, régulateurs, sous-traitants). L'information utile reste dans la tête des commerciaux, les comptes rendus ne sont pas écrits, personne ne voit clairement qui soutient ou bloque, les prévisions de signature reposent sur l'intuition, et l'historique se perd quand quelqu'un change de poste.

**L'utilisateur** : le commercial lui-même. C'est **son outil**, qui l'aide à gagner son contrat, **pas un outil de surveillance** pour son manager. Il tourne idéalement en local, pour la confidentialité.

**La promesse** : « 60 secondes de dictée après une réunion. L'agent repère ce que vous n'avez pas vu, vous pose au plus 2 questions, et vous donne le compte rendu, le plan d'action et l'e-mail de suivi. »

**Le parcours** :
1. Après une réunion, le commercial **dicte un débrief** d'environ 60 secondes.
2. Le système extrait des **signaux structurés** (acteur, position, objection, échéance, citation exacte, confiance).
3. Le **modèle stochastique** met à jour la position probable de chaque acteur et la **probabilité de signature avec son incertitude**.
4. **L'agent** pose au plus 2 questions ciblées (avec un bouton « Passer »), puis propose un plan d'action classé, rédige le compte rendu et l'e-mail de suivi.

## 3. Le modèle stochastique : positions des acteurs et détenteurs de veto

**Décision de l'audit : on ne fait PAS de HMM global sur l'état du dossier.** Trop de paramètres pour trop peu de données, et un état « en péril » n'est pas observable. On modélise les acteurs, comme fonctionne réellement un grand contrat.

### Structure
- **Chaque acteur clé a une position cachée** parmi {pour, neutre, contre}, représentée par une distribution de probabilité.
- **La position évolue dans le temps comme une chaîne de Markov** : à chaque pas de temps (par exemple une semaine), une petite probabilité de changement d'avis. **Sans nouvelle observation, l'incertitude sur un acteur augmente avec le temps** : c'est ainsi que le silence d'un acteur est pris en compte.
- **Chaque signal extrait d'un débrief est une observation bruitée** de la position d'un acteur, avec une matrice de vraisemblance selon le type et la force du signal (« il soutient clairement » est fort, « elle a dit "on verra" » est faible). La confiance de l'extraction module la force de l'observation.
- **Mise à jour bayésienne** (filtre de type forward d'un modèle de Markov caché, **par acteur**).
- **Règle de signature** : certains acteurs sont **détenteurs de veto** (par exemple la direction financière de l'opérateur, le financeur principal, le régulateur). La signature exige que **tous les veto passent**. Les autres acteurs pèsent selon leur **influence**.
  - Version de base : P(signature) = Π P(veto i favorable ou neutre acceptable) × f(soutien pondéré des autres acteurs), en supposant l'indépendance entre acteurs (hypothèse à documenter dans le README).
  - L'incertitude sur la probabilité de signature s'obtient par Monte-Carlo : on tire les positions des acteurs selon leurs distributions et on calcule la distribution du résultat (intervalle à 80 %).
- **Peu de paramètres, tous compréhensibles** : probabilité de changement d'avis par semaine, fiabilité d'un signal selon son type, poids d'influence, liste des veto. Ils sont regroupés dans un fichier de configuration et documentés.
- Les probabilités de départ peuvent être calibrées sur la base publique PPI de la Banque mondiale (projets d'infrastructure, y compris annulés), à vérifier.

### Ce que le modèle doit exposer
- `posterior(deal)` : la distribution de position de chaque acteur, et P(signature) avec son intervalle.
- `explain(deal)` : les signaux qui ont le plus fait bouger la probabilité, et le veto le plus incertain.
- `simulate(deal, hypothèse)` : la probabilité si une hypothèse était vraie (« si la directrice financière passait favorable »). Sert au moteur de décision.
- Une **version de secours** à base de règles (score pondéré) si le modèle n'est pas stable à temps.

## 4. L'agent : débrief actif + stratège

Un moteur unique répond à la question : « quelle information ou quelle action changerait le plus la probabilité de signature ? ».

### Schéma « le LLM propose, le modèle tranche »
- **Muse Spark génère** des questions et des actions candidates, y compris créatives (« proposer un phasage avec garantie bancaire »).
- **Le modèle les évalue et les classe** :
  - pour une question : la **valeur de l'information**, c'est-à-dire la réduction attendue de l'incertitude sur P(signature), en moyenne sur les réponses possibles pondérées par leur probabilité. En pratique, elle cible l'acteur **le plus incertain qui a le plus de poids**, en priorité un détenteur de veto ;
  - pour une action : l'**effet attendu** sur P(signature), via `simulate()`.
- **Muse Spark formule** ensuite la question ou la recommandation en langage naturel, en citant ses sources.

### Débrief actif
- Après le débrief, l'agent pose **au plus 2 questions**, auxquelles on répond en une phrase, avec un bouton « Passer ».
- Arrêt plus tôt si la question suivante n'apporte presque plus rien.
- **Les changements de position importants** (un acteur qui passe de « pour » à « contre ») sont **toujours confirmés** par le commercial.

### Stratège
- Plan d'action classé avec l'effet attendu de chaque action et son explication.
- Rédaction automatique du compte rendu, de l'e-mail de suivi pour l'action n°1, et de rappels pour les acteurs silencieux.

### Règles de vérifiabilité (non négociables)
- L'agent **ne fabrique jamais un chiffre** et **ne modifie jamais les probabilités lui-même** : il passe toujours par les outils du modèle.
- Chaque affirmation **cite sa source** (débrief, signal avec sa citation exacte).
- Nombre d'étapes de l'agent limité, pour éviter les boucles coûteuses.
- **Pas de chat** dans la version de base.

## 5. L'API Meta (d'après le cookbook officiel github.com/meta-models/meta-model-cookbook)

- Compatible avec le **SDK OpenAI**. `base_url="https://api.meta.ai/v1"`, clé dans la variable d'environnement **`MODEL_API_KEY`** (format `LLM|{id}|{secret}`), chargée depuis `.env` avec python-dotenv. Le SDK OpenAI ne lit pas cette variable automatiquement : il faut la passer explicitement.
- **Muse Spark** : modèle `muse-spark-1.3`, contexte de 1M tokens, vision, sortie structurée (`response_format` avec `json_schema`, ou `client.beta.chat.completions.parse` avec Pydantic), appels d'outils, cache de prompt, effort de raisonnement réglable.
- Images : dans le message `user` (pas `developer`), au format `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`.
- **Muse Voice Transcribe** : modèle `muse-voice-transcribe-1.0`.
  - Fichier entier : `POST https://api.meta.ai/v1/asr/transcribe`, en-tête `Authorization: Bearer <clé>`, multipart avec une partie `request` en JSON (`{"mode": "PUSH_TO_TALK", "model": ..., "audioEncoding": "WAV", "languageBias": ["french"], "keywords": [...]}`) et une partie `audio`. Réponse : `transcript`, `audioDurationMs`, `turns`.
  - Temps réel : WebSocket `wss://api.meta.ai/v1/asr/realtime`.
  - Audio : **WAV mono 16 bits, 16 ou 24 kHz**, 10 minutes ou 32 Mo maximum. Conversion : `ffmpeg -i in.m4a -ac 1 -ar 24000 -sample_fmt s16 out.wav`.
  - **Décision de l'audit** : passer automatiquement en `keywords` **les noms et alias des acteurs et organisations du dossier**, tirés de la mémoire, pour mieux transcrire les noms propres.
- **SAM 3.1** disponible via l'API, non utilisé dans ce projet.
- **Open weights** : Muse Spark Open, via Baseten (modèle `meta-models/muse-spark-open-1026`, PAS `meta-models/muse-spark-open`), Modal ou Fireworks. Prévoir dès le départ une couche `llm.py` qui permet de basculer entre l'API Meta et un fournisseur open weights.
- **Budget** : 150 $ de crédits (tarif indicatif de Muse Spark : environ 1,25 $ par million de tokens en entrée et 4,25 $ en sortie, source tierce à vérifier). Avec les crédits gratuits, les contenus envoyés peuvent servir à Meta pour améliorer ses produits, raison de plus pour n'envoyer que des données fictives. Mettre les réponses en cache, sauvegarder les jeux générés, tester sur 2 ou 3 éléments avant tout traitement complet.

## 6. L'évaluation

**Décision de l'audit : l'expérience centrale est « hybride contre LLM seul », sur des scénarios générés indépendamment du modèle.**

### Le jeu de test
- 8 à 10 contrats fictifs. Pour chacun, des **fiches de personnages** avec leurs **intérêts cachés**, la liste des veto et une **issue réelle** (signé, perdu, retardé).
- **Muse Spark écrit les histoires et les débriefs** à partir de ces fiches, avec du bruit (oublis, hésitations, formulations ambiguës), **sans connaître la structure du modèle**. Le modèle doit s'en débrouiller : c'est ce qui rend le test honnête.
- Pour chaque contrat, on garde la **vérité cachée** (positions réelles des acteurs à chaque date), pour pouvoir simuler les réponses du commercial aux questions de l'agent.
- Jeu généré une seule fois et sauvegardé dans `data/scenarios/`.

### Les comparaisons
1. **Qualité de l'extraction** : précision et rappel des signaux.
2. **Qualité de la probabilité** : score de Brier et calibration, en comparant trois approches :
   - **Muse Spark seul** (on lui donne les débriefs et on lui demande une probabilité) ;
   - **le modèle seul** (règles ou modèle stochastique sans agent) ;
   - **l'hybride** (extraction LLM + modèle + agent).
3. **Utilité des questions** : réduction de l'incertitude et amélioration du score de Brier après 2 questions, en comparant les **questions de l'agent** aux **questions proposées par Muse Spark seul** (et au hasard, en référence basse).
4. **Détection anticipée** : combien de réunions plus tôt un contrat qui sera perdu est repéré.
5. **Petit test humain** : 2 ou 3 camarades de l'IMT jouent le commercial avec une fiche de scénario secrète et répondent à l'agent à la voix (environ 5 sessions). Résultats qualitatifs pour la vidéo.

Si l'hybride ne bat pas le LLM seul, le dire honnêtement et ajuster le récit.

## 7. Règles non négociables

1. **Aucune donnée réelle d'entreprise.** Tout est fictif : entreprises, personnes, projets. Ne jamais mentionner l'employeur du participant, ni dans le code, ni dans les données, ni dans le README, ni dans la vidéo. Dire « expérience dans l'industrie des télécoms ».
2. **Des entreprises et des financeurs, pas des États.** Aucune rivalité entre pays, aucune géopolitique, aucun conflit dans les données ou les exemples.
3. **Aucun secret dans le dépôt.** La clé reste dans `.env`, exclu par `.gitignore`. Vérifier `git status` avant chaque commit. Ne jamais lire ni afficher le contenu de `.env`.
4. **Pas de données personnelles réelles.** Personnes fictives uniquement.
5. **Licences** : vérifier la licence de tout jeu de données externe et la citer dans le README.
6. **Chaque soir, la chaîne complète doit tourner**, même de façon simple.

## 8. Architecture

```
deal-copilot/
├── CLAUDE.md
├── README.md               ← problème, utilisateur, architecture, rôle de chaque modèle Meta, modèle stochastique et hypothèses, résultats, limites, sources et licences
├── requirements.txt
├── .env.example            ← modèle de clé (publié)
├── .gitignore              ← contient .env, .venv/, outputs/, *.wav, *.m4a
├── app.py                  ← interface Streamlit
├── config/
│   └── model_params.yaml   ← paramètres du modèle, documentés
├── copilot/
│   ├── llm.py              ← client unique, bascule API Meta / Muse Spark Open
│   ├── capture.py          ← voix (Muse Voice Transcribe, keywords tirés de la mémoire)
│   ├── extract.py          ← signaux structurés (JSON schema, citation exacte, confiance)
│   ├── memory.py           ← SQLite : contrats, acteurs (avec alias et veto), réunions, signaux, historique des positions
│   ├── model.py            ← positions cachées par acteur (Markov + Bayes), règle de veto, Monte-Carlo, explain(), simulate(), version de secours
│   ├── decision.py         ← valeur de l'information (questions) et effet attendu (actions)
│   └── agent.py            ← le LLM propose, le modèle tranche : débrief actif + stratège, citations, confirmations
├── data/
│   ├── demo_deal/          ← contrat de démo fictif (câble Port-Aven – Kerlis) et scénario « piège » de la vidéo
│   └── scenarios/          ← jeu de test : fiches de personnages, vérité cachée, débriefs générés
├── eval/
│   ├── generate.py         ← génère les histoires et les débriefs à partir des fiches (indépendamment du modèle)
│   ├── baselines.py        ← Muse Spark seul (probabilité et questions)
│   └── evaluate.py         ← extraction, Brier et calibration, utilité des questions, détection anticipée
├── samples/                ← débriefs d'exemple
└── test_meta.py            ← tests de fumée de l'API (ping, transcribe, extract, image)
```

### Interface (Streamlit)
Un seul écran principal :
- bouton **Débrief** (enregistrement ou dépôt d'un fichier audio) ;
- **carte des parties prenantes** : couleur = position la plus probable, taille = influence, **contour marqué pour les détenteurs de veto**, **pointillé pour les signaux incertains** jusqu'à confirmation ;
- **courbe de probabilité de signature** avec zone d'incertitude, qui se resserre quand le commercial répond aux questions ;
- **questions de l'agent** (au plus 2, bouton « Passer ») ;
- **plan d'action classé**, compte rendu et e-mail de suivi ;
- **mode démo** avec le contrat préchargé et des réponses en cache en secours.

## 9. Décisions de l'audit (28 octobre)

1. Modèle « positions cachées des acteurs + détenteurs de veto » à la place d'un HMM global sur l'état du dossier.
2. Expérience centrale : hybride contre Muse Spark seul, sur des scénarios générés indépendamment du modèle, plus un petit test humain.
3. Agent selon le schéma « le LLM propose, le modèle tranche ».
4. L'outil appartient au commercial (pas de surveillance), friction minimale : 60 s de dictée, au plus 2 questions, bouton « Passer ».
5. Mots-clés de transcription tirés automatiquement de la mémoire du dossier.
6. Chaque signal porte sa citation et sa confiance ; les changements de position importants sont toujours confirmés.
7. Périmètre réduit : chat supprimé, lecture des photos d'organigramme en bonus, résolution d'entités simple (alias confirmés), open weights seulement si tout le reste marche.
8. Démo construite autour d'un **piège** : une réunion qui semble excellente, mais la directrice financière (détentrice de veto) a dit « on en reparlera après le budget ». L'agent repère le seul veto incertain, pose la question qui révèle le risque, la probabilité baisse et le plan d'action change. Voix enregistrée à l'avance pour la vidéo.

## 10. Planning (heures de Paris)

| Jour | Objectif | Fini quand |
|---|---|---|
| Mer 28 | Tests API (ping, extract, transcribe), contrat de démo fictif avec acteurs, alias, influence et veto, scénario « piège ». 17h : session Agents 102 | Un débrief vocal donne des signaux JSON corrects |
| Jeu 29 | Mémoire SQLite (acteurs, alias, veto), transcription avec keywords, fiches de personnages et génération du jeu de test, mesure de l'extraction | Les débriefs s'accumulent proprement et le jeu de test est sauvegardé |
| Ven 30 | Modèle : positions cachées par acteur, règle de veto, Monte-Carlo, `explain()`, `simulate()`, version de secours. Valeur de l'information et effet des actions. 17h : session Fireworks | Questions et actions classées avec leurs chiffres |
| Sam 31 | Agent : « le LLM propose, le modèle tranche », débrief actif (matin), stratège et rédaction (après-midi), confirmations et citations | Le scénario piège déclenche la bonne question puis un plan cohérent |
| Dim 1 | Interface Streamlit complète | Parcours de démo complet en local |
| Lun 2 | Évaluation (Muse Spark seul, extraction, Brier, utilité des questions, détection anticipée), test humain si possible, README. Open weights seulement si tout marche | Tableau de résultats |
| Mar 3 | Déploiement, robustesse, cache, répétition. Gel des fonctionnalités à 20h | 10 démos d'affilée sans erreur |
| Mer 4 | Vidéo (voix enregistrée à l'avance), vérifications, rendu avant 23h | Rendu envoyé |

**Avancement (jeu 29, midi)** :
- Fait : clé API active (ping et extraction OK, citations exactes vérifiées), contrat de démo avec veto, scénario piège, `llm.py` avec cache et mode hors ligne, maquette Streamlit, `memory.py` (SQLite, alias, mots-clés de transcription, dernier contact direct) et ses tests.
- Reste de mer 28 : test de transcription vocale (il faut un fichier WAV enregistré).
- Reste de jeu 29 : transcription avec keywords, `extract.py` (ajouter `source_type`, position « conditionnelle », séparer organisations et personnes), fiches de personnages et jeu de test, mesure de l'extraction.

**Points de décision** :
- Vendredi soir : si le modèle par acteur n'est pas stable, garder la version de secours à règles (le moteur de décision fonctionne avec n'importe quel modèle qui expose `simulate()`).
- Lundi 18h : si l'open weights ne marche pas, rester sur l'API.

**Priorités si le temps manque** :
- Indispensable : débrief, signaux, modèle par acteur (ou version de secours), au moins une question de l'agent, interface, démo en ligne, vidéo, comparaison avec Muse Spark seul.
- Ensuite : stratège complet, utilité des questions, détection anticipée, test humain.
- Bonus : Muse Spark Open, lecture des photos d'organigramme.

## 11. Façon de travailler

- Avancer par petites étapes testables, et faire tourner chaque étape avant de passer à la suivante.
- Code simple et lisible, commentaires utiles, pas de sur-ingénierie.
- Commits fréquents avec des messages clairs, en anglais.
- Toujours expliquer brièvement ce qui a été fait et comment le tester (commandes PowerShell).
- Signaler tout ce qui pourrait enfreindre les règles de la section 7.
- Mettre à jour la section 10 de ce fichier quand une étape est finie ou qu'une décision change.
