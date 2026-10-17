"""📋 Factures — le portefeuille trié par urgence, l'ajout et l'import."""
from __future__ import annotations

import base64
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from .. import ai, config, db, ingesta, messages, reporting, service
from . import common


# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------
def _filtres(portefeuille: pd.DataFrame, params: dict) -> pd.DataFrame:
    actif = service.actifs(portefeuille)
    if actif.empty:
        return actif

    with st.expander("🔎 Filtres", expanded=False):
        ligne1 = st.columns([1.4, 1.6, 1])
        with ligne1[0]:
            recherche = st.text_input(
                "Rechercher (client ou n° de facture)",
                value=st.session_state.get("recherche", ""),
                key="recherche",
                placeholder="Ex. Anouar, F-2026-002…",
            )
        with ligne1[1]:
            niveaux = st.multiselect(
                "Niveaux",
                options=[n["code"] for n in config.NIVEAUX],
                default=st.session_state.get("filtre_niveaux", []),
                format_func=lambda code: f"{config.niveau(code)['icone']} {config.niveau(code)['nom']}",
                key="filtre_niveaux",
            )
        with ligne1[2]:
            statuts = st.multiselect(
                "Statut",
                options=["impayee", "echelonnee", "litige"],
                default=st.session_state.get("filtre_statuts", []),
                format_func=lambda code: config.STATUTS.get(code, code),
                key="filtre_statuts",
            )
        ligne2 = st.columns([1.4, 1, 1])
        with ligne2[0]:
            clients = sorted(actif["client"].dropna().unique().tolist())
            selection_clients = st.multiselect(
                "Clients", options=clients, default=st.session_state.get("filtre_clients", []),
                key="filtre_clients",
            )
        with ligne2[1]:
            profils = st.multiselect(
                "Profil de paiement",
                options=list(config.PROFILS.keys()),
                default=st.session_state.get("filtre_profils", []),
                format_func=lambda code: f"{config.PROFILS[code]['icone']} {config.PROFILS[code]['nom']}",
                key="filtre_profils",
            )
        with ligne2[2]:
            devise = params.get("devise", "MAD")
            borne = st.slider(
                f"Montant minimum ({devise})",
                min_value=0,
                max_value=int(max(actif["montant"].max(), 1000)),
                value=int(st.session_state.get("filtre_montant_min", 0)),
                step=500,
                key="filtre_montant_min",
            )

    cadre = actif
    if recherche:
        motif = recherche.strip().lower()
        cadre = cadre[
            cadre["client"].str.lower().str.contains(motif, na=False)
            | cadre["numero"].astype(str).str.lower().str.contains(motif, na=False)
        ]
    if niveaux:
        cadre = cadre[cadre["niveau"].isin(niveaux)]
    if statuts:
        cadre = cadre[cadre["statut"].isin(statuts)]
    if selection_clients:
        cadre = cadre[cadre["client"].isin(selection_clients)]
    if profils:
        cadre = cadre[cadre["profil"].isin(profils)]
    if borne:
        cadre = cadre[cadre["montant"] >= borne]
    return cadre


