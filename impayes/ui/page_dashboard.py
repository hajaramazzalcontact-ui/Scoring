"""🏠 Tableau de bord — « que fais-je aujourd'hui ? » en dix secondes."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import ai, config, db, messages, service
from . import common


def _briefing_local(synthese: dict, params: dict) -> str:
    """Briefing de repli, écrit à partir des chiffres du jour."""
    devise = params.get("devise", "MAD")
    repartition = synthese["repartition"]
    lignes = [
        f"**{synthese['nb_retard']} facture(s) en retard** aujourd'hui, pour "
        f"{messages.formater_montant(synthese['montant_retard'], devise)} — retard moyen de "
        f"{synthese['retard_moyen']:.0f} jours.",
    ]
    if synthese["nb_nouveaux"]:
        lignes.append(
            f"• {synthese['nb_nouveaux']} facture(s) viennent de basculer en retard : c'est là que le "
            "recouvrement coûte le moins cher."
        )
    if synthese["changements"]:
        detail = ", ".join(
            f"{c['client']} ({c['numero']}) → {c['niveau']}" for c in synthese["changements"][:4]
        )
        lignes.append(f"• Changements de niveau du jour : {detail}.")
    if synthese["risques"]:
        lignes.append(
            f"• À surveiller : {synthese['risques'][0]['client']} "
            f"({messages.formater_montant(synthese['risques'][0]['montant'], devise)}, profil "
            f"{synthese['risques'][0]['profil']})."
        )
    lignes.append(
        f"• Encaissement attendu sous 30 jours : "
        f"{messages.formater_montant(synthese['encaissement_30j'], devise)}."
    )
    if synthese["top"]:
        premier = synthese["top"][0]
        lignes.append(
            f"**Priorité n° 1 : {premier['client']} — facture {premier['numero']} "
            f"({messages.formater_montant(premier['montant'], devise)}, score {premier['score']}).**"
        )
    if repartition.get("contentieux"):
        lignes.append(
            f"• {repartition['contentieux']} dossier(s) au niveau contentieux : préparez les preuves."
        )
    return "\n\n".join(lignes)


def afficher() -> None:
    params = common.lire_params()
    portefeuille = common.portefeuille(params)
    actif = service.actifs(portefeuille)
    retard = service.en_retard(portefeuille)
    stats = service.synthese(portefeuille, params)
    devise = params.get("devise", "MAD")

    common.entete(
        "🏠 Tableau de bord",
        "Ce que l'application recommande de faire aujourd'hui, dans l'ordre.",
        params,
        extra=(
            f'<p>Montant impayé : <b>{messages.formater_montant(stats["total_impaye"], devise)}</b> · '
            f'{stats["nb_retard"]} facture(s) en retard sur {stats["nb_factures"]} en cours · '
            f'retard moyen {stats["retard_moyen"]:.0f} jours</p>'
        ),
    )

    if actif.empty:
        st.info(
            "Aucune facture enregistrée. Rendez-vous sur **📋 Factures** pour en saisir, "
            "importer un fichier Excel/CSV, ou charger le jeu de démonstration."
        )
        return

    # ------------------------------------------------------------- Indicateurs
    colonnes = st.columns(4)
    with colonnes[0]:
        common.carte_synthese(
            "Montant total impayé",
            messages.formater_montant(stats["total_impaye"], devise),
            "Somme des factures non réglées, échues ou non.",
        )
    with colonnes[1]:
        common.carte_synthese(
            "Factures en retard",
            f"{stats['nb_retard']}",
            f"Sur {stats['nb_factures']} factures en cours.",
            delta=f"+{stats['nb_nouveaux']} aujourd'hui" if stats["nb_nouveaux"] else None,
        )
    with colonnes[2]:
        common.carte_synthese(
            "Retard moyen",
            f"{stats['retard_moyen']:.1f} jours",
            "Moyenne pondérée par facture, pas par montant.",
        )
    with colonnes[3]:
        common.carte_synthese(
            "Encaissement prévu (30 j)",
            messages.formater_montant(stats["encaissement_30j"], devise),
            "Probabilités de paiement estimées, relances comprises. Scénario réaliste.",
        )

    st.divider()

    # ------------------------------------------------------- Entonnoir cliquable
    st.subheader("Entonnoir des niveaux — cliquez pour filtrer")
    selection = common.cartes_niveaux(retard, params, cle_prefixe="dash")
    if selection:
        st.session_state["filtre_niveaux"] = [selection]
        st.session_state["retour_dashboard"] = selection

    filtre_actif = st.session_state.get("retour_dashboard")
    if filtre_actif:
        definition = config.niveau(filtre_actif)
        sous_ensemble = retard[retard["niveau"] == filtre_actif]
        st.markdown(
            f"**Filtre actif :** {definition['icone']} {definition['nom']} — "
            f"{len(sous_ensemble)} facture(s) pour "
            f"{messages.formater_montant(sous_ensemble['montant'].sum(), devise)}."
        )
        if st.button("Réinitialiser le filtre", key="reset_dash"):
            st.session_state.pop("retour_dashboard", None)
            st.session_state.pop("filtre_niveaux", None)
            st.rerun()
        with st.container(border=True):
            for _, ligne in sous_ensemble.head(8).iterrows():
                _ligne_urgence(ligne, params)

    gauche, droite = st.columns([1, 1])
    with gauche:
        st.plotly_chart(common.graphique_entonnoir(retard, params), width="stretch")
    with droite:
        st.plotly_chart(common.graphique_repartition(retard, params), width="stretch")

    # ------------------------------------------------------------ Top des urgences
    st.divider()
    st.subheader("🔥 Les 5 urgences du jour")
    st.caption(
        "Classement par score : durée du retard, montant, historique du client et risque de non-paiement."
    )
    urgences = service.plan_du_jour(portefeuille, limite=5)
    if urgences.empty:
        st.success("Aucune facture en retard : rien à relancer aujourd'hui.")
    else:
        for _, ligne in urgences.iterrows():
            _ligne_urgence(ligne, params)

    # ---------------------------------------------------------------- Évolution
    st.divider()
    gauche, droite = st.columns([1.15, 1])
    with gauche:
        st.plotly_chart(common.graphique_aging(retard, params), width="stretch")
    with droite:
        st.plotly_chart(common.graphique_profils(retard, params), width="stretch")

    st.divider()
    with st.expander("💰 Simulateur de trésorerie — encaissements attendus", expanded=False):
        st.plotly_chart(
            common.graphique_projection(actif.to_dict("records"), params), width="stretch"
        )
        simulation = service.cashflow.simuler(actif.to_dict("records"), params)
        st.dataframe(
            simulation["par_horizon"].rename(
                columns={
                    "horizon": "Horizon (jours)",
                    "sans_relance": f"Sans relance ({devise})",
                    "prudent": f"Prudent ({devise})",
                    "realiste": f"Réaliste ({devise})",
                    "optimiste": f"Optimiste ({devise})",
                }
            ),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Scénario prudent : seuls 55 % des paiements attendus sont retenus. "
            "Optimiste : 125 %, plafonné au montant total impayé."
        )

    # ---------------------------------------------------------------- Briefing
    st.divider()
    st.subheader("🗞️ Briefing du jour")
    if ai.disponible(params):
        if st.button("Générer le briefing par IA", type="primary", key="briefing_ia"):
            with st.spinner("Rédaction du briefing…"):
                texte = ai.briefing_quotidien(
                    {
                        "date": stats["date"],
                        "total_impaye": f"{stats['total_impaye']:,.0f}".replace(",", " "),
                        "nb_retard": stats["nb_retard"],
                        "nb_nouveaux": stats["nb_nouveaux"],
                        "retard_moyen": f"{stats['retard_moyen']:.1f}",
                        "repartition": {
                            config.niveau(code)["nom"]: nombre
                            for code, nombre in stats["repartition"].items()
                        },
                        "changements": stats["changements"],
                        "top": stats["top"],
                        "encaissement_30j": f"{stats['encaissement_30j']:,.0f}".replace(",", " "),
                        "risques": stats["risques"],
                    },
                    params,
                )
            st.session_state["briefing_texte"] = texte or _briefing_local(stats, params)
            st.session_state["briefing_source"] = "ia" if texte else "local"
        if st.session_state.get("briefing_texte"):
            source = st.session_state.get("briefing_source")
            st.caption("Rédigé par l'IA." if source == "ia" else "IA indisponible : synthèse locale.")
            st.markdown(st.session_state["briefing_texte"])
        else:
            st.caption("Cliquez sur le bouton pour laisser l'IA rédiger le briefing, ou lisez la synthèse locale ci-dessous.")
            st.markdown(_briefing_local(stats, params))
    else:
        st.caption(
            "Synthèse locale — activez l'IA dans ⚙️ Réglages pour un briefing rédigé automatiquement."
        )
        st.markdown(_briefing_local(stats, params))

    # ------------------------------------------------------ Changements de niveau
    if stats["changements"]:
        with st.expander(
            f"🔔 {len(stats['changements'])} facture(s) changent de niveau aujourd'hui", expanded=True
        ):
            for changement in stats["changements"]:
                st.markdown(
                    f"- **{changement['client']}** — facture {changement['numero']} → "
                    f"niveau *{changement['niveau']}* : {changement['action']}"
                )


def _ligne_urgence(ligne: pd.Series, params: dict) -> None:
    """Une ligne de la liste prioritaire, avec accès direct à la fiche."""
    couleur = ligne.get("couleur") or common.couleur_score(ligne["score"])
    colonnes = st.columns([0.42, 0.16, 0.16, 0.14, 0.12])
    with colonnes[0]:
        st.markdown(
            f'<div style="border-left:5px solid {couleur};padding-left:10px">'
            f'<b>{ligne["client"]}</b><br>'
            f'<span class="petit">{ligne["numero"]} — échéance {common.date_courte(ligne["echeance"])} '
            f'— {int(ligne["jours_retard"])} j de retard</span></div>',
            unsafe_allow_html=True,
        )
    with colonnes[1]:
        st.markdown(
            f'<div class="mono"><b>{messages.formater_montant(ligne["montant"], params.get("devise", "MAD"))}</b>'
            f'<br><span class="petit">score {int(ligne["score"])}/100</span></div>',
            unsafe_allow_html=True,
        )
    with colonnes[2]:
        st.markdown(
            f'<div>{common.badge(ligne["niveau"])}<br>'
            f'<span class="petit">{ligne["action_prevue"]}</span></div>',
            unsafe_allow_html=True,
        )
    with colonnes[3]:
        st.markdown(
            f'<span class="petit">{ligne["profil_icone"]} {ligne["profil_nom"]}<br>'
            f'{common.pourcentage(ligne["p30"])} sous 30 j</span>',
            unsafe_allow_html=True,
        )
    with colonnes[4]:
        if st.button("Ouvrir →", key=f"ouvrir_{ligne['id']}", width="stretch"):
            common.ouvrir_fiche(int(ligne["id"]))
    st.markdown('<hr class="sep">', unsafe_allow_html=True)
