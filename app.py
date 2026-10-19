"""Scoring des Impayés — V3 (Streamlit + IA Claude).
10 onglets : Tableau de bord · Clients · Factures · Fiche & message · Analyses ·
Trésorerie · Calendrier · Assistant IA · Historique & preuves · Réglages.
Palette 7.1, mode sombre, 13 graphiques, 4 familles de données exportables.
Stockage en session. IA via API Claude (repli sur gabarits si pas de clé).
"""
import calendar
import json
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
#  7.1 PALETTE & IDENTITÉ VISUELLE
# ============================================================
THEME = {
    "marque": "#0B1F3A",        # bleu nuit — marque
    "marque_clair": "#16325C",
    "paiement": "#14B8A6",      # turquoise — paiements
    "ia": "#7C3AED",            # violet — IA
    "alerte": "#DC2626",
}

# Échelle d'urgence du vert au noir (5 niveaux) + icône (accessibilité daltonienne)
URGENCE = [
    {"code": "rappel", "label": "1 — Rappel",           "couleur": "#16A34A", "icone": "🟢", "action": "SMS de rappel",           "canal": "SMS"},
    {"code": "contact", "label": "2 — Contact",          "couleur": "#65A30D", "icone": "🟡", "action": "Appel téléphonique",      "canal": "Appel"},
    {"code": "relance", "label": "3 — Relance",          "couleur": "#CA8A04", "icone": "🟠", "action": "Email personnalisé",      "canal": "Email"},
    {"code": "miseendemeure", "label": "4 — Mise en demeure",  "couleur": "#B45309", "icone": "🔴", "action": "Mise en demeure",         "canal": "Courrier"},
    {"code": "contentieux", "label": "5 — Contentieux",      "couleur": "#111827", "icone": "⚫", "action": "Transmission à l'avocat", "canal": "Avocat"},
]
URG = {n["code"]: n["couleur"] for n in URGENCE}
NIV_LABELS = [n["label"] for n in URGENCE]
NIV_ACTIONS = [n["action"] for n in URGENCE]
ICONES = {n["label"]: n["icone"] for n in URGENCE}
COLORS = {n["label"]: n["couleur"] for n in URGENCE}
COLORS["À jour"] = "#64748B"
COLORS["Payée"] = THEME["paiement"]
ICONES["À jour"] = "⚪"
ICONES["Payée"] = "🟢"

CYAN = THEME["paiement"]
VIOLET = THEME["ia"]

PAGES = [
    "🏠 Tableau de bord", "👥 Clients", "🧾 Factures", "📨 Fiche & message",
    "📈 Analyses", "💧 Trésorerie", "📅 Calendrier", "🤖 Cashy — Assistant IA",
    "🗂️ Historique & preuves", "⚙️ Réglages",
]