# ---------------------------------------------------------------------------
# Tableau
# ---------------------------------------------------------------------------
def _tableau(cadre: pd.DataFrame, params: dict) -> None:
    devise = params.get("devise", "MAD")
    st.caption(
        f"{len(cadre)} facture(s) — {messages.formater_montant(cadre['montant'].sum(), devise)} — "
        "triées par score décroissant. Cliquez sur une ligne puis sur **Ouvrir la fiche**."
    )
    colonnes = [
        "numero", "client", "montant", "echeance", "jours_retard", "niveau_nom",
        "score", "priorite", "action_prevue", "p30", "profil_nom", "nb_actions", "telephone",
    ]
    affichage = cadre[colonnes].copy()
    affichage["jours_retard"] = affichage["jours_retard"].astype(int)
    affichage["p30"] = (affichage["p30"] * 100).round(0)
    affichage["niveau_nom"] = [
        f"{config.niveau(code)['icone']} {config.niveau(code)['nom']}" for code in cadre["niveau"]
    ]
    affichage = affichage.rename(
        columns={
            "numero": "N° facture",
            "client": "Client",
            "montant": f"Montant ({devise})",
            "echeance": "Échéance",
            "jours_retard": "Retard (j)",
            "niveau_nom": "Niveau",
            "score": "Score",
            "priorite": "Priorité",
            "action_prevue": "Action prévue",
            "p30": "Paiement 30 j (%)",
            "profil_nom": "Profil",
            "nb_actions": "Relances",
            "telephone": "Téléphone",
        }
    )
    evenement = st.dataframe(
        affichage,
        width="stretch",
        hide_index=True,
        height=min(560, 60 + 35 * len(affichage)),
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d", help="Urgence de 0 à 100"
            ),
            "Montant (" + devise + ")": st.column_config.NumberColumn(
                "Montant (" + devise + ")", format="%.2f"
            ),
            "Échéance": st.column_config.DateColumn("Échéance", format="DD/MM/YYYY"),
            "Paiement 30 j (%)": st.column_config.ProgressColumn(
                "Paiement 30 j (%)", min_value=0, max_value=100, format="%d %%",
                help="Probabilité de paiement estimée sous 30 jours",
            ),
        },
    )

    lignes_selectionnees = getattr(getattr(evenement, "selection", None), "rows", []) or []
    if lignes_selectionnees:
        index = lignes_selectionnees[0]
        ligne = cadre.iloc[index] if index < len(cadre) else None
        if ligne is not None:
            colonnes_action = st.columns([3, 1, 1])
            with colonnes_action[0]:
                st.markdown(
                    f"Sélection : **{ligne['client']}** — {ligne['numero']} — "
                    f"{messages.formater_montant(ligne['montant'], devise)} — "
                    f"{common.badge(ligne['niveau'])}",
                    unsafe_allow_html=True,
                )
            with colonnes_action[1]:
                if st.button("📨 Ouvrir la fiche", type="primary", width="stretch", key="sel_fiche"):
                    common.ouvrir_fiche(int(ligne["id"]))
            with colonnes_action[2]:
                if st.button("✅ Action faite", width="stretch", key="sel_fait"):
                    db.journaliser(
                        action=f"Relance effectuée ({ligne['action_prevue']})",
                        facture_id=int(ligne["id"]),
                        numero=ligne["numero"],
                        client=ligne["client"],
                        niveau=ligne["niveau"],
                        canal=ligne["canal"],
                        note="Marquée comme faite depuis la liste des factures.",
                    )
                    common.recharger()
    else:
        st.caption("Astuce : cliquez sur le carré à gauche d'une ligne pour la sélectionner.")


# ---------------------------------------------------------------------------
# Saisie manuelle
# ---------------------------------------------------------------------------
def _saisie_manuelle(params: dict) -> None:
    devise = params.get("devise", "MAD")
    clients_connus = db.clients_connus()
    with st.form("nouvelle_facture", clear_on_submit=True):
        colonnes = st.columns(2)
        with colonnes[0]:
            client = st.text_input("Client *", help="Saisissez ou collez le nom ; la liste des clients connus est affichée plus bas.")
            numero = st.text_input("N° de facture *")
            montant = st.number_input(f"Montant ({devise}) *", min_value=0.0, step=100.0, format="%.2f")
            echeance = st.date_input("Échéance *", value=date.today() + timedelta(days=30))
        with colonnes[1]:
            emission = st.date_input("Date de facture", value=date.today())
            telephone = st.text_input("Téléphone")
            email = st.text_input("Email")
            nb_retards = st.number_input("Retards passés du client", min_value=0, step=1, value=0)
            statut = st.selectbox(
                "Statut", options=list(config.STATUTS.keys()),
                format_func=lambda code: config.STATUTS[code], index=0,
            )
        notes = st.text_area("Notes internes", height=70)
        valider = st.form_submit_button("Enregistrer la facture", type="primary")

    if clients_connus:
        st.caption("Clients déjà connus : " + ", ".join(clients_connus[:12]) + ("…" if len(clients_connus) > 12 else ""))

    if valider:
        erreurs = []
        if not client.strip():
            erreurs.append("Le nom du client est obligatoire.")
        if not numero.strip():
            erreurs.append("Le numéro de facture est obligatoire.")
        if montant <= 0:
            erreurs.append("Le montant doit être supérieur à zéro.")
        if db.numero_existe(numero.strip()):
            erreurs.append(f"La facture {numero} existe déjà et n'est pas payée.")
        if erreurs:
            for erreur in erreurs:
                st.error(erreur)
            return
        identifiant = db.ajouter_facture(
            {
                "client": client.strip(),
                "numero": numero.strip(),
                "montant": float(montant),
                "date_emission": emission,
                "echeance": echeance,
                "telephone": telephone.strip() or None,
                "email": email.strip() or None,
                "nb_retards_passes": int(nb_retards),
                "statut": statut,
                "notes": notes.strip() or None,
                "source": "saisie",
            }
        )
        db.journaliser(
            action="Facture enregistrée (saisie manuelle)",
            facture_id=identifiant,
            numero=numero.strip(),
            client=client.strip(),
            niveau=config.NIVEAU_A_JOUR["code"],
            note=notes.strip() or None,
        )
        st.success(f"Facture {numero} enregistrée.")
        common.recharger()


