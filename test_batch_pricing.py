"""
Script de test pour évaluer les performances du batch pricing avec yfinance.
Compare l'approche actuelle (requête par date) vs batch (period='max').
"""

import time
import yfinance as yf
from datetime import datetime, date, timedelta
from typing import Dict, List
import statistics

# ISINs de test (ETFs populaires)
TEST_ISINS = [
    "IE00B4L5Y983",  # iShares Core MSCI World
    "IE00B3RBWM25",  # Vanguard FTSE All-World
    "IE00BKM4GZ66",  # iShares Core MSCI EM IMI
    "LU0274208692",  # Xtrackers MSCI World
    "IE00B52VJ196",  # iShares MSCI Europe
]

# Dates de test (24 derniers mois, 1er de chaque mois)
def generate_test_dates(num_months=24) -> List[date]:
    """Génère une liste de dates (1er de chaque mois) pour les N derniers mois."""
    dates = []
    today = date.today()

    for i in range(num_months, 0, -1):
        # Calculer le mois i mois en arrière
        target_month = today.month - i
        target_year = today.year

        while target_month <= 0:
            target_month += 12
            target_year -= 1

        dates.append(date(target_year, target_month, 1))

    return dates


def test_current_approach(isin: str, test_dates: List[date]) -> Dict:
    """
    Teste l'approche actuelle : une requête yfinance par date.
    Simule ce que fait _get_yahoo_historical_price() actuellement.
    """
    print(f"\n🔵 Test APPROCHE ACTUELLE pour {isin}")
    print(f"   Fetching prix pour {len(test_dates)} dates distinctes...")

    start_time = time.time()
    request_count = 0
    success_count = 0
    prices = {}

    yf_ticker = yf.Ticker(isin)

    for target_date in test_dates:
        request_count += 1

        # Fenêtre de 10 jours comme dans le code actuel
        start_date = target_date - timedelta(days=10)
        end_date = target_date + timedelta(days=1)

        try:
            hist = yf_ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d"
            )

            if not hist.empty:
                # Trouver la meilleure date disponible
                hist = hist.sort_index()
                for idx, row in hist.iterrows():
                    price_date = idx.date()
                    if price_date <= target_date:
                        prices[target_date] = {
                            'price': float(row.get("Close")),
                            'date': price_date
                        }

                if target_date in prices:
                    success_count += 1

        except Exception as e:
            print(f"   ❌ Erreur pour {target_date}: {e}")

    elapsed_time = time.time() - start_time

    result = {
        'approach': 'CURRENT (per-date requests)',
        'isin': isin,
        'total_dates': len(test_dates),
        'request_count': request_count,
        'success_count': success_count,
        'elapsed_time': elapsed_time,
        'avg_time_per_request': elapsed_time / request_count if request_count > 0 else 0,
        'prices': prices
    }

    print(f"   ✅ Terminé en {elapsed_time:.2f}s")
    print(f"   📊 {success_count}/{len(test_dates)} prix récupérés")
    print(f"   ⏱️  Temps moyen par requête: {result['avg_time_per_request']:.3f}s")

    return result


def test_batch_approach(isin: str, test_dates: List[date]) -> Dict:
    """
    Teste l'approche BATCH : une seule requête period='max' puis lookup local.
    """
    print(f"\n🟢 Test APPROCHE BATCH pour {isin}")
    print(f"   Fetching TOUTES les données historiques en une fois...")

    start_time = time.time()
    request_count = 1  # Une seule requête
    success_count = 0
    prices = {}

    yf_ticker = yf.Ticker(isin)

    try:
        # UNE SEULE requête pour tout l'historique
        hist = yf_ticker.history(period='max', interval='1d')

        fetch_time = time.time() - start_time
        print(f"   📥 Données fetched en {fetch_time:.2f}s ({len(hist)} jours)")

        if not hist.empty:
            # Créer un index de lookup pour accès O(1)
            hist = hist.sort_index()
            hist_dates = [idx.date() for idx in hist.index]

            # Pour chaque date de test, trouver le prix (lookup local)
            lookup_start = time.time()

            for target_date in test_dates:
                # Trouver la meilleure date <= target_date
                best_date = None
                best_price = None

                for hist_date in reversed(hist_dates):
                    if hist_date <= target_date:
                        best_date = hist_date
                        # Récupérer le prix
                        row = hist.loc[hist.index[hist.index.map(lambda x: x.date()) == hist_date][0]]
                        best_price = float(row['Close'])
                        break

                if best_price is not None:
                    prices[target_date] = {
                        'price': best_price,
                        'date': best_date
                    }
                    success_count += 1

            lookup_time = time.time() - lookup_start
            print(f"   🔍 Lookup local en {lookup_time:.3f}s")

    except Exception as e:
        print(f"   ❌ Erreur batch: {e}")

    elapsed_time = time.time() - start_time

    result = {
        'approach': 'BATCH (period=max)',
        'isin': isin,
        'total_dates': len(test_dates),
        'request_count': request_count,
        'success_count': success_count,
        'elapsed_time': elapsed_time,
        'fetch_time': fetch_time if 'fetch_time' in locals() else elapsed_time,
        'lookup_time': lookup_time if 'lookup_time' in locals() else 0,
        'prices': prices
    }

    print(f"   ✅ Terminé en {elapsed_time:.2f}s")
    print(f"   📊 {success_count}/{len(test_dates)} prix récupérés")

    return result


