# Configuration Stripe pour le Modèle Freemium

## 📋 Guide de Configuration Complète

### 1. Créer un Compte Stripe

1. Allez sur [stripe.com](https://stripe.com) et créez un compte
2. Activez votre compte (vérification d'identité requise pour la production)
3. Accédez au [Dashboard Stripe](https://dashboard.stripe.com)

### 2. Créer les Produits et Prix

#### Produit Premium (4,99€/mois)

1. Dans le Dashboard Stripe, allez dans **Produits** → **Créer un produit**
2. Remplissez les informations :
   - **Nom** : `Suivi Finance Premium`
   - **Description** : `Accès complet aux fonctionnalités premium de suivi de portefeuille`
3. Ajoutez un prix :
   - **Type** : Récurrent
   - **Prix** : `4,99 EUR`
   - **Fréquence** : Mensuel
   - **ID Prix** : Notez l'ID généré (ex: `price_1234567890abcdef`)

### 3. Configurer les Webhooks

#### Créer l'Endpoint Webhook

1. Allez dans **Développeurs** → **Webhooks**
2. Cliquez sur **Ajouter un endpoint**
3. URL de l'endpoint : `https://votre-domaine.com/api/stripe/webhook`
4. Sélectionnez les événements à écouter :
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
5. Notez le **Secret de signature** généré

### 4. Configuration des Variables d'Environnement

Copiez le fichier `.env.example` vers `.env` et remplissez :

```bash
cp .env.example .env
```

Éditez `.env` avec vos vraies valeurs :

```env
# Clés de test (pour développement)
STRIPE_SECRET_KEY=sk_test_51xxxxx...
STRIPE_PUBLISHABLE_KEY=pk_test_51xxxxx...
STRIPE_WEBHOOK_SECRET=whsec_xxxxx...

# ID du prix premium
STRIPE_PREMIUM_PRICE_ID=price_xxxxx...

# Clés de production (quand vous êtes prêt)
# STRIPE_SECRET_KEY=sk_live_51xxxxx...
# STRIPE_PUBLISHABLE_KEY=pk_live_51xxxxx...
```

### 5. Configuration du Portail Client

1. Dans le Dashboard, allez dans **Paramètres** → **Portail de facturation**
2. Activez le portail client
3. Configurez :
   - **Lien de retour par défaut** : `https://votre-domaine.com/subscription`
   - **Fonctionnalités** : Mettre à jour les informations de paiement, Télécharger les factures, Annuler l'abonnement

### 6. Test en Mode Développement

#### Cartes de Test Stripe

Utilisez ces numéros de carte pour tester :

- **Succès** : `4242 4242 4242 4242`
- **Échec** : `4000 0000 0000 0002`
- **3D Secure** : `4000 0027 6000 3184`

#### Tester les Webhooks Localement

1. Installez le CLI Stripe :
```bash
# macOS
brew install stripe/stripe-cli/stripe

# Ou téléchargez depuis https://stripe.com/docs/stripe-cli
```

2. Connectez-vous :
```bash
stripe login
```

3. Écoutez les webhooks localement :
```bash
stripe listen --forward-to localhost:8000/api/stripe/webhook
```

4. Testez un événement :
```bash
stripe trigger checkout.session.completed
```

### 7. Fonctionnalités Implémentées

#### ✅ Fonctionnalités Backend
- [x] Service Stripe complet avec gestion des abonnements
- [x] Webhooks pour synchronisation automatique
- [x] Modèle de données Firebase étendu pour les abonnements
- [x] Décorateurs d'authentification premium
- [x] Limitations freemium sur les APIs

#### ✅ Fonctionnalités Frontend
- [x] Page de gestion des abonnements (`/subscription`)
- [x] Composants de paywall réutilisables
- [x] Modal de limitation freemium
- [x] Badges premium et indicateurs visuels

#### ✅ Limitations Freemium Implémentées
- [x] **Dashboard** : Graphiques limités à 1 mois
- [x] **Positions** : Analyse d'1 position maximum
- [x] **Projections** : Capital actuel seulement (pas de contributions)
- [x] **Exports** : JSON seulement (pas CSV/Excel)

### 8. Routes API Disponibles

```
GET  /api/subscription          # Infos abonnement utilisateur
POST /api/subscription/checkout # Créer session checkout
POST /api/subscription/portal   # Accès portail client
POST /api/subscription/trial    # Démarrer essai gratuit
POST /api/subscription/cancel   # Annuler abonnement
POST /api/stripe/webhook        # Webhook Stripe
GET  /api/export/{type}         # Export avec limitations freemium
```

### 9. Sécurité et Production

#### Variables d'Environnement Sécurisées
- Utilisez un gestionnaire de secrets (AWS Secrets Manager, etc.)
- Ne jamais committer les clés dans le code
- Utilisez les clés de test pendant le développement

#### HTTPS Obligatoire
Stripe exige HTTPS pour les webhooks en production.

#### Validation des Webhooks
Le code vérifie automatiquement la signature des webhooks pour éviter les attaques.

### 10. Monitoring et Analytics

#### Événements à Suivre
- Conversions d'essai gratuit vers premium
- Taux d'annulation
- Utilisation des fonctionnalités premium
- Erreurs de paiement

#### Dashboard Stripe
Surveillez les métriques dans le Dashboard Stripe :
- MRR (Monthly Recurring Revenue)
- Churn rate
- Customer Lifetime Value

### 11. Support et Documentation

- [Documentation Stripe](https://stripe.com/docs)
- [API Reference](https://stripe.com/docs/api)
- [Webhooks Guide](https://stripe.com/docs/webhooks)
- [Testing Guide](https://stripe.com/docs/testing)

---

## 🚀 Déploiement

1. Configurez votre serveur avec HTTPS
2. Mettez les clés de production dans les variables d'environnement
3. Testez les webhooks en production
4. Configurez le monitoring des erreurs
5. Lancez ! 🎉