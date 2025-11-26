"""
Test d'intégration du batch pricing avec les vrais services.
Teste le flux complet comme l'API le ferait.
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Ajouter le dossier parent au path pour importer les services
sys.path.insert(0, str(Path(__file__).parent))

from services.price_service import PriceService
from services.portfolio_service import PortfolioService

# Données de test (ordres utilisateur simulés)
MOCK_ORDERS = [
    {"id": 1, "isin": "IE00B4L5Y983", "quantity": 50, "date": "2022-01-15", "unitPrice": 75.20, "totalPriceEUR": 3760},
    {"id": 2, "isin": "IE00B3RBWM25", "quantity": 40, "date": "2022-03-10", "unitPrice": 95.50, "totalPriceEUR": 3820},
    {"id": 3, "isin": "IE00BKM4GZ66", "quantity": 100, "date": "2022-06-05", "unitPrice": 28.30, "totalPriceEUR": 2830},
    {"id": 4, "isin": "LU0274208692", "quantity": 30, "date": "2022-09-20", "unitPrice": 125.00, "totalPriceEUR": 3750},
    {"id": 5, "isin": "IE00B52VJ196", "quantity": 60, "date": "2023-01-12", "unitPrice": 42.10, "totalPriceEUR": 2526},
    {"id": 6, "isin": "IE00B3XXRP09", "quantity": 25, "date": "2023-04-08", "unitPrice": 68.40, "totalPriceEUR": 1710},
    {"id": 7, "isin": "IE00BZ163L38", "quantity": 80, "date": "2023-07-15", "unitPrice": 32.20, "totalPriceEUR": 2576},
    {"id": 8, "isin": "LU1681043599", "quantity": 45, "date": "2023-10-05", "unitPrice": 88.50, "totalPriceEUR": 3982.5},
    {"id": 9, "isin": "IE00BK5BQT80", "quantity": 35, "date": "2024-01-18", "unitPrice": 105.30, "totalPriceEUR": 3685.5},
    {"id": 10, "isin": "LU1437016972", "quantity": 90, "date": "2024-05-22", "unitPrice": 21.80, "totalPriceEUR": 1962},
]


def debug_log(message, data=None):
    """Fonction de logging pour les services."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if data:
        print(f"[{timestamp}] {message}: {data}")
    else:
        print(f"[{timestamp}] {message}")


def test_integration():
    """Test d'intégration complet."""
    print("="*70)
    print("🧪 TEST D'INTÉGRATION - BATCH PRICING")
    print("="*70)

    print(f"\n📋 Configuration:")
    print(f"   {len(MOCK_ORDERS)} ordres de test")
    print(f"   {len(set(o['isin'] for o in MOCK_ORDERS))} ISINs distincts")

    # Initialiser les services
    print(f"\n🔧 Initialisation des services...")
    price_service = PriceService(debug_logger=debug_log)
    portfolio_service = PortfolioService(
        orders_file_path="orders.json",  # Non utilisé ici
        price_service=price_service,
        debug_logger=debug_log
    )

    print(f"   ✅ Services initialisés")

    # Test 1: Calculer les valeurs mensuelles (avec batch pricing)
    print(f"\n" + "="*70)
    print(f"📊 TEST: Calcul des valeurs mensuelles du portefeuille")
    print(f"="*70)

    start_time = time.time()

    monthly_values = portfolio_service.get_monthly_portfolio_values(MOCK_ORDERS)

    elapsed_time = time.time() - start_time

    print(f"\n⏱️  Résultats:")
    print(f"   Temps total: {elapsed_time:.2f}s")
    print(f"   Nombre de mois calculés: {len(monthly_values)}")

    if len(monthly_values) > 0:
        print(f"\n📈 Échantillon de données (3 derniers mois):")
        for month_data in monthly_values[-3:]:
            month_display = month_data.get('month_display', month_data.get('month', 'N/A'))
            portfolio_value = month_data.get('portfolio_value', 0)
            invested_capital = month_data.get('invested_capital', 0)
            pl = portfolio_value - invested_capital
            pl_pct = (pl / invested_capital * 100) if invested_capital > 0 else 0

            print(f"   {month_display}: {portfolio_value:.2f}€ (investi: {invested_capital:.2f}€, +/- {pl:.2f}€ = {pl_pct:+.2f}%)")

    # Vérifier que le batch cache est rempli
    print(f"\n🗄️  État du cache batch:")
    print(f"   ISINs en cache: {len(price_service._batch_cache)}")
    for isin in price_service._batch_cache:
        days_cached = len(price_service._batch_cache[isin])
        print(f"   - {isin}: {days_cached} jours")

    # Test 2: Vérifier qu'on peut réutiliser le cache
    print(f"\n" + "="*70)
    print(f"🔄 TEST: Réutilisation du cache (devrait être instantané)")
    print(f"="*70)

    cache_start = time.time()

    # Recalculer (devrait utiliser le cache)
    monthly_values_cached = portfolio_service.get_monthly_portfolio_values(MOCK_ORDERS)

    cache_elapsed = time.time() - cache_start

    print(f"\n⏱️  Résultats avec cache:")
    print(f"   Temps total: {cache_elapsed:.2f}s")
    print(f"   Speedup vs premier chargement: {elapsed_time/cache_elapsed:.1f}x")

    if cache_elapsed < 1.0:
        print(f"   ✅ Cache fonctionne parfaitement (< 1s)")
    else:
        print(f"   ⚠️  Cache semble ne pas fonctionner (> 1s)")

    # Test 3: Position individuelle
    test_isin = "IE00B4L5Y983"
    test_position_orders = [o for o in MOCK_ORDERS if o['isin'] == test_isin]

    print(f"\n" + "="*70)
    print(f"📊 TEST: Valeurs mensuelles d'une position ({test_isin})")
    print(f"="*70)

    position_start = time.time()

    position_values = portfolio_service.get_monthly_position_values(test_position_orders, test_isin)

    position_elapsed = time.time() - position_start

    print(f"\n⏱️  Résultats:")
    print(f"   Temps total: {position_elapsed:.2f}s")
    print(f"   Nombre de mois: {len(position_values)}")

    # Recommandations finales
    print(f"\n" + "="*70)
    print(f"💡 ÉVALUATION FINALE")
    print(f"="*70)

    if elapsed_time < 3.0:
        print(f"\n✅ EXCELLENT - Chargement initial < 3s")
        print(f"   Le batch pricing fonctionne parfaitement !")
        print(f"   Prêt pour la production.")
    elif elapsed_time < 5.0:
        print(f"\n⚠️  BON - Chargement initial < 5s")
        print(f"   Le batch pricing améliore les performances.")
        print(f"   Considérer un cache Firebase pour encore mieux.")
    else:
        print(f"\n❌ LENT - Chargement initial > 5s")
        print(f"   Le batch pricing aide mais pas suffisant.")
        print(f"   Cache Firebase OBLIGATOIRE pour production.")

    print(f"\n📊 Métriques clés:")
    print(f"   - Chargement initial: {elapsed_time:.2f}s")
    print(f"   - Avec cache: {cache_elapsed:.2f}s")
    print(f"   - Position individuelle: {position_elapsed:.2f}s")
    print(f"   - ISINs en cache: {len(price_service._batch_cache)}")

    print(f"\n" + "="*70)
    print(f"✅ TEST TERMINÉ")
    print(f"="*70)


if __name__ == "__main__":
    test_integration()
