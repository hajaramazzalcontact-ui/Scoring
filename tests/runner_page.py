"""Lanceur d'une seule page — utilisé par :mod:`tests.ui_test`.

Le nom de la page est lu dans la variable d'environnement ``IMPAYES_PAGE``.
Ce fichier existe parce que le lanceur d'application de Streamlit
(``AppTest.from_function``) recopie le code d'une fonction sans ses imports :
passer par un vrai script garantit que les modules sont chargés normalement.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from impayes.ui import (  # noqa: E402
    page_assistant,
    page_dashboard,
    page_factures,
    page_fiche,
    page_reglages,
)

PAGES = {
    "dashboard": page_dashboard.afficher,
    "factures": page_factures.afficher,
    "fiche": page_fiche.afficher,
    "assistant": page_assistant.afficher,
    "reglages": page_reglages.afficher,
}

PAGES[os.environ.get("IMPAYES_PAGE", "dashboard")]()
