"""Prédiction de paiement et profils clients.

Deux étages, dans cet ordre :

1. **Modèle appris** — une régression logistique par horizon (7, 15 et 30 jours)
   entraînée sur l'historique des règlements (table ``reglements``). Elle répond
   à « ce type de créance a-t-il été payé dans les 30 jours, par le passé ? ».
2. **Heuristique de repli** — dès que l'historique est trop mince, une formule
   explicite prend le relais. L'application ne bloque jamais faute de données.

Le module n'importe pas Streamlit : il reste testable en ligne de commande.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from . import config

HORIZONS = (7, 15, 30)
MIN_LIGNES_MODELE = 40
MIN_CLASSE_MODELE = 8

# Cache d'entraînement : le modèle ne se réentraîne que si l'historique change.
_CACHE: dict = {"cle": None, "valeur": None}


# ---------------------------------------------------------------------------
# Statistiques par client
# ---------------------------------------------------------------------------
def statistiques_clients(reglements: list[dict]) -> dict[str, dict]:
    """Agrège l'historique par client.

    Pour chaque client : nombre de règlements, retard moyen et médian, part de
    factures payées en retard, retard maximum.
    """
    par_client: dict[str, list[int]] = {}
    montants: dict[str, list[float]] = {}
    for r in reglements:
        client = r.get("client") or "—"
        par_client.setdefault(client, []).append(int(r.get("jours_retard") or 0))
        montants.setdefault(client, []).append(float(r.get("montant") or 0))

    stats: dict[str, dict] = {}
    for client, retards in par_client.items():
        tries = sorted(retards)
        n = len(tries)
        mediane = tries[n // 2] if n % 2 else (tries[n // 2 - 1] + tries[n // 2]) / 2
        stats[client] = {
            "client": client,
            "nb_reglements": n,
            "retard_moyen": sum(tries) / n,
            "retard_median": mediane,
            "retard_max": max(tries),
            "taux_retard": sum(1 for x in tries if x > 0) / n,
            "montant_moyen": sum(montants[client]) / n,
            "dernier_retard": tries[-1],
        }
    return stats


# ---------------------------------------------------------------------------
# Jeu d'entraînement
# ---------------------------------------------------------------------------
def _matrice(reglements: list[dict], stats: dict[str, dict]) -> list[list[float]]:
    """Vecteur de caractéristiques, identique pour l'entraînement et la prédiction."""
    lignes = []
    for r in reglements:
        client = r.get("client") or "—"
        st = stats.get(client, {})
        lignes.append(vecteur_caracteristiques(
            montant=float(r.get("montant") or 0),
            stats_client=st,
            montant_median_client=st.get("montant_moyen") or 0,
        ))
    return lignes


def vecteur_caracteristiques(
    montant: float,
    stats_client: dict,
    montant_median_client: float = 0.0,
    jours_retard_courant: int = 0,
) -> list[float]:
    """Caractéristiques utilisées par le modèle (toutes disponibles avant la relance)."""
    retard_moyen = float(stats_client.get("retard_moyen") or 0)
    taux_retard = float(stats_client.get("taux_retard") or 0)
    nb = float(stats_client.get("nb_reglements") or 0)
    ratio = 0.0
    if montant_median_client > 0:
        ratio = min(max(math.log1p(montant / montant_median_client), -2), 2)
    return [
        math.log1p(max(montant, 0.0)),   # taille de la créance
        retard_moyen / 30.0,             # habitude de retard du client
        taux_retard,                     # fréquence des retards
        math.log1p(nb) / 5.0,            # ancienneté de la relation
        ratio,                           # facture plus grosse que d'habitude ?
        min(jours_retard_courant / 60.0, 2.0),  # retard déjà accumulé
    ]


NOMS_CARACTERISTIQUES = [
    "log(montant)",
    "retard moyen / 30",
    "taux de retard",
    "log(ancienneté)",
    "montant relatif",
    "retard courant / 60",
]


def entrainer(reglements: list[dict], horizon: int = 30) -> dict | None:
    """Entraîne une régression logistique pour un horizon donné.

    Renvoie ``None`` si l'historique est insuffisant ou si scikit-learn est absent.
    """
    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError:  # dépendance optionnelle
        return None

    stats = statistiques_clients(reglements)
    X, y = [], []
    for r in reglements:
        paiement = r.get("date_paiement")
        echeance = r.get("echeance")
        if not (paiement and echeance):
            continue
        retard_reel = int(r.get("jours_retard") or 0)
        label = 1 if retard_reel <= horizon else 0
        y.append(label)
        X.append(vecteur_caracteristiques(
            montant=float(r.get("montant") or 0),
            stats_client=stats.get(r.get("client") or "—", {}),
        ))
    if len(X) < MIN_LIGNES_MODELE:
        return None
    positifs = sum(y)
    if positifs < MIN_CLASSE_MODELE or (len(y) - positifs) < MIN_CLASSE_MODELE:
        return None
    try:
        modele = LogisticRegression(max_iter=2000, C=0.4, class_weight="balanced")
        modele.fit(X, y)
    except (ValueError, TypeError):
        return None
    return {"modele": modele, "effectif": len(y), "taux_base": positifs / len(y), "horizon": horizon}


