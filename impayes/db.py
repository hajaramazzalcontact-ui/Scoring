"""Couche de persistance SQLite.

Trois familles de données :

* ``params``  : réglages de l'application (clé/valeur).
* ``factures`` : les créances à suivre.
* ``actions``  : le journal horodaté — la preuve des relances.
* ``reglements`` : l'historique des factures déjà payées, utilisé comme
  jeu d'entraînement par le modèle de prédiction.
* ``clients`` : coordonnées et notes par client.

Aucun serveur à installer : tout vit dans ``data/impayes.db``.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from . import config

# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------
CHEMIN_DB = Path(os.environ.get("IMPAYES_DB", config.DOSSIER_DATA / "impayes.db"))


def chemin_base() -> Path:
    """Chemin du fichier SQLite utilisé (affiché dans les réglages)."""
    return CHEMIN_DB


@contextmanager
def connexion():
    """Ouvre une connexion, commit en sortie, ferme toujours."""
    CHEMIN_DB.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(CHEMIN_DB, timeout=15)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA foreign_keys = ON")
    try:
        yield cx
        cx.commit()
    finally:
        cx.close()


def _iso(d) -> str | None:
    """Convertit une date/datetime en chaîne ISO (ou None)."""
    if d is None or d == "":
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    texte = str(d).strip()
    return texte[:10] if texte else None


def _date(v) -> date | None:
    """Convertit une valeur stockée en ``date`` Python."""
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _horodatage() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS params (
    cle     TEXT PRIMARY KEY,
    valeur  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factures (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    numero             TEXT NOT NULL,
    client             TEXT NOT NULL,
    montant            REAL NOT NULL DEFAULT 0,
    date_emission      TEXT,
    echeance           TEXT NOT NULL,
    telephone          TEXT,
    email              TEXT,
    nb_retards_passes  INTEGER NOT NULL DEFAULT 0,
    statut             TEXT NOT NULL DEFAULT 'impayee',
    date_paiement      TEXT,
    montant_paye       REAL,
    date_promesse      TEXT,
    notes              TEXT,
    source             TEXT,
    cree_le            TEXT NOT NULL,
    maj_le             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_factures_statut ON factures(statut);
CREATE INDEX IF NOT EXISTS idx_factures_client ON factures(client);
CREATE INDEX IF NOT EXISTS idx_factures_echeance ON factures(echeance);

CREATE TABLE IF NOT EXISTS actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    facture_id  INTEGER,
    numero      TEXT,
    client      TEXT,
    niveau      TEXT,
    canal       TEXT,
    ton         TEXT,
    langue      TEXT,
    action      TEXT NOT NULL,
    message     TEXT,
    note        TEXT,
    utilisateur TEXT,
    fait_le     TEXT NOT NULL,
    FOREIGN KEY (facture_id) REFERENCES factures(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_facture ON actions(facture_id);
CREATE INDEX IF NOT EXISTS idx_actions_date ON actions(fait_le);

CREATE TABLE IF NOT EXISTS reglements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client       TEXT NOT NULL,
    numero       TEXT,
    montant      REAL NOT NULL,
    echeance     TEXT NOT NULL,
    date_paiement TEXT NOT NULL,
    jours_retard INTEGER NOT NULL DEFAULT 0,
    montant_paye REAL,
    source       TEXT
);
CREATE INDEX IF NOT EXISTS idx_reglements_client ON reglements(client);

CREATE TABLE IF NOT EXISTS clients (
    nom        TEXT PRIMARY KEY,
    telephone  TEXT,
    email      TEXT,
    segment    TEXT,
    notes      TEXT,
    maj_le     TEXT
);
"""


def init_db() -> None:
    """Crée les tables si besoin. Idempotent."""
    with connexion() as cx:
        cx.executescript(SCHEMA)
    # Trace « journal d'accueil » pour la première ouverture
    if not lire_params(brut=True):
        ecrire_params({}, creer_uniquement=True)


# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------
def _decoder(valeur: str):
    try:
        return json.loads(valeur)
    except (TypeError, ValueError):
        return valeur


def lire_params(brut: bool = False) -> dict:
    """Renvoie les réglages, complétés par les valeurs par défaut.

    ``brut=True`` renvoie uniquement ce qui est réellement stocké (utilisé pour
    détecter une base neuve).
    """
    with connexion() as cx:
        lignes = cx.execute("SELECT cle, valeur FROM params").fetchall()
    stockes = {row["cle"]: _decoder(row["valeur"]) for row in lignes}
    if brut:
        return stockes
    params = dict(config.DEFAUT_PARAMS)
    params.update(stockes)
    return params


