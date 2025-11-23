"""
Service Firebase pour la gestion des données Firestore
"""
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore
from pathlib import Path

class FirebaseService:
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Initialise la connexion Firebase"""
        try:
            # Vérifier si Firebase est déjà initialisé
            if firebase_admin._apps:
                print("✅ Firebase déjà initialisé, réutilisation de l'instance existante")
                self.db = firestore.client()
                return
            
            # Chemin vers le fichier de clé de service
            service_account_path = Path(__file__).parent.parent / "suivi-financ-firebase-adminsdk-fbsvc-6f17b62499.json"
            
            if not service_account_path.exists():
                raise FileNotFoundError(f"Fichier de clé de service non trouvé: {service_account_path}")
            
            # Initialiser Firebase Admin SDK
            cred = credentials.Certificate(str(service_account_path))
            firebase_admin.initialize_app(cred)
            
            # Obtenir la référence Firestore
            self.db = firestore.client()
            print("✅ Firebase initialisé avec succès")
            
        except Exception as e:
            print(f"❌ Erreur lors de l'initialisation Firebase: {e}")
            raise
    
    def get_user_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """Récupère tous les ordres d'un utilisateur"""
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
            print(f"❌ Erreur lors de la récupération des ordres: {e}")
            return []
    
    def add_order(self, user_id: str, order_data: Dict[str, Any]) -> str:
        """Ajoute un nouvel ordre pour un utilisateur"""
        try:
            # Ajouter des métadonnées
            order_data['createdAt'] = datetime.utcnow()
            order_data['updatedAt'] = datetime.utcnow()
            
            # Ajouter l'ordre à Firestore
            orders_ref = self.db.collection('users').document(user_id).collection('orders')
            doc_ref = orders_ref.add(order_data)
            
            print(f"✅ Ordre ajouté avec l'ID: {doc_ref[1].id}")
            return doc_ref[1].id
            
        except Exception as e:
            print(f"❌ Erreur lors de l'ajout de l'ordre: {e}")
            raise
    
    def delete_order(self, user_id: str, order_id: str) -> bool:
        """Supprime un ordre d'un utilisateur"""
        try:
            order_ref = self.db.collection('users').document(user_id).collection('orders').document(order_id)
            order_ref.delete()
            print(f"✅ Ordre {order_id} supprimé")
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la suppression de l'ordre: {e}")
            return False
    
    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Récupère le profil d'un utilisateur"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                return user_doc.to_dict()
            return None
        except Exception as e:
            print(f"❌ Erreur lors de la récupération du profil: {e}")
            return None
    
    def create_user_profile(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """Crée le profil d'un utilisateur"""
        try:
            user_data['createdAt'] = datetime.utcnow()
            user_data['lastLogin'] = datetime.utcnow()
            
            user_ref = self.db.collection('users').document(user_id)
            user_ref.set(user_data)
            
            print(f"✅ Profil utilisateur créé: {user_id}")
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la création du profil: {e}")
            return False
    
    def update_user_profile(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        """Met à jour le profil d'un utilisateur"""
        try:
            user_data['updatedAt'] = datetime.utcnow()
            
            user_ref = self.db.collection('users').document(user_id)
            user_ref.update(user_data)
            
            print(f"✅ Profil utilisateur mis à jour: {user_id}")
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du profil: {e}")
            return False
    
    def update_last_login(self, user_id: str) -> bool:
        """Met à jour la dernière connexion d'un utilisateur"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_ref.update({'lastLogin': datetime.utcnow()})
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour de la dernière connexion: {e}")
            return False

    # ========== GESTION DES ABONNEMENTS ==========

    def get_user_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Récupère l'abonnement actuel d'un utilisateur"""
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_doc = user_ref.get()

            if user_doc.exists:
                user_data = user_doc.to_dict()
                subscription = user_data.get('subscription', {})

                # Valeurs par défaut pour les nouveaux utilisateurs
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
                    # Sauvegarder les valeurs par défaut
                    self.update_user_subscription(user_id, subscription)

                return subscription
            return None
        except Exception as e:
            print(f"❌ Erreur lors de la récupération de l'abonnement: {e}")
            return None

    def update_user_subscription(self, user_id: str, subscription_data: Dict[str, Any]) -> bool:
        """Met à jour l'abonnement d'un utilisateur"""
        try:
            subscription_data['updated_at'] = datetime.utcnow()

            user_ref = self.db.collection('users').document(user_id)
            # Utiliser set avec merge=True pour créer le document s'il n'existe pas
            user_ref.set({'subscription': subscription_data}, merge=True)

            print(f"✅ Abonnement mis à jour pour l'utilisateur {user_id}")
            return True
        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour de l'abonnement: {e}")
            return False

    def is_user_premium(self, user_id: str) -> bool:
        """Vérifie si un utilisateur a un abonnement premium actif"""
        try:
            subscription = self.get_user_subscription(user_id)
            if not subscription:
                return False

            # Vérifier le plan
            plan = subscription.get('plan', 'freemium')
            status = subscription.get('status', 'inactive')

            # L'utilisateur est premium si:
            # 1. Il a un plan premium avec statut actif
            # 2. Ou il est en période d'essai gratuit (status peut être 'active' ou 'trialing')
            if plan == 'premium' and status == 'active':
                return True

            if plan == 'trial' and status in ['active', 'trialing']:
                # Vérifier que l'essai n'est pas expiré
                trial_end = subscription.get('trial_end')
                if trial_end:
                    # Utiliser datetime.now(timezone.utc) pour comparaison avec timestamp Firestore
                    now = datetime.now(timezone.utc)
                    if trial_end > now:
                        return True

            return False
        except Exception as e:
            print(f"❌ Erreur lors de la vérification du statut premium: {e}")
            return False

    def start_user_trial(self, user_id: str) -> bool:
        """Démarre un essai gratuit de 3 jours pour un utilisateur"""
        try:
            from datetime import timedelta

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
            print(f"❌ Erreur lors du démarrage de l'essai: {e}")
            return False

# Instance globale du service
firebase_service = FirebaseService()
