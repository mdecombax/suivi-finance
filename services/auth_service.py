"""
Service d'authentification Firebase
"""
import firebase_admin
from firebase_admin import auth
from typing import Optional, Dict, Any
import json

class AuthService:
    def __init__(self):
        self.firebase_service = None
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Vérifie un token Firebase et retourne les données utilisateur"""
        try:
            # Vérifier le token
            decoded_token = auth.verify_id_token(token)
            user_id = decoded_token['uid']

            # Récupérer les informations utilisateur
            user_record = auth.get_user(user_id)

            return {
                'uid': user_id,
                'email': user_record.email,
                'display_name': user_record.display_name,
                'email_verified': user_record.email_verified,
                'photo_url': user_record.photo_url,
                'disabled': user_record.disabled
            }
        except Exception as e:
            return None

# Instance globale du service
auth_service = AuthService()
