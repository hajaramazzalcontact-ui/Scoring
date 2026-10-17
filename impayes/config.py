"""Constantes, niveaux de traitement et paramètres par défaut.

Toutes les valeurs réglables de l'application vivent ici : seuils des niveaux,
pondérations du score, tons et langues des messages. Les valeurs réellement
utilisées par l'application sont stockées en base (table ``params``) et
fusionnées avec ``DEFAUT_PARAMS`` par :func:`impayes.db.lire_params`.
"""
from __future__ import annotations

from pathlib import Path

APP_TITRE = "Scoring des Impayés"
APP_SOUS_TITRE = (
    "Le copilote intelligent qui transforme chaque facture en retard "
    "en action claire, au bon moment, avec le bon message."
)

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_DATA = RACINE / "data"

# ---------------------------------------------------------------------------
# Niveaux de traitement
# ---------------------------------------------------------------------------
# Le code est un identifiant stable (jamais affiché) : il permet de renommer
# un niveau sans casser les données déjà enregistrées.
NIVEAUX: list[dict] = [
    {
        "code": "rappel",
        "ordre": 1,
        "nom": "Rappel",
        "icone": "🟢",
        "action": "SMS de rappel",
        "canal": "sms",
        "ton": "Courtois, bienveillant",
        "couleur": "#16a34a",
        "description": "Probable oubli : un rappel suffit, sans mettre la pression.",
    },
    {
        "code": "contact",
        "ordre": 2,
        "nom": "Contact",
        "icone": "🟡",
        "action": "Appel téléphonique",
        "canal": "appel",
        "ton": "Cordial, à l'écoute",
        "couleur": "#ca8a04",
        "description": "L'écrit n'a pas suffi : un appel permet de comprendre le motif.",
    },
    {
        "code": "relance",
        "ordre": 3,
        "nom": "Relance",
        "icone": "🟠",
        "action": "Email personnalisé",
        "canal": "email",
        "ton": "Ferme et professionnel",
        "couleur": "#ea580c",
        "description": "Le retard s'installe : relance écrite traçable et datée.",
    },
    {
        "code": "miseendemeure",
        "ordre": 4,
        "nom": "Mise en demeure",
        "icone": "🔴",
        "action": "Mise en demeure",
        "canal": "courrier",
        "ton": "Formel, juridique",
        "couleur": "#dc2626",
        "description": "Dernière étape amiable avant transmission du dossier.",
    },
    {
        "code": "contentieux",
        "ordre": 5,
        "nom": "Contentieux",
        "icone": "⚫",
        "action": "Transmission à l'avocat",
        "canal": "avocat",
        "ton": "Dossier complet avec preuves",
        "couleur": "#1f2937",
        "description": "Le dossier part chez le conseil, pièces et preuves jointes.",
    },
]

NIVEAU_A_JOUR = {
    "code": "a_jour",
    "ordre": 0,
    "nom": "À jour",
    "icone": "⚪",
    "action": "Aucune action",
    "canal": "-",
    "ton": "-",
    "couleur": "#64748b",
    "description": "Échéance non dépassée : rien à faire aujourd'hui.",
}

NIVEAUX_PAR_CODE = {n["code"]: n for n in NIVEAUX}
NIVEAUX_PAR_CODE[NIVEAU_A_JOUR["code"]] = NIVEAU_A_JOUR


def niveau(code: str | None) -> dict:
    """Renvoie la définition d'un niveau, ``À jour`` par défaut."""
    return NIVEAUX_PAR_CODE.get(code or "", NIVEAU_A_JOUR)


def niveau_par_ordre(ordre: int) -> dict | None:
    """Renvoie le niveau dont l'ordre correspond (1..5), sinon ``None``."""
    for n in NIVEAUX:
        if n["ordre"] == ordre:
            return n
    return None


# ---------------------------------------------------------------------------
# Statuts de facture
# ---------------------------------------------------------------------------
STATUTS = {
    "impayee": "Impayée",
    "echelonnee": "Échelonnée",
    "litige": "En litige",
    "payee": "Payée",
}
STATUTS_CLOTURES = ("payee",)

# ---------------------------------------------------------------------------
# Tons, langues, profils
# ---------------------------------------------------------------------------
TONS = ["bienveillant", "neutre", "ferme"]
TONS_LIBELLES = {
    "bienveillant": "🤝 Bienveillant",
    "neutre": "⚖️ Neutre",
    "ferme": "📌 Ferme",
}

LANGUES = ["fr", "en", "ar"]
LANGUES_LIBELLES = {
    "fr": "🇫🇷 Français",
    "en": "🇬🇧 English",
    "ar": "🇲🇦 العربية",
}
LANGUES_RTL = ("ar",)