def mode_sombre():
    """Suit le thème choisi par l'utilisateur dans Streamlit (⋮ → Settings → Theme).

    On ne force pas un thème maison : les tableaux, champs et menus Streamlit
    garderaient leurs couleurs natives et deviendraient illisibles sur un fond
    sombre. En suivant le thème natif, toute l'interface reste cohérente.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def injecter_css():
    dark = mode_sombre()
    fond = "#0B1220" if dark else "#F7F9FC"
    carte = "#111C2E" if dark else "#FFFFFF"
    texte = "#E5E7EB" if dark else "#0F172A"
    sous = "#94A3B8" if dark else "#475569"
    bord = "#1E293B" if dark else "#E2E8F0"
    ombre = "rgba(0,0,0,.45)" if dark else "rgba(15,23,42,.07)"
    css = """
    <style>
    html, body, [class*="css"] {
        font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
    }
    .stApp { background: __FOND__; color: __TEXTE__; }
    .block-container { padding-top: 2.4rem; padding-bottom: 3.5rem; max-width: 1180px; }
    h1 { letter-spacing: -1px; font-weight: 800; }
    h2, h3 { letter-spacing: -.4px; }
    .carte { background: __CARTE__; border: 1px solid __BORD__; border-radius: 18px;
             padding: 18px 20px; margin-bottom: 12px;
             box-shadow: 0 8px 28px __OMBRE__; }
    .carte h4 { margin: 0 0 6px 0; font-size: .72rem; letter-spacing: .09em;
                text-transform: uppercase; color: __SOUS__; font-weight: 700; }
    .carte .valeur { font-size: 1.65rem; font-weight: 800; letter-spacing: -.6px; color: __TEXTE__; }
    .carte .note { font-size: .8rem; color: __SOUS__; margin-top: 2px; }
    .badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
             font-size: .78rem; font-weight: 700; color: #fff; }
    .lead { color: __SOUS__; font-size: 0.95rem; }
    .petit { font-size: 0.78rem; color: __SOUS__; }
    .marque { color: __MARQUE__; }
    .pill-ia { display: inline-block; padding: 3px 12px; border-radius: 999px;
               font-size: .75rem; font-weight: 700; color: #7C3AED;
               background: rgba(124,58,237,.10); border: 1px solid rgba(124,58,237,.35);
               margin-bottom: 6px; }
    [data-testid="stMetric"] { background: __CARTE__; border: 1px solid __BORD__;
        border-radius: 16px; padding: 14px 18px; box-shadow: 0 8px 28px __OMBRE__; }
    [data-testid="stMetricValue"] { font-size: 1.85rem; font-weight: 800; letter-spacing: -.7px; }
    [data-testid="stMetricLabel"] { text-transform: uppercase; letter-spacing: .08em;
        font-size: .70rem; opacity: .8; }
    .stButton > button { border-radius: 12px; font-weight: 650; padding: .5rem 1rem; }
    [data-testid="stExpander"] { border-radius: 14px; }
    [data-testid="stSidebar"] { border-right: 1px solid __BORD__; }
    section[data-testid="stSidebar"] { background: __CARTE__; }
    </style>
    """
    css = (css.replace("__FOND__", fond).replace("__CARTE__", carte)
              .replace("__TEXTE__", texte).replace("__SOUS__", sous)
              .replace("__BORD__", bord).replace("__OMBRE__", ombre)
              .replace("__MARQUE__", THEME["marque"]))
    st.markdown(css, unsafe_allow_html=True)


def _layout(fig, height=320, titre=None):
    dark = mode_sombre()
    fig.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=height, margin=dict(l=10, r=10, t=45 if titre else 15, b=10),
        title=titre, font=dict(color="#E5E7EB" if dark else "#0F172A"),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def badge(niveau):
    col = COLORS.get(niveau, "#64748B")
    ico = ICONES.get(niveau, "")
    return (f"<span class='badge' style='background:{col}'>{ico} {niveau}</span>")


# ============================================================
#  ÉTAT
# ============================================================
try:
    _cle_secret = st.secrets.get("ANTHROPIC_API_KEY", "")
    _modele_secret = st.secrets.get("ANTHROPIC_MODEL", "")
except Exception:
    _cle_secret, _modele_secret = "", ""

DEFAULT_STATE = {
    "societe": "Ma Société",
    "seuil_1": 1, "seuil_2": 8, "seuil_3": 15, "seuil_4": 30, "seuil_5": 60,
    "poids_retard": 40, "poids_montant": 25, "poids_hist": 20, "poids_risque": 15,
    "ton": "bienveillant", "langue": "français",
    "utilisateur": "Karim", "onboarding_done": False,
    "api_key": _cle_secret, "model": _modele_secret or "claude-sonnet-4-5",
    "factures": [], "historique": [], "messages": {}, "recos": {}, "chat": [],
    "filtre_niveau": None, "date_ref": date.today(), "next_id": 1,
    "navpage": "🏠 Tableau de bord",
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
        ("Atlas SARL", "F-007", 12000, 38, "0612345678", "atlas@mail.ma", 3),
        ("Clinique Anouar", "F-008", 18000, 95, "0623456789", "compta@anouar.ma", 2),
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
#  LOGIQUE MÉTIER
# ============================================================
def fmt_mad(x):
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " MAD"


def fmt_court(x):
    if abs(x) >= 1_000_000:
        return f"{x/1_000_000:.1f} M"
    if abs(x) >= 1000:
        return f"{x/1000:.0f} k"
    return f"{x:.0f}"


def seuils():
    return [st.session_state.seuil_1, st.session_state.seuil_2,
            st.session_state.seuil_3, st.session_state.seuil_4, st.session_state.seuil_5]


def niveau_index(jours, s=None):
    """Index 0-4 du niveau atteint, ou -1 si à jour."""
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
    s = s or seuils()
    i = niveau_index(jours, s)
    ni = i + 1
    if ni > 4:
        return None, None
    return NIV_LABELS[ni], s[ni] - jours


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
    if not SKLEARN:
        return None
    payees = [f for f in st.session_state.factures
              if f.get("statut") == "Payée" and f.get("date_paiement")]
    if len(payees) < 12:
        return None
    try:
        X, y = [], []
        for f in payees:
            dp = f["date_paiement"]
            if isinstance(dp, str):
                dp = datetime.strptime(dp, "%Y-%m-%d").date()
            retard_regle = max(0, (dp - f["echeance"]).days)
            X.append([retard_regle, f.get("nb_retards", 0)])
            y.append(1 if retard_regle <= 30 else 0)
        if len(set(y)) < 2:
            return None
        return LogisticRegression(max_iter=500).fit(X, y)
    except Exception:
        return None


def predire(f, jours, model=None):
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
        rows.append({**f, "jours_retard": jours, "niveau": niv, "score": score,
                     "p7": pred["p7"], "p15": pred["p15"], "p30": pred["p30"],
                     "date_probable": pred["date_probable"], "profil": pred["profil"]})
    df = pd.DataFrame(rows)
    return df.sort_values(["statut", "score"], ascending=[True, False])


def explication(f, df):
    jours = f["jours_retard"]
    montants = df[df["statut"] != "Payée"]["montant"].tolist() or [f["montant"]]
    pct = sum(1 for m in montants if m < f["montant"]) / len(montants)
    top = "top 10 %" if pct >= 0.9 else ("top 25 %" if pct >= 0.75 else "montant moyen")
    return (f"Score {int(f['score'])} : retard de {int(jours)} jours, {top} des montants, "
            f"{int(f.get('nb_retards', 0))} retard(s) passé(s), probabilité de paiement 30 j : "
            f"{f['p30']*100:.0f} %.")


# ============================================================
#  MESSAGES — gabarits + IA
# ============================================================
def _montant_txt(f):
    return fmt_mad(f["montant"]).replace(" MAD", "")


FORMULES = {
    "français": {
        "bienveillant": {
            "ouverture": "Bonjour {client}, nous espérons que tout va bien.",
            "relance": "Si un échelonnement vous aidait, parlons-en : nous préférons trouver une solution amiable.",
            "cloture": "Bien cordialement,",
        },
        "neutre": {
            "ouverture": "Bonjour {client},",
            "relance": "Merci de nous confirmer la date de règlement.",
            "cloture": "Cordialement,",
        },
        "ferme": {
            "ouverture": "Madame, Monsieur,",
            "relance": "Sans règlement dans le délai indiqué, nous engagerons la procédure prévue, sans nouvelle relance.",
            "cloture": "Veuillez agréer, Madame, Monsieur, nos salutations distinguées.",
        },
    },
    "anglais": {
        "bienveillant": {
            "ouverture": "Hello {client}, we hope you are well.",
            "relance": "If a payment plan would help, let us know — we would rather find an amicable solution.",
            "cloture": "Kind regards,",
        },
        "neutre": {
            "ouverture": "Dear {client},",
            "relance": "Please confirm the payment date.",
            "cloture": "Regards,",
        },
        "ferme": {
            "ouverture": "Dear Sir or Madam,",
            "relance": "If payment is not received within the stated deadline, we will start the formal procedure without further notice.",
            "cloture": "Yours faithfully,",
        },
    },
    "arabe": {
        "bienveillant": {
            "ouverture": "مرحبا {client}، نأمل أن تكون بخير.",
            "relance": "إذا كان التقسيط يساعدكم، أخبرونا؛ نفضل حلاً ودياً.",
            "cloture": "مع تحياتنا،",
        },
        "neutre": {
            "ouverture": "مرحبا {client}،",
            "relance": "المرجو تأكيد تاريخ الأداء.",
            "cloture": "وتقبلوا فائق الاحترام،",
        },
        "ferme": {
            "ouverture": "السيد(ة) المحترم(ة)،",
            "relance": "في حال عدم الأداء داخل الأجل المحدد، سنباشر الإجراء القانوني دون إشعار آخر.",
            "cloture": "وتقبلوا فائق الاحترام،",
        },
    },
}


def _formule(langue, ton, cle, client=""):
    langues = FORMULES.get(langue, FORMULES["français"])
    return langues.get(ton, langues["neutre"])[cle].format(client=client)


def gabarit(niveau_label, f, ton, langue):
    eche = f["echeance"].strftime("%d/%m/%Y")
    jours = int(f["jours_retard"])
    soc = st.session_state.societe
    m = _montant_txt(f)
    if langue == "anglais":
        base = {
            "1 — Rappel": f"Invoice {f['numero']} of {m} MAD (due {eche}) is {jours} days overdue.",
            "2 — Contact": (f"CALL SCRIPT — {f['client']} ({f.get('telephone','')}).\n"
                            f"1. Introduce yourself and mention invoice {f['numero']} ({m} MAD, due {eche}, {jours} days late).\n"
                            f"2. Listen to the reason.\n3. Offer immediate payment or a dated promise.\n"
                            f"4. Confirm the commitment in writing."),
            "3 — Relance": (f"Subject: Overdue invoice {f['numero']} — {m} MAD\n\n"
                            f"Invoice {f['numero']} of {m} MAD, due on {eche}, is {jours} days overdue. "
                            f"Please settle it within 7 days, otherwise the file moves to the next step."),
            "4 — Mise en demeure": (f"FORMAL NOTICE — invoice {f['numero']}\n\n"
                                    f"To {f['client']}: please pay {m} MAD within 8 days (invoice due {eche}, "
                                    f"{jours} days late). Otherwise the file will be transferred to our lawyer, "
                                    f"together with interest and costs. Done on "
                                    f"{st.session_state.date_ref.strftime('%d/%m/%Y')}.\n"
                                    f"⚠️ Draft — legal review required."),
            "5 — Contentieux": (f"CASE FOR OUR LAWYER — {f['client']} / invoice {f['numero']}\n"
                                f"Phone: {f.get('telephone','')} — Email: {f.get('email','')}\n"
                                f"Claim: {m} MAD, due {eche} ({jours} days). Previous late payments: {f.get('nb_retards',0)}.\n"
                                f"Attachments: invoice, reminders, formal notice. ⚠️ Draft to be validated."),
        }
    elif langue == "arabe":
        base = {
            "1 — Rappel": f"الفاتورة {f['numero']} بمبلغ {m} درهم (تاريخ الاستحقاق {eche}) متأخرة بـ {jours} يوماً.",
            "2 — Contact": (f"سكريبت المكالمة — {f['client']} ({f.get('telephone','')}).\n"
                            f"1. التعريف بالنفس وذكر الفاتورة {f['numero']} ({m} درهم، استحقاق {eche}، تأخر {jours} يوماً).\n"
                            f"2. الاستماع إلى السبب.\n3. اقتراح الأداء الفوري أو وعد مؤرخ.\n"
                            f"4. تأكيد الالتزام كتابياً."),
            "3 — Relance": (f"الموضوع: الفاتورة {f['numero']} غير مسددة — {m} درهم\n\n"
                            f"الفاتورة {f['numero']} بمبلغ {m} درهم، المستحقة في {eche}، متأخرة بـ {jours} يوماً. "
                            f"المرجو التسوية خلال 7 أيام، وإلا سينتقل الملف إلى المرحلة الموالية."),
            "4 — Mise en demeure": (f"إنذار بالدفع — الفاتورة {f['numero']}\n\n"
                                    f"{f['client']}: المرجو أداء {m} درهم خلال 8 أيام (الفاتورة المستحقة في {eche}، "
                                    f"تأخر {jours} يوماً). وإلا سيحال الملف على محامينا مع الفوائد والمصاريف. "
                                    f"حرر بتاريخ {st.session_state.date_ref.strftime('%d/%m/%Y')}.\n"
                                    f"⚠️ مسودة — تستلزم مراجعة قانونية."),
            "5 — Contentieux": (f"ملف للمحامي — {f['client']} / الفاتورة {f['numero']}\n"
                                f"الهاتف: {f.get('telephone','')} — البريد: {f.get('email','')}\n"
                                f"المبلغ: {m} درهم، الاستحقاق {eche} ({jours} يوماً). التأخرات السابقة: {f.get('nb_retards',0)}.\n"
                                f"الوثائق: الفاتورة، التذكيرات، الإنذار. ⚠️ مسودة تستلزم المصادقة."),
        }
    else:
        base = {
            "1 — Rappel": (f"La facture {f['numero']} de {m} MAD (échéance {eche}) reste impayée "
                           f"({jours} jours de retard)."),
            "2 — Contact": (f"SCRIPT D'APPEL — {f['client']} ({f.get('telephone','')})\n"
                            f"1. Se présenter : « Bonjour, {soc}, au sujet de la facture {f['numero']} de {m} MAD, "
                            f"échue le {eche} ({jours} j de retard). »\n"
                            f"2. Écouter le motif (oubli / litige / trésorerie).\n"
                            f"3. Proposer : paiement immédiat ou promesse datée.\n"
                            f"4. Conclure : « Je note votre engagement et vous envoie un récapitulatif. »\n"
                            f"5. Noter l'action comme faite dans l'application."),
            "3 — Relance": (f"Objet : Facture {f['numero']} impayée — {m} MAD\n\n"
                            f"Notre facture {f['numero']} de {m} MAD, échue le {eche}, soit {jours} jours de retard, "
                            f"reste impayée. Sans règlement sous 7 jours, nous engagerons une mise en demeure."),
            "4 — Mise en demeure": (f"MISE EN DEMEURE — facture {f['numero']}\n\n"
                                    f"{f['client']}\n\nMise en demeure de payer {m} MAD (facture du {eche}, "
                                    f"{jours} jours de retard) sous 8 jours. À défaut, transmission à notre avocat "
                                    f"avec intérêts et frais. Fait le {st.session_state.date_ref.strftime('%d/%m/%Y')}.\n"
                                    f"⚠️ Brouillon : validation juriste requise."),
            "5 — Contentieux": (f"NOTE À L'AVOCAT — {f['client']} / facture {f['numero']}\n"
                                f"Tél : {f.get('telephone','')} — Email : {f.get('email','')}\n"
                                f"Créance : {m} MAD, échéance {eche} ({jours} j). Antécédents : {f.get('nb_retards',0)} retard(s).\n"
                                f"Pièces : facture, relances, mise en demeure. ⚠️ Brouillon à valider."),
        }
    corps = base.get(niveau_label, "Aucune action requise.")
    if niveau_label == "5 — Contentieux":
        # La note à l'avocat est un document interne : pas de formule de politesse.
        return corps
    ouverture = _formule(langue, ton, "ouverture", f["client"])
    relance = _formule(langue, ton, "relance")
    cloture = _formule(langue, ton, "cloture")
    return f"{ouverture}\n\n{corps}\n\n{relance}\n\n{cloture}\n{soc}"


def controle_juridique(texte, niveau_label):
    """Vérifie les mentions attendues avant d'envoyer une mise en demeure.

    Ce n'est pas un avis juridique : c'est un garde-fou qui empêche d'envoyer
    un courrier incomplet (montant, référence, délai, date, créancier).
    """
    attendus = [
        ("Référence de la facture", any(x in texte for x in ("facture", "invoice", "الفاتورة"))),
        ("Montant dû", "MAD" in texte or "درهم" in texte),
        ("Délai de paiement", any(x in texte for x in ("jours", "days", "أيام"))),
        ("Date du courrier", st.session_state.date_ref.strftime("%Y") in texte
         or st.session_state.date_ref.strftime("%d/%m/%Y") in texte),
        ("Identité du créancier", st.session_state.societe in texte),
        ("Qualification « mise en demeure »",
         any(x in texte.lower() for x in ("mise en demeure", "formal notice", "إنذار"))),
    ]
    if niveau_label == "5 — Contentieux":
        attendus.append(("Transmission au conseil",
                         any(x in texte.lower() for x in ("avocat", "lawyer", "محامي"))))
    return attendus


def appel_claude(prompt, system=None, max_tokens=700):
    key = st.session_state.get("api_key", "").strip()
    if not key:
        return None
    model = st.session_state.get("model", "claude-sonnet-4-5")
    system = system or ("Tu es l'assistant de recouvrement de la société "
                        f"{st.session_state.societe}. Réponds en {st.session_state.langue}, ton {st.session_state.ton}. "
                        "Sois concis, professionnel et respectueux. N'invente aucune donnée.")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    except Exception:
        pass
    try:
        import requests
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60)
        r.raise_for_status()
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", []))
    except Exception as e:
        st.session_state["last_llm_error"] = str(e)
        return None


def generer_message(f, niveau_label, variante=0):
    fid = f["id"]
    if st.session_state.get("api_key", "").strip():
        prompt = (
            f"Rédige le message de relance de niveau « {niveau_label} » "
            f"({NIV_ACTIONS[NIV_LABELS.index(niveau_label)] if niveau_label in NIV_LABELS else ''}).\n"
            f"Client : {f['client']}\nN° facture : {f['numero']}\nMontant : {f['montant']:.2f} MAD\n"
            f"Échéance : {f['echeance'].strftime('%d/%m/%Y')}\nJours de retard : {int(f['jours_retard'])}\n"
            f"Retards passés du client : {f.get('nb_retards',0)}\nProfil estimé : {f.get('profil','')}.\n"
            f"Ton demandé : {st.session_state.ton}. Langue : {st.session_state.langue}.\n"
            f"Requête n°{variante+1} : propose une {'nouvelle variante' if variante else 'rédaction'} prête à copier. "
            f"Pour une mise en demeure, inclus les mentions légales indispensables et l'avertissement de validation juridique."
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
                "nb_retards": nb, "statut": "Impayée", "date_paiement": None})
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
        moy, sd = imp["montant"].mean(), imp["montant"].std()
        for _, r in imp.iterrows():
            if sd and sd > 0 and r["montant"] > moy + 3 * sd:
                a.append(f"Montant inhabituel : {r['numero']} ({fmt_mad(r['montant'])})")
            if r["jours_retard"] > 730:
                a.append(f"Échéance incohérente : {r['numero']} ({int(r['jours_retard'])} j)")
            if not r.get("telephone") and not r.get("email"):
                a.append(f"Coordonnées manquantes : {r['numero']}")
    return a


# ============================================================
#  ANALYTIQUE
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
            dp = f.get("date_paiement")
            if isinstance(dp, str):
                try:
                    dp = datetime.strptime(dp, "%Y-%m-%d").date()
                except Exception:
                    dp = None
            paye_avant = f["statut"] == "Payée" and dp is not None and dp <= d
            encore_du = f["statut"] != "Payée" or (dp is not None and dp > d)
            if not paye_avant and f["echeance"] < d and encore_du:
                tot += f["montant"]; n += 1
        rows.append({"semaine": d.strftime("%d/%m"), "montant": tot, "nombre": n})
    return pd.DataFrame(rows)


def simulateur(df, horizon, scenario="realiste", facteur=1.0):
    if df.empty:
        return 0.0
    imp = df[df["statut"] != "Payée"]
    tot = 0.0
    for _, f in imp.iterrows():
        p = f["p7"] if horizon <= 7 else (f["p15"] if horizon <= 30 else f["p30"])
        if scenario == "optimiste":
            p = min(1.0, p * 1.25)
        elif scenario == "prudent":
            p = p * 0.7
        p = min(1.0, max(0.0, p * facteur))
        tot += f["montant"] * p
    return tot


def clients_agg(df):
    if df.empty:
        return pd.DataFrame()
    act = df[df["statut"] != "Payée"]
    if act.empty:
        return pd.DataFrame()
    g = act.groupby("client").agg(
        factures=("numero", "count"),
        montant=("montant", "sum"),
        retard_moyen=("jours_retard", "mean"),
        score_max=("score", "max"),
        p30=("p30", "mean"),
    ).reset_index()
    prof = act.groupby("client")["profil"].agg(lambda s: s.mode().iat[0] if not s.mode().empty else "—")
    tel = act.groupby("client")["telephone"].agg(lambda s: next((x for x in s if x), ""))
    mail = act.groupby("client")["email"].agg(lambda s: next((x for x in s if x), ""))
    g = g.merge(prof.rename("profil"), on="client", how="left")
    g = g.merge(tel.rename("telephone"), on="client", how="left")
    g = g.merge(mail.rename("email"), on="client", how="left")
    return g.sort_values(["score_max", "montant"], ascending=False)


def donnees_calendrier(df, annee, mois):
    """dict jour -> (montant, index niveau max, nb factures)."""
    out = {}
    if df.empty:
        return out
    imp = df[df["statut"] != "Payée"]
    dref = st.session_state.date_ref
    for _, r in imp.iterrows():
        e = r["echeance"]
        if e.year == annee and e.month == mois:
            i = niveau_index((dref - e).days)
            prev = out.get(e.day, (0.0, -1, 0))
            out[e.day] = (prev[0] + r["montant"], max(prev[1], i), prev[2] + 1)
    return out


def encaissement_cumule(df):
    horizons = [0, 7, 15, 30, 60, 90]
    vals = [0.0] + [simulateur(df, h) for h in horizons[1:]]
    return horizons, vals


def briefing_local(df):
    if df.empty:
        return "Aucune facture enregistrée."
    imp = df[df["statut"] != "Payée"]
    retard = imp[imp["jours_retard"] > 0]
    if retard.empty:
        return f"Aucune facture en retard aujourd'hui. {len(imp)} facture(s) à venir."
    lignes = [f"**Briefing du {st.session_state.date_ref.strftime('%d/%m/%Y')}**",
              f"- {len(retard)} facture(s) en retard pour {fmt_mad(retard['montant'].sum())}.",
              f"- Retard moyen : {retard['jours_retard'].mean():.0f} jours.",
              f"- Encaissement prévu à 30 j : {fmt_mad(simulateur(df, 30))}.",
              "- À traiter en priorité :"]
    for _, r in retard.sort_values("score", ascending=False).head(3).iterrows():
        lignes.append(f"  - {r['numero']} · {r['client']} · {fmt_mad(r['montant'])} · "
                      f"{int(r['jours_retard'])} j · score {int(r['score'])}")
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
        return (f"Encaissement prévu — 7 j : {fmt_mad(simulateur(df, 7))}\n"
                f"30 j : {fmt_mad(simulateur(df, 30))}\n"
                f"90 j : {fmt_mad(simulateur(df, 90))}")
    return ("Assistant en mode local (sans clé API). Ajoutez une clé Claude dans Réglages. "
            "Exemples : « Quelles factures ce matin ? », « Quel client me doit le plus ? ».")


# ============================================================
#  13 GRAPHIQUES
# ============================================================
def g_entonnoir(df):
    rep = df["niveau"].value_counts().reindex(NIV_LABELS, fill_value=0) if not df.empty else pd.Series([0] * 5, index=NIV_LABELS)
    fig = go.Figure(go.Funnel(y=NIV_LABELS, x=[int(rep[l]) for l in NIV_LABELS],
                              marker={"color": [COLORS[l] for l in NIV_LABELS]},
                              textinfo="value"))
    return _layout(fig, 300, "Entonnoir des cinq niveaux")


def g_evolution(df):
    serie = serie_retard(df, 10)
    if serie.empty:
        return None
    fig = px.area(serie, x="semaine", y="montant", labels={"semaine": "", "montant": "MAD"})
    fig.update_traces(line_color=THEME["marque"], fillcolor="rgba(11,31,58,0.15)")
    return _layout(fig, 300, "Évolution du retard (10 semaines)")


def g_bar_niveaux(df):
    rep = df["niveau"].value_counts().reindex(NIV_LABELS, fill_value=0) if not df.empty else pd.Series([0] * 5, index=NIV_LABELS)
    mont = df.groupby("niveau")["montant"].sum().reindex(NIV_LABELS, fill_value=0) if not df.empty else pd.Series([0] * 5, index=NIV_LABELS)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=NIV_LABELS, y=[int(rep[l]) for l in NIV_LABELS], name="Factures",
                         marker_color=[COLORS[l] for l in NIV_LABELS], yaxis="y"))
    fig.add_trace(go.Bar(x=NIV_LABELS, y=[float(mont[l]) for l in NIV_LABELS], name="Montant (MAD)",
                         marker_color=THEME["paiement"], opacity=0.55, yaxis="y2"))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
    return _layout(fig, 320, "Volume et montant par niveau")


def g_jauge(score, niveau):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=int(score),
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": COLORS.get(niveau, "#64748B")},
               "steps": [{"range": [0, 25], "color": "#DCFCE7"},
                         {"range": [25, 50], "color": "#ECFCCB"},
                         {"range": [50, 75], "color": "#FEF3C7"},
                         {"range": [75, 100], "color": "#FEE2E2"}]}))
    return _layout(fig, 230)


def g_frise(f):
    """Frise chronologique des étapes (dates = échéance + seuil)."""
    s = seuils()
    eche = f["echeance"]
    dates = [eche + timedelta(days=s[i]) for i in range(5)]
    ci = niveau_index(int(f["jours_retard"]))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=[1] * 5, mode="lines", line=dict(color="#CBD5E1", width=3), hoverinfo="skip"))
    for i, (d, lab) in enumerate(zip(dates, NIV_LABELS)):
        fig.add_trace(go.Scatter(
            x=[d], y=[1], mode="markers+text",
            marker=dict(size=26 if i == ci else 16, color=COLORS[lab],
                        line=dict(color="#FFFFFF" if i == ci else "rgba(0,0,0,0)", width=3)),
            text=[ICONES[lab]], textposition="middle center",
            name=lab, hovertemplate=f"{lab}<br>%{{x|%d/%m/%Y}}<extra></extra>"))
    return _layout(fig, 200, "Frise des étapes")


def g_top_clients(cl):
    if cl.empty:
        return None
    t = cl.head(8).sort_values("montant")
    fig = go.Figure(go.Bar(x=t["montant"], y=t["client"], orientation="h",
                           marker_color=THEME["marque"], text=[fmt_court(v) + " MAD" for v in t["montant"]],
                           textposition="outside"))
    return _layout(fig, 340, "Top clients par montant dû")


def g_heatmap(df):
    if df.empty:
        return None
    act = df[df["statut"] != "Payée"]
    if act.empty:
        return None
    top = act.groupby("client")["montant"].sum().sort_values(ascending=False).head(12).index
    p = act[act["client"].isin(top)].pivot_table(index="client", columns="niveau",
                                                 values="montant", aggfunc="sum", fill_value=0)
    order = [l for l in NIV_LABELS if l in p.columns]
    p = p.reindex(index=list(top), columns=order, fill_value=0)
    fig = go.Figure(go.Heatmap(z=p.values, x=p.columns, y=p.index,
                               colorscale=[[0, "#F1F5F9"], [0.25, "#CA8A04"],
                                           [0.6, "#B45309"], [1, "#111827"]],
                               text=[[fmt_court(v) for v in row] for row in p.values],
                               texttemplate="%{text}", hovertemplate="%{y} · %{x}<br>%{z:,.0f} MAD<extra></extra>"))
    return _layout(fig, 380, "Carte de chaleur clients × niveaux (MAD)")


def g_donut(df):
    if df.empty:
        return None
    act = df[df["statut"] != "Payée"]
    if act.empty:
        return None
    g = act.groupby("profil")["montant"].sum().reset_index()
    couleurs = {"Bon payeur": "#16A34A", "Distrait": "#0EA5E9", "Lent mais fiable": "#CA8A04",
                "Récidiviste": "#B45309", "À risque": "#111827"}
    fig = px.pie(g, names="profil", values="montant", hole=0.55,
                 color="profil", color_discrete_map=couleurs)
    fig.update_traces(textinfo="label+percent")
    return _layout(fig, 340, "Répartition par profil client")


def g_scatter(df):
    if df.empty:
        return None
    act = df[df["statut"] != "Payée"].copy()
    if act.empty:
        return None
    act["_taille"] = act["score"].clip(lower=5)
    fig = px.scatter(act, x="jours_retard", y="montant", color="niveau", size="_taille",
                     hover_name="client", color_discrete_map=COLORS,
                     labels={"jours_retard": "Jours de retard", "montant": "Montant (MAD)"})
    return _layout(fig, 360, "Montant × retard (taille = score)")


def g_histo(df):
    if df.empty:
        return None
    act = df[(df["statut"] != "Payée") & (df["jours_retard"] > 0)]
    if act.empty:
        return None
    fig = px.histogram(act, x="jours_retard", color="niveau", nbins=20,
                       color_discrete_map=COLORS, barmode="stack",
                       labels={"jours_retard": "Jours de retard", "count": "Factures"})
    return _layout(fig, 340, "Distribution des retards")


def g_cascade(df, facteur=1.0):
    total = float(df[df["statut"] != "Payée"]["montant"].sum()) if not df.empty else 0.0
    e7, e15, e30, e90 = (simulateur(df, h, facteur=facteur) for h in (7, 15, 30, 90))
    mesures = ["Impayé total", "≤ 7 j", "≤ 15 j", "≤ 30 j", "≤ 90 j", "Reste à risque"]
    valeurs = [total, -e7, -(e15 - e7), -(e30 - e15), -(e90 - e30), 0]
    fig = go.Figure(go.Waterfall(
        x=mesures, y=valeurs, measure=["absolute", "relative", "relative", "relative", "relative", "total"],
        text=[fmt_court(v) for v in [total, e7, e15 - e7, e30 - e15, e90 - e30, total - e90]],
        textposition="outside",
        connector={"line": {"color": "#94A3B8"}},
        increasing={"marker": {"color": THEME["marque"]}},
        decreasing={"marker": {"color": THEME["paiement"]}},
        totals={"marker": {"color": THEME["alerte"]}}))
    return _layout(fig, 380, "Cascade d'encaissement prévue")


def g_encaisse_cumule(df):
    h, v = encaissement_cumule(df)
    fig = go.Figure(go.Scatter(x=h, y=v, mode="lines+markers", fill="tozeroy",
                               line=dict(color=THEME["paiement"], width=3),
                               marker=dict(size=8, color=THEME["paiement"]),
                               hovertemplate="%{x} j : %{y:,.0f} MAD<extra></extra>"))
    return _layout(fig, 340, "Encaissement cumulé attendu (90 j)")


def g_recupere(df):
    """Cumul des montants réellement récupérés (factures clôturées)."""
    total, d = argent_recupere(df)
    if d.empty:
        return None
    fig = go.Figure(go.Scatter(x=d["date_paiement"], y=d["cumul"], mode="lines+markers",
                               fill="tozeroy", line=dict(color=THEME["paiement"], width=3),
                               marker=dict(size=9, color=THEME["paiement"]),
                               hovertemplate="%{x|%d/%m/%Y} : %{y:,.0f} MAD<extra></extra>"))
    return _layout(fig, 320, "Argent récupéré grâce aux relances (cumul)")


def g_calendrier(df, annee, mois):
    cmap = donnees_calendrier(df, annee, mois)
    cal = calendar.Calendar(firstweekday=0)
    semaines = cal.monthdayscalendar(annee, mois)
    while len(semaines) < 6:
        semaines.append([0] * 7)
    semaines = semaines[:6]
    z, txt = [], []
    for sem in semaines:
        rz, rt = [], []
        for j in sem:
            if j == 0:
                rz.append(None); rt.append("")
            elif j in cmap:
                montant, idx, nb = cmap[j]
                rz.append(idx + 1 if idx >= 0 else 0.5)
                rt.append(f"{j}<br>{fmt_court(montant)}")
            else:
                rz.append(0); rt.append(str(j))
        z.append(rz); txt.append(rt)
    colorscale = [[0.00, "#EEF2F7"], [0.09, "#EEF2F7"],
                  [0.10, "#0EA5E9"], [0.19, "#0EA5E9"],
                  [0.20, "#16A34A"], [0.39, "#16A34A"],
                  [0.40, "#65A30D"], [0.59, "#65A30D"],
                  [0.60, "#CA8A04"], [0.79, "#CA8A04"],
                  [0.80, "#B45309"], [0.99, "#B45309"],
                  [1.00, "#111827"]]
    fig = go.Figure(go.Heatmap(z=z, x=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"],
                               y=[f"S{i+1}" for i in range(len(z))], colorscale=colorscale,
                               zmin=0, zmax=5, showscale=False,
                               text=txt, texttemplate="%{text}", xgap=3, ygap=3,
                               hovertemplate="%{text}<extra></extra>"))
    fig.update_traces(textfont=dict(size=12, color="#0F172A"))
    return _layout(fig, 360, f"Calendrier des échéances — {calendar.month_name[mois]} {annee}")


# ============================================================
#  EXPÉRIENCE UTILISATEUR (accueil, animations, indicateurs)
# ============================================================
def _ui():
    """Couleurs d'interface cohérentes avec le thème actif."""
    dark = mode_sombre()
    return {
        "dark": dark,
        "carte": "#111C2E" if dark else "#FFFFFF",
        "texte": "#E5E7EB" if dark else "#0F172A",
        "sous": "#94A3B8" if dark else "#475569",
        "bord": "#1E293B" if dark else "#E2E8F0",
        "piste": "#1E293B" if dark else "#EDF2F7",
        "ombre": "rgba(0,0,0,.45)" if dark else "rgba(15,23,42,.07)",
    }


