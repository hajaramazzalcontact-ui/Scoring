"""Scoring des Impayés — V2 (Streamlit + IA Claude).
5 pages : Tableau de bord · Factures · Fiche & message · Assistant IA · Réglages & historique.
Stockage en session. IA via API Claude (fallback règles si pas de clé).
"""
from datetime import date, datetime, timedelta

import streamlit as st
import pandas as pd

# --- dépendances optionnelles ---
try:
    import numpy as np
except Exception:
    np = None

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY = True
except Exception:
    PLOTLY = False

try:
    from sklearn.linear_model import LogisticRegression
    SKLEARN = True
except Exception:
    SKLEARN = False

try:
    from fpdf import FPDF
    FPDF_OK = True
except Exception:
    FPDF_OK = False

st.set_page_config(page_title="Scoring des Impayés", page_icon="💰", layout="wide")

# ============================================================
#  ÉTAT
# ============================================================
DEFAULT_STATE = {
    "societe": "Ma Société",
    "seuil_1": 1, "seuil_2": 8, "seuil_3": 15, "seuil_4": 30, "seuil_5": 60,
    "poids_retard": 40, "poids_montant": 25, "poids_hist": 20, "poids_risque": 15,
    "ton": "bienveillant",
    "langue": "français",
    "api_key": "",
    "model": "claude-sonnet-4-5",
    "factures": [],
    "historique": [],
    "messages": {},      # id -> texte généré
    "chat": [],
    "filtre_niveau": None,
    "date_ref": date.today(),
    "next_id": 1,
    "navpage": "Tableau de bord",
}
for k, v in DEFAULT_STATE.items():
    if k not in st.session_state:
        st.session_state[k] = v


def init_demo():
    d = st.session_state.date_ref
    demo = [
        ("Client Atlas SARL", "F-001", 15000, 3, "0612345678", "atlas@mail.ma", 0),
        ("Clinique Anouar", "F-002", 45000, 12, "0623456789", "compta@anouar.ma", 2),
        ("École Al Manar", "F-003", 8000, 22, "0634567890", "finance@almanar.ma", 1),
        ("Boulangerie Baraka", "F-004", 32000, 45, "0645678901", "baraka@mail.ma", 4),
        ("Garage Tazi", "F-005", 60000, 75, "0656789012", "tazi@mail.ma", 3),
        ("Café Nour", "F-006", 5000, -10, "0667890123", "nour@mail.ma", 0),
    ]
    for client, num, montant, jr, tel, mail, nr in demo:
        st.session_state.factures.append({
            "id": st.session_state.next_id, "client": client, "numero": num,
            "montant": float(montant), "echeance": d - timedelta(days=jr),
            "telephone": tel, "email": mail, "nb_retards": nr,
            "statut": "Impayée", "date_paiement": None,
        })
        st.session_state.next_id += 1


# ============================================================
#  NIVEAUX & COULEURS
# ============================================================
NIVEAUX = [
    ("1 — Rappel", "SMS de rappel", "SMS"),
    ("2 — Contact", "Appel téléphonique", "Appel"),
    ("3 — Relance", "Email personnalisé", "Email"),
    ("4 — Mise en demeure", "Mise en demeure", "Mise en demeure"),
    ("5 — Contentieux", "Transmission à l'avocat", "Avocat"),
]
NIV_LABELS = [n[0] for n in NIVEAUX]
NIV_ACTIONS = [n[1] for n in NIVEAUX]
COLORS = {
    "À jour": "#1b5e20",
    "1 — Rappel": "#2e7d32",
    "2 — Contact": "#7cb342",
    "3 — Relance": "#f9a825",
    "4 — Mise en demeure": "#e65100",
    "5 — Contentieux": "#111111",
}
RISK_COLORS = {
    "Bon payeur": "#2e7d32", "Distrait": "#7cb342",
    "Lent mais fiable": "#f9a825", "Récidiviste": "#e65100", "À risque": "#b71c1c",
}


def fmt_mad(x):
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " MAD"


def seuils():
    return [st.session_state.seuil_1, st.session_state.seuil_2,
            st.session_state.seuil_3, st.session_state.seuil_4, st.session_state.seuil_5]


def niveau_index(jours, s=None):
    """Retourne l'index 0-4 du niveau atteint, ou -1 si à jour."""
    s = s or seuils()
    if jours < s[0]:
        return -1
    for i in range(4, -1, -1):
        if jours >= s[i]:
            return i
    return -1


def niveau_label(jours, s=None):
    i = niveau_index(jours, s)
    return "À jour" if i < 0 else NIV_LABELS[i]


def prochain_seuil(jours, s=None):
    """(label du prochain niveau, jours restants) ou (None, None)."""
    s = s or seuils()
    i = niveau_index(jours, s)
    ni = i + 1
    if ni > 4:
        return None, None
    return NIV_LABELS[ni], s[ni] - jours


# ============================================================
#  PRÉDICTION DE PAIEMENT (heuristique + sklearn si assez d'historique)
# ============================================================
def _heuristique(jours, nb_retards):
    base = 0.88
    p7 = base - 0.020 * jours - 0.075 * nb_retards
    p15 = base - 0.013 * jours - 0.060 * nb_retards
    p30 = base - 0.007 * jours - 0.045 * nb_retards
    cl = lambda x: max(0.02, min(0.98, x))
    p7, p15, p30 = cl(p7), cl(p15), cl(p30)
    p15 = max(p15, p7); p30 = max(p30, p15)
    return p7, p15, p30


def _entrainer_modele():
    """Entraîne une régression logistique si assez de factures payées avec historique."""
    if not SKLEARN:
        return None
    payees = [f for f in st.session_state.factures if f.get("statut") == "Payée" and f.get("date_paiement")]
    if len(payees) < 12:
        return None
    try:
        X, y = [], []
        dref = st.session_state.date_ref
        for f in payees:
            dp = f["date_paiement"]
            if isinstance(dp, str):
                dp = datetime.strptime(dp, "%Y-%m-%d").date()
            retard_regle = max(0, (dp - f["echeance"]).days)
            X.append([retard_regle, f.get("nb_retards", 0)])
            y.append(1 if retard_regle <= 30 else 0)
        if len(set(y)) < 2:
            return None
        m = LogisticRegression(max_iter=500).fit(X, y)
        return m
    except Exception:
        return None


