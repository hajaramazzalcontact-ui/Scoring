# Scoring des Impayés — V3 (Streamlit + IA Claude)

Application de relance des impayés en français, en dirhams (MAD) : elle **note chaque
facture en retard sur 100**, déclenche **l'action adaptée** selon le nombre de jours de
retard, **prépare le message** (SMS, script d'appel, email, mise en demeure, note avocat)
et **garde la preuve** de chaque relance.

- Fonctionne **à 100 % sans clé API** (gabarits et réponses locales).
- **Aucun envoi automatique** : vous relisez, copiez et envoyez vous-même.
- Données **en session** : rien n'est écrit sur le disque.

## Lancer l'application

```powershell
# 1) installer les dépendances
pip install -r requirements.txt

# 2) démarrer
streamlit run app.py
```

> Si `python`/`pip` n'est pas reconnu, installez Python 3.10+ et cochez « Add to PATH ».

**Mode démonstration partageable** : ajoutez `?demo=1` à l'URL
(`http://localhost:8501/?demo=1`) pour charger 8 factures fictives sans rien saisir.

## Les 10 onglets

Chaque onglet affiche **ses graphiques et ses données clés** (rappelés sous le titre).

| # | Onglet | Graphiques | Données clés |
|---|---|---|---|
| 1 | **Tableau de bord** | Entonnoir cliquable, évolution du retard, volume/montant par niveau | Impayé total animé, santé du portefeuille, relances de la semaine, encaissement prévu |
| 2 | **Clients** | Top clients (barres horizontales) | Nombre de factures, montant dû, retard moyen, niveau dominant |
| 3 | **Factures** | — | Liste triée par score, filtres, ajout, import Excel/CSV, détection d'anomalies |
| 4 | **Fiche & message** | Jauge de score, frise des étapes | Explication du score, compte à rebours, prédiction, recommandation IA, message, preuve |
| 5 | **Analyses** | Carte de chaleur, donut des profils, nuage de points, histogramme | Score moyen, factures et montants > 30 j, concentration |
| 6 | **Trésorerie** | Cascade d'encaissement, encaissement cumulé | Encaissement attendu 7/30/90 j, 3 scénarios, simulateur temps réel |
| 7 | **Calendrier** | Calendrier coloré des échéances | Échéances du mois, montants par jour, retards |
| 8 | **Cashy — Assistant IA** | — | Briefing du jour, conversation en langage naturel |
| 9 | **Historique & preuves** | Journal horodaté (tableau), exports | Preuves de relance, 4 familles de données, exports CSV/Excel/PDF |
| 10 | **Réglages** | — | Prénom, société, seuils, pondérations, IA, apparence |

## L'expérience utilisateur (« effet waouh »)

- **Compteur animé** de l'impayé total en MAD, qui s'incrémente à l'ouverture.
- **Phrase d'accueil personnalisée** : « Bonjour Karim, 7 factures à traiter aujourd'hui,
  190 000 MAD attendus cette semaine. » (prénom réglable dans *Réglages*).
- **Action unique** : bouton « 🚀 Commencer les relances » qui ouvre la liste filtrée.
- **Santé du portefeuille** : note sur 100 (retard, probabilité de paiement, ancienneté,
  concentration), avec un libellé et une couleur.
- **Progression de la semaine** : « 72 % des relances faites » + série de jours d'affilée.
- **Argent récupéré** : montant des factures clôturées, mis en avant sur l'accueil.
- **Simulateur temps réel** : deux curseurs (horizon, hypothèse de recouvrement) font
  bouger la cascade de trésorerie et les 3 scénarios instantanément.
- **Ton par curseur** : `bienveillant → neutre → ferme` (au lieu d'une case à cocher).
- **Cashy**, l'assistant IA, a une identité propre (violet) et une bulle de conversation.
- **Message qui s'écrit en direct** à l'écran, avec bouton *Copier* et bouton *Régénérer*.
- **Étiquettes « ✨ Recommandé par l'IA »** avec la raison en une phrase.
- **Visite guidée en 3 étapes** au premier lancement, refermable.
- **États vides soignés** : message positif et bouton de démo plutôt qu'un écran blanc.
- **Récompense** : confettis (`st.balloons`) et toast vert quand une facture est payée.

## 7.1 Palette et identité visuelle

| Rôle | Couleur | Hex | Usage |
|---|---|---|---|
| Marque | Bleu nuit | `#0B1F3A` | Titres, navigation, en-têtes |
| Marque claire | Bleu nuit clair | `#16325C` | Survols, accents secondaires |
| Paiements | Turquoise | `#14B8A6` | Montants encaissés, boutons principaux, barres de progression |
| IA | Violet | `#7C3AED` | Tout ce qui est produit par l'IA (messages, briefings, recommandations) |
| Alerte | Rouge | `#DC2626` | Erreurs, reste à risque |

**Échelle d'urgence (5 niveaux, du vert au noir)** — chaque couleur est doublée d'une
icône pour les personnes daltoniennes :

| Niveau | Couleur | Icône | Action |
|---|---|---|---|
| 1 — Rappel | `#16A34A` | 🟢 | SMS de rappel |
| 2 — Contact | `#65A30D` | 🟡 | Appel téléphonique |
| 3 — Relance | `#CA8A04` | 🟠 | Email personnalisé |
| 4 — Mise en demeure | `#B45309` | 🔴 | Courrier |
| 5 — Contentieux | `#111827` | ⚫ | Transmission à l'avocat |

**Mode sombre élégant** : deux thèmes complets sont définis dans `.streamlit/config.toml`
(`[theme.light]` et `[theme.dark]`). L'utilisateur bascule via **⋮ → Settings → Theme**
(ou suit le réglage système). L'application détecte le thème actif (`st.context.theme`)
et adapte cartes, badges, graphiques et composants animés.

**Style fintech** : coins arrondis (18 px), ombres légères, typographie nette, gros
chiffres pour les indicateurs, texte discret, beaucoup d'espace blanc.

## 7.2 Catalogue des 13 graphiques

| # | Graphique | Type | Page |
|---|---|---|---|
| 1 | Entonnoir des 5 niveaux | Entonnoir **cliquable** (filtre + navigation) | Tableau de bord |
| 2 | Évolution du retard | Courbe | Tableau de bord |
| 3 | Volume et montant par niveau | Barres groupées | Tableau de bord |
| 4 | Score de la facture | Jauge | Fiche & message |
| 5 | Étapes de la relance | Frise chronologique | Fiche & message |
| 6 | Top clients | Barres horizontales | Clients |
| 7 | Clients × niveaux | Carte de chaleur | Analyses |
| 8 | Profils clients | Donut | Analyses |
| 9 | Montant × retard | Nuage de points | Analyses |
| 10 | Distribution des retards | Histogramme | Analyses |
| 11 | Cascade d'encaissement | Cascade (waterfall) | Trésorerie |
| 12 | Encaissement cumulé 90 j | Courbe cumulée | Trésorerie |
| 13 | Échéances du mois | Calendrier coloré | Calendrier |

Tous les graphiques sont en **Plotly** (interactifs, thème clair/sombre appliqué).

Un visuel complémentaire apparaît en **Trésorerie** dès qu'une facture est clôturée :
le **cumul de l'argent récupéré** grâce aux relances.

## 7.3 Les 4 familles de données et leurs exports

| Famille | Contenu | Provenance | Consultation | Export |
|---|---|---|---|---|
| ① **Saisies** | Factures, clients, coordonnées, statuts | Utilisateur (formulaire, import) | Clients, Factures | CSV `donnees_saisies.csv` |
| ② **Calculées** | Jours de retard, niveau, score, p7/p15/p30, profil, date probable | Moteur de score et modèle | Factures, Fiche, Analyses | CSV `donnees_calculees.csv` |
| ③ **IA** | Messages, recommandations, briefing | Claude **ou** gabarits locaux | Fiche, Cashy | CSV `contenus_ia.csv` |
| ④ **Historique** | Actions horodatées = preuves de relance | Journal | Historique & preuves | CSV, PDF (si `fpdf2`), Excel |

Un **export Excel unique** (`donnees_impayes.xlsx`) regroupe les quatre familles dans un
classeur à quatre feuilles.

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
- **Avec clé** : rédaction des messages (3 tons × FR/AR/EN = 9 variantes par niveau),
  recommandation « meilleure action suivante », briefing quotidien, assistant Cashy.

Pour activer : page **Réglages** → *Clé API Anthropic* → collez votre clé (`sk-ant-...`).
Le modèle par défaut est `claude-sonnet-4-5` (modifiable).

## Déployer sur Streamlit Cloud

1. Poussez le dépôt sur GitHub (branche `main`).
2. Sur [share.streamlit.io](https://share.streamlit.io) → **New app** → dépôt
   `hajaramazzalcontact-ui/mon_app`, branche `main`, fichier principal **`app.py`**.
3. (Optionnel) **Clé IA en ligne** : *Settings → Secrets* :

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ANTHROPIC_MODEL = "claude-sonnet-4-5"
   ```

   L'application lit ces secrets au démarrage ; sinon, laissez vide et saisissez la clé
   dans *Réglages*.
4. Les données sont **en session** : chaque visiteur démarre avec un portefeuille vide
   (bouton *Charger la démo* disponible). Rien n'est écrit sur le disque.

## Tests

```powershell
.\.venv\Scripts\python.exe tests\parcours.py
```

Le parcours charge la démo, visite les **10 onglets**, vérifie la phrase d'accueil et le
bouton « Commencer les relances », la visite guidée, puis génère les **9 combinaisons
ton × langue** et contrôle qu'elles sont toutes distinctes.

## Points juridiques et données

- Les modèles de **mise en demeure** et de **note à l'avocat** sont des **brouillons** :
  faites-les valider par un juriste, ainsi que les seuils de 30 et 60 jours.
- Un **contrôle automatique des mentions** (référence, montant, délai, date, créancier,
  qualification, avocat) s'affiche pour les niveaux 4 et 5 — ce n'est pas un avis juridique.
- Noms, téléphones et emails sont des **données personnelles** : conformité **loi 09-08 / CNDP**.
- Aucun message n'est envoyé automatiquement : vous relisez, copiez et envoyez vous-même.
- Stockage des données **en session** : elles sont perdues à la fermeture de l'application.

## Feuille de route

- ✅ **V1 (socle)** : factures, retards, niveaux, scoring, messages, historique.
- ✅ **V2 (IA)** : messages générés, recommandations, assistant, briefing.
- ✅ **V3 (pilotage)** : 10 onglets, 13 graphiques, 4 familles de données, prédiction de
  paiement, simulateur de trésorerie, palette et mode sombre, expérience « waouh ».
- 🔜 **V4 (connectée)** : envoi direct SMS/emails, rapprochement bancaire, persistance locale.
