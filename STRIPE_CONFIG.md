# Configuration Stripe - Abonnement Premium

## Produit créé dans Stripe

**Produit:** Abonnement Premium
- **ID Produit:** `prod_TSx5U8LBmPNXBI`
- **Description:** Accès complet à toutes les fonctionnalités avec période d'essai de 3 jours

**Prix:** 3,99€/mois
- **ID Prix:** `price_1SW1B6LvFYywhxGQ8uqzLnD0`
- **Devise:** EUR
- **Récurrence:** Mensuelle
- **Période d'essai:** 3 jours (configurée dans le checkout)

## Configuration .env

Ajoutez ou mettez à jour la ligne suivante dans votre fichier `.env` :

```bash
# ID du prix Premium à 3,99€/mois avec 3 jours d'essai
STRIPE_PREMIUM_PRICE_ID=price_1SW1B6LvFYywhxGQ8uqzLnD0
```

## Fonctionnement

1. L'utilisateur clique sur une fonctionnalité premium (changement de période temporelle)
2. Une modal apparaît pour proposer l'abonnement
3. L'utilisateur est redirigé vers Stripe Checkout
4. Période d'essai de 3 jours commence immédiatement
5. Après 3 jours, le paiement de 3,99€ est prélevé automatiquement
6. L'abonnement se renouvelle chaque mois

## Notes importantes

- La période d'essai est configurée via `trial_period_days: 3` dans la session de checkout
- Pendant l'essai, l'utilisateur a accès complet aux fonctionnalités premium
- Le paiement est différé de 3 jours
- L'utilisateur doit entrer ses informations de carte bancaire lors de la souscription