# ---------------------------------------------------------------------------
# Import de tableau
# ---------------------------------------------------------------------------
def _import_tableau(fichier, params: dict) -> None:
    try:
        cadre = ingesta.lire_tableau(fichier, fichier.name)
    except Exception as erreur:  # fichier illisible
        st.error(f"Lecture impossible : {erreur}")
        return

    if cadre.empty:
        st.warning("Le fichier ne contient aucune ligne exploitable.")
        return

    st.markdown(f"**{len(cadre)} ligne(s) détectée(s)** — associez les colonnes :")
    devine = ingesta.deviner_mapping(cadre.columns)
    champs = list(config.COLONNES_IMPORT.keys())
    libelles = {
        "client": "Client *", "numero": "N° de facture *", "montant": "Montant *",
        "echeance": "Échéance *", "date_emission": "Date de facture",
        "telephone": "Téléphone", "email": "Email", "nb_retards_passes": "Retards passés",
    }
    options = ["— ignorée —"] + list(cadre.columns)
    mapping: dict[str, str] = {}
    colonnes_saisie = st.columns(4)
    for position, champ in enumerate(champs):
        with colonnes_saisie[position % 4]:
            valeur = st.selectbox(
                libelles[champ],
                options=options,
                index=options.index(devine[champ]) if devine.get(champ) in options else 0,
                key=f"mapping_{champ}_{fichier.name}",
            )
            if valeur != "— ignorée —":
                mapping[champ] = valeur

    manquants = [libelles[c] for c in ingesta.CHAMPS_OBLIGATOIRES if c not in mapping]
    if manquants:
        st.warning("Colonnes obligatoires non associées : " + ", ".join(manquants))

    lignes, rejets = ingesta.preparer_lignes(cadre, mapping)
    if rejets:
        with st.expander(f"⚠️ {len(rejets)} ligne(s) non importable(s)", expanded=False):
            st.dataframe(pd.DataFrame(rejets), width="stretch", hide_index=True)

    if not lignes:
        st.info("Aucune ligne valide à importer.")
        return

    anomalies = ingesta.detecter_anomalies(lignes, db.lister_factures(), params)
    bloquants = {a["index"] for a in anomalies if a["niveau"] == "bloquant"}
    if anomalies:
        st.markdown(f"**🔍 {len(anomalies)} anomalie(s) détectée(s)** — rien n'est encore enregistré :")
        cadre_anomalies = pd.DataFrame(
            [
                {
                    "Gravité": ingesta.GRAVITES.get(a["niveau"], "") + " " + a["niveau"],
                    "Ligne": a["ligne"],
                    "Type": a["type"].replace("_", " "),
                    "Détail": a["message"],
                    "Ligne concernée": (lignes[a["index"]].get("numero") or "") + " / " + (lignes[a["index"]].get("client") or ""),
                }
                for a in anomalies
            ]
        )
        st.dataframe(cadre_anomalies, width="stretch", hide_index=True)
    else:
        st.success("Aucune anomalie détectée : doublons, montants et échéances cohérents.")

    apercu = pd.DataFrame(
        [
            {
                "Client": l["client"],
                "N° facture": l["numero"],
                "Montant": l["montant"],
                "Échéance": l["echeance"],
                "Téléphone": l["telephone"],
                "Email": l["email"],
                "Retards passés": l["nb_retards_passes"],
                "Anomalie bloquante": "oui" if index in bloquants else "",
            }
            for index, l in enumerate(lignes)
        ]
    )
    st.markdown("**Aperçu avant import**")
    st.dataframe(apercu, width="stretch", hide_index=True, height=280)

    exclure = st.checkbox(
        f"Exclure les {len(bloquants)} ligne(s) à anomalie bloquante (recommandé)",
        value=True,
        disabled=not bloquants,
    )
    a_importer = [l for index, l in enumerate(lignes) if not (exclure and index in bloquants)]
    if st.button(f"⬇️ Importer {len(a_importer)} facture(s)", type="primary"):
        identifiants = db.ajouter_factures(a_importer)
        for identifiant, ligne in zip(identifiants, a_importer):
            db.journaliser(
                action="Facture enregistrée (import de fichier)",
                facture_id=identifiant,
                numero=ligne["numero"],
                client=ligne["client"],
                niveau=config.NIVEAU_A_JOUR["code"],
                note=f"Source : {fichier.name}",
            )
        st.success(f"{len(identifiants)} facture(s) importée(s).")
        common.recharger()


