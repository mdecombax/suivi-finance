# Suivi Finance

Application complète de suivi de portefeuille d'investissement avec authentification Firebase, paiements Stripe et modèle freemium.

## 🚀 Installation Rapide

### 1. Prérequis
- Python 3.8+
- Node.js 16+ (pour les dépendances Firebase frontend)
- Compte Firebase (gratuit)
- Compte Stripe (optionnel pour le freemium)

### 2. Installation

```bash
# Cloner le repository
git clone <your-repo-url>
cd suivi-finance

# Activer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# Installer les dépendances Python
pip install -r requirements.txt

# Installer les dépendances Node.js
npm install
```

### 3. Configuration Firebase

#### 3.1 Créer un projet Firebase
1. Aller sur [console.firebase.google.com](https://console.firebase.google.com)
2. Créer un nouveau projet
3. Activer **Authentication** avec Email/Password et Google
4. Créer une base de données **Firestore** en mode production

#### 3.2 Règles de sécurité Firestore

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Règles pour les données utilisateur
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;

      // Sous-collection des ordres
      match /orders/{orderId} {
        allow read, write: if request.auth != null && request.auth.uid == userId;
      }
    }
  }
}
```

#### 3.3 Télécharger les clés

1. **Clé de service Admin (Backend)**:
   - Aller dans Paramètres du projet > Comptes de service
   - Générer une nouvelle clé privée
   - Renommer le fichier en `suivi-financ-firebase-adminsdk-*.json`
   - Placer à la racine du projet

2. **Configuration Web (Frontend)**:
   - Aller dans Paramètres du projet > Général
   - Dans "Vos applications", sélectionner "Web"
   - Copier la configuration Firebase
   - Créer `firebase-config.json` à la racine avec:

```json
{
  "apiKey": "votre-api-key",
  "authDomain": "votre-projet.firebaseapp.com",
  "projectId": "votre-projet-id",
  "storageBucket": "votre-projet.appspot.com",
  "messagingSenderId": "123456789",
  "appId": "votre-app-id"
}
```

### 4. Configuration Stripe (Optionnel)

#### 4.1 Créer un compte Stripe
1. S'inscrire sur [stripe.com](https://stripe.com)
2. Activer le mode test

#### 4.2 Créer un produit Premium
1. Aller dans Produits > Ajouter un produit
2. Nom: "Premium Monthly"
3. Prix: 9.99 EUR/mois (ou votre tarif)
4. Récurrent: Mensuel
5. Copier l'ID du prix (commence par `price_...`)

#### 4.3 Configurer les variables d'environnement

Créer un fichier `.env` à la racine:

```bash
# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_PREMIUM_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...  # Optionnel, pour les webhooks

# Flask
FLASK_ENV=development
FLASK_DEBUG=True
HOST=0.0.0.0
PORT=8000
```

#### 4.4 Configurer les webhooks (Production)

1. Aller dans Développeurs > Webhooks
2. Ajouter un endpoint: `https://votre-domaine.com/api/stripe/webhook`
3. Sélectionner les événements:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
4. Copier le secret de signature webhook dans `.env`

### 5. Lancement

```bash
# Activer l'environnement virtuel (si pas déjà fait)
source venv/bin/activate

# Démarrer l'application
python app.py
```

L'application sera accessible sur `http://localhost:8000`

## 📁 Architecture du Projet

```
suivi-finance/
├── app.py                              # Application Flask principale (routes)
├── database.py                         # Firebase/Firestore + Auth middleware
├── payments.py                         # Stripe integration
├── models.py                           # Dataclasses (Portfolio, Projections)
├── services/
│   ├── portfolio_service.py            # Logique métier portefeuille
│   ├── price_service.py                # Récupération des prix (Yahoo, JustETF)
│   └── projection_service.py           # Calculs de projections financières
├── templates/                          # Pages HTML
│   ├── index.html                      # Dashboard principal
│   ├── orders.html                     # Gestion des ordres
│   ├── login.html                      # Page de connexion
│   ├── register.html                   # Page d'inscription
│   ├── projections.html                # Projections financières
│   ├── subscription.html               # Gestion de l'abonnement
│   └── position_detail.html            # Détail d'une position
├── static/                             # Assets statiques (CSS, JS, images)
├── requirements.txt                     # Dépendances Python
├── package.json                        # Dépendances Node.js
├── firebase-config.json                # Config Firebase frontend
└── .env                                # Variables d'environnement

### Nouveauté: Architecture simplifiée
✅ Modules consolidés (database.py, payments.py, models.py)
✅ Plus de classes wrapper inutiles
✅ Routes Flask directes
✅ Code plus lisible et maintenable
```

## 🔧 Fonctionnalités Principales

### Authentification
- Connexion Email/Password
- Connexion Google OAuth
- Inscription sécurisée
- Gestion des sessions JWT
- Middleware d'authentification