def compteur_anime(valeur, libelle="Impayé total", note=""):
    """Grand compteur qui s'incrémente à l'ouverture (JavaScript, sans dépendance)."""
    u = _ui()
    html = """
<div style="font-family:'Segoe UI',system-ui,sans-serif;background:CARTE;border:1px solid BORD;
     border-radius:18px;padding:16px 20px;box-shadow:0 8px 28px OM;height:150px;box-sizing:border-box">
  <div style="font-size:.70rem;letter-spacing:.09em;text-transform:uppercase;color:SOUS;font-weight:700">TITRE</div>
  <div id="val" style="font-size:clamp(1.5rem,3.1vw,2.35rem);font-weight:800;letter-spacing:-1.2px;
       color:TEXTE;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">0</div>
  <div style="font-size:.80rem;color:SOUS">NOTE</div>
</div>
<script>
(function(){
  var cible = CIBLE, el = document.getElementById('val'), debut = null, duree = 1300;
  function fmt(n){
    var s = new Intl.NumberFormat('fr-FR',{maximumFractionDigits:0}).format(n);
    return s.replace(/\\s|\\u202f/g, '\\u00A0') + '\\u00A0MAD';
  }
  function pas(t){
    if(!debut) debut = t;
    var p = Math.min(1,(t-debut)/duree), e = 1-Math.pow(1-p,3);
    el.textContent = fmt(Math.round(cible*e));
    if(p<1) requestAnimationFrame(pas);
  }
  requestAnimationFrame(pas);
})();
</script>
"""
    html = (html.replace("CARTE", u["carte"]).replace("BORD", u["bord"])
                .replace("TEXTE", u["texte"]).replace("SOUS", u["sous"])
                .replace("OM", u["ombre"]).replace("TITRE", libelle)
                .replace("NOTE", note).replace("CIBLE", f"{float(valeur):.0f}"))
    st.iframe(html, height=150)


