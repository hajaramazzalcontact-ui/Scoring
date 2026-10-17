"""Test de fumée : vérifie le moteur complet sans lancer l'interface.

Usage :
    python tests/smoke_test.py

Le test s'exécute sur une base temporaire : vos données réelles ne sont pas touchées.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

# La console Windows est en cp1252 : on force UTF-8 pour afficher les accents.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# Base jetable AVANT d'importer le paquet (le chemin est lu à l'import).
TEMPORAIRE = Path(tempfile.mkdtemp(prefix="impayes_test_"))
os.environ["IMPAYES_DB"] = str(TEMPORAIRE / "test.db")

import pandas as pd  # noqa: E402

from impayes import (  # noqa: E402
    ai, cashflow, config, db, ingesta, messages, prediction, reporting, scoring, seed, service,
)

ECHECS: list[str] = []


def verifier(condition, libelle: str) -> None:
    if condition:
        print(f"  ok   {libelle}")
    else:
        print(f"  ECHEC {libelle}")
        ECHECS.append(libelle)


def titre(texte: str) -> None:
    print(f"\n=== {texte} ===")


def main() -> int:
    titre("1. Base de données")
    db.init_db()
    params = db.lire_params()
    verifier(params["societe"] == "Ma Société", "paramètres par défaut chargés")
    verifier(config.seuils_valides(params)[0], "seuils par défaut cohérents")

    titre("2. Jeu de démonstration")
    resume = seed.charger_donnees_demo(remplacer=True)
    verifier(resume["factures"] == 13, f"13 factures de démonstration insérées ({resume['factures']})")
    verifier(resume["reglements"] > 60, f"historique de règlements généré ({resume['reglements']})")

    titre("3. Portefeuille enrichi")
    portefeuille = service.construire_portefeuille(params)
    verifier(not portefeuille.empty, "portefeuille non vide")
    verifier(
        portefeuille["score"].between(0, 100).all(),
        "tous les scores sont dans l'intervalle 0-100",
    )
    retard = service.en_retard(portefeuille)
    niveaux_obtenus = set(retard["niveau"])
    verifier(len(niveaux_obtenus) == 5, f"les cinq niveaux sont représentés ({sorted(niveaux_obtenus)})")
    verifier(
        retard["score"].is_monotonic_decreasing,
        "les factures en retard sont triées par score décroissant",
    )
    verifier(
        (retard.sort_values("jours_retard")["score"].diff().dropna() >= -60).all(),
        "le score ne s'effondre pas quand le retard augmente (contrôle de bon sens)",
    )
    mesures = retard.copy()
    mesures["rang_retard"] = mesures["jours_retard"].rank()
    mesures["rang_score"] = mesures["score"].rank()
    correlation = mesures["rang_retard"].corr(mesures["rang_score"], method="spearman")
    verifier(correlation > 0.5, f"corrélation retard/score positive (rho = {correlation:.2f})")

    titre("4. Explication et composantes du score")
    premiere = retard.iloc[0]
    verifier("Score" in premiere["explication_score"], "l'explication commence par le score")
    verifier(len(premiere["composantes"]) == 4, "quatre composantes de score")
    verifier(
        abs(sum(premiere["composantes"].values()) - premiere["score"]) < 2,
        "la somme des composantes correspond au score",
    )
    print(f"       exemple : {premiere['explication_score']}")

    titre("5. Prédiction de paiement")
    paquet = prediction.modeles(db.lister_reglements())
    verifier(paquet["source"] == "modele", "le modèle s'entraîne sur l'historique de démonstration")
    verifier(paquet.get("auc") is not None, f"qualité mesurée (AUC = {paquet.get('auc')})")
    estimations = [prediction.predire(ligne.to_dict(), paquet) for _, ligne in retard.head(5).iterrows()]
    verifier(
        all(e["p7"] <= e["p15"] <= e["p30"] for e in estimations),
        "probabilités croissantes avec l'horizon (7 j <= 15 j <= 30 j)",
    )
    verifier(
        all(0.0 <= e["p30"] <= 1.0 for e in estimations),
        "probabilités bornées entre 0 et 1",
    )
    verifier(all(e["profil"] for e in estimations), "profil de paiement attribué à chaque facture")
    for estimation in estimations[:2]:
        print(
            f"       {estimation['profil_nom']:<16} p7={estimation['p7']:.2f} "
            f"p15={estimation['p15']:.2f} p30={estimation['p30']:.2f} "
            f"date probable={estimation['date_probable']}"
        )

    titre("6. Messages : 5 niveaux × 3 tons × 3 langues")
    facture = retard.iloc[0].to_dict()
    total = 0
    for definition in config.NIVEAUX:
        for langue in config.LANGUES:
            for ton in config.TONS:
                message = messages.generer(
                    facture, params, niveau_code=definition["code"], ton=ton, langue=langue
                )
                total += 1
                if not message["texte"] or len(message["texte"]) < 40:
                    ECHECS.append(f"message vide {definition['code']}/{langue}/{ton}")
    verifier(total == 45, f"45 messages générés ({total})")
    verifier(
        not any(e.startswith("message vide") for e in ECHECS),
        "aucun message vide",
    )
    sms = messages.generer(facture, params, niveau_code="rappel", ton="bienveillant")
    verifier(len(sms["texte"]) < 700, f"SMS de longueur raisonnable ({len(sms['texte'])} caractères)")
    med = messages.generer(facture, params, niveau_code="miseendemeure")
    controles = messages.controle_juridique(med["texte"], facture, params)
    verifier(all(c["ok"] for c in controles), "mise en demeure : toutes les mentions obligatoires présentes")
    verifier(
        all(messages.generer(facture, params, niveau_code=n, langue=l)["texte"]
            for n in ["rappel", "contact", "relance", "miseendemeure", "contentieux"]
            for l in config.LANGUES),
        "les cinq niveaux existent dans les trois langues",
    )

    titre("7. Recommandations")
    recommandation = service.recommandation_locale(facture, params)
    verifier(bool(recommandation["action"]) and bool(recommandation["raison"]), "recommandation locale complète")
    print(f"       {recommandation['action']}")

    titre("8. Trésorerie")
    actif = service.actifs(portefeuille)
    simulation = cashflow.simuler(actif.to_dict("records"), params)
    verifier(len(simulation["par_horizon"]) == 3, "trois horizons projetés (7, 30, 90 jours)")
    verifier(
        (simulation["par_horizon"]["prudent"] <= simulation["par_horizon"]["realiste"]).all()
        and (simulation["par_horizon"]["realiste"] <= simulation["par_horizon"]["optimiste"]).all(),
        "scénarios ordonnés prudent <= realiste <= optimiste",
    )
    verifier(
        (simulation["par_horizon"]["sans_relance"] <= simulation["par_horizon"]["realiste"]).all(),
        "la relance augmente l'encaissement attendu",
    )
    print(simulation["par_horizon"].to_string(index=False))

    titre("9. Journal et exports")
    db.journaliser(
        action="Relance envoyée — Email personnalisé",
        facture_id=int(facture["id"]), numero=facture["numero"], client=facture["client"],
        niveau="relance", canal="Email", ton="neutre", langue="fr", message="Bonjour, …",
    )
    actions = db.lister_actions()
    verifier(len(actions) > 0, "le journal enregistre les actions")
    pdf = reporting.journal_pdf(actions, params, facture)
    verifier(pdf[:4] == b"%PDF", f"journal PDF généré ({len(pdf) // 1024} Ko)")
    excel = reporting.factures_excel(portefeuille, params)
    verifier(excel[:2] == b"PK", f"classeur Excel généré ({len(excel) // 1024} Ko)")
    verifier(len(reporting.csv_bytes(portefeuille)) > 100, "export CSV généré")

    titre("10. Import et anomalies")
    modele = pd.DataFrame(
        [
            {"client": "Atlas Distribution SARL", "numero": "IMP-001", "montant": "12 500,00",
             "echeance": "01/10/2026", "telephone": "06 11 22 33 44", "email": "a@b.ma"},
            {"client": "Garage Tazi & Fils", "numero": "IMP-002", "montant": "3 200",
             "echeance": "2026-09-15"},
            {"client": "Garage Tazi & Fils", "numero": "IMP-001", "montant": "3 200",
             "echeance": "2026-09-15"},
            {"client": "", "numero": "IMP-003", "montant": "1 000", "echeance": "2026-09-01"},
            {"client": "Immobilière Chaouia", "numero": "IMP-004", "montant": "900000",
             "echeance": "2026-09-01", "telephone": "0670 00 00 00", "email": "c@d.ma"},
            {"client": "Clinique Anouar", "numero": "IMP-005", "montant": "5 000",
             "echeance": "2020-01-01", "telephone": "0662 00 00 00", "email": "e@f.ma"},
            {"client": "Pharmacie Riad", "numero": "F-2026-001", "montant": "4 000",
             "echeance": "2026-10-01", "telephone": "0670 11 22 33", "email": "g@h.ma"},
        ]
    )
    mapping = ingesta.deviner_mapping(modele.columns)
    verifier(
        {"client", "numero", "montant", "echeance"} <= set(mapping),
        f"colonnes devinées automatiquement ({sorted(mapping)})",
    )
    lignes, rejets = ingesta.preparer_lignes(modele, mapping)
    verifier(
        len(lignes) == 6 and len(rejets) == 1,
        f"6 lignes valides, 1 rejetée, la ligne sans client ({len(lignes)}/{len(rejets)})",
    )
    verifier(lignes[0]["montant"] == 12500.0, "montant « 12 500,00 » correctement interprété")
    verifier(lignes[0]["echeance"] == date(2026, 10, 1), "date « 01/10/2026 » correctement interprétée")
    verifier(lignes[1]["email"] is None, "cellule vide interprétée comme absente, pas comme « nan »")
    anomalies = ingesta.detecter_anomalies(lignes, db.lister_factures(), params)
    types = {a["type"] for a in anomalies}
    verifier("doublon_fichier" in types, "doublon interne détecté")
    verifier("doublon_base" in types, "doublon avec la base détecté")
    verifier("montant_inhabituel" in types, "montant inhabituel détecté")
    verifier("echeance_tres_ancienne" in types, "échéance incohérente détectée")
    verifier("coordonnees_manquantes" in types, "coordonnées manquantes signalées")
    print(f"       {len(anomalies)} anomalies, types : {sorted(types)}")

    titre("11. Mise à jour du portefeuille après règlement")
    identifiant = int(facture["id"])
    db.ajouter_reglement(
        client=facture["client"], numero=facture["numero"], montant=float(facture["montant"]),
        echeance=facture["echeance"], date_paiement=date.today(),
    )
    db.maj_facture(identifiant, statut="payee", date_paiement=date.today(), montant_paye=float(facture["montant"]))
    apres = service.construire_portefeuille(db.lire_params())
    ligne = apres[apres["id"] == identifiant].iloc[0]
    verifier(ligne["statut"] == "payee", "la facture est passée en « payée »")
    verifier(int(ligne["score"]) == 0, "une facture payée a un score de 0")
    verifier(
        db.compter_reglements() == resume["reglements"] + 1,
        "le règlement alimente l'historique d'apprentissage",
    )

    titre("12. Modes dégradés")
    params_sans_ia = {**params, "ia_actif": "0", "ia_cle_api": ""}
    verifier(not ai.disponible(params_sans_ia), "IA détectée comme indisponible sans clé")
    verifier(ai.etat(params_sans_ia)["raison"], "l'état de l'IA est expliqué à l'utilisateur")
    prediction._CACHE["valeur"] = None
    heuristique = prediction.predire({"jours_retard": 20, "montant": 5000, "client": "Inconnu"}, bundle=None)
    verifier(0 < heuristique["p30"] < 1, f"repli heuristique opérationnel (p30 = {heuristique['p30']:.2f})")
    verifier(heuristique["source"] == "heuristique", "la source de l'estimation est indiquée")
    prediction._CACHE["valeur"] = None
    prediction.modeles(db.lister_reglements(), forcer=True)

    titre("Résultat")
    if ECHECS:
        print(f"{len(ECHECS)} contrôle(s) en échec :")
        for echec in ECHECS:
            print(f"  - {echec}")
        return 1
    print("Tous les contrôles sont passés.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