### Gestion du Portefeuille
- **KPIs en temps réel**: Total investi, Valeur actuelle, P/L, Performance annualisée
- **Analyse fiscale**: Comparaison PEA vs CTO (30% flat tax)
- **Positions agrégées**: Vue consolidée par ISIN
- **Performance XIRR**: Calcul du taux de rendement money-weighted
- **Graphiques**: Évolution du portefeuille dans le temps

### Ordres d'Investissement
- Ajout/Suppression d'ordres
- Récupération automatique des prix (date historique ou actuel)
- Validation ISIN
- Historique complet
- Export des données

### Projections Financières
- **3 scénarios**: Pessimiste (3%), Normal (7%), Optimiste (11%)
- Contributions mensuelles programmables
- Horizon temporel ajustable (1-50 ans)
- Prise en compte des frais (0.75% annuels par défaut)
- Graphiques d'évolution

### Modèle Freemium

#### Plan Gratuit (Freemium)
- ✅ Gestion illimitée des ordres
- ✅ Dashboard avec KPIs actuels
- ✅ 1 période d'analyse (1 mois)
- ✅ Projections capital actuel uniquement
- ✅ Export JSON
- ❌ Contributions récurrentes dans projections
- ❌ Périodes historiques multiples
- ❌ Analyse détaillée par position
- ❌ Export CSV/Excel

#### Plan Premium (9.99€/mois)
- ✅ Toutes les fonctionnalités gratuites
- ✅ Essai gratuit de 3 jours
- ✅ Projections avec contributions récurrentes
- ✅ Périodes d'analyse multiples (1m, 3m, 6m, 1a, YTD, All)
- ✅ Analyse détaillée de chaque position
- ✅ Export CSV et Excel
- ✅ Graphiques avancés
- ✅ Support prioritaire

## 🌐 API Endpoints

### Authentification
- `POST /api/auth/verify` - Vérifier un token Firebase

### Portefeuille
- `GET /api/portfolio` - Récupérer les données du portefeuille
- `POST /api/portfolio` - Mettre à jour le type de compte
- `GET /api/portfolio/monthly-values` - Évolution mensuelle du portefeuille (Premium)

### Ordres
- `GET /api/orders` - Récupérer tous les ordres
- `POST /api/orders` - Ajouter un nouvel ordre
- `DELETE /api/orders?order_id=xxx` - Supprimer un ordre

### Prix
- `GET /api/price/<isin>` - Prix actuel d'un ISIN
- `GET /api/historical_prices/<isin>?date=YYYY-MM-DD` - Prix historique
- `GET/POST /api/history?isin=...&dateFrom=...&dateTo=...` - Série historique

### Positions
- `GET /api/position/<isin>` - Détails enrichis d'une position
- `GET /api/position/<isin>/monthly-values` - Évolution mensuelle (Premium)

### Projections
- `GET /api/projections` - Projections par défaut
- `POST /api/projections` - Projections personnalisées (Premium pour contributions)

### Export
- `GET /api/export/json` - Export JSON (Gratuit)
- `GET /api/export/csv` - Export CSV (Premium)
- `GET /api/export/excel` - Export Excel (Premium)

### Abonnement
- `GET /api/subscription` - Informations d'abonnement
- `POST /api/subscription/checkout` - Créer session de paiement
- `POST /api/subscription/portal` - Accéder au portail Stripe
- `POST /api/subscription/trial` - Démarrer l'essai gratuit
- `POST /api/subscription/cancel` - Annuler l'abonnement
- `POST /api/subscription/sync` - Synchroniser statut Stripe ↔ Firebase

### Webhooks
- `POST /api/stripe/webhook` - Webhook Stripe (pour la synchronisation)

## 🔒 Sécurité

### Backend
- Authentification Firebase obligatoire sur toutes les routes sensibles
- Validation des tokens JWT à chaque requête
- Isolation des données par utilisateur (userId)
- Règles Firestore restrictives côté serveur
- Variables d'environnement pour les secrets

### Frontend
- Tokens stockés en localStorage (HttpOnly en production recommandé)
- CORS configuré pour domaines autorisés
- Validation des inputs côté client et serveur
- Protection CSRF sur les formulaires

### Base de données
- Firestore avec règles de sécurité strictes
- Indexation automatique pour les performances
- Backup automatique (si configuré dans Firebase)

## 🎨 Développement

### Structure du code

**database.py** - Tout ce qui concerne Firebase:
- `FirebaseService`: Gestion Firestore (ordres, abonnements)
- `verify_firebase_token()`: Vérification des tokens
- Décorateurs: `@require_auth`, `@require_premium`, `@check_freemium_limits`
- Helpers: `get_current_user_id()`, `get_user_plan_info()`

**payments.py** - Tout ce qui concerne Stripe:
- `StripeService`: Gestion des paiements et abonnements
- `create_checkout_session()`: Créer une session de paiement
- `create_customer_portal_session()`: Portail de gestion
- `handle_webhook()`: Traitement des webhooks Stripe

