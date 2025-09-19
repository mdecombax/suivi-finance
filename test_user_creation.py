#!/usr/bin/env python3
"""
Script pour créer un utilisateur de test Firebase
"""
import sys
from pathlib import Path

# Ajouter le répertoire courant au path
sys.path.append(str(Path(__file__).parent))

def create_test_user():
    """Créer un utilisateur de test"""
    try:
        # Initialiser Firebase d'abord
        import firebase_admin
        from firebase_admin import credentials
        from pathlib import Path
        
        if not firebase_admin._apps:
            service_account_path = Path(__file__).parent / "suivi-financ-firebase-adminsdk-fbsvc-6f17b62499.json"
            cred = credentials.Certificate(str(service_account_path))
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialisé pour le test")
        
        from services.auth_service import auth_service
        
        email = "test@example.com"
        password = "password123"
        display_name = "Test User"
        
        print(f"🔍 Tentative de création d'utilisateur: {email}")
        
        # Vérifier si l'utilisateur existe déjà
        existing_user = auth_service.get_user_by_email(email)
        if existing_user:
            print(f"⚠️  Utilisateur {email} existe déjà")
            return existing_user
        
        # Créer l'utilisateur
        user = auth_service.create_user(email, password, display_name)
        if user:
            print(f"✅ Utilisateur créé avec succès: {user['uid']}")
            return user
        else:
            print("❌ Échec de la création de l'utilisateur")
            return None
            
    except Exception as e:
        print(f"❌ Erreur lors de la création de l'utilisateur: {e}")
        return None

def test_user_auth():
    """Tester l'authentification de l'utilisateur"""
    try:
        from services.auth_service import auth_service
        
        email = "test@example.com"
        password = "password123"
        
        print(f"🔍 Test d'authentification pour: {email}")
        
        # Note: On ne peut pas tester la connexion côté serveur
        # car Firebase Auth côté serveur ne supporte pas la connexion avec email/password
        # C'est uniquement possible côté client
        
        print("ℹ️  L'authentification email/password doit être testée côté client")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test d'authentification: {e}")
        return False

def main():
    """Fonction principale"""
    print("🚀 Test de création d'utilisateur Firebase")
    print("=" * 50)
    
    # Créer l'utilisateur de test
    user = create_test_user()
    
    if user:
        print(f"\n📊 Utilisateur de test créé:")
        print(f"   UID: {user['uid']}")
        print(f"   Email: {user['email']}")
        print(f"   Nom: {user['display_name']}")
        
        # Tester l'authentification
        test_user_auth()
        
        print(f"\n✅ Vous pouvez maintenant tester la connexion avec:")
        print(f"   Email: test@example.com")
        print(f"   Mot de passe: password123")
    else:
        print("❌ Impossible de créer l'utilisateur de test")

if __name__ == "__main__":
    main()
