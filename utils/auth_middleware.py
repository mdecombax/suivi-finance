"""
Middleware d'authentification Firebase pour Flask
"""
from functools import wraps
from typing import Optional, Dict, Any
from flask import request, jsonify, g
import firebase_admin
from firebase_admin import auth


def verify_firebase_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Vérifie un token Firebase et retourne les informations de l'utilisateur

    Args:
        token: Le token Firebase à vérifier

    Returns:
        Dict contenant les infos utilisateur ou None si invalide
    """
    try:
        # Supprimer le préfixe "Bearer " si présent
        if token.startswith('Bearer '):
            token = token[7:]

        # Vérifier le token avec Firebase Admin SDK
        decoded_token = auth.verify_id_token(token)

        return {
            'uid': decoded_token['uid'],
            'email': decoded_token.get('email'),
            'email_verified': decoded_token.get('email_verified', False),
            'firebase_claims': decoded_token
        }

    except firebase_admin.auth.InvalidIdTokenError:
        return None
    except firebase_admin.auth.ExpiredIdTokenError:
        return None
    except firebase_admin.auth.RevokedIdTokenError:
        return None
    except Exception as e:
        debug_log("Token verification error", {"error": str(e)})
        return None


def require_auth(f):
    """
    Décorateur pour protéger les routes avec l'authentification Firebase
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Récupérer le token de l'en-tête Authorization
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({'error': 'Token d\'authentification requis'}), 401

        # Vérifier le token
        user_info = verify_firebase_token(auth_header)

        if not user_info:
            return jsonify({'error': 'Token invalide ou expiré'}), 401

        # Stocker les infos utilisateur dans g pour les utiliser dans la route
        g.current_user = user_info
        g.user_id = user_info['uid']

        return f(*args, **kwargs)

    return decorated_function


def get_current_user_id() -> Optional[str]:
    """
    Récupère l'ID de l'utilisateur actuellement connecté

    Returns:
        L'ID utilisateur ou None si non connecté
    """
    return getattr(g, 'user_id', None)


def get_current_user() -> Optional[Dict[str, Any]]:
    """
    Récupère les informations de l'utilisateur actuellement connecté

    Returns:
        Dict avec les infos utilisateur ou None si non connecté
    """
    return getattr(g, 'current_user', None)


def is_user_authenticated() -> bool:
    """
    Vérifie si l'utilisateur est actuellement connecté via le token dans les headers

    Returns:
        True si l'utilisateur est connecté, False sinon
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False

    user_info = verify_firebase_token(auth_header)
    return user_info is not None


def require_premium(f):
    """
    Décorateur pour protéger les routes avec un abonnement premium

    À utiliser en combinaison avec @require_auth :
    @require_auth
    @require_premium
    def ma_route_premium():
        pass
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Vérifier que l'utilisateur est connecté (doit être appelé après @require_auth)
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Authentification requise'}), 401

        # Vérifier le statut premium
        from services.firebase_service import firebase_service
        is_premium = firebase_service.is_user_premium(user_id)

        if not is_premium:
            # Récupérer les infos d'abonnement pour plus de détails
            subscription = firebase_service.get_user_subscription(user_id)
            plan = subscription.get('plan', 'freemium') if subscription else 'freemium'

            return jsonify({
                'error': 'Abonnement premium requis',
                'error_type': 'premium_required',
                'current_plan': plan,
                'message': 'Cette fonctionnalité nécessite un abonnement premium.'
            }), 403

        return f(*args, **kwargs)

    return decorated_function


def check_freemium_limits(feature: str, limit_value: int = None):
    """
    Décorateur pour vérifier les limites freemium sur certaines fonctionnalités

    Args:
        feature: Nom de la fonctionnalité à vérifier
        limit_value: Limite pour les utilisateurs freemium (optionnel)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = get_current_user_id()
            if not user_id:
                return jsonify({'error': 'Authentification requise'}), 401

            # Vérifier si l'utilisateur est premium
            from services.firebase_service import firebase_service
            is_premium = firebase_service.is_user_premium(user_id)

            if is_premium:
                return f(*args, **kwargs)

            # Appliquer les limitations freemium
            # Ajouter les informations de limitation à la requête
            g.is_freemium = True
            g.feature_limits = {
                'dashboard_periods': ['1m'],  # Seulement 1 mois
                'position_analysis': 1,       # 1 seule position
                'projections_type': 'current_only',  # Capital actuel seulement
                'export_formats': ['json']    # JSON seulement
            }

            return f(*args, **kwargs)

        return decorated_function
    return decorator


def get_user_plan_info() -> Optional[Dict[str, Any]]:
    """
    Récupère les informations de plan de l'utilisateur actuel

    Returns:
        Dict avec les infos du plan ou None si non connecté
    """
    user_id = get_current_user_id()
    if not user_id:
        return None

    from services.firebase_service import firebase_service
    subscription = firebase_service.get_user_subscription(user_id)

    if not subscription:
        return {
            'plan': 'freemium',
            'is_premium': False,
            'trial_remaining_days': 0
        }

    plan = subscription.get('plan', 'freemium')
    is_premium = firebase_service.is_user_premium(user_id)

    # Calculer les jours d'essai restants
    trial_remaining_days = 0
    if plan == 'trial' and subscription.get('trial_end'):
        from datetime import datetime, timezone
        trial_end = subscription['trial_end']
        if isinstance(trial_end, datetime):
            # Utiliser datetime.now(timezone.utc) pour comparaison timezone-aware
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