def predire(f, jours, model=None):
    """Retourne dict {p7,p15,p30, date_probable, profil}."""
    p7, p15, p30 = _heuristique(max(jours, 0), f.get("nb_retards", 0))
    m = model if model is not None else _entrainer_modele()
    if m is not None:
        try:
            import numpy as _np
            p = m.predict_proba(_np.array([[max(jours, 0), f.get("nb_retards", 0)]]))[0][1]
            p30 = max(0.02, min(0.98, p))
            p15 = max(0.02, min(0.98, p30 * 0.8))
            p7 = max(0.02, min(0.98, p30 * 0.5))
        except Exception:
            pass
    # délai attendu : plus la proba 7j est faible, plus on pousse la date
    delai = int(round((1 - p7) * 7 + (1 - p15) * 8 + (1 - p30) * 15))
    date_probable = st.session_state.date_ref + timedelta(days=max(3, delai))
    nb = f.get("nb_retards", 0)
    if jours <= 0 and nb == 0:
        profil = "Bon payeur"
    elif nb == 0 and p15 > 0.6:
        profil = "Distrait"
    elif nb <= 1 and p15 > 0.4:
        profil = "Lent mais fiable"
    elif nb >= 3 or p30 < 0.3:
        profil = "Récidiviste" if nb >= 3 else "À risque"
    else:
        profil = "Lent mais fiable"
    if p30 < 0.25:
        profil = "À risque"
    return {"p7": p7, "p15": p15, "p30": p30, "date_probable": date_probable, "profil": profil}


# ============================================================
#  DATAFRAME ENRICHI
# ============================================================
def enrichir():
    s = seuils()
    dref = st.session_state.date_ref
    facts = st.session_state.factures
    if not facts:
        return pd.DataFrame()
    impayees = [f for f in facts if f.get("statut") != "Payée"]
    montants = [f["montant"] for f in impayees] or [1.0]
    max_m = max(montants)
    wsum = (st.session_state.poids_retard + st.session_state.poids_montant
            + st.session_state.poids_hist + st.session_state.poids_risque) or 1
    modele = _entrainer_modele()
    rows = []
    for f in facts:
        jours = (dref - f["echeance"]).days
        paye = f.get("statut") == "Payée"
        pred = predire(f, jours, modele)
        if paye:
            niv, score = "Payée", 0
        else:
            niv = niveau_label(jours, s)
            pts_ret = min(max(jours, 0) / 60.0, 1.0) * st.session_state.poids_retard
            pts_mon = (f["montant"] / max_m) * st.session_state.poids_montant
            pts_his = min(f.get("nb_retards", 0) / 5.0, 1.0) * st.session_state.poids_hist
            pts_ris = (1 - pred["p30"]) * st.session_state.poids_risque
            score = int(round(min(100, (pts_ret + pts_mon + pts_his + pts_ris) * 100 / wsum)))
            score = min(100, score)
        rows.append({**f, "jours_retard": jours, "niveau": niv, "score": score,
                     "p7": pred["p7"], "p15": pred["p15"], "p30": pred["p30"],
                     "date_probable": pred["date_probable"], "profil": pred["profil"]})
    df = pd.DataFrame(rows)
    return df.sort_values(["statut", "score"], ascending=[True, False])


def explication(f, df):
    """Phrase expliquant le score."""
    jours = f["jours_retard"]
    montants = df[df["statut"] != "Payée"]["montant"].tolist() or [f["montant"]]
    pct_montant = sum(1 for m in montants if m < f["montant"]) / len(montants)
    top = "top 10 %" if pct_montant >= 0.9 else ("top 25 %" if pct_montant >= 0.75 else "montant moyen")
    return (f"Score {int(f['score'])} : retard de {int(jours)} jours, {top} des montants, "
            f"{int(f.get('nb_retards', 0))} retard(s) passé(s), probabilité de paiement 30 j : "
            f"{f['p30']*100:.0f} %.")


# ============================================================
#  MESSAGES — gabarits + IA
# ============================================================
def _montant_txt(f):
    return fmt_mad(f["montant"]).replace(" MAD", "")


