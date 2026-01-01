"""
Position Service - Enriched position data retrieval.
Extracts and consolidates data from multiple sources (Yahoo Finance, JustETF, Firebase).
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

import yfinance as yf
import requests


logger = logging.getLogger(__name__)


class PositionService:
    """Service for retrieving enriched position data."""

    def __init__(
        self,
        price_service,
        firebase_service,
        debug_logger: Optional[Callable] = None
    ):
        """
        Initialize PositionService.

        Args:
            price_service: Service for fetching current prices
            firebase_service: Service for Firebase/Firestore operations
            debug_logger: Optional debug logging function
        """
        self.price_service = price_service
        self.firebase_service = firebase_service
        self.debug_log = debug_logger or (lambda msg, data=None: None)

    def get_enriched_position_data(self, isin: str, user_id: str) -> Dict[str, Any]:
        """
        Get enriched data for a specific position.

        Combines data from:
        - Current price quote
        - Yahoo Finance (fund info, technical indicators)
        - JustETF (daily changes, trading venue)
        - User's portfolio (orders, P&L calculations)

        Args:
            isin: The ISIN of the position
            user_id: The authenticated user's ID

        Returns:
            Dict containing enriched position data
        """
        try:
            # Get basic price quote
            current_price_quote = self.price_service.get_current_price(isin)

            # Fetch data from all sources
            yahoo_info = self._fetch_yahoo_data(isin)
            justetf_data = self._fetch_justetf_data(isin)
            portfolio_info = self._calculate_portfolio_info(
                isin, user_id, current_price_quote
            )

            # Combine all data
            return {
                'isin': isin,
                'basic_quote': {
                    'price': current_price_quote.price,
                    'source': current_price_quote.source,
                    'is_valid': current_price_quote.is_valid,
                    'currency': current_price_quote.currency or 'EUR'
                },
                'yahoo_finance': yahoo_info,
                'justetf': justetf_data,
                'portfolio': portfolio_info,
                'last_updated': datetime.now().isoformat()
            }

        except Exception as e:
            self.debug_log("Error getting enriched position data", {
                "isin": isin,
                "error": str(e)
            })
            return self._get_error_response(isin, str(e))

    def _fetch_yahoo_data(self, isin: str) -> Dict[str, Any]:
        """Fetch data from Yahoo Finance."""
        yahoo_info = {}

        try:
            ticker = yf.Ticker(isin)
            info = ticker.info or {}

            yahoo_info = {
                'full_name': info.get('longName') or info.get('shortName', isin),
                'short_name': info.get('shortName', isin),
                'fund_family': info.get('fundFamily', 'N/A'),
                'currency': info.get('currency', 'EUR'),
                'expense_ratio': info.get('netExpenseRatio'),
                'pe_ratio': info.get('trailingPE'),
                'beta': info.get('beta3Year'),
                'ytd_return': info.get('ytdReturn'),
                'inception_date': info.get('fundInceptionDate'),
                'exchange': info.get('exchange', 'N/A'),
                'week_52_low': info.get('fiftyTwoWeekLow'),
                'week_52_high': info.get('fiftyTwoWeekHigh'),
                'avg_volume': info.get('averageVolume'),
                'market_cap': info.get('marketCap')
            }

            # Calculate technical indicators from historical data
            hist_1y = ticker.history(period='1y')
            if not hist_1y.empty:
                current_price = hist_1y['Close'].iloc[-1]
                sma_50 = (
                    hist_1y['Close'].rolling(50).mean().iloc[-1]
                    if len(hist_1y) > 50 else None
                )
                sma_200 = (
                    hist_1y['Close'].rolling(200).mean().iloc[-1]
                    if len(hist_1y) > 200 else None
                )

                yahoo_info.update({
                    'sma_50': float(sma_50) if sma_50 is not None else None,
                    'sma_200': float(sma_200) if sma_200 is not None else None,
                    'current_price_yahoo': float(current_price)
                })

        except Exception as e:
            self.debug_log("Error fetching Yahoo data", {
                "isin": isin,
                "error": str(e)
            })

        return yahoo_info

    def _fetch_justetf_data(self, isin: str) -> Dict[str, Any]:
        """Fetch data from JustETF."""
        justetf_data = {}

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
                'Accept': 'application/json',
                'Referer': f'https://www.justetf.com/fr/etf-profile.html?isin={isin}'
            }

            url = f"https://www.justetf.com/api/etfs/{isin}/quote"
            params = {'currency': 'EUR', 'locale': 'fr'}
            response = requests.get(url, params=params, headers=headers, timeout=8)

            if response.status_code == 200:
                data = response.json()
                justetf_data = {
                    'latest_quote': data.get('latestQuote', {}).get('raw'),
                    'previous_quote': data.get('previousQuote', {}).get('raw'),
                    'daily_change_pct': data.get('dtdPrc', {}).get('raw'),
                    'daily_change_abs': data.get('dtdAmt', {}).get('raw'),
                    'trading_venue': data.get('quoteTradingVenue'),
                    'week_52_low': data.get('quoteLowHigh', {}).get('low', {}).get('raw'),
                    'week_52_high': data.get('quoteLowHigh', {}).get('high', {}).get('raw')
                }

        except Exception as e:
            self.debug_log("Error fetching JustETF data", {
                "isin": isin,
                "error": str(e)
            })

        return justetf_data

    def _calculate_portfolio_info(
        self,
        isin: str,
        user_id: str,
        current_price_quote
    ) -> Dict[str, Any]:
        """Calculate portfolio metrics for the position."""
        portfolio_info = {'has_position': False}

        try:
            # Load user's orders from Firebase
            user_orders = self.firebase_service.get_user_orders(user_id)

            # Filter orders for this ISIN
            user_positions = [
                order for order in user_orders
                if order.get('isin') == isin
            ]

            if not user_positions:
                return portfolio_info

            # Calculate metrics
            total_quantity = sum(
                order.get('quantity', 0) for order in user_positions
            )
            total_invested = sum(
                order.get('totalPriceEUR', 0) for order in user_positions
            )
            avg_price = total_invested / total_quantity if total_quantity > 0 else 0

            # Parse order dates
            order_dates = self._parse_order_dates(user_positions)

            # Calculate current value
            current_value = (
                current_price_quote.price * total_quantity
                if current_price_quote.is_valid else None
            )

            portfolio_info = {
                'has_position': True,
                'total_quantity': total_quantity,
                'total_invested': total_invested,
                'average_purchase_price': avg_price,
                'orders_count': len(user_positions),
                'first_purchase_date': (
                    min(order_dates).isoformat() if order_dates else None
                ),
                'last_purchase_date': (
                    max(order_dates).isoformat() if order_dates else None
                ),
                'current_value': current_value
            }

            # Calculate P&L
            if current_value and total_invested > 0:
                portfolio_info['unrealized_pnl'] = current_value - total_invested
                portfolio_info['unrealized_pnl_pct'] = (
                    (portfolio_info['unrealized_pnl'] / total_invested) * 100
                )
            elif current_value:
                # Edge case: current_value exists but total_invested = 0
                portfolio_info['unrealized_pnl'] = 0
                portfolio_info['unrealized_pnl_pct'] = 0

        except Exception as e:
            self.debug_log("Error fetching portfolio data", {
                "isin": isin,
                "user_id": user_id,
                "error": str(e)
            })
            portfolio_info = {'has_position': False}

        return portfolio_info

    def _parse_order_dates(self, orders: List[Dict]) -> List[datetime]:
        """Parse order dates from various formats."""
        dates = []
        for order in orders:
            date_str = order.get('date')
            if not date_str:
                continue

            try:
                if isinstance(date_str, str):
                    # Handle ISO format with timezone
                    date_str = date_str.replace('Z', '+00:00')
                    dates.append(datetime.fromisoformat(date_str))
                else:
                    dates.append(date_str)
            except (ValueError, TypeError):
                continue

        return dates

    def _get_error_response(self, isin: str, error: str) -> Dict[str, Any]:
        """Return a standardized error response."""
        return {
            'isin': isin,
            'error': error,
            'basic_quote': {
                'price': 0.0,
                'source': 'Error',
                'is_valid': False,
                'currency': 'EUR'
            },
            'yahoo_finance': {},
            'justetf': {},
            'portfolio': {'has_position': False},
            'last_updated': datetime.now().isoformat()
        }
