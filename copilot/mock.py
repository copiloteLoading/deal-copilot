"""Données de maquette pour le squelette de l'interface.

Tout ce qui est ici sera remplacé par les vrais calculs (extract, model, decision, agent).
Les chiffres sont inventés à la main pour donner l'allure de l'écran, rien de plus.
"""

# Historique de la probabilité de signature : (date, p, borne basse, borne haute, ce qui l'a fait bouger)
PROBA_HISTORY = [
    ("2026-04-14", 0.30, 0.10, 0.55, "Ouverture du dossier (taux de base)"),
    ("2026-09-15", 0.45, 0.25, 0.65, "Banque intéressée sur le principe"),
    ("2026-10-06", 0.52, 0.35, 0.69, "Julien Marec défendra la solution en interne"),
    ("2026-10-27", 0.48, 0.33, 0.63, "Condition de phasage, banque silencieuse"),
]

CURRENT = {"p": 0.48, "delta_pts": -4, "low": 0.33, "high": 0.63, "state": "Négociation"}

# Signaux extraits du débrief du 27 octobre (citations copiées du texte)
SIGNALS = [
    {"Acteur": "Julien Marec", "Type": "soutien", "Position": "support",
     "Citation": "la plus solide techniquement", "Confiance": 0.90},
    {"Acteur": "Sophie Lenoir", "Type": "objection", "Position": "neutral",
     "Citation": "elle veut étaler sur quatre ans au lieu de trois, sinon elle ne valide pas",
     "Confiance": 0.85},
    {"Acteur": "Thomas Riou", "Type": "risque", "Position": "unknown",
     "Citation": "attend toujours l'étude d'impact environnemental avant de s'engager",
     "Confiance": 0.80},
    {"Acteur": "Thomas Riou", "Type": "risque", "Position": "unknown",
     "Citation": "ça fait maintenant six semaines qu'on ne l'a pas vu", "Confiance": 0.90},
    {"Acteur": "Oceanix Cables", "Type": "concurrent", "Position": "oppose",
     "Citation": "ils ont proposé un prix plus bas, mais je ne suis pas sûr du montant",
     "Confiance": 0.40},
    {"Acteur": "Sophie Lenoir", "Type": "échéance", "Position": "neutral",
     "Citation": "envoyer une proposition de phasage sur quatre ans avant le 15",
     "Confiance": 0.90},
]

# Questions du débrief actif (au plus 2) : id de l'inconnue (unknowns.json) et gain
# d'incertitude en points. Elles ciblent en priorité les détenteurs de veto les plus incertains.
QUESTIONS = [
    {"unknown": "bank_commitment", "gain_pts": 9.0},
    {"unknown": "cfo_phasing", "gain_pts": 5.0},
]

ACTIONS = [
    {"action": "Organiser une réunion avec Thomas Riou (banque)",
     "why": "Acteur à forte influence, silencieux depuis 6 semaines",
     "effect_pts": 12, "source": "2026-10-27_consortium"},
    {"action": "Envoyer la proposition de phasage sur 4 ans",
     "why": "Condition posée par Sophie Lenoir pour valider",
     "effect_pts": 8, "source": "2026-10-27_consortium"},
    {"action": "Obtenir un rendez-vous avec Claire Dantec",
     "why": "Décideur final, position inconnue depuis septembre",
     "effect_pts": 7, "source": "2026-09-15_lancement"},
    {"action": "Confirmer l'écart de prix avec Oceanix",
     "why": "Rumeur de -10 %, confiance faible",
     "effect_pts": 3, "source": "2026-10-27_consortium"},
]

EMAIL_DRAFT = """Objet : Port-Aven – Kerlis : proposition de phasage et point financement

Bonjour Sophie,

Merci pour nos échanges de mardi. Comme convenu, vous trouverez d'ici le 15 notre
proposition de phasage des paiements sur quatre ans.

Nous souhaiterions également organiser avant la fin du mois une réunion avec la
Banque Atlantique de Développement, pour faire le point sur l'étude d'impact.

Bien cordialement,
Léa Garnier
Ondine Subsea"""

MEETING_SUMMARY = """Réunion consortium du 27 octobre 2026, projet Port-Aven – Kerlis

Points clés
- Julien Marec (Baltis Telecom) soutient notre solution de répéteurs, « la plus solide techniquement ».
- Sophie Lenoir (Baltis Telecom, veto budgétaire) conditionne sa validation à un phasage des paiements sur quatre ans.
- La Banque Atlantique de Développement attend l'étude d'impact environnemental ; Thomas Riou est absent depuis six semaines.
- Oceanix Cables aurait proposé un prix plus bas (montant non confirmé).

Prochaines étapes
- Envoyer la proposition de phasage sur quatre ans avant le 15 novembre.
- Organiser une réunion avec la banque avant la fin du mois."""

# Position des nœuds sur la carte des parties prenantes (x, y)
MAP_ORGS = {
    "nordlink": (0.0, 2.0),
    "baltis": (-1.8, 0.7),
    "kerlis_connect": (1.8, 0.7),
    "bad": (-1.4, -1.2),
    "agence_littoral": (1.4, -1.2),
}
MAP_ORG_LABELS = {
    "nordlink": "Consortium Nordlink Bay",
    "baltis": "Baltis Telecom",
    "kerlis_connect": "Kerlis Connect",
    "bad": "Banque (BAD)",
    "agence_littoral": "Agence du littoral",
}
MAP_ACTORS = {
    "claire_dantec": (0.0, 1.2),
    "julien_marec": (-2.4, -0.1),
    "sophie_lenoir": (-1.2, -0.1),
    "yann_le_goff": (1.8, -0.1),
    "thomas_riou": (-1.4, -1.9),
    "marion_kervella": (1.4, -1.9),
}
