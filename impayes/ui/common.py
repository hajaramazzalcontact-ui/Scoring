"""Briques d'interface partagées : thème, badges, jauges, graphiques, frise."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import cashflow, config, db, messages, prediction, scoring, service

PALETTE = {
    "rappel": "#16a34a",
    "contact": "#ca8a04",
    "relance": "#ea580c",
    "miseendemeure": "#dc2626",
    "contentieux": "#1f2937",
    "a_jour": "#64748b",
}

SEUILS_CRITIQUES = [
    {"libelle": "P1 — critique", "valeur": 80, "couleur": "#dc2626"},
    {"libelle": "P2 — élevée", "valeur": 65, "couleur": "#ea580c"},
    {"libelle": "P3 — moyenne", "valeur": 45, "couleur": "#ca8a04"},
    {"libelle": "P4 — modérée", "valeur": 25, "couleur": "#0ea5e9"},
    {"libelle": "P5 — faible", "valeur": 0, "couleur": "#16a34a"},
]


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3)
def _portefeuille(signature: str, params_json: str, date_reference_iso: str) -> pd.DataFrame:
    params = json.loads(params_json)
    return service.construire_portefeuille(
        params=params, date_reference=date.fromisoformat(date_reference_iso)
    )


def portefeuille(params: dict | None = None, forcer: bool = False) -> pd.DataFrame:
    """Portefeuille enrichi, recalculé uniquement quand les données changent."""
    params = params or lire_params()
    if forcer:
        _portefeuille.clear()
    return _portefeuille(
        db.signature(),
        json.dumps(params, sort_keys=True, default=str),
        date.today().isoformat(),
    )


def lire_params() -> dict:
    return db.lire_params()


def invalider() -> None:
    """À appeler après toute écriture : vide le cache de calcul."""
    _portefeuille.clear()


def recharger() -> None:
    invalider()
    st.rerun()


# ---------------------------------------------------------------------------
# Formatage
# ---------------------------------------------------------------------------
def montant(valeur, params: dict | None = None, langue: str = "fr") -> str:
    params = params or {}
    return messages.formater_montant(valeur or 0, params.get("devise", "MAD"), langue)


def date_courte(valeur, langue: str = "fr") -> str:
    return messages.formater_date(valeur, langue)


def pourcentage(valeur, decimales: int = 0) -> str:
    try:
        return f"{float(valeur or 0) * 100:.{decimales}f} %"
    except (TypeError, ValueError):
        return "—"


def couleur_niveau(code: str | None) -> str:
    return PALETTE.get(code or "", config.niveau(code).get("couleur", "#64748b"))


def couleur_score(score: float) -> str:
    for seuil in SEUILS_CRITIQUES:
        if (score or 0) >= seuil["valeur"]:
            return seuil["couleur"]
    return "#16a34a"


# ---------------------------------------------------------------------------
# Thème
# ---------------------------------------------------------------------------
CSS = """
<style>
/* --- Cartes et blocs ------------------------------------------------- */
div[data-testid="stMetric"] {
    background: var(--carte-fond);
    border: 1px solid var(--carte-bord);
    border-left: 4px solid var(--carte-accent);
    border-radius: 10px;
    padding: 12px 14px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .06);
}
div[data-testid="stMetric"] label p { font-size: .82rem; letter-spacing: .01em; }
div[data-testid="stMetricValue"] { font-weight: 700; }
/* --- Badges de niveau ------------------------------------------------- */
.badge {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: .78rem; font-weight: 700; color: #fff; white-space: nowrap;
}
.badge-outline {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: .78rem; font-weight: 600; border: 1px solid currentColor;
}
/* --- Bandeau d'en-tête ------------------------------------------------ */
.entete {
    border-radius: 14px; padding: 18px 22px; margin-bottom: 10px;
    background: var(--entete-fond); border: 1px solid var(--carte-bord);
}
.entete h1 { margin: 0; font-size: 1.55rem; }
.entete p { margin: 4px 0 0 0; opacity: .82; font-size: .9rem; }
/* --- Frise chronologique --------------------------------------------- */
.frise { display: flex; gap: 6px; flex-wrap: wrap; margin: 6px 0 2px 0; }
.frise .etape {
    flex: 1 1 150px; border-radius: 10px; padding: 8px 10px; font-size: .8rem;
    border: 1px solid var(--carte-bord); background: var(--carte-fond); position: relative;
}
.frise .etape .nom { font-weight: 700; display: block; margin-bottom: 2px; }
.frise .etape.actuel { border-width: 2px; border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent); }
.frise .etape.passe, .frise .etape.depasse { opacity: .72; }
.frise .etape.passe { background: color-mix(in srgb, var(--accent) 10%, var(--carte-fond)); }
/* --- Cartes cliquables ------------------------------------------------ */
.carte-niveau {
    border-radius: 12px; padding: 12px; text-align: center; color: #fff;
    box-shadow: 0 2px 6px rgba(15,23,42,.10);
}
.carte-niveau .nb { font-size: 1.6rem; font-weight: 800; line-height: 1.1; }
.carte-niveau .lib { font-size: .78rem; opacity: .95; }
.carte-niveau .mt { font-size: .72rem; opacity: .85; }
/* --- Bulles de l'assistant ------------------------------------------- */
.bulle { border-radius: 12px; padding: 12px 14px; margin: 6px 0; border: 1px solid var(--carte-bord); }
.bulle.ia { background: color-mix(in srgb, #2563eb 8%, var(--carte-fond)); }
.bulle.moi { background: var(--carte-fond); }
.bulle .qui { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; opacity: .65; }
/* --- Couleur du code de priorité ------------------------------------- */
.mono { font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }
.rtl { direction: rtl; text-align: right; }
.petit { font-size: .8rem; opacity: .78; }
.sep { height: 1px; background: var(--carte-bord); margin: 10px 0; border: 0; }
</style>
"""


def appliquer_theme(params: dict) -> None:
    """Injecte les variables de couleur selon le thème clair ou sombre."""
    sombre = params.get("theme_graphique") == "plotly_dark"
    if sombre:
        variables = """
        --carte-fond: #1e293b; --carte-bord: #334155; --entete-fond: linear-gradient(100deg,#111827,#1e293b);
        --accent: #f8fafc; --texte: #e2e8f0;
        """
    else:
        variables = """
        --carte-fond: #ffffff; --carte-bord: #e2e8f0; --entete-fond: linear-gradient(100deg,#f8fafc,#eef2ff);
        --accent: #1e293b; --texte: #0f172a;
        """
    st.markdown(f"<style>:root {{ {variables} }}</style>", unsafe_allow_html=True)
    st.markdown(CSS.replace("--carte-accent", couleur_score(70)), unsafe_allow_html=True)


def gabarit_graphique(params: dict) -> dict:
    """Thème Plotly cohérent avec le mode clair ou sombre."""
    return {
        "template": params.get("theme_graphique", "plotly_white"),
        "margin": {"l": 10, "r": 10, "t": 36, "b": 10},
        "font": {"family": "Inter, Segoe UI, sans-serif", "size": 12},
        "showlegend": True,
    }


# ---------------------------------------------------------------------------
# Petits composants HTML
# ---------------------------------------------------------------------------
def badge(code_niveau: str | None, libelle: str | None = None) -> str:
    definition = config.niveau(code_niveau)
    texte = libelle or f"{definition['icone']} {definition['nom']}"
    retour = "\n" if not texte else ""
    return (
        f'<span class="badge" style="background:{couleur_niveau(code_niveau)}">'
        f"{texte}{retour}</span>"
    )


def badge_priorite(score: int) -> str:
    couleur = couleur_score(score)
    return (
        f'<span class="badge-outline" style="color:{couleur};background:{couleur}18">'
        f"Score {int(score or 0)}/100</span>"
    )


def entete(titre: str, sous_titre: str, params: dict, extra: str = "") -> None:
    st.markdown(
        f"""<div class="entete">
        <h1>{titre}</h1>
        <p>{params.get('societe', 'Ma Société')} — {sous_titre}</p>
        {extra}
        </div>""",
        unsafe_allow_html=True,
    )


def bloc_texte(texte: str, langue: str = "fr", classe: str = "petit") -> None:
    """Affiche un texte, en respectant le sens de lecture de l'arabe."""
    if langue in config.LANGUES_RTL:
        st.markdown(f'<div class="rtl {classe}">{texte}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="{classe}">{texte}</div>', unsafe_allow_html=True)


def bloc_copiable(texte: str, langue: str = "fr", hauteur: int | None = None) -> None:
    """Affiche un texte dans un bloc mono avec le bouton de copie natif de Streamlit.

    Streamlit place une icône de copie en haut à droite du bloc : un clic copie
    l'intégralité du texte dans le presse-papiers du navigateur.
    """
    st.code(texte or "", language=None, wrap_lines=True, height=hauteur or "content")
    if langue in config.LANGUES_RTL:
        st.caption("Aperçu dans le sens de lecture de droite à gauche :")
        st.markdown(
            f'<div class="rtl" style="border:1px solid var(--carte-bord);'
            f'border-radius:10px;padding:10px 12px;white-space:pre-wrap">{texte}</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Graphiques
# ---------------------------------------------------------------------------
def jauge_score(score: float, hauteur: int = 210, titre: str = "Score d'urgence") -> go.Figure:
    """Jauge circulaire : un coup d'œil suffit pour juger l'urgence."""
    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=float(score or 0),
            number={"suffix": " / 100", "font": {"size": 26}},
            title={"text": titre, "font": {"size": 13}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#94a3b8"},
                "bar": {"color": couleur_score(score), "thickness": 0.28},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 25], "color": "rgba(22,163,74,.22)"},
                    {"range": [25, 45], "color": "rgba(14,165,233,.20)"},
                    {"range": [45, 65], "color": "rgba(202,138,4,.22)"},
                    {"range": [65, 80], "color": "rgba(234,88,12,.22)"},
                    {"range": [80, 100], "color": "rgba(220,38,38,.25)"},
                ],
                "threshold": {
                    "line": {"color": "#0f172a", "width": 3},
                    "thickness": 0.8,
                    "value": float(score or 0),
                },
            },
        )
    )
    figure.update_layout(height=hauteur, margin={"l": 14, "r": 14, "t": 34, "b": 6})
    return figure


