"""
Database module - Firebase/Firestore operations and authentication middleware.
Consolidates all database and auth functionality in one place.
"""

import os
import logging
from functools import wraps
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore, auth
from flask import request, jsonify, g


# ============================================================================
# FIREBASE INITIALIZATION
# ============================================================================

class FirebaseService:
    """Service for managing Firebase/Firestore operations."""

    def __init__(self):
        self.db = None
        self._initialize_firebase()

    def _initialize_firebase(self):
        """Initialize Firebase connection."""
        try:
            # Check if Firebase is already initialized
            if firebase_admin._apps:
                self.db = firestore.client()
                return

            # Path to service account key file
            service_account_path = Path(__file__).parent / "suivi-financ-firebase-adminsdk-fbsvc-6f17b62499.json"

            if not service_account_path.exists():
                raise FileNotFoundError(f"Service account key not found: {service_account_path}")

            # Initialize Firebase Admin SDK
            cred = credentials.Certificate(str(service_account_path))
            firebase_admin.initialize_app(cred)

            # Get Firestore reference
            self.db = firestore.client()
            logging.info("Firebase initialized successfully")

        except Exception as e:
            logging.error(f"Firebase initialization error: {e}")
            raise

    # ========== ORDER MANAGEMENT ==========

    def get_user_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve all orders for a user from customers/{user_id}/orders."""
        try:
            orders_ref = self.db.collection('customers').document(user_id).collection('orders')
            orders = orders_ref.order_by('date', direction=firestore.Query.ASCENDING).stream()

            orders_list = []
            for order in orders:
                order_data = order.to_dict()
                order_data['id'] = order.id
                orders_list.append(order_data)

            return orders_list
        except Exception as e:
            logging.error(f"Error fetching orders for user {user_id}: {e}")
            return []

    def add_order(self, user_id: str, order_data: Dict[str, Any]) -> str:
        """Add a new order for a user to customers/{user_id}/orders."""
        try:
            # Add metadata
            order_data['createdAt'] = datetime.utcnow()
            order_data['updatedAt'] = datetime.utcnow()

            # Add order to Firestore
            orders_ref = self.db.collection('customers').document(user_id).collection('orders')
            doc_ref = orders_ref.add(order_data)

            logging.info(f"Order added for user {user_id}: {doc_ref[1].id}")
            return doc_ref[1].id

        except Exception as e:
            logging.error(f"Error adding order for user {user_id}: {e}")
            raise

    def delete_order(self, user_id: str, order_id: str) -> bool:
        """Delete a user's order from customers/{user_id}/orders."""
        try:
            order_ref = self.db.collection('customers').document(user_id).collection('orders').document(order_id)
            order_ref.delete()
            logging.info(f"Order deleted for user {user_id}: {order_id}")
            return True
        except Exception as e:
            logging.error(f"Error deleting order for user {user_id}: {e}")
            return False

    # ========== SUBSCRIPTION MANAGEMENT ==========

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        """Get Stripe customer ID for a user.

        Checks both:
        1. customers/{uid}.stripeId (Firebase Extension format)
        2. users/{uid}.subscription.stripe_customer_id (legacy format)

        Returns the first one found, prioritizing the Extension format.
        """
        try:
            # First, check the 'customers' collection (Firebase Stripe Extension format)
            customers_ref = self.db.collection('customers').document(user_id)
            customers_doc = customers_ref.get()

            if customers_doc.exists:
                customer_data = customers_doc.to_dict()
                stripe_id = customer_data.get('stripeId')
                if stripe_id:
                    logging.info(f"Found stripeId in customers collection for user {user_id}: {stripe_id}")
                    return stripe_id

            # Fallback: check users/{uid}.subscription.stripe_customer_id
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()

            if user_doc.exists:
                user_data = user_doc.to_dict()
                subscription = user_data.get('subscription', {})
                stripe_customer_id = subscription.get('stripe_customer_id')
                if stripe_customer_id:
                    logging.info(f"Found stripe_customer_id in users collection for user {user_id}: {stripe_customer_id}")
                    return stripe_customer_id

            return None

        except Exception as e:
            logging.error(f"Error getting Stripe customer ID for user {user_id}: {e}")
            return None

    def update_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> bool:
        """Update Stripe customer ID in both collections for consistency."""
        try:
            # Update customers collection (for Firebase Extension)
            customers_ref = self.db.collection('customers').document(user_id)
            customers_ref.set({'stripeId': stripe_customer_id}, merge=True)

            # Also update users collection (for legacy code)
            user_ref = self.db.collection('users').document(user_id)
            user_ref.set({
                'subscription': {
                    'stripe_customer_id': stripe_customer_id
                }
            }, merge=True)

            logging.info(f"Updated Stripe customer ID for user {user_id}: {stripe_customer_id}")
            return True

        except Exception as e:
            logging.error(f"Error updating Stripe customer ID for user {user_id}: {e}")
            return False

    def get_user_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve current subscription for a user from Stripe Extension collection.

        Reads from customers/{uid}/subscriptions/ (Firebase Stripe Extension format).
        Returns the most recent active/trialing subscription, or None if no subscription.
        """
        try:
            # Read from customers/{uid}/subscriptions/ collection
            subscriptions_ref = self.db.collection('customers').document(user_id).collection('subscriptions')

            # Get all subscriptions, ordered by created date (most recent first)
            subscriptions = subscriptions_ref.order_by('created', direction=firestore.Query.DESCENDING).limit(5).stream()

            # Find the first active or trialing subscription
            for sub_doc in subscriptions:
                sub_data = sub_doc.to_dict()
                status = sub_data.get('status')

                # Return active or trialing subscription
                if status in ['active', 'trialing']:
                    sub_data['id'] = sub_doc.id
                    return sub_data

                # Also return if cancel_at_period_end but still in period
                if status == 'active' or (sub_data.get('cancel_at_period_end') and status != 'canceled'):
                    sub_data['id'] = sub_doc.id
                    return sub_data

            # No active subscription found - return None (freemium user)
            return None

        except Exception as e:
            logging.error(f"Error fetching subscription for user {user_id}: {e}")
            return None

    def update_user_subscription(self, user_id: str, subscription_data: Dict[str, Any]) -> bool:
        """Update user's subscription."""
        try:
            subscription_data['updated_at'] = datetime.utcnow()

            user_ref = self.db.collection('users').document(user_id)
            # Use set with merge=True to create document if it doesn't exist
            user_ref.set({'subscription': subscription_data}, merge=True)

            logging.info(f"Subscription updated for user {user_id}")
            return True
        except Exception as e:
            logging.error(f"Error updating subscription for user {user_id}: {e}")
            return False

    def is_user_premium(self, user_id: str) -> bool:
        """Check if a user has an active premium subscription.

        Uses Stripe Extension format from customers/{uid}/subscriptions/.
        User is premium if they have an active or trialing subscription.

        Important: If user is trialing and has requested cancellation (cancel_at is set),
        they lose access immediately (no payment made = no access).
        """
        try:
            subscription = self.get_user_subscription(user_id)
            if not subscription:
                return False

            status = subscription.get('status')

            # Check if subscription is canceled
            if status == 'canceled':
                return False

            # User is premium if status is 'active'
            if status == 'active':
                # If cancel_at_period_end, user keeps access until period ends
                return True

            if status == 'trialing':
                # IMPORTANT: If trialing user requested cancellation, revoke access immediately
                # (they haven't paid, so no access after cancellation request)
                cancel_at = subscription.get('cancel_at')
                canceled_at = subscription.get('canceled_at')

                if cancel_at is not None or canceled_at is not None:
                    # User requested cancellation during trial - no access
                    logging.info(f"User {user_id} is trialing but has requested cancellation - access revoked")
                    return False

                # Check trial hasn't expired
                trial_end = subscription.get('trial_end')
                if trial_end:
                    # Handle both timestamp and datetime objects
                    if hasattr(trial_end, 'timestamp'):
                        trial_end_ts = trial_end.timestamp()
                    else:
                        trial_end_ts = trial_end

                    now_ts = datetime.now(timezone.utc).timestamp()
                    if trial_end_ts > now_ts:
                        return True

            return False
        except Exception as e:
            logging.error(f"Error checking premium status for user {user_id}: {e}")
            return False

    def start_user_trial(self, user_id: str) -> bool:
        """Start a 3-day free trial for a user."""
        try:
            now = datetime.utcnow()
            trial_end = now + timedelta(days=3)

            subscription_data = {
                'plan': 'trial',
                'status': 'active',
                'trial_start': now,
                'trial_end': trial_end,
                'stripe_customer_id': None,
                'stripe_subscription_id': None,
                'current_period_start': now,
                'current_period_end': trial_end
            }

            return self.update_user_subscription(user_id, subscription_data)
        except Exception as e:
            logging.error(f"Error starting trial for user {user_id}: {e}")
            return False


