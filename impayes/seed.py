"""Jeu de démonstration : clients, historique de paiement et factures du jour.

L'historique synthétique sert aussi de jeu d'entraînement au modèle de
prédiction : sans lui, les probabilités resteraient des estimations par défaut.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from . import config, db

CLIENTS_DEMO = [
    # nom, profil, téléphone, email, montant moyen, nb de factures d'historique
    ("Atlas Distribution SARL", "fiable", "0661 22 33 44", "compta@atlas-distrib.ma", 18000, 9),
    ("Clinique Anouar", "lent_fiable", "0662 34 56 78", "facturation@clinique-anouar.ma", 42000, 8),
    ("École Al Manar", "oublieux", "0663 45 67 89", "finance@almanar.ma", 9500, 7),
    ("Boulangerie Baraka", "oublieux", "0664 56 78 90", "baraka.boulangerie@gmail.com", 4200, 6),
    ("Garage Tazi & Fils", "recidiviste", "0665 67 89 01", "tazi.facturation@outlook.com", 27000, 8),
    ("Café Nour", "fiable", "0666 78 90 12", "cafe.nour@menara.ma", 3800, 6),
    ("Menuiserie Benjelloun", "lent_fiable", "0667 89 01 23", "benjelloun.bois@gmail.com", 33000, 7),
    ("Prestige Traiteur", "recidiviste", "0668 90 12 34", "contact@prestige-traiteur.ma", 21000, 7),
    ("Immobilière Chaouia", "risque", "0669 01 23 45", "gestion@chaouia-immo.ma", 55000, 7),
    ("Pharmacie Riad", "fiable", "0670 12 34 56", "pharmacie.riad@gmail.com", 12000, 5),
    ("Bureau d'études Massira", "risque", "0671 23 45 67", "direction@be-massira.ma", 38000, 6),
    ("Coopérative Tifnout", "lent_fiable", "0672 34 56 78", "coop.tifnout@gmail.com", 16000, 6),
]

# Délai (en jours) entre échéance et paiement, par profil — paires (min, max)
DELAIS_PROFIL = {
    "fiable": (0, 4),
    "oublieux": (4, 22),
    "lent_fiable": (18, 55),
    "recidiviste": (35, 95),
    "risque": (60, 190),
}

FACTURES_DU_JOUR = [
    # client, jours de retard, montant, commentaire
    ("Atlas Distribution SARL", 3, 14500, "Oubli probable : premier retard du client."),
    ("Café Nour", 5, 3200, "Petit montant, client habituellement à jour."),
    ("Pharmacie Riad", 6, 9800, "Relance automatique suffisante."),
    ("École Al Manar", 11, 11200, "Deuxième retard cette année."),
    ("Clinique Anouar", 13, 48500, "Gros montant, client lent mais solvable."),
    ("Boulangerie Baraka", 19, 4600, "Urgence faible, mais récidive à surveiller."),
    ("Menuiserie Benjelloun", 24, 36000, "Montant significatif, retard qui s'installe."),
    ("Garage Tazi & Fils", 34, 29500, "Quatrième retard : ton ferme nécessaire."),
    ("Prestige Traiteur", 41, 23800, "Retards répétés, promesses non tenues."),
    ("Immobilière Chaouia", 52, 61000, "Montant le plus élevé du portefeuille."),
    ("Bureau d'études Massira", 68, 41200, "Profil à risque : dossier à préparer."),
    ("Coopérative Tifnout", 96, 18500, "Le plus ancien impayé de la liste."),
]


def _aleatoire(graine: int = 42) -> random.Random:
    return random.Random(graine)


def historique_demo(graine: int = 42) -> list[dict]:
    """Génère l'historique de règlements (3 ans) — jeu d'entraînement du modèle."""
    alea = _aleatoire(graine)
    aujourdhui = date.today()
    lignes: list[dict] = []
    compteur = 1
    for nom, profil, _tel, _mail, montant_moyen, nb in CLIENTS_DEMO:
        mini, maxi = DELAIS_PROFIL[profil]
        for _ in range(nb):
            # échéance répartie sur les 36 derniers mois
            echeance = aujourdhui - timedelta(days=alea.randint(60, 1080))
            retard = max(int(alea.gauss((mini + maxi) / 2, (maxi - mini) / 3)), mini)
            retard = min(retard, maxi + 20)
            montant = round(montant_moyen * alea.uniform(0.55, 1.55), -1)
            lignes.append(
                {
                    "client": nom,
                    "numero": f"H-{echeance.year}-{compteur:04d}",
                    "montant": montant,
                    "echeance": echeance,
                    "date_paiement": echeance + timedelta(days=retard),
                    "jours_retard": retard,
                    "montant_paye": montant,
                    "source": "demo",
                }
            )
            compteur += 1
    return lignes


def factures_demo() -> list[dict]:
    """Les factures en retard du jour, réparties sur les cinq niveaux."""
    aujourdhui = date.today()
    contacts = {nom: (tel, mail) for nom, _p, tel, mail, _m, _n in CLIENTS_DEMO}
    profils = {nom: profil for nom, profil, *_ in CLIENTS_DEMO}
    historique = {}
    for ligne in historique_demo():
        historique[ligne["client"]] = historique.get(ligne["client"], 0)
        if ligne["jours_retard"] > 0:
            historique[ligne["client"]] += 1

    factures = []
    for index, (client, retard, montant, note) in enumerate(FACTURES_DU_JOUR, start=1):
        tel, mail = contacts.get(client, ("", ""))
        factures.append(
            {
                "numero": f"F-{aujourdhui.year}-{index:03d}",
                "client": client,
                "montant": float(montant),
                "date_emission": aujourdhui - timedelta(days=retard + 30),
                "echeance": aujourdhui - timedelta(days=retard),
                "telephone": tel,
                "email": mail,
                "nb_retards_passes": historique.get(client, 0),
                "statut": "impayee",
                "notes": f"{note} Profil attendu : {config.PROFILS[profils.get(client, 'inconnu')]['nom']}.",
                "source": "demo",
            }
        )
    # Deux factures à venir, pour montrer le niveau « À jour »
    factures.append(
        {
            "numero": f"F-{aujourdhui.year}-101",
            "client": "Coopérative Tifnout",
            "montant": 7400.0,
            "date_emission": aujourdhui - timedelta(days=5),
            "echeance": aujourdhui + timedelta(days=12),
            "telephone": "0672 34 56 78",
            "email": "coop.tifnout@gmail.com",
            "nb_retards_passes": 2,
            "statut": "impayee",
            "notes": "Échéance à venir : aucun rappel à envoyer aujourd'hui.",
            "source": "demo",
        }
    )
    return factures


def charger_donnees_demo(remplacer: bool = False, avec_historique: bool = True) -> dict:
    """Insère les données de démonstration. Renvoie un récapitulatif."""
    if remplacer:
        db.supprimer_tout()
    factures = factures_demo()
    db.ajouter_factures(factures)
    nb_reglements = 0
    if avec_historique:
        nb_reglements = db.ajouter_reglements(historique_demo())
    for facture in factures:
        db.journaliser(
            action="Facture enregistrée (import de démonstration)",
            numero=facture["numero"],
            client=facture["client"],
            niveau=config.NIVEAU_A_JOUR["code"],
            canal="—",
            note="Donnée de démonstration générée par l'application.",
        )
    db.maj_param("date_derniere_demo", date.today().isoformat())
    return {"factures": len(factures), "reglements": nb_reglements}