# ---------------------------------------------------------------------------
# Import de document (PDF / photo)
# ---------------------------------------------------------------------------
def _import_document(fichier, params: dict) -> None:
    nom = (fichier.name or "").lower()
    texte = ""
    image_base64 = None
    media_type = None
    if nom.endswith(".pdf"):
        texte = ingesta.texte_pdf(fichier)
        if not texte:
            st.warning(
                "Ce PDF ne contient pas de texte (document scanné). Enregistrez-le en image (JPG/PNG) "
                "et importez la photo : l'IA lira alors la facture."
            )
            return
        st.text_area("Texte extrait du PDF", texte[:4000], height=160)
    elif nom.endswith((".png", ".jpg", ".jpeg", ".webp")):
        donnees = fichier.read()
        image_base64 = base64.b64encode(donnees).decode("ascii")
        media_type = "image/png" if nom.endswith(".png") else "image/jpeg"
        st.image(donnees, caption=fichier.name, width=320)
    else:
        st.error("Format non pris en charge pour la lecture d'un document (PDF, PNG, JPG).")
        return

    resultat = None
    if ai.disponible(params):
        if st.button("🤖 Lire le document avec l'IA", type="primary"):
            with st.spinner("Lecture du document…"):
                resultat = ai.extraire_facture_document(texte, params, image_base64, media_type)
            if not resultat:
                st.error("Lecture impossible. Réessayez ou utilisez la saisie manuelle.")
            st.session_state["_document_extrait"] = resultat
        resultat = st.session_state.get("_document_extrait")
    else:
        st.info(
            "IA non configurée : l'application tente une lecture par règles (moins fiable). "
            "Ajoutez une clé API dans ⚙️ Réglages pour une extraction robuste."
        )
        if texte and st.button("Extraire par règles"):
            resultat = [ingesta.extraire_par_regles(texte)]
            st.session_state["_document_extrait"] = resultat
        resultat = st.session_state.get("_document_extrait")

    if not resultat:
        return
    st.markdown("**Vérifiez et corrigez avant d'enregistrer :**")
    candidat = resultat[0] if resultat else {}
    with st.form("facture_document"):
        colonnes = st.columns(2)
        with colonnes[0]:
            client = st.text_input("Client", value=str(candidat.get("client") or ""))
            numero = st.text_input("N° de facture", value=str(candidat.get("numero") or ""))
            montant = st.number_input(
                f"Montant ({params.get('devise', 'MAD')})",
                min_value=0.0,
                value=float(ingesta.parser_montant(candidat.get("montant")) or 0.0),
                format="%.2f",
            )
        with colonnes[1]:
            echeance_defaut = ingesta.parser_date(candidat.get("echeance")) or date.today() + timedelta(days=30)
            echeance = st.date_input("Échéance", value=echeance_defaut)
            telephone = st.text_input("Téléphone", value=str(candidat.get("telephone") or ""))
            email = st.text_input("Email", value=str(candidat.get("email") or ""))
        valider = st.form_submit_button("Enregistrer", type="primary")
    if valider:
        if not client.strip() or not numero.strip() or montant <= 0:
            st.error("Client, numéro de facture et montant sont obligatoires.")
            return
        if db.numero_existe(numero.strip()):
            st.error("Cette facture existe déjà.")
            return
        identifiant = db.ajouter_facture(
            {
                "client": client.strip(),
                "numero": numero.strip(),
                "montant": float(montant),
                "echeance": echeance,
                "telephone": telephone.strip() or None,
                "email": email.strip() or None,
                "statut": "impayee",
                "source": f"document:{fichier.name}",
            }
        )
        db.journaliser(
            action="Facture enregistrée (lecture de document)",
            facture_id=identifiant,
            numero=numero.strip(),
            client=client.strip(),
            niveau=config.NIVEAU_A_JOUR["code"],
            note="Extraction automatique vérifiée par l'utilisateur.",
        )
        st.session_state.pop("_document_extrait", None)
        st.success("Facture enregistrée.")
        common.recharger()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