def carte_sante(note, libelle, couleur):
    u = _ui()
    pct = max(0, min(100, int(note)))
    html = """
<div style="background:CARTE;border:1px solid BORD;border-radius:18px;padding:12px 14px;
     box-shadow:0 8px 28px OM;height:150px;box-sizing:border-box;display:flex;
     flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:4px">
  <div style="width:66px;height:66px;border-radius:50%;flex:0 0 66px;
       background:conic-gradient(COUL PCT%, PISTE 0);display:grid;place-items:center">
    <div style="width:50px;height:50px;border-radius:50%;background:CARTE;display:grid;
         place-items:center;font-size:1.05rem;font-weight:800;color:TEXTE">PCT</div>
  </div>
  <div style="font-size:.60rem;letter-spacing:.06em;text-transform:uppercase;color:SOUS;
       font-weight:700;line-height:1.2">Santé du portefeuille</div>
  <div style="font-size:.95rem;font-weight:800;color:TEXTE">LIB</div>
</div>
"""
    return (html.replace("CARTE", u["carte"]).replace("BORD", u["bord"])
                .replace("TEXTE", u["texte"]).replace("SOUS", u["sous"])
                .replace("OM", u["ombre"]).replace("PISTE", u["piste"])
                .replace("COUL", couleur).replace("PCT", str(pct)).replace("LIB", libelle))


def carte_progression(faites, total, pct, serie):
    u = _ui()
    html = """
<div style="background:CARTE;border:1px solid BORD;border-radius:18px;padding:12px 16px;
     box-shadow:0 8px 28px OM;height:150px;box-sizing:border-box">
  <div style="font-size:.64rem;letter-spacing:.07em;text-transform:uppercase;color:SOUS;font-weight:700">
    Relances de la semaine</div>
  <div style="font-size:1.25rem;font-weight:800;color:TEXTE;margin:1px 0 4px">PCT %</div>
  <div style="height:9px;border-radius:99px;background:PISTE;overflow:hidden">
    <div style="width:PCT%;height:9px;border-radius:99px;background:PAIEMENT"></div>
  </div>
  <div style="font-size:.74rem;color:SOUS;margin-top:5px">FAITES / TOTAL factures en retard traitées</div>
  <div style="margin-top:6px;font-size:.76rem;font-weight:700;color:FEU">🔥 SERIE jour(s) d'affilée</div>
</div>
"""
    return (html.replace("CARTE", u["carte"]).replace("BORD", u["bord"])
                .replace("TEXTE", u["texte"]).replace("SOUS", u["sous"])
                .replace("OM", u["ombre"]).replace("PISTE", u["piste"])
                .replace("PAIEMENT", THEME["paiement"]).replace("FEU", u["texte"])
                .replace("PCT", str(int(pct))).replace("FAITES", str(faites))
                .replace("TOTAL", str(total)).replace("SERIE", str(serie)))


