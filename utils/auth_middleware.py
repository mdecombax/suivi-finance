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
        print(f"Erreur lors de la vérification du token: {e}")
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