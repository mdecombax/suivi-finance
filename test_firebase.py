#!/usr/bin/env python3
"""
Test simple pour vérifier la connexion Firebase
"""
import sys
import os
from pathlib import Path

# Ajouter le répertoire courant au path
sys.path.append(str(Path(__file__).parent))

def test_firebase_imports():
    """Test 1: Vérifier les imports Firebase"""
    print("🔍 Test 1: Vérification des imports Firebase...")
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, auth
        print("✅ Imports Firebase réussis")
        return True
    except ImportError as e:
        print(f"❌ Erreur d'import Firebase: {e}")
        return False

def test_service_account_file():
    """Test 2: Vérifier le fichier de clé de service"""
    print("\n🔍 Test 2: Vérification du fichier de clé de service...")
    service_account_path = Path(__file__).parent / "suivi-financ-firebase-adminsdk-fbsvc-6f17b62499.json"
    
    if not service_account_path.exists():
        print(f"❌ Fichier de clé de service non trouvé: {service_account_path}")
        return False
    
    print(f"✅ Fichier de clé de service trouvé: {service_account_path}")
    
    # Vérifier le contenu du fichier
    try:
        import json
        with open(service_account_path, 'r') as f:
            service_data = json.load(f)
        
        required_fields = ['type', 'project_id', 'private_key', 'client_email']
        for field in required_fields:
            if field not in service_data:
                print(f"❌ Champ manquant dans la clé de service: {field}")
                return False
        
        print(f"✅ Fichier de clé de service valide (projet: {service_data.get('project_id')})")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la lecture du fichier de clé: {e}")
        return False

def test_firebase_initialization():
    """Test 3: Vérifier l'initialisation Firebase"""
    print("\n🔍 Test 3: Vérification de l'initialisation Firebase...")
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, auth
        
        # Vérifier si Firebase est déjà initialisé
        if firebase_admin._apps:
            print("⚠️  Firebase déjà initialisé, nettoyage...")
            firebase_admin.delete_app(firebase_admin.get_app())
        
        # Initialiser Firebase
        service_account_path = Path(__file__).parent / "suivi-financ-firebase-adminsdk-fbsvc-6f17b62499.json"
        cred = credentials.Certificate(str(service_account_path))
        app = firebase_admin.initialize_app(cred)
        
        print("✅ Firebase initialisé avec succès")
        return True, app
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation Firebase: {e}")
        return False, None

def test_firestore_connection(app):
    """Test 4: Vérifier la connexion Firestore"""
    print("\n🔍 Test 4: Vérification de la connexion Firestore...")
    try:
        from firebase_admin import firestore
        db = firestore.client()
        
        # Test simple: essayer de lire une collection
        test_collection = db.collection('test')
        docs = test_collection.limit(1).stream()
        
        print("✅ Connexion Firestore réussie")
        return True
    except Exception as e:
        print(f"❌ Erreur de connexion Firestore: {e}")
        return False

def test_auth_connection(app):
    """Test 5: Vérifier la connexion Auth"""
    print("\n🔍 Test 5: Vérification de la connexion Auth...")
    try:
        from firebase_admin import auth
        
        # Test simple: lister les utilisateurs (peut être vide)
        users = auth.list_users(max_results=1)
        user_count = sum(1 for _ in users.iterate_all())
        
        print(f"✅ Connexion Auth réussie (utilisateurs trouvés: {user_count})")
        return True
    except Exception as e:
        print(f"❌ Erreur de connexion Auth: {e}")
        return False

def test_services():
    """Test 6: Vérifier nos services personnalisés"""
    print("\n🔍 Test 6: Vérification des services personnalisés...")
    try:
        from services.firebase_service import firebase_service
        from services.auth_service import auth_service
        
        print("✅ Services personnalisés importés avec succès")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de l'import des services: {e}")
        return False

def test_web_config():
    """Test 7: Vérifier la configuration web"""
    print("\n🔍 Test 7: Vérification de la configuration web...")
    try:
        config_path = Path(__file__).parent / "firebase-config.json"
        
        if not config_path.exists():
            print("❌ Fichier firebase-config.json non trouvé")
            return False
        
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        required_fields = ['apiKey', 'authDomain', 'projectId', 'storageBucket', 'messagingSenderId', 'appId']
        for field in required_fields:
            if field not in config:
                print(f"❌ Champ manquant dans la config web: {field}")
                return False
        
        print(f"✅ Configuration web valide (projet: {config.get('projectId')})")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la lecture de la config web: {e}")
        return False

def main():
    """Fonction principale de test"""
    print("🚀 Démarrage des tests Firebase...")
    print("=" * 50)
    
    tests_passed = 0
    total_tests = 7
    
    # Test 1: Imports
    if test_firebase_imports():
        tests_passed += 1
    
    # Test 2: Fichier de clé de service
    if test_service_account_file():
        tests_passed += 1
    
    # Test 3: Initialisation Firebase
    success, app = test_firebase_initialization()
    if success:
        tests_passed += 1
        
        # Test 4: Firestore
        if test_firestore_connection(app):
            tests_passed += 1
        
        # Test 5: Auth
        if test_auth_connection(app):
            tests_passed += 1
    
    # Test 6: Services personnalisés
    if test_services():
        tests_passed += 1
    
    # Test 7: Configuration web
    if test_web_config():
        tests_passed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 Résultats: {tests_passed}/{total_tests} tests réussis")
    
    if tests_passed == total_tests:
        print("🎉 Tous les tests sont passés ! Firebase est correctement configuré.")
    else:
        print("⚠️  Certains tests ont échoué. Vérifiez la configuration Firebase.")
    
    return tests_passed == total_tests

if __name__ == "__main__":
    main()
