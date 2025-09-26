"""
Script de migration des ordres depuis orders.json vers Firebase
pour un utilisateur spécifique
"""
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import uuid

# Configuration Firebase
try:
    # Tenter d'obtenir l'app existante
    app = firebase_admin.get_app()
except ValueError:
    # Si l'app n'existe pas, l'initialiser
    cred = credentials.Certificate('suivi-financ-firebase-adminsdk-fbsvc-6f17b62499.json')
    app = firebase_admin.initialize_app(cred)

db = firestore.client()

def load_orders_from_json():
    """Charge les ordres depuis le fichier orders.json"""
    try:
        with open('orders.json', 'r', encoding='utf-8') as f:
            orders = json.load(f)
        print(f"✅ {len(orders)} ordres chargés depuis orders.json")
        return orders
    except Exception as e:
        print(f"❌ Erreur lors du chargement du fichier orders.json: {e}")
        return []

def delete_user_orders(user_id):
    """Supprime tous les ordres existants d'un utilisateur dans Firebase"""
    try:
        # Référence de la collection orders de l'utilisateur
        user_orders_ref = db.collection('users').document(user_id).collection('orders')

        # Récupérer tous les documents
        orders = user_orders_ref.stream()

        deleted_count = 0
        for order in orders:
            order.reference.delete()
            deleted_count += 1

        print(f"✅ {deleted_count} ordres supprimés pour l'utilisateur {user_id}")
        return deleted_count
    except Exception as e:
        print(f"❌ Erreur lors de la suppression des ordres: {e}")
        return 0

def add_orders_to_firebase(user_id, orders):
    """Ajoute les ordres dans Firebase pour un utilisateur spécifique"""
    try:
        # Référence de la collection orders de l'utilisateur
        user_orders_ref = db.collection('users').document(user_id).collection('orders')

        added_count = 0
        for order in orders:
            # Générer un ID unique pour chaque ordre dans Firebase
            order_id = str(uuid.uuid4())

            # Préparer les données de l'ordre pour Firebase
            firebase_order = {
                'id': order_id,
                'date': order['date'],
                'isin': order['isin'],
                'quantity': order['quantity'],
                'unitPrice': order['unitPriceEUR'],
                'totalPriceEUR': order['totalPriceEUR'],
                'createdAt': datetime.now(),
                'updatedAt': datetime.now()
            }

            # Ajouter l'ordre dans Firebase
            user_orders_ref.document(order_id).set(firebase_order)
            added_count += 1

        print(f"✅ {added_count} ordres ajoutés pour l'utilisateur {user_id}")
        return added_count
    except Exception as e:
        print(f"❌ Erreur lors de l'ajout des ordres: {e}")
        return 0

def migrate_orders_for_user(user_id):
    """Migration complète des ordres pour un utilisateur"""
    print(f"🚀 Démarrage de la migration pour l'utilisateur: {user_id}")

    # 1. Charger les ordres depuis orders.json
    orders = load_orders_from_json()
    if not orders:
        print("❌ Aucun ordre à migrer")
        return False

    # 2. Supprimer les ordres existants
    print(f"🗑️ Suppression des ordres existants...")
    deleted_count = delete_user_orders(user_id)

    # 3. Ajouter les nouveaux ordres
    print(f"📝 Ajout des nouveaux ordres...")
    added_count = add_orders_to_firebase(user_id, orders)

    # 4. Résumé
    print(f"\n📊 RÉSUMÉ DE LA MIGRATION:")
    print(f"   - Ordres supprimés: {deleted_count}")
    print(f"   - Ordres ajoutés: {added_count}")
    print(f"   - Statut: {'✅ SUCCÈS' if added_count > 0 else '❌ ÉCHEC'}")

    return added_count > 0

if __name__ == "__main__":
    # ID de l'utilisateur à migrer
    USER_ID = "Noq6DpqLnbXE1ROfboyfDIbnVVo2"

    print("=" * 60)
    print("  MIGRATION DES ORDRES VERS FIREBASE")
    print("=" * 60)

    try:
        success = migrate_orders_for_user(USER_ID)

        if success:
            print(f"\n🎉 Migration terminée avec succès pour l'utilisateur {USER_ID}")
        else:
            print(f"\n💥 Échec de la migration pour l'utilisateur {USER_ID}")

    except Exception as e:
        print(f"\n💥 Erreur fatale: {e}")

    print("=" * 60)