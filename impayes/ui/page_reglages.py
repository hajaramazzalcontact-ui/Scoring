"""⚙️ Réglages & historique — les paramètres, le journal des preuves, les données."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from .. import ai, config, db, messages, prediction, reporting, seed, service
from . import common


# ---------------------------------------------------------------------------
# Enregistrement
# ---------------------------------------------------------------------------
def _enregistrer(valeurs: dict) -> None:
    db.ecrire_params(valeurs)
    st.success("Réglages enregistrés.")
    common.recharger()


# ---------------------------------------------------------------------------
# Onglet 1 — Entreprise
# ---------------------------------------------------------------------------
def _onglet_entreprise(params: dict) -> None:
    st.caption(
        "Ces informations apparaissent dans les messages, la mise en demeure et le journal PDF : "
        "elles conditionnent la solidité des preuves."
    )
    with st.form("form_entreprise"):
        colonnes = st.columns(2)
        with colonnes[0]:
            societe = st.text_input("Nom de la société", value=params.get("societe", ""))
            adresse = st.text_input("Adresse", value=params.get("adresse", ""))
            ville = st.text_input("Ville", value=params.get("ville", ""))
            ice = st.text_input("ICE (identifiant commun de l'entreprise)", value=params.get("ice", ""))
        with colonnes[1]:
            telephone = st.text_input("Téléphone", value=params.get("tel_societe", ""))
            email = st.text_input("Email", value=params.get("email_societe", ""))
            devise = st.selectbox(
                "Devise",
                options=["MAD", "EUR", "USD", "TND", "DZD", "XOF"],
                index=["MAD", "EUR", "USD", "TND", "DZD", "XOF"].index(params.get("devise", "MAD")),
            )
            taux = st.number_input(
                "Intérêts de retard (% par mois) — 0 pour ne pas en mentionner",
                min_value=0.0,
                max_value=10.0,
                value=float(params.get("taux_interet_retard", 0.0)),
                step=0.1,
                format="%.2f",
            )
        signature = st.text_area(
            "Formule de politesse / signature",
            value=params.get("signature", ""),
            height=80,
            placeholder="Ex. Cordialement, le service comptabilité",
        )
        if st.form_submit_button("Enregistrer", type="primary"):
            _enregistrer(
                {
                    "societe": societe,
                    "adresse": adresse,
                    "ville": ville,
                    "ice": ice,
                    "tel_societe": telephone,
                    "email_societe": email,
                    "devise": devise,
                    "taux_interet_retard": float(taux),
                    "signature": signature,
                }
            )


# ---------------------------------------------------------------------------
# Onglet 2 — Seuils et scoring
# ---------------------------------------------------------------------------
def _onglet_seuils(params: dict) -> None:
    st.markdown("##### Les cinq niveaux de traitement")
    st.caption(
        "Les seuils se comptent en jours de retard depuis l'échéance. Un seuil à 8 signifie "
        "« niveau atteint dès le 8ᵉ jour de retard »."
    )
    with st.form("form_seuils"):
        colonnes = st.columns(5)
        valeurs = {}
        for colonne, definition in zip(colonnes, config.NIVEAUX):
            with colonne:
                cle = f"seuil_{definition['code']}"
                valeurs[cle] = int(
                    st.number_input(
                        f"{definition['icone']} {definition['nom']}",
                        min_value=1,
                        max_value=730,
                        value=int(params.get(cle, config.DEFAUT_PARAMS[cle])),
                        step=1,
                        key=f"input_{cle}",
                    )
                )
                st.caption(definition["action"])
        st.markdown("##### Pondérations du score (0-100)")
        st.caption(
            "Les quatre critères sont normalisés : quel que soit le total saisi, le score reste sur 100. "
            "L'application affiche toujours le détail des points attribués."
        )
        colonnes_poids = st.columns(4)
        poids = {}
        for colonne, (cle, libelle, aide) in zip(
            colonnes_poids,
            [
                ("poids_retard", "Durée du retard", "Poids le plus déterminant en général."),
                ("poids_montant", "Montant impayé", "Position du montant dans votre portefeuille."),
                ("poids_historique", "Historique du client", "Nombre de retards déjà constatés."),
                ("poids_risque", "Risque de non-paiement", "Issu de la probabilité estimée par l'IA."),
            ],
        ):
            with colonne:
                poids[cle] = int(
                    st.number_input(
                        libelle, min_value=0, max_value=100,
                        value=int(params.get(cle, config.DEFAUT_PARAMS[cle])),
                        step=5, help=aide, key=f"input_{cle}",
                    )
                )
        colonnes_fin = st.columns(2)
        with colonnes_fin[0]:
            horizon = int(
                st.number_input(
                    "Retard à partir duquel le critère « durée » est saturé (jours)",
                    min_value=10, max_value=365,
                    value=int(params.get("horizon_retard", 60)), step=5,
                )
            )
        with colonnes_fin[1]:
            max_retards = int(
                st.number_input(
                    "Nombre de retards passés saturant le critère « historique »",
                    min_value=1, max_value=20,
                    value=int(params.get("score_max_retards", 5)), step=1,
                )
            )
        valider = st.form_submit_button("Enregistrer les seuils et pondérations", type="primary")

    if valider:
        toutes = {**valeurs, **poids, "horizon_retard": horizon, "score_max_retards": max_retards}
        valide, message = config.seuils_valides({**params, **toutes})
        if not valide:
            st.error(message)
        else:
            _enregistrer(toutes)

    valide, message = config.seuils_valides(params)
    if valide:
        st.success(message)
    else:
        st.error(message)

    st.markdown("##### Ce que ces seuils produisent aujourd'hui")
    lignes = []
    aujourdhui = date.today()
    for definition in config.NIVEAUX:
        seuil = config.seuils(params)[definition["code"]]
        lignes.append(
            {
                "Niveau": f"{definition['icone']} {definition['nom']}",
                "Déclenchement": f"dès {seuil} jour(s) de retard",
                "Date d'atteinte pour une facture échue aujourd'hui": (aujourdhui + timedelta(days=seuil)).strftime("%d/%m/%Y"),
                "Action": definition["action"],
                "Ton": definition["ton"],
            }
        )
    st.dataframe(pd.DataFrame(lignes), width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Onglet 3 — Messages
# ---------------------------------------------------------------------------
def _onglet_messages(params: dict) -> None:
    with st.form("form_messages"):
        colonnes = st.columns(2)
        with colonnes[0]:
            ton = st.radio(
                "Ton par défaut",
                options=config.TONS,
                index=config.TONS.index(params.get("ton_defaut", "neutre")),
                format_func=lambda code: config.TONS_LIBELLES[code],
            )
        with colonnes[1]:
            langue = st.radio(
                "Langue par défaut",
                options=config.LANGUES,
                index=config.LANGUES.index(params.get("langue_defaut", "fr")),
                format_func=lambda code: config.LANGUES_LIBELLES[code],
            )
        colonnes_delai = st.columns(3)
        with colonnes_delai[0]:
            delai_rappel = int(
                st.number_input(
                    "Délai laissé au niveau 1 (heures)", min_value=1, max_value=336,
                    value=int(params.get("delai_rappel", 48)), step=12,
                )
            )
        with colonnes_delai[1]:
            delai_relance = int(
                st.number_input(
                    "Délai laissé au niveau 3 (jours)", min_value=1, max_value=90,
                    value=int(params.get("delai_relance", 7)), step=1,
                )
            )
        with colonnes_delai[2]:
            delai_med = int(
                st.number_input(
                    "Délai laissé en mise en demeure (jours)", min_value=1, max_value=90,
                    value=int(params.get("delai_miseendemeure", 8)), step=1,
                )
            )
        if st.form_submit_button("Enregistrer", type="primary"):
            _enregistrer(
                {
                    "ton_defaut": ton,
                    "langue_defaut": langue,
                    "delai_rappel": delai_rappel,
                    "delai_relance": delai_relance,
                    "delai_miseendemeure": delai_med,
                }
            )

    st.markdown("##### Aperçu des modèles par niveau et par ton")
    exemple = {
        "client": "Clinique Anouar",
        "numero": "F-2026-002",
        "montant": 45000.0,
        "echeance": date.today() - timedelta(days=12),
        "jours_retard": 12,
        "telephone": "0662 34 56 78",
        "email": "facturation@clinique-anouar.ma",
        "nb_retards_passes": 2,
    }
    onglets = st.tabs([f"{d['icone']} {d['nom']}" for d in config.NIVEAUX] + ["🎚️ Comparer les tons"])
    for onglet, definition in zip(onglets, config.NIVEAUX):
        with onglet:
            vignette = {
                **exemple,
                "jours_retard": config.seuils(params)[definition["code"]] + 2,
                "echeance": date.today() - timedelta(days=config.seuils(params)[definition["code"]] + 2),
            }
            message = messages.generer(vignette, params, niveau_code=definition["code"])
            st.caption(f"Canal : {message['canal']} — délai accordé : {messages.delai_pour_niveau(definition['code'], params)} jour(s)")
            st.code(message["texte"], language="text")
    with onglets[-1]:
        colonnes = st.columns(3)
        for colonne, ton_code in zip(colonnes, config.TONS):
            with colonne:
                st.markdown(f"**{config.TONS_LIBELLES[ton_code]}**")
                texte = messages.generer(exemple, params, niveau_code="relance", ton=ton_code)["texte"]
                st.text_area(
                    "Email de relance", value=texte, height=280,
                    key=f"apercu_ton_{ton_code}", label_visibility="collapsed",
                )


# ---------------------------------------------------------------------------
# Onglet 4 — IA
# ---------------------------------------------------------------------------
def _onglet_ia(params: dict) -> None:
    etat = ai.etat(params)
    if etat["niveau"] == "success":
        st.success(etat["raison"])
    elif etat["niveau"] == "warning":
        st.warning(etat["raison"])
    else:
        st.info(etat["raison"])

    st.caption(
        "L'application fonctionne intégralement sans IA : les modèles de messages, le scoring et les "
        "prédictions sont calculés localement. L'IA apporte la réécriture libre, la recommandation, "
        "le briefing et la lecture des factures scannées."
    )
    with st.form("form_ia"):
        actif = st.toggle("Activer les fonctions IA", value=str(params.get("ia_actif", "1")) in ("1", "True", "true"))
        cle = st.text_input(
            "Clé API Anthropic",
            value=params.get("ia_cle_api", ""),
            type="password",
            help="Stockée uniquement dans votre base locale. Vous pouvez aussi définir la variable d'environnement ANTHROPIC_API_KEY.",
        )
        modele = st.selectbox(
            "Modèle",
            options=ai.MODELES_CONNUS,
            index=ai.MODELES_CONNUS.index(params.get("ia_modele"))
            if params.get("ia_modele") in ai.MODELES_CONNUS
            else 0,
            help="Choisissez un modèle rapide pour les messages, un modèle plus capable pour l'analyse.",
        )
        if st.form_submit_button("Enregistrer", type="primary"):
            _enregistrer({"ia_actif": "1" if actif else "0", "ia_cle_api": cle, "ia_modele": modele})

    colonnes = st.columns([1, 2])
    with colonnes[0]:
        if st.button("🔌 Tester la connexion", width="stretch"):
            with st.spinner("Appel du modèle…"):
                ok, message = ai.tester_connexion({**params, "ia_cle_api": params.get("ia_cle_api", "")})
            (st.success if ok else st.error)(message)
    with colonnes[1]:
        st.caption(
            "Confidentialité : seules les informations nécessaires (nom du client, montant, dates, "
            "historique des relances) sont transmises au modèle. Aucun message n'est envoyé à un client "
            "sans votre validation explicite."
        )

    st.markdown("##### Où l'IA intervient")
    st.dataframe(
        pd.DataFrame(
            [
                {"Fonction": "Rédaction des messages", "Ce qu'elle apporte": "Réécrit le message selon le profil, l'historique et le ton choisi.", "Sans IA": "Modèles intégrés, 5 niveaux × 3 tons × 3 langues."},
                {"Fonction": "Recommandation d'action", "Ce qu'elle apporte": "Choisit la meilleure étape suivante et l'explique.", "Sans IA": "Règles par profil client (oublieux, récidiviste…)."},
                {"Fonction": "Briefing quotidien", "Ce qu'elle apporte": "Résumé rédigé de la journée.", "Sans IA": "Synthèse chiffrée automatique."},
                {"Fonction": "Assistant conversationnel", "Ce qu'elle apporte": "Répond à toute question libre sur le portefeuille.", "Sans IA": "Questions courantes traitées par calcul."},
                {"Fonction": "Lecture de factures scannées", "Ce qu'elle apporte": "Extrait client, montant, échéance d'un PDF ou d'une photo.", "Sans IA": "Lecture par règles (PDF texte uniquement)."},
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    st.markdown("##### Apparence")
    theme = st.radio(
        "Thème des graphiques",
        options=["plotly_white", "plotly_dark"],
        index=["plotly_white", "plotly_dark"].index(params.get("theme_graphique", "plotly_white")),
        format_func=lambda valeur: "☀️ Clair" if valeur == "plotly_white" else "🌙 Sombre",
        horizontal=True,
    )
    if theme != params.get("theme_graphique"):
        db.ecrire_params({"theme_graphique": theme})
        common.recharger()


# ---------------------------------------------------------------------------
# Onglet 5 — Historique
# ---------------------------------------------------------------------------
def _onglet_historique(params: dict) -> None:
    st.caption(
        "Le journal horodaté est la preuve du recouvrement amiable : il montre qui a été relancé, quand, "
        "par quel canal et avec quels mots. Exportez-le avant toute transmission à un avocat."
    )
    actions = db.lister_actions()
    if not actions:
        st.info("Aucune action enregistrée pour l'instant.")
        return

    cadre = pd.DataFrame(actions)
    cadre["fait_le_brut"] = pd.to_datetime(cadre["fait_le"], errors="coerce")
    colonnes = st.columns(4)
    with colonnes[0]:
        periode = st.selectbox("Période", ["Tout", "7 derniers jours", "30 derniers jours", "Aujourd'hui"])
    with colonnes[1]:
        clients = ["Tous"] + sorted(cadre["client"].dropna().unique().tolist())
        client_choisi = st.selectbox("Client", clients)
    with colonnes[2]:
        niveaux = ["Tous"] + [n["code"] for n in config.NIVEAUX]
        niveau_choisi = st.selectbox(
            "Niveau", niveaux, format_func=lambda c: "Tous" if c == "Tous" else config.niveau(c)["nom"]
        )
    with colonnes[3]:
        recherche = st.text_input("N° de facture", "")

    filtre = cadre.copy()
    maintenant = datetime.now()
    if periode == "7 derniers jours":
        filtre = filtre[filtre["fait_le_brut"] >= maintenant - timedelta(days=7)]
    elif periode == "30 derniers jours":
        filtre = filtre[filtre["fait_le_brut"] >= maintenant - timedelta(days=30)]
    elif periode == "Aujourd'hui":
        filtre = filtre[filtre["fait_le_brut"].dt.date == date.today()]
    if client_choisi != "Tous":
        filtre = filtre[filtre["client"] == client_choisi]
    if niveau_choisi != "Tous":
        filtre = filtre[filtre["niveau"] == niveau_choisi]
    if recherche:
        filtre = filtre[filtre["numero"].astype(str).str.contains(recherche.strip(), case=False, na=False)]

    st.markdown(f"**{len(filtre)} action(s)** sur {len(cadre)} enregistrée(s).")
    st.dataframe(
        filtre[["fait_le", "numero", "client", "niveau", "canal", "action", "note", "utilisateur"]].rename(
            columns={
                "fait_le": "Date et heure", "numero": "Facture", "client": "Client", "niveau": "Niveau",
                "canal": "Canal", "action": "Action", "note": "Note", "utilisateur": "Par",
            }
        ),
        width="stretch",
        hide_index=True,
        height=min(460, 80 + 32 * len(filtre)),
    )

    colonnes_export = st.columns(4)
    libelle_periode = "Journal complet" if periode == "Tout" else f"Journal — {periode.lower()}"
    with colonnes_export[0]:
        st.download_button(
            "⬇️ Journal PDF (preuve)",
            data=reporting.journal_pdf(filtre.to_dict("records"), params, periode=libelle_periode),
            file_name=f"journal_relances_{date.today().isoformat()}.pdf",
            mime="application/pdf",
            type="primary",
            width="stretch",
        )
    with colonnes_export[1]:
        st.download_button(
            "⬇️ Journal CSV",
            data=reporting.csv_bytes(filtre.drop(columns=["fait_le_brut"])),
            file_name=f"journal_relances_{date.today().isoformat()}.csv",
            mime="text/csv",
            width="stretch",
        )
    with colonnes_export[2]:
        periode_debut = (cadre["fait_le_brut"].min() or maintenant).strftime("%d/%m/%Y")
        st.caption(f"Première action : {periode_debut}")
    with colonnes_export[3]:
        st.caption("Le PDF inclut la copie des messages adressés.")

    with st.expander("📚 Historique d'apprentissage du modèle"):
        reglements = db.lister_reglements()
        if not reglements:
            st.info("Aucun règlement historique enregistré.")
            return
        cadre_reg = pd.DataFrame(reglements)
        st.markdown(
            f"**{len(cadre_reg)} règlement(s)** — de "
            f"{cadre_reg['echeance'].min()} à {cadre_reg['echeance'].max()}."
        )
        statistiques = prediction.statistiques_clients(reglements)
        tableau = pd.DataFrame(
            [
                {
                    "Client": valeur["client"],
                    "Factures réglées": valeur["nb_reglements"],
                    "Retard moyen (j)": round(valeur["retard_moyen"], 1),
                    "Retard maximum (j)": valeur["retard_max"],
                    "Payées en retard": common.pourcentage(valeur["taux_retard"]),
                }
                for valeur in sorted(statistiques.values(), key=lambda v: -v["nb_reglements"])
            ]
        )
        st.dataframe(tableau, width="stretch", hide_index=True)
        st.download_button(
            "⬇️ Exporter l'historique des règlements (CSV)",
            data=reporting.csv_bytes(cadre_reg),
            file_name="historique_reglements.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# Onglet 6 — Données
# ---------------------------------------------------------------------------
def _onglet_donnees(params: dict) -> None:
    statistiques = db.statistiques_base()
    colonnes = st.columns(4)
    colonnes[0].metric("Factures", statistiques["factures"])
    colonnes[1].metric("Actions journalisées", statistiques["actions"])
    colonnes[2].metric("Règlements historiques", statistiques["reglements"])
    colonnes[3].metric("Fichier de données", f"{db.chemin_base().stat().st_size / 1024:.0f} Ko" if db.chemin_base().exists() else "absent")
    st.caption(f"Base locale : `{db.chemin_base()}` — aucune donnée ne sort de votre machine en dehors des appels IA que vous déclenchez.")

    st.markdown("##### Jeu de démonstration")
    st.caption(
        "Charge 12 factures réparties sur les cinq niveaux, plus un historique de paiement de trois ans "
        "qui sert à entraîner le modèle de prédiction."
    )
    colonnes_demo = st.columns(2)
    with colonnes_demo[0]:
        if st.button("📥 Charger la démonstration (ajoute aux données existantes)", width="stretch"):
            resume = seed.charger_donnees_demo(remplacer=False)
            st.success(f"{resume['factures']} facture(s) et {resume['reglements']} règlement(s) ajoutés.")
            common.recharger()
    with colonnes_demo[1]:
        if st.button("♻️ Remplacer toutes les données par la démonstration", width="stretch"):
            resume = seed.charger_donnees_demo(remplacer=True)
            st.success(f"Données remplacées : {resume['factures']} factures, {resume['reglements']} règlements.")
            common.recharger()

    st.divider()
    st.markdown("##### Sauvegarde et remise à zéro")
    colonnes_donnees = st.columns(3)
    with colonnes_donnees[0]:
        st.download_button(
            "💾 Télécharger la base complète",
            data=db.sauvegarde_bytes(),
            file_name=f"impayes_sauvegarde_{date.today().isoformat()}.db",
            mime="application/octet-stream",
            width="stretch",
        )
    with colonnes_donnees[1]:
        with st.popover("🗑️ Vider toutes les données", width="stretch"):
            st.write(
                "Supprime les factures, le journal, les règlements et les clients. "
                "Les réglages (seuils, pondérations, société) sont conservés."
            )
            if st.button("Confirmer la suppression", key="vider_tout"):
                db.supprimer_tout()
                st.success("Données supprimées.")
                common.recharger()
    with colonnes_donnees[2]:
        with st.popover("↩️ Réinitialiser les réglages", width="stretch"):
            st.write("Rétablit les seuils, pondérations et textes par défaut.")
            if st.button("Confirmer la réinitialisation", key="reset_params"):
                db.reinitialiser_params()
                st.success("Réglages réinitialisés.")
                common.recharger()

    st.divider()
    st.markdown("##### À propos")
    st.markdown(
        f"""