def graphique_entonnoir(cadre: pd.DataFrame, params: dict) -> go.Figure:
    """Entonnoir des cinq niveaux : combien de factures, pour quel montant."""
    compte = service.repartition_niveaux(cadre)
    etiquettes, valeurs, montants, couleurs = [], [], [], []
    for definition in config.NIVEAUX:
        code = definition["code"]
        compte_niveau = compte.get(code, 0)
        sous_ensemble = cadre[cadre["niveau"] == code] if not cadre.empty else cadre
        etiquettes.append(f"{definition['icone']} {definition['nom']}")
        valeurs.append(compte_niveau)
        montants.append(float(sous_ensemble["montant"].sum()) if not sous_ensemble.empty else 0.0)
        couleurs.append(definition["couleur"])
    figure = go.Figure(
        go.Funnel(
            y=etiquettes,
            x=valeurs,
            text=[f"{v} facture(s) — {messages.formater_montant(m, params.get('devise', 'MAD'))}" for m, v in zip(montants, valeurs)],
            textinfo="text",
            marker={"color": couleurs},
            connector={"line": {"color": "#cbd5e1"}},
        )
    )
    figure.update_layout(title="Entonnoir des niveaux de traitement", height=300, **gabarit_graphique(params))
    return figure


def graphique_repartition(cadre: pd.DataFrame, params: dict) -> go.Figure:
    """Répartition du montant impayé par niveau (barres horizontales)."""
    lignes = []
    for definition in config.NIVEAUX:
        sous_ensemble = cadre[cadre["niveau"] == definition["code"]] if not cadre.empty else cadre
        lignes.append(
            {
                "niveau": f"{definition['icone']} {definition['nom']}",
                "montant": float(sous_ensemble["montant"].sum()) if not sous_ensemble.empty else 0.0,
                "couleur": definition["couleur"],
            }
        )
    cadre_graphique = pd.DataFrame(lignes)
    figure = go.Figure(
        go.Bar(
            x=cadre_graphique["montant"],
            y=cadre_graphique["niveau"],
            orientation="h",
            marker={"color": cadre_graphique["couleur"]},
            text=[messages.formater_montant(m, params.get("devise", "MAD")) for m in cadre_graphique["montant"]],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,.0f}<extra></extra>",
        )
    )
    figure.update_layout(
        title="Montant impayé par niveau", height=300, yaxis={"autorange": "reversed"},
        **gabarit_graphique(params),
    )
    return figure


