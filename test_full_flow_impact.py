"""
Analyse de l'impact du batch pricing sur le FLUX COMPLET de chargement du graphique.

Simule le workflow complet:
1. Chargement des ordres utilisateur
2. Calcul des valeurs mensuelles du portefeuille
3. Fetching des prix historiques (APPROCHE ACTUELLE vs BATCH)
"""

import time
import yfinance as yf
from datetime import datetime, date, timedelta
from typing import Dict, List, Any
import json
from pathlib import Path
import concurrent.futures

# Simulation de données utilisateur réalistes
MOCK_USER_ORDERS = [
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


def generate_monthly_dates(start_date: date, end_date: date) -> List[date]:
    """Génère toutes les dates du 1er de chaque mois entre start_date et end_date."""
    dates = []
    current = date(start_date.year, start_date.month, 1)

    while current <= end_date:
        dates.append(current)

        # Mois suivant
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return dates


def get_portfolio_isins(orders: List[Dict]) -> List[str]:
    """Extrait la liste unique des ISINs du portefeuille."""
    return list(set(order['isin'] for order in orders))


def calculate_positions_at_date(orders: List[Dict], target_date: date) -> Dict[str, Dict]:
    """Calcule les positions (quantité, capital investi) à une date donnée."""
    positions = {}

    for order in orders:
        order_date = datetime.strptime(order['date'], '%Y-%m-%d').date()

        if order_date < target_date:
            isin = order['isin']

            if isin not in positions:
                positions[isin] = {'quantity': 0, 'invested': 0}

            positions[isin]['quantity'] += order['quantity']
            positions[isin]['invested'] += order['totalPriceEUR']

    return positions


# ============================================================================
# APPROCHE ACTUELLE: Fetch prix un par un pour chaque position à chaque mois
# ============================================================================

def fetch_price_current_approach(isin: str, target_date: date) -> float:
    """Fetch prix avec l'approche actuelle (requête individuelle)."""
    try:
        yf_ticker = yf.Ticker(isin)
        start_date = target_date - timedelta(days=10)
        end_date = target_date + timedelta(days=1)

        hist = yf_ticker.history(
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d"
        )

        if hist.empty:
            return None

        # Trouver la meilleure date
        hist = hist.sort_index()
        for idx, row in hist.iterrows():
            price_date = idx.date()
            if price_date <= target_date:
                best_price = float(row.get("Close"))

        return best_price
    except:
        return None


def calculate_monthly_values_current_approach(orders: List[Dict]) -> Dict:
    """Calcul complet avec l'approche actuelle."""
    print("\n" + "="*70)
    print("🔵 APPROCHE ACTUELLE (requête par position par mois)")
    print("="*70)

    start_time = time.time()

    # 1. Déterminer la période
    first_order_date = min(datetime.strptime(o['date'], '%Y-%m-%d').date() for o in orders)
    monthly_dates = generate_monthly_dates(first_order_date, date.today())

    print(f"\n📅 Période: {first_order_date} → {date.today()}")
    print(f"   {len(monthly_dates)} mois à calculer")

    unique_isins = get_portfolio_isins(orders)
    print(f"📦 {len(unique_isins)} ISINs distincts")

    # 2. Calculer pour chaque mois
    monthly_values = []
    api_calls = 0

    calc_start = time.time()

    for i, month_date in enumerate(monthly_dates):
        if i == 0:
            # Premier mois = valeur 0
            monthly_values.append({
                'date': month_date,
                'portfolio_value': 0,
                'invested': 0
            })
            continue

        # Positions à cette date
        positions = calculate_positions_at_date(orders, month_date)

        portfolio_value = 0
        invested = 0

        # Pour chaque position, fetch le prix (GOULET D'ÉTRANGLEMENT)
        for isin, pos_data in positions.items():
            api_calls += 1
            price = fetch_price_current_approach(isin, month_date)

            if price:
                portfolio_value += price * pos_data['quantity']

            invested += pos_data['invested']

        monthly_values.append({
            'date': month_date,
            'portfolio_value': portfolio_value,
            'invested': invested
        })

        # Progress indicator
        if (i + 1) % 5 == 0:
            print(f"   📊 Progression: {i+1}/{len(monthly_dates)} mois calculés...")

    calc_time = time.time() - calc_start
    total_time = time.time() - start_time

    print(f"\n⏱️  RÉSULTATS:")
    print(f"   Temps total: {total_time:.2f}s")
    print(f"   Temps calcul (avec API): {calc_time:.2f}s")
    print(f"   Requêtes API: {api_calls}")
    print(f"   Temps moyen/requête: {calc_time/api_calls:.3f}s")

    return {
        'approach': 'CURRENT',
        'total_time': total_time,
        'calc_time': calc_time,
        'api_calls': api_calls,
        'monthly_values': monthly_values
    }


# ============================================================================
# APPROCHE BATCH: Fetch tous les prix d'un ISIN en une fois, puis lookup
# ============================================================================

def fetch_all_prices_batch(isin: str) -> Dict[date, float]:
    """Fetch TOUS les prix historiques d'un ISIN en une seule requête."""
    try:
        yf_ticker = yf.Ticker(isin)
        hist = yf_ticker.history(period='max', interval='1d')

        if hist.empty:
            return {}

        # Créer un dictionnaire date -> prix
        prices = {}
        for idx, row in hist.iterrows():
            prices[idx.date()] = float(row['Close'])

        return prices
    except:
        return {}


def get_price_for_date(price_cache: Dict[date, float], target_date: date) -> float:
    """Lookup du prix à une date donnée depuis le cache."""
    # Chercher la date exacte ou la plus proche avant
    available_dates = sorted([d for d in price_cache.keys() if d <= target_date], reverse=True)

    if available_dates:
        best_date = available_dates[0]
        return price_cache[best_date]

    return None


def calculate_monthly_values_batch_approach(orders: List[Dict]) -> Dict:
    """Calcul complet avec l'approche BATCH."""
    print("\n" + "="*70)
    print("🟢 APPROCHE BATCH (une requête par ISIN + lookup local)")
    print("="*70)

    start_time = time.time()

    # 1. Déterminer la période
    first_order_date = min(datetime.strptime(o['date'], '%Y-%m-%d').date() for o in orders)
    monthly_dates = generate_monthly_dates(first_order_date, date.today())

    print(f"\n📅 Période: {first_order_date} → {date.today()}")
    print(f"   {len(monthly_dates)} mois à calculer")

    unique_isins = get_portfolio_isins(orders)
    print(f"📦 {len(unique_isins)} ISINs distincts")

    # 2. BATCH FETCH: Télécharger TOUS les prix pour TOUS les ISINs EN PARALLÈLE
    print(f"\n📥 Fetching batch pour {len(unique_isins)} ISINs (parallèle)...")
    fetch_start = time.time()

    price_cache = {}  # {isin: {date: price}}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_all_prices_batch, isin): isin for isin in unique_isins}

        for future in concurrent.futures.as_completed(futures):
            isin = futures[future]
            prices = future.result()
            price_cache[isin] = prices
            print(f"   ✅ {isin}: {len(prices)} jours")

    fetch_time = time.time() - fetch_start
    api_calls = len(unique_isins)  # Une requête par ISIN

    print(f"   ⏱️  Fetch temps: {fetch_time:.2f}s")
    print(f"   🌐 Requêtes API: {api_calls}")

    # 3. Calcul des valeurs mensuelles (LOOKUP LOCAL, ultra rapide)
    print(f"\n🔍 Calcul des valeurs mensuelles (lookup local)...")
    calc_start = time.time()

    monthly_values = []

    for i, month_date in enumerate(monthly_dates):
        if i == 0:
            monthly_values.append({
                'date': month_date,
                'portfolio_value': 0,
                'invested': 0
            })
            continue

        positions = calculate_positions_at_date(orders, month_date)

        portfolio_value = 0
        invested = 0

        # Lookup local (O(log n), super rapide)
        for isin, pos_data in positions.items():
            price = get_price_for_date(price_cache.get(isin, {}), month_date)

            if price:
                portfolio_value += price * pos_data['quantity']

            invested += pos_data['invested']

        monthly_values.append({
            'date': month_date,
            'portfolio_value': portfolio_value,
            'invested': invested
        })

    calc_time = time.time() - calc_start
    total_time = time.time() - start_time

    print(f"   ⏱️  Lookup temps: {calc_time:.3f}s")

    print(f"\n⏱️  RÉSULTATS:")
    print(f"   Temps total: {total_time:.2f}s")
    print(f"   - Fetch batch: {fetch_time:.2f}s")
    print(f"   - Lookup local: {calc_time:.3f}s")
    print(f"   Requêtes API: {api_calls}")

    return {
        'approach': 'BATCH',
        'total_time': total_time,
        'fetch_time': fetch_time,
        'calc_time': calc_time,
        'api_calls': api_calls,
        'monthly_values': monthly_values
    }


def compare_full_flow(current_result: Dict, batch_result: Dict):
    """Compare les deux approches sur le flux complet."""
    print("\n" + "="*70)
    print("📊 IMPACT DU BATCH PRICING SUR LE FLUX COMPLET")
    print("="*70)

    print(f"\n⏱️  TEMPS TOTAL (ce que l'utilisateur attend):")
    print(f"   Approche actuelle: {current_result['total_time']:.2f}s")
    print(f"   Approche batch:    {batch_result['total_time']:.2f}s")

    speedup = current_result['total_time'] / batch_result['total_time'] if batch_result['total_time'] > 0 else 0
    reduction = current_result['total_time'] - batch_result['total_time']
    reduction_pct = (reduction / current_result['total_time']) * 100 if current_result['total_time'] > 0 else 0

    print(f"\n   🚀 GAIN: {reduction:.2f}s économisés ({reduction_pct:.0f}% plus rapide)")
    print(f"   📈 Speedup: {speedup:.1f}x")

    print(f"\n🌐 REQUÊTES API:")
    print(f"   Approche actuelle: {current_result['api_calls']} requêtes")
    print(f"   Approche batch:    {batch_result['api_calls']} requêtes")

    api_reduction = current_result['api_calls'] - batch_result['api_calls']
    api_reduction_pct = (api_reduction / current_result['api_calls']) * 100 if current_result['api_calls'] > 0 else 0

    print(f"\n   📉 RÉDUCTION: {api_reduction} requêtes économisées ({api_reduction_pct:.0f}%)")

    # Décomposition du temps batch
    if 'fetch_time' in batch_result:
        print(f"\n🔍 DÉCOMPOSITION (Approche batch):")
        print(f"   Fetch batch (API):  {batch_result['fetch_time']:.2f}s ({batch_result['fetch_time']/batch_result['total_time']*100:.0f}%)")
        print(f"   Lookup local:       {batch_result['calc_time']:.3f}s ({batch_result['calc_time']/batch_result['total_time']*100:.0f}%)")

    # Recommandation
    print("\n" + "="*70)
    print("💡 RECOMMANDATION")
    print("="*70)

    if reduction_pct > 50:
        print(f"\n✅ IMPACT TRÈS SIGNIFICATIF ({reduction_pct:.0f}% de gain)")
        print(f"   👉 IMPLÉMENTATION FORTEMENT RECOMMANDÉE")
        print(f"\n   Bénéfices:")
        print(f"   - Expérience utilisateur: passage de {current_result['total_time']:.0f}s → {batch_result['total_time']:.0f}s")
        print(f"   - Charge API: {api_reduction_pct:.0f}% de requêtes en moins")
        print(f"   - Scalabilité: meilleure avec plus d'utilisateurs")
    elif reduction_pct > 30:
        print(f"\n⚠️  IMPACT SIGNIFICATIF ({reduction_pct:.0f}% de gain)")
        print(f"   👉 IMPLÉMENTATION RECOMMANDÉE")
    else:
        print(f"\n⚡ IMPACT MODÉRÉ ({reduction_pct:.0f}% de gain)")
        print(f"   👉 Considérer d'autres optimisations aussi")


def main():
    """Fonction principale."""
    print("="*70)
    print("🧪 ANALYSE D'IMPACT: BATCH PRICING SUR FLUX COMPLET")
    print("="*70)

    print(f"\n📋 Portefeuille de test:")
    print(f"   {len(MOCK_USER_ORDERS)} ordres")
    print(f"   {len(get_portfolio_isins(MOCK_USER_ORDERS))} ISINs distincts")

    first_date = min(datetime.strptime(o['date'], '%Y-%m-%d').date() for o in MOCK_USER_ORDERS)
    print(f"   Période: {first_date} → {date.today()}")

    # Test approche actuelle
    current_result = calculate_monthly_values_current_approach(MOCK_USER_ORDERS)

    print("\n⏸️  Pause de 3 secondes...")
    time.sleep(3)

    # Test approche batch
    batch_result = calculate_monthly_values_batch_approach(MOCK_USER_ORDERS)

    # Comparaison et recommandation
    compare_full_flow(current_result, batch_result)

    print("\n" + "="*70)
    print("✅ ANALYSE TERMINÉE")
    print("="*70)


if __name__ == "__main__":
    main()
