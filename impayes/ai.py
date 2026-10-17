"""La couche intelligence artificielle (API Claude), entièrement optionnelle.

Principe de conception : **l'application ne dépend jamais de l'IA pour
fonctionner**. Chaque fonction renvoie ``None`` en cas d'absence de clé, de
réseau ou d'erreur ; l'appelant retombe alors sur le moteur local
(:mod:`impayes.messages`, :mod:`impayes.prediction`).

Confidentialité : seules les informations strictement nécessaires au message
sont transmises (nom du client, montant, dates, historique de relances). Rien
n'est envoyé sans action de l'utilisateur.
"""
from __future__ import annotations

import base64
import json
import os
import re

MODELES_CONNUS = [
    "claude-sonnet-4-5",
    "claude-opus-4-1",
    "claude-haiku-4-5",
    "claude-3-7-sonnet-latest",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-latest",
]

SYSTEME = (
    "Tu es l'assistant recouvrement d'une PME marocaine. Tu écris en français, "
    "en anglais ou en arabe selon la demande. Tes messages sont courts, factuels, "
    "courtois, sans menace ni jugement, et toujours prêts à être copiés-collés. "
    "Tu n'inventes jamais un montant, une date ou une référence : tu n'utilises que "
    "les données fournies. Tu ne promets aucune action juridique de ta part."
)