def machine_a_ecrire(texte, cle=0):
    """Aperçu du message qui s'écrit en direct, avec bouton Copier."""
    u = _ui()
    texte_js = json.dumps(texte, ensure_ascii=False).replace("</", "<\\/")
    lignes = texte.count("\n") + len(texte) // 92 + 2
    hauteur = max(170, min(430, 58 + lignes * 21))
    html = """
<div style="font-family:'Segoe UI',system-ui,sans-serif;background:CARTE;border:1px solid BORD;
     border-radius:16px;padding:14px 16px;box-shadow:0 8px 28px OM;box-sizing:border-box">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
    <span style="font-size:.70rem;letter-spacing:.09em;text-transform:uppercase;color:SOUS;font-weight:700">
      Aperçu du message</span>
    <button id="cp" style="border:1px solid VIOLET;background:transparent;color:VIOLET;
      border-radius:9px;padding:4px 10px;font-size:.76rem;font-weight:700;cursor:pointer">Copier</button>
  </div>
  <pre id="txt" dir="auto" style="white-space:pre-wrap;word-wrap:break-word;margin:0;font-family:'JetBrains Mono',
    Consolas,monospace;font-size:.82rem;line-height:1.5;color:TEXTE"></pre>
</div>
<script>
(function(){
  var complet = TXT, el = document.getElementById('txt');
  var pas = Math.max(2, Math.floor(complet.length / 110)), i = 0;
  function ecrire(){
    el.textContent = complet.slice(0, i);
    i += pas;
    if(i <= complet.length) requestAnimationFrame(ecrire);
    else el.textContent = complet;
  }
  requestAnimationFrame(ecrire);
  document.getElementById('cp').onclick = async function(){
    try {
      await navigator.clipboard.writeText(complet);
      this.textContent = 'Copié';
    } catch (e) {
      var r = document.createRange(); r.selectNodeContents(el);
      var s = getSelection(); s.removeAllRanges(); s.addRange(r);
      this.textContent = 'Sélectionné : Ctrl+C';
    }
    setTimeout(() => { this.textContent = 'Copier'; }, 1800);
  };
})();
</script>
<!-- cle: CLE -->
"""
    html = (html.replace("CARTE", u["carte"]).replace("BORD", u["bord"])
                .replace("TEXTE", u["texte"]).replace("SOUS", u["sous"])
                .replace("OM", u["ombre"]).replace("VIOLET", THEME["ia"])
                .replace("TXT", texte_js).replace("CLE", str(cle)))
    st.iframe(html, height=hauteur)


def phrase_accueil(df):
    prenom = st.session_state.get("utilisateur") or ""
    prenom = f" {prenom}" if prenom else ""
    retard = df[(df["statut"] != "Payée") & (df["jours_retard"] > 0)] if not df.empty else pd.DataFrame()
    if retard.empty:
        return f"Bonjour{prenom}, aucun impayé en retard : belle journée pour prendre de l'avance."
    n = len(retard)
    semaine = simulateur(df, 7)
    return (f"Bonjour{prenom}, {n} facture{'s' if n > 1 else ''} à traiter aujourd'hui, "
            f"{fmt_mad(semaine)} attendus cette semaine.")


def sante_portefeuille(df):
    imp = df[df["statut"] != "Payée"] if not df.empty else pd.DataFrame()
    if imp.empty:
        return 100, "Excellent", URG["rappel"]
    part_retard = float((imp["jours_retard"] > 0).mean())
    p30 = float(imp["p30"].mean())
    anciennete = min(1.0, float(imp["jours_retard"].clip(lower=0).mean()) / 90)
    part_top = float(imp["montant"].max() / max(float(imp["montant"].sum()), 1))
    note = 100 * (0.35 * (1 - part_retard) + 0.35 * p30
                  + 0.20 * (1 - anciennete) + 0.10 * (1 - part_top))
    note = int(round(max(0, min(100, note))))
    if note >= 80:
        return note, "Excellent", URG["rappel"]
    if note >= 60:
        return note, "Correct", URG["contact"]
    if note >= 40:
        return note, "Fragile", URG["relance"]
    return note, "Critique", URG["miseendemeure"]


def _date_action(h):
    try:
        return datetime.strptime(h["date"], "%d/%m/%Y %H:%M").date()
    except Exception:
        return None


def progression_semaine(df):
    dref = st.session_state.date_ref
    debut = dref - timedelta(days=dref.weekday())
    cibles = set(df[(df["statut"] != "Payée") & (df["jours_retard"] > 0)]["numero"]) if not df.empty else set()
    if not cibles:
        return 0, 0, 100
    faites = {h["facture"] for h in st.session_state.historique
              if (d := _date_action(h)) and debut <= d <= dref}
    n = len(faites & cibles)
    return n, len(cibles), int(round(100 * n / len(cibles)))


def serie_jours():
    """Nombre de jours consécutifs (en remontant depuis aujourd'hui) avec au moins une action."""
    jours = {_date_action(h) for h in st.session_state.historique}
    jours.discard(None)
    if not jours:
        return 0
    d = st.session_state.date_ref
    if d not in jours:
        d -= timedelta(days=1)
    n = 0
    while d in jours:
        n += 1
        d -= timedelta(days=1)
    return n


def factures_oubliees(df):
    if df.empty:
        return 0
    faites = {h["facture"] for h in st.session_state.historique}
    retard = df[(df["statut"] != "Payée") & (df["jours_retard"] > 0)]
    return int((~retard["numero"].isin(faites)).sum())


def argent_recupere(df):
    if df.empty or "date_paiement" not in df.columns:
        return 0.0, pd.DataFrame()
    payees = df[(df["statut"] == "Payée") & df["date_paiement"].notna()].copy()
    if payees.empty:
        return 0.0, pd.DataFrame()
    payees["date_paiement"] = pd.to_datetime(payees["date_paiement"], errors="coerce")
    payees = payees.dropna(subset=["date_paiement"]).sort_values("date_paiement")
    if payees.empty:
        return 0.0, pd.DataFrame()
    payees["cumul"] = payees["montant"].cumsum()
    return float(payees["montant"].sum()), payees[["date_paiement", "client", "numero", "montant", "cumul"]]


# ============================================================
#  EXPORTS
# ============================================================
def _latin(txt):
    return str(txt).encode("latin-1", "replace").decode("latin-1")


def export_pdf(titre, df, sous_titre=""):
    if not FPDF_OK:
        return None
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _latin(titre)); pdf.ln(10)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, _latin(sous_titre or
                          f"{st.session_state.societe} — {datetime.now().strftime('%d/%m/%Y %H:%M')}")); pdf.ln(9)
    cols = list(df.columns)[:6]
    largeurs = {0: 200}
    w = int(190 / max(1, len(cols)))
    pdf.set_font("Helvetica", "B", 8)
    for c in cols:
        pdf.cell(w, 7, _latin(str(c))[:22], border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 7)
    for _, r in df.head(60).iterrows():
        for c in cols:
            pdf.cell(w, 6, _latin(str(r.get(c, "")))[:24], border=1)
        pdf.ln()
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(0, 4, _latin("Preuve generee par l'application. Modeles de mise en demeure et note a l'avocat : "
                                "brouillons a valider par un juriste. Donnees personnelles : loi 09-08 / CNDP."))
    return bytes(pdf.output())


def export_excel(feuilles):
    """Écrit plusieurs DataFrames dans un classeur Excel (une feuille chacun)."""
    try:
        from io import BytesIO

        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            for nom, donnees in feuilles.items():
                d = donnees if not donnees.empty else pd.DataFrame({"info": ["aucune donnée"]})
                d.to_excel(writer, sheet_name=nom[:31], index=False)
        return buffer.getvalue()
    except Exception:
        return None


def log_action(numero, client, niveau, action, canal="—"):
    st.session_state.historique.append({
        "date": datetime.now().strftime("%d/%m/%Y %H:%M"), "facture": numero,
        "client": client, "niveau": niveau, "canal": canal, "action": action})


# ============================================================
#  NAVIGATION
# ============================================================
def filtrer_niveau(lab):
    st.session_state.filtre_niveau = lab
    st.session_state["flt_niv_ml"] = [lab]
    st.session_state.navpage = "🧾 Factures"


def ouvrir_facture(fid):
    st.session_state["sel_facture"] = fid
    st.session_state.navpage = "📨 Fiche & message"


def aller(page):
    st.session_state.navpage = page


def lancer_relances():
    st.session_state["flt_niv_ml"] = []
    st.session_state.navpage = "🧾 Factures"


# ============================================================
#  SIDEBAR
# ============================================================
# Lien de démonstration partageable : ?demo=1 charge les données fictives.
if st.query_params.get("demo") == "1" and not st.session_state.factures:
    init_demo()
    st.session_state.onboarding_done = True

with st.sidebar:
    st.markdown(f"<div style='font-size:1.1rem;font-weight:800;color:{THEME['marque']}'>💰 Scoring des Impayés</div>",
                unsafe_allow_html=True)
    st.caption(st.session_state.societe)
    st.radio("Navigation", PAGES, key="navpage", label_visibility="collapsed")
    st.divider()
    st.caption(f"🌓 Thème : {'sombre' if mode_sombre() else 'clair'} — réglable dans ⋮ → Settings → Theme")
    st.session_state.date_ref = st.date_input("Date de référence", value=st.session_state.date_ref)
    st.divider()
    st.markdown("<div class='petit'>Échelle d'urgence</div>", unsafe_allow_html=True)
    for n in URGENCE:
        st.markdown(f"<div class='petit'>{n['icone']} <span style='color:{n['couleur']};font-weight:700'>■</span> {n['label']}</div>",
                    unsafe_allow_html=True)
    st.divider()
    if st.session_state.api_key:
        st.success("🤖 IA Claude active", icon="🤖")
    else:
        st.warning("IA en mode gabarits", icon="🤖")
    if not st.session_state.factures:
        if st.button("Charger la démo", width="stretch"):
            init_demo(); st.rerun()

# Le CSS est injecté après la barre latérale : le mode sombre est ainsi
# appliqué dès le premier rendu qui suit le clic, sans décalage d'un rerun.
injecter_css()

df = enrichir()
actives = df[df["statut"] != "Payée"] if not df.empty else pd.DataFrame()
en_retard = actives[actives["jours_retard"] > 0] if not actives.empty else pd.DataFrame()
clients = clients_agg(df)
page = st.session_state.navpage

if st.session_state.pop("_confettis", False):
    st.balloons()
    st.toast("Facture payée — bien joué !")


def entete(graphiques, donnees):
    st.caption(f"📊 **Graphiques :** {graphiques}  ·  🔑 **Données clés :** {donnees}")