**models.py** - Tous les dataclasses:
- `InvestmentOrder`: Ordre d'investissement
- `PositionSummary`: Position agrégée
- `PerformanceMetrics`: Métriques de performance
- `FiscalScenario`: Scénario fiscal (PEA/CTO)
- `PriceQuote`: Citation de prix
- `ProjectionScenario`, `ProjectionParams`, `ProjectionResult`: Projections

**services/** - Logique métier:
- `PortfolioService`: Agrégation, calculs de performance, XIRR
- `PriceService`: Fetch de prix (Yahoo Finance, JustETF)
- `ProjectionService`: Calculs de projections financières

### Ajouter une nouvelle fonctionnalité

1. **Définir le modèle** dans `models.py` si nécessaire
2. **Créer la logique métier** dans un service approprié
3. **Ajouter la route** dans `app.py`
4. **Protéger avec auth** si nécessaire (`@require_auth`, `@require_premium`)
5. **Créer la vue** dans `templates/`
6. **Tester** en local puis déployer

### Debug

```bash
# Activer le mode debug (déjà activé par défaut en dev)
export FLASK_DEBUG=True

# Logs détaillés
tail -f server.log

# Vérifier les règles Firestore
# Aller dans console Firebase > Firestore Database > Rules

# Tester les webhooks Stripe (utiliser Stripe CLI)
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

## 📱 Responsive Design

L'application s'adapte à tous les écrans:
- **Desktop** (1200px+): Layout complet avec sidebar
- **Tablet** (768px - 1199px): Layout adapté
- **Mobile** (< 768px): Navigation hamburger, cartes empilées

## 🚀 Déploiement

### Variables d'environnement (Production)

```bash
FLASK_ENV=production
FLASK_DEBUG=False
HOST=0.0.0.0
PORT=8000
STRIPE_SECRET_KEY=sk_live_...  # Clé LIVE
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_PREMIUM_PRICE_ID=price_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

### Checklist de déploiement

- [ ] Passer Stripe en mode LIVE
- [ ] Mettre à jour les clés API dans `.env`
- [ ] Configurer le webhook Stripe avec l'URL de production
- [ ] Activer HTTPS (obligatoire pour Stripe et Firebase Auth)
- [ ] Configurer les domaines autorisés dans Firebase Auth
- [ ] Vérifier les règles Firestore
- [ ] Désactiver le mode debug (`FLASK_DEBUG=False`)
- [ ] Configurer un reverse proxy (Nginx recommandé)
- [ ] Mettre en place un système de backup
- [ ] Configurer les logs de production
- [ ] Tester le parcours complet utilisateur

### Hébergement recommandé

- **Backend**: Heroku, Google Cloud Run, AWS Elastic Beanstalk, Railway
- **Frontend statique**: Firebase Hosting, Netlify, Vercel
- **Base de données**: Firebase Firestore (inclus)
- **Fichiers**: Firebase Storage (si nécessaire)

## 📊 Données

### Structure Firestore

```
users/
  {userId}/
    subscription: {
      plan: 'freemium' | 'trial' | 'premium'
      status: 'active' | 'inactive' | 'cancel_at_period_end'
      stripe_customer_id: string
      stripe_subscription_id: string
      trial_start: timestamp
      trial_end: timestamp
      current_period_start: timestamp
      current_period_end: timestamp
      created_at: timestamp
      updated_at: timestamp
    }
    orders/
      {orderId}: {
        isin: string
        quantity: number
        unitPrice: number
        totalPriceEUR: number
        date: string (YYYY-MM-DD)
        createdAt: timestamp
        updatedAt: timestamp
      }
```

## 🧪 Tests

```bash
# Installer les dépendances de test (à ajouter à requirements.txt)
pip install pytest pytest-flask pytest-cov

# Lancer les tests
pytest

# Avec coverage
pytest --cov=. --cov-report=html
```

## 📝 Changelog

### Version 2.0.0 (Refactoring Complet)
- ✅ Architecture simplifiée (database.py, payments.py, models.py)
- ✅ Suppression des classes wrapper inutiles
- ✅ Routes Flask directes
- ✅ Imports consolidés
- ✅ Suppression de 7 fichiers MD redondants
- ✅ Meilleure séparation des responsabilités

### Version 1.0.0
- Système d'authentification Firebase
- Gestion du portefeuille
- Intégration Stripe
- Modèle freemium

## 🤝 Contribution

1. Fork le projet
2. Créer une branche (`git checkout -b feature/AmazingFeature`)
3. Commit les changements (`git commit -m 'Add AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

## 📄 Licence

MIT License - Voir le fichier LICENSE pour plus de détails.

## 🆘 Support

- **Documentation**: Ce README
- **Issues**: Utiliser GitHub Issues
- **Email**: support@votre-domaine.com (remplacer)

## 🙏 Remerciements

- Firebase pour l'authentification et la base de données
- Stripe pour les paiements
- Yahoo Finance et JustETF pour les données de prix
- Flask pour le framework web
- Toutes les bibliothèques open-source utilisées
