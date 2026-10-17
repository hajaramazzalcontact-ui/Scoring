"""Le cœur applicatif : transforme les factures brutes en portefeuille enrichi.

Une seule fonction, :func:`construire_portefeuille`, produit tout ce dont les
pages ont besoin : jours de retard, niveau, score expliqué, probabilités de
paiement, profil du client et prochaine échéance de niveau.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import ai, cashflow, config, db, messages, prediction, scoring

# ---------------------------------------------------------------------------
# Enrichissement
# ---------------------------------------------------------------------------
def construire_portefeuille(
    params: dict | None = None,
    factures: list[dict] | None = None,
    reglements: list[dict] | None = None,
    date_reference: date | None = None,
) -> pd.DataFrame:
    """Renvoie le portefeuille complet, trié par score décroissant."""
    params = params or db.lire_params()
    factures = db.lister_factures() if factures is None else factures
    reglements = db.lister_reglements() if reglements is None else reglements
    date_reference = date_reference or date.today()

    if not factures:
        return pd.DataFrame(columns=list(COLONNES_PORTEFEUILLE))

    seuils = config.seuils(params)
    montants_actifs = [
        float(f.get("montant") or 0) for f in factures if f.get("statut") != "payee"
    ]
    paquet = prediction.modeles(reglements)

    lignes = []
    for facture in factures:
        ligne = dict(facture)
        echeance = facture.get("echeance")
        statut = facture.get("statut") or "impayee"
        # --- Retard -------------------------------------------------------
        if statut == "payee":
            jours = 0
        elif echeance is None:
            jours = 0
        else:
            jours = (date_reference - echeance).days
        ligne["jours_retard"] = int(jours)
        ligne["jours_avant_echeance"] = int(-jours) if jours < 0 else 0

        # --- Niveau -------------------------------------------------------
        if statut == "payee":
            code_niveau = config.NIVEAU_A_JOUR["code"]
        else:
            code_niveau = scoring.calculer_niveau(int(jours), seuils)
        definition = config.niveau(code_niveau)
        ligne["niveau"] = code_niveau
        ligne["niveau_nom"] = definition["nom"]
        ligne["niveau_icone"] = definition["icone"]
        ligne["niveau_ordre"] = definition["ordre"]
        ligne["couleur"] = definition["couleur"]
        ligne["action_prevue"] = definition["action"]
        ligne["canal"] = definition["canal"]
        prochain, restant = scoring.prochain_niveau(int(jours), seuils)
        ligne["prochain_niveau"] = prochain
        ligne["prochain_niveau_nom"] = config.niveau(prochain)["nom"] if prochain else None
        ligne["jours_avant_prochain"] = restant
        ligne["prochaine_echeance"] = (
            echeance + timedelta(days=seuils[prochain]) if (prochain and echeance) else None
        )
        ligne["statut_libelle"] = config.STATUTS.get(statut, statut)

        # --- Prédiction ---------------------------------------------------
        estimation = prediction.predire(
            {
                "jours_retard": int(jours),
                "montant": float(facture.get("montant") or 0),
                "client": facture.get("client"),
            },
            bundle=paquet,
        )
        ligne.update(
            {
                "p7": estimation["p7"],
                "p15": estimation["p15"],
                "p30": estimation["p30"],
                "date_probable": estimation["date_probable"],
                "profil": estimation["profil"],
                "profil_nom": estimation["profil_nom"],
                "profil_icone": estimation["profil_icone"],
                "profil_resume": estimation["profil_resume"],
                "profil_conseil": estimation["profil_conseil"],
                "prediction_source": estimation["source"],
                "stats_client": estimation["stats_client"],
            }
        )

        # --- Score --------------------------------------------------------
        rang = scoring.rang_percentile(float(facture.get("montant") or 0), montants_actifs)
        resultat = scoring.calculer_score(
            jours_retard=int(jours) if statut != "payee" else 0,
            montant=float(facture.get("montant") or 0),
            nb_retards_passes=int(facture.get("nb_retards_passes") or 0),
            proba_paiement_30j=estimation["p30"],
            rang_montant=rang,
            params=params,
        )
        ligne["rang_montant"] = rang
        ligne["score"] = 0 if statut == "payee" else resultat["score"]
        ligne["explication_score"] = resultat["explication"]
        ligne["composantes"] = resultat["composantes"]
        ligne["critere_dominant"] = scoring.composante_dominante(resultat["composantes"])
        ligne["priorite"] = scoring.lettre_priorite(ligne["score"])
        ligne["nb_actions"] = db.compter_actions_facture(int(facture["id"])) if facture.get("id") else 0

        # --- Alertes de niveau -------------------------------------------
        ligne["franchit_seuil_aujourdhui"] = bool(
            statut != "payee" and code_niveau != config.NIVEAU_A_JOUR["code"] and int(jours) == seuils[code_niveau]
        )
        ligne["est_nouvelle_en_retard"] = bool(
            statut != "payee" and 0 < int(jours) <= 1 and code_niveau != config.NIVEAU_A_JOUR["code"]
        )
        lignes.append(ligne)

    portefeuille = pd.DataFrame(lignes)
    portefeuille = portefeuille.sort_values(
        ["statut", "score", "montant"], ascending=[True, False, False]
    ).reset_index(drop=True)
    return portefeuille


COLONNES_PORTEFEUILLE = (
    "id",
    "numero",
    "client",
    "montant",
    "echeance",
    "telephone",
    "email",
    "nb_retards_passes",
    "statut",
    "jours_retard",
    "niveau",
    "niveau_nom",
    "niveau_icone",
    "niveau_ordre",
    "couleur",
    "action_prevue",
    "canal",
    "prochain_niveau_nom",
    "jours_avant_prochain",
    "score",
    "explication_score",
    "composantes",
    "critere_dominant",
    "priorite",
    "p7",
    "p15",
    "p30",
    "date_probable",
    "profil",
    "profil_nom",
    "profil_icone",
    "prediction_source",
    "stats_client",
    "nb_actions",
)


def actifs(portefeuille: pd.DataFrame) -> pd.DataFrame:
    if portefeuille.empty:
        return portefeuille
    return portefeuille[portefeuille["statut"] != "payee"].copy()


def en_retard(portefeuille: pd.DataFrame) -> pd.DataFrame:
    cadre = actifs(portefeuille)
    if cadre.empty:
        return cadre
    return cadre[cadre["jours_retard"] > 0].copy()


# ---------------------------------------------------------------------------
# Synthèse
# ---------------------------------------------------------------------------
def repartition_niveaux(cadre: pd.DataFrame) -> dict[str, int]:
    """Comptage par niveau, dans l'ordre du parcours, zéros inclus."""
    base = {definition["code"]: 0 for definition in config.NIVEAUX}
    if cadre.empty:
        return base
    for code, total in cadre["niveau"].value_counts().items():
        if code in base:
            base[code] = int(total)
    return base


