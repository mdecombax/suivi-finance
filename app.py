"""
Suivi Finance - Flask application for portfolio tracking and performance analysis.

This refactored version uses a clean service-oriented architecture with:
- Clear separation of concerns
- Descriptive naming conventions  
- Modular service classes
- Type-safe data models
- Comprehensive error handling
"""

import os
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS

from services.price_service import PriceService
from services.portfolio_service import PortfolioService
from services.firebase_service import firebase_service
from services.projection_service import ProjectionService, ProjectionParams
from utils.logger import debug_log
from utils.auth_middleware import require_auth, get_current_user_id, is_user_authenticated


class FinancialPortfolioApp:
    """Main application class for the financial portfolio tracker."""
    
    def __init__(self):
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for frontend requests
        
        # Initialize services
        self.price_service = PriceService(debug_logger=debug_log)

        orders_file_path = Path(__file__).parent / "orders.json"
        self.portfolio_service = PortfolioService(
            orders_file_path=str(orders_file_path),
            price_service=self.price_service,
            debug_logger=debug_log
        )

        self.projection_service = ProjectionService(debug_logger=debug_log)
        
        # Register routes
        self._register_routes()
    
    def _register_routes(self):
        """Register all application routes."""
        
        @self.app.route("/")
        def home_page():
            """Main portfolio dashboard page."""
            return render_template("index.html")
        
        @self.app.route("/orders")
        def orders_management_page():
            """Orders management page."""
            return render_template("orders.html")

        @self.app.route("/login")
        def login_page():
            """Login page."""
            return render_template("login.html")

        @self.app.route("/register")
        def register_page():
            """Register page."""
            return render_template("register.html")

        @self.app.route("/projections")
        def projections_page():
            """Financial projections page."""
            return render_template("projections.html")

        @self.app.route("/position/<isin>")
        def position_detail(isin):
            """Position detail page."""
            return render_template("position_detail.html", isin=isin)
        
        @self.app.route("/health")
        def health_check():
            """Health check endpoint for monitoring."""
            return {"status": "ok"}
        
        # API Routes
        @self.app.route("/api/portfolio", methods=["GET", "POST"])
        @require_auth
        def portfolio_api():
            """API endpoint for portfolio data and analytics (authentification requise)."""
            try:
                user_id = get_current_user_id()
                account_type = self._get_account_type_from_request()

                # Récupérer les ordres depuis Firebase pour cet utilisateur
                user_orders = firebase_service.get_user_orders(user_id)

                # Utiliser les ordres Firebase pour les calculs de portefeuille
                portfolio_summary = self.portfolio_service.get_portfolio_summary(user_orders)

                # Add account type specific data
                fiscal_scenarios = portfolio_summary.get("fiscal_scenarios", {})
                selected_scenario = fiscal_scenarios.get(account_type, fiscal_scenarios.get("pea", {}))

                return jsonify({
                    "success": True,
                    "data": {
                        "total_invested": portfolio_summary["total_invested"],
                        "current_value": portfolio_summary["current_value"],
                        "pl_abs": portfolio_summary["profit_loss_absolute"],
                        "pl_pct": portfolio_summary["profit_loss_percentage"],
                        "aggregated_positions": portfolio_summary["positions"],
                        "performance_data": portfolio_summary["performance"],
                        "fiscal_scenarios": portfolio_summary["fiscal_scenarios"],
                        "selected_scenario": selected_scenario,
                        "account_type": account_type,
                        "orders_count": portfolio_summary["orders_count"],
                        "user_id": user_id,
                        "firebase_orders_count": len(user_orders)
                    }
                })

            except Exception as e:
                debug_log("Portfolio API error", {"error": str(e)})
                return jsonify({"error": str(e)}), 500
        
        @self.app.route("/api/orders", methods=["GET", "POST", "DELETE"])
        @require_auth
        def orders_api():
            """API endpoint for managing investment orders (authentification requise)."""
            try:
                user_id = get_current_user_id()

                if request.method == "GET":
                    return self._handle_get_orders(user_id)
                elif request.method == "POST":
                    return self._handle_create_order(user_id)
                elif request.method == "DELETE":
                    return self._handle_delete_order(user_id)

            except Exception as e:
                debug_log("Orders API error", {"error": str(e)})
                return jsonify({"error": str(e)}), 500
        
        @self.app.route("/api/price/<ticker_or_isin>")
        def current_price_api(ticker_or_isin: str):
            """API endpoint for getting current price of a financial instrument."""
            try:
                price_quote = self.price_service.get_current_price(ticker_or_isin)
                
                if price_quote.is_valid:
                    return jsonify({
                        "success": True,
                        "price": price_quote.price,
                        "source": price_quote.source,
                        "venue": price_quote.venue,
                        "currency": price_quote.currency
                    })
                else:
                    return jsonify({
                        "success": False,
                        "error": price_quote.error_message
                    }), 404
                    
            except Exception as e:
                debug_log("Price API error", {"ticker": ticker_or_isin, "error": str(e)})
                return jsonify({"error": str(e)}), 500
        
        @self.app.route("/api/historical_prices/<ticker_or_isin>")
        def historical_prices_api(ticker_or_isin: str):
            """API endpoint for getting historical prices."""
            try:
                target_date_str = request.args.get("date")
                if not target_date_str:
                    return jsonify({"error": "Date parameter required (YYYY-MM-DD)"}), 400
                
                try:
                    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
                except ValueError:
                    return jsonify({"error": "Invalid date format (use YYYY-MM-DD)"}), 400
                
                price_quote = self.price_service.get_historical_price(ticker_or_isin, target_date)
                
                if price_quote.is_valid:
                    return jsonify({
                        "success": True,
                        "price": price_quote.price,
                        "date": price_quote.quote_date.isoformat() if price_quote.quote_date else None,
                        "source": price_quote.source,
                        "venue": price_quote.venue,
                        "currency": price_quote.currency
                    })
                else:
                    return jsonify({
                        "success": False,
                        "error": price_quote.error_message
                    }), 404
                    
            except Exception as e:
                debug_log("Historical price API error", {
                    "ticker": ticker_or_isin,
                    "error": str(e)
                })
                return jsonify({"error": str(e)}), 500
        
        @self.app.route("/api/history", methods=["GET", "POST"])
        def price_history_api():
            """API endpoint for JustETF historical price series."""
            try:
                # Extract parameters from various request sources
                params = self._extract_history_parameters()
                
                if not self.price_service.is_valid_isin(params["isin"]):
                    return jsonify({"error": "Invalid ISIN parameter"}), 400
                
                if not params["date_from"] or not params["date_to"]:
                    return jsonify({"error": "dateFrom and dateTo required (YYYY-MM-DD)"}), 400
                
                historical_data = self.price_service._fetch_justetf_historical_data(
                    params["isin"], params["date_from"], params["date_to"]
                )
                
                if historical_data is None:
                    return jsonify({"error": "Historical data unavailable"}), 502
                
                return jsonify(historical_data)
                
            except Exception as e:
                debug_log("History API error", {"error": str(e)})
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/position/<isin>", methods=["GET"])
        def position_detail_api(isin):
            """API endpoint for position details with enriched data."""
            try:
                # Récupérer les données enrichies pour cette position
                enriched_data = self._get_enriched_position_data(isin)
                return jsonify(enriched_data)
            except Exception as e:
                debug_log("Position detail API error", {"isin": isin, "error": str(e)})
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/projections", methods=["GET", "POST"])
        @require_auth
        def projections_api():
            """API endpoint for financial projections with scenario analysis (authentification requise)."""
            try:
                # Get current user and portfolio value
                user_id = get_current_user_id()
                current_value = 0

                # Get current portfolio value from user's data
                try:
                    user_orders = firebase_service.get_user_orders(user_id)
                    if user_orders:
                        portfolio_summary = self.portfolio_service.get_portfolio_summary(user_orders)
                        current_value = portfolio_summary.get("current_value", 0)
                    else:
                        current_value = 10000  # Default if no orders
                except Exception as e:
                    debug_log("Error getting portfolio value for projections", {"user_id": user_id, "error": str(e)})
                    current_value = 10000  # Default 10k EUR

                if request.method == "GET":
                    # Return default projections
                    params = ProjectionParams(
                        current_value=current_value,
                        monthly_contribution=500,  # Default 500 EUR/month
                        time_horizon_years=10,     # Default 10 years
                        annual_fees_rate=0.0075    # Default 0.75% fees
                    )

                    projections_summary = self.projection_service.get_projection_summary(params)
                    return jsonify({"success": True, "data": projections_summary})

                elif request.method == "POST":
                    # Custom projections with user parameters
                    data = request.get_json() or {}

                    # Validate parameters
                    validation_error = self.projection_service.validate_projection_params(data)
                    if validation_error:
                        return jsonify({"error": validation_error}), 400

                    # Extract parameters with fallbacks
                    params = ProjectionParams(
                        current_value=float(data.get("current_value", current_value)),
                        monthly_contribution=float(data.get("monthly_contribution", 500)),
                        time_horizon_years=int(data.get("time_horizon_years", 10)),
                        annual_fees_rate=float(data.get("annual_fees_rate", 0.0075))
                    )

                    projections_summary = self.projection_service.get_projection_summary(params)
                    return jsonify({"success": True, "data": projections_summary})

            except Exception as e:
                debug_log("Projections API error", {"error": str(e)})
                return jsonify({"error": str(e)}), 500
    
    def _get_account_type_from_request(self) -> str:
        """Extract account type from request, defaulting to 'pea'."""
        if request.method == "POST":
            return request.form.get("account_type", "pea")
        return request.args.get("account_type", "pea")
    
    def _handle_get_orders(self, user_id: str) -> Dict[str, Any]:
        """Handle GET request for orders list (par utilisateur)."""
        # Récupérer les ordres Firebase pour cet utilisateur
        firebase_orders = firebase_service.get_user_orders(user_id)

        # Si pas d'ordres Firebase, utiliser le système local comme fallback
        if not firebase_orders:
            orders = self.portfolio_service.load_orders()
            orders.sort(key=lambda o: (o.order_date, o.id), reverse=True)
            orders_data = [order.to_dict() for order in orders]
        else:
            # Trier par date décroissante
            firebase_orders.sort(key=lambda o: o.get('date', ''), reverse=True)

            # Convertir le format Firebase vers le format attendu par le frontend
            orders_data = []
            for order in firebase_orders:
                # Mapper les champs pour compatibilité avec le frontend
                formatted_order = {
                    'id': order.get('id'),
                    'isin': order.get('isin'),
                    'quantity': order.get('quantity'),
                    'date': order.get('date'),
                    'unitPriceEUR': order.get('unitPrice'),  # Frontend attend unitPriceEUR
                    'totalPriceEUR': order.get('totalPriceEUR'),
                    # Champs supplémentaires pour compatibilité
                    'unitPrice': order.get('unitPrice'),
                    'createdAt': order.get('createdAt'),
                    'updatedAt': order.get('updatedAt')
                }
                orders_data.append(formatted_order)

        return jsonify({
            "success": True,
            "orders": orders_data,
            "source": "firebase" if firebase_orders else "local",
            "user_id": user_id
        })
    
    def _handle_create_order(self, user_id: str) -> Dict[str, Any]:
        """Handle POST request to create a new order (par utilisateur)."""
        order_data = request.get_json()

        # Validate required fields (unitPrice and totalPriceEUR are optional, will be calculated)
        required_fields = ['isin', 'quantity', 'date']
        for field in required_fields:
            if field not in order_data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        try:
            # If unitPrice or totalPriceEUR are missing, fetch price automatically
            if 'unitPrice' not in order_data or 'totalPriceEUR' not in order_data:
                from datetime import datetime

                # Parse the date
                order_date = datetime.strptime(order_data['date'], '%Y-%m-%d').date()

                # Fetch price for the given date
                price_quote = self.price_service.get_historical_price(order_data['isin'], order_date)

                if not price_quote.is_valid:
                    # Try current price as fallback
                    price_quote = self.price_service.get_current_price(order_data['isin'])

                if not price_quote.is_valid:
                    return jsonify({"error": f"Unable to fetch price for ISIN {order_data['isin']}"}), 400

                # Calculate missing fields
                order_data['unitPrice'] = price_quote.price
                order_data['totalPriceEUR'] = price_quote.price * float(order_data['quantity'])

            # Ajouter l'ordre à Firebase pour cet utilisateur
            order_id = firebase_service.add_order(user_id, order_data)
            return jsonify({
                "success": True,
                "order_id": order_id,
                "user_id": user_id,
                "source": "firebase"
            })
        except Exception as e:
            debug_log("Create order error", {"order_data": order_data, "error": str(e)})
            return jsonify({"error": f"Failed to create order: {str(e)}"}), 400
    
    def _handle_delete_order(self, user_id: str) -> Dict[str, Any]:
        """Handle DELETE request to remove an order (par utilisateur)."""
        order_id_str = request.args.get('order_id')
        if not order_id_str:
            return jsonify({"error": "Missing order_id parameter"}), 400

        try:
            # Supprimer l'ordre de Firebase pour cet utilisateur
            was_deleted = firebase_service.delete_order(user_id, order_id_str)

            if was_deleted:
                return jsonify({
                    "success": True,
                    "user_id": user_id,
                    "source": "firebase"
                })
            else:
                return jsonify({"error": "Order not found"}), 404

        except Exception as e:
            debug_log("Delete order error", {"order_id": order_id_str, "error": str(e)})
            return jsonify({"error": f"Failed to delete order: {str(e)}"}), 400
    
    def _extract_history_parameters(self) -> Dict[str, str]:
        """Extract history API parameters from request."""
        # Support both query parameters (GET) and JSON/form body (POST)
        payload = {}
        if request.is_json:
            try:
                payload = request.get_json(silent=True) or {}
            except Exception:
                payload = {}
        
        isin = (
            (request.args.get("isin") if request.method == "GET" else None) or
            payload.get("isin") or
            request.form.get("isin", "")
        ).strip()
        
        date_from = (
            (request.args.get("dateFrom") if request.method == "GET" else None) or
            payload.get("dateFrom") or
            request.form.get("dateFrom", "")
        ).strip()
        
        date_to = (
            (request.args.get("dateTo") if request.method == "GET" else None) or
            payload.get("dateTo") or
            request.form.get("dateTo", "")
        ).strip()
        
        return {
            "isin": isin,
            "date_from": date_from,
            "date_to": date_to
        }
    
    def _get_enriched_position_data(self, isin: str) -> Dict[str, Any]:
        """Get enriched data for a specific position including name, portfolio info, and technical data."""
        import yfinance as yf
        import requests
        from datetime import datetime, timedelta

        try:
            # Récupérer les données de base
            current_price_quote = self.price_service.get_current_price(isin)

            # Récupérer les informations détaillées via Yahoo Finance
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

                # Calculs historiques
                hist_1y = ticker.history(period='1y')
                if not hist_1y.empty:
                    current_price = hist_1y['Close'].iloc[-1]
                    sma_50 = hist_1y['Close'].rolling(50).mean().iloc[-1] if len(hist_1y) > 50 else None
                    sma_200 = hist_1y['Close'].rolling(200).mean().iloc[-1] if len(hist_1y) > 200 else None

                    yahoo_info.update({
                        'sma_50': float(sma_50) if sma_50 is not None else None,
                        'sma_200': float(sma_200) if sma_200 is not None else None,
                        'current_price_yahoo': float(current_price)
                    })

            except Exception as e:
                debug_log("Error fetching Yahoo data", {"isin": isin, "error": str(e)})

            # Récupérer les données de portefeuille utilisateur
            portfolio_info = {}
            try:
                orders = self.portfolio_service.load_orders()
                user_positions = [order for order in orders if order.isin == isin]

                if user_positions:
                    total_quantity = sum(order.quantity for order in user_positions)
                    total_invested = sum(order.total_price_eur for order in user_positions)
                    avg_price = total_invested / total_quantity if total_quantity > 0 else 0

                    portfolio_info = {
                        'has_position': True,
                        'total_quantity': total_quantity,
                        'total_invested': total_invested,
                        'average_purchase_price': avg_price,
                        'orders_count': len(user_positions),
                        'first_purchase_date': min(order.order_date for order in user_positions).isoformat(),
                        'last_purchase_date': max(order.order_date for order in user_positions).isoformat(),
                        'current_value': current_price_quote.price * total_quantity if current_price_quote.is_valid else None
                    }

                    if portfolio_info['current_value']:
                        portfolio_info['unrealized_pnl'] = portfolio_info['current_value'] - total_invested
                        portfolio_info['unrealized_pnl_pct'] = (portfolio_info['unrealized_pnl'] / total_invested) * 100
                else:
                    portfolio_info = {'has_position': False}

            except Exception as e:
                debug_log("Error fetching portfolio data", {"isin": isin, "error": str(e)})
                portfolio_info = {'has_position': False}

            # Récupérer des données JustETF enrichies
            justetf_data = {}
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15',
                    'Accept': 'application/json',
                    'Referer': f'https://www.justetf.com/fr/etf-profile.html?isin={isin}'
                }

                # Quote avec plus de détails
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
                debug_log("Error fetching JustETF data", {"isin": isin, "error": str(e)})

            # Combiner toutes les données
            enriched_data = {
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

            return enriched_data

        except Exception as e:
            debug_log("Error getting enriched position data", {"isin": isin, "error": str(e)})
            return {
                'isin': isin,
                'error': str(e),
                'basic_quote': {
                    'price': 0.0,
                    'source': 'Error',
                    'is_valid': False,
                    'currency': 'EUR'
                },
                'portfolio': {'has_position': False}
            }

    def run(self, host: str = None, port: int = None, debug: bool = True):
        """Start the Flask application."""
        host = host or os.environ.get("HOST", "0.0.0.0")
        
        try:
            port = port or int(os.environ.get("PORT", "8000"))
        except ValueError:
            port = 8000
        
        debug_log("Starting application", {
            "host": host,
            "port": port,
            "debug": debug
        })
        
        self.app.run(host=host, port=port, debug=debug)


def create_app() -> Flask:
    """Application factory function."""
    portfolio_app = FinancialPortfolioApp()
    return portfolio_app.app


if __name__ == "__main__":
    app_instance = FinancialPortfolioApp()
    app_instance.run()