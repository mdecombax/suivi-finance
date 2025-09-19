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
from utils.logger import debug_log


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
        
        @self.app.route("/health")
        def health_check():
            """Health check endpoint for monitoring."""
            return {"status": "ok"}
        
        # API Routes
        @self.app.route("/api/portfolio", methods=["GET", "POST"])
        def portfolio_api():
            """API endpoint for portfolio data and analytics."""
            try:
                account_type = self._get_account_type_from_request()
                portfolio_summary = self.portfolio_service.get_portfolio_summary()
                
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
                        "orders_count": portfolio_summary["orders_count"]
                    }
                })
                
            except Exception as e:
                debug_log("Portfolio API error", {"error": str(e)})
                return jsonify({"error": str(e)}), 500
        
        @self.app.route("/api/orders", methods=["GET", "POST", "DELETE"])
        def orders_api():
            """API endpoint for managing investment orders."""
            try:
                if request.method == "GET":
                    return self._handle_get_orders()
                elif request.method == "POST":
                    return self._handle_create_order()
                elif request.method == "DELETE":
                    return self._handle_delete_order()
                    
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
    
    def _get_account_type_from_request(self) -> str:
        """Extract account type from request, defaulting to 'pea'."""
        if request.method == "POST":
            return request.form.get("account_type", "pea")
        return request.args.get("account_type", "pea")
    
    def _handle_get_orders(self) -> Dict[str, Any]:
        """Handle GET request for orders list."""
        orders = self.portfolio_service.load_orders()
        
        # Sort by date descending (newest first)
        orders.sort(key=lambda o: (o.order_date, o.id), reverse=True)
        
        orders_data = [order.to_dict() for order in orders]
        return jsonify({"success": True, "orders": orders_data})
    
    def _handle_create_order(self) -> Dict[str, Any]:
        """Handle POST request to create a new order."""
        order_data = request.get_json()
        
        # Validate required fields
        required_fields = ['isin', 'quantity', 'unitPrice', 'totalPriceEUR', 'date']
        for field in required_fields:
            if field not in order_data:
                return jsonify({"error": f"Missing field: {field}"}), 400
        
        try:
            new_order = self.portfolio_service.add_order(order_data)
            return jsonify({"success": True, "order_id": new_order.id})
        except Exception as e:
            debug_log("Create order error", {"order_data": order_data, "error": str(e)})
            return jsonify({"error": f"Failed to create order: {str(e)}"}), 400
    
    def _handle_delete_order(self) -> Dict[str, Any]:
        """Handle DELETE request to remove an order."""
        order_id_str = request.args.get('order_id')
        if not order_id_str:
            return jsonify({"error": "Missing order_id parameter"}), 400
        
        try:
            order_id = int(order_id_str)
        except ValueError:
            return jsonify({"error": "Invalid order_id format"}), 400
        
        was_deleted = self.portfolio_service.delete_order(order_id)
        
        if was_deleted:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Order not found"}), 404
    
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
    
    def run(self, host: str = None, port: int = None, debug: bool = True):
        """Start the Flask application."""
        host = host or os.environ.get("HOST", "0.0.0.0")
        
        try:
            port = port or int(os.environ.get("PORT", "5050"))
        except ValueError:
            port = 5050
        
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