# ============================================================
#  1. TABLEAU DE BORD
# ============================================================
if page == PAGES[0]:
    st.title("🏠 Tableau de bord")
    entete("entonnoir cliquable, évolution du retard, volume/montant par niveau, top 5 urgences",
           "impayé total, santé du portefeuille, relances de la semaine, encaissement prévu")

    if not st.session_state.onboarding_done:
        st.markdown(
            "<div class='carte' style='border-left:5px solid " + THEME["paiement"] + "'>"
            "<h4>Bienvenue — 3 étapes pour démarrer</h4>"
            "<div class='petit'>① Chargez vos factures (ou la démo) · ② Laissez le score trier par urgence · "
            "③ Relancez, copiez, gardez la preuve.</div></div>",
            unsafe_allow_html=True)
        o1, o2, _ = st.columns([1.5, 1, 1.5])
        if o1.button("🎬 Charger la démo", key="demo_onboarding", width="stretch"):
            if not st.session_state.factures:
                init_demo()
            st.session_state.onboarding_done = True
            st.rerun()
        if o2.button("C'est parti →", width="stretch"):
            st.session_state.onboarding_done = True
            st.rerun()

    total = float(en_retard["montant"].sum()) if not en_retard.empty else 0.0
    sante, sante_lib, sante_coul = sante_portefeuille(df)
    faites, cibles, pct = progression_semaine(df)
    recupere, _ = argent_recupere(df)

    st.markdown(f"<div style='font-size:1.05rem;color:inherit;margin:4px 0 14px'>"
                f"👋 <b>{phrase_accueil(df)}</b></div>", unsafe_allow_html=True)

    c1, c2 = st.columns([2, 1])
    with c1:
        compteur_anime(total, "Impayé total", f"{len(en_retard)} facture(s) en retard")
    with c2:
        st.markdown(carte_sante(sante, sante_lib, sante_coul), unsafe_allow_html=True)

    c3, c4 = st.columns([2, 1])
    with c3:
        st.markdown(carte_progression(faites, cibles, pct, serie_jours()), unsafe_allow_html=True)
    with c4:
        st.metric("Récupéré", fmt_mad(recupere),
                  help="Montant des factures marquées payées depuis l'ouverture de l'application.")

    st.write("")
    st.button("🚀 Commencer les relances", type="primary", width="stretch",
              on_click=lancer_relances)

    if actives.empty:
        st.markdown(
            "<div class='carte' style='text-align:center;padding:34px'>"
            "<div style='font-size:2rem'>🎉</div>"
            "<div style='font-size:1.05rem;font-weight:800;margin-top:6px'>Votre portefeuille est vide</div>"
            "<div class='petit' style='margin-top:4px'>Importez vos factures, ou chargez la démo pour "
            "découvrir l'application sans rien saisir.</div></div>",
            unsafe_allow_html=True)
        if st.button("🎬 Charger la démo", key="demo_vide", width="stretch"):
            init_demo()
            st.session_state.onboarding_done = True
            st.rerun()
    elif en_retard.empty:
        st.markdown(
            "<div class='carte' style='text-align:center;padding:34px'>"
            "<div style='font-size:2rem'>✅</div>"
            "<div style='font-size:1.05rem;font-weight:800;margin-top:6px'>Aucun impayé en retard</div>"
            "<div class='petit' style='margin-top:4px'>Tout est à jour : belle journée pour prendre de l'avance.</div>"
            "</div>", unsafe_allow_html=True)
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Factures en retard", len(en_retard))
        m2.metric("Retard moyen", f"{en_retard['jours_retard'].mean():.0f} jours")
        m3.metric("Encaissement prévu (30 j)", fmt_mad(simulateur(df, 30)))
        m4.metric("Factures oubliées", factures_oubliees(df),
                  delta="à traiter" if factures_oubliees(df) else "aucune", delta_color="inverse")

        if PLOTLY:
            a, b = st.columns(2)
            with a:
                evt = st.plotly_chart(g_entonnoir(en_retard), width="stretch",
                                      on_select="rerun", selection_mode="points",
                                      key="entonnoir")
                points = []
                try:
                    points = evt.selection.points
                except Exception:
                    try:
                        points = evt.get("selection", {}).get("points", [])
                    except Exception:
                        points = []
                niveau_clique = points[0].get("y") if points else None
                if niveau_clique in NIV_LABELS:
                    st.caption(f"Niveau sélectionné : **{niveau_clique}**")
                    st.button(f"Voir les factures « {niveau_clique} »", key="voir_funnel",
                              on_click=filtrer_niveau, args=(niveau_clique,))
                else:
                    st.caption("Cliquez sur une barre de l'entonnoir pour filtrer les factures de ce niveau.")
            with b:
                fig = g_evolution(df)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
            st.plotly_chart(g_bar_niveaux(en_retard), width="stretch")

        st.subheader("Top 5 urgences")
        for _, r in en_retard.sort_values("score", ascending=False).head(5).iterrows():
            with st.container(border=True):
                a, b = st.columns([5, 1])
                with a:
                    st.markdown(f"{badge(r['niveau'])} &nbsp; <b>{r['numero']}</b> · {r['client']} · "
                                f"{fmt_mad(r['montant'])} · {int(r['jours_retard'])} j",
                                unsafe_allow_html=True)
                    st.progress(int(r["score"]) / 100, text=f"Score {int(r['score'])}/100")
                with b:
                    st.button("Ouvrir", key=f"dash_{r['id']}", width="stretch",
                              on_click=ouvrir_facture, args=(int(r["id"]),))

# ============================================================
#  2. CLIENTS
# ============================================================
elif page == PAGES[1]:
    st.title("👥 Clients")
    entete("top clients par montant dû, répartition des profils",
           "montant dû, nb factures, retard moyen, score max, coordonnées")
    if clients.empty:
        st.info("Aucun client avec facture impayée.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Clients débiteurs", len(clients))
        c2.metric("Montant dû total", fmt_mad(clients["montant"].sum()))
        c3.metric("Concentration top 20 %", f"{(clients.head(max(1, len(clients)//5))['montant'].sum() / clients['montant'].sum() * 100):.0f} %")
        if PLOTLY:
            a, b = st.columns(2)
            with a:
                fig = g_top_clients(clients)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
            with b:
                fig = g_donut(df)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
        st.dataframe(
            clients.rename(columns={"client": "Client", "factures": "Factures", "montant": "Montant dû",
                                    "retard_moyen": "Retard moyen (j)", "score_max": "Score max",
                                    "p30": "P(30j)", "profil": "Profil",
                                    "telephone": "Téléphone", "email": "Email"}),
            width="stretch", hide_index=True,
            column_config={"P(30j)": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=1)})
        st.subheader("Détail d'un client")
        choix = st.selectbox("Client", clients["client"].tolist())
        cf = actives[actives["client"] == choix]
        for _, r in cf.iterrows():
            st.markdown(f"{badge(r['niveau'])} &nbsp; <b>{r['numero']}</b> · {fmt_mad(r['montant'])} · "
                        f"{int(r['jours_retard'])} j · score {int(r['score'])}", unsafe_allow_html=True)
        if st.button("Ouvrir la fiche de la 1re facture", on_click=ouvrir_facture,
                     args=(int(cf.iloc[0]["id"]),)) if not cf.empty else None:
            pass

# ============================================================
#  3. FACTURES
# ============================================================
elif page == PAGES[2]:
    st.title("🧾 Factures")
    entete("badges d'urgence, barres de score (liste) ; top clients et distribution dans Analyses",
           "n°, client, montant, échéance, niveau, score, profil")
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
            vue = vue.sort_values({"Score": "score", "Retard": "jours_retard", "Montant": "montant"}[tri], ascending=False)
            for _, r in vue.iterrows():
                with st.container(border=True):
                    a, b = st.columns([5, 1])
                    with a:
                        st.markdown(f"{badge(r['niveau'])} &nbsp; <b>{r['numero']}</b> · {r['client']} · "
                                    f"{fmt_mad(r['montant'])} · {int(r['jours_retard'])} j de retard",
                                    unsafe_allow_html=True)
                        st.progress(int(r["score"]) / 100,
                                    text=f"Score {int(r['score'])}/100 · {r['profil']} · P(30j) {r['p30']*100:.0f} %")
                    with b:
                        st.button("Ouvrir", key=f"open_{r['id']}", width="stretch",
                                  on_click=ouvrir_facture, args=(int(r["id"]),))
    with tab_ajout:
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
            if st.form_submit_button("Enregistrer"):
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
        st.caption("Colonnes reconnues : client, numero, montant, echeance, telephone, email, retards.")
        up = st.file_uploader("Fichier Excel / CSV", type=["csv", "xlsx", "xls"])
        if up is not None:
            try:
                d = pd.read_csv(up, sep=None, engine="python") if up.name.lower().endswith(".csv") else pd.read_excel(up)
                st.dataframe(d.head(20), width="stretch")
                if st.button("Importer ces lignes"):
                    n, an = importer_dataframe(d)
                    st.success(f"{n} facture(s) importée(s).")
                    if an:
                        st.warning("Anomalies :\n- " + "\n- ".join(an))
                    st.rerun()
            except Exception as e:
                st.error(f"Lecture impossible : {e}")
        st.divider()
        an = detecter_anomalies(df)
        if an:
            st.warning("\n".join("- " + x for x in an))
        else:
            st.success("Aucune anomalie détectée.")
        if not df.empty:
            st.download_button("⬇️ Exporter les factures (CSV)",
                               df.to_csv(index=False).encode("utf-8-sig"), "impayes.csv", "text/csv")

