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
            print(f"❌ Erreur lors de la vérification du token: {e}")
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Récupère un utilisateur par son email"""
        try:
            user_record = auth.get_user_by_email(email)
            return {
                'uid': user_record.uid,
                'email': user_record.email,
                'display_name': user_record.display_name,
                'email_verified': user_record.email_verified,
                'photo_url': user_record.photo_url,
                'disabled': user_record.disabled
            }
        except Exception as e:
            print(f"❌ Erreur lors de la récupération de l'utilisateur: {e}")
            return None
    
    def create_user(self, email: str, password: str, display_name: str = None) -> Optional[Dict[str, Any]]:
        """Crée un nouvel utilisateur"""
        try:
            user_record = auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )
            
            return {
                'uid': user_record.uid,
                'email': user_record.email,
                'display_name': user_record.display_name,
                'email_verified': user_record.email_verified,
                'photo_url': user_record.photo_url,
                'disabled': user_record.disabled
            }
        except Exception as e:
            print(f"❌ Erreur lors de la création de l'utilisateur: {e}")
            return None
    
    def update_user(self, uid: str, **kwargs) -> bool:
        """Met à jour un utilisateur"""
        try:
            auth.update_user(uid, **kwargs)
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour de l'utilisateur: {e}")
            return False
    
    def delete_user(self, uid: str) -> bool:
        """Supprime un utilisateur"""
        try:
            auth.delete_user(uid)
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la suppression de l'utilisateur: {e}")
            return False

# Instance globale du service
auth_service = AuthService()
