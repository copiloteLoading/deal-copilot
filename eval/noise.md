# Dictée dans le bruit

Débrief du scénario piège (52 s), bruits synthétiques ajoutés, transcription par Muse Voice Transcribe avec les noms du dossier en mots-clés.

Sans bruit : WER 6%, noms propres retrouvés 88%.

| Bruit | SNR réel | SNR estimé | WER brut | WER débruité | Noms (brut / débruité) |
|---|---|---|---|---|---|
| transport | 10 dB | 9.8 dB | 5% | 10% | 88% / 88% |
| transport | 5 dB | 5.6 dB | 8% | 8% | 88% / 88% |
| transport | 0 dB | 1.6 dB | 12% | 10% | 88% / 88% |
| douche | 10 dB | 10.5 dB | 7% | 9% | 88% / 88% |
| douche | 5 dB | 5.8 dB | 10% | 10% | 88% / 88% |
| douche | 0 dB | 1.3 dB | 11% | 9% | 88% / 88% |
| brouhaha | 10 dB | 11.8 dB | 4% | 6% | 88% / 88% |
| brouhaha | 5 dB | 7.9 dB | 5% | 8% | 88% / 88% |
| brouhaha | 0 dB | 4.8 dB | 14% | 18% | 88% / 88% |

Lecture : Muse Voice Transcribe résiste bien au bruit (les noms du dossier sont retrouvés comme sans bruit). Le débruitage n'apporte pas de gain fiable : d'un essai à l'autre, la transcription varie autant que l'effet du filtre (transport à 0 dB : 4 % avec une soustraction de 0,21, 10 % avec 0,2 ; une soustraction complète améliore le SNR mais dégrade la transcription). Il n'est donc pas appliqué par défaut ; le SNR estimé sert à prévenir le commercial quand le bruit est très fort. Limites : un seul enregistrement (voix de synthèse), bruits synthétiques, un essai par cas.