def ecrire_params(params: dict, creer_uniquement: bool = False) -> None:
    """Écrit (ou met à jour) un ensemble de réglages."""
    if creer_uniquement and params == {}:
        with connexion() as cx:
            cx.execute(
                "INSERT OR REPLACE INTO params (cle, valeur) VALUES (?, ?)",
                ("societe", json.dumps(config.DEFAUT_PARAMS["societe"], ensure_ascii=False)),
            )
        return
    with connexion() as cx:
        for cle, valeur in params.items():
            cx.execute(
                "INSERT OR REPLACE INTO params (cle, valeur) VALUES (?, ?)",
                (cle, json.dumps(valeur, ensure_ascii=False)),
            )


def maj_param(cle: str, valeur) -> None:
    ecrire_params({cle: valeur})


def reinitialiser_params() -> None:
    with connexion() as cx:
        cx.execute("DELETE FROM params")


# ---------------------------------------------------------------------------
# Factures
# ---------------------------------------------------------------------------
CHAMPS_FACTURE = (
    "numero",
    "client",
    "montant",
    "date_emission",
    "echeance",
    "telephone",
    "email",
    "nb_retards_passes",
    "statut",
    "date_paiement",
    "montant_paye",
    "date_promesse",
    "notes",
    "source",
)


def _normaliser_facture(donnees: dict) -> dict:
    """Nettoie un dict destiné à la table ``factures``."""
    propre: dict = {}
    for champ in CHAMPS_FACTURE:
        if champ not in donnees:
            continue
        valeur = donnees[champ]
        if champ in ("date_emission", "echeance", "date_paiement", "date_promesse"):
            valeur = _iso(valeur)
        elif champ == "montant":
            valeur = float(valeur or 0)
        elif champ in ("montant_paye",):
            valeur = None if valeur in (None, "") else float(valeur)
        elif champ == "nb_retards_passes":
            valeur = int(valeur or 0)
        elif champ in ("telephone", "email", "notes", "source"):
            valeur = (str(valeur).strip() or None) if valeur is not None else None
        propre[champ] = valeur
    return propre


def ajouter_facture(donnees: dict) -> int:
    """Insère une facture et renvoie son identifiant."""
    propre = _normaliser_facture(donnees)
    propre.setdefault("statut", "impayee")
    propre.setdefault("montant", 0.0)
    maintenant = _horodatage()
    colonnes = list(propre.keys()) + ["cree_le", "maj_le"]
    valeurs = list(propre.values()) + [maintenant, maintenant]
    sql = (
        f"INSERT INTO factures ({', '.join(colonnes)}) "
        f"VALUES ({', '.join('?' for _ in colonnes)})"
    )
    with connexion() as cx:
        cur = cx.execute(sql, valeurs)
        identifiant = int(cur.lastrowid)
    _enregistrer_client(propre.get("client"), propre.get("telephone"), propre.get("email"))
    return identifiant


def ajouter_factures(lignes: list[dict]) -> list[int]:
    """Insertion en lot (import) — plus rapide, une seule transaction."""
    ids: list[int] = []
    maintenant = _horodatage()
    with connexion() as cx:
        for ligne in lignes:
            propre = _normaliser_facture(ligne)
            propre.setdefault("statut", "impayee")
            propre.setdefault("montant", 0.0)
            colonnes = list(propre.keys()) + ["cree_le", "maj_le"]
            valeurs = list(propre.values()) + [maintenant, maintenant]
            sql = (
                f"INSERT INTO factures ({', '.join(colonnes)}) "
                f"VALUES ({', '.join('?' for _ in colonnes)})"
            )
            ids.append(int(cx.execute(sql, valeurs).lastrowid))
    return ids


def maj_facture(facture_id: int, **champs) -> None:
    propre = _normaliser_facture(champs)
    if not propre:
        return
    propre["maj_le"] = _horodatage()
    affectations = ", ".join(f"{c} = ?" for c in propre)
    with connexion() as cx:
        cx.execute(
            f"UPDATE factures SET {affectations} WHERE id = ?",
            list(propre.values()) + [int(facture_id)],
        )


def supprimer_facture(facture_id: int) -> None:
    with connexion() as cx:
        cx.execute("DELETE FROM factures WHERE id = ?", (int(facture_id),))


def supprimer_tout() -> None:
    """Vide factures, actions, règlements et clients (les réglages restent)."""
    with connexion() as cx:
        for table in ("actions", "factures", "reglements", "clients"):
            cx.execute(f"DELETE FROM {table}")