def _qualite(reglements: list[dict], horizon: int = 30) -> float | None:
    """AUC en validation croisée — sert d'indicateur de fiabilité affiché."""
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import cross_val_predict
        from sklearn.metrics import roc_auc_score
    except ImportError:
        return None
    stats = statistiques_clients(reglements)
    X, y = [], []
    for r in reglements:
        if not (r.get("date_paiement") and r.get("echeance")):
            continue
        y.append(1 if int(r.get("jours_retard") or 0) <= horizon else 0)
        X.append(vecteur_caracteristiques(
            montant=float(r.get("montant") or 0),
            stats_client=stats.get(r.get("client") or "—", {}),
        ))
    if len(X) < MIN_LIGNES_MODELE or len(set(y)) < 2:
        return None
    positifs = sum(y)
    if positifs < MIN_CLASSE_MODELE or (len(y) - positifs) < MIN_CLASSE_MODELE:
        return None
    plis = max(2, min(5, positifs, len(y) - positifs))
    try:
        probas = cross_val_predict(
            LogisticRegression(max_iter=2000, C=0.4, class_weight="balanced"),
            X,
            y,
            cv=plis,
            method="predict_proba",
        )[:, 1]
        return float(roc_auc_score(y, probas))
    except (ValueError, TypeError):
        return None


def modeles(reglements: list[dict], forcer: bool = False) -> dict:
    """Renvoie (et met en cache) les modèles des trois horizons + leur qualité."""
    cle = (
        len(reglements),
        max((str(r.get("date_paiement")) for r in reglements), default=""),
        sum(int(r.get("jours_retard") or 0) for r in reglements),
    )
    if not forcer and _CACHE["cle"] == cle and _CACHE["valeur"] is not None:
        return _CACHE["valeur"]

    bundle: dict = {"horizons": {}, "effectif": len(reglements), "source": "heuristique"}
    if len(reglements) >= MIN_LIGNES_MODELE:
        for horizon in HORIZONS:
            modele = entrainer(reglements, horizon)
            if modele:
                bundle["horizons"][horizon] = modele
        if bundle["horizons"]:
            bundle["source"] = "modele"
            bundle["auc"] = _qualite(reglements, 30)
    bundle["stats_clients"] = statistiques_clients(reglements)
    _CACHE["cle"] = cle
    _CACHE["valeur"] = bundle
    return bundle


# ---------------------------------------------------------------------------
# Prédiction
# ---------------------------------------------------------------------------
def _probas_exponentielles(p30: float) -> dict[int, float]:
    """Décline une probabilité à 30 jours sur 7 et 15 jours (loi exponentielle)."""
    p30 = min(max(p30, 0.01), 0.99)
    taux = -math.log(1 - p30) / 30.0
    return {h: 1 - math.exp(-taux * h) for h in HORIZONS}


def proba_heuristique(jours_retard: int, stats_client: dict) -> float:
    """Formule de repli, explicite et monotone.

    Plus le retard est long, plus la probabilité de paiement sous 30 jours baisse ;
    un client habitué au retard ou à la récidive est pénalisé.
    """
    base = 0.90 - 0.55 * min(max(jours_retard, 0) / 120.0, 1.0)
    retard_moyen = float(stats_client.get("retard_moyen") or 0)
    if retard_moyen > 0:
        # un client qui paie habituellement d'emblée garde une chance plus élevée
        base += 0.10 * (1 - min(retard_moyen / 60.0, 1.0))
    taux_retard = float(stats_client.get("taux_retard") or 0)
    base -= 0.12 * taux_retard
    nb = float(stats_client.get("nb_reglements") or 0)
    if nb >= 5:
        base -= 0.02
    return min(max(base, 0.03), 0.97)


