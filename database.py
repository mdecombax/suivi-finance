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
        """Retrieve all orders for a user."""
        try:
            orders_ref = self.db.collection('users').document(user_id).collection('orders')
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
        """Add a new order for a user."""
        try:
            # Add metadata
            order_data['createdAt'] = datetime.utcnow()
            order_data['updatedAt'] = datetime.utcnow()

            # Add order to Firestore
            orders_ref = self.db.collection('users').document(user_id).collection('orders')
            doc_ref = orders_ref.add(order_data)

            logging.info(f"Order added for user {user_id}: {doc_ref[1].id}")
            return doc_ref[1].id

        except Exception as e:
            logging.error(f"Error adding order for user {user_id}: {e}")
            raise

    def delete_order(self, user_id: str, order_id: str) -> bool:
        """Delete a user's order."""
        try:
            order_ref = self.db.collection('users').document(user_id).collection('orders').document(order_id)
            order_ref.delete()
            logging.info(f"Order deleted for user {user_id}: {order_id}")
            return True
        except Exception as e:
            logging.error(f"Error deleting order for user {user_id}: {e}")
            return False

    # ========== SUBSCRIPTION MANAGEMENT ==========

    def get_user_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve current subscription for a user."""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()

            if user_doc.exists:
                user_data = user_doc.to_dict()
                subscription = user_data.get('subscription', {})

                # Default values for new users
                if not subscription:
                    subscription = {
                        'plan': 'freemium',
                        'status': 'active',
                        'stripe_customer_id': None,
                        'stripe_subscription_id': None,
                        'trial_start': None,
                        'trial_end': None,
                        'current_period_start': None,
                        'current_period_end': None,
                        'created_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow()
                    }
                    # Save defaults
                    self.update_user_subscription(user_id, subscription)

                return subscription
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
        """Check if a user has an active premium subscription."""
        try:
            subscription = self.get_user_subscription(user_id)
            if not subscription:
                return False

            plan = subscription.get('plan', 'freemium')
            status = subscription.get('status', 'inactive')

            # User is premium if:
            # 1. Has premium plan with active status
            # 2. Or is in trial period (status can be 'active' or 'trialing')
            if plan == 'premium' and status == 'active':
                return True

            if plan == 'trial' and status in ['active', 'trialing']:
                # Check trial hasn't expired
                trial_end = subscription.get('trial_end')
                if trial_end:
                    now = datetime.now(timezone.utc)
                    if trial_end > now:
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
            plan = subscription.get('plan', 'freemium') if subscription else 'freemium'

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
            'trial_remaining_days': 0
        }

    plan = subscription.get('plan', 'freemium')
    is_premium = firebase_service.is_user_premium(user_id)

    # Calculate remaining trial days
    trial_remaining_days = 0
    if plan == 'trial' and subscription.get('trial_end'):
        trial_end = subscription['trial_end']
        if isinstance(trial_end, datetime):
            now = datetime.now(timezone.utc)
            remaining = trial_end - now
            trial_remaining_days = max(0, remaining.days)

    result = {
        'plan': plan,
        'is_premium': is_premium,
        'trial_remaining_days': trial_remaining_days,
        'status': subscription.get('status', 'active'),
        'stripe_customer_id': subscription.get('stripe_customer_id'),
        'current_period_end': subscription.get('current_period_end')
    }
    return result
