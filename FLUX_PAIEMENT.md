# Flux de Paiement - Gestion de Session Firebase

## Problème Rencontré

Lors du retour de Stripe Checkout, la session Firebase peut expirer, ce qui empêche la synchronisation automatique immédiate.

## Solution Implémentée

### Flux Complet

1. **Utilisateur Freemium clique sur période verrouillée**
   - Modale Premium s'ouvre
   - Clic sur "Commencer l'essai gratuit"

2. **Création session Stripe**
   - Appel à `/api/subscription/checkout`
   - Création du customer Stripe si nécessaire
   - Redirect vers Stripe Checkout

3. **Paiement sur Stripe**
   - Utilisateur entre carte de test: `4242 4242 4242 4242`
   - Stripe crée l'abonnement avec trial de 3 jours
   - Redirect vers `/subscription?success=true`

4. **Retour sur /subscription?success=true**

   **CAS A: Utilisateur toujours connecté (Firebase Auth active)**
   - ✅ Token récupéré via `onAuthStateChanged`
   - ✅ Appel immédiat à `/api/subscription/sync`
   - ✅ Firebase mis à jour avec plan "trial"
   - ✅ Redirect vers `/` après 2 secondes
   - ✅ Boutons déverrouillés

   **CAS B: Session Firebase expirée**
   - ❌ `onAuthStateChanged` détecte utilisateur non connecté
   - 💾 Sauvegarde flag `pendingSubscriptionSync` dans localStorage
   - 📄 Affichage message: "Votre paiement a été effectué avec succès ! Reconnectez-vous pour activer votre essai."
   - ⏱️ Redirect automatique vers `/` après 3 secondes

5. **Sur la page d'accueil (/)**

   **Si utilisateur non connecté:**
   - Redirect automatique vers `/login`

   **Si utilisateur connecté:**
   - Chargement du plan utilisateur via `/api/subscription`
   - Deux mécanismes de synchronisation automatique:

   **A. Détection client Stripe en freemium:**
   ```javascript
   if (planInfo.plan === 'freemium' && planInfo.stripe_customer_id) {
       syncSubscriptionFromStripe();
   }
   ```

   **B. Détection flag pendingSubscriptionSync:**
   ```javascript
   if (localStorage.getItem('pendingSubscriptionSync') === 'true') {
       localStorage.removeItem('pendingSubscriptionSync');
       syncSubscriptionFromStripe();
   }
   ```

6. **Synchronisation automatique**
   - Appel à `/api/subscription/sync`
   - Backend récupère abonnement Stripe
   - Détection du plan (trial car dans période d'essai)
   - Mise à jour Firebase
   - Rechargement de la page
   - Boutons déverrouillés ✅

## Avantages de cette Approche

1. **Robuste**: Fonctionne même si session Firebase expire
2. **Automatique**: Pas besoin d'action utilisateur après connexion
3. **Double sécurité**: Deux mécanismes de détection
4. **UX Simple**: Message clair pour l'utilisateur

## Logs Console Attendus

### Cas A (Session active)
```
📊 URL params - success: true canceled: null
✅ Utilisateur Firebase connecté: [uid]
🔑 Token Firebase récupéré
✅ Mode succès activé
🔄 Début de la synchronisation...
✅ Synchronisation abonnement: {success: true, data: {plan: "trial"}}
```

### Cas B (Session expirée)
```
📊 URL params - success: true canceled: null
❌ Utilisateur non connecté
💾 Sauvegarde du statut success pour après connexion
⏱️ Redirection vers accueil dans 3 secondes...

[Puis sur la page d'accueil après connexion:]
🔄 Synchronisation en attente détectée, déclenchement...
✅ Synchronisation auto terminée: {success: true, data: {plan: "trial"}}
```

## Logs Serveur Attendus

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

## Test Complet

1. Se déconnecter si connecté
2. Se connecter
3. Cliquer sur "6m" ou "1an" ou "MAX"
4. Cliquer sur "Commencer l'essai gratuit"
5. Entrer carte: `4242 4242 4242 4242`
6. Compléter le paiement
7. Observer la page de succès (3 secondes)
8. Redirect vers `/`
9. Se reconnecter si nécessaire
10. Observer la synchronisation automatique dans les logs
11. Vérifier que tous les boutons sont déverrouillés

## Fichiers Modifiés

- [templates/subscription.html](templates/subscription.html) - Gestion session expirée
- [templates/index.html](templates/index.html) - Double mécanisme de sync
- [app.py](app.py) - Endpoint `/api/subscription/sync`