**Scoring des Impayés** — version {__import__('impayes').__version__}

Le parcours en sept étapes : régler l'application → enregistrer les factures →
laisser calculer → lire la synthèse → ouvrir la facture la plus urgente →
envoyer le message préparé → clôturer.

* Les modèles de mise en demeure et de note au conseil sont des **brouillons** :
  faites-les valider par un juriste avant tout envoi.
* Les noms, téléphones et emails sont des données personnelles : au Maroc,
  la loi 09-08 et la CNDP encadrent leur traitement. Les données restent sur votre machine.
* Aucun message n'est envoyé automatiquement : vous relisez, vous copiez, vous envoyez.
"""
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def afficher() -> None:
    params = common.lire_params()
    common.entete(
        "⚙️ Réglages & historique",
        "Tout est réglable : seuils, pondérations, tons. Le journal horodaté est votre preuve.",
        params,
    )

    onglets = st.tabs(
        [
            "🏢 Entreprise",
            "🎚️ Seuils & scoring",
            "✍️ Messages",
            "🤖 Intelligence artificielle",
            "🗂️ Journal & preuves",
            "🧪 Données",
        ]
    )
    with onglets[0]:
        _onglet_entreprise(params)
    with onglets[1]:
        _onglet_seuils(params)
    with onglets[2]:
        _onglet_messages(params)
    with onglets[3]:
        _onglet_ia(params)
    with onglets[4]:
        _onglet_historique(params)
    with onglets[5]:
        _onglet_donnees(params)