def compare_results(current_result: Dict, batch_result: Dict):
    """Compare les deux approches."""
    print("\n" + "="*70)
    print("📊 COMPARAISON DES RÉSULTATS")
    print("="*70)

    print(f"\n🏷️  ISIN: {current_result['isin']}")
    print(f"📅 Nombre de dates testées: {current_result['total_dates']}")

    print(f"\n⏱️  TEMPS D'EXÉCUTION:")
    print(f"   Approche actuelle: {current_result['elapsed_time']:.2f}s")
    print(f"   Approche batch:    {batch_result['elapsed_time']:.2f}s")
    speedup = current_result['elapsed_time'] / batch_result['elapsed_time'] if batch_result['elapsed_time'] > 0 else 0
    print(f"   🚀 Speedup: {speedup:.1f}x plus rapide")

    print(f"\n🌐 NOMBRE DE REQUÊTES API:")
    print(f"   Approche actuelle: {current_result['request_count']} requêtes")
    print(f"   Approche batch:    {batch_result['request_count']} requête(s)")
    reduction = (1 - batch_result['request_count'] / current_result['request_count']) * 100
    print(f"   📉 Réduction: {reduction:.0f}%")

    print(f"\n✅ TAUX DE SUCCÈS:")
    current_rate = (current_result['success_count'] / current_result['total_dates']) * 100
    batch_rate = (batch_result['success_count'] / batch_result['total_dates']) * 100
    print(f"   Approche actuelle: {current_rate:.1f}%")
    print(f"   Approche batch:    {batch_rate:.1f}%")

    # Vérifier la cohérence des prix
    price_differences = []
    for target_date in current_result['prices']:
        if target_date in batch_result['prices']:
            current_price = current_result['prices'][target_date]['price']
            batch_price = batch_result['prices'][target_date]['price']
            diff = abs(current_price - batch_price)
            price_differences.append(diff)

    if price_differences:
        avg_diff = statistics.mean(price_differences)
        max_diff = max(price_differences)
        print(f"\n💰 COHÉRENCE DES PRIX:")
        print(f"   Différence moyenne: {avg_diff:.4f} EUR")
        print(f"   Différence maximale: {max_diff:.4f} EUR")

        if max_diff < 0.01:
            print(f"   ✅ Prix identiques (cohérence parfaite)")
        elif max_diff < 0.1:
            print(f"   ⚠️  Légères différences (acceptable)")
        else:
            print(f"   ❌ Différences significatives (vérifier)")


def main():
    """Fonction principale de test."""
    print("="*70)
    print("🧪 TEST DE PERFORMANCE: BATCH PRICING vs APPROCHE ACTUELLE")
    print("="*70)

    # Générer les dates de test
    test_dates = generate_test_dates(num_months=24)
    print(f"\n📅 {len(test_dates)} dates de test générées")
    print(f"   Période: {test_dates[0]} → {test_dates[-1]}")

    # Tester avec UN SEUL ISIN pour commencer
    test_isin = TEST_ISINS[0]

    print(f"\n🎯 Test avec 1 ISIN: {test_isin}")

    # Test 1: Approche actuelle
    current_result = test_current_approach(test_isin, test_dates)

    # Pause entre les tests
    print("\n⏸️  Pause de 2 secondes...")
    time.sleep(2)

    # Test 2: Approche batch
    batch_result = test_batch_approach(test_isin, test_dates)

    # Comparaison
    compare_results(current_result, batch_result)

    # Projection pour 10 ISINs
    print("\n" + "="*70)
    print("📈 PROJECTION POUR UN PORTEFEUILLE RÉEL (10 positions)")
    print("="*70)

    print(f"\n⏱️  Temps total estimé:")
    current_total = current_result['elapsed_time'] * 10
    batch_total = batch_result['elapsed_time'] * 10
    print(f"   Approche actuelle: {current_total:.1f}s ({current_total/60:.1f} minutes)")
    print(f"   Approche batch:    {batch_total:.1f}s")

    print(f"\n🌐 Requêtes API totales:")
    print(f"   Approche actuelle: {current_result['request_count'] * 10} requêtes")
    print(f"   Approche batch:    {batch_result['request_count'] * 10} requêtes")

    print("\n" + "="*70)
    print("✅ TEST TERMINÉ")
    print("="*70)


if __name__ == "__main__":
    main()