def graphique_aging(cadre: pd.DataFrame, params: dict) -> go.Figure:
    """Courbe du vieillissement des créances : montant cumulé par jours de retard."""
    if cadre.empty:
        figure = go.Figure()
        figure.update_layout(title="Aucun impayé", height=280, **gabarit_graphique(params))
        return figure
    tries = cadre.sort_values("jours_retard").copy()
    tries["cumul"] = tries["montant"].cumsum()
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=tries["jours_retard"], y=tries["cumul"], mode="lines+markers",
            name="Cumul du montant à ce retard", line={"color": "#dc2626", "width": 3},
            fill="tozeroy", fillcolor="rgba(220,38,38,.12)",
            hovertemplate="Retard ≥ %{x} j<br>Cumul : %{y:,.0f}<extra></extra>",
        )
    )
    for definition in config.NIVEAUX:
        seuil = config.seuils(params)[definition["code"]]
        figure.add_vline(
            x=seuil, line_dash="dot", line_color=definition["couleur"],
            annotation_text=definition["nom"], annotation_position="top",
            annotation_font_size=10,
        )
    figure.update_layout(
        title="Vieillissement des créances (montant cumulé)",
        xaxis_title="Jours de retard", yaxis_title=f"Montant cumulé ({params.get('devise', 'MAD')})",
        height=320, **gabarit_graphique(params),
    )
    return figure


