"""🤖 Assistant IA — briefing, conversation en langage naturel, simulateur."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from .. import ai, cashflow, config, db, messages, prediction, reporting, service
from . import common

QUESTIONS_SUGGEREES = [
    "Quelles factures dois-je traiter ce matin ?",
    "Quel client me doit le plus ?",
    "Combien vais-je encaisser d'ici la fin du mois ?",
    "Quels dossiers risquent de ne pas être payés ?",
    "Prépare un échéancier pour le premier client de la liste.",
]


# ---------------------------------------------------------------------------
# Assistant local (fonctionne sans clé API)
# ---------------------------------------------------------------------------
def repondre_local(question: str, portefeuille: pd.DataFrame, params: dict) -> str:
    """Réponse calculée localement : l'assistant reste utile sans IA."""
    params = params or db.lire_params()
    devise = params.get("devise", "MAD")
    actif = service.actifs(portefeuille)
    retard = service.en_retard(portefeuille)
    stats = service.synthese(portefeuille, params)
    texte = (question or "").lower()

    def argent(valeur: float) -> str:
        return messages.formater_montant(valeur, devise)

    if retard.empty:
        return "Aucune facture en retard : il n'y a rien à relancer aujourd'hui."

    if any(mot in texte for mot in ("ce matin", "aujourd'hui", "traiter", "priorit", "commencer")):
        plan = service.plan_du_jour(portefeuille, limite=6)
        lignes = [
            f"{position}. **{ligne['client']}** — {ligne['numero']} — {argent(ligne['montant'])} "
            f"({int(ligne['jours_retard'])} j) → {ligne['action_prevue']} · score {int(ligne['score'])}"
            for position, (_, ligne) in enumerate(plan.iterrows(), start=1)
        ]
        return (
            f"**{len(retard)} facture(s) en retard** pour {argent(stats['montant_retard'])}. "
            "Ordre de traitement conseillé :\n\n" + "\n".join(lignes)
        )

    if any(mot in texte for mot in ("me doit le plus", "plus gros", "plus important", "gros montant")):
        par_client = actif.groupby("client")["montant"].sum().sort_values(ascending=False)
        lignes = [
            f"{position}. {client} — {argent(montant)}"
            for position, (client, montant) in enumerate(par_client.head(5).items(), start=1)
        ]
        return "**Clients qui vous doivent le plus :**\n\n" + "\n".join(lignes)

    if any(mot in texte for mot in ("encaisser", "trésorerie", "tresorerie", "fin du mois", "cash")):
        simulation = cashflow.simuler(actif.to_dict("records"), params)
        tableau = simulation["par_horizon"]
        lignes = [
            f"- Sous {int(ligne['horizon'])} jours : **{argent(ligne['realiste'])}** "
            f"(prudent {argent(ligne['prudent'])} · optimiste {argent(ligne['optimiste'])})"
            for _, ligne in tableau.iterrows()
        ]
        return (
            f"Sur {argent(stats['total_impaye'])} impayés, voici ce que vous pouvez espérer encaisser :\n\n"
            + "\n".join(lignes)
            + f"\n\nSans aucune relance, l'encaissement à 30 jours tomberait à "
            f"**{argent(tableau.iloc[0]['sans_relance'] if not tableau.empty else 0)}**."
        )

    if any(mot in texte for mot in ("risque", "ne pas être payé", "ne sera pas payé", "contentieux", "perte")):
        risques = actif[(actif["profil"].isin(["risque", "recidiviste"])) & (actif["p30"] < 0.45)]
        if risques.empty:
            risques = actif.nsmallest(5, "p30")
        lignes = [
            f"- **{ligne['client']}** ({ligne['numero']}) — {argent(ligne['montant'])} — "
            f"paiement à 30 j estimé à {common.pourcentage(ligne['p30'])} · profil {ligne['profil_nom']}"
            for _, ligne in risques.head(6).iterrows()
        ]
        return (
            "**Dossiers les plus exposés :**\n\n" + "\n".join(lignes)
            + "\n\nConseil : escaladez d'un niveau, obtenez un engagement écrit et conservez le journal PDF des relances."
        )

    if "échéancier" in texte or "echelonner" in texte or "echeancier" in texte:
        cible = None
        for _, ligne in retard.head(12).iterrows():
            if str(ligne["client"]).lower() in texte:
                cible = ligne
                break
        if cible is None:
            cible = retard.sort_values("score", ascending=False).iloc[0]
        moitie = float(cible["montant"]) / 2
        date_1 = date.today() + timedelta(days=10)
        date_2 = date.today() + timedelta(days=40)
        return (
            f"**Proposition d'échéancier — {cible['client']} ({cible['numero']})**\n\n"
            f"Bonjour {cible['client']},\n\n"
            f"Afin de régulariser la facture {cible['numero']} d'un montant de "
            f"{argent(cible['montant'])}, nous vous proposons deux versements :\n\n"
            f"- {argent(moitie)} le {date_1.strftime('%d/%m/%Y')} ;\n"
            f"- {argent(moitie)} le {date_2.strftime('%d/%m/%Y')}.\n\n"
            "Merci de nous confirmer votre accord par retour de message. "
            "Dès réception du premier versement, nous poursuivrons le suivi de la facture en toute confiance.\n\n"
            "(Aucun intérêt de retard ne sera appliqué si l'échéancier est respecté.)"
        )

    if any(mot in texte for mot in ("combien de factures", "retard moyen", "synthèse", "synthese", "bilan")):
        return (
            f"**Synthèse au {stats['date']}**\n\n"
            f"- {stats['nb_factures']} facture(s) en cours pour {argent(stats['total_impaye'])}\n"
            f"- {stats['nb_retard']} en retard, pour {argent(stats['montant_retard'])}\n"
            f"- Retard moyen : {stats['retard_moyen']:.1f} jours · score moyen : {stats['score_moyen']:.0f}/100\n"
            f"- Encaissement attendu à 30 jours : {argent(stats['encaissement_30j'])}"
        )

    # Réponse par défaut : résumé + mode d'emploi
    return (
        "Je peux répondre sans IA configurée sur : *les factures à traiter aujourd'hui*, "
        "*qui vous doit le plus*, *combien vous allez encaisser*, *les dossiers à risque* "
        "et *les échéanciers*.\n\n"
        f"En résumé : {stats['nb_retard']} facture(s) en retard pour {argent(stats['montant_retard'])}, "
        f"retard moyen de {stats['retard_moyen']:.0f} jours. "
        "Posez votre question autrement, ou activez l'IA dans ⚙️ Réglages pour des réponses libres."
    )


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------
def _conversation(portefeuille: pd.DataFrame, params: dict) -> None:
    st.markdown("#### Poser une question sur votre portefeuille")
    actif = service.actifs(portefeuille)
    contexte = reporting.contexte_assistant(
        actif.to_dict("records"), params, service.synthese(portefeuille, params)
    )
    ia_active = ai.disponible(params)
    if not ia_active:
        st.caption(
            "IA non configurée : l'assistant répond par calcul local sur les questions de recouvrement courantes. "
            "Ajoutez une clé API dans ⚙️ Réglages pour des réponses entièrement libres."
        )

    colonnes = st.columns(len(QUESTIONS_SUGGEREES))
    for position, (colonne, question) in enumerate(zip(colonnes, QUESTIONS_SUGGEREES)):
        with colonne:
            if st.button(question, key=f"question_suggeree_{position}", width="stretch"):
                st.session_state.setdefault("conversation", []).append({"role": "user", "contenu": question})
                _repondre(question, contexte, portefeuille, params, ia_active)

    historique = st.session_state.get("conversation", [])
    for message in historique:
        with st.chat_message("user" if message["role"] == "user" else "assistant"):
            st.markdown(message["contenu"])
            if message.get("source"):
                st.caption(message["source"])

    question = st.chat_input("Ex. Combien vais-je encaisser d'ici la fin du mois ?")
    if question:
        st.session_state.setdefault("conversation", []).append({"role": "user", "contenu": question})
        _repondre(question, contexte, portefeuille, params, ia_active)

    if historique and st.button("🗑️ Effacer la conversation"):
        st.session_state["conversation"] = []
        st.rerun()


