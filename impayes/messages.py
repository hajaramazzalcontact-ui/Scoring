"""Rédaction des messages : le texte prêt à envoyer pour chaque niveau.

L'application fonctionne **sans aucune dépendance externe** : les modèles
ci-dessous produisent un message complet, personnalisé et utilisable tel quel.
Lorsqu'une clé API est configurée, :mod:`impayes.ai` peut réécrire ce texte
pour l'adapter au dossier ; le modèle local reste alors le filet de sécurité.

Composition d'un message :

* un **corps** qui dépend du niveau (SMS, script d'appel, email, mise en
  demeure, note à l'avocat) et de la langue ;
* trois **fragments de ton** (ouverture, pression, clôture) qui font varier la
  fermeté sans jamais toucher aux faits.

Résultat : 5 niveaux × 3 tons × 3 langues = 45 messages distincts.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import config

# ---------------------------------------------------------------------------
# Fragments de ton
# ---------------------------------------------------------------------------
TONS_FRAGMENTS: dict[str, dict[str, dict[str, str]]] = {
    "fr": {
        "bienveillant": {
            "ouverture": "Bonjour {client}, j'espère que vous allez bien.",
            "pression": "Il s'agit très probablement d'un simple oubli, et nous préférons vous le signaler avant toute autre démarche.",
            "cloture": "Merci beaucoup pour votre compréhension, et bonne journée à vous.",
        },
        "neutre": {
            "ouverture": "Bonjour {client},",
            "pression": "Sauf erreur de notre part, ce règlement n'est pas encore parvenu à notre comptabilité.",
            "cloture": "Nous restons à votre disposition pour tout renseignement complémentaire.",
        },
        "ferme": {
            "ouverture": "Bonjour {client},",
            "pression": "Cette créance est exigible depuis la date d'échéance indiquée et aucun motif n'a été porté à notre connaissance.",
            "cloture": "Nous vous remercions de traiter ce point sans délai.",
        },
    },
    "en": {
        "bienveillant": {
            "ouverture": "Dear {client}, I hope you are well.",
            "pression": "This is most likely a simple oversight, and we would rather let you know before taking any further step.",
            "cloture": "Thank you very much for your understanding and have a good day.",
        },
        "neutre": {
            "ouverture": "Dear {client},",
            "pression": "Unless we are mistaken, this payment has not yet reached our accounts.",
            "cloture": "We remain at your disposal for any further information.",
        },
        "ferme": {
            "ouverture": "Dear {client},",
            "pression": "This amount has been due since the date shown above and no reason has been brought to our attention.",
            "cloture": "We would appreciate your prompt attention to this matter.",
        },
    },
    "ar": {
        "bienveillant": {
            "ouverture": "عزيزي {client}، نأمل أن تكون بخير.",
            "pression": "الأمر على الأرجح سهو بسيط، ونفضّل تنبيهكم قبل أي إجراء آخر.",
            "cloture": "شكراً جزيلاً على تفهمكم، وطاب يومكم.",
        },
        "neutre": {
            "ouverture": "عزيزي {client}،",
            "pression": "في حال عدم وجود خطأ من جانبنا، فإن هذا المبلغ لم يُسجَّل بعد في محاسبتنا.",
            "cloture": "نبقى رهن إشارتكم لأي معلومة إضافية.",
        },
        "ferme": {
            "ouverture": "عزيزي {client}،",
            "pression": "هذا المبلغ مستحق منذ تاريخ الاستحقاق المذكور ولم يتلقَّ أي تبرير من جانبكم.",
            "cloture": "نرجو معالجة هذا الأمر دون تأخير.",
        },
    },
}

# ---------------------------------------------------------------------------
# Corps par niveau et par langue
# ---------------------------------------------------------------------------
CORPS: dict[str, dict[str, dict[str, str]]] = {
    # ---------------------------------------------------------------- niveau 1
    "rappel": {
        "fr": {
            "canal": "SMS",
            "objet": "Rappel — facture {numero}",
            "texte": (
                "{ouverture} La facture {numero} d'un montant de {montant}, exigible le {echeance}, "
                "reste impayée ({jours} jours de retard). {pression} "
                "Vous pouvez régler par virement ou nous appeler au {telephone_societe}. "
                "{cloture} — {societe}"
            ),
        },
        "en": {
            "canal": "SMS",
            "objet": "Reminder — invoice {numero}",
            "texte": (
                "{ouverture} Invoice {numero} for {montant}, due on {echeance}, is still unpaid "
                "({jours} days overdue). {pression} You may pay by bank transfer or call us on "
                "{telephone_societe}. {cloture} — {societe}"
            ),
        },
        "ar": {
            "canal": "رسالة نصية",
            "objet": "تذكير — الفاتورة {numero}",
            "texte": (
                "{ouverture} الفاتورة رقم {numero} بمبلغ {montant}، المستحقة في {echeance}، "
                "لم تُسدَّد بعد ({jours} يوماً من التأخير). {pression} "
                "يمكنكم السداد بالتحويل البنكي أو الاتصال بنا على {telephone_societe}. "
                "{cloture} — {societe}"
            ),
        },
    },
    # ---------------------------------------------------------------- niveau 2
    "contact": {
        "fr": {
            "canal": "Script d'appel",
            "objet": "Appel — facture {numero} — {jours} jours de retard",
            "texte": (
                "SCRIPT D'APPEL — {client} ({telephone})\n"
                "Objectif : obtenir une date de paiement ferme pour la facture {numero}.\n\n"
                "« {ouverture} »\n\n"
                "1. Accroche — se présenter ({societe}) et annoncer le motif de l'appel.\n"
                "2. Exposé — « La facture {numero}, d'un montant de {montant}, était exigible le "
                "{echeance}. Nous sommes aujourd'hui à {jours} jours de retard. »\n"
                "3. Écoute — laisser le client expliquer (oubli, litige, trésorerie) et noter le motif.\n"
                "4. Réponse — {pression}\n"
                "5. Engagement — demander une date de paiement précise ; si le client hésite, "
                "proposer un échéancier en 2 versements.\n"
                "6. Conclusion — « Je note votre engagement au {date_paiement}. Je vous envoie un "
                "récapitulatif par email dans la journée. »\n"
                "7. Après l'appel — {cloture} Puis noter l'action dans l'application (preuve de relance).\n\n"
                "À éviter : élever la voix, menacer, relancer si un litige est signalé — dans ce cas, "
                "basculer la facture en statut « En litige »."
            ),
        },
        "en": {
            "canal": "Call script",
            "objet": "Call — invoice {numero} — {jours} days overdue",
            "texte": (
                "CALL SCRIPT — {client} ({telephone})\n"
                "Goal: obtain a firm payment date for invoice {numero}.\n\n"
                "\"{ouverture}\"\n\n"
                "1. Opening — introduce yourself ({societe}) and state the reason for the call.\n"
                "2. Facts — \"Invoice {numero} for {montant} was due on {echeance}. We are now "
                "{jours} days past the due date.\"\n"
                "3. Listen — let the customer explain (oversight, dispute, cash flow) and take notes.\n"
                "4. Response — {pression}\n"
                "5. Commitment — ask for a specific payment date; if the customer hesitates, "
                "offer a two-instalment plan.\n"
                "6. Closing — \"I am noting your commitment for {date_paiement}. I will email you a "
                "summary today.\"\n"
                "7. After the call — {cloture} Then record the action in the app (proof of the reminder).\n\n"
                "What to avoid: raising your voice, threatening, or pursuing reminders if a dispute "
                "is reported — in that case, switch the invoice to \"In dispute\"."
            ),
        },
        "ar": {
            "canal": "نص مكالمة",
            "objet": "مكالمة — الفاتورة {numero} — تأخير {jours} يوماً",
            "texte": (
                "نص مكالمة هاتفية — {client} ({telephone})\n"
                "الهدف: الحصول على تاريخ سداد محدد للفاتورة {numero}.\n\n"
                "«{ouverture}»\n\n"
                "1. الافتتاح — التعريف بالشركة ({societe}) وذكر سبب الاتصال.\n"
                "2. عرض الوقائع — «الفاتورة رقم {numero} بمبلغ {montant} كان استحقاقها في {echeance}. "
                "ونحن اليوم في اليوم {jours} من التأخير.»\n"
                "3. الإنصات — ترك العميل يشرح السبب (سهو، نزاع، سيولة) وتدوينه.\n"
                "4. الرد — {pression}\n"
                "5. الالتزام — طلب تاريخ سداد محدد؛ وفي حال التردد، اقتراح تقسيط على دفعتين.\n"
                "6. الختام — «سجّلت التزامكم بتاريخ {date_paiement}. سأرسل لكم ملخصاً بالبريد "
                "الإلكتروني اليوم.»\n"
                "7. بعد المكالمة — {cloture} ثم تسجيل الإجراء في التطبيق (إثبات المتابعة).\n\n"
                "ما يجب تجنّبه: رفع الصوت، التهديد، ومواصلة التنبيه عند وجود نزاع — في هذه الحالة "
                "تُحوَّل الفاتورة إلى حالة «نزاع»."
            ),
        },
    },
    # ---------------------------------------------------------------- niveau 3
    "relance": {
        "fr": {
            "canal": "Email",
            "objet": "Facture {numero} — {montant} — règlement en attente ({jours} jours)",
            "texte": (
                "{ouverture}\n\n"
                "Notre facture {numero}, d'un montant de {montant}, était exigible le {echeance}. "
                "À ce jour, soit {jours} jours plus tard, son règlement n'a pas été enregistré. "
                "{pression}\n\n"
                "Nous vous demandons de procéder au règlement avant le {date_limite}, soit {delai} jours. "
                "Si un litige ou une difficulté de trésorerie explique ce retard, merci de nous le "
                "signaler : nous étudierons ensemble une solution, y compris un échéancier.\n\n"
                "{cloture}\n\n"
                "{signature}\n"
                "{societe}{adresse_societe}{telephone_societe}{email_societe}"
            ),
        },
        "en": {
            "canal": "Email",
            "objet": "Invoice {numero} — {montant} — payment outstanding ({jours} days)",
            "texte": (
                "{ouverture}\n\n"
                "Invoice {numero} for {montant} was due on {echeance}. To date, {jours} days later, "
                "no payment has been recorded. {pression}\n\n"
                "Please settle this invoice by {date_limite}, i.e. {delai} days. If a dispute or a "
                "cash-flow difficulty explains the delay, please let us know: we will look for a "
                "solution together, including an instalment plan.\n\n"
                "{cloture}\n\n"
                "{signature}\n"
                "{societe}{adresse_societe}{telephone_societe}{email_societe}"
            ),
        },
        "ar": {
            "canal": "بريد إلكتروني",
            "objet": "الفاتورة {numero} — {montant} — في انتظار السداد ({jours} يوماً)",
            "texte": (
                "{ouverture}\n\n"
                "الفاتورة رقم {numero} بمبلغ {montant} كان استحقاقها في {echeance}. وحتى اليوم، أي بعد "
                "{jours} يوماً، لم يُسجَّل أي سداد. {pression}\n\n"
                "نرجو تسوية هذه الفاتورة قبل {date_limite}، أي {delai} يوماً. وإذا كان هناك نزاع أو "
                "صعوبة في السيولة تفسّر هذا التأخير، نرجو إبلاغنا بذلك: سنبحث معكم حلاً، بما في ذلك "
                "تقسيط المبلغ.\n\n"
                "{cloture}\n\n"
                "{signature}\n"
                "{societe}{adresse_societe}{telephone_societe}{email_societe}"
            ),
        },
    },
    # ---------------------------------------------------------------- niveau 4
    "miseendemeure": {
        "fr": {
            "canal": "Courrier recommandé",
            "objet": "Mise en demeure de payer — facture {numero} — {montant}",
            "texte": (
                "{societe}\n{adresse_societe}{telephone_societe}{email_societe}{ice_mention}\n\n"
                "MISE EN DEMEURE DE PAYER\n"
                "Lettre recommandée avec accusé de réception\n\n"
                "Destinataire : {client}\n{contact_client}\n\n"
                "Objet : mise en demeure de payer la facture {numero} — {montant}\n\n"
                "{ouverture}\n\n"
                "En notre qualité de créancier, nous vous mettons en demeure de nous régler la somme "
                "de {montant}, au titre de la facture {numero}, échue le {echeance} et impayée à ce "
                "jour, soit {jours} jours de retard. {pression}\n\n"
                "Le règlement devra intervenir au plus tard le {date_limite}, soit {delai_med} jours "
                "à compter de la réception de la présente.\n\n"
                "À défaut de paiement dans ce délai, nous engagerons une action en recouvrement et "
                "transmettrons le dossier à notre conseil, sans nouvel avis, les intérêts de retard "
                "et les frais y afférents restant à votre charge.{interet_mention} {cloture}\n\n"
                "Fait à {ville}, le {date_jour}\n{societe}\n[Signature et cachet]\n\n"
                "⚠️ Brouillon généré automatiquement : à faire valider par un juriste avant envoi."
            ),
        },
        "en": {
            "canal": "Registered letter",
            "objet": "Formal notice to pay — invoice {numero} — {montant}",
            "texte": (
                "{societe}\n{adresse_societe}{telephone_societe}{email_societe}{ice_mention}\n\n"
                "FORMAL NOTICE TO PAY\n"
                "Sent by registered mail with acknowledgement of receipt\n\n"
                "To: {client}\n{contact_client}\n\n"
                "Subject: formal notice to pay invoice {numero} — {montant}\n\n"
                "{ouverture}\n\n"
                "As creditor, we hereby formally require you to pay the sum of {montant} in respect "
                "of invoice {numero}, due on {echeance} and unpaid to date, i.e. {jours} days "
                "overdue. {pression}\n\n"
                "Payment must be received no later than {date_limite}, i.e. {delai_med} days from "
                "receipt of this notice.\n\n"
                "Failing payment within that period, we will start recovery proceedings and refer "
                "the file to our legal counsel, without further notice; late-payment interest and "
                "related costs shall remain at your charge.{interet_mention} {cloture}\n\n"
                "Done at {ville}, on {date_jour}\n{societe}\n[Signature and stamp]\n\n"
                "⚠️ Automatically generated draft: have a legal adviser review it before sending."
            ),
        },
        "ar": {
            "canal": "رسالة موصى عليها",
            "objet": "إنذار بالأداء — الفاتورة {numero} — {montant}",
            "texte": (
                "{societe}\n{adresse_societe}{telephone_societe}{email_societe}{ice_mention}\n\n"
                "إنذار بالأداء\n"
                "رسالة موصى عليها مع إشعار بالتسلم\n\n"
                "المرسل إليه: {client}\n{contact_client}\n\n"
                "الموضوع: إنذار بأداء الفاتورة {numero} — {montant}\n\n"
                "{ouverture}\n\n"
                "بصفتنا دائناً، نُنذركم بأداء مبلغ {montant} المستحق عن الفاتورة {numero}، التي كان "
                "استحقاقها في {echeance} ولم تُسدَّد إلى اليوم، أي بتأخير قدره {jours} يوماً. {pression}\n\n"
                "يجب أن يتم السداد في أجل أقصاه {date_limite}، أي {delai_med} يوماً من تاريخ توصل هذه "
                "الرسالة.\n\n"
                "وفي حال عدم السداد داخل هذا الأجل، سنباشر مسطرة التحصيل ونحيل الملف إلى محامينا دون "
                "إشعار جديد، مع بقاء فوائد التأخير والمصاريف المترتبة على عاتقكم.{interet_mention} {cloture}\n\n"
                "حُرِّر بـ {ville}، في {date_jour}\n{societe}\n[التوقيع والطابع]\n\n"
                "⚠️ مشروع مُنشأ آلياً: يُنصح بمراجعته من طرف مستشار قانوني قبل الإرسال."
            ),
        },
    },
    # ---------------------------------------------------------------- niveau 5
    "contentieux": {
        "fr": {
            "canal": "Note au conseil",
            "objet": "Transmission contentieux — {client} — facture {numero}",
            "texte": (
                "NOTE DE TRANSMISSION AU CONSEIL\n"
                "Dossier : {client} — facture {numero} — créance de {montant}\n\n"
                "{ouverture}\n\n"
                "1. Identification du débiteur\n"
                "   Nom : {client}\n{contact_client}\n"
                "   Référence client : {client}\n\n"
                "2. Créance\n"
                "   Montant principal : {montant}\n"
                "   Facture : {numero}\n"
                "   Échéance : {echeance}\n"
                "   Retard à ce jour : {jours} jours\n\n"
                "3. Procédure amiable déjà engagée\n"
                "   Niveau atteint : {niveau_nom} ({icone_niveau})\n"
                "   Nombre d'actions de relance enregistrées : {nb_relances}\n"
                "   Retards antérieurs constatés chez ce client : {nb_retards_passes}\n"
                "   {historique_actions}\n\n"
                "4. Pièces à joindre au dossier\n"
                "   • Facture et bon de commande / de livraison\n"
                "   • Mise en demeure et accusé de réception\n"
                "   • Journal horodaté des relances (export PDF de l'application)\n"
                "   • Éventuelles promesses de paiement non tenues\n\n"
                "5. Observations\n"
                "   {pression}\n"
                "   Probabilité de paiement à 30 jours estimée : {proba_30}\n"
                "   Date de paiement la plus probable : {date_probable}\n\n"
                "⛔ Aucune relance amiable supplémentaire n'est recommandée à ce stade. {cloture}\n\n"
                "Fait le {date_jour} — {societe}\n\n"
                "⚠️ Brouillon : à faire valider par un juriste et à adapter à la procédure applicable."
            ),
        },
        "en": {
            "canal": "Note to counsel",
            "objet": "Litigation referral — {client} — invoice {numero}",
            "texte": (
                "MEMORANDUM TO LEGAL COUNSEL\n"
                "File: {client} — invoice {numero} — claim of {montant}\n\n"
                "{ouverture}\n\n"
                "1. Debtor identification\n"
                "   Name: {client}\n{contact_client}\n"
                "   Customer reference: {client}\n\n"
                "2. Claim\n"
                "   Principal amount: {montant}\n"
                "   Invoice: {numero}\n"
                "   Due date: {echeance}\n"
                "   Days overdue to date: {jours}\n\n"
                "3. Amicable steps already taken\n"
                "   Level reached: {niveau_nom} ({icone_niveau})\n"
                "   Number of reminder actions recorded: {nb_relances}\n"
                "   Previous late payments by this customer: {nb_retards_passes}\n"
                "   {historique_actions}\n\n"
                "4. Documents to enclose\n"
                "   • Invoice and purchase / delivery order\n"
                "   • Formal notice and acknowledgement of receipt\n"
                "   • Timestamped reminder log (PDF export from the app)\n"
                "   • Any payment promises not honoured\n\n"
                "5. Observations\n"
                "   {pression}\n"
                "   Estimated 30-day payment probability: {proba_30}\n"
                "   Most likely payment date: {date_probable}\n\n"
                "⛔ No further amicable reminder is recommended at this stage. {cloture}\n\n"
                "Dated {date_jour} — {societe}\n\n"
                "⚠️ Draft: have a legal adviser review it and adapt it to the applicable procedure."
            ),
        },
        "ar": {
            "canal": "مذكرة إلى المحامي",
            "objet": "إحالة على القضاء — {client} — الفاتورة {numero}",
            "texte": (
                "مذكرة إحالة إلى المحامي\n"
                "الملف: {client} — الفاتورة {numero} — الدين {montant}\n\n"
                "{ouverture}\n\n"
                "1. التعريف بالمدين\n"
                "   الاسم: {client}\n{contact_client}\n\n"
                "2. الدين\n"
                "   المبلغ الأصلي: {montant}\n"
                "   الفاتورة: {numero}\n"
                "   تاريخ الاستحقاق: {echeance}\n"
                "   التأخير إلى اليوم: {jours} يوماً\n\n"
                "3. المسطرة الرضائية المتبعة\n"
                "   المستوى الذي تم بلوغه: {niveau_nom} ({icone_niveau})\n"
                "   عدد إجراءات التنبيه المسجلة: {nb_relances}\n"
                "   حالات التأخير السابقة لهذا العميل: {nb_retards_passes}\n"
                "   {historique_actions}\n\n"
                "4. الوثائق المرفقة\n"
                "   • الفاتورة وأمر التسليم أو الشراء\n"
                "   • الإنذار بالأداء وإشعار التوصل\n"
                "   • سجل التنبيهات المؤرخ (تصدير PDF من التطبيق)\n"
                "   • الالتزامات بالسداد غير المحترمة إن وُجدت\n\n"
                "5. ملاحظات\n"
                "   {pression}\n"
                "   احتمال السداد خلال 30 يوماً: {proba_30}\n"
                "   التاريخ الأكثر ترجيحاً للسداد: {date_probable}\n\n"
                "⛔ لا يُنصح بأي تنبيه رضائي إضافي في هذه المرحلة. {cloture}\n\n"
                "حُرِّر في {date_jour} — {societe}\n\n"
                "⚠️ مشروع: يُنصح بمراجعته من طرف مستشار قانوني وتكييفه مع المسطرة المعمول بها."
            ),
        },
    },
}

MOIS = {
    "fr": [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ],
    "en": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "ar": [
        "يناير", "فبراير", "مارس", "أبريل", "ماي", "يونيو",
        "يوليوز", "غشت", "شتنبر", "أكتوبر", "نونبر", "دجنبر",
    ],
}


# ---------------------------------------------------------------------------
# Formatage
# ---------------------------------------------------------------------------
def formater_montant(montant: float, devise: str = "MAD", langue: str = "fr") -> str:
    """« 15 000,00 MAD » en français, « 15,000.00 MAD » en anglais."""
    montant = float(montant or 0)
    if langue == "fr":
        entier, _, decimales = f"{montant:,.2f}".partition(".")
        corps = entier.replace(",", " ").replace("\u202f", " ")
        texte = f"{corps},{decimales}"
    else:
        texte = f"{montant:,.2f}"
    return f"{texte} {devise}".strip()


def formater_date(valeur, langue: str = "fr", long: bool = False) -> str:
    """Rend une date lisible dans la langue choisie."""
    if not valeur:
        return "—"
    if isinstance(valeur, str):
        try:
            valeur = date.fromisoformat(valeur[:10])
        except ValueError:
            return valeur
    if long:
        return f"{valeur.day} {MOIS.get(langue, MOIS['fr'])[valeur.month - 1]} {valeur.year}"
    return valeur.strftime("%d/%m/%Y")


def formater_retard(jours: int, langue: str = "fr") -> str:
    if langue == "fr":
        return f"{jours} jour{'s' if abs(jours) > 1 else ''}"
    if langue == "ar":
        return f"{jours} يوماً"
    return f"{jours} day{'s' if abs(jours) != 1 else ''}"


def tronquer_pour_sms(texte: str, limite: int = 480) -> str:
    """Un SMS trop long est coupé proprement, avec mention de la suite."""
    if len(texte) <= limite:
        return texte
    coupe = texte[: limite - 3]
    if " " in coupe:
        coupe = coupe.rsplit(" ", 1)[0]
    return coupe.rstrip(" ,;:") + "…"


# ---------------------------------------------------------------------------
# Contexte de rédaction
# ---------------------------------------------------------------------------
def construire_contexte(
    facture: dict,
    params: dict,
    ton: str,
    langue: str,
    delai_med: int,
    proba_30: float | None = None,
    date_probable=None,
    nb_relances: int | None = None,
    historique_actions: str | None = None,
) -> dict:
    """Assemble toutes les variables remplaçables des modèles."""
    devise = params.get("devise", "MAD")
    jours = int(facture.get("jours_retard") or 0)
    echeance = facture.get("echeance")
    montant = formater_montant(facture.get("montant") or 0, devise, langue)
    niveau = config.niveau(facture.get("niveau"))
    fragments = TONS_FRAGMENTS.get(langue, TONS_FRAGMENTS["fr"])[ton]

    adresse = params.get("adresse") or ""
    adresse_texte = f"\n{adresse}" if adresse else ""
    telephone_societe = params.get("tel_societe") or ""
    telephone_texte = f"\nTél. : {telephone_societe}" if telephone_societe else "\n"
    email_societe = params.get("email_societe") or ""
    email_texte = f" — {email_societe}" if email_societe else ""
    ice = params.get("ice") or ""
    ice_texte = f"\nICE : {ice}" if ice else ""
    taux = float(params.get("taux_interet_retard") or 0)
    interet_texte = (
        f" Des intérêts de retard de {taux:g} % par mois seront appliqués." if taux > 0 else ""
    )

    signature = params.get("signature") or ""
    signature = signature or ("Cordialement," if langue == "fr" else ("Kind regards," if langue == "en" else "مع خالص التحية،"))

    contact_client = " — ".join(
        filtre for filtre in [facture.get("telephone"), facture.get("email")] if filtre
    )

    date_limite = date.today() + timedelta(days=delai_med)

    return {
        "client": facture.get("client") or "—",
        "numero": facture.get("numero") or "—",
        "montant": montant,
        "jours": jours,
        "echeance": formater_date(echeance, langue),
        "date_limite": formater_date(date_limite, langue),
        "date_jour": formater_date(date.today(), langue, long=True),
        "date_paiement": formater_date(date.today() + timedelta(days=7), langue),
        "delai": delai_med,
        "delai_med": delai_med,
        "societe": params.get("societe", "Ma Société"),
        "ville": params.get("ville", ""),
        "adresse_societe": adresse_texte,
        "telephone_societe": telephone_societe,
        "email_societe": email_texte,
        "ice_mention": ice_texte,
        "interet_mention": interet_texte,
        "signature": signature,
        "contact_client": contact_client or "—",
        "telephone": facture.get("telephone") or "—",
        "email": facture.get("email") or "—",
        "nb_retards_passes": int(facture.get("nb_retards_passes") or 0),
        "nb_relances": nb_relances if nb_relances is not None else 0,
        "niveau_nom": niveau["nom"],
        "icone_niveau": niveau["icone"],
        "historique_actions": historique_actions or "Voir le journal horodaté joint.",
        "proba_30": f"{(proba_30 or 0) * 100:.0f} %" if proba_30 is not None else "non estimée",
        "date_probable": formater_date(date_probable, langue) if date_probable else "non estimée",
        "ouverture": fragments["ouverture"].format(**{"client": facture.get("client") or "—"}),
        "pression": fragments["pression"],
        "cloture": fragments["cloture"],
    }


def delai_pour_niveau(niveau_code: str, params: dict) -> int:
    """Délai accordé au client selon le niveau (jours)."""
    if niveau_code == "miseendemeure":
        return int(params.get("delai_miseendemeure", 8))
    if niveau_code == "relance":
        return int(params.get("delai_relance", 7))
    if niveau_code == "rappel":
        return max(int(params.get("delai_rappel", 48)) // 24, 1)
    return 7


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------
def generer(
    facture: dict,
    params: dict,
    niveau_code: str | None = None,
    ton: str | None = None,
    langue: str | None = None,
    proba_30: float | None = None,
    date_probable=None,
    nb_relances: int | None = None,
    historique_actions: str | None = None,
) -> dict:
    """Produit le message prêt à envoyer pour une facture.

    Renvoie un dict : ``objet``, ``texte``, ``canal``, ``ton``, ``langue``,
    ``niveau``, ``source`` (``modele_local`` ou ``ia``) et ``avertissements``.
    """
    niveau_code = niveau_code or facture.get("niveau") or "rappel"
    if niveau_code == config.NIVEAU_A_JOUR["code"]:
        return {
            "objet": "Aucune action requise",
            "texte": (
                "Échéance non dépassée : aucun message à envoyer pour l'instant. "
                "L'application vous alertera dès le premier jour de retard."
            ),
            "canal": "—",
            "ton": ton or params.get("ton_defaut", "neutre"),
            "langue": langue or params.get("langue_defaut", "fr"),
            "niveau": niveau_code,
            "source": "modele_local",
            "avertissements": [],
        }

    ton = ton or params.get("ton_defaut", "neutre")
    langue = langue or params.get("langue_defaut", "fr")
    if ton not in TONS_FRAGMENTS[langue]:
        ton = "neutre"
    bloc = CORPS.get(niveau_code, CORPS["rappel"])[langue]
    delai = delai_pour_niveau(niveau_code, params)
    contexte = construire_contexte(
        {**facture, "niveau": niveau_code},
        params,
        ton,
        langue,
        delai,
        proba_30=proba_30,
        date_probable=date_probable,
        nb_relances=nb_relances,
        historique_actions=historique_actions,
    )
    texte = bloc["texte"].format(**contexte)
    objet = bloc["objet"].format(**contexte)
    avertissements: list[str] = []

    if niveau_code == "rappel" and len(texte) > 480:
        texte = tronquer_pour_sms(texte)
        avertissements.append("SMS raccourci : préférez un email si le message dépasse 3 SMS.")
    if niveau_code in ("miseendemeure", "contentieux"):
        avertissements.append(
            "Brouillon à faire valider par un juriste avant envoi (mentions et délais à adapter)."
        )
    if niveau_code == "miseendemeure" and not (params.get("adresse") and params.get("ville")):
        avertissements.append(
            "Complétez l'adresse et la ville de la société dans les Réglages : elles encadrent la validité de la mise en demeure."
        )
    if niveau_code == "contentieux":
        avertissements.append(
            "Joignez le journal PDF des relances : c'est la preuve du recouvrement amiable déjà mené."
        )

    return {
        "objet": objet,
        "texte": texte,
        "canal": bloc["canal"],
        "ton": ton,
        "langue": langue,
        "niveau": niveau_code,
        "source": "modele_local",
        "avertissements": avertissements,
    }


def controle_juridique(texte: str, facture: dict, params: dict) -> list[dict]:
    """Vérifie qu'une mise en demeure contient les mentions indispensables.

    Renvoie une liste de contrôles ``{libelle, ok, detail}``.
    """
    montant = formater_montant(facture.get("montant") or 0, params.get("devise", "MAD"), "fr")
    controle = [
        {
            "libelle": "Référence de la facture",
            "ok": bool(facture.get("numero")) and str(facture.get("numero")) in texte,
        },
        {
            "libelle": "Montant réclamé",
            "ok": montant.replace(" MAD", "") in texte or f"{float(facture.get('montant') or 0):,.2f}" in texte,
        },
        {
            "libelle": "Délai accordé",
            "ok": any(mot in texte.lower() for mot in ("au plus tard", "délai", "delai", "jours à compter", "days from")),
        },
        {
            "libelle": "Conséquences en cas de non-paiement",
            "ok": any(
                mot in texte.lower()
                for mot in ("action en recouvrement", "transmettrons", "frais", "intérêts", "interets", "legal counsel", "recovery")
            ),
        },
        {
            "libelle": "Identification du créancier",
            "ok": bool(params.get("societe")) and params.get("societe") in texte,
        },
        {
            "libelle": "Signature et date",
            "ok": any(mot in texte.lower() for mot in ("signature", "fait à", "fait le", "done at", "dated", "cachet")),
        },
    ]
    return controle
