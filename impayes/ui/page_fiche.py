"""📨 Fiche & message — le dossier d'une facture et le message prêt à envoyer."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from .. import ai, config, db, messages, reporting, scoring, service
from . import common


def _choisir_facture(portefeuille: pd.DataFrame, params: dict) -> pd.Series | None:
    if portefeuille.empty:
        st.info("Aucune facture enregistrée. Commencez par la page 📋 Factures.")
        return None

    actif = service.actifs(portefeuille)
    liste = actif if not actif.empty else portefeuille
    options = liste["id"].tolist()
    identifiant = st.session_state.get("facture_id")
    if identifiant not in options:
        identifiant = options[0]
        st.session_state["facture_id"] = int(identifiant)

    colonnes = st.columns([3, 1])
    with colonnes[0]:
        choix = st.selectbox(
            "Facture à traiter",
            options=options,
            index=options.index(identifiant),
            format_func=lambda i: _libelle_option(liste, i),
            key="selecteur_facture",
        )
    with colonnes[1]:
        st.caption("La liste suit l'ordre du score.")
        if actif.empty:
            st.warning("Toutes les factures sont réglées.")
    st.session_state["facture_id"] = int(choix)
    ligne = portefeuille[portefeuille["id"] == choix]
    return ligne.iloc[0] if not ligne.empty else None


def _libelle_option(liste: pd.DataFrame, identifiant) -> str:
    ligne = liste[liste["id"] == identifiant]
    if ligne.empty:
        return str(identifiant)
    ligne = ligne.iloc[0]
    return (
        f"[{int(ligne['score'])}] {ligne['client']} — {ligne['numero']} — "
        f"{ligne['montant']:,.0f}".replace(",", " ")
        + f" — {ligne['niveau_nom']} ({int(ligne['jours_retard'])} j)"
    )


# ---------------------------------------------------------------------------
# Bloc d'identification
# ---------------------------------------------------------------------------
def _en_tete(facture: pd.Series, params: dict) -> None:
    devise = params.get("devise", "MAD")
    gauche, milieu, droite = st.columns([2.1, 1.1, 1])
    with gauche:
        st.markdown(
            f"### {facture['client']}\n"
            f"Facture **{facture['numero']}** — "
            f"**{messages.formater_montant(facture['montant'], devise)}**"
        )
        st.markdown(
            f"{common.badge(facture['niveau'])}&nbsp; {common.badge_priorite(facture['score'])}&nbsp; "
            f"{facture['profil_icone']} **{facture['profil_nom']}**",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Échéance {common.date_courte(facture['echeance'])} · "
            f"{int(facture['jours_retard'])} jours de retard · "
            f"statut : {facture['statut_libelle']}"
            + (f" · payée le {common.date_courte(facture['date_paiement'])}" if facture.get("date_paiement") else "")
        )
    with milieu:
        st.plotly_chart(
            common.jauge_score(facture["score"], hauteur=200), width="stretch"
        )
    with droite:
        st.metric("Action attendue", facture["action_prevue"])
        st.caption(f"Ton recommandé : {config.niveau(facture['niveau'])['ton']}")
        st.markdown(common.compte_a_rebond(facture), unsafe_allow_html=True)
        labels = {"telephone": "☎️", "email": "✉️"}
        coordonnees = " · ".join(
            f"{labels[champ]} {facture[champ]}" for champ in ("telephone", "email") if facture.get(champ)
        )
        st.caption(coordonnees or "⚠️ Aucune coordonnée enregistrée")


def _frise(facture: pd.Series, params: dict) -> None:
    st.markdown("#### Parcours de la facture")
    st.markdown(common.frise_html(facture, params), unsafe_allow_html=True)
    st.caption(
        "✅ relance effectuée · ⏳ étape franchie sans relance enregistrée · 👉 étape du jour · ⬜ à venir"
    )


# ---------------------------------------------------------------------------
# Analyse
# ---------------------------------------------------------------------------
def _prediction(facture: pd.Series, params: dict) -> None:
    devise = params.get("devise", "MAD")
    st.markdown("#### Ce que l'IA anticipe")
    colonnes = st.columns(4)
    with colonnes[0]:
        st.metric("Paiement sous 7 j", common.pourcentage(facture["p7"]))
    with colonnes[1]:
        st.metric("Sous 15 j", common.pourcentage(facture["p15"]))
    with colonnes[2]:
        st.metric("Sous 30 j", common.pourcentage(facture["p30"]))
    with colonnes[3]:
        probable = facture.get("date_probable")
        st.metric(
            "Date probable",
            common.date_courte(probable) if probable else "—",
            help="Médiane du délai de paiement restant, estimée à partir de l'historique du client.",
        )
    source = (
        "modèle entraîné sur l'historique des règlements"
        if facture.get("prediction_source") == "modele"
        else "estimation par défaut (historique encore trop mince)"
    )
    st.caption(f"Estimation : {source}.")
    st.markdown(
        f"**Profil du client — {facture['profil_icone']} {facture['profil_nom']}.** "
        f"{facture['profil_resume']} *Conseil : {facture['profil_conseil']}*"
    )
    statistiques = facture.get("stats_client") or {}
    if statistiques.get("nb_reglements"):
        st.caption(
            f"Historique : {int(statistiques['nb_reglements'])} facture(s) réglée(s), retard moyen de "
            f"{statistiques['retard_moyen']:.0f} jours, {common.pourcentage(statistiques['taux_retard'])} payées en retard, "
            f"retard maximum {int(statistiques['retard_max'])} jours."
        )


def _score(facture: pd.Series, params: dict) -> None:
    st.markdown("#### Pourquoi ce score ?")
    st.markdown(facture["explication_score"])
    st.plotly_chart(common.graphique_composantes(facture.to_dict(), params), width="stretch")
    st.caption(
        "Critère dominant : **" + str(facture["critere_dominant"]) + "**. "
        "Les pondérations se règlent dans ⚙️ Réglages."
    )


def _recommandation(facture: pd.Series, params: dict, portefeuille: pd.DataFrame) -> None:
    st.markdown("#### Meilleure action suivante")
    cle = f"reco_{facture['id']}"
    with_ia = ai.disponible(params)
    if with_ia:
        bouton = st.button("🤖 Demander une recommandation à l'IA", key=f"btn_{cle}")
        if bouton:
            with st.spinner("Analyse du dossier…"):
                st.session_state[cle] = service.recommandation(
                    facture.to_dict(), params, portefeuille, avec_ia=True
                )
    recommandation = st.session_state.get(cle) or service.recommandation_locale(
        facture.to_dict(), params
    )
    st.info(f"**{recommandation['action']}**\n\n{recommandation.get('raison', '')}")
    if recommandation.get("alternative"):
        st.caption(f"Repli proposé : {recommandation['alternative']}")
    st.caption(
        "Recommandation rédigée par l'IA d'après l'historique du client."
        if recommandation.get("source") == "ia"
        else "Recommandation calculée localement à partir du profil et des probabilités."
    )


def _alertes(facture: pd.Series, params: dict, portefeuille: pd.DataFrame) -> None:
    enrichie = facture.to_dict()
    enrichie["jour_retard_egal_seuil"] = bool(
        facture["statut"] != "payee" and int(facture["jours_retard"]) == config.seuils(params)[facture["niveau"]]
    )
    alertes = service.construire_alertes(enrichie, params, portefeuille)
    for alerte in alertes:
        if alerte["niveau"] == "grave":
            st.error(alerte["texte"])
        elif alerte["niveau"] == "attention":
            st.warning(alerte["texte"])
        else:
            st.info(alerte["texte"])


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------
def _message(facture: pd.Series, params: dict, portefeuille: pd.DataFrame) -> None:
    st.markdown("#### Message prêt à envoyer")
    if facture["statut"] == "payee":
        st.success("Facture réglée : aucun message à envoyer.")
        return

    identifiant = int(facture["id"])
    avec_ia = ai.disponible(params)

    colonnes = st.columns([1.1, 1.1, 1])
    with colonnes[0]:
        ton = st.radio(
            "Ton",
            options=config.TONS,
            format_func=lambda code: config.TONS_LIBELLES[code],
            index=config.TONS.index(params.get("ton_defaut", "neutre")),
            horizontal=True,
            key=f"ton_{identifiant}",
        )
    with colonnes[1]:
        langue = st.radio(
            "Langue",
            options=config.LANGUES,
            format_func=lambda code: config.LANGUES_LIBELLES[code],
            index=config.LANGUES.index(params.get("langue_defaut", "fr")),
            horizontal=True,
            key=f"langue_{identifiant}",
        )
    with colonnes[2]:
        st.caption(f"Canal : **{config.niveau(facture['niveau'])['action']}**")
        regenerer = st.button("🔄 Régénérer une variante", width="stretch")

    # Le texte réécrit par l'IA n'est valable que pour le ton et la langue demandés.
    cle_ia = f"message_ia_{identifiant}"
    memoire = st.session_state.get(cle_ia) or {}
    texte_ia = memoire.get("texte") if (memoire.get("ton"), memoire.get("langue")) == (ton, langue) else None

    if regenerer:
        variation = st.session_state.get(f"variation_{identifiant}", 0) + 1
        st.session_state[f"variation_{identifiant}"] = variation
        if avec_ia:
            with st.spinner("Nouvelle rédaction par l'IA…"):
                brouillon = service.message_pour(
                    facture.to_dict(), params, ton=ton, langue=langue, avec_ia=False
                )
                proposition = ai.rediger_message(
                    facture={**facture.to_dict(), "nb_relances": int(facture.get("nb_actions") or 0)},
                    niveau_nom=config.niveau(facture["niveau"])["nom"],
                    canal=brouillon["canal"],
                    ton=ton,
                    langue=langue,
                    brouillon=brouillon["texte"],
                    params=params,
                    profil=facture["profil_nom"],
                    conseil_profil=facture["profil_conseil"],
                )
            if proposition:
                st.session_state[cle_ia] = {"ton": ton, "langue": langue, "texte": proposition}
                st.rerun()
            st.warning("L'IA n'a pas répondu : la variante porte sur le ton du modèle intégré.")
        # Sans IA (ou après un échec) : on fait varier le ton, seule dimension paramétrable.
        st.session_state[f"ton_{identifiant}"] = config.TONS[(config.TONS.index(ton) + 1) % len(config.TONS)]
        st.rerun()

    resultat = service.message_pour(facture.to_dict(), params, ton=ton, langue=langue, avec_ia=False)
    texte = texte_ia or resultat["texte"]
    variation = st.session_state.get(f"variation_{identifiant}", 0)

    if resultat["objet"]:
        st.markdown(f"**Objet :** {resultat['objet']}")
    modifier = st.toggle(
        "✏️ Modifier le texte avant de l'envoyer",
        key=f"modifier_{identifiant}",
        help="Ouvrez l'éditeur pour ajuster le message : rien n'est envoyé automatiquement.",
    )
    if modifier:
        texte = st.text_area(
            "Message modifiable",
            value=texte,
            height=320,
            key=f"edition_{identifiant}_{ton}_{langue}_{variation}",
            label_visibility="collapsed",
        )
    else:
        texte = st.text_area(
            "Message",
            value=texte,
            height=340,
            key=f"apercu_{identifiant}_{ton}_{langue}_{variation}",
            label_visibility="collapsed",
        )
    st.caption(
        "Cliquez sur l'icône de copie en haut à droite du bloc ci-dessous, ou sélectionnez le texte. "
        "Vous envoyez ensuite le message par vos propres moyens (SMS, téléphone, email, courrier)."
    )
    common.bloc_copiable(texte, langue)

    boutons = st.columns([1.1, 1.1, 1.4])
    with boutons[0]:
        if st.button("✅ Marquer comme fait", type="primary", width="stretch"):
            db.journaliser(
                action=f"Relance envoyée — {config.niveau(facture['niveau'])['action']}",
                facture_id=identifiant,
                numero=facture["numero"],
                client=facture["client"],
                niveau=facture["niveau"],
                canal=resultat["canal"],
                ton=resultat["ton"],
                langue=resultat["langue"],
                message=texte,
                note=(
                    f"Ton {resultat['ton']} · Langue {resultat['langue']} · "
                    f"Source : {'IA' if texte_ia else 'modèle intégré'}."
                ),
            )
            st.success("Action enregistrée : elle figure dans le journal horodaté et sert de preuve.")
            common.recharger()
    with boutons[1]:
        if st.button("💵 Marquer payée", width="stretch"):
            db.maj_facture(identifiant, statut="payee", date_paiement=date.today(), montant_paye=float(facture["montant"]))
            db.ajouter_reglement(
                client=facture["client"], numero=facture["numero"], montant=float(facture["montant"]),
                echeance=facture["echeance"], date_paiement=date.today(),
                montant_paye=float(facture["montant"]), source="application",
            )
            db.journaliser(
                action="Facture payée — dossier clôturé",
                facture_id=identifiant, numero=facture["numero"], client=facture["client"],
                niveau=facture["niveau"], canal="—",
                note="Ajoutée à l'historique d'apprentissage du modèle de prédiction.",
            )
            st.success("Facture clôturée et ajoutée à l'historique d'apprentissage.")
            common.recharger()
    with boutons[2]:
        st.caption(
            "Texte rédigé par l'IA."
            if texte_ia
            else "Texte produit par le modèle intégré (5 niveaux × 3 tons × 3 langues)."
        )
        if not avec_ia:
            st.caption("Activez l'IA dans ⚙️ Réglages pour une réécriture libre du message.")

    for avertissement in resultat.get("avertissements", []):
        st.warning(avertissement)

    if facture["niveau"] == "miseendemeure":
        st.markdown("##### Contrôle des mentions obligatoires")
        controles = messages.controle_juridique(texte, facture.to_dict(), params)
        for controle in controles:
            st.markdown(("✅ " if controle["ok"] else "❌ ") + controle["libelle"])
        if not all(c["ok"] for c in controles):
            st.error("Complétez les mentions manquantes avant envoi : une mise en demeure incomplète est fragile.")


# ---------------------------------------------------------------------------
# Suivi et clôture
# ---------------------------------------------------------------------------
def _suivi(facture: pd.Series, params: dict) -> None:
    st.markdown("#### Suivi du dossier")
    actions = db.lister_actions(facture_id=int(facture["id"]))
    if actions:
        st.dataframe(
            pd.DataFrame(actions)[["fait_le", "niveau", "canal", "action", "note"]].rename(
                columns={
                    "fait_le": "Date et heure",
                    "niveau": "Niveau",
                    "canal": "Canal",
                    "action": "Action",
                    "note": "Note",
                }
            ),
            width="stretch",
            hide_index=True,
            height=min(320, 80 + 32 * len(actions)),
        )
    else:
        st.info("Aucune action enregistrée pour cette facture.")

    colonnes = st.columns([1, 1, 1])
    with colonnes[0]:
        st.download_button(
            "⬇️ Dossier PDF (preuves)",
            data=reporting.journal_pdf(actions, params, facture.to_dict()),
            file_name=f"dossier_{facture['numero']}.pdf",
            mime="application/pdf",
            width="stretch",
        )
    with colonnes[2]:
        with st.popover("🗑️ Supprimer la facture", width="stretch"):
            st.write("Cette action est définitive.")
            if st.button("Confirmer la suppression", key=f"sup_{facture['id']}"):
                db.supprimer_facture(int(facture["id"]))
                st.session_state.pop("facture_id", None)
                st.success("Facture supprimée.")
                common.recharger()

    with st.expander("➕ Enregistrer une action manuelle ou une note"):
        with st.form(f"action_libre_{facture['id']}"):
            libelle = st.text_input(
                "Action", value="Échange téléphonique avec le client", key=f"libelle_{facture['id']}"
            )
            note = st.text_area("Note", height=80, key=f"note_{facture['id']}")
            if st.form_submit_button("Enregistrer au journal"):
                db.journaliser(
                    action=libelle or "Action",
                    facture_id=int(facture["id"]),
                    numero=facture["numero"],
                    client=facture["client"],
                    niveau=facture["niveau"],
                    canal="manuel",
                    note=note or None,
                )
                st.success("Note ajoutée au journal.")
                common.recharger()

    with st.expander("🔧 Changer le statut / enregistrer un règlement"):
        with st.form(f"statut_{facture['id']}"):
            nouveau = st.selectbox(
                "Nouveau statut",
                options=list(config.STATUTS.keys()),
                index=list(config.STATUTS.keys()).index(facture["statut"]),
                format_func=lambda code: config.STATUTS[code],
            )
            colonnes_form = st.columns([1, 1])
            with colonnes_form[0]:
                jour_paiement = st.date_input("Date de paiement", value=date.today())
            with colonnes_form[1]:
                montant_paye = st.number_input(
                    f"Montant encaissé ({params.get('devise', 'MAD')})",
                    min_value=0.0,
                    value=float(facture["montant"]),
                    format="%.2f",
                )
            promesse = st.date_input("Promesse de paiement (échéancier)", value=date.today() + timedelta(days=15))
            valider = st.form_submit_button("Appliquer", type="primary")
        if valider:
            champs = {"statut": nouveau}
            if nouveau == "payee":
                champs.update(
                    {"date_paiement": jour_paiement, "montant_paye": float(montant_paye)}
                )
                db.ajouter_reglement(
                    client=facture["client"],
                    numero=facture["numero"],
                    montant=float(facture["montant"]),
                    echeance=facture["echeance"],
                    date_paiement=jour_paiement,
                    montant_paye=float(montant_paye),
                    source="application",
                )
                db.journaliser(
                    action="Facture payée — dossier clôturé",
                    facture_id=int(facture["id"]),
                    numero=facture["numero"],
                    client=facture["client"],
                    niveau=facture["niveau"],
                    canal="—",
                    note=f"Encaissé : {montant_paye:.2f} le {jour_paiement}. Ajouté à l'historique d'apprentissage.",
                )
            elif nouveau == "echelonnee":
                champs["date_promesse"] = promesse
                db.journaliser(
                    action="Échéancier accepté",
                    facture_id=int(facture["id"]),
                    numero=facture["numero"],
                    client=facture["client"],
                    niveau=facture["niveau"],
                    canal="accord",
                    note=f"Promesse de paiement au {promesse}.",
                )
            else:
                db.journaliser(
                    action=f"Statut modifié : {config.STATUTS[nouveau]}",
                    facture_id=int(facture["id"]),
                    numero=facture["numero"],
                    client=facture["client"],
                    niveau=facture["niveau"],
                )
            db.maj_facture(int(facture["id"]), **champs)
            st.success("Fiche mise à jour.")
            common.recharger()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def afficher() -> None:
    params = common.lire_params()
    portefeuille = common.portefeuille(params)

    common.entete(
        "📨 Fiche & message",
        "Un dossier à la fois : le niveau atteint, les prédictions, le message et les preuves.",
        params,
    )

    facture = _choisir_facture(portefeuille, params)
    if facture is None:
        return

    _en_tete(facture, params)
    _frise(facture, params)
    st.divider()

    gauche, droite = st.columns([1, 1.05])
    with gauche:
        _alertes(facture, params, portefeuille)
        _prediction(facture, params)
        st.divider()
        _score(facture, params)
        st.divider()
        _recommandation(facture, params, portefeuille)
    with droite:
        _message(facture, params, portefeuille)

    st.divider()
    _suivi(facture, params)