def lister_factures(statut: str | None = None) -> list[dict]:
    """Liste les factures, dates converties en objets ``date``."""
    sql = "SELECT * FROM factures"
    args: tuple = ()
    if statut:
        sql += " WHERE statut = ?"
        args = (statut,)
    sql += " ORDER BY echeance ASC, id ASC"
    with connexion() as cx:
        lignes = cx.execute(sql, args).fetchall()
    return [_facture_depuis_row(row) for row in lignes]


def obtenir_facture(facture_id: int) -> dict | None:
    with connexion() as cx:
        row = cx.execute("SELECT * FROM factures WHERE id = ?", (int(facture_id),)).fetchone()
    return _facture_depuis_row(row) if row else None


def _facture_depuis_row(row: sqlite3.Row) -> dict:
    facture = dict(row)
    for champ in ("echeance", "date_emission", "date_paiement", "date_promesse"):
        facture[champ] = _date(facture.get(champ))
    return facture


def numero_existe(numero: str, ignorer_id: int | None = None) -> bool:
    """Un numéro de facture déjà présent et non payé ?"""
    sql = "SELECT COUNT(*) AS n FROM factures WHERE statut != 'payee' AND LOWER(numero) = LOWER(?)"
    args: list = [numero]
    if ignorer_id:
        sql += " AND id != ?"
        args.append(int(ignorer_id))
    with connexion() as cx:
        return int(cx.execute(sql, args).fetchone()["n"]) > 0


def clients_connus() -> list[str]:
    with connexion() as cx:
        lignes = cx.execute(
            "SELECT DISTINCT client FROM factures ORDER BY client COLLATE NOCASE"
        ).fetchall()
    return [row["client"] for row in lignes if row["client"]]


# ---------------------------------------------------------------------------
# Journal des actions (preuves)
# ---------------------------------------------------------------------------
def journaliser(
    action: str,
    facture: dict | None = None,
    niveau: str | None = None,
    canal: str | None = None,
    ton: str | None = None,
    langue: str | None = None,
    message: str | None = None,
    note: str | None = None,
    utilisateur: str | None = None,
    fait_le: str | None = None,
    facture_id: int | None = None,
    numero: str | None = None,
    client: str | None = None,
) -> int:
    """Ajoute une ligne au journal horodaté."""
    if facture:
        facture_id = facture_id or facture.get("id")
        numero = numero or facture.get("numero")
        client = client or facture.get("client")
    with connexion() as cx:
        cur = cx.execute(
            """INSERT INTO actions
               (facture_id, numero, client, niveau, canal, ton, langue,
                action, message, note, utilisateur, fait_le)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                facture_id,
                numero,
                client,
                niveau,
                canal,
                ton,
                langue,
                action,
                message,
                note,
                utilisateur or os.environ.get("USERNAME") or "utilisateur",
                fait_le or _horodatage(),
            ),
        )
        return int(cur.lastrowid)


def lister_actions(
    facture_id: int | None = None,
    limite: int | None = None,
    depuis: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM actions"
    conditions: list[str] = []
    args: list = []
    if facture_id is not None:
        conditions.append("facture_id = ?")
        args.append(int(facture_id))
    if depuis:
        conditions.append("fait_le >= ?")
        args.append(depuis)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY fait_le DESC, id DESC"
    if limite:
        sql += f" LIMIT {int(limite)}"
    with connexion() as cx:
        lignes = cx.execute(sql, args).fetchall()
    return [dict(row) for row in lignes]


def compter_actions_facture(facture_id: int) -> int:
    with connexion() as cx:
        row = cx.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE facture_id = ?", (int(facture_id),)
        ).fetchone()
    return int(row["n"])


def derniere_action(facture_id: int) -> dict | None:
    lignes = lister_actions(facture_id=facture_id, limite=1)
    return lignes[0] if lignes else None


# ---------------------------------------------------------------------------
# Historique des règlements (jeu d'entraînement du modèle)
# ---------------------------------------------------------------------------
def ajouter_reglement(
    client: str,
    montant: float,
    echeance,
    date_paiement,
    numero: str | None = None,
    montant_paye: float | None = None,
    source: str = "saisie",
) -> int:
    """Enregistre un règlement passé ; ``jours_retard`` est calculé ici."""
    ech = _date(echeance)
    pai = _date(date_paiement)
    retard = max((pai - ech).days, 0) if (ech and pai) else 0
    with connexion() as cx:
        cur = cx.execute(
            """INSERT INTO reglements
               (client, numero, montant, echeance, date_paiement, jours_retard, montant_paye, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                client,
                numero,
                float(montant or 0),
                _iso(ech),
                _iso(pai),
                retard,
                float(montant_paye) if montant_paye not in (None, "") else None,
                source,
            ),
        )
        return int(cur.lastrowid)