def gabarit(niveau_label, f, ton, langue):
    """Message de secours (sans IA)."""
    eche = f["echeance"].strftime("%d/%m/%Y")
    jours = int(f["jours_retard"])
    soc = st.session_state.societe
    m = _montant_txt(f)
    if langue == "anglais":
        base = {
            "1 — Rappel": f"Hello {f['client']}, invoice {f['numero']} of {m} MAD (due {eche}) is overdue by {jours} days. Thank you for settling it within 48h. {soc}",
            "2 — Contact": f"CALL SCRIPT — {f['client']} ({f.get('telephone','')})\n1. Introduce yourself, mention invoice {f['numero']} ({m} MAD, due {eche}, {jours} days late).\n2. Listen to the reason.\n3. Offer immediate payment or a dated promise.\n4. Confirm the commitment by email.",
            "3 — Relance": f"Subject: Overdue invoice {f['numero']} — {m} MAD\n\nHello {f['client']},\nInvoice {f['numero']} of {m} MAD, due on {eche}, is {jours} days overdue.\nPlease settle within 7 days or we will send a formal notice.\nRegards,\n{soc}",
            "4 — Mise en demeure": f"{soc}\nFORMAL NOTICE — invoice {f['numero']}\n\nTo {f['client']}: please pay {m} MAD within 8 days (invoice due {eche}, {jours} days late). Otherwise the file goes to our lawyer.\n(⚠️ Draft — to be validated by a lawyer.)",
            "5 — Contentieux": f"FILE FOR LAWYER — {f['client']} / invoice {f['numero']}: {m} MAD, due {eche} ({jours} days late). Include invoice, reminders, formal notice. (⚠️ Draft.)",
        }
    elif langue == "arabe":
        base = {
            "1 — Rappel": f"مرحبا {f['client']}، الفاتورة {f['numero']} بمبلغ {m} درهم (تاريخ الاستحقاق {eche}) متأخرة بـ {jours} يوم. المرجو التسوية خلال 48 ساعة. {soc}",
            "2 — Contact": f"سكريبت المكالمة — {f['client']} ({f.get('telephone','')}): الفاتورة {f['numero']} ({m} درهم، استحقاق {eche}، تأخر {jours} يوم). الاستماع للسبب ثم اقتراح الدفع.",
            "3 — Relance": f"الموضوع: الفاتورة {f['numero']} غير مسددة ({m} درهم)\n\nمرحبا {f['client']}، الفاتورة {f['numero']} متأخرة بـ {jours} يوم. المرجو التسوية خلال 7 أيام.\n{soc}",
            "4 — Mise en demeure": f"{soc}\nإنذار بالدفع — الفاتورة {f['numero']}: {m} درهم خلال 8 أيام. وإلا سيحال الملف على المحامي. (⚠️ مسودة.)",
            "5 — Contentieux": f"ملف للمحامي — {f['client']} / {f['numero']}: {m} درهم، تأخر {jours} يوم. (⚠️ مسودة.)",
        }
    else:
        base = {
            "1 — Rappel": f"Bonjour {f['client']}, sauf erreur, la facture {f['numero']} de {m} MAD (échéance {eche}) reste impayée ({jours} j de retard). Merci de régulariser sous 48h. {soc}",
            "2 — Contact": (f"SCRIPT D'APPEL — {f['client']} ({f.get('telephone','')})\n"
                            f"1. Se présenter : « Bonjour, {soc}, au sujet de la facture {f['numero']} de {m} MAD, échue le {eche} ({jours} j de retard). »\n"
                            f"2. Écouter le motif (oubli / litige / trésorerie).\n"
                            f"3. Proposer : paiement immédiat ou promesse datée.\n"
                            f"4. Conclure : « Je note votre engagement et vous envoie un récapitulatif. »\n"
                            f"5. Noter l'action comme faite dans l'application."),
            "3 — Relance": (f"Objet : Facture {f['numero']} impayée — {m} MAD\n\n"
                            f"Bonjour {f['client']},\n\nNotre facture {f['numero']} de {m} MAD, échue le {eche}, "
                            f"soit {jours} jours de retard, reste impayée.\nSans règlement sous 7 jours, nous engagerons une mise en demeure.\n\n"
                            f"Cordialement,\n{soc}"),
            "4 — Mise en demeure": (f"{soc}\nMISE EN DEMEURE — facture {f['numero']}\n\n{f['client']}\n\n"
                                    f"Mise en demeure de payer {m} MAD (facture du {eche}, {jours} jours de retard) sous 8 jours.\n"
                                    f"À défaut, transmission à notre avocat avec intérêts et frais.\n\nFait le "
                                    f"{st.session_state.date_ref.strftime('%d/%m/%Y')}\n{soc}\n\n⚠️ Brouillon : validation juriste requise."),
            "5 — Contentieux": (f"NOTE À L'AVOCAT — {f['client']} / facture {f['numero']}\n"
                                f"Tél : {f.get('telephone','')} — Email : {f.get('email','')}\n"
                                f"Créance : {m} MAD, échéance {eche} ({jours} j). Antécédents : {f.get('nb_retards',0)} retard(s).\n"
                                f"Pièces : facture, relances, mise en demeure. ⚠️ Brouillon à valider."),
        }
    txt = base.get(niveau_label, "Aucune action requise.")
    if ton == "ferme":
        txt += "\n\n— Ton ferme : sans règlement rapide, nous appliquerons les conséquences prévues."
    elif ton == "bienveillant" and niveau_label in ("1 — Rappel", "2 — Contact"):
        txt += "\n\n— Nous restons à votre disposition si besoin d'un échelonnement."
    return txt


def appel_claude(prompt, system=None, max_tokens=700):
    key = st.session_state.get("api_key", "").strip()
    if not key:
        return None
    model = st.session_state.get("model", "claude-sonnet-4-5")
    system = system or ("Tu es l'assistant de recouvrement de la société "
                        f"{st.session_state.societe}. Réponds en {st.session_state.langue}, ton {st.session_state.ton}. "
                        "Sois concis, professionnel et respectueux. N'invente aucune donnée.")
    # 1) SDK officiel
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    except Exception:
        pass
    # 2) HTTP direct
    try:
        import requests
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", []))
    except Exception as e:
        st.session_state["last_llm_error"] = str(e)
        return None


def generer_message(f, niveau_label, variante=0):
    """Génère (IA) ou renvoie le gabarit. Résultat stocké en session."""
    fid = f["id"]
    if st.session_state.get("api_key", "").strip():
        prompt = (
            f"Rédige le message de relance de niveau « {niveau_label} » ({NIV_ACTIONS[NIV_LABELS.index(niveau_label)] if niveau_label in NIV_LABELS else ''}).\n"
            f"Client : {f['client']}\nN° facture : {f['numero']}\nMontant : {f['montant']:.2f} MAD\n"
            f"Échéance : {f['echeance'].strftime('%d/%m/%Y')}\nJours de retard : {int(f['jours_retard'])}\n"
            f"Retards passés du client : {f.get('nb_retards',0)}\nProfil estimé : {f.get('profil','')}.\n"
            f"Ton demandé : {st.session_state.ton}. Langue : {st.session_state.langue}.\n"
            f"Requête n°{variante+1} : propose une {'nouvelle variante' if variante else 'rédaction'} prête à copier. "
            f"Pour une mise en demeure, inclus les mentions légales indispensables. Ajoute un avertissement de validation par un juriste le cas échéant."
        )
        txt = appel_claude(prompt)
        if txt:
            st.session_state.messages[fid] = txt
            return txt
        st.warning("IA indisponible — message généré par gabarit.")
    txt = gabarit(niveau_label, f, st.session_state.ton, st.session_state.langue)
    st.session_state.messages[fid] = txt
    return txt


