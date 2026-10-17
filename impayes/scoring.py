"""Le moteur de scoring : niveaux de traitement et note de 0 à 100.

Tout est transparent et explicable : le score est la somme de quatre critères
pondérés, chacun mesuré sur une échelle 0-1, et chaque score est accompagné
d'une phrase qui dit *pourquoi*.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config

# ---------------------------------------------------------------------------
# Niveaux de traitement
# ---------------------------------------------------------------------------
ORDRE_NIVEAUX = ["rappel", "contact", "relance", "miseendemeure", "contentieux"]


def calculer_niveau(jours_retard: int, s: dict) -> str:
    """Renvoie le code du niveau correspondant au retard (``a_jour`` avant le 1er seuil)."""
    if jours_retard < s["rappel"]:
        return config.NIVEAU_A_JOUR["code"]
    for code in reversed(ORDRE_NIVEAUX):
        if jours_retard >= s[code]:
            return code
    return config.NIVEAU_A_JOUR["code"]


def prochain_niveau(jours_retard: int, s: dict) -> tuple[str | None, int | None]:
    """Renvoie (code du niveau suivant, jours restants) ou ``(None, None)`` au dernier niveau."""
    for code in ORDRE_NIVEAUX:
        if jours_retard < s[code]:
            return code, s[code] - jours_retard
    return None, None


def etapes(facture: dict, s: dict, seuils_atteints: set[str] | None = None) -> list[dict]:
    """Frise chronologique des cinq étapes pour une facture.

    Chaque élément porte : ``code``, ``nom``, ``icone``, ``couleur``, ``etat``
    (``passe`` / ``actuel`` / ``a_venir``) et ``jours`` (seuil du niveau).
    """
    jours = int(facture.get("jours_retard") or 0)
    niveau_actuel = facture.get("niveau") or calculer_niveau(jours, s)
    seuils_atteints = seuils_atteints or set()
    indice_actuel = ORDRE_NIVEAUX.index(niveau_actuel) if niveau_actuel in ORDRE_NIVEAUX else -1
    frise = []
    for position, code in enumerate(ORDRE_NIVEAUX):
        definition = config.niveau(code)
        if code in seuils_atteints and position < indice_actuel:
            etat = "passe"  # franchi ET déjà relancé
        elif position < indice_actuel:
            etat = "depasse"
        elif position == indice_actuel:
            etat = "actuel"
        else:
            etat = "a_venir"
        frise.append(
            {
                "code": code,
                "nom": definition["nom"],
                "icone": definition["icone"],
                "couleur": definition["couleur"],
                "action": definition["action"],
                "etat": etat,
                "jours": s[code],
                "fait": code in seuils_atteints,
            }
        )
    return frise


def jours_ecoules(niveau_code: str, jours_retard: int, s: dict) -> int:
    """Nombre de jours passés dans le niveau courant."""
    if niveau_code == config.NIVEAU_A_JOUR["code"]:
        return max(jours_retard, 0)
    return max(jours_retard - s[niveau_code] + 1, 0)


def echeance_du_niveau(niveau_code: str, echeance: date, s: dict) -> date | None:
    """Date à laquelle un niveau a été atteint."""
    if niveau_code not in s:
        return None
    return echeance + timedelta(days=s[niveau_code])


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
def rang_percentile(valeur: float, population: list[float]) -> float:
    """Position relative d'une valeur dans une population, entre 0 et 1."""
    if not population:
        return 0.5
    inferieurs = sum(1 for v in population if v < valeur)
    egaux = sum(1 for v in population if v == valeur)
    if len(population) == 1:
        return 1.0
    return min((inferieurs + 0.5 * egaux) / len(population), 1.0)


