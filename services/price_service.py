"""
Service for fetching financial prices from external APIs.
Handles both Yahoo Finance and JustETF data sources.
"""

import re
import threading
import time
import requests
import yfinance as yf
from datetime import datetime, timedelta, date
from typing import Optional, Tuple, Dict, Any, List
import concurrent.futures
import bisect
import math

from models import PriceQuote


class PriceService:
    """Service for fetching current and historical prices from various sources."""

    ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
    JUSTETF_BASE_URL = "https://www.justetf.com/api/etfs"

    # Durées de vie des caches (secondes). Sans cache, chaque requête refaisait tous
    # les appels JustETF / Yahoo (≈ 5-7 s par page, mesuré sur téléphone).
    CURRENT_PRICE_TTL = 600      # prix courant : 10 min
    HISTORY_TTL = 3600           # historique journalier : 1 h
    FX_TTL = 12 * 3600           # taux de change : 12 h

    def __init__(self, debug_logger=None):
        self.logger = debug_logger
        self._current_price_cache = {}  # {ticker/isin: (expiration, PriceQuote)}
        self._historical_price_cache = {}  # {(ticker/isin, date): (expiration, PriceQuote)}
        self._batch_cache_expiry = {}   # {isin: expiration}
        self._fx_cache_expiry = {}      # {devise: expiration}
        self._fetch_locks = {}          # {clé: Lock} : une seule requête réseau par clé à la fois
        self._locks_guard = threading.Lock()
        self._batch_cache = {}  # Cache pour le batch pricing: {isin: {date: price}}
        self._batch_sorted_dates = {}  # {isin: [dates triées]} pour la recherche dichotomique
        self._fx_cache = {}  # {devise: {date: taux vers EUR}}
    
    def _lock_for(self, key) -> threading.Lock:
        with self._locks_guard:
            lock = self._fetch_locks.get(key)
            if lock is None:
                lock = self._fetch_locks[key] = threading.Lock()
            return lock

    def _log(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log debug information if logger is available."""
        if self.logger:
            self.logger(message, extra)
    
    def is_valid_isin(self, identifier: str) -> bool:
        """Check if the given string is a valid ISIN code."""
        if not identifier:
            return False
        clean_identifier = identifier.strip().upper()
        return bool(self.ISIN_PATTERN.match(clean_identifier))
    
    def get_current_price(self, ticker_or_isin: str) -> PriceQuote:
        """
        Get the current price for a ticker symbol or ISIN.
        Returns price in EUR when possible.
        """
        if not ticker_or_isin:
            return PriceQuote(
                price=0.0,
                source="Error",
                error_message="Empty ticker/ISIN provided"
            )
        
        cached = self._current_price_cache.get(ticker_or_isin)
        if cached and cached[0] > time.time():
            return cached[1]

        # Requêtes simultanées pour le même ISIN (plusieurs API appelées en parallèle par
        # la page) : une seule part sur le réseau, les autres attendent son résultat.
        with self._lock_for(("price", ticker_or_isin)):
            cached = self._current_price_cache.get(ticker_or_isin)
            if cached and cached[0] > time.time():
                return cached[1]

            self._log("Fetching current price", {"ticker": ticker_or_isin})
            quote = None

            # Try Yahoo Finance first for ticker symbols
            if not self.is_valid_isin(ticker_or_isin):
                yahoo_quote = self._get_yahoo_current_price(ticker_or_isin)
                if yahoo_quote.is_valid:
                    quote = yahoo_quote

            # Try JustETF for ISIN codes or as fallback
            if quote is None and self.is_valid_isin(ticker_or_isin):
                justetf_quote = self._get_justetf_current_price(ticker_or_isin)
                if justetf_quote.is_valid:
                    quote = justetf_quote

            if quote is not None:
                self._current_price_cache[ticker_or_isin] = (time.time() + self.CURRENT_PRICE_TTL, quote)
                return quote

        return PriceQuote(
            price=0.0,
            source="Error",
            error_message="Price unavailable from all sources"
        )
    
    def get_historical_price(self, ticker_or_isin: str, target_date: date) -> PriceQuote:
        """
        Get historical price for a specific date.
        Returns the closest available price on or before the target date.
        """
        if not ticker_or_isin:
            return PriceQuote(
                price=0.0,
                source="Error",
                error_message="Empty ticker/ISIN provided"
            )
        
        # Un prix passé ne change plus : mémorisé 24 h (1 h pour aujourd'hui).
        # Sans ça, le graphique mensuel refaisait ~0,5 s d'appel JustETF par point manquant.
        key = (ticker_or_isin, target_date)
        cached = self._historical_price_cache.get(key)
        if cached and cached[0] > time.time():
            return cached[1]

        self._log("Fetching historical price", {
            "ticker": ticker_or_isin,
            "date": target_date.isoformat()
        })

        if self.is_valid_isin(ticker_or_isin):
            # Use JustETF for ISIN codes
            quote = self._get_justetf_historical_price(ticker_or_isin, target_date)
        else:
            # Use Yahoo Finance for ticker symbols
            quote = self._get_yahoo_historical_price(ticker_or_isin, target_date)

        ttl = self.HISTORY_TTL if target_date >= date.today() else 24 * 3600
        # Un échec est retenté au bout de 5 min plutôt qu'à chaque requête
        self._historical_price_cache[key] = (time.time() + (ttl if quote.is_valid else 300), quote)
        return quote
    
    def _get_yahoo_current_price(self, ticker: str) -> PriceQuote:
        """Get current price from Yahoo Finance."""
        try:
            yf_ticker = yf.Ticker(ticker)
            
            # Try fast_info first (more reliable in newer versions)
            price = self._extract_yahoo_fast_price(yf_ticker)
            
            # Fallback to info
            if price is None:
                price = self._extract_yahoo_info_price(yf_ticker)
            
            # Final fallback to recent history
            if price is None:
                price = self._extract_yahoo_history_price(yf_ticker)
            
            if price is None:
                return PriceQuote(
                    price=0.0,
                    source="Yahoo Finance",
                    error_message="No price data available"
                )
            
            # Convert to EUR if needed
            currency = self._get_yahoo_currency(yf_ticker)
            if currency and currency.upper() != "EUR":
                eur_price = self._convert_to_eur(price, currency)
                if eur_price is not None:
                    return PriceQuote(
                        price=eur_price,
                        source="Yahoo Finance (EUR)",
                        currency="EUR"
                    )
            
            return PriceQuote(
                price=price,
                source="Yahoo Finance",
                currency=currency or "EUR"
            )
            
        except Exception as e:
            self._log("Yahoo Finance error", {"ticker": ticker, "error": str(e)})
            return PriceQuote(
                price=0.0,
                source="Yahoo Finance",
                error_message=f"Yahoo Finance error: {str(e)}"
            )
    
    def _extract_yahoo_fast_price(self, yf_ticker) -> Optional[float]:
        """Extract price from Yahoo Finance fast_info."""
        try:
            fast_info = getattr(yf_ticker, "fast_info", None)
            if not fast_info:
                return None
            
            for key in ("lastPrice", "regularMarketPrice", "last_price", "last_trade_price"):
                if key in fast_info and fast_info[key] is not None:
                    return float(fast_info[key])
        except Exception:
            pass
        return None
    
    def _extract_yahoo_info_price(self, yf_ticker) -> Optional[float]:
        """Extract price from Yahoo Finance info."""
        try:
            info = yf_ticker.info or {}
            for key in ("currentPrice", "regularMarketPrice", "regularMarketPreviousClose"):
                if key in info and info[key] is not None:
                    return float(info[key])
        except Exception:
            pass
        return None
    
    def _extract_yahoo_history_price(self, yf_ticker) -> Optional[float]:
        """Extract latest price from Yahoo Finance history."""
        try:
            hist = yf_ticker.history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return None
    
    def _get_yahoo_currency(self, yf_ticker) -> Optional[str]:
        """Get currency from Yahoo Finance ticker."""
        try:
            # Try fast_info first
            fast_info = getattr(yf_ticker, "fast_info", None)
            if fast_info and "currency" in fast_info and fast_info["currency"]:
                return str(fast_info["currency"]).upper()
        except Exception:
            pass
        
        try:
            # Fallback to info
            info = yf_ticker.info or {}
            currency = info.get("currency")
            if currency:
                return str(currency).upper()
        except Exception:
            pass
        
        return None
    
    def _convert_to_eur(self, amount: float, from_currency: str) -> Optional[float]:
        """Convert amount from given currency to EUR using Yahoo Finance FX rates."""
        if from_currency.upper() == "EUR":
            return amount
        
        try:
            fx_pair = f"{from_currency.upper()}EUR=X"
            fx_ticker = yf.Ticker(fx_pair)
            
            # Try fast_info first
            try:
                fast_info = getattr(fx_ticker, "fast_info", None)
                if fast_info:
                    for key in ("lastPrice", "regularMarketPrice", "last_price"):
                        if key in fast_info and fast_info[key] is not None:
                            rate = float(fast_info[key])
                            return amount * rate
            except Exception:
                pass
            
            # Fallback to recent history
            hist = fx_ticker.history(period="5d", interval="1d")
            if not hist.empty:
                rate = float(hist["Close"].iloc[-1])
                return amount * rate
                
        except Exception as e:
            self._log("Currency conversion error", {
                "from": from_currency,
                "to": "EUR",
                "error": str(e)
            })
        
        return None
    
    def _get_yahoo_historical_price(self, ticker: str, target_date: date) -> PriceQuote:
        """Get historical price from Yahoo Finance."""
        try:
            yf_ticker = yf.Ticker(ticker)
            start_date = target_date - timedelta(days=10)
            end_date = target_date + timedelta(days=1)
            
            self._log("Yahoo Finance history request", {
                "ticker": ticker,
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            })
            
            hist = yf_ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d"
            )
            
            if hist.empty:
                return PriceQuote(
                    price=0.0,
                    source="Yahoo Finance",
                    error_message="No historical data available"
                )
            
            # Find the best available date on or before target date
            best_date = None
            best_price = None
            
            hist = hist.sort_index()
            for idx, row in hist.iterrows():
                price_date = idx.date()
                if price_date <= target_date:
                    if not best_date or price_date > best_date:
                        best_date = price_date
                        best_price = float(row.get("Close"))
            
            if best_price is None:
                return PriceQuote(
                    price=0.0,
                    source="Yahoo Finance",
                    error_message="No price data for requested date"
                )
            
            # Convert to EUR if needed
            currency = self._get_yahoo_currency(yf_ticker)
            if currency and currency.upper() != "EUR":
                eur_price = self._convert_to_eur(best_price, currency)
                if eur_price is not None:
                    return PriceQuote(
                        price=eur_price,
                        source="Yahoo Finance (EUR)",
                        quote_date=best_date,
                        currency="EUR"
                    )
            
            return PriceQuote(
                price=best_price,
                source="Yahoo Finance",
                quote_date=best_date,
                currency=currency or "EUR"
            )
            
        except Exception as e:
            self._log("Yahoo Finance historical error", {
                "ticker": ticker,
                "date": target_date.isoformat(),
                "error": str(e)
            })
            return PriceQuote(
                price=0.0,
                source="Yahoo Finance",
                error_message=f"Yahoo Finance error: {str(e)}"
            )
    
    def _get_justetf_current_price(self, isin: str) -> PriceQuote:
        """Get current price from JustETF."""
        try:
            clean_isin = isin.strip().upper()
            url = f"{self.JUSTETF_BASE_URL}/{clean_isin}/quote"
            params = {"currency": "EUR", "locale": "fr"}
            
            self._log("JustETF quote request", {"url": url, "params": params})
            
            headers = self._get_justetf_headers(clean_isin)
            response = requests.get(url, params=params, headers=headers, timeout=8)
            
            self._log("JustETF response", {"status_code": response.status_code})
            response.raise_for_status()
            
            data = response.json()
            latest_quote = data.get("latestQuote", {})
            raw_price = latest_quote.get("raw")
            
            if raw_price is None:
                return PriceQuote(
                    price=0.0,
                    source="JustETF",
                    error_message="Invalid JustETF response"
                )
            
            venue = data.get("quoteTradingVenue")
            return PriceQuote(
                price=float(raw_price),
                source="JustETF",
                venue=venue,
                currency="EUR"
            )
            
        except Exception as e:
            self._log("JustETF quote error", {"isin": isin, "error": str(e)})
            return PriceQuote(
                price=0.0,
                source="JustETF",
                error_message=f"JustETF error: {str(e)}"
            )
    
    def _get_justetf_historical_price(self, isin: str, target_date: date) -> PriceQuote:
        """Get historical price from JustETF performance chart."""
        try:
            clean_isin = isin.strip().upper()
            start_date = target_date - timedelta(days=10)
            
            historical_data = self._fetch_justetf_historical_data(
                clean_isin,
                start_date.strftime("%Y-%m-%d"),
                target_date.strftime("%Y-%m-%d")
            )
            
            if not historical_data:
                # Fallback to current quote
                current_quote = self._get_justetf_current_price(isin)
                if current_quote.is_valid:
                    return current_quote
                return PriceQuote(
                    price=0.0,
                    source="JustETF",
                    error_message="No historical data available"
                )
            
            # Find best available date
            series = historical_data.get("series", [])
            best_date = None
            best_price = None
            
            for item in series:
                try:
                    item_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
                    if item_date <= target_date:
                        if not best_date or item_date > best_date:
                            best_date = item_date
                            best_price = float(item["value"])
                except Exception:
                    continue
            
            if best_price is not None:
                return PriceQuote(
                    price=best_price,
                    source="JustETF",
                    quote_date=best_date,
                    currency="EUR"
                )
            
            # Fallback to latest quote if no historical match
            latest_value = historical_data.get("latestQuote")
            latest_date = historical_data.get("latestQuoteDate")
            
            if latest_value is not None and latest_date:
                try:
                    latest_d = datetime.strptime(latest_date[:10], "%Y-%m-%d").date()
                    if latest_d <= target_date:
                        return PriceQuote(
                            price=float(latest_value),
                            source="JustETF",
                            quote_date=latest_d,
                            currency="EUR"
                        )
                except Exception:
                    pass
            
            return PriceQuote(
                price=0.0,
                source="JustETF",
                error_message="No suitable historical price found"
            )
            
        except Exception as e:
            self._log("JustETF historical error", {
                "isin": isin,
                "date": target_date.isoformat(),
                "error": str(e)
            })
            return PriceQuote(
                price=0.0,
                source="JustETF",
                error_message=f"JustETF historical error: {str(e)}"
            )
    
    def _fetch_justetf_historical_data(
        self,
        isin: str,
        date_from: str,
        date_to: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch historical data from JustETF performance chart endpoint."""
        try:
            url = f"{self.JUSTETF_BASE_URL}/{isin}/performance-chart"
            params = {
                "locale": "fr",
                "currency": "EUR",
                "valuesType": "MARKET_VALUE",
                "reduceData": "false",
                "includeDividends": "false",
                "features": "DIVIDENDS",
                "dateFrom": date_from,
                "dateTo": date_to,
            }
            
            headers = self._get_justetf_headers(isin)
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            self._log("JustETF performance chart request", {"url": url, "params": params})
            self._log("JustETF response", {"status_code": response.status_code})
            
            response.raise_for_status()
            data = response.json()
            
            # Normalize series data
            normalized_series = []
            for item in data.get("series", []) or []:
                date_str = item.get("date")
                value_obj = item.get("value", {}) or {}
                raw_value = value_obj.get("raw")
                
                if date_str is not None and raw_value is not None:
                    try:
                        normalized_series.append({
                            "date": date_str,
                            "value": float(raw_value)
                        })
                    except Exception:
                        continue
            
            latest_quote = data.get("latestQuote", {}) or {}
            latest_raw = latest_quote.get("raw")
            latest_value = float(latest_raw) if latest_raw is not None else None
            
            result = {
                "latestQuote": latest_value,
                "latestQuoteDate": data.get("latestQuoteDate"),
                "series": normalized_series,
                "source": "JustETF",
            }
            
            self._log("JustETF performance parsed", {
                "points": len(normalized_series),
                "latestQuote": latest_value
            })
            
            return result
            
        except Exception as e:
            self._log("JustETF performance error", {"isin": isin, "error": str(e)})
            return None
    
    def _get_justetf_headers(self, isin: str) -> Dict[str, str]:
        """Get standard headers for JustETF API requests."""
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.justetf.com",
            "Referer": f"https://www.justetf.com/fr/etf-profile.html?isin={isin}",
            "Connection": "keep-alive",
        }

    # ============================================================================
    # BATCH PRICING - Optimisation pour récupérer tous les prix en une fois
    # ============================================================================

    def fetch_batch_historical_prices(self, isins: List[str], max_workers: int = 5) -> Dict[str, Dict[date, float]]:
        """
        Fetch tous les prix historiques pour une liste d'ISINs EN PARALLÈLE.

        Retourne: {isin: {date: price}}

        Cette méthode est ~50x plus rapide que des appels individuels à get_historical_price().
        """
        # Réutiliser les séries encore fraîches (re-télécharger l'historique complet
        # coûtait ~1,3 s par ISIN à chaque requête)
        now = time.time()
        results = {}
        to_fetch = []
        for isin in isins:
            if self._batch_cache.get(isin) and self._batch_cache_expiry.get(isin, 0) > now:
                results[isin] = self._batch_cache[isin]
            else:
                to_fetch.append(isin)

        self._log("Batch fetch starting", {"isins_count": len(isins), "from_cache": len(results),
                                           "to_fetch": len(to_fetch), "max_workers": max_workers})
        if not to_fetch:
            return results

        def fetch_one(isin):
            # Verrou par ISIN : deux requêtes simultanées ne téléchargent pas deux fois
            with self._lock_for(("history", isin)):
                if self._batch_cache.get(isin) and self._batch_cache_expiry.get(isin, 0) > time.time():
                    return self._batch_cache[isin]
                return self._fetch_all_prices_for_isin(isin)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Soumettre toutes les tâches en parallèle
            futures = {executor.submit(fetch_one, isin): isin for isin in to_fetch}

            # Récupérer les résultats au fur et à mesure
            for future in concurrent.futures.as_completed(futures):
                isin = futures[future]
                try:
                    prices = future.result()
                    results[isin] = prices

                    # Mettre à jour le cache (seules les séries non vides sont gardées 1 h)
                    if self._batch_cache.get(isin) is not prices:
                        self._batch_cache[isin] = prices
                        self._batch_sorted_dates.pop(isin, None)
                    if prices:
                        self._batch_cache_expiry[isin] = time.time() + self.HISTORY_TTL

                    self._log("Batch fetch completed for ISIN", {
                        "isin": isin,
                        "days_fetched": len(prices)
                    })
                except Exception as e:
                    self._log("Batch fetch failed for ISIN", {"isin": isin, "error": str(e)})
                    results[isin] = {}

        self._log("Batch fetch completed", {
            "total_isins": len(isins),
            "successful": sum(1 for p in results.values() if p)
        })

        return results

    def _fetch_all_prices_for_isin(self, isin: str) -> Dict[date, float]:
        """
        Fetch TOUS les prix historiques pour un ISIN en une seule requête.

        Utilise yfinance.history(period='max') pour récupérer tout l'historique.
        """
        try:
            yf_ticker = yf.Ticker(isin)
            hist = yf_ticker.history(period='max', interval='1d')

            if hist.empty:
                self._log("No historical data", {"isin": isin})
                return {}

            # Créer un dictionnaire date -> prix (on ignore les NaN de la séance en cours)
            prices = {}
            for idx, row in hist.iterrows():
                close = float(row['Close'])
                if not math.isnan(close) and close > 0:
                    prices[idx.date()] = close

            # Yahoo peut résoudre l'ISIN vers une cotation hors EUR (ex. IWDA.L en USD) :
            # convertir l'historique en EUR pour rester cohérent avec les prix JustETF.
            currency = None
            try:
                currency = (yf_ticker.history_metadata or {}).get('currency')
            except Exception:
                currency = None

            if prices and currency and currency.upper() != 'EUR':
                prices = self._convert_history_to_eur(prices, currency)

            return prices

        except Exception as e:
            self._log("Failed to fetch all prices", {"isin": isin, "error": str(e)})
            return {}

    def _get_fx_history_to_eur(self, currency: str) -> Dict[date, float]:
        """Historique journalier du taux <currency> -> EUR (Yahoo, ex. USDEUR=X), mis en cache."""
        if currency in self._fx_cache and self._fx_cache_expiry.get(currency, 0) > time.time():
            return self._fx_cache[currency]
        rates: Dict[date, float] = {}
        try:
            hist = yf.Ticker(f"{currency}EUR=X").history(period='max', interval='1d')
            for idx, row in hist.iterrows():
                rate = float(row['Close'])
                if not math.isnan(rate) and rate > 0:
                    rates[idx.date()] = rate
        except Exception as e:
            self._log("Failed to fetch FX history", {"currency": currency, "error": str(e)})
        self._fx_cache[currency] = rates
        # Un échec n'est mémorisé que 5 min (nouvel essai rapide), un succès 12 h
        self._fx_cache_expiry[currency] = time.time() + (self.FX_TTL if rates else 300)
        return rates

    def _convert_history_to_eur(self, prices: Dict[date, float], currency: str) -> Dict[date, float]:
        """Convertit un historique {date: prix} exprimé en `currency` vers l'EUR."""
        factor = 1.0
        cur = currency
        # Cotations en pence / cents (GBp, GBX, ZAc, ILA...) : ramener à l'unité
        if currency in ('GBp', 'GBX'):
            cur, factor = 'GBP', 0.01
        elif currency == 'ZAc':
            cur, factor = 'ZAR', 0.01
        elif currency == 'ILA':
            cur, factor = 'ILS', 0.01
        cur = cur.upper()

        with self._lock_for(("fx", cur)):  # plusieurs ISIN en USD → un seul téléchargement
            rates = self._get_fx_history_to_eur(cur)
        if not rates:
            # Sans taux de change, mieux vaut ne rien renvoyer que des prix faux :
            # le calcul retombera sur les autres sources de prix.
            self._log("No FX rates, dropping non-EUR history", {"currency": currency})
            return {}

        rate_dates = sorted(rates.keys())
        converted: Dict[date, float] = {}
        for d, price in prices.items():
            idx = bisect.bisect_right(rate_dates, d)
            # Taux au plus tard à cette date, sinon le premier disponible
            rate = rates[rate_dates[idx - 1]] if idx > 0 else rates[rate_dates[0]]
            converted[d] = price * factor * rate
        self._log("Converted history to EUR", {"currency": currency, "points": len(converted)})
        return converted

    def get_historical_price_from_batch(self, isin: str, target_date: date) -> Optional[float]:
        """
        Récupère un prix historique depuis le cache batch.

        Si le cache n'existe pas pour cet ISIN, retourne None.
        Cherche le prix à la date exacte ou la date la plus proche avant target_date.
        """
        if isin not in self._batch_cache:
            return None

        price_cache = self._batch_cache[isin]

        if not price_cache:
            return None

        # Chercher la date exacte ou la plus proche avant (recherche dichotomique
        # sur les dates triées, mises en cache : indispensable en granularité jour)
        sorted_dates = self._batch_sorted_dates.get(isin)
        if sorted_dates is None or len(sorted_dates) != len(price_cache):
            sorted_dates = sorted(price_cache.keys())
            self._batch_sorted_dates[isin] = sorted_dates

        idx = bisect.bisect_right(sorted_dates, target_date)
        if idx > 0:
            return price_cache[sorted_dates[idx - 1]]

        return None

    def clear_batch_cache(self):
        """Vide le cache batch (utile pour libérer de la mémoire)."""
        self._batch_cache = {}
        self._batch_sorted_dates = {}
        self._log("Batch cache cleared")