def ajouter_reglements(lignes: list[dict]) -> int:
    """Insertion en lot de règlements historiques."""
    total = 0
    with connexion() as cx:
        for ligne in lignes:
            ech = _date(ligne.get("echeance"))
            pai = _date(ligne.get("date_paiement"))
            if not (ech and pai):
                continue
            retard = ligne.get("jours_retard")
            if retard is None:
                retard = max((pai - ech).days, 0)
            cx.execute(
                """INSERT INTO reglements
                   (client, numero, montant, echeance, date_paiement, jours_retard,
                    montant_paye, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ligne.get("client"),
                    ligne.get("numero"),
                    float(ligne.get("montant") or 0),
                    _iso(ech),
                    _iso(pai),
                    int(retard),
                    ligne.get("montant_paye"),
                    ligne.get("source") or "import",
                ),
            )
            total += 1
    return total


def lister_reglements() -> list[dict]:
    with connexion() as cx:
        lignes = cx.execute("SELECT * FROM reglements ORDER BY date_paiement DESC").fetchall()
    resultat = []
    for row in lignes:
        item = dict(row)
        item["echeance"] = _date(item.get("echeance"))
        item["date_paiement"] = _date(item.get("date_paiement"))
        resultat.append(item)
    return resultat


def compter_reglements() -> int:
    with connexion() as cx:
        return int(cx.execute("SELECT COUNT(*) AS n FROM reglements").fetchone()["n"])


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
def _enregistrer_client(nom: str | None, telephone: str | None, email: str | None) -> None:
    if not nom:
        return
    maintenant = _horodatage()
    with connexion() as cx:
        row = cx.execute("SELECT * FROM clients WHERE nom = ?", (nom,)).fetchone()
        if row is None:
            cx.execute(
                "INSERT INTO clients (nom, telephone, email, maj_le) VALUES (?, ?, ?, ?)",
                (nom, telephone, email, maintenant),
            )
        elif telephone or email:
            cx.execute(
                "UPDATE clients SET telephone = COALESCE(?, telephone), "
                "email = COALESCE(?, email), maj_le = ? WHERE nom = ?",
                (telephone, email, maintenant, nom),
            )


def lister_clients() -> list[dict]:
    with connexion() as cx:
        lignes = cx.execute("SELECT * FROM clients ORDER BY nom COLLATE NOCASE").fetchall()
    return [dict(row) for row in lignes]


def maj_client(nom: str, **champs) -> None:
    if not champs:
        return
    champs["maj_le"] = _horodatage()
    affectations = ", ".join(f"{c} = ?" for c in champs)
    with connexion() as cx:
        cx.execute(
            f"UPDATE clients SET {affectations} WHERE nom = ?",
            list(champs.values()) + [nom],
        )


# ---------------------------------------------------------------------------
# Divers
# ---------------------------------------------------------------------------
def signature() -> str:
    """Empreinte des données : sert à invalider les calculs mis en cache."""
    with connexion() as cx:
        factures = cx.execute(
            "SELECT COUNT(*) AS n, COALESCE(MAX(maj_le), '') AS m FROM factures"
        ).fetchone()
        actions = cx.execute(
            "SELECT COUNT(*) AS n, COALESCE(MAX(fait_le), '') AS m FROM actions"
        ).fetchone()
        reglements = cx.execute("SELECT COUNT(*) AS n FROM reglements").fetchone()
        params = cx.execute("SELECT COUNT(*) AS n FROM params").fetchone()
    return (
        f"{factures['n']}/{factures['m']}"
        f"|{actions['n']}/{actions['m']}"
        f"|{reglements['n']}|{params['n']}"
    )


def statistiques_base() -> dict:
    """Quelques compteurs affichés dans les réglages."""
    with connexion() as cx:
        factures = int(cx.execute("SELECT COUNT(*) AS n FROM factures").fetchone()["n"])
        actions = int(cx.execute("SELECT COUNT(*) AS n FROM actions").fetchone()["n"])
        reglements = int(cx.execute("SELECT COUNT(*) AS n FROM reglements").fetchone()["n"])
    return {"factures": factures, "actions": actions, "reglements": reglements}


def sauvegarde_bytes() -> bytes:
    """Copie de la base pour téléchargement (sauvegarde manuelle)."""
    if not CHEMIN_DB.exists():
        return b""
    return CHEMIN_DB.read_bytes()
