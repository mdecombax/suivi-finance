"""
Payments module - Stripe integration for subscription management.
Handles checkout, webhooks, and subscription lifecycle.
"""

import os
import logging
import stripe
from typing import Dict, Any, Optional
from datetime import datetime

from database import firebase_service


class StripeService:
    """Service for managing Stripe subscriptions and payments."""

    def __init__(self):
        """Initialize Stripe service."""
        # Configure Stripe (use your real keys in production)
        secret_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_...')

        # Clean the key (remove quotes and spaces)
        secret_key = secret_key.strip().strip('"').strip("'")

        stripe.api_key = secret_key
        self.webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', 'whsec_...')

        # Stripe product IDs (create in your Stripe dashboard)
        self.premium_price_id = os.environ.get('STRIPE_PREMIUM_PRICE_ID', 'price_premium_monthly')

        logging.info("Stripe service initialized")

    def create_customer(self, user_id: str, email: str, name: str = None) -> Optional[str]:
        """Create a Stripe customer for a user."""
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

            # Update Firebase with Stripe customer ID
            subscription = firebase_service.get_user_subscription(user_id)
            if not subscription:
                # Create new subscription document if it doesn't exist
                subscription = {
                    'plan': 'freemium',
                    'stripe_customer_id': customer.id
                }
            else:
                # Update existing document
                subscription['stripe_customer_id'] = customer.id

            firebase_service.update_user_subscription(user_id, subscription)

            logging.info(f"Stripe customer created for user {user_id}: {customer.id}")
            return customer.id

        except Exception as e:
            logging.error(f"Stripe customer creation error for user {user_id}: {e}")
            return None

    def create_checkout_session(self, user_id: str, email: str,
                              success_url: str, cancel_url: str,
                              trial_days: int = 3) -> Optional[Dict[str, Any]]:
        """Create a Stripe checkout session for premium subscription."""
        try:
            # Create or retrieve Stripe customer
            subscription = firebase_service.get_user_subscription(user_id)
            customer_id = subscription.get('stripe_customer_id') if subscription else None

            if not customer_id:
                customer_id = self.create_customer(user_id, email)
                if not customer_id:
                    raise Exception("Unable to create Stripe customer")

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

            # Add free trial if specified
            if trial_days > 0:
                session_params['subscription_data']['trial_period_days'] = trial_days

            session = stripe.checkout.Session.create(**session_params)

            logging.info(f"Stripe checkout session created for user {user_id}: {session.id}")

            return {
                'session_id': session.id,
                'url': session.url
            }

        except Exception as e:
            logging.error(f"Stripe checkout session error for user {user_id}: {e}")
            return None

    def create_customer_portal_session(self, user_id: str, return_url: str) -> Optional[str]:
        """Create a customer portal session for managing subscription."""
        try:
            subscription = firebase_service.get_user_subscription(user_id)
            customer_id = subscription.get('stripe_customer_id') if subscription else None

            if not customer_id:
                raise Exception("No Stripe customer found for this user")

            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )

            logging.info(f"Stripe portal session created for user {user_id}")
            return session.url

        except Exception as e:
            logging.error(f"Stripe portal session error for user {user_id}: {e}")
            return None

    def cancel_subscription(self, user_id: str) -> bool:
        """Cancel a user's subscription."""
        try:
            subscription = firebase_service.get_user_subscription(user_id)
            stripe_subscription_id = subscription.get('stripe_subscription_id') if subscription else None

            if not stripe_subscription_id:
                raise Exception("No Stripe subscription found")

            # Cancel subscription at end of billing period
            stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True
            )

            # Update Firebase
            subscription['status'] = 'cancel_at_period_end'
            firebase_service.update_user_subscription(user_id, subscription)

            logging.info(f"Stripe subscription cancelled for user {user_id}")
            return True

        except Exception as e:
            logging.error(f"Stripe subscription cancellation error for user {user_id}: {e}")
            return False

    def handle_webhook(self, payload: bytes, sig_header: str) -> bool:
        """Process Stripe webhooks."""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret
            )

            logging.info(f"Stripe webhook received: {event['type']}")

            # Handle different event types
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
            logging.error(f"Invalid webhook signature: {e}")
            return False
        except Exception as e:
            logging.error(f"Stripe webhook error: {e}")
            return False

    def _handle_checkout_completed(self, session):
        """Handle checkout session completion."""
        try:
            user_id = session['metadata'].get('firebase_uid')
            if not user_id:
                logging.warning("No user ID in session metadata")
                return

            customer_id = session['customer']
            subscription_id = session['subscription']

            logging.info(f"Checkout completed for user {user_id}: subscription {subscription_id}")

        except Exception as e:
            logging.error(f"Error handling checkout.session.completed: {e}")

    def _handle_subscription_created(self, subscription):
        """Handle subscription creation."""
        try:
            user_id = subscription['metadata'].get('firebase_uid')
            if not user_id:
                logging.warning("No user ID in subscription metadata")
                return

            # Update Firebase
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

            logging.info(f"Subscription created for user {user_id}: {subscription['id']}")

        except Exception as e:
            logging.error(f"Error handling customer.subscription.created: {e}")

    def _handle_subscription_updated(self, subscription):
        """Handle subscription update."""
        try:
            user_id = subscription['metadata'].get('firebase_uid')
            if not user_id:
                logging.warning("No user ID in subscription metadata")
                return

            # Determine plan based on subscription state
            plan = 'freemium'  # Default

            if subscription['status'] == 'active':
                if subscription.get('trial_end') and subscription['trial_end'] > datetime.now().timestamp():
                    plan = 'trial'
                else:
                    plan = 'premium'

            # Update Firebase
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

            logging.info(f"Subscription updated for user {user_id}: plan={plan}, status={subscription['status']}")

        except Exception as e:
            logging.error(f"Error handling customer.subscription.updated: {e}")

    def _handle_subscription_deleted(self, subscription):
        """Handle subscription deletion."""
        try:
            user_id = subscription['metadata'].get('firebase_uid')
            if not user_id:
                logging.warning("No user ID in subscription metadata")
                return

            # Revert to freemium
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

            logging.info(f"Subscription deleted for user {user_id}, reverted to freemium")

        except Exception as e:
            logging.error(f"Error handling customer.subscription.deleted: {e}")

    def _handle_payment_succeeded(self, invoice):
        """Handle successful payment."""
        try:
            subscription_id = invoice.get('subscription')
            if not subscription_id:
                return

            # Retrieve subscription to get user ID
            subscription = stripe.Subscription.retrieve(subscription_id)
            user_id = subscription['metadata'].get('firebase_uid')

            if user_id:
                logging.info(f"Payment succeeded for user {user_id}: {invoice['amount_paid']} cents")

        except Exception as e:
            logging.error(f"Error handling invoice.payment_succeeded: {e}")

    def _handle_payment_failed(self, invoice):
        """Handle failed payment."""
        try:
            subscription_id = invoice.get('subscription')
            if not subscription_id:
                return

            # Retrieve subscription to get user ID
            subscription = stripe.Subscription.retrieve(subscription_id)
            user_id = subscription['metadata'].get('firebase_uid')

            if user_id:
                logging.warning(f"Payment failed for user {user_id}: {invoice['amount_due']} cents")

        except Exception as e:
            logging.error(f"Error handling invoice.payment_failed: {e}")


# Global instance
stripe_service = StripeService()