def synthese(portefeuille: pd.DataFrame, params: dict | None = None) -> dict:
    """Tous les indicateurs affichés sur le tableau de bord et dans le briefing."""
    params = params or db.lire_params()
    retard = en_retard(portefeuille)
    actif = actifs(portefeuille)

    total_impaye = float(actif["montant"].sum()) if not actif.empty else 0.0
    nb_retard = int(len(retard))
    retard_moyen = float(retard["jours_retard"].mean()) if not retard.empty else 0.0
    encaissement_30j = cashflow.encaissement_attendu_30j(actif.to_dict("records"), params) if not actif.empty else 0.0

    top = []
    if not retard.empty:
        for _, ligne in retard.head(5).iterrows():
            top.append(
                {
                    "numero": ligne["numero"],
                    "client": ligne["client"],
                    "montant": float(ligne["montant"]),
                    "score": int(ligne["score"]),
                    "niveau": ligne["niveau_nom"],
                    "jours_retard": int(ligne["jours_retard"]),
                }
            )

    risques = []
    if not actif.empty:
        risque = actif[(actif["profil"] == "risque") | (actif["profil"] == "recidiviste")]
        for _, ligne in risque.sort_values("montant", ascending=False).head(5).iterrows():
            risques.append(
                {
                    "client": ligne["client"],
                    "numero": ligne["numero"],
                    "montant": float(ligne["montant"]),
                    "profil": ligne["profil_nom"],
                    "proba_30": float(ligne["p30"]),
                }
            )

    changements = []
    if not actif.empty:
        for _, ligne in actif[actif["franchit_seuil_aujourdhui"]].iterrows():
            changements.append(
                {
                    "client": ligne["client"],
                    "numero": ligne["numero"],
                    "niveau": ligne["niveau_nom"],
                    "action": ligne["action_prevue"],
                }
            )

    nouvelle_retard = int(actif["est_nouvelle_en_retard"].sum()) if not actif.empty else 0

    return {
        "date": date.today().strftime("%d/%m/%Y"),
        "total_impaye": total_impaye,
        "nb_factures": int(len(actif)),
        "nb_retard": nb_retard,
        "nb_a_jour": int(len(actif) - nb_retard),
        "retard_moyen": retard_moyen,
        "montant_retard": float(retard["montant"].sum()) if not retard.empty else 0.0,
        "encaissement_30j": encaissement_30j,
        "repartition": repartition_niveaux(retard),
        "top": top,
        "risques": risques,
        "changements": changements,
        "nb_nouveaux": nouvelle_retard,
        "score_moyen": float(retard["score"].mean()) if not retard.empty else 0.0,
        "nb_actions": int(actif["nb_actions"].sum()) if not actif.empty else 0,
        "devise": params.get("devise", "MAD"),
    }


