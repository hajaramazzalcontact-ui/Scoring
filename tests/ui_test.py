"""Test d'interface : chaque page Streamlit est exécutée sans navigateur.

Usage :
    python tests/ui_test.py

Streamlit fournit un lanceur d'application (*AppTest*) : le script est exécuté
réellement et toute exception est remontée. C'est le meilleur filet de sécurité
avant d'ouvrir l'application dans un navigateur.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

TEMPORAIRE = Path(tempfile.mkdtemp(prefix="impayes_ui_"))
os.environ["IMPAYES_DB"] = str(TEMPORAIRE / "ui.db")

from streamlit.testing.v1 import AppTest  # noqa: E402

from impayes import db, seed  # noqa: E402

ECHECS: list[str] = []

PAGES = [
    ("dashboard", "🏠 Tableau de bord"),
    ("factures", "📋 Factures"),
    ("fiche", "📨 Fiche & message"),
    ("assistant", "🤖 Assistant IA"),
    ("reglages", "⚙️ Réglages & historique"),
]


def executer(script: str, libelle: str) -> None:
    """Exécute un script Streamlit en mode « sans navigateur » et inspecte les erreurs."""
    try:
        application = AppTest.from_file(str(RACINE / script))
        application.run(timeout=180)
    except Exception as erreur:  # échec au démarrage
        print(f"  ECHEC {libelle} : {type(erreur).__name__} — {erreur}")
        ECHECS.append(libelle)
        return
    if application.exception:
        for exception in application.exception:
            print(f"  ECHEC {libelle} : {exception.value}")
            ECHECS.append(f"{libelle} : {exception.value}")
        return
    print(f"  ok   {libelle}")


def main() -> int:
    print("=== Préparation des données de démonstration ===")
    db.init_db()
    resume = seed.charger_donnees_demo(remplacer=True)
    print(f"  {resume['factures']} factures, {resume['reglements']} règlements")

    print("\n=== Exécution des pages ===")
    for identifiant, libelle in PAGES:
        os.environ["IMPAYES_PAGE"] = identifiant
        executer("tests/runner_page.py", libelle)

    print("\n=== Point d'entrée complet (barre latérale + navigation) ===")
    os.environ.pop("IMPAYES_PAGE", None)
    executer("app_modulaire.py", "app_modulaire.py (page par défaut)")
    executer("app_modulaire.py", "app_modulaire.py (deuxième exécution, données en cache)")

    print("\n=== Résultat ===")
    if ECHECS:
        print(f"{len(ECHECS)} écran(s) en échec :")
        for echec in ECHECS:
            print(f"  - {echec}")
        return 1
    print("Tous les écrans s'exécutent sans erreur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
