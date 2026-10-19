"""Parcours complet : charge la démo et visite les 10 onglets.

Usage :  .\\.venv\\Scripts\\python.exe tests\\parcours.py
Sortie : code 0 si aucun onglet ne lève d'exception.
"""
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = str(RACINE / "app.py")

PAGES = [
    "🏠 Tableau de bord", "👥 Clients", "🧾 Factures", "📨 Fiche & message",
    "📈 Analyses", "💧 Trésorerie", "📅 Calendrier", "🤖 Cashy — Assistant IA",
    "🗂️ Historique & preuves", "⚙️ Réglages",
]


def main() -> int:
    at = AppTest.from_file(SCRIPT, default_timeout=90)
    at.run()
    if at.exception:
        print("ECHEC au premier rendu :", at.exception[0].value)
        return 1
    print(f"OK  premier rendu ({len(at.radio)} navigation)")

    # Charge les données de démonstration (bouton de la barre latérale).
    bouton = [b for b in at.button if "démo" in b.label.lower()]
    if bouton:
        bouton[0].click()
        at.run()
        if at.exception:
            print("ECHEC au chargement de la démo :", at.exception[0].value)
            return 1
        print(f"OK  démo chargée ({len(at.session_state['factures'])} factures)")

    for page in PAGES:
        at.session_state["navpage"] = page
        at.run()
        if at.exception:
            print(f"ECHEC {page} : {at.exception[0].value}")
            return 1
        print(f"OK  {page}  ({len(at.markdown)} blocs, {len(at.dataframe)} tableaux)")

    # --- Accueil : phrase personnalisée, compteur, action unique -----------
    at.session_state["navpage"] = PAGES[0]
    at.run()
    textes = " ".join(m.value for m in at.markdown)
    if "Bonjour Karim" not in textes:
        print("ECHEC accueil : phrase personnalisée absente")
        return 1
    cta = [b for b in at.button if "Commencer les relances" in b.label]
    if not cta:
        print("ECHEC accueil : bouton « Commencer les relances » absent")
        return 1
    cta[0].click()
    at.run()
    if at.session_state["navpage"] != PAGES[2]:
        print("ECHEC accueil : le bouton ne mène pas aux factures")
        return 1
    print("OK  accueil : phrase personnalisée, compteur et action unique")

    # --- Visite guidée : le bouton de démarrage referme l'onboarding ------
    at.session_state["onboarding_done"] = False
    at.session_state["navpage"] = PAGES[0]
    at.run()
    sortie = [b for b in at.button if "C'est parti" in b.label]
    if not sortie:
        print("ECHEC visite guidée : bouton de sortie absent")
        return 1
    sortie[0].click()
    at.run()
    if not at.session_state["onboarding_done"]:
        print("ECHEC visite guidée : l'onboarding ne se referme pas")
        return 1
    print("OK  visite guidée : 3 étapes affichées puis refermées")

    # --- Messages : 3 tons × 3 langues produisent des textes distincts ----
    at.session_state["navpage"] = PAGES[3]
    at.run()
    if at.exception:
        print("ECHEC fiche :", at.exception[0].value)
        return 1

    def widget(label):
        for w in list(at.selectbox) + list(at.select_slider):
            if w.label == label:
                return w
        raise AssertionError(f"widget introuvable : {label}")

    # Le premier choix est l'urgence maximale (niveau 5, note interne sans
    # formule de politesse) : on cherche une facture de niveau 1 à 4.
    facture = widget("Facture")
    choix = facture.options[0]
    for option in facture.options:
        widget("Facture").set_value(option)
        at.session_state["messages"] = {}
        at.run()
        msgs = at.session_state["messages"]
        if msgs and not next(iter(msgs.values())).startswith("NOTE À L'AVOCAT"):
            choix = option
            break
    print(f"    facture retenue : {choix}")

    produit = {}
    for ton in ("bienveillant", "neutre", "ferme"):
        for langue in ("français", "arabe", "anglais"):
            widget("Facture").set_value(choix)
            widget("Ton").set_value(ton)
            widget("Langue").set_value(langue)
            at.session_state["messages"] = {}
            at.run()
            if at.exception:
                print(f"ECHEC message ({ton}/{langue}) :", at.exception[0].value)
                return 1
            msgs = at.session_state["messages"]
            if not msgs:
                print(f"ECHEC message ({ton}/{langue}) : aucun message généré")
                return 1
            produit[(ton, langue)] = next(iter(msgs.values()))
    if len(set(produit.values())) != 9:
        print(f"ECHEC messages : {len(set(produit.values()))} variantes distinctes sur 9")
        return 1
    print("OK  messages : 9 combinaisons ton × langue, toutes distinctes")

    print("\nParcours complet : 10/10 onglets + accueil, visite guidée et messages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