# Global instance
firebase_service = FirebaseService()


# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================

def verify_firebase_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Firebase token and return user information.

    Args:
        token: The Firebase token to verify

    Returns:
        Dict containing user info or None if invalid
    """
    try:
        # Remove "Bearer " prefix if present
        if token.startswith('Bearer '):
            token = token[7:]

        # Verify token with Firebase Admin SDK
        decoded_token = auth.verify_id_token(token)

        return {
            'uid': decoded_token['uid'],
            'email': decoded_token.get('email'),
            'email_verified': decoded_token.get('email_verified', False),
            'firebase_claims': decoded_token
        }

    except firebase_admin.auth.InvalidIdTokenError:
        logging.warning("Invalid Firebase token")
        return None
    except firebase_admin.auth.ExpiredIdTokenError:
        logging.warning("Expired Firebase token")
        return None
    except firebase_admin.auth.RevokedIdTokenError:
        logging.warning("Revoked Firebase token")
        return None
    except Exception as e:
        logging.error(f"Token verification error: {e}")
        return None


def require_auth(f):
    """
    Decorator to protect routes with Firebase authentication.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'Authentication token required'}), 401

        # Verify token
        user_info = verify_firebase_token(auth_header)

        if not user_info:
            return jsonify({'error': 'Invalid or expired token'}), 401

        # Store user info in g for use in the route
        g.current_user = user_info
        g.user_id = user_info['uid']

        return f(*args, **kwargs)

    return decorated_function


