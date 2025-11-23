# Guide de Test - Abonnement Freemium

## Installation

1. Installer les dépendances:
```bash
python3 -m pip install -r requirements.txt
```

2. Vérifier que le fichier `.env` existe et contient vos clés Stripe:
```bash
STRIPE_SECRET_KEY=your_stripe_secret_key_here
STRIPE_PUBLISHABLE_KEY=your_stripe_publishable_key_here
STRIPE_PREMIUM_PRICE_ID=your_premium_price_id_here
```

3. Lancer le serveur:
```bash
cd suivi-finance
python3 app.py
```

## Test du Flux Freemium

### 1. Vérifier l'état initial (Freemium)

1. Se connecter à l'application
2. Ouvrir la console du navigateur (F12)
3. Sur la page d'accueil, vérifier que seul le bouton "3m" est actif
4. Les boutons "6m", "1an", "MAX" doivent avoir un cadenas 🔒

### 2. Tester le clic sur un bouton verrouillé

1. Cliquer sur "6m" ou "1an" ou "MAX"
2. Une modale Premium doit s'ouvrir avec:
   - Le titre "Passez à Premium"
   - Le prix "3,99€/mois"
   - "3 jours d'essai gratuit"
   - Un bouton "Commencer l'essai gratuit"

### 3. Tester le processus de paiement

1. Cliquer sur "Commencer l'essai gratuit"
2. Vérifier les logs de la console:
   ```
   🔑 Auth token présent: true
   📧 Email utilisateur: [votre email]
   🚀 Création session checkout...
   ```
3. Vous devez être redirigé vers Stripe Checkout
4. Utiliser la carte de test: `4242 4242 4242 4242`
   - Date: n'importe quelle date future (ex: 12/25)
   - CVC: n'importe quel 3 chiffres (ex: 123)
   - Code postal: n'importe lequel (ex: 75001)

### 4. Vérifier la synchronisation après paiement

1. Après le paiement, vous serez redirigé vers `/subscription?success=true`
2. Vérifier les logs de la console du navigateur:
   ```
   📊 URL params - success: true canceled: null
   ✅ Utilisateur Firebase connecté: [uid]
   🔑 Token Firebase récupéré
   ✅ Mode succès activé
   🔄 Début de la synchronisation...
   ✅ Synchronisation abonnement: {success: true, data: {plan: "trial", status: "active"}}
   ```

3. Vérifier les logs du serveur Flask:
   ```
   🔄 SYNC: Début synchronisation pour user_id=[uid]
   🔄 SYNC: Subscription Firebase = {...}
   🔄 SYNC: Customer ID Stripe = cus_...
   🔄 SYNC: Récupération des abonnements depuis Stripe...
   🔄 SYNC: Nombre d'abonnements trouvés = 1
   🔄 SYNC: Abonnement Stripe trouvé:
     - ID: sub_...
     - Status: active
     - Trial end: [timestamp]
   ✅ SYNC: Plan déterminé = TRIAL
   🔄 SYNC: Mise à jour Firebase avec les données: {...}
   ✅ SYNC: Firebase mis à jour avec succès!
   ```

4. Après 2 secondes, redirection automatique vers `/`

### 5. Vérifier l'accès Premium

1. Sur la page d'accueil, tous les boutons (3m, 6m, 1an, MAX) doivent être déverrouillés
2. Le badge dans le header doit afficher "ESSAI" ou "Premium"
3. Vous pouvez maintenant cliquer sur n'importe quelle période

### 6. Vérifier la persistance

1. Se déconnecter et se reconnecter
2. Le statut Premium/Trial doit être conservé
3. Les boutons restent déverrouillés

## Synchronisation Automatique

Si l'utilisateur a un `stripe_customer_id` mais est en plan "freemium" (cas où le webhook n'a pas fonctionné), une synchronisation automatique se déclenche au chargement de la page d'accueil.

Logs attendus:
```
🔄 Auto-sync: Utilisateur a un customer_id mais est freemium
🔄 Lancement synchronisation automatique...
✅ Synchronisation auto terminée: {...}
```

## Vérifier dans Firebase

1. Aller dans Firebase Console > Firestore
2. Collection `subscriptions` > Document avec votre UID
3. Vérifier les champs:
   - `plan`: "trial" (pendant les 3 jours)
   - `status`: "active"
   - `stripe_customer_id`: "cus_..."
   - `stripe_subscription_id`: "sub_..."
   - `trial_end`: [timestamp dans 3 jours]
   - `current_period_end`: [timestamp]

## Carte de Test Stripe

Pour les tests, utilisez toujours:
- Numéro: `4242 4242 4242 4242`
- Date d'expiration: n'importe quelle date future
- CVC: n'importe quel 3 chiffres
- Code postal: n'importe lequel

## Troubleshooting

### La synchronisation ne fonctionne pas

1. Vérifier que le token Firebase est bien récupéré (console navigateur)
2. Vérifier les logs du serveur Flask
3. Vérifier que la clé Stripe dans `.env` est correcte (sans guillemets)

### Les boutons restent verrouillés après paiement

1. Vérifier Firebase pour confirmer que `plan` = "trial"
2. Rafraîchir la page
3. Vérifier les logs de synchronisation automatique

### Erreur "Invalid API Key"

1. Vérifier que `.env` n'a pas de guillemets autour des clés
2. Redémarrer le serveur après modification de `.env`

## Après les 3 jours d'essai

Stripe facturera automatiquement 3,99€ et le plan passera de "trial" à "premium".
Les fonctionnalités restent identiques (tous les boutons déverrouillés).