def plan_du_jour(portefeuille: pd.DataFrame, limite: int = 12) -> pd.DataFrame:
    """Les factures à traiter aujourd'hui, dans l'ordre : score décroissant."""
    cadre = en_retard(portefeuille)
    if cadre.empty:
        return cadre
    return cadre.sort_values(["score", "montant"], ascending=[False, False]).head(limite)


# ---------------------------------------------------------------------------
# Alertes et recommandations
# ---------------------------------------------------------------------------
def construire_alertes(facture: dict, params: dict, portefeuille: pd.DataFrame) -> list[dict]:
    """Liste d'alertes lisibles pour la fiche d'une facture."""
    alertes: list[dict] = []
    niveau = config.niveau(facture.get("niveau"))
    if facture.get("statut") == "payee":
        return alertes

    if facture.get("jour_retard_egal_seuil"):
        alertes.append(
            {
                "niveau": "attention",
                "texte": f"Cette facture vient d'atteindre le niveau {niveau['nom']} : c'est le moment d'agir.",
            }
        )
    if facture.get("jours_avant_prochain") is not None:
        alertes.append(
            {
                "niveau": "info",
                "texte": f"Prochain niveau ({facture.get('prochain_niveau_nom')}) dans {facture.get('jours_avant_prochain')} jour(s) : {facture.get('prochaine_echeance')}.",
            }
        )
    else:
        alertes.append(
            {
                "niveau": "grave",
                "texte": "Dernier niveau atteint : le dossier peut être transmis au conseil, preuves à l'appui.",
            }
        )
    if not facture.get("telephone") and not facture.get("email"):
        alertes.append(
            {
                "niveau": "attention",
                "texte": "Aucune coordonnée : impossible d'envoyer un SMS ou un email — complétez la fiche client.",
            }
        )
    if float(facture.get("p30") or 0) < 0.3:
        alertes.append(
            {
                "niveau": "grave",
                "texte": f"Probabilité de paiement à 30 jours faible ({(facture.get('p30') or 0) * 100:.0f} %) : préparez le dossier contentieux.",
            }
        )
    if facture.get("profil") == "risque":
        alertes.append(
            {
                "niveau": "attention",
                "texte": "Profil « à risque » : escaladez rapidement et conservez toutes les preuves de relance.",
            }
        )
    return alertes