# ---------------------------------------------------------------------------
# Disponibilité
# ---------------------------------------------------------------------------
def cle_api(params: dict | None = None) -> str:
    """Clé API : celle des réglages, sinon la variable d'environnement."""
    params = params or {}
    return (params.get("ia_cle_api") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def bibliotheque_presente() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def disponible(params: dict | None = None) -> bool:
    """L'IA générative est-elle utilisable en l'état ?"""
    params = params or {}
    if str(params.get("ia_actif", "1")) not in ("1", "True", "true"):
        return False
    return bool(cle_api(params)) and bibliotheque_presente()


def etat(params: dict | None = None) -> dict:
    """Diagnostic affiché dans les réglages."""
    params = params or {}
    if str(params.get("ia_actif", "1")) not in ("1", "True", "true"):
        return {"actif": False, "raison": "L'IA est désactivée dans les réglages.", "niveau": "info"}
    if not bibliotheque_presente():
        return {
            "actif": False,
            "raison": "Le paquet `anthropic` n'est pas installé : `pip install anthropic`.",
            "niveau": "warning",
        }
    if not cle_api(params):
        return {
            "actif": False,
            "raison": "Aucune clé API : l'application utilise ses modèles de messages intégrés (elle fonctionne entièrement).",
            "niveau": "info",
        }
    return {
        "actif": True,
        "raison": f"IA active — modèle `{params.get('ia_modele') or MODELES_CONNUS[0]}`.",
        "niveau": "success",
    }


def _client(params: dict):
    from anthropic import Anthropic

    return Anthropic(api_key=cle_api(params), max_retries=1, timeout=45.0)


def _texte(reponse) -> str:
    morceaux = []
    for bloc in getattr(reponse, "content", []) or []:
        texte = getattr(bloc, "text", None)
        if texte:
            morceaux.append(texte)
    return "\n".join(morceaux).strip()


def _demander(
    invite: str,
    params: dict,
    systeme: str = SYSTEME,
    max_tokens: int = 1200,
    contenu_multimodal: list | None = None,
    json_attendu: bool = False,
) -> str | None:
    """Appel unique et défensif à l'API. ``None`` si quoi que ce soit échoue."""
    if not disponible(params):
        return None
    contenu = contenu_multimodal or invite
    try:
        client = _client(params)
        reponse = client.messages.create(
            model=params.get("ia_modele") or MODELES_CONNUS[0],
            max_tokens=max_tokens,
            system=systeme + (" Réponds uniquement par du JSON valide." if json_attendu else ""),
            messages=[{"role": "user", "content": contenu}],
        )
        texte = _texte(reponse)
        return texte or None
    except Exception:  # réseau, quota, modèle inconnu : on ne casse jamais l'app
        return None


def _extraire_json(texte: str | None):
    """Récupère le premier objet/tableau JSON d'une réponse de modèle."""
    if not texte:
        return None
    texte = texte.strip()
    if texte.startswith("```"):
        texte = re.sub(r"^```[a-zA-Z]*\n?", "", texte)
        texte = re.sub(r"```$", "", texte).strip()
    for debut, fin in (("[", "]"), ("{", "}")):
        i, j = texte.find(debut), texte.rfind(fin)
        if i != -1 and j > i:
            candidat = texte[i : j + 1]
            try:
                return json.loads(candidat)
            except json.JSONDecodeError:
                continue
    return None


# ---------------------------------------------------------------------------
# 4.3 — Rédaction des messages
# ---------------------------------------------------------------------------
def rediger_message(
    facture: dict,
    niveau_nom: str,
    canal: str,
    ton: str,
    langue: str,
    brouillon: str,
    params: dict,
    profil: str | None = None,
    conseil_profil: str | None = None,
) -> str | None:
    """Réécrit le message local en l'adaptant au profil et à l'historique du client."""
    langues = {"fr": "français", "en": "anglais", "ar": "arabe"}
    invite = f"""Rédige le message de recouvrement ci-dessous, prêt à envoyer.

Contexte
- Entreprise créancière : {params.get('societe')}
- Client : {facture.get('client')}
- Facture : {facture.get('numero')} — {facture.get('montant')} {params.get('devise', 'MAD')}
- Échéance : {facture.get('echeance')}
- Jours de retard : {facture.get('jours_retard')}
- Niveau de traitement : {niveau_nom}
- Canal prévu : {canal}
- Ton demandé : {ton} (bienveillant = compréhensif, neutre = professionnel, ferme = direct et sans ambiguïté)
- Profil du client : {profil or 'inconnu'}{(' — ' + conseil_profil) if conseil_profil else ''}
- Probabilité de paiement à 30 jours : {(facture.get('proba_30') or 0) * 100:.0f} %
- Nombre de relances déjà effectuées : {facture.get('nb_relances', 0)}

Contraintes
- Écris en {langues.get(langue, 'français')}.
- Conserve TOUS les faits du brouillon : montant, référence de facture, dates, délai accordé.
- Adapte la longueur au canal ({canal}) : un texto reste court ; une mise en demeure est formelle et complète.
- Ne menace pas, n'invente rien, et n'ajoute pas de mention juridique absente du brouillon.
- Réponds uniquement avec le message final, sans commentaire ni balise.

Brouillon de référence
---
{brouillon}
---"""
    return _demander(invite, params, max_tokens=1500)


# ---------------------------------------------------------------------------
# 4.4 — Meilleure action suivante
# ---------------------------------------------------------------------------
def recommander_action(
    facture: dict,
    niveau_nom: str,
    profil: str,
    statistiques: dict,
    historique: list[dict],
    params: dict,
) -> dict | None:
    """Suggère la prochaine étape optimale, avec sa justification."""
    historique_texte = "\n".join(
        f"- {a.get('fait_le')} : {a.get('action')} ({a.get('canal') or '—'})" for a in historique[:8]
    ) or "- aucune action enregistrée"
    invite = f"""Tu conseilles une PME marocaine sur le recouvrement amiable d'une créance.

Dossier
- Client : {facture.get('client')} — profil : {profil}
- Facture {facture.get('numero')} : {facture.get('montant')} {params.get('devise', 'MAD')}, échéance {facture.get('echeance')}, {facture.get('jours_retard')} jours de retard
- Niveau procédural atteint : {niveau_nom}
- Probabilité de paiement à 7 / 15 / 30 jours : {(facture.get('p7') or 0) * 100:.0f} % / {(facture.get('p15') or 0) * 100:.0f} % / {(facture.get('p30') or 0) * 100:.0f} %
- Historique du client : {json.dumps(statistiques, ensure_ascii=False)}
- Relances déjà effectuées :
{historique_texte}

Réponds en JSON : {{"action": "l'action concrète à mener (une phrase à l'impératif)", "raison": "pourquoi, en une phrase appuyée sur les données", "canal": "sms|appel|email|courrier|avocat", "alternative": "la solution de repli (échéancier, remise...)"}}"""
    reponse = _demander(invite, params, max_tokens=700, json_attendu=True)
    donnees = _extraire_json(reponse)
    if isinstance(donnees, dict) and donnees.get("action"):
        return donnees
    return None


# ---------------------------------------------------------------------------
# 4.6 — Briefing quotidien
# ---------------------------------------------------------------------------
def briefing_quotidien(donnees: dict, params: dict) -> str | None:
    """Résume la journée de recouvrement en quelques lignes."""
    invite = f"""Rédige le briefing de recouvrement du matin pour {params.get('societe')}.

Données du jour ({donnees.get('date')})
- Montant total impayé : {donnees.get('total_impaye')} {params.get('devise', 'MAD')}
- Factures en retard : {donnees.get('nb_retard')} (dont {donnees.get('nb_nouveaux')} nouvelles en retard aujourd'hui)
- Retard moyen : {donnees.get('retard_moyen')} jours
- Répartition par niveau : {json.dumps(donnees.get('repartition', {}), ensure_ascii=False)}
- Factures changeant de niveau aujourd'hui : {json.dumps(donnees.get('changements', []), ensure_ascii=False)}
- Top 3 des urgences : {json.dumps(donnees.get('top', []), ensure_ascii=False)}
- Encaissement attendu sous 30 jours : {donnees.get('encaissement_30j')} {params.get('devise', 'MAD')}
- Risques à surveiller : {json.dumps(donnees.get('risques', []), ensure_ascii=False)}

Contraintes : 5 à 8 lignes maximum, en français, ton professionnel et direct, avec des
puces. Commence par le nombre d'actions du jour. Termine par la priorité numéro un.
Pas de titre, pas de conclusion pompeuse, aucun fait inventé."""
    return _demander(invite, params, max_tokens=800)


# ---------------------------------------------------------------------------
# 4.5 — Assistant conversationnel
# ---------------------------------------------------------------------------
def assistant_conversation(
    question: str,
    contexte: dict,
    params: dict,
    historique: list[dict] | None = None,
) -> str | None:
    """Répond à une question libre, en s'appuyant sur les données du portefeuille."""
    messages = list(historique or [])[-6:]
    bloc_contexte = json.dumps(contexte, ensure_ascii=False, default=str)[:12000]
    invite = (
        "Voici l'état du portefeuille d'impayés, en JSON :\n"
        f"{bloc_contexte}\n\n"
        f"Question de l'utilisateur : {question}\n\n"
        "Réponds en français, en 2 à 6 lignes, en t'appuyant uniquement sur ces données. "
        "Si une information manque, dis-le et indique où la saisir. "
        "Utilise le format monétaire marocain (1 234,56 MAD) et des dates jj/mm/aaaa. "
        "Si on te demande un échéancier ou un message, propose directement le texte à envoyer."
    )
    return _demander(invite, params, max_tokens=900)


# ---------------------------------------------------------------------------
# 4.7 — Extraction depuis un document
# ---------------------------------------------------------------------------
def extraire_facture_document(
    texte: str | None,
    params: dict,
    image_base64: str | None = None,
    media_type: str | None = None,
) -> list[dict] | None:
    """Extrait les factures d'un PDF (texte) ou d'une photo (image)."""
    consigne = (
        "Extrais toutes les factures présentes dans ce document. "
        "Réponds en JSON : une liste d'objets avec les clés "
        '"client", "numero", "montant", "devise", "echeance" (AAAA-MM-JJ), '
        '"date_emission" (AAAA-MM-JJ ou null), "telephone", "email". '
        "N'invente rien : mets null quand l'information est absente."
    )
    if image_base64 and media_type:
        contenu = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": image_base64},
            },
            {"type": "text", "text": consigne},
        ]
        reponse = _demander(consigne, params, contenu_multimodal=contenu, max_tokens=1500, json_attendu=True)
    else:
        invite = f"{consigne}\n\nDocument :\n---\n{(texte or '')[:20000]}\n---"
        reponse = _demander(invite, params, max_tokens=1500, json_attendu=True)
    donnees = _extraire_json(reponse)
    if isinstance(donnees, dict):
        donnees = donnees.get("factures") or [donnees]
    if isinstance(donnees, list):
        return [d for d in donnees if isinstance(d, dict)]
    return None


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------
def tester_connexion(params: dict) -> tuple[bool, str]:
    """Bouton « Tester la connexion » des réglages."""
    if not bibliotheque_presente():
        return False, "Le paquet `anthropic` n'est pas installé (`pip install anthropic`)."
    if not cle_api(params):
        return False, "Aucune clé API renseignée."
    texte = _demander("Réponds exactement : connexion OK", params, max_tokens=32)
    if texte:
        return True, f"Connexion réussie — réponse du modèle : « {texte.strip()[:80]} »"
    return False, "Échec de l'appel : vérifie la clé, le nom du modèle et la connexion réseau."