def graphique_projection(factures: list[dict], params: dict) -> go.Figure:
    """Projection d'encaissement : prudent / réaliste / optimiste à 7, 30 et 90 jours."""
    simulation = cashflow.simuler(factures, params)
    tableau = simulation["par_horizon"]
    figure = go.Figure()
    for scenario, couleur in (("prudent", "#dc2626"), ("realiste", "#0ea5e9"), ("optimiste", "#16a34a")):
        figure.add_trace(
            go.Bar(
                x=[f"J+{int(h)}" for h in tableau["horizon"]],
                y=tableau[scenario],
                name=scenario.capitalize(),
                marker={"color": couleur},
                hovertemplate="%{x} — " + scenario + " : %{y:,.0f}<extra></extra>",
            )
        )
    figure.add_trace(
        go.Scatter(
            x=[f"J+{int(h)}" for h in tableau["horizon"]],
            y=tableau["sans_relance"],
            name="Sans relance",
            mode="lines+markers",
            line={"color": "#64748b", "dash": "dash"},
            hovertemplate="Sans relance : %{y:,.0f}<extra></extra>",
        )
    )
    figure.update_layout(
        barmode="group", title="Encaissements attendus par scénario",
        yaxis_title=params.get("devise", "MAD"), height=340, **gabarit_graphique(params),
    )
    return figure


def graphique_composantes(facture: dict, params: dict) -> go.Figure:
    """Décomposition du score : d'où viennent les points."""
    composantes = facture.get("composantes") or {}
    libelles = {
        "retard": "Durée du retard",
        "montant": "Montant impayé",
        "historique": "Historique du client",
        "risque": "Risque de non-paiement",
    }
    cles = list(libelles)
    figure = go.Figure(
        go.Bar(
            x=[composantes.get(cle, 0) for cle in cles],
            y=[libelles[cle] for cle in cles],
            orientation="h",
            marker={"color": ["#dc2626", "#ea580c", "#ca8a04", "#0ea5e9"]},
            text=[f"{composantes.get(cle, 0):.0f} pts" for cle in cles],
            textposition="outside",
        )
    )
    figure.update_layout(
        title="Composition du score", height=230, xaxis_title="Points",
        xaxis={"range": [0, max(45, max(composantes.values(), default=0) * 1.35)]},
        **gabarit_graphique(params),
    )
    figure.update_layout(showlegend=False)
    return figure


def graphique_profils(cadre: pd.DataFrame, params: dict) -> go.Figure:
    """Répartition des clients par profil de paiement."""
    if cadre.empty:
        figure = go.Figure()
        figure.update_layout(height=260, **gabarit_graphique(params))
        return figure
    compte = cadre["profil_nom"].value_counts()
    figure = go.Figure(
        go.Pie(labels=compte.index, values=compte.values, hole=0.55, textinfo="label+value")
    )
    figure.update_layout(title="Profils de paiement", height=280, **gabarit_graphique(params))
    return figure


