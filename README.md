# Scoring des Impayés — V2 (Streamlit + IA Claude)

Application de relance des impayés : elle **note chaque facture en retard sur 100**,
déclenche **l'action adaptée** selon le nombre de jours de retard, **prépare le message**
(SMS, script d'appel, email, mise en demeure, note avocat) et **garde la preuve** de chaque relance.

## Lancer l'application

```powershell
# 1) installer les dépendances
pip install -r requirements.txt

# 2) démarrer
streamlit run app.py
```

> Si `python`/`pip` n'est pas reconnu, installez Python 3.10+ et cochez « Add to PATH ».

## Les 5 pages

| Page | Contenu |
|---|---|
| **Tableau de bord** | Cartes (impayé total, factures en retard, retard moyen, encaissement prévu 30 j), entonnoir cliquable des 5 niveaux, courbe d'évolution, top 5 urgences |
| **Factures** | Liste triée par score, badges colorés, filtres (niveau / client / montant), ajout, import Excel-CSV, détection d'anomalies |
| **Fiche & message** | Jauge de score, explication du score, frise des étapes, compte à rebours, prédiction de paiement, recommandation, message à copier, boutons Copier/Régénérer/Marquer fait/payée |
| **Assistant IA** | Briefing quotidien et conversation en langage naturel + simulateur de trésorerie (7/30/90 j) |
| **Réglages & historique** | Société, seuils, pondérations du score, clé IA, journal horodaté exportable (CSV / PDF) |

## Niveaux de traitement (réglables)

| Retard | Action |
|---|---|
| 1–7 j | SMS de rappel |
| 8–14 j | Appel téléphonique |
| 15–29 j | Email personnalisé |
| 30–59 j | Mise en demeure |
| 60 j et + | Transmission à l'avocat |

## Scoring (0–100)

Somme pondérée, pondérations réglables dans **Réglages** :
- **Retard** (défaut 40 pts, 60 j = max)
- **Montant** (25 pts, relatif à la plus grosse facture)
- **Historique du client** (20 pts, 5 retards = max)
- **Risque IA** (15 pts = 1 − probabilité de paiement à 30 j)

Chaque score est **expliqué en une phrase** (aucune boîte noire).

## Prédiction de paiement

- Probabilité d'être payée à **7 / 15 / 30 jours**, date probable, profil client
  (Bon payeur, Distrait, Lent mais fiable, Récidiviste, À risque).
- **Sans historique** : modèle heuristique.
- **Dès ~12 factures payées** : une régression logistique (scikit-learn) affine l'estimation.

## IA Claude (optionnelle)

- **Sans clé API** : l'application fonctionne avec des gabarits et des réponses locales.
- **Avec clé** : rédaction des messages (ton + langue FR/AR/EN), recommandation
  « meilleure action suivante », briefing quotidien, assistant conversationnel.

Pour activer : page **Réglages & historique** → *Clé API Anthropic* → collez votre clé
(`sk-ant-...`). Le modèle par défaut est `claude-sonnet-4-5` (modifiable).

## Points juridiques et données

- Les modèles de **mise en demeure** et de **note à l'avocat** sont des **brouillons** :
  faites-les valider par un juriste, ainsi que les seuils de 30 et 60 jours.
- Noms, téléphones et emails sont des **données personnelles** : conformité **loi 09-08 / CNDP**.
- Aucun message n'est envoyé automatiquement : vous relisez, copiez et envoyez vous-même.
- Stockage des données **en session** : elles sont perdues à la fermeture de l'application.

## Feuille de route du cahier

- ✅ **V1 (socle)** : factures, retards, niveaux, scoring, messages, historique.
- ✅ **V2 (IA)** : messages générés, recommandations, assistant, briefing.
- 🔜 **V3 (prédictif)** : probabilité de paiement (implémentée), profils clients, simulateur
  (implémenté), import de factures scannées (à venir).
- 🔜 **V4 (connectée)** : envoi direct SMS/emails, rapprochement bancaire.
