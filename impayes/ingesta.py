"""Import intelligent et détection d'anomalies.

Deux entrées possibles :

* un **tableau** (Excel, CSV) — colonnes devinées automatiquement, puis
  contrôlées avant insertion ;
* un **document** (PDF ou photo de facture) — extraction du texte, puis lecture
  par l'IA si elle est disponible, sinon par expressions régulières.

Rien n'est écrit en base sans que l'utilisateur ait vu et validé les anomalies.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime, timedelta

import pandas as pd

from . import config

# ---------------------------------------------------------------------------
# Lecture d'un tableau
# ---------------------------------------------------------------------------
def lire_tableau(fichier, nom: str | None = None) -> pd.DataFrame:
    """Lit un CSV/Excel et renvoie un DataFrame de chaînes."""
    donnees = fichier.read() if hasattr(fichier, "read") else fichier
    nom = (nom or getattr(fichier, "name", "") or "").lower()
    if nom.endswith((".xlsx", ".xlsm", ".xls")):
        feuilles = pd.read_excel(io.BytesIO(donnees), sheet_name=None)
        cadre = next(iter(feuilles.values())) if feuilles else pd.DataFrame()
    else:
        for encodage in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                cadre = pd.read_csv(
                    io.BytesIO(donnees), sep=None, engine="python", encoding=encodage
                )
                break
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        else:
            cadre = pd.read_csv(io.BytesIO(donnees), sep=";", encoding="latin-1")
    cadre.columns = [str(c).strip() for c in cadre.columns]
    return cadre


def _normaliser(nom: str) -> str:
    """Minuscule, sans accent, sans ponctuation : « N° Facture » → « n facture »."""
    nom = str(nom).strip().lower()
    remplacements = {
        "à": "a", "â": "a", "ä": "a", "é": "e", "è": "e", "ê": "e", "ë": "e",
        "î": "i", "ï": "i", "ô": "o", "ö": "o", "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "ñ": "n", "°": " ", "º": " ",
    }
    for origine, cible in remplacements.items():
        nom = nom.replace(origine, cible)
    nom = re.sub(r"[^a-z0-9]+", " ", nom)
    return re.sub(r"\s+", " ", nom).strip()


def deviner_mapping(colonnes) -> dict[str, str]:
    """Associe chaque champ attendu à une colonne du fichier, si possible."""
    normalisees = {_normaliser(c): c for c in colonnes}
    mapping: dict[str, str] = {}
    for champ, candidats in config.COLONNES_IMPORT.items():
        for candidat in candidats:
            candidat = _normaliser(candidat)
            if candidat in normalisees:
                mapping[champ] = normalisees[candidat]
                break
        if champ in mapping:
            continue
        # deuxième passe : correspondance partielle
        for cle, original in normalisees.items():
            if any(candidat in cle for candidat in [_normaliser(c) for c in candidats]):
                mapping[champ] = original
                break
    return mapping


# ---------------------------------------------------------------------------
# Conversion des valeurs
# ---------------------------------------------------------------------------
def parser_date(valeur) -> date | None:
    """Tolérant : objet date, chaîne jj/mm/aaaa, aaaa-mm-jj, nombre série Excel."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        # Numéro de série Excel (origine 1899-12-30)
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(valeur))).date()
        except (OverflowError, ValueError):
            return None
    texte = str(valeur).strip()
    if not texte:
        return None
    for format_ in (
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y/%m/%d", "%d/%m/%y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(texte[:19], format_).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(texte, dayfirst=True).date()
    except (ValueError, TypeError):
        return None


def parser_montant(valeur) -> float | None:
    """« 15 000,00 MAD », « 15,000.00 », « (2 500) » → nombre."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return None
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return float(valeur)
    texte = str(valeur).strip()
    if not texte:
        return None
    negatif = texte.startswith("(") and texte.endswith(")")
    texte = re.sub(r"[^\d,.\-]", "", texte)
    if not texte:
        return None
    if "," in texte and "." in texte:
        if texte.rfind(",") > texte.rfind("."):
            texte = texte.replace(".", "").replace(",", ".")
        else:
            texte = texte.replace(",", "")
    elif "," in texte:
        partie = texte.split(",")[-1]
        texte = texte.replace(",", "." if len(partie) <= 2 else "")
    try:
        valeur_num = float(texte)
    except ValueError:
        return None
    return -valeur_num if negatif else valeur_num


def parser_telephone(valeur) -> str | None:
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return None
    texte = str(valeur).strip()
    if texte.endswith(".0"):
        texte = texte[:-2]
    return texte or None


def parser_texte(valeur) -> str | None:
    """Texte nettoyé, ou ``None`` si la cellule est vide (NaN compris)."""
    if valeur is None:
        return None
    if isinstance(valeur, float) and pd.isna(valeur):
        return None
    texte = str(valeur).strip()
    return texte or None


# ---------------------------------------------------------------------------
# Préparation d'un import
# ---------------------------------------------------------------------------
CHAMPS_OBLIGATOIRES = ("client", "numero", "montant", "echeance")


def preparer_lignes(
    cadre: pd.DataFrame, mapping: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Transforme un DataFrame en lignes prêtes pour la base.

    :returns: ``(lignes, rejets)`` — les rejets portent la raison du refus.
    """
    lignes: list[dict] = []
    rejets: list[dict] = []
    for position, (_, ligne) in enumerate(cadre.iterrows(), start=2):  # ligne 1 = en-têtes
        brute = {champ: ligne.get(colonne) for champ, colonne in mapping.items()}
        if all(
            brute.get(champ) is None or str(brute.get(champ)).strip() == ""
            for champ in CHAMPS_OBLIGATOIRES
        ):
            continue  # ligne vide

        client = parser_texte(brute.get("client")) or ""
        numero = parser_texte(brute.get("numero")) or ""
        if numero.endswith(".0"):
            numero = numero[:-2]
        montant = parser_montant(brute.get("montant"))
        echeance = parser_date(brute.get("echeance"))
        date_emission = parser_date(brute.get("date_emission"))
        nb_retards = parser_montant(brute.get("nb_retards_passes")) or 0

        raisons = []
        if not client:
            raisons.append("client manquant")
        if not numero:
            raisons.append("numéro de facture manquant")
        if montant is None or montant <= 0:
            raisons.append("montant illisible ou nul")
        if echeance is None:
            raisons.append("échéance illisible")
        if raisons:
            rejets.append({"ligne": position, "client": client, "numero": numero, "raison": ", ".join(raisons)})
            continue

        lignes.append(
            {
                "client": client,
                "numero": numero,
                "montant": montant,
                "echeance": echeance,
                "date_emission": date_emission,
                "telephone": parser_telephone(brute.get("telephone")),
                "email": parser_texte(brute.get("email")),
                "nb_retards_passes": int(nb_retards),
                "statut": "impayee",
                "source": "import",
            }
        )
    return lignes, rejets


# ---------------------------------------------------------------------------
# Détection d'anomalies
# ---------------------------------------------------------------------------
GRAVITES = {"bloquant": "🔴", "attention": "🟠", "info": "🔵"}


def detecter_anomalies(
    lignes: list[dict],
    factures_existantes: list[dict] | None = None,
    params: dict | None = None,
) -> list[dict]:
    """Signale doublons, montants inhabituels, échéances incohérentes, contacts manquants.

    Chaque anomalie renvoie ``{niveau, type, message, ligne, index}`` où ``index``
    est la position dans la liste analysée (pour permettre sa suppression).
    """
    params = params or {}
    factures_existantes = factures_existantes or []
    anomalies: list[dict] = []
    aujourdhui = date.today()

    # Doublons internes au fichier
    numeros_vus: dict[str, int] = {}
    combos_vus: dict[tuple, int] = {}
    for index, ligne in enumerate(lignes):
        numero = (ligne.get("numero") or "").strip().lower()
        if numero and numero in numeros_vus:
            anomalies.append(
                {
                    "niveau": "bloquant",
                    "type": "doublon_fichier",
                    "ligne": index + 2,
                    "index": index,
                    "message": (
                        f"Doublon dans le fichier : la facture {ligne.get('numero')} apparaît "
                        f"aux lignes {numeros_vus[numero] + 2} et {index + 2}."
                    ),
                }
            )
        elif numero:
            numeros_vus[numero] = index

        combo = (
            (ligne.get("client") or "").lower(),
            round(float(ligne.get("montant") or 0), 2),
            str(ligne.get("echeance") or ""),
        )
        if combo in combos_vus:
            anomalies.append(
                {
                    "niveau": "attention",
                    "type": "doublon_probable",
                    "ligne": index + 2,
                    "index": index,
                    "message": (
                        f"Même client, même montant et même échéance qu'une autre ligne du fichier "
                        f"(ligne {combos_vus[combo] + 2}) : vérifiez qu'il ne s'agit pas d'un doublon."
                    ),
                }
            )
        else:
            combos_vus[combo] = index

    # Doublons avec la base
    numeros_base = {(f.get("numero") or "").lower() for f in factures_existantes if f.get("statut") != "payee"}
    combos_base = {
        (
            (f.get("client") or "").lower(),
            round(float(f.get("montant") or 0), 2),
            str(f.get("echeance") or ""),
        )
        for f in factures_existantes
        if f.get("statut") != "payee"
    }
    for index, ligne in enumerate(lignes):
        if (ligne.get("numero") or "").lower() in numeros_base:
            anomalies.append(
                {
                    "niveau": "bloquant",
                    "type": "doublon_base",
                    "ligne": index + 2,
                    "index": index,
                    "message": f"La facture {ligne.get('numero')} existe déjà en base et n'est pas payée.",
                }
            )
        combo = (
            (ligne.get("client") or "").lower(),
            round(float(ligne.get("montant") or 0), 2),
            str(ligne.get("echeance") or ""),
        )
        if combo in combos_base:
            anomalies.append(
                {
                    "niveau": "attention",
                    "type": "doublon_probable",
                    "ligne": index + 2,
                    "index": index,
                    "message": (
                        f"Même client, même montant et même échéance qu'une facture déjà en base "
                        f"({ligne.get('client')} — {ligne.get('montant')})."
                    ),
                }
            )

    # Montants inhabituels (par client, sinon global)
    par_client: dict[str, list[float]] = {}
    for facture in factures_existantes:
        par_client.setdefault((facture.get("client") or "").lower(), []).append(
            float(facture.get("montant") or 0)
        )
    tous = [m for liste in par_client.values() for m in liste] or [
        float(l.get("montant") or 0) for l in lignes
    ]
    if tous:
        serie = pd.Series(tous)
        mediane = float(serie.median())
        ecart = float(serie.std(ddof=0)) or 1.0
        facteur = float(params.get("seuil_anomalie_montant", 3.0))
        for index, ligne in enumerate(lignes):
            montant = float(ligne.get("montant") or 0)
            reference = par_client.get((ligne.get("client") or "").lower()) or tous
            mediane_ref = float(pd.Series(reference).median()) if reference else mediane
            if montant > 0 and (montant - mediane) / ecart > facteur:
                anomalies.append(
                    {
                        "niveau": "attention",
                        "type": "montant_inhabituel",
                        "ligne": index + 2,
                        "index": index,
                        "message": (
                            f"Montant inhabituellement élevé : {montant:,.2f}".replace(",", " ")
                            + f" alors que la médiane du client est de {mediane_ref:,.2f}".replace(",", " ")
                            + ". Vérifiez la saisie."
                        ),
                    }
                )
            if montant <= 0:
                anomalies.append(
                    {
                        "niveau": "bloquant",
                        "type": "montant_nul",
                        "ligne": index + 2,
                        "index": index,
                        "message": "Montant nul ou négatif.",
                    }
                )

    # Échéances incohérentes
    for index, ligne in enumerate(lignes):
        echeance = ligne.get("echeance")
        emission = ligne.get("date_emission")
        if echeance is None:
            continue
        if emission and echeance < emission:
            anomalies.append(
                {
                    "niveau": "bloquant",
                    "type": "echeance_avant_emission",
                    "ligne": index + 2,
                    "index": index,
                    "message": f"Échéance ({echeance}) antérieure à la date de facture ({emission}).",
                }
            )
        elif echeance < aujourdhui - timedelta(days=730):
            anomalies.append(
                {
                    "niveau": "attention",
                    "type": "echeance_tres_ancienne",
                    "ligne": index + 2,
                    "index": index,
                    "message": f"Échéance de plus de deux ans ({echeance}) : créance probablement prescrite ou déjà traitée.",
                }
            )
        elif echeance > aujourdhui + timedelta(days=365 * 3):
            anomalies.append(
                {
                    "niveau": "info",
                    "type": "echeance_lointaine",
                    "ligne": index + 2,
                    "index": index,
                    "message": f"Échéance très lointaine ({echeance}) : à confirmer.",
                }
            )

    # Coordonnées manquantes
    for index, ligne in enumerate(lignes):
        if not ligne.get("telephone") and not ligne.get("email"):
            anomalies.append(
                {
                    "niveau": "info",
                    "type": "coordonnees_manquantes",
                    "ligne": index + 2,
                    "index": index,
                    "message": f"Aucun téléphone ni email pour {ligne.get('client')} : les relances automatiques seront impossibles.",
                }
            )
    return anomalies


# ---------------------------------------------------------------------------
# Documents (PDF / photo)
# ---------------------------------------------------------------------------
def texte_pdf(fichier) -> str:
    """Extrait le texte d'un PDF texte (pas d'OCR : une photo utilise l'IA)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    donnees = fichier.read() if hasattr(fichier, "read") else fichier
    try:
        lecteur = PdfReader(io.BytesIO(donnees))
        return "\n".join((page.extract_text() or "") for page in lecteur.pages).strip()
    except Exception:
        return ""


MOTIFS = {
    "numero": [
        r"(?:facture|invoice|n[°o]?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/_]{2,})",
    ],
    "montant": [
        r"(?:montant|total|net\s+à\s+payer|amount|ttc)\s*[:]?\s*([\d\s.,]{3,})\s*(?:mad|dh|dirham|mads?|eur|usd|\$|€)?",
    ],
    "echeance": [
        r"(?:échéance|echeance|due\s+date|à\s+régler\s+avant)\s*[:]?\s*(\d{2}[/\-.]\d{2}[/\-.]\d{2,4})",
    ],
    "date_emission": [
        r"(?:date\s+facture|date\s+d'?émission|invoice\s+date|le)\s*[:]?\s*(\d{2}[/\-.]\d{2}[/\-.]\d{2,4})",
    ],
    "telephone": [r"(\+?\d[\d\s.\-]{7,14}\d)"],
    "email": [r"([\w.\-+]+@[\w.\-]+\.\w+)"],
}


def extraire_par_regles(texte: str) -> dict:
    """Lecture « à l'ancienne » d'un texte de facture, quand l'IA n'est pas active."""
    resultat: dict = {}
    plat = re.sub(r"[ \t]+", " ", texte or "")
    for champ, motifs in MOTIFS.items():
        for motif in motifs:
            trouve = re.search(motif, plat, flags=re.IGNORECASE)
            if trouve:
                resultat[champ] = trouve.group(1).strip()
                break
    # Le nom du client : première ligne qui ressemble à une raison sociale
    for ligne in (texte or "").splitlines():
        ligne = ligne.strip()
        if 3 < len(ligne) < 60 and re.search(r"(SARL|S\.A\.R\.L|SA|SAS|SNC|ETS|STE|Établissement|École|Clinique|Cabinet|SARL AU)", ligne, re.IGNORECASE):
            resultat["client"] = ligne
            break
    return resultat


def facture_depuis_regles(texte: str) -> list[dict]:
    """Convertit une lecture par règles en ligne d'import exploitable."""
    brut = extraire_par_regles(texte)
    return [
        {
            "client": brut.get("client"),
            "numero": brut.get("numero"),
            "montant": parser_montant(brut.get("montant")),
            "echeance": parser_date(brut.get("echeance")),
            "date_emission": parser_date(brut.get("date_emission")),
            "telephone": parser_telephone(brut.get("telephone")),
            "email": brut.get("email"),
            "a_verifier": True,
        }
    ]