PROFILS = {
    "fiable": {
        "nom": "Fiable",
        "icone": "🟢",
        "resume": "Paie à l'échéance ou presque.",
        "conseil": "Rappel automatique, aucun effort commercial à fournir.",
    },
    "oublieux": {
        "nom": "Oublieux",
        "icone": "🔵",
        "resume": "Paie, mais toujours après un rappel.",
        "conseil": "Un SMS ou un email suffit ; inutile d'appeler.",
    },
    "lent_fiable": {
        "nom": "Lent mais fiable",
        "icone": "🟡",
        "resume": "Retard récurrent de quelques semaines, mais paie toujours.",
        "conseil": "Relance écrite, ton courtois, pas de mise en demeure précipitée.",
    },
    "recidiviste": {
        "nom": "Récidiviste",
        "icone": "🟠",
        "resume": "Retards longs et répétés, paie après pression.",
        "conseil": "Appel téléphonique dès le premier seuil + engagement daté.",
    },
    "risque": {
        "nom": "À risque",
        "icone": "🔴",
        "resume": "Historique de non-paiement ou probabilité de paiement faible.",
        "conseil": "Escalade rapide, preuves accumulées, transmission anticipée.",
    },
    "inconnu": {
        "nom": "Nouveau client",
        "icone": "⚪",
        "resume": "Pas encore d'historique exploitable.",
        "conseil": "Dérouler la procédure standard du niveau atteint.",
    },
}

# ---------------------------------------------------------------------------
# Paramètres par défaut (réglables dans la page Réglages)
# ---------------------------------------------------------------------------
DEFAUT_PARAMS: dict = {
    # Entreprise
    "societe": "Ma Société",
    "ville": "Casablanca",
    "adresse": "",
    "ice": "",
    "tel_societe": "",
    "email_societe": "",
    "devise": "MAD",
    # Seuils des niveaux (en jours de retard)
    "seuil_rappel": 1,
    "seuil_contact": 8,
    "seuil_relance": 15,
    "seuil_miseendemeure": 30,
    "seuil_contentieux": 60,
    # Pondérations du score (la somme est normalisée sur 100)
    "poids_retard": 40,
    "poids_montant": 25,
    "poids_historique": 20,
    "poids_risque": 15,
    "horizon_retard": 60,  # retard à partir duquel le critère retard est saturé
    "score_max_retards": 5,  # nombre de retards passés saturant le critère historique
    # Messages
    "ton_defaut": "neutre",
    "langue_defaut": "fr",
    "delai_rappel": 48,  # heures laissées pour un rappel niveau 1
    "delai_relance": 7,  # jours laissés pour un email de relance
    "delai_miseendemeure": 8,  # jours laissés pour une mise en demeure
    "signature": "",
    # Apparence
    "theme_graphique": "plotly_white",
    # Intelligence artificielle
    "ia_actif": "1",
    "ia_modele": "claude-sonnet-4-5",
    "ia_cle_api": "",
    # Facturation / recouvrement
    "taux_interet_retard": 0.0,  # % mensuel, mentionné dans la mise en demeure
    "seuil_anomalie_montant": 3.0,  # écart-type / médiane pour signaler un montant inhabituel
}

# Champs numériques entiers (conversion à la lecture)
PARAMS_ENTIERS = (
    "seuil_rappel",
    "seuil_contact",
    "seuil_relance",
    "seuil_miseendemeure",
    "seuil_contentieux",
    "horizon_retard",
    "score_max_retards",
    "delai_rappel",
    "delai_relance",
    "delai_miseendemeure",
)
PARAMS_FLOTTANTS = ("taux_interet_retard", "seuil_anomalie_montant")

# ---------------------------------------------------------------------------
# Colonnes standard pour l'import de fichiers
# ---------------------------------------------------------------------------
COLONNES_IMPORT = {
    "client": ["client", "nom", "nom client", "raison sociale", "societe", "tiers", "customer"],
    "numero": [
        "numero",
        "n facture",
        "no facture",
        "num facture",
        "facture",
        "ref",
        "reference",
        "invoice",
        "piece",
    ],
    "montant": [
        "montant",
        "montant ttc",
        "ttc",
        "total",
        "montant mad",
        "amount",
        "solde",
        "reste",
    ],
    "echeance": ["echeance", "date echeance", "date limite", "du", "due", "due date", "echeance prevue"],
    "date_emission": ["date emission", "date facture", "emission", "date", "invoice date"],
    "telephone": ["telephone", "tel", "gsm", "mobile", "phone", "portable"],
    "email": ["email", "mail", "courriel", "e mail"],
    "nb_retards_passes": ["nb retards", "retards", "retards passes", "nombre retards", "historique retards"],
}


def seuils(params: dict) -> dict[str, int]:
    """Extrait le dict des seuils utilisable par :mod:`impayes.scoring`."""
    return {
        "rappel": int(params.get("seuil_rappel", 1)),
        "contact": int(params.get("seuil_contact", 8)),
        "relance": int(params.get("seuil_relance", 15)),
        "miseendemeure": int(params.get("seuil_miseendemeure", 30)),
        "contentieux": int(params.get("seuil_contentieux", 60)),
    }


def seuils_valides(params: dict) -> tuple[bool, str]:
    """Vérifie que les seuils sont croissants et positifs."""
    s = seuils(params)
    ordre = ["rappel", "contact", "relance", "miseendemeure", "contentieux"]
    libelles = {n["code"]: n["nom"] for n in NIVEAUX}
    precedent = 0
    for code in ordre:
        if s[code] <= precedent:
            return (
                False,
                "Les seuils doivent être strictement croissants : "
                + " ≤ ".join(f"{libelles[c]} {s[c]} j" for c in ordre),
            )
        precedent = s[code]
    if s["rappel"] < 1:
        return False, "Le premier seuil (Rappel) doit être au minimum de 1 jour."
    return True, "Seuils cohérents."