def calculer_score(
    jours_retard: int,
    montant: float,
    nb_retards_passes: int = 0,
    proba_paiement_30j: float | None = None,
    rang_montant: float | None = None,
    params: dict | None = None,
) -> dict:
    """Note d'urgence 0-100 et détail de ses quatre composantes.

    :param jours_retard: jours écoulés depuis l'échéance.
    :param montant: montant impayé en devise locale.
    :param nb_retards_passes: retards déjà constatés sur ce client.
    :param proba_paiement_30j: probabilité de paiement à 30 jours (0-1), estimée par l'IA.
    :param rang_montant: position relative du montant (0-1). Calculée si absente.
    :param params: réglages (poids, horizons). Valeurs par défaut sinon.
    """
    params = params or config.DEFAUT_PARAMS
    if jours_retard <= 0:
        return {
            "score": 0,
            "composantes": {"retard": 0.0, "montant": 0.0, "historique": 0.0, "risque": 0.0},
            "explication": "Échéance non dépassée : aucune relance à déclencher.",
        }

    poids = {
        "retard": float(params.get("poids_retard", 40)),
        "montant": float(params.get("poids_montant", 25)),
        "historique": float(params.get("poids_historique", 20)),
        "risque": float(params.get("poids_risque", 15)),
    }
    total_poids = sum(poids.values()) or 1.0
    horizon = max(int(params.get("horizon_retard", 60)), 1)
    max_retards = max(int(params.get("score_max_retards", 5)), 1)

    # 1. Durée du retard — courbe légèrement concave : tôt = déjà significatif.
    duree = min(jours_retard / horizon, 1.0) ** 0.85
    # 2. Poids financier — position du montant parmi les créances en cours.
    financier = 1.0 if rang_montant is None else min(max(rang_montant, 0.0), 1.0)
    # 3. Récidive — nombre de retards passés du client.
    recidive = min(nb_retards_passes / max_retards, 1.0)
    # 4. Risque — probabilité de ne pas payer sous 30 jours.
    if proba_paiement_30j is None:
        risque = 0.5
    else:
        risque = 1.0 - min(max(proba_paiement_30j, 0.0), 1.0)

    brut = {
        "retard": duree * poids["retard"],
        "montant": financier * poids["montant"],
        "historique": recidive * poids["historique"],
        "risque": risque * poids["risque"],
    }
    # Normalisation : le score reste sur 100 même si l'utilisateur change les poids.
    facteur = 100.0 / total_poids
    composantes = {cle: round(valeur * facteur, 1) for cle, valeur in brut.items()}
    score = int(round(min(sum(composantes.values()), 100)))

    return {
        "score": score,
        "composantes": composantes,
        "explication": expliquer(
            score, composantes, jours_retard, montant, nb_retards_passes, proba_paiement_30j, rang_montant, params
        ),
    }


def expliquer(
    score: int,
    composantes: dict,
    jours_retard: int,
    montant: float,
    nb_retards_passes: int,
    proba_paiement_30j: float | None,
    rang_montant: float | None,
    params: dict,
) -> str:
    """Une phrase qui justifie le score, sans boîte noire."""
    if score <= 0:
        return "Échéance non dépassée : aucune relance à déclencher."
    devise = params.get("devise", "MAD")
    morceaux = [f"Retard de {jours_retard} jour{'s' if jours_retard > 1 else ''}"]
    if rang_montant is not None:
        pourcent = int(round((1 - rang_montant) * 100))
        if pourcent <= 20:
            morceaux.append(f"montant dans le top {max(pourcent, 5)} % des impayés")
        elif pourcent >= 80:
            morceaux.append("montant parmi les plus faibles du portefeuille")
        else:
            morceaux.append(f"montant au {100 - pourcent}ᵉ centile")
    morceaux.append(f"{montant:,.0f} {devise}".replace(",", " "))
    if nb_retards_passes:
        morceaux.append(f"{nb_retards_passes} retard{'s' if nb_retards_passes > 1 else ''} passé{'s' if nb_retards_passes > 1 else ''}")
    else:
        morceaux.append("aucun retard antérieur")
    if proba_paiement_30j is not None:
        morceaux.append(f"probabilité de paiement à 30 jours estimée à {proba_paiement_30j * 100:.0f} %")
    return f"Score {score} : " + ", ".join(morceaux) + "."


def composante_dominante(composantes: dict) -> str:
    """Critère qui pèse le plus dans le score (pour les graphiques et le tri)."""
    if not composantes:
        return "-"
    libelles = {
        "retard": "Durée du retard",
        "montant": "Montant impayé",
        "historique": "Historique du client",
        "risque": "Risque de non-paiement",
    }
    cle = max(composantes, key=composantes.get)
    return libelles[cle]


def lettre_priorite(score: int) -> str:
    """Étiquette lisible pour le tri visuel."""
    if score >= 80:
        return "P1 — critique"
    if score >= 65:
        return "P2 — élevée"
    if score >= 45:
        return "P3 — moyenne"
    if score >= 25:
        return "P4 — modérée"
    return "P5 — faible"
