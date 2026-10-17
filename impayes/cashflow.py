"""Simulateur de trésorerie : combien vais-je encaisser, et quand ?

La projection s'appuie sur la probabilité de paiement de chaque facture à
7, 15 et 30 jours (module :mod:`impayes.prediction`). Trois scénarios encadrent
l'estimation :

* **prudent** — seuls les paiements les plus sûrs sont retenus ;
* **réaliste** — probabilités telles qu'estimées ;
* **optimiste** — effet maximal des relances.

Un quatrième chiffre sert de repère : « sans relance », c'est-à-dire ce qui
rentrerait sans que personne ne s'occupe des factures.
"""
from __future__ import annotations

import math

import pandas as pd

from . import prediction


def proba_a_horizon(p30: float, horizon: int) -> float:
    """Décline une probabilité à 30 jours sur un autre horizon (loi exponentielle)."""
    p30 = min(max(float(p30 or 0), 0.001), 0.999)
    if horizon == 30:
        return p30
    taux = -math.log(1 - p30) / 30.0
    return 1 - math.exp(-taux * horizon)


def _facteur_scenario(scenario: str) -> float:
    return {"prudent": 0.55, "realiste": 1.0, "optimiste": 1.25}.get(scenario, 1.0)


def simuler(
    factures: list[dict],
    params: dict | None = None,
    horizons: tuple[int, ...] = (7, 30, 90),
    avec_relance: bool = True,
) -> dict:
    """Projette les encaissements attendus pour chaque facture et chaque horizon.

    :param factures: factures enrichies (``montant``, ``p30``, ``niveau``, ``niveau_ordre``...).
    :returns: ``{"lignes": DataFrame, "par_horizon": DataFrame, "totaux": dict}``
    """
    params = params or {}
    lignes = []
    for facture in factures:
        if facture.get("statut") in ("payee",):
            continue
        montant = float(facture.get("montant") or 0)
        base = facture.get("p30") or prediction.proba_heuristique(
            int(facture.get("jours_retard") or 0), facture.get("stats_client") or {}
        )
        ordre = int(facture.get("niveau_ordre") or 0)
        if avec_relance:
            base = prediction.impact_relance(float(base), ordre)
        ligne = {
            "facture": facture.get("numero"),
            "client": facture.get("client"),
            "niveau": facture.get("niveau_nom") or facture.get("niveau"),
            "montant": montant,
            "profil": facture.get("profil_nom"),
            "date_probable": facture.get("date_probable"),
        }
        for horizon in horizons:
            proba = proba_a_horizon(base, horizon)
            ligne[f"p{horizon}"] = proba
            ligne[f"attendu_{horizon}"] = montant * proba
            ligne[f"attendu_{horizon}_sans_relance"] = montant * proba_a_horizon(
                facture.get("p30") or base, horizon
            )
        lignes.append(ligne)

    tableau = pd.DataFrame(lignes)
    if tableau.empty:
        tableau = pd.DataFrame(
            columns=["facture", "client", "niveau", "montant", "profil", "date_probable"]
        )

    lignes_horizon = []
    for horizon in horizons:
        colonne = f"attendu_{horizon}"
        sans = f"attendu_{horizon}_sans_relance"
        total_realiste = float(tableau[colonne].sum()) if colonne in tableau else 0.0
        total_sans = float(tableau[sans].sum()) if sans in tableau else 0.0
        lignes_horizon.append(
            {
                "horizon": horizon,
                "sans_relance": total_sans,
                "prudent": total_realiste * _facteur_scenario("prudent"),
                "realiste": total_realiste,
                "optimiste": min(total_realiste * _facteur_scenario("optimiste"), float(tableau["montant"].sum()) if "montant" in tableau else 0.0),
            }
        )
    par_horizon = pd.DataFrame(lignes_horizon)

    totaux = {
        "impaye": float(tableau["montant"].sum()) if "montant" in tableau else 0.0,
        "nb_factures": int(len(tableau)),
        "retard_total": float(tableau["montant"].sum()) if "montant" in tableau else 0.0,
    }
    return {"lignes": tableau, "par_horizon": par_horizon, "totaux": totaux}


def encaissement_attendu_30j(factures: list[dict], params: dict | None = None) -> float:
    """Chiffre unique utilisé par le briefing et les cartes d'indicateurs."""
    resultat = simuler(factures, params, horizons=(30,))
    if resultat["par_horizon"].empty:
        return 0.0
    return float(resultat["par_horizon"].iloc[0]["realiste"])


def plan_tresorerie(factures: list[dict], params: dict | None = None) -> dict:
    """Répartition des encaissements attendus par semaine sur 90 jours (réaliste)."""
    resultat = simuler(factures, params, horizons=(7, 15, 30, 60, 90))
    return resultat