def get_current_user_id() -> Optional[str]:
    """
    Get the ID of the currently authenticated user.

    Returns:
        User ID or None if not authenticated
    """
    return getattr(g, 'user_id', None)


def get_current_user() -> Optional[Dict[str, Any]]:
    """
    Get information about the currently authenticated user.

    Returns:
        Dict with user info or None if not authenticated
    """
    return getattr(g, 'current_user', None)


def is_user_authenticated() -> bool:
    """
    Check if the user is currently authenticated via token in headers.

    Returns:
        True if user is authenticated, False otherwise
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False

    user_info = verify_firebase_token(auth_header)
    return user_info is not None


def require_premium(f):
    """
    Decorator to protect routes requiring premium subscription.

    Use in combination with @require_auth:
    @require_auth
    @require_premium
    def my_premium_route():
        pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check user is authenticated (should be called after @require_auth)
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401

        # Check premium status
        is_premium = firebase_service.is_user_premium(user_id)

        if not is_premium:
            # Get subscription info for more details
            subscription = firebase_service.get_user_subscription(user_id)

            # Determine plan from subscription status
            if subscription:
                status = subscription.get('status')
                if status == 'trialing':
                    plan = 'trial'
                elif status == 'active':
                    plan = 'premium'
                else:
                    plan = 'freemium'
            else:
                plan = 'freemium'

            return jsonify({
                'error': 'Premium subscription required',
                'error_type': 'premium_required',
                'current_plan': plan,
                'message': 'This feature requires a premium subscription.'
            }), 403

        return f(*args, **kwargs)

    return decorated_function


def check_freemium_limits(feature: str, limit_value: int = None):
    """
    Decorator to check freemium limits on certain features.

    Args:
        feature: Name of the feature to check
        limit_value: Limit for freemium users (optional)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = get_current_user_id()
            if not user_id:
                return jsonify({'error': 'Authentication required'}), 401

            # Check if user is premium
            is_premium = firebase_service.is_user_premium(user_id)

            if is_premium:
                return f(*args, **kwargs)

            # Apply freemium limitations
            # Add limitation information to request
            g.is_freemium = True
            g.feature_limits = {
                'dashboard_periods': ['1m'],  # Only 1 month
                'position_analysis': 1,       # 1 position only
                'projections_type': 'current_only',  # Current capital only
                'export_formats': ['json']    # JSON only
            }

            return f(*args, **kwargs)

        return decorated_function
    return decorator


def get_user_plan_info() -> Optional[Dict[str, Any]]:
    """
    Get plan information for the current user.

    Uses Stripe Extension format from customers/{uid}/subscriptions/.

    Returns:
        Dict with plan info or None if not authenticated
    """
    user_id = get_current_user_id()
    if not user_id:
        return None

    subscription = firebase_service.get_user_subscription(user_id)

    if not subscription:
        return {
            'plan': 'freemium',
            'is_premium': False,
            'trial_remaining_days': 0,
            'status': None,
            'current_period_end': None,
            'cancel_at_period_end': False
        }

    status = subscription.get('status')
    is_premium = firebase_service.is_user_premium(user_id)

    # Determine plan type based on is_premium flag (not just status)
    # This ensures that cancelled trials show as freemium
    if not is_premium:
        plan = 'freemium'
    elif status == 'trialing':
        plan = 'trial'
    elif status == 'active':
        plan = 'premium'
    else:
        plan = 'freemium'

    # Calculate remaining trial days
    trial_remaining_days = 0
    trial_end = subscription.get('trial_end')
    if trial_end and status == 'trialing':
        # Handle both timestamp and datetime objects
        if hasattr(trial_end, 'timestamp'):
            trial_end_dt = trial_end
        else:
            # Convert timestamp to datetime
            trial_end_dt = datetime.fromtimestamp(trial_end, tz=timezone.utc)

        now = datetime.now(timezone.utc)
        remaining = trial_end_dt - now
        trial_remaining_days = max(0, remaining.days)

    # Get current_period_end for display
    current_period_end = subscription.get('current_period_end')
    if current_period_end and hasattr(current_period_end, 'isoformat'):
        current_period_end_str = current_period_end.isoformat()
    elif current_period_end:
        current_period_end_str = datetime.fromtimestamp(current_period_end, tz=timezone.utc).isoformat()
    else:
        current_period_end_str = None

    result = {
        'plan': plan,
        'is_premium': is_premium,
        'trial_remaining_days': trial_remaining_days,
        'status': status,
        'current_period_end': current_period_end_str,
        'cancel_at_period_end': subscription.get('cancel_at_period_end', False),
        'subscription_id': subscription.get('id')
    }
    return result