# ============================================================
#  IMPORT & ANOMALIES
# ============================================================
COL_MAP = {
    "client": "client", "nom": "client", "name": "client",
    "numero": "numero", "num": "numero", "facture": "numero", "n°": "numero", "invoice": "numero",
    "montant": "montant", "amount": "montant", "mad": "montant", "total": "montant",
    "echeance": "echeance", "date": "echeance", "due": "echeance",
    "telephone": "telephone", "tel": "telephone", "phone": "telephone",
    "email": "email", "mail": "email",
    "retards": "nb_retards", "nb_retards": "nb_retards", "historique": "nb_retards",
}


def importer_dataframe(df_in):
    df_in = df_in.copy()
    df_in.columns = [str(c).strip().lower() for c in df_in.columns]
    ren = {c: COL_MAP[c] for c in df_in.columns if c in COL_MAP}
    df_in = df_in.rename(columns=ren)
    ajoutees, anomalies = 0, []
    for _, r in df_in.iterrows():
        try:
            client = str(r.get("client", "")).strip()
            num = str(r.get("numero", "")).strip()
            montant = float(str(r.get("montant", 0)).replace(",", ".").replace(" ", ""))
            ech = pd.to_datetime(r.get("echeance"), dayfirst=True).date()
            nb = int(float(r.get("nb_retards", 0) or 0))
            tel = str(r.get("telephone", "") or "")
            mail = str(r.get("email", "") or "")
            if not client or not num or montant <= 0:
                anomalies.append(f"Ligne ignorée (données manquantes) : {num or '?'}")
                continue
            if any(x["numero"] == num and x.get("statut") != "Payée" for x in st.session_state.factures):
                anomalies.append(f"Doublon : {num}")
                continue
            st.session_state.factures.append({
                "id": st.session_state.next_id, "client": client, "numero": num,
                "montant": montant, "echeance": ech, "telephone": tel, "email": mail,
                "nb_retards": nb, "statut": "Impayée", "date_paiement": None,
            })
            st.session_state.next_id += 1
            ajoutees += 1
        except Exception as e:
            anomalies.append(f"Ligne en erreur : {e}")
    return ajoutees, anomalies


def detecter_anomalies(df):
    a = []
    if df.empty:
        return a
    imp = df[df["statut"] != "Payée"]
    if not imp.empty:
        moy = imp["montant"].mean()
        sd = imp["montant"].std()
        for _, r in imp.iterrows():
            if sd and sd > 0 and r["montant"] > moy + 3 * sd:
                a.append(f"Montant inhabituel : {r['numero']} ({fmt_mad(r['montant'])})")
            if r["jours_retard"] > 730:
                a.append(f"Échéance incohérente : {r['numero']} ({int(r['jours_retard'])} j)")
            if not r.get("telephone") and not r.get("email"):
                a.append(f"Coordonnées manquantes : {r['numero']}")
    return a


# ============================================================
#  SÉRIE D'ÉVOLUTION & SIMULATEUR
# ============================================================
def serie_retard(df, semaines=10):
    if df.empty:
        return pd.DataFrame({"semaine": [], "montant": [], "nombre": []})
    rows = []
    dref = st.session_state.date_ref
    for w in range(semaines):
        d = dref - timedelta(days=(semaines - 1 - w) * 7)
        tot, n = 0.0, 0
        for _, f in df.iterrows():
            paye_avant = (f["statut"] == "Payée" and f.get("date_paiement")
                          and (f["date_paiement"] if not isinstance(f["date_paiement"], str)
                               else datetime.strptime(f["date_paiement"], "%Y-%m-%d").date()) <= d)
            if not paye_avant and f["echeance"] < d and (f["statut"] != "Payée" or (f.get("date_paiement") or dref) > d):
                tot += f["montant"]; n += 1
        rows.append({"semaine": d.strftime("%d/%m"), "montant": tot, "nombre": n})
    return pd.DataFrame(rows)


def simulateur(df, horizon, scenario):
    """Encaissement attendu sur l'horizon (7/30/90 j) selon un scénario."""
    if df.empty:
        return 0.0
    imp = df[df["statut"] != "Payée"]
    if imp.empty:
        return 0.0
    tot = 0.0
    for _, f in imp.iterrows():
        if horizon <= 7:
            p = f["p7"]
        elif horizon <= 30:
            p = f["p15"]
        else:
            p = f["p30"]
        if scenario == "optimiste":
            p = min(1.0, p * 1.25)
        elif scenario == "prudent":
            p = p * 0.7
        tot += f["montant"] * p
    return tot


# ============================================================
#  BRIEFING & ASSISTANT (fallback sans IA)
# ============================================================
def briefing_local(df):
    if df.empty:
        return "Aucune facture enregistrée."
    imp = df[df["statut"] != "Payée"]
    retard = imp[imp["jours_retard"] > 0]
    if retard.empty:
        return f"Aucune facture en retard aujourd'hui. {len(imp)} facture(s) à venir."
    total = retard["montant"].sum()
    top = retard.sort_values("score", ascending=False).head(3)
    lignes = [f"**Briefing du {st.session_state.date_ref.strftime('%d/%m/%Y')}**",
              f"- {len(retard)} facture(s) en retard pour {fmt_mad(total)}.",
              f"- Retard moyen : {retard['jours_retard'].mean():.0f} jours.",
              f"- Encaissement prévu à 30 j : {fmt_mad(simulateur(df,30,'realiste'))}.",
              "- À traiter en priorité :"]
    for _, r in top.iterrows():
        lignes.append(f"  - {r['numero']} · {r['client']} · {fmt_mad(r['montant'])} · {int(r['jours_retard'])} j · score {int(r['score'])}")
    return "\n".join(lignes)


