"""Exports : journal PDF (la preuve), classeur Excel et CSV.

Le journal horodaté est la pièce maîtresse en cas de contentieux : il montre
qui a relancé, quand, par quel canal et avec quel message.
"""
from __future__ import annotations

import io
import unicodedata
from datetime import datetime

import pandas as pd

from . import config, messages


def _latin(texte) -> str:
    """Reportlab (Helvetica) n'encode pas l'arabe : on neutralise proprement."""
    if texte is None:
        return ""
    propre = str(texte).replace("\n", " — ")
    sortie = []
    for caractere in propre:
        if caractere.encode("latin-1", "ignore"):
            sortie.append(caractere)
        else:
            sortie.append("·")
    resultat = unicodedata.normalize("NFC", "".join(sortie))
    while "····" in resultat:
        resultat = resultat.replace("····", "·")
    return resultat


def _pied_de_page(canvas_obj, doc, params: dict) -> None:
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.setFillColorRGB(0.42, 0.45, 0.5)
    texte = (
        f"{params.get('societe', '')} — Journal des relances généré le "
        f"{datetime.now().strftime('%d/%m/%Y à %H:%M')} — page {doc.page}"
    )
    canvas_obj.drawString(40, 25, _latin(texte))
    canvas_obj.restoreState()


def journal_pdf(
    actions: list[dict],
    params: dict | None = None,
    facture: dict | None = None,
    periode: str = "",
) -> bytes:
    """Construit le PDF du journal horodaté (preuve de recouvrement)."""
    params = params or {}
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(
        tampon,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title="Journal des relances",
        author=params.get("societe", ""),
    )
    styles = getSampleStyleSheet()
    titre = ParagraphStyle("titre", parent=styles["Title"], fontSize=16, spaceAfter=4)
    sous_titre = ParagraphStyle("sous", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#475569"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=4)
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=8.5, leading=11)

    contenu = [
        Paragraph(_latin("Journal des relances"), titre),
        Paragraph(
            _latin(
                f"{params.get('societe', '')}"
                + (f" — ICE : {params.get('ice')}" if params.get("ice") else "")
                + (f" — {params.get('ville')}" if params.get("ville") else "")
            ),
            sous_titre,
        ),
    ]
    if facture:
        contenu.append(
            Paragraph(
                _latin(
                    f"Dossier : {facture.get('client')} — facture {facture.get('numero')} — "
                    f"{messages.formater_montant(facture.get('montant') or 0, params.get('devise', 'MAD'))}"
                ),
                sous_titre,
            )
        )
    contenu.append(
        Paragraph(
            _latin(
                f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
                + (f" — {periode}" if periode else "")
                + f" — {len(actions)} action(s) enregistrée(s)."
            ),
            sous_titre,
        )
    )
    contenu.append(Spacer(1, 8))
    contenu.append(
        Paragraph(
            _latin(
                "Ce journal constitue la preuve des démarches amiables effectuées : chaque ligne "
                "indique la date et l'heure, le niveau de traitement appliqué, le canal utilisé et "
                "le message adressé au client."
            ),
            normal,
        )
    )
    contenu.append(Spacer(1, 8))

    if not actions:
        contenu.append(Paragraph(_latin("Aucune action enregistrée."), normal))
    else:
        entetes = ["Date et heure", "Facture", "Client", "Niveau", "Canal", "Action", "Note"]
        donnees = [entetes]
        for action in actions:
            donnees.append(
                [
                    str(action.get("fait_le") or ""),
                    _latin(action.get("numero")),
                    _latin(action.get("client")),
                    _latin(config.niveau(action.get("niveau")).get("nom") or action.get("niveau")),
                    _latin(action.get("canal")),
                    _latin(action.get("action")),
                    _latin((action.get("note") or "")[:120]),
                ]
            )
        table = Table(donnees, colWidths=[26 * mm, 22 * mm, 34 * mm, 24 * mm, 18 * mm, 34 * mm, 16 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        contenu.append(table)

    messages_texte = [a for a in actions if a.get("message")]
    if messages_texte:
        contenu.append(Spacer(1, 12))
        contenu.append(Paragraph(_latin("Copie des messages adressés"), h2))
        for action in messages_texte[:40]:
            contenu.append(
                Paragraph(
                    _latin(
                        f"<b>{action.get('fait_le')} — {action.get('numero')} — "
                        f"{config.niveau(action.get('niveau')).get('nom')} :</b> {action.get('message')}"
                    ),
                    normal,
                )
            )
            contenu.append(Spacer(1, 5))

    contenu.append(Spacer(1, 16))
    contenu.append(
        Paragraph(
            _latin(
                "Fait pour servir et valoir ce que de droit. Ce document est généré "
                "automatiquement par l'application Scoring des Impayés à partir des données "
                "saisies par l'utilisateur."
            ),
            sous_titre,
        )
    )

    doc.build(contenu, onFirstPage=lambda c, d: _pied_de_page(c, d, params), onLaterPages=lambda c, d: _pied_de_page(c, d, params))
    return tampon.getvalue()


def factures_excel(factures: list[dict] | pd.DataFrame, params: dict | None = None) -> bytes:
    """Classeur Excel des factures, avec une feuille par vue utile."""
    params = params or {}
    cadre = factures if isinstance(factures, pd.DataFrame) else pd.DataFrame(factures)
    if cadre.empty:
        cadre = pd.DataFrame(columns=["numero", "client", "montant", "echeance", "jours_retard", "score", "niveau_nom"])
    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as classeur:
        cadre.to_excel(classeur, sheet_name="Factures", index=False)
        if "niveau_nom" in cadre.columns:
            synthese = (
                cadre.groupby("niveau_nom")
                .agg(factures=("numero", "count"), montant=("montant", "sum"))
                .reset_index()
                .rename(columns={"niveau_nom": "Niveau"})
            )
            synthese.to_excel(classeur, sheet_name="Synthèse par niveau", index=False)
    return tampon.getvalue()


def csv_bytes(cadre: pd.DataFrame) -> bytes:
    """CSV lisible par Excel francophone (séparateur point-virgule)."""
    return cadre.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def contexte_assistant(factures: list[dict], params: dict, stats: dict | None = None) -> dict:
    """Version compacte du portefeuille, transmise à l'assistant conversationnel."""
    factures_triees = sorted(
        [f for f in factures if f.get("statut") != "payee"],
        key=lambda f: -(f.get("score") or 0),
    )
    return {
        "societe": params.get("societe"),
        "devise": params.get("devise", "MAD"),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "synthese": stats or {},
        "factures": [
            {
                "numero": f.get("numero"),
                "client": f.get("client"),
                "montant": round(float(f.get("montant") or 0), 2),
                "echeance": str(f.get("echeance") or ""),
                "jours_retard": f.get("jours_retard"),
                "niveau": config.niveau(f.get("niveau")).get("nom"),
                "action_prevue": config.niveau(f.get("niveau")).get("action"),
                "score": f.get("score"),
                "proba_30j": f.get("p30"),
                "profil": f.get("profil_nom"),
                "telephone": f.get("telephone"),
            }
            for f in factures_triees[:60]
        ],
    }