def afficher() -> None:
    params = common.lire_params()
    portefeuille = common.portefeuille(params)
    devise = params.get("devise", "MAD")

    common.entete(
        "📋 Factures",
        "Le portefeuille classé par score : traitez toujours la première ligne avant les suivantes.",
        params,
    )

    cadre = _filtres(portefeuille, params)
    if cadre.empty:
        st.info(
            "Aucune facture ne correspond aux filtres, ou aucune facture n'est enregistrée. "
            "Utilisez les onglets ci-dessous pour en ajouter."
        )
    else:
        _tableau(cadre, params)
        gauche, droite, tiers = st.columns([1, 1, 1])
        with gauche:
            st.download_button(
                "⬇️ Exporter en Excel",
                data=reporting.factures_excel(cadre, params),
                file_name=f"factures_{date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        with droite:
            st.download_button(
                "⬇️ Exporter en CSV",
                data=reporting.csv_bytes(cadre),
                file_name=f"factures_{date.today().isoformat()}.csv",
                mime="text/csv",
                width="stretch",
            )
        with tiers:
            if st.button("🔄 Recalculer", width="stretch"):
                common.recharger()

    st.divider()
    onglet_import, onglet_saisie, onglet_client = st.tabs(
        ["📥 Importer un fichier ou une facture scannée", "✍️ Saisie manuelle", "👥 Fiches clients"]
    )
    with onglet_import:
        fichier = st.file_uploader(
            "Excel, CSV, PDF ou photo de facture",
            type=["csv", "xlsx", "xlsm", "xls", "txt", "pdf", "png", "jpg", "jpeg"],
            help=(
                "Colonnes reconnues automatiquement : client, n° de facture, montant, échéance, "
                "téléphone, email, retards passés."
            ),
        )
        if fichier is not None:
            if (fichier.name or "").lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp")):
                _import_document(fichier, params)
            else:
                _import_tableau(fichier, params)
        else:
            st.caption(
                "Formats acceptés : `.xlsx`, `.csv`, `.pdf` (facture texte), `.jpg`/`.png` (photo de facture, "
                "lue par l'IA). Rien n'est enregistré sans votre validation."
            )
            modele = pd.DataFrame(
                [
                    {
                        "client": "Atlas Distribution SARL",
                        "numero": "F-2026-001",
                        "montant": 14500,
                        "date_emission": "2026-09-01",
                        "echeance": "2026-10-01",
                        "telephone": "0661223344",
                        "email": "compta@atlas.ma",
                        "nb_retards_passes": 1,
                    }
                ]
            )
            st.download_button(
                "⬇️ Télécharger le modèle CSV",
                data=reporting.csv_bytes(modele),
                file_name="modele_import_factures.csv",
                mime="text/csv",
            )
    with onglet_saisie:
        _saisie_manuelle(params)
    with onglet_client:
        clients = db.lister_clients()
        if not clients:
            st.info("Aucun client enregistré.")
        else:
            cadre_clients = pd.DataFrame(clients).rename(
                columns={"nom": "Client", "telephone": "Téléphone", "email": "Email", "notes": "Notes"}
            )
            st.dataframe(
                cadre_clients[["Client", "Téléphone", "Email", "Notes"]],
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "Les coordonnées proviennent des factures. Un client sans téléphone ni email ne peut pas "
                "être relancé automatiquement : complétez-les ici depuis la fiche concernée."
            )