def reponse_locale(question, df):
    q = question.lower()
    if "ce matin" in q or "aujourd" in q or "traiter" in q:
        imp = df[(df["statut"] != "Payée") & (df["jours_retard"] > 0)].sort_values("score", ascending=False)
        if imp.empty:
            return "Rien à traiter : aucune facture en retard."
        return "À traiter ce matin :\n" + "\n".join(
            f"- {r['numero']} · {r['client']} · {fmt_mad(r['montant'])} · score {int(r['score'])}"
            for _, r in imp.head(5).iterrows())
    if "doit le plus" in q or "me doit" in q:
        imp = df[df["statut"] != "Payée"]
        if imp.empty:
            return "Aucune facture impayée."
        g = imp.groupby("client")["montant"].sum().sort_values(ascending=False).head(3)
        return "Clients qui vous doivent le plus :\n" + "\n".join(f"- {c} : {fmt_mad(m)}" for c, m in g.items())
    if "encaiss" in q or "fin du mois" in q or "trésorerie" in q:
        return (f"Encaissement prévu — 7 j : {fmt_mad(simulateur(df,7,'realiste'))}\n"
                f"30 j : {fmt_mad(simulateur(df,30,'realiste'))}\n"
                f"90 j : {fmt_mad(simulateur(df,90,'realiste'))}")
    if "échéancier" in q or "echeancier" in q:
        return ("Pour un échéancier : proposez 2 à 3 versements datés, confirmez par écrit "
                "et notez l'action dans la fiche de la facture. (Sans clé API, réponse générique.)")
    return ("Assistant en mode local (sans clé API). Ajoutez une clé Claude dans Réglages pour "
            "des réponses personnalisées. Exemples : « Quelles factures ce matin ? », "
            "« Quel client me doit le plus ? », « Combien vais-je encaisser ? ».")


# ============================================================
#  EXPORT
# ============================================================
def _latin(txt):
    return str(txt).encode("latin-1", "replace").decode("latin-1")


def export_historique_pdf(df, question=None):
    if not FPDF_OK:
        return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, "Scoring des Impayes - Journal des relances")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _latin(f"Societe : {st.session_state.societe}  |  Edite le {datetime.now().strftime('%d/%m/%Y %H:%M')}"))
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 9)
    widths = [30, 25, 55, 40, 0]
    for h, w in zip(["Date", "Facture", "Client", "Niveau", "Action"], widths):
        pdf.cell(w, 7, h, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for _, r in df.iterrows():
        vals = [str(r.get("date", ""))[:16], str(r.get("facture", ""))[:14],
                str(r.get("client", ""))[:28], str(r.get("niveau", ""))[:20], str(r.get("action", ""))[:40]]
        for v, w in zip(vals, widths):
            pdf.cell(w, 6, _latin(v), border=1)
        pdf.ln()
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 5, _latin("Preuve de relance generee par l'application. Les modeles de mise en demeure et de note "
                                "a l'avocat sont des brouillons : validation par un juriste requise. Donnees "
                                "personnelles : conformite CNDP (loi 09-08)."))
    return bytes(pdf.output())


# ============================================================
#  HISTORIQUE
# ============================================================
def log_action(numero, client, niveau, action):
    st.session_state.historique.append({
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "facture": numero, "client": client, "niveau": niveau, "action": action,
    })


def filtrer_niveau(lab):
    """Callback : filtre + navigation (évite d'écrire sur une clé de widget déjà créée)."""
    st.session_state.filtre_niveau = lab
    st.session_state["flt_niv_ml"] = [lab]
    st.session_state.navpage = "Factures"


def ouvrir_facture(fid):
    """Callback : ouvre la fiche d'une facture."""
    st.session_state["sel_facture"] = fid
    st.session_state.navpage = "Fiche & message"


# ============================================================
#  SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## 💰 Scoring des Impayés")
    st.caption(f"**{st.session_state.societe}**")
    st.radio("Navigation", ["Tableau de bord", "Factures", "Fiche & message",
                            "Assistant IA", "Réglages & historique"],
             key="navpage")
    st.divider()
    st.caption("Date de référence")
    st.session_state.date_ref = st.date_input("Date", value=st.session_state.date_ref,
                                              label_visibility="collapsed")
    if not st.session_state.api_key:
        st.warning("IA désactivée : ajoutez une clé Claude dans Réglages pour l'IA générative.", icon="🤖")
    else:
        st.success("IA Claude active", icon="🤖")
    if not st.session_state.factures:
        if st.button("Charger la démo", width="stretch"):
            init_demo(); st.rerun()

df = enrichir()
actives = df[df["statut"] != "Payée"] if not df.empty else pd.DataFrame()
en_retard = actives[actives["jours_retard"] > 0] if not actives.empty else pd.DataFrame()
page = st.session_state.navpage

# ============================================================
#  PAGE 1 — TABLEAU DE BORD
# ============================================================
if page == "Tableau de bord":
    st.title("📊 Tableau de bord")
    if en_retard.empty and actives.empty:
        st.info("Aucune donnée. Chargez la démo ou enregistrez des factures (page Factures).")
    else:
        total = en_retard["montant"].sum() if not en_retard.empty else 0
        nb = len(en_retard)
        moy = en_retard["jours_retard"].mean() if not en_retard.empty else 0
        enc = simulateur(df, 30, "realiste")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Impayé total", fmt_mad(total))
        c2.metric("Factures en retard", nb)
        c3.metric("Retard moyen", f"{moy:.0f} jours")
        c4.metric("Encaissement prévu (30 j)", fmt_mad(enc))

        st.subheader("Entonnoir des cinq niveaux")
        rep = (en_retard["niveau"].value_counts().reindex(NIV_LABELS, fill_value=0)
               if not en_retard.empty else pd.Series([0]*5, index=NIV_LABELS))
        cols = st.columns(5)
        for i, lab in enumerate(NIV_LABELS):
            with cols[i]:
                st.markdown(
                    f"<div style='background:{COLORS[lab]};color:white;padding:10px;border-radius:8px;text-align:center'>"
                    f"<b>{lab}</b><br><span style='font-size:22px'>{int(rep[lab])}</span></div>",
                    unsafe_allow_html=True)
                st.button("Filtrer", key=f"flt{i}", width="stretch",
                          on_click=filtrer_niveau, args=(lab,))
        if PLOTLY and not en_retard.empty:
            fig = go.Figure(go.Funnel(
                y=NIV_LABELS,
                x=[int(rep[l]) for l in NIV_LABELS],
                marker={"color": [COLORS[l] for l in NIV_LABELS]}))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, width="stretch")

        col_g, col_t = st.columns([3, 2])
        with col_g:
            st.subheader("Évolution du retard (10 semaines)")
            serie = serie_retard(df, 10)
            if PLOTLY and not serie.empty:
                fg = px.area(serie, x="semaine", y="montant", labels={"semaine": "", "montant": "MAD"})
                fg.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fg, width="stretch")
            else:
                st.line_chart(serie.set_index("semaine")["montant"])
        with col_t:
            st.subheader("Top 5 urgences")
            if not en_retard.empty:
                top = en_retard.sort_values("score", ascending=False).head(5)
                for _, r in top.iterrows():
                    st.markdown(
                        f"<div style='border-left:6px solid {COLORS[r['niveau']]};padding:6px 10px;margin-bottom:6px'>"
                        f"<b>{int(r['score'])}/100</b> · {r['numero']} · {r['client']}<br>"
                        f"<small>{fmt_mad(r['montant'])} · {int(r['jours_retard'])} j · {r['niveau']}</small></div>",
                        unsafe_allow_html=True)