def recommandation_locale(facture: dict, params: dict) -> dict:
    """Recommandation de repli, calculée localement (utilisée sans IA)."""
    profil = facture.get("profil")
    niveau = config.niveau(facture.get("niveau"))
    p30 = float(facture.get("p30") or 0)
    jours = int(facture.get("jours_retard") or 0)
    nb_relances = int(facture.get("nb_actions") or 0)
    montant = float(facture.get("montant") or 0)

    if facture.get("statut") == "payee":
        return {"action": "Aucune : la facture est réglée.", "raison": "Dossier clôturé.", "canal": "—", "source": "local"}

    if profil == "oublieux":
        action = "Envoyer le SMS de rappel et programmer un email de confirmation si rien ne bouge sous 48 h."
        raison = "Ce client paie, mais toujours après un rappel écrit : l'appel est inutile et coûteux."
        canal = "sms"
    elif profil == "lent_fiable":
        action = "Relance écrite courtoise, en proposant spontanément un échéancier en deux versements."
        raison = "Le client paie systématiquement, mais avec 3 à 8 semaines de décalage : la pression dégrade la relation sans accélérer l'encaissement."
        canal = "email"
    elif profil == "recidiviste":
        action = "Appeler pour obtenir une date de paiement ferme, puis confirmer par email."
        raison = f"{nb_relances} relance(s) déjà enregistrée(s) et des retards répétés : l'écrit seul ne produit plus d'effet."
        canal = "appel"
    elif profil == "risque":
        action = "Appliquer le niveau suivant sans délai et constituer le dossier de preuves (journal des relances)."
        raison = f"Probabilité de paiement à 30 jours de seulement {p30 * 100:.0f} % : le temps joue contre vous."
        canal = "courrier"
    elif p30 >= 0.75:
        action = f"Simple rappel automatique : le paiement est probable sous 30 jours ({p30 * 100:.0f} %)."
        raison = "Aucun signal de risque : ne consommez pas de temps commercial sur ce dossier."
        canal = "sms"
    else:
        action = f"Appliquer le niveau {niveau['nom']} — {niveau['action'].lower()}."
        raison = f"Retard de {jours} jours et probabilité de paiement modérée ({p30 * 100:.0f} %)."
        canal = niveau["canal"]

    if montant > 0 and jours >= 30 and profil in ("risque", "recidiviste"):
        action += " Vérifier aussi la possibilité d'un échéancier en 3 fois pour éviter le contentieux."
    return {"action": action, "raison": raison, "canal": canal, "source": "local"}


def recommandation(facture: dict, params: dict, portefeuille: pd.DataFrame, avec_ia: bool = True) -> dict:
    """Recommandation IA si disponible, sinon la version locale."""
    locale = recommandation_locale(facture, params)
    if not avec_ia or not ai.disponible(params):
        return locale
    suggestion = ai.recommander_action(
        facture=facture,
        niveau_nom=config.niveau(facture.get("niveau"))["nom"],
        profil=facture.get("profil_nom") or "inconnu",
        statistiques=facture.get("stats_client") or {},
        historique=db.lister_actions(facture_id=int(facture.get("id") or 0), limite=8),
        params=params,
    )
    if suggestion and suggestion.get("action"):
        suggestion["source"] = "ia"
        suggestion.setdefault("raison", locale["raison"])
        suggestion.setdefault("canal", locale["canal"])
        return suggestion
    return locale


def message_pour(
    facture: dict,
    params: dict,
    ton: str | None = None,
    langue: str | None = None,
    avec_ia: bool = True,
) -> dict:
    """Message prêt à envoyer : modèle local, éventuellement réécrit par l'IA."""
    niveau_code = facture.get("niveau") or "rappel"
    actions = db.lister_actions(facture_id=int(facture.get("id") or 0), limite=12)
    resume = "; ".join(
        f"{a.get('fait_le')} — {config.niveau(a.get('niveau')).get('nom')} : {a.get('action')}"
        for a in actions
    )
    resultat = messages.generer(
        facture,
        params,
        niveau_code=niveau_code,
        ton=ton,
        langue=langue,
        proba_30=facture.get("p30"),
        date_probable=facture.get("date_probable"),
        nb_relances=len(actions),
        historique_actions=resume or None,
    )
    resultat["historique_resume"] = resume
    if avec_ia and ai.disponible(params):
        texte = ai.rediger_message(
            facture={**facture, "nb_relances": len(actions)},
            niveau_nom=config.niveau(niveau_code)["nom"],
            canal=resultat["canal"],
            ton=resultat["ton"],
            langue=resultat["langue"],
            brouillon=resultat["texte"],
            params=params,
            profil=facture.get("profil_nom"),
            conseil_profil=facture.get("profil_conseil"),
        )
        if texte:
            resultat["texte_ia"] = texte
            resultat["source"] = "ia"
    return resultat