# ============================================================
#  4. FICHE & MESSAGE
# ============================================================
elif page == PAGES[3]:
    st.title("📨 Fiche & message")
    entete("jauge de score, frise chronologique des étapes",
           "niveau, score expliqué, prédiction, compte à rebours, message prêt")
    if actives.empty:
        st.info("Aucune facture impayée.")
    else:
        options = {f"{r['numero']} · {r['client']} · {fmt_mad(r['montant'])}": r["id"]
                   for _, r in actives.sort_values("score", ascending=False).iterrows()}
        labels = list(options.keys())
        default_id = st.session_state.get("sel_facture")
        default_label = next((k for k in labels if options[k] == default_id), labels[0])
        if st.session_state.get("_last_sel") != default_id:
            st.session_state["sel_facture_box"] = default_label
            st.session_state["_last_sel"] = default_id
        if st.session_state.get("sel_facture_box") not in labels:
            st.session_state["sel_facture_box"] = default_label
        choix = st.selectbox("Facture", labels, key="sel_facture_box")
        fid = options[choix]
        r = actives[actives["id"] == fid].iloc[0]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(badge(r["niveau"]), unsafe_allow_html=True)
            st.markdown(f"### {r['numero']} — {r['client']}")
            st.write(f"**Montant :** {fmt_mad(r['montant'])}  \n**Échéance :** {r['echeance'].strftime('%d/%m/%Y')}  "
                     f"\n**Retard :** {int(r['jours_retard'])} jours  \n**Tél :** {r.get('telephone','—')}  "
                     f"\n**Email :** {r.get('email','—')}")
            if PLOTLY:
                st.plotly_chart(g_jauge(r["score"], r["niveau"]), width="stretch")
            else:
                st.progress(int(r["score"]) / 100, text=f"Score {int(r['score'])}/100")
            st.info(explication(r, df))
            nom_next, rest = prochain_seuil(int(r["jours_retard"]))
            if nom_next:
                st.warning(f"⏳ Niveau suivant « {nom_next} » dans **{rest} jour(s)**.")
            else:
                st.error("🔴 Dernier niveau atteint : transmission à l'avocat.")
            st.markdown(f"**Prédiction :** 7 j : {r['p7']*100:.0f} % · 15 j : {r['p15']*100:.0f} % · "
                        f"30 j : {r['p30']*100:.0f} %  \n**Date probable :** {r['date_probable'].strftime('%d/%m/%Y')} · "
                        f"**Profil :** {r['profil']}")
            if st.button("💡 Meilleure action suivante", width="stretch"):
                if st.session_state.api_key:
                    p = (f"Facture {r['numero']} ({r['client']}, {fmt_mad(r['montant'])}, "
                         f"{int(r['jours_retard'])} j de retard, profil {r['profil']}, P(30j) {r['p30']*100:.0f} %). "
                         f"Recommande en une phrase la meilleure action suivante et pourquoi.")
                    txt = appel_claude(p, max_tokens=200)
                    st.session_state.recos[fid] = txt or "IA indisponible."
                elif r["profil"] in ("Récidiviste", "À risque"):
                    st.session_state.recos[fid] = "Appeler plutôt qu'écrire : proposer un échelonnement daté."
                elif r["profil"] == "Distrait":
                    st.session_state.recos[fid] = "SMS court et bienveillant : oubli probable."
                else:
                    st.session_state.recos[fid] = "Email avec délai ferme, puis appel si pas de réponse."
            if fid in st.session_state.recos:
                st.markdown("<div class='pill-ia'>✨ Recommandé par l'IA</div>", unsafe_allow_html=True)
                st.success(st.session_state.recos[fid])
        with c2:
            if PLOTLY:
                st.plotly_chart(g_frise(r), width="stretch")
            ci = niveau_index(int(r["jours_retard"]))
            for i, lab in enumerate(NIV_LABELS):
                etat = "✅" if i < ci else ("👉" if i == ci else "⬜")
                st.markdown(f"{etat} {ICONES[lab]} **{lab}** — {NIV_ACTIONS[i]}")
            st.divider()
            st.markdown("**Actions déjà notées**")
            hist_f = [h for h in st.session_state.historique if h["facture"] == r["numero"]]
            if hist_f:
                for h in hist_f[-4:]:
                    st.caption(f"{h['date']} — {h['niveau']} — {h['action']}")
            else:
                st.caption("Aucune action enregistrée.")

        st.divider()
        st.subheader("Message prêt à envoyer")
        e1, e2, e3 = st.columns([1.2, 1, 1.3])
        e1.select_slider("Ton", options=["bienveillant", "neutre", "ferme"], key="ton")
        e2.selectbox("Langue", ["français", "arabe", "anglais"], key="langue")
        if (st.session_state.get("_prev_ton") != st.session_state.ton
                or st.session_state.get("_prev_langue") != st.session_state.langue):
            st.session_state.messages = {}
            st.session_state["_prev_ton"] = st.session_state.ton
            st.session_state["_prev_langue"] = st.session_state.langue
        if e3.button("🔄 Générer / Régénérer le message", width="stretch"):
            st.session_state[f"var_{fid}"] = st.session_state.get(f"var_{fid}", 0) + 1
            generer_message(r.to_dict(), r["niveau"], st.session_state[f"var_{fid}"])
        if fid not in st.session_state.messages:
            st.session_state.messages[fid] = gabarit(r["niveau"], r.to_dict(),
                                                     st.session_state.ton, st.session_state.langue)
        machine_a_ecrire(st.session_state.messages[fid], st.session_state.get(f"var_{fid}", 0))
        with st.expander("📋 Texte brut (copier / coller)"):
            st.code(st.session_state.messages[fid], language="markdown")
        if r["niveau"] in ("4 — Mise en demeure", "5 — Contentieux"):
            controles = controle_juridique(st.session_state.messages[fid], r["niveau"])
            manquants = [nom for nom, ok in controles if not ok]
            with st.expander("⚖️ Contrôle juridique des mentions", expanded=bool(manquants)):
                for nom, ok in controles:
                    st.markdown(f"{'✅' if ok else '⚠️'} {nom}")
                st.caption("Garde-fou automatique, pas un avis juridique : faites relire le courrier "
                           "avant envoi.")
        b1, b2, b3 = st.columns(3)
        if b1.button("✅ Marquer comme fait", width="stretch"):
            log_action(r["numero"], r["client"], r["niveau"], "Action effectuée",
                       {"2 — Contact": "Appel"}.get(r["niveau"], "—"))
            st.success("Action notée dans l'historique.")
        if b2.button("💵 Marquer payée", width="stretch"):
            for fac in st.session_state.factures:
                if fac["id"] == fid:
                    fac["statut"] = "Payée"; fac["date_paiement"] = st.session_state.date_ref
            log_action(r["numero"], r["client"], r["niveau"], "Facture payée — clôturée")
            st.session_state["_confettis"] = True
            st.rerun()
        if b3.button("🗑️ Supprimer", width="stretch"):
            st.session_state.factures = [x for x in st.session_state.factures if x["id"] != fid]
            st.rerun()

# ============================================================
#  5. ANALYSES
# ============================================================
elif page == PAGES[4]:
    st.title("📈 Analyses")
    entete("carte de chaleur, donut des profils, nuage de points, histogramme",
           "score moyen, concentration, distribution des retards")
    if actives.empty:
        st.info("Aucune facture impayée à analyser.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Score moyen", f"{en_retard['score'].mean() if not en_retard.empty else 0:.0f}/100")
        c2.metric("Factures > 30 j", int((en_retard["jours_retard"] >= 30).sum()) if not en_retard.empty else 0)
        c3.metric("Montant > 30 j", fmt_mad(en_retard[en_retard["jours_retard"] >= 30]["montant"].sum()) if not en_retard.empty else "0")
        if PLOTLY:
            a, b = st.columns(2)
            with a:
                fig = g_heatmap(df)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
            with b:
                fig = g_donut(df)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
            a, b = st.columns(2)
            with a:
                fig = g_scatter(df)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
            with b:
                fig = g_histo(df)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch")
        with st.expander("📚 Catalogue des 13 graphiques de l'application"):
            st.markdown("""
| # | Graphique | Page |
|---|---|---|
| 1 | Entonnoir cliquable des niveaux | Tableau de bord |
| 2 | Courbe d'évolution du retard | Tableau de bord |
| 3 | Barres volume + montant par niveau | Tableau de bord |
| 4 | Jauge de score | Fiche & message |
| 5 | Frise chronologique des étapes | Fiche & message |
| 6 | Top clients (barres horizontales) | Clients |
| 7 | Carte de chaleur clients × niveaux | Analyses |
| 8 | Donut des profils clients | Analyses |
| 9 | Nuage de points montant × retard | Analyses |
| 10 | Histogramme des retards | Analyses |
| 11 | Cascade d'encaissement | Trésorerie |
| 12 | Encaissement cumulé (90 j) | Trésorerie |
| 13 | Calendrier coloré des échéances | Calendrier |
""")

# ============================================================
#  6. TRÉSORERIE
# ============================================================
elif page == PAGES[5]:
    st.title("💧 Trésorerie")
    entete("cascade d'encaissement, encaissement cumulé, simulateur temps réel",
           "encaissement attendu 7/30/90 j, 3 scénarios, reste à risque")
    c = st.columns(4)
    c[0].metric("Impayé total", fmt_mad(actives["montant"].sum() if not actives.empty else 0))
    c[1].metric("Attendu ≤ 7 j", fmt_mad(simulateur(df, 7)))
    c[2].metric("Attendu ≤ 30 j", fmt_mad(simulateur(df, 30)))
    c[3].metric("Attendu ≤ 90 j", fmt_mad(simulateur(df, 90)))

    st.subheader("Simulateur — bougez les curseurs, la trésorerie change en direct")
    s1, s2 = st.columns(2)
    h = s1.select_slider("Horizon (jours)", options=[7, 30, 90], value=30)
    taux = s2.slider("Hypothèse de recouvrement (%)", min_value=50, max_value=120, value=100, step=5)
    facteur = taux / 100.0
    base = simulateur(df, h)
    perso = simulateur(df, h, facteur=facteur)
    cols = st.columns(4)
    for col, sc in zip(cols[:3], ["optimiste", "realiste", "prudent"]):
        col.metric(sc.capitalize(), fmt_mad(simulateur(df, h, sc, facteur)))
    cols[3].metric("Scénario personnalisé", fmt_mad(perso), delta=fmt_mad(perso - base))
    st.caption("Estimation à partir des probabilités de paiement par facture (IA / heuristique), "
               f"corrigées de votre hypothèse ({taux} %).")

    if PLOTLY:
        st.plotly_chart(g_cascade(df, facteur=facteur), width="stretch")
        st.plotly_chart(g_encaisse_cumule(df), width="stretch")
        recupere, _ = argent_recupere(df)
        if recupere > 0:
            st.plotly_chart(g_recupere(df), width="stretch")
            st.caption(f"**{fmt_mad(recupere)}** récupérés sur des factures clôturées depuis "
                       "l'ouverture de l'application.")
    if not actives.empty:
        sim = actives[["numero", "client", "montant", "p7", "p15", "p30", "date_probable", "profil"]].copy()
        sim["attendu 30 j"] = sim["montant"] * sim["p30"] * facteur
        st.dataframe(sim, width="stretch", hide_index=True)

# ============================================================
#  7. CALENDRIER
# ============================================================
elif page == PAGES[6]:
    st.title("📅 Calendrier")
    entete("calendrier coloré des échéances",
           "échéances du mois, montants attendus, niveaux atteints")
    dref = st.session_state.date_ref
    mois_options = []
    for delta in range(-2, 4):
        m = dref.month - 1 + delta
        y = dref.year + m // 12
        m = m % 12 + 1
        mois_options.append((y, m, f"{calendar.month_name[m]} {y}"))
    idx = next((i for i, (_, _, lab) in enumerate(mois_options) if f"{calendar.month_name[dref.month]} {dref.year}" == lab), 2)
    choix = st.selectbox("Mois", [lab for _, _, lab in mois_options], index=idx)
    annee, mois = next((y, m) for y, m, lab in mois_options if lab == choix)
    if PLOTLY:
        st.plotly_chart(g_calendrier(df, annee, mois), width="stretch")
    cmap = donnees_calendrier(df, annee, mois)
    if cmap:
        st.subheader("Échéances du mois")
        lignes = []
        for j in sorted(cmap):
            montant, i, nb = cmap[j]
            d = date(annee, mois, j)
            lignes.append({"Date": d.strftime("%d/%m/%Y"), "Factures": nb, "Montant": fmt_mad(montant),
                           "Niveau max": "À jour" if i < 0 else NIV_LABELS[i]})
        st.dataframe(pd.DataFrame(lignes), width="stretch", hide_index=True)
    else:
        st.info("Aucune échéance ce mois-ci.")