def predire(
    facture: dict,
    bundle: dict | None = None,
    reglements: list[dict] | None = None,
) -> dict:
    """Estime les probabilités de paiement, la date probable et le profil du client.

    :param facture: dict avec au minimum ``jours_retard``, ``montant``, ``client``.
    """
    facture = dict(facture or {})
    jours_retard = int(facture.get("jours_retard") or 0)
    client = facture.get("client") or "—"
    montant = float(facture.get("montant") or 0)

    if bundle is None:
        bundle = modeles(reglements or []) if reglements is not None else {"horizons": {}, "stats_clients": {}, "source": "heuristique"}
    stats_client = (bundle.get("stats_clients") or {}).get(client, {})

    probabilites: dict[int, float] = {}
    source = "heuristique"
    if bundle.get("horizons"):
        try:
            vecteur = [vecteur_caracteristiques(
                montant=montant,
                stats_client=stats_client,
                montant_median_client=stats_client.get("montant_moyen") or 0,
                jours_retard_courant=jours_retard,
            )]
            for horizon, paquet in bundle["horizons"].items():
                probabilites[horizon] = float(paquet["modele"].predict_proba(vecteur)[0][1])
            source = "modele"
        except (ValueError, TypeError, KeyError):
            probabilites = {}

    if not probabilites:
        p30 = proba_heuristique(jours_retard, stats_client)
        probabilites = _probas_exponentielles(p30)

    # Cohérence : p7 <= p15 <= p30
    probabilites = {
        7: min(probabilites.get(7, 0.0), probabilites.get(15, 1.0), probabilites.get(30, 1.0)),
        15: min(probabilites.get(15, 0.0), probabilites.get(30, 1.0)),
        30: probabilites.get(30, 0.0),
    }
    # Aucune estimation n'est jamais certaine : on borne à [1 %, 99 %].
    probabilites = {h: round(min(max(v, 0.01), 0.99), 3) for h, v in probabilites.items()}

    date_probable, delai_restant = date_paiement_probable(probabilites[30], jours_retard, stats_client)
    profil = profil_client(stats_client, probabilites[30], jours_retard)

    return {
        "p7": probabilites[7],
        "p15": probabilites[15],
        "p30": probabilites[30],
        "date_probable": date_probable,
        "delai_restant": delai_restant,
        "profil": profil["code"],
        "profil_nom": profil["nom"],
        "profil_icone": profil["icone"],
        "profil_resume": profil["resume"],
        "profil_conseil": profil["conseil"],
        "source": source,
        "fiabilite": bundle.get("auc"),
        "effectif": bundle.get("effectif", 0),
        "stats_client": stats_client,
    }


def date_paiement_probable(
    p30: float, jours_retard: int, stats_client: dict
) -> tuple[date | None, int | None]:
    """Date de paiement la plus probable, à partir du taux de hasard estimé."""
    if p30 >= 0.995:
        return None, None
    taux = -math.log(1 - min(max(p30, 0.001), 0.999)) / 30.0
    if taux <= 0:
        return None, None
    # Médiane d'une loi exponentielle = ln(2)/taux (délai restant à partir d'aujourd'hui).
    mediane = math.log(2) / taux
    retard_moyen = float(stats_client.get("retard_moyen") or 0)
    if retard_moyen > 0:
        mediane *= 0.75 + 0.5 * min(retard_moyen / 60.0, 1.0)
    delai = int(round(min(mediane, 180)))
    return date.today() + timedelta(days=delai), delai


def profil_client(stats_client: dict, p30: float, jours_retard: int = 0) -> dict:
    """Classe le client dans un profil parlant (fiable, oublieux, récidiviste...)."""
    nb = int(stats_client.get("nb_reglements") or 0)
    if nb < 3:
        if p30 < 0.35:
            return {"code": "risque", **{k: config.PROFILS["risque"][k] for k in ("nom", "icone", "resume", "conseil")}}
        return {"code": "inconnu", **{k: config.PROFILS["inconnu"][k] for k in ("nom", "icone", "resume", "conseil")}}

    taux_retard = float(stats_client.get("taux_retard") or 0)
    retard_moyen = float(stats_client.get("retard_moyen") or 0)
    retard_max = float(stats_client.get("retard_max") or 0)

    if p30 < 0.40:
        code = "risque"
    elif taux_retard < 0.25:
        code = "fiable"
    elif retard_max <= 25 and retard_moyen <= 12:
        code = "oublieux"
    elif taux_retard >= 0.6 and retard_moyen >= 30:
        code = "recidiviste"
    else:
        code = "lent_fiable"
    return {"code": code, **{k: config.PROFILS[code][k] for k in ("nom", "icone", "resume", "conseil")}}


def impact_relance(probabilite: float, niveau_ordre: int) -> float:
    """Effet estimé d'une relance sur la probabilité de paiement.

    Plus la relance est douce et le client peu risqué, plus le relais est modeste ;
    une relance formelle sur un dossier installé apporte davantage.
    """
    gain = 0.05 + 0.05 * min(niveau_ordre, 5)
    if probabilite > 0.7:
        gain *= 0.6  # le client allait payer de toute façon
    return min(probabilite + gain * (1 - probabilite), 0.98)