# ============================================================
#  PAGE 2 — FACTURES
# ============================================================
elif page == "Factures":
    st.title("🧾 Factures")
    tab_liste, tab_ajout, tab_import = st.tabs(["Liste", "Ajouter", "Importer"])

    with tab_liste:
        if actives.empty:
            st.info("Aucune facture impayée.")
        else:
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            f_niv = c1.multiselect("Niveau", NIV_LABELS, key="flt_niv_ml")
            f_cli = c2.text_input("Client contient")
            mmin = c3.number_input("Montant min", min_value=0.0, value=0.0, step=1000.0)
            tri = c4.selectbox("Tri", ["Score", "Retard", "Montant"])
            vue = actives.copy()
            if f_niv:
                vue = vue[vue["niveau"].isin(f_niv)]
            if f_cli:
                vue = vue[vue["client"].str.contains(f_cli, case=False, na=False)]
            vue = vue[vue["montant"] >= mmin]
            vue = vue.sort_values({"Score": "score", "Retard": "jours_retard", "Montant": "montant"}[tri],
                                  ascending=False)
            for _, r in vue.iterrows():
                with st.container(border=True):
                    a, b = st.columns([5, 1])
                    with a:
                        st.markdown(
                            f"<span style='background:{COLORS[r['niveau']]};color:white;padding:2px 8px;"
                            f"border-radius:10px;font-size:12px'>{r['niveau']}</span>&nbsp; "
                            f"<b>{r['numero']}</b> · {r['client']} · {fmt_mad(r['montant'])} · "
                            f"{int(r['jours_retard'])} j de retard",
                            unsafe_allow_html=True)
                        st.progress(int(r["score"]) / 100, text=f"Score {int(r['score'])}/100 · Profil : {r['profil']} · P(30j) {r['p30']*100:.0f} %")
                    with b:
                        st.write("")
                        st.button("Ouvrir", key=f"open_{r['id']}", width="stretch",
                                  on_click=ouvrir_facture, args=(int(r["id"]),))

    with tab_ajout:
        st.subheader("Enregistrer une facture")
        with st.form("form_new", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                client = st.text_input("Client *")
                numero = st.text_input("N° de facture *")
                montant = st.number_input("Montant (MAD) *", min_value=0.0, step=100.0)
            with c2:
                echeance = st.date_input("Échéance *", value=st.session_state.date_ref)
                tel = st.text_input("Téléphone")
                mail = st.text_input("Email")
                nb = st.number_input("Retards passés du client", min_value=0, step=1, value=0)
            ok = st.form_submit_button("Enregistrer")
            if ok:
                if not client or not numero or montant <= 0:
                    st.error("Client, numéro et montant (> 0) obligatoires.")
                elif any(x["numero"] == numero and x.get("statut") != "Payée" for x in st.session_state.factures):
                    st.error("Ce numéro existe déjà (impayée).")
                else:
                    st.session_state.factures.append({
                        "id": st.session_state.next_id, "client": client, "numero": numero,
                        "montant": float(montant), "echeance": echeance, "telephone": tel,
                        "email": mail, "nb_retards": int(nb), "statut": "Impayée", "date_paiement": None})
                    st.session_state.next_id += 1
                    log_action(numero, client, "—", "Facture enregistrée")
                    st.success("Facture enregistrée."); st.rerun()

    with tab_import:
        st.subheader("Import Excel / CSV")
        st.caption("Colonnes reconnues : client, numero, montant, echeance, telephone, email, retards.")
        up = st.file_uploader("Fichier", type=["csv", "xlsx", "xls"])
        if up is not None:
            try:
                if up.name.lower().endswith(".csv"):
                    d = pd.read_csv(up, sep=None, engine="python")
                else:
                    d = pd.read_excel(up)
                st.dataframe(d.head(20), width="stretch")
                if st.button("Importer ces lignes"):
                    n, an = importer_dataframe(d)
                    st.success(f"{n} facture(s) importée(s).")
                    if an:
                        st.warning("Anomalies :\n- " + "\n- ".join(an))
                        log_action("—", "—", "Import", "Import : " + "; ".join(an))
                    st.rerun()
            except Exception as e:
                st.error(f"Lecture impossible : {e}")
        st.divider()
        st.subheader("Anomalies détectées dans les données")
        an = detecter_anomalies(df)
        if an:
            st.warning("\n".join("- " + x for x in an))
        else:
            st.success("Aucune anomalie détectée.")
        if not df.empty:
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ Exporter les factures (CSV)", csv, "impayes.csv", "text/csv")

# ============================================================
#  PAGE 3 — FICHE & MESSAGE
# ============================================================
elif page == "Fiche & message":
    st.title("🗂️ Fiche & message")
    impayees = actives if not actives.empty else pd.DataFrame()
    if impayees.empty:
        st.info("Aucune facture impayée.")
    else:
        options = {f"{r['numero']} · {r['client']} · {fmt_mad(r['montant'])}": r["id"]
                   for _, r in impayees.sort_values("score", ascending=False).iterrows()}
        labels = list(options.keys())
        default_id = st.session_state.get("sel_facture")
        default_label = next((k for k in labels if options[k] == default_id), labels[0])
        # met la clé du widget à jour AVANT sa création (navigation depuis la liste)
        if st.session_state.get("_last_sel") != default_id:
            st.session_state["sel_facture_box"] = default_label
            st.session_state["_last_sel"] = default_id
        if st.session_state.get("sel_facture_box") not in labels:
            st.session_state["sel_facture_box"] = default_label
        choix = st.selectbox("Facture", labels, key="sel_facture_box")
        fid = options[choix]
        r = impayees[impayees["id"] == fid].iloc[0]

        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(
                f"<span style='background:{COLORS[r['niveau']]};color:white;padding:3px 10px;"
                f"border-radius:12px'>{r['niveau']}</span>",
                unsafe_allow_html=True)
            st.markdown(f"### {r['numero']} — {r['client']}")
            st.write(f"**Montant :** {fmt_mad(r['montant'])}  \n**Échéance :** {r['echeance'].strftime('%d/%m/%Y')}  "
                     f"\n**Retard :** {int(r['jours_retard'])} jours  \n**Tél :** {r.get('telephone','—')}  "
                     f"\n**Email :** {r.get('email','—')}")
            if PLOTLY:
                g = go.Figure(go.Indicator(
                    mode="gauge+number", value=int(r["score"]),
                    gauge={"axis": {"range": [0, 100]},
                           "bar": {"color": COLORS[r["niveau"]]},
                           "steps": [{"range": [0, 25], "color": "#c8e6c9"},
                                     {"range": [25, 50], "color": "#ffe082"},
                                     {"range": [50, 75], "color": "#ffb74d"},
                                     {"range": [75, 100], "color": "#e57373"}]}))
                g.update_layout(height=220, margin=dict(l=20, r=20, t=10, b=10))
                st.plotly_chart(g, width="stretch")
            else:
                st.progress(int(r["score"]) / 100, text=f"Score {int(r['score'])}/100")
            st.info(explication(r, df))
            nom_next, rest = prochain_seuil(int(r["jours_retard"]))
            if nom_next:
                st.warning(f"⏳ Niveau suivant « {nom_next} » dans **{rest} jour(s)**.")
            else:
                st.error("🔴 Dernier niveau atteint : transmission à l'avocat.")
            st.markdown(f"**Prédiction :** payée à 7 j : {r['p7']*100:.0f} % · 15 j : {r['p15']*100:.0f} % · "
                        f"30 j : {r['p30']*100:.0f} %  \n**Date probable :** {r['date_probable'].strftime('%d/%m/%Y')} · "
                        f"**Profil :** {r['profil']}")
            # recommandation
            if st.button("💡 Meilleure action suivante", width="stretch"):
                if st.session_state.api_key:
                    p = (f"Pour la facture {r['numero']} ({r['client']}, {fmt_mad(r['montant'])}, "
                         f"{int(r['jours_retard'])} j de retard, profil {r['profil']}, "
                         f"probabilité de paiement 30 j {r['p30']*100:.0f}%), "
                         f"recommande en une phrase la meilleure action suivante et pourquoi.")
                    txt = appel_claude(p, max_tokens=200)
                    st.session_state[f"reco_{fid}"] = txt or "IA indisponible."
                else:
                    if r["profil"] in ("Récidiviste", "À risque"):
                        st.session_state[f"reco_{fid}"] = "Appeler plutôt qu'écrire : ce client réagit peu aux messages ; proposer un échelonnement daté."
                    elif r["profil"] == "Distrait":
                        st.session_state[f"reco_{fid}"] = "Envoyer un SMS de rappel court et bienveillant : oubli probable."
                    else:
                        st.session_state[f"reco_{fid}"] = "Relancer par email avec un délai ferme, puis appeler si pas de réponse."
            if f"reco_{fid}" in st.session_state:
                st.success(st.session_state[f"reco_{fid}"])

        with c2:
            st.markdown("**Frise des étapes**")
            etapes = NIV_LABELS
            ci = niveau_index(int(r["jours_retard"]))
            for i, e in enumerate(etapes):
                if i < ci:
                    st.markdown(f"✅ ~~{e}~~")
                elif i == ci:
                    st.markdown(f"👉 **{e}** (en cours)")
                else:
                    st.markdown(f"⬜ {e}")
            st.divider()
            st.markdown("**Messages déjà notés pour cette facture**")
            hist_f = [h for h in st.session_state.historique if h["facture"] == r["numero"]]
            if hist_f:
                for h in hist_f[-4:]:
                    st.caption(f"{h['date']} — {h['niveau']} — {h['action']}")
            else:
                st.caption("Aucune action enregistrée.")

        st.divider()
        st.subheader("Message prêt à envoyer")
        e1, e2, e3 = st.columns([1, 1, 2])
        e1.selectbox("Ton", ["bienveillant", "neutre", "ferme"], key="ton")
        e2.selectbox("Langue", ["français", "arabe", "anglais"], key="langue")
        if (st.session_state.get("_prev_ton") != st.session_state.ton
                or st.session_state.get("_prev_langue") != st.session_state.langue):
            st.session_state.messages = {}
            st.session_state["_prev_ton"] = st.session_state.ton
            st.session_state["_prev_langue"] = st.session_state.langue
        if e3.button("🔄 Générer / Régénérer le message"):
            st.session_state[f"var_{fid}"] = st.session_state.get(f"var_{fid}", 0) + 1
            generer_message(r.to_dict(), r["niveau"], st.session_state[f"var_{fid}"])
        if fid not in st.session_state.messages:
            st.session_state.messages[fid] = gabarit(r["niveau"], r.to_dict(),
                                                     st.session_state.ton, st.session_state.langue)
        st.code(st.session_state.messages[fid], language="markdown")
        st.caption("Utilisez l'icône « copier » en haut à droite du bloc.")
        b1, b2, b3 = st.columns(3)
        if b1.button("✅ Marquer comme fait", width="stretch"):
            log_action(r["numero"], r["client"], r["niveau"], "Action effectuée")
            st.success("Action notée dans l'historique.")
        if b2.button("💵 Marquer payée", width="stretch"):
            for fac in st.session_state.factures:
                if fac["id"] == fid:
                    fac["statut"] = "Payée"; fac["date_paiement"] = st.session_state.date_ref
            log_action(r["numero"], r["client"], r["niveau"], "Facture payée — clôturée")
            st.rerun()
        if b3.button("🗑️ Supprimer", width="stretch"):
            st.session_state.factures = [x for x in st.session_state.factures if x["id"] != fid]
            st.rerun()

# ============================================================
#  PAGE 4 — ASSISTANT IA
# ============================================================
elif page == "Assistant IA":
    st.title("🤖 Assistant IA")
    tab_b, tab_c = st.tabs(["Briefing du jour", "Conversation"])

    with tab_b:
        st.subheader("Briefing quotidien")
        if st.button("Générer le briefing"):
            if st.session_state.api_key:
                contexte = briefing_local(df)
                p = (f"Rédige un briefing de recouvrement concis (5-7 lignes) à partir de ces données :\n{contexte}\n"
                     f"Termine par les 3 actions prioritaires du jour.")
                txt = appel_claude(p, max_tokens=400)
                st.session_state["briefing"] = txt or contexte
            else:
                st.session_state["briefing"] = briefing_local(df)
        st.markdown(st.session_state.get("briefing", briefing_local(df)))

        st.divider()
        st.subheader("Simulateur de trésorerie")
        h = st.select_slider("Horizon (jours)", options=[7, 30, 90], value=30)
        cols = st.columns(3)
        for c, sc in zip(cols, ["optimiste", "realiste", "prudent"]):
            c.metric(sc.capitalize(), fmt_mad(simulateur(df, h, sc)))
        st.caption("Estimation à partir des probabilités de paiement par facture.")

    with tab_c:
        st.subheader("Poser une question")
        for m in st.session_state.chat:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
        q = st.chat_input("Ex. : Quelles factures dois-je traiter ce matin ?")
        if q:
            st.session_state.chat.append({"role": "user", "content": q})
            with st.chat_message("user"):
                st.markdown(q)
            if st.session_state.api_key:
                ctx = briefing_local(df)
                p = (f"Données de recouvrement :\n{ctx}\n\nQuestion de l'utilisateur : {q}\n"
                     f"Réponds de façon précise et concise, en t'appuyant sur ces données uniquement.")
                rep = appel_claude(p, max_tokens=500)
                if not rep:
                    rep = reponse_locale(q, df)
            else:
                rep = reponse_locale(q, df)
            st.session_state.chat.append({"role": "assistant", "content": rep})
            with st.chat_message("assistant"):
                st.markdown(rep)

# ============================================================
#  PAGE 5 — RÉGLAGES & HISTORIQUE
# ============================================================
elif page == "Réglages & historique":
    st.title("⚙️ Réglages & historique")
    tab_r, tab_h = st.tabs(["Réglages", "Historique (preuves)"])

    with tab_r:
        st.subheader("Société")
        st.session_state.societe = st.text_input("Nom de la société", value=st.session_state.societe)

        st.subheader("Seuils (jours de retard)")
        c = st.columns(5)
        st.session_state.seuil_1 = c[0].number_input("Rappel dès", 0, 365, st.session_state.seuil_1)
        st.session_state.seuil_2 = c[1].number_input("Contact dès", 0, 365, st.session_state.seuil_2)
        st.session_state.seuil_3 = c[2].number_input("Relance dès", 0, 365, st.session_state.seuil_3)
        st.session_state.seuil_4 = c[3].number_input("Mise en demeure dès", 0, 365, st.session_state.seuil_4)
        st.session_state.seuil_5 = c[4].number_input("Contentieux dès", 0, 365, st.session_state.seuil_5)
        s = seuils()
        if s != sorted(s):
            st.warning("⚠️ Les seuils doivent être croissants.")

        st.subheader("Pondérations du score")
        c = st.columns(4)
        st.session_state.poids_retard = c[0].slider("Retard", 0, 100, st.session_state.poids_retard)
        st.session_state.poids_montant = c[1].slider("Montant", 0, 100, st.session_state.poids_montant)
        st.session_state.poids_hist = c[2].slider("Historique", 0, 100, st.session_state.poids_hist)
        st.session_state.poids_risque = c[3].slider("Risque (prédiction)", 0, 100, st.session_state.poids_risque)

        st.subheader("Assistant IA (Claude)")
        st.session_state.api_key = st.text_input("Clé API Anthropic", value=st.session_state.api_key,
                                                 type="password")
        st.session_state.model = st.text_input("Modèle", value=st.session_state.model)
        st.caption("Sans clé, l'application fonctionne avec des gabarits et des réponses locales. "
                   "Les données transmises se limitent au strict nécessaire.")

    with tab_h:
        st.subheader("Journal horodaté des actions")
        if not st.session_state.historique:
            st.info("Aucune action enregistrée.")
        else:
            h = pd.DataFrame(st.session_state.historique)
            st.dataframe(h, width="stretch", hide_index=True)
            c = st.columns(3)
            c[0].download_button("⬇️ Historique (CSV)", h.to_csv(index=False).encode("utf-8-sig"),
                                 "historique_relances.csv", "text/csv")
            if not df.empty:
                c[1].download_button("⬇️ Factures (CSV)", df.to_csv(index=False).encode("utf-8-sig"),
                                     "impayes.csv", "text/csv")
            if FPDF_OK:
                pdf = export_historique_pdf(h)
                if pdf:
                    c[2].download_button("⬇️ Historique (PDF — preuve)", pdf,
                                         "historique_relances.pdf", "application/pdf")
            else:
                c[2].caption("Export PDF indisponible (installez fpdf2).")

st.divider()
st.caption("Scoring des Impayés — V2 · Streamlit + IA Claude · Les modèles de mise en demeure et de note à l'avocat "
           "sont des brouillons à faire valider par un juriste. Données personnelles : conformité loi 09-08 / CNDP.")
