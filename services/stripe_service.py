"""
Service Stripe pour la gestion des abonnements et paiements
"""
import os
import stripe
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from .firebase_service import firebase_service
from utils.logger import debug_log


class StripeService:
    def __init__(self):
        """Initialise le service Stripe"""
        # Configuration Stripe (utilisez vos vraies clés en production)
        secret_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_...')

        # Nettoyer la clé (enlever guillemets et espaces)
        secret_key = secret_key.strip().strip('"').strip("'")

        stripe.api_key = secret_key
        self.webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', 'whsec_...')

        # IDs des produits Stripe (à créer dans votre dashboard Stripe)
        self.premium_price_id = os.environ.get('STRIPE_PREMIUM_PRICE_ID', 'price_premium_monthly')

        debug_log("Stripe service initialized")

    def create_customer(self, user_id: str, email: str, name: str = None) -> Optional[str]:
        """Crée un client Stripe pour un utilisateur"""
        try:
            customer_data = {
                'email': email,
                'metadata': {
                    'firebase_uid': user_id
                }
            }

            if name:
                customer_data['name'] = name

            customer = stripe.Customer.create(**customer_data)

            # Mettre à jour Firebase avec l'ID client Stripe
            subscription = firebase_service.get_user_subscription(user_id)
            if not subscription:
                # Créer un nouveau document subscription si il n'existe pas
                subscription = {
                    'plan': 'freemium',
                    'stripe_customer_id': customer.id
                }
            else:
                # Mettre à jour le document existant
                subscription['stripe_customer_id'] = customer.id

            firebase_service.update_user_subscription(user_id, subscription)

            debug_log("Stripe customer created", {
                "user_id": user_id,
                "customer_id": customer.id,
                "email": email
            })

            return customer.id

        except Exception as e:
            debug_log("Stripe customer creation error", {"user_id": user_id, "error": str(e)})
            return None

    def create_checkout_session(self, user_id: str, email: str,
                              success_url: str, cancel_url: str,
                              trial_days: int = 3) -> Optional[Dict[str, Any]]:
        """Crée une session de checkout Stripe pour l'abonnement premium"""
        try:
            # Créer ou récupérer le client Stripe
            subscription = firebase_service.get_user_subscription(user_id)
            customer_id = subscription.get('stripe_customer_id') if subscription else None

            if not customer_id:
                customer_id = self.create_customer(user_id, email)
                if not customer_id:
                    raise Exception("Impossible de créer le client Stripe")

            session_params = {
                'customer': customer_id,
                'payment_method_types': ['card'],
                'line_items': [{
                    'price': self.premium_price_id,
                    'quantity': 1,
                }],
                'mode': 'subscription',
                'success_url': success_url,
                'cancel_url': cancel_url,
                'metadata': {
                    'firebase_uid': user_id
                },
                'subscription_data': {
                    'metadata': {
                        'firebase_uid': user_id
                    }
                }
            }

            # Ajouter l'essai gratuit si spécifié
            if trial_days > 0:
                session_params['subscription_data']['trial_period_days'] = trial_days

            session = stripe.checkout.Session.create(**session_params)

            debug_log("Stripe checkout session created", {
                "user_id": user_id,
                "session_id": session.id,
                "trial_days": trial_days
            })

            return {
                'session_id': session.id,
                'url': session.url
            }

        except Exception as e:
            debug_log("Stripe checkout session error", {"user_id": user_id, "error": str(e)})
            return None

    def create_customer_portal_session(self, user_id: str, return_url: str) -> Optional[str]:
        """Crée une session de portail client pour gérer l'abonnement"""
        try:
            subscription = firebase_service.get_user_subscription(user_id)
            customer_id = subscription.get('stripe_customer_id') if subscription else None

            if not customer_id:
                raise Exception("Aucun client Stripe trouvé pour cet utilisateur")

            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            debug_log("Stripe portal session created", {
                "user_id": user_id,
                "customer_id": customer_id
            })

            return session.url

        except Exception as e:
            debug_log("Stripe portal session error", {"user_id": user_id, "error": str(e)})
            return None

    def cancel_subscription(self, user_id: str) -> bool:
        """Annule l'abonnement d'un utilisateur"""
        try:
            subscription = firebase_service.get_user_subscription(user_id)
            stripe_subscription_id = subscription.get('stripe_subscription_id') if subscription else None

            if not stripe_subscription_id:
                raise Exception("Aucun abonnement Stripe trouvé")

            # Annuler l'abonnement à la fin de la période de facturation
            stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True
            )

            # Mettre à jour Firebase
            subscription['status'] = 'cancel_at_period_end'
            firebase_service.update_user_subscription(user_id, subscription)

            debug_log("Stripe subscription cancelled", {
                "user_id": user_id,
                "subscription_id": stripe_subscription_id
            })

            return True

        except Exception as e:
            debug_log("Stripe subscription cancellation error", {"user_id": user_id, "error": str(e)})
            return False

    def handle_webhook(self, payload: bytes, sig_header: str) -> bool:
        """Traite les webhooks Stripe"""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )

            debug_log("Stripe webhook received", {"event_type": event['type']})

            # Gérer les différents types d'événements
            if event['type'] == 'checkout.session.completed':
                self._handle_checkout_completed(event['data']['object'])

            elif event['type'] == 'customer.subscription.created':
                self._handle_subscription_created(event['data']['object'])

            elif event['type'] == 'customer.subscription.updated':
                self._handle_subscription_updated(event['data']['object'])

            elif event['type'] == 'customer.subscription.deleted':
                self._handle_subscription_deleted(event['data']['object'])

            elif event['type'] == 'invoice.payment_succeeded':
                self._handle_payment_succeeded(event['data']['object'])

            elif event['type'] == 'invoice.payment_failed':
                self._handle_payment_failed(event['data']['object'])

            return True

        except ValueError as e:
            debug_log("Invalid webhook signature", {"error": str(e)})
            return False
        except Exception as e:
            debug_log("Stripe webhook error", {"error": str(e)})
            return False

    def _handle_checkout_completed(self, session):
        """Traite la completion d'une session de checkout"""
        try:
            user_id = session['metadata'].get('firebase_uid')
            if not user_id:
                debug_log("No user ID in session metadata")
                return

            customer_id = session['customer']
            subscription_id = session['subscription']

            debug_log("Checkout session completed", {
                "user_id": user_id,
                "customer_id": customer_id,
                "subscription_id": subscription_id
            })

        except Exception as e:
            debug_log("Error handling checkout.session.completed", {"error": str(e)})

    def _handle_subscription_created(self, subscription):
        """Traite la création d'un abonnement"""
        try:
            user_id = subscription['metadata'].get('firebase_uid')
            if not user_id:
                debug_log("No user ID in subscription metadata")
                return

            # Mettre à jour Firebase
            subscription_data = {
                'plan': 'trial' if subscription.get('trial_end') else 'premium',
                'status': subscription['status'],
                'stripe_customer_id': subscription['customer'],
                'stripe_subscription_id': subscription['id'],
                'current_period_start': datetime.fromtimestamp(subscription['current_period_start']),
                'current_period_end': datetime.fromtimestamp(subscription['current_period_end'])
            }

            if subscription.get('trial_end'):
                subscription_data['trial_end'] = datetime.fromtimestamp(subscription['trial_end'])

            firebase_service.update_user_subscription(user_id, subscription_data)

            debug_log("Subscription created", {
                "user_id": user_id,
                "subscription_id": subscription['id'],
                "status": subscription['status']
            })

        except Exception as e:
            debug_log("Error handling customer.subscription.created", {"error": str(e)})

    def _handle_subscription_updated(self, subscription):
        """Traite la mise à jour d'un abonnement"""
        try:
            user_id = subscription['metadata'].get('firebase_uid')
            if not user_id:
                debug_log("No user ID in subscription metadata")
                return

            # Déterminer le plan en fonction de l'état de l'abonnement
            plan = 'freemium'  # Par défaut

            if subscription['status'] == 'active':
                if subscription.get('trial_end') and subscription['trial_end'] > datetime.now().timestamp():
                    plan = 'trial'
                else:
                    plan = 'premium'

            # Mettre à jour Firebase
            subscription_data = {
                'plan': plan,
                'status': subscription['status'],
                'stripe_customer_id': subscription['customer'],
                'stripe_subscription_id': subscription['id'],
                'current_period_start': datetime.fromtimestamp(subscription['current_period_start']),
                'current_period_end': datetime.fromtimestamp(subscription['current_period_end'])
            }

            if subscription.get('trial_end'):
                subscription_data['trial_end'] = datetime.fromtimestamp(subscription['trial_end'])

            firebase_service.update_user_subscription(user_id, subscription_data)

            debug_log("Subscription updated", {
                "user_id": user_id,
                "subscription_id": subscription['id'],
                "status": subscription['status'],
                "plan": plan
            })

        except Exception as e:
            debug_log("Error handling customer.subscription.updated", {"error": str(e)})

    def _handle_subscription_deleted(self, subscription):
        """Traite la suppression d'un abonnement"""
        try:
            user_id = subscription['metadata'].get('firebase_uid')
            if not user_id:
                debug_log("No user ID in subscription metadata")
                return

            # Repasser en freemium
            subscription_data = {
                'plan': 'freemium',
                'status': 'active',
                'stripe_customer_id': subscription['customer'],
                'stripe_subscription_id': None,
                'trial_start': None,
                'trial_end': None,
                'current_period_start': None,
                'current_period_end': None
            }

            firebase_service.update_user_subscription(user_id, subscription_data)

            debug_log("Subscription deleted", {
                "user_id": user_id,
                "subscription_id": subscription['id']
            })

        except Exception as e:
            debug_log("Error handling customer.subscription.deleted", {"error": str(e)})

    def _handle_payment_succeeded(self, invoice):
        """Traite le succès d'un paiement"""
        try:
            subscription_id = invoice.get('subscription')
            if not subscription_id:
                return

            # Récupérer l'abonnement pour obtenir l'ID utilisateur
            subscription = stripe.Subscription.retrieve(subscription_id)
            user_id = subscription['metadata'].get('firebase_uid')

            if user_id:
                debug_log("Payment succeeded", {
                    "user_id": user_id,
                    "invoice_id": invoice['id'],
                    "amount": invoice['amount_paid']
                })

        except Exception as e:
            debug_log("Error handling invoice.payment_succeeded", {"error": str(e)})

    def _handle_payment_failed(self, invoice):
        """Traite l'échec d'un paiement"""
        try:
            subscription_id = invoice.get('subscription')
            if not subscription_id:
                return

            # Récupérer l'abonnement pour obtenir l'ID utilisateur
            subscription = stripe.Subscription.retrieve(subscription_id)
            user_id = subscription['metadata'].get('firebase_uid')

            if user_id:
                debug_log("Payment failed", {
                    "user_id": user_id,
                    "invoice_id": invoice['id'],
                    "amount": invoice['amount_due']
                })

        except Exception as e:
            debug_log("Error handling invoice.payment_failed", {"error": str(e)})


# Instance globale du service
stripe_service = StripeService()