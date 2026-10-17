"""Scoring des Impayés — point d'entrée de l'application Streamlit.

    streamlit run app.py

Cinq pages : Tableau de bord · Factures · Fiche & message · Assistant IA ·
Réglages & historique. Les données sont stockées localement (SQLite) et
l'intelligence artificielle est facultative : sans clé API, l'application
fonctionne intégralement grâce à ses modèles intégrés.
"""
from __future__ import annotations

import streamlit as st

from impayes import __version__, ai, config, db, service
from impayes.ui import (
    common,
    page_assistant,
    page_dashboard,
    page_factures,
    page_fiche,
    page_reglages,
)

st.set_page_config(
    page_title=config.APP_TITRE,
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Initialisation ---------------------------------------------------------
db.init_db()
params = common.lire_params()
common.appliquer_theme(params)

# --- Déclaration des pages --------------------------------------------------
REFERENCES = {
    "dashboard": st.Page(
        page_dashboard.afficher,
        title="Tableau de bord",
        icon="🏠",
        url_path="tableau-de-bord",
        default=True,
    ),
    "factures": st.Page(
        page_factures.afficher, title="Factures", icon="📋", url_path="factures"
    ),
    "fiche": st.Page(
        page_fiche.afficher, title="Fiche & message", icon="📨", url_path="fiche"
    ),
    "assistant": st.Page(
        page_assistant.afficher, title="Assistant IA", icon="🤖", url_path="assistant"
    ),
    "reglages": st.Page(
        page_reglages.afficher, title="Réglages & historique", icon="⚙️", url_path="reglages"
    ),
}
# Exposé aux pages pour permettre la navigation programmatique (« Ouvrir la fiche »).
st.session_state["_pages_"] = REFERENCES

navigation = st.navigation(list(REFERENCES.values()), position="sidebar")


# --- Barre latérale commune -------------------------------------------------
def _barre_laterale() -> None:
    params = common.lire_params()
    devise = params.get("devise", "MAD")
    with st.sidebar:
        st.markdown(
            f"<div style='font-size:1.06rem;font-weight:800'>💰 {config.APP_TITRE}</div>"
            f"<div class='petit'>{params.get('societe', 'Ma Société')}</div>",
            unsafe_allow_html=True,
        )
        st.divider()

        portefeuille = common.portefeuille(params)
        if portefeuille.empty:
            st.caption("Aucune facture enregistrée.")
            if st.button("📥 Charger le jeu de démonstration", width="stretch"):
                from impayes import seed

                seed.charger_donnees_demo(remplacer=True)
                common.recharger()
        else:
            actif = service.actifs(portefeuille)
            retard = service.en_retard(portefeuille)
            total = float(actif["montant"].sum()) if not actif.empty else 0.0
            st.markdown(
                f"<div class='petit'>Montant impayé</div>"
                f"<div style='font-size:1.15rem;font-weight:700'>"
                f"{common.montant(total, params)}</div>"
                f"<div class='petit'>{len(retard)} facture(s) en retard · "
                f"retard moyen {retard['jours_retard'].mean() if not retard.empty else 0:.0f} j</div>",
                unsafe_allow_html=True,
            )
            if not retard.empty:
                premiere = retard.iloc[0]
                st.divider()
                st.markdown(
                    f"<div class='petit'>Priorité n° 1</div>"
                    f"<div style='font-weight:700'>{premiere['client']}</div>"
                    f"<div class='petit'>{premiere['numero']} — "
                    f"{common.montant(premiere['montant'], params)} — "
                    f"score {int(premiere['score'])}</div>",
                    unsafe_allow_html=True,
                )
                if st.button("📨 Ouvrir la fiche", width="stretch", type="primary"):
                    common.ouvrir_fiche(int(premiere["id"]), REFERENCES["fiche"])

        st.divider()
        etat = ai.etat(params)
        icone = {"success": "🤖", "warning": "⚠️", "info": "ℹ️"}.get(etat["niveau"], "ℹ️")
        st.caption(f"{icone} {etat['raison']}")
        st.caption(
            "Données stockées localement. Aucun message n'est envoyé automatiquement : "
            "vous relisez, vous copiez, vous envoyez."
        )
        st.caption(f"Version {__version__} · {devise}")


_barre_laterale()
navigation.run()
