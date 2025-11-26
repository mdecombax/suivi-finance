"""
Test batch pricing avec plusieurs ISINs en parallèle.
"""

import time
import yfinance as yf
from datetime import datetime, date, timedelta
from typing import Dict, List
import concurrent.futures

# ISINs de test (ETFs populaires)
TEST_ISINS = [
    "IE00B4L5Y983",  # iShares Core MSCI World
    "IE00B3RBWM25",  # Vanguard FTSE All-World
    "IE00BKM4GZ66",  # iShares Core MSCI EM IMI
    "LU0274208692",  # Xtrackers MSCI World
    "IE00B52VJ196",  # iShares MSCI Europe
    "IE00B3XXRP09",  # Vanguard S&P 500
    "IE00BZ163L38",  # Vanguard FTSE Dev Europe
    "LU1681043599",  # Amundi MSCI World
    "IE00BK5BQT80",  # Vanguard FTSE Dev World
    "LU1437016972",  # Amundi MSCI EM
]

def generate_test_dates(num_months=24) -> List[date]:
    """Génère une liste de dates (1er de chaque mois) pour les N derniers mois."""
    dates = []
    today = date.today()

    for i in range(num_months, 0, -1):
        target_month = today.month - i
        target_year = today.year

        while target_month <= 0:
            target_month += 12
            target_year -= 1

        dates.append(date(target_year, target_month, 1))

    return dates


def fetch_batch_for_isin(isin: str, test_dates: List[date]) -> Dict:
    """Fetch batch pour un ISIN."""
    try:
        yf_ticker = yf.Ticker(isin)
        hist = yf_ticker.history(period='max', interval='1d')

        if hist.empty:
            return {'isin': isin, 'success': False, 'error': 'No data'}

        hist = hist.sort_index()
        hist_dates = [idx.date() for idx in hist.index]

        prices = {}
        for target_date in test_dates:
            for hist_date in reversed(hist_dates):
                if hist_date <= target_date:
                    row = hist.loc[hist.index[hist.index.map(lambda x: x.date()) == hist_date][0]]
                    prices[target_date] = {
                        'price': float(row['Close']),
                        'date': hist_date
                    }
                    break

        return {
            'isin': isin,
            'success': True,
            'prices': prices,
            'total_days': len(hist),
            'success_rate': len(prices) / len(test_dates) * 100
        }
    except Exception as e:
        return {'isin': isin, 'success': False, 'error': str(e)}


def test_batch_multi_sequential(isins: List[str], test_dates: List[date]) -> Dict:
    """Test batch SÉQUENTIEL (un après l'autre)."""
    print(f"\n🔵 Test BATCH SÉQUENTIEL")
    print(f"   {len(isins)} ISINs × {len(test_dates)} dates")

    start_time = time.time()
    results = []

    for isin in isins:
        print(f"   Fetching {isin}...", end=" ")
        result = fetch_batch_for_isin(isin, test_dates)
        results.append(result)
        if result['success']:
            print(f"✅ ({result['success_rate']:.0f}%)")
        else:
            print(f"❌ {result.get('error', 'Unknown error')}")

    elapsed_time = time.time() - start_time

    successful = sum(1 for r in results if r['success'])

    return {
        'approach': 'SEQUENTIAL',
        'elapsed_time': elapsed_time,
        'isins_count': len(isins),
        'successful': successful,
        'results': results
    }


def test_batch_multi_parallel(isins: List[str], test_dates: List[date], max_workers=5) -> Dict:
    """Test batch PARALLÈLE (concurrent)."""
    print(f"\n🟢 Test BATCH PARALLÈLE (max_workers={max_workers})")
    print(f"   {len(isins)} ISINs × {len(test_dates)} dates")

    start_time = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_batch_for_isin, isin, test_dates): isin for isin in isins}

        for future in concurrent.futures.as_completed(futures):
            isin = futures[future]
            try:
                result = future.result()
                results.append(result)
                if result['success']:
                    print(f"   ✅ {isin} ({result['success_rate']:.0f}%)")
                else:
                    print(f"   ❌ {isin}: {result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"   ❌ {isin}: Exception {e}")
                results.append({'isin': isin, 'success': False, 'error': str(e)})

    elapsed_time = time.time() - start_time

    successful = sum(1 for r in results if r['success'])

    return {
        'approach': 'PARALLEL',
        'elapsed_time': elapsed_time,
        'isins_count': len(isins),
        'successful': successful,
        'max_workers': max_workers,
        'results': results
    }


def compare_multi_results(seq_result: Dict, par_result: Dict):
    """Compare les résultats séquentiels vs parallèles."""
    print("\n" + "="*70)
    print("📊 COMPARAISON SÉQUENTIEL vs PARALLÈLE")
    print("="*70)

    print(f"\n📦 Nombre d'ISINs: {seq_result['isins_count']}")

    print(f"\n⏱️  TEMPS D'EXÉCUTION:")
    print(f"   Séquentiel: {seq_result['elapsed_time']:.2f}s")
    print(f"   Parallèle:  {par_result['elapsed_time']:.2f}s")
    speedup = seq_result['elapsed_time'] / par_result['elapsed_time'] if par_result['elapsed_time'] > 0 else 0
    print(f"   🚀 Speedup: {speedup:.1f}x plus rapide")

    print(f"\n✅ TAUX DE SUCCÈS:")
    print(f"   Séquentiel: {seq_result['successful']}/{seq_result['isins_count']}")
    print(f"   Parallèle:  {par_result['successful']}/{par_result['isins_count']}")


def main():
    """Fonction principale."""
    print("="*70)
    print("🧪 TEST MULTI-ISIN: SÉQUENTIEL vs PARALLÈLE")
    print("="*70)

    test_dates = generate_test_dates(num_months=24)
    print(f"\n📅 {len(test_dates)} dates de test")
    print(f"   Période: {test_dates[0]} → {test_dates[-1]}")

    print(f"\n🎯 Test avec {len(TEST_ISINS)} ISINs")

    # Test séquentiel
    seq_result = test_batch_multi_sequential(TEST_ISINS, test_dates)

    print("\n⏸️  Pause de 3 secondes...")
    time.sleep(3)

    # Test parallèle
    par_result = test_batch_multi_parallel(TEST_ISINS, test_dates, max_workers=5)

    # Comparaison
    compare_multi_results(seq_result, par_result)

    # Recommandation finale
    print("\n" + "="*70)
    print("💡 RECOMMANDATION")
    print("="*70)

    if par_result['elapsed_time'] < 5.0:
        print("\n✅ Le batch parallèle est EXCELLENT pour la production")
        print(f"   Temps: {par_result['elapsed_time']:.1f}s pour {len(TEST_ISINS)} ISINs")
        print(f"   Estimation pour 20 ISINs: ~{par_result['elapsed_time'] * 2:.1f}s")
    elif par_result['elapsed_time'] < 10.0:
        print("\n⚠️  Le batch parallèle est BON mais peut être amélioré")
        print(f"   Temps: {par_result['elapsed_time']:.1f}s pour {len(TEST_ISINS)} ISINs")
        print("   Considérer un cache Redis pour améliorer davantage")
    else:
        print("\n❌ Le batch parallèle reste lent")
        print(f"   Temps: {par_result['elapsed_time']:.1f}s")
        print("   Cache backend OBLIGATOIRE pour production")

    print("\n" + "="*70)
    print("✅ TEST TERMINÉ")
    print("="*70)


if __name__ == "__main__":
    main()