# ============================================================
#  8. ASSISTANT IA
# ============================================================
elif page == PAGES[7]:
    st.markdown("<div class='pill-ia'>● IA</div>", unsafe_allow_html=True)
    st.title("🤖 Cashy — votre assistant IA")
    entete("aucun graphique — briefing et conversation",
           "actions prioritaires, réponses en langage naturel")
    st.caption(f"🔮 Cashy est identifié par le violet ({VIOLET}) : tout ce qu'il produit est signalé ainsi.")
    tab_b, tab_c = st.tabs(["Briefing du jour", "Conversation"])
    with tab_b:
        if st.button("✨ Générer le briefing"):
            if st.session_state.api_key:
                ctx = briefing_local(df)
                p = (f"Rédige un briefing de recouvrement concis (5-7 lignes) à partir de ces données :\n{ctx}\n"
                     f"Termine par les 3 actions prioritaires du jour.")
                st.session_state["briefing"] = appel_claude(p, max_tokens=400) or ctx
            else:
                st.session_state["briefing"] = briefing_local(df)
        st.markdown(f"<div class='carte' style='border-left:5px solid {VIOLET}'>"
                    f"{st.session_state.get('briefing', briefing_local(df)).replace(chr(10), '<br>')}</div>",
                    unsafe_allow_html=True)
        if st.button("Voir la trésorerie", on_click=aller, args=("💧 Trésorerie",)):
            pass
    with tab_c:
        for m in st.session_state.chat:
            with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "🤖"):
                st.markdown(m["content"])
        q = st.chat_input("Ex. : Quelles factures dois-je traiter ce matin ?")
        if q:
            st.session_state.chat.append({"role": "user", "content": q})
            with st.chat_message("user", avatar="🧑"):
                st.markdown(q)
            if st.session_state.api_key:
                ctx = briefing_local(df)
                p = (f"Données de recouvrement :\n{ctx}\n\nQuestion : {q}\n"
                     f"Réponds précisément, uniquement à partir de ces données.")
                rep = appel_claude(p, max_tokens=500) or reponse_locale(q, df)
            else:
                rep = reponse_locale(q, df)
            st.session_state.chat.append({"role": "assistant", "content": rep})
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(rep)

# ============================================================
#  9. HISTORIQUE & PREUVES
# ============================================================
elif page == PAGES[8]:
    st.title("🗂️ Historique & preuves")
    entete("journal horodaté (tableau), exports",
           "preuves de relance, 4 familles de données")
    tab_j, tab_d = st.tabs(["Journal des actions", "Données & exports"])
    with tab_j:
        if not st.session_state.historique:
            st.info("Aucune action enregistrée.")
        else:
            h = pd.DataFrame(st.session_state.historique)
            st.dataframe(h, width="stretch", hide_index=True)
            c = st.columns(3)
            c[0].download_button("⬇️ Journal (CSV)", h.to_csv(index=False).encode("utf-8-sig"),
                                 "historique_relances.csv", "text/csv")
            if FPDF_OK:
                pdf = export_pdf("Journal des relances (preuve)", h)
                if pdf:
                    c[1].download_button("⬇️ Journal (PDF — preuve)", pdf, "historique_relances.pdf", "application/pdf")
            else:
                c[1].caption("PDF indisponible (fpdf2).")
            st.caption("Chaque ligne horodatée constitue une preuve de relance en cas de contentieux.")

    with tab_d:
        st.markdown("#### Les 4 familles de données")
        st.caption("Chaque famille a sa provenance, sa page de consultation et son export. "
                   "L'export Excel ci-dessous regroupe les quatre dans un seul classeur.")

        saisies = pd.DataFrame([{
            "id": f["id"], "client": f["client"], "numero": f["numero"], "montant": f["montant"],
            "echeance": f["echeance"], "telephone": f.get("telephone", ""), "email": f.get("email", ""),
            "nb_retards": f.get("nb_retards", 0), "statut": f.get("statut", "Impayée"),
        } for f in st.session_state.factures]) if st.session_state.factures else pd.DataFrame()
        cols = [c for c in ["numero", "client", "montant", "jours_retard", "niveau", "score",
                            "p7", "p15", "p30", "profil", "date_probable"]
                if not df.empty and c in df.columns]
        calc = df[cols] if cols else pd.DataFrame()
        rows = []
        for fid, txt in st.session_state.messages.items():
            num = next((f["numero"] for f in st.session_state.factures if f["id"] == fid), fid)
            rows.append({"facture": num, "type": "Message", "contenu": txt})
        for fid, txt in st.session_state.recos.items():
            num = next((f["numero"] for f in st.session_state.factures if f["id"] == fid), fid)
            rows.append({"facture": num, "type": "Recommandation", "contenu": txt})
        if "briefing" in st.session_state:
            rows.append({"facture": "—", "type": "Briefing", "contenu": st.session_state["briefing"]})
        ia = pd.DataFrame(rows, columns=["facture", "type", "contenu"])
        hist = pd.DataFrame(st.session_state.historique) if st.session_state.historique else pd.DataFrame()

        t1, t2, t3, t4 = st.tabs(["① Saisies", "② Calculées", "③ IA", "④ Historique"])
        with t1:
            st.caption("Données entrées par l'utilisateur (factures, clients, coordonnées).")
            st.dataframe(saisies, width="stretch", hide_index=True)
            if not saisies.empty:
                st.download_button("⬇️ Exporter (CSV)", saisies.to_csv(index=False).encode("utf-8-sig"),
                                   "donnees_saisies.csv", "text/csv")
        with t2:
            st.caption("Calculées : jours de retard, niveau, score, probabilités, profil.")
            st.dataframe(calc, width="stretch", hide_index=True)
            if not calc.empty:
                st.download_button("⬇️ Exporter (CSV)", calc.to_csv(index=False).encode("utf-8-sig"),
                                   "donnees_calculees.csv", "text/csv")
        with t3:
            st.caption("Produites par l'IA (ou par les gabarits en mode dégradé) : "
                       "messages, recommandations, briefing. Signalées en violet dans l'application.")
            st.dataframe(ia, width="stretch", hide_index=True)
            if not ia.empty:
                st.download_button("⬇️ Exporter (CSV)", ia.to_csv(index=False).encode("utf-8-sig"),
                                   "contenus_ia.csv", "text/csv")
        with t4:
            st.caption("Historique horodaté des actions : la preuve de chaque relance.")
            st.dataframe(hist, width="stretch", hide_index=True)
            if not hist.empty:
                st.download_button("⬇️ Exporter (CSV)", hist.to_csv(index=False).encode("utf-8-sig"),
                                   "historique.csv", "text/csv")

        st.divider()
        classeur = export_excel({"Saisies": saisies, "Calculees": calc, "IA": ia, "Historique": hist})
        if classeur:
            st.download_button("⬇️ Exporter les 4 familles (Excel)", classeur, "donnees_impayes.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.caption("Export Excel indisponible (openpyxl). Utilisez les exports CSV ci-dessus.")

# ============================================================
#  10. RÉGLAGES
# ============================================================
elif page == PAGES[9]:
    st.title("⚙️ Réglages")
    entete("aucun graphique — configuration et identité visuelle",
           "société, seuils, pondérations, IA, apparence")
    tab_s, tab_a = st.tabs(["Société & règles", "Apparence & IA"])
    with tab_s:
        st.subheader("Vous")
        c0, c1 = st.columns(2)
        st.session_state.utilisateur = c0.text_input("Votre prénom (accueil personnalisé)",
                                                    value=st.session_state.utilisateur)
        st.session_state.societe = c1.text_input("Nom de la société", value=st.session_state.societe)
        st.subheader("Seuils (jours de retard)")
        c = st.columns(5)
        st.session_state.seuil_1 = c[0].number_input("Rappel dès", 0, 365, st.session_state.seuil_1)
        st.session_state.seuil_2 = c[1].number_input("Contact dès", 0, 365, st.session_state.seuil_2)
        st.session_state.seuil_3 = c[2].number_input("Relance dès", 0, 365, st.session_state.seuil_3)
        st.session_state.seuil_4 = c[3].number_input("Mise en demeure dès", 0, 365, st.session_state.seuil_4)
        st.session_state.seuil_5 = c[4].number_input("Contentieux dès", 0, 365, st.session_state.seuil_5)
        if seuils() != sorted(seuils()):
            st.warning("⚠️ Les seuils doivent être croissants.")
        st.subheader("Pondérations du score")
        c = st.columns(4)
        st.session_state.poids_retard = c[0].slider("Retard", 0, 100, st.session_state.poids_retard)
        st.session_state.poids_montant = c[1].slider("Montant", 0, 100, st.session_state.poids_montant)
        st.session_state.poids_hist = c[2].slider("Historique", 0, 100, st.session_state.poids_hist)
        st.session_state.poids_risque = c[3].slider("Risque (prédiction)", 0, 100, st.session_state.poids_risque)
    with tab_a:
        st.markdown("**Apparence**")
        st.caption(f"Thème détecté : **{'sombre' if mode_sombre() else 'clair'}**. "
                   "L'application suit le thème de Streamlit : menu **⋮ → Settings → Theme** "
                   "(clair, sombre ou système). Graphiques, cartes et badges s'adaptent automatiquement.")
        st.markdown("**Palette 7.1**")
        for nom, col, role in [("Bleu nuit", THEME["marque"], "marque"),
                               ("Turquoise", THEME["paiement"], "paiements"),
                               ("Violet", THEME["ia"], "contenus IA"),
                               ("Alerte", THEME["alerte"], "reste à risque")]:
            st.markdown(f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                        f"<span style='width:22px;height:22px;border-radius:5px;background:{col};display:inline-block'></span>"
                        f"<b>{nom}</b> <span class='petit'>— {role} — {col}</span></div>", unsafe_allow_html=True)
        st.markdown("**Échelle d'urgence (doublée d'icônes pour le daltonisme)**")
        for n in URGENCE:
            st.markdown(f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                        f"<span style='width:22px;height:22px;border-radius:5px;background:{n['couleur']};display:inline-block'></span>"
                        f"<span>{n['icone']}</span> <b>{n['label']}</b> <span class='petit'>— {n['action']}</span></div>",
                        unsafe_allow_html=True)
        st.divider()
        st.session_state.api_key = st.text_input("Clé API Anthropic", value=st.session_state.api_key, type="password")
        st.session_state.model = st.text_input("Modèle", value=st.session_state.model)
        st.caption("Sans clé, l'application fonctionne avec des gabarits et des réponses locales.")

st.divider()
st.caption("Scoring des Impayés — V3 · Streamlit + IA Claude · 10 onglets · 13 graphiques · "
           "Brouillons juridiques à valider · Données personnelles : loi 09-08 / CNDP.")