def _repondre(question: str, contexte: dict, portefeuille: pd.DataFrame, params: dict, ia_active: bool) -> None:
    """Ajoute la réponse à la conversation : IA si possible, calcul local sinon."""
    reponse = None
    source = None
    if ia_active:
        historique = [
            {"role": m["role"] if m["role"] == "user" else "assistant", "content": m["contenu"]}
            for m in st.session_state.get("conversation", [])[:-1]
        ]
        reponse = ai.assistant_conversation(question, contexte, params, historique)
        source = "Réponse de l'IA d'après vos données."
    if not reponse:
        reponse = repondre_local(question, portefeuille, params)
        source = "Calcul local (IA indisponible ou en échec)."
    st.session_state["conversation"].append({"role": "assistant", "contenu": reponse, "source": source})
    st.rerun()


# ---------------------------------------------------------------------------
# Prévisions détaillées
# ---------------------------------------------------------------------------
def _previsions(portefeuille: pd.DataFrame, params: dict) -> None:
    devise = params.get("devise", "MAD")
    actif = service.actifs(portefeuille)
    if actif.empty:
        st.info("Aucune facture en cours.")
        return
    tableau = actif[
        ["numero", "client", "montant", "jours_retard", "niveau_nom", "p7", "p15", "p30", "date_probable", "profil_nom", "prediction_source"]
    ].copy()
    for colonne in ("p7", "p15", "p30"):
        tableau[colonne] = (tableau[colonne] * 100).round(0)
    tableau = tableau.rename(
        columns={
            "numero": "N° facture",
            "client": "Client",
            "montant": f"Montant ({devise})",
            "jours_retard": "Retard (j)",
            "niveau_nom": "Niveau",
            "p7": "7 j (%)",
            "p15": "15 j (%)",
            "p30": "30 j (%)",
            "date_probable": "Paiement probable",
            "profil_nom": "Profil",
            "prediction_source": "Méthode",
        }
    )
    tableau["Méthode"] = tableau["Méthode"].map(
        {"modele": "modèle appris", "heuristique": "estimation par défaut"}
    )
    st.dataframe(
        tableau,
        width="stretch",
        hide_index=True,
        column_config={
            "7 j (%)": st.column_config.ProgressColumn("7 j (%)", min_value=0, max_value=100, format="%d"),
            "15 j (%)": st.column_config.ProgressColumn("15 j (%)", min_value=0, max_value=100, format="%d"),
            "30 j (%)": st.column_config.ProgressColumn("30 j (%)", min_value=0, max_value=100, format="%d"),
            f"Montant ({devise})": st.column_config.NumberColumn(format="%.2f"),
            "Paiement probable": st.column_config.DateColumn(format="DD/MM/YYYY"),
        },
    )
    nombre_reglements = db.compter_reglements()
    paquet = prediction.modeles(db.lister_reglements())
    if paquet.get("source") == "modele":
        qualite = paquet.get("auc")
        st.caption(
            f"Modèle entraîné sur {nombre_reglements} règlements passés"
            + (f" — qualité (AUC en validation croisée) : {qualite:.2f}" if qualite else "")
            + ". Au-delà de 0,75, le modèle distingue correctement les clients qui paient de ceux qui ne paient pas."
        )
    else:
        st.caption(
            f"Historique insuffisant ({nombre_reglements} règlement(s) enregistré(s)) : il en faut au moins "
            "40, avec au moins 8 exemples de chaque catégorie. Les probabilités affichées proviennent donc "
            "de la formule par défaut. En marquant les factures « payée » au fil des mois, le modèle "
            "s'active automatiquement, sans réglage."
        )