# ---------------------------------------------------------------------------
# Frise chronologique
# ---------------------------------------------------------------------------
def frise_html(facture: dict, params: dict) -> str:
    """Frise des cinq étapes : franchies, actuelle, à venir + compte à rebours."""
    seuils = config.seuils(params)
    etapes = scoring.etapes(facture, seuils)
    blocs = []
    for etape in etapes:
        couleur = etape["couleur"]
        if etape["etat"] == "passe":
            marque, style = "✅", f"--accent:{couleur}"
        elif etape["etat"] == "depasse":
            marque, style = "⏳", f"--accent:{couleur}"
        elif etape["etat"] == "actuel":
            marque, style = "👉", f"--accent:{couleur}"
        else:
            marque, style = "⬜", "--accent:#94a3b8"
        blocs.append(
            f'<div class="etape {etape["etat"]}" style="{style}">'
            f'<span class="nom">{marque} {etape["icone"]} {etape["nom"]}</span>'
            f'dès J+{etape["jours"]} — {etape["action"]}'
            f"{'<br><b>relance effectuée</b>' if etape['fait'] and etape['etat'] == 'passe' else ''}"
            "</div>"
        )
    return '<div class="frise">' + "".join(blocs) + "</div>"


def compte_a_rebond(facture: dict) -> str:
    """Phrase de compte à rebours avant le niveau suivant."""
    if facture.get("statut") == "payee":
        return "Dossier clôturé."
    restant = facture.get("jours_avant_prochain")
    if restant is None:
        return "Dernier niveau atteint : le dossier peut partir chez le conseil."
    nom = facture.get("prochain_niveau_nom")
    return f"Niveau « {nom} » dans <b>{restant} jour(s)</b> (le {date_courte(facture.get('prochaine_echeance'))})."


# ---------------------------------------------------------------------------
# Cartes cliquables des niveaux
# ---------------------------------------------------------------------------
def cartes_niveaux(cadre: pd.DataFrame, params: dict, cle_prefixe: str = "niv") -> str | None:
    """Cinq cartes cliquables ; renvoie le niveau sélectionné si clic."""
    compte = service.repartition_niveaux(cadre)
    colonnes = st.columns(5)
    selection = None
    for colonne, definition in zip(colonnes, config.NIVEAUX):
        code = definition["code"]
        sous_ensemble = cadre[cadre["niveau"] == code] if not cadre.empty else cadre
        total = float(sous_ensemble["montant"].sum()) if not sous_ensemble.empty else 0.0
        with colonne:
            st.markdown(
                f'<div class="carte-niveau" style="background:{definition["couleur"]}">'
                f'<div class="lib">{definition["icone"]} {definition["nom"]}</div>'
                f'<div class="nb">{compte.get(code, 0)}</div>'
                f'<div class="mt">{messages.formater_montant(total, params.get("devise", "MAD"))}</div>'
                "</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                f"Voir {definition['nom']}",
                key=f"{cle_prefixe}_{code}",
                width="stretch",
                disabled=compte.get(code, 0) == 0,
            ):
                selection = code
    return selection


def carte_synthese(titre: str, valeur: str, aide: str = "", delta: str | None = None) -> None:
    st.metric(titre, valeur, delta=delta, help=aide or None)


def ouvrir_fiche(facture_id: int, page=None) -> None:
    """Mémorise la facture choisie puis bascule sur la page « Fiche & message »."""
    st.session_state["facture_id"] = int(facture_id)
    if page is None:
        page = (st.session_state.get("_pages_") or {}).get("fiche")
    if page is not None:
        st.switch_page(page)
    else:  # repli si la navigation n'a pas exposé la page
        st.session_state["page_demandee"] = "fiche"
        st.rerun()


def legendes_priorite() -> None:
    puces = " ".join(
        f'<span class="badge" style="background:{s["couleur"]}">{s["libelle"]} · ≥ {s["valeur"]}</span>'
        for s in SEUILS_CRITIQUES
    )
    st.markdown(f'<div class="petit">{puces}</div>', unsafe_allow_html=True)