def _simulateur(portefeuille: pd.DataFrame, params: dict) -> None:
    devise = params.get("devise", "MAD")
    actif = service.actifs(portefeuille)
    if actif.empty:
        st.info("Aucune facture en cours à projeter.")
        return
    colonnes = st.columns([1.2, 1.2, 2])
    with colonnes[0]:
        avec_relance = st.toggle(
            "Intégrer l'effet des relances", value=True,
            help="Compare l'encaissement attendu avec et sans action de recouvrement.",
        )
    with colonnes[1]:
        st.metric("Relances enregistrées", int(actif["nb_actions"].sum()))
    with colonnes[2]:
        st.caption(
            "Les projections reposent sur les probabilités de paiement de chaque facture, "
            "recalculées à chaque modification du portefeuille."
        )
    simulation = cashflow.simuler(actif.to_dict("records"), params, avec_relance=avec_relance)
    st.plotly_chart(common.graphique_projection(actif.to_dict("records"), params), width="stretch")
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
    detail = simulation["lignes"]
    if not detail.empty:
        with st.expander("Détail par facture (probabilités et montants attendus à 30 jours)"):
            affichage = detail[
                ["facture", "client", "montant", "p30", "attendu_30", "date_probable", "profil"]
            ].copy()
            affichage["p30"] = (affichage["p30"] * 100).round(0)
            st.dataframe(
                affichage.rename(
                    columns={
                        "facture": "N° facture",
                        "client": "Client",
                        "montant": f"Montant ({devise})",
                        "p30": "Paiement 30 j (%)",
                        "attendu_30": f"Attendu 30 j ({devise})",
                        "date_probable": "Date probable",
                        "profil": "Profil",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "⬇️ Exporter la projection (CSV)",
                data=reporting.csv_bytes(affichage),
                file_name=f"projection_tresorerie_{date.today().isoformat()}.csv",
                mime="text/csv",
            )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def afficher() -> None:
    params = common.lire_params()
    portefeuille = common.portefeuille(params)
    stats = service.synthese(portefeuille, params)

    common.entete(
        "🤖 Assistant IA",
        "Posez vos questions en français : l'assistant lit votre portefeuille et répond avec vos chiffres.",
        params,
    )

    st.markdown("#### Briefing du jour")
    colonnes = st.columns([3, 1])
    with colonnes[1]:
        if ai.disponible(params):
            if st.button("Générer par IA", type="primary", width="stretch"):
                with st.spinner("Rédaction…"):
                    st.session_state["briefing_asst"] = ai.briefing_quotidien(
                        {
                            "date": stats["date"],
                            "total_impaye": f"{stats['total_impaye']:,.0f}".replace(",", " "),
                            "nb_retard": stats["nb_retard"],
                            "nb_nouveaux": stats["nb_nouveaux"],
                            "retard_moyen": f"{stats['retard_moyen']:.1f}",
                            "repartition": {
                                config.niveau(code)["nom"]: nombre for code, nombre in stats["repartition"].items()
                            },
                            "changements": stats["changements"],
                            "top": stats["top"],
                            "encaissement_30j": f"{stats['encaissement_30j']:,.0f}".replace(",", " "),
                            "risques": stats["risques"],
                        },
                        params,
                    )
        else:
            st.caption("L'IA n'est pas configurée : briefing calculé localement.")
    with colonnes[0]:
        texte_briefing = st.session_state.get("briefing_asst")
        if texte_briefing:
            st.markdown(texte_briefing)
        else:
            st.markdown(repondre_local("fais-moi la synthèse", portefeuille, params))
            if stats["changements"]:
                st.caption(
                    f"{len(stats['changements'])} facture(s) changent de niveau aujourd'hui — "
                    "voir le tableau de bord pour le détail."
                )

    st.divider()
    onglets = st.tabs(["💬 Conversation", "🔮 Prévisions de paiement", "💰 Simulateur de trésorerie"])
    with onglets[0]:
        _conversation(portefeuille, params)
    with onglets[1]:
        _previsions(portefeuille, params)
    with onglets[2]:
        _simulateur(portefeuille, params)
