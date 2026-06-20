"""
Suivi Finance - Flask application for portfolio tracking and performance analysis.

Simplified architecture with direct Flask routes and consolidated modules:
- database.py: Firebase/Firestore operations and auth middleware
- payments.py: Stripe integration
- models.py: All dataclasses
- services/: Business logic (portfolio, price, projection)
"""

import os
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, g
from flask_cors import CORS

# New consolidated imports
from database import firebase_service, require_auth, get_current_user_id, get_current_user, require_premium, get_user_plan_info
from payments import stripe_service

# Service imports
from services.price_service import PriceService
from services.portfolio_service import PortfolioService
from services.position_service import PositionService
from services import import_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def debug_log(message: str, data: Dict[str, Any] = None):
    """Simple debug logging function."""
    if data:
        logger.info(f"{message}: {data}")
    else:
        logger.info(message)


# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend requests

# Initialize services
price_service = PriceService(debug_logger=debug_log)

orders_file_path = Path(__file__).parent / "orders.json"
portfolio_service = PortfolioService(
    orders_file_path=str(orders_file_path),
    price_service=price_service,
    debug_logger=debug_log
)

position_service = PositionService(
    price_service=price_service,
    firebase_service=firebase_service,
    debug_logger=debug_log
)


# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route("/")
def home_page():
    """Main portfolio dashboard page."""
    return render_template("index.html")

@app.route("/orders")
def orders_management_page():
    """Orders management page."""
    return render_template("orders.html")

@app.route("/import")
def import_orders_page():
    """Page d'import d'ordres assisté par IA (CSV / screenshot / PDF)."""
    return render_template("import.html")

@app.route("/login")
def login_page():
    """Login page."""
    return render_template("login.html")

@app.route("/register")
def register_page():
    """Register page."""
    return render_template("register.html")

@app.route("/objectif")
def objectif_page():
    """Financial objective tracking page."""
    return render_template("objectif.html")

@app.route("/subscription")
def subscription_page():
    """Subscription management page."""
    return render_template("subscription.html")

@app.route("/position/<isin>")
def position_detail(isin):
    """Position detail page."""
    return render_template("position_detail.html", isin=isin)

@app.route("/health")
def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "ok"}

        # API Routes
@app.route("/api/portfolio", methods=["GET", "POST"])
@require_auth
def portfolio_api():
    """API endpoint for portfolio data and analytics (authentification requise)."""
    try:
        user_id = get_current_user_id()
        account_type = _get_account_type_from_request()

                # Récupérer les ordres depuis Firebase pour cet utilisateur
        user_orders = firebase_service.get_user_orders(user_id)

                # Utiliser les ordres Firebase pour les calculs de portefeuille
        portfolio_summary = portfolio_service.get_portfolio_summary(user_orders)

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

@app.route("/api/orders", methods=["GET", "POST", "DELETE"])
@require_auth
def orders_api():
    """API endpoint for managing investment orders (authentification requise)."""
    try:
        user_id = get_current_user_id()

        if request.method == "GET":
            return _handle_get_orders(user_id)
        elif request.method == "POST":
            return _handle_create_order(user_id)
        elif request.method == "DELETE":
            return _handle_delete_order(user_id)

    except Exception as e:
        debug_log("Orders API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500


# ============================================================================
# IMPORT D'ORDRES ASSISTÉ PAR IA
# ============================================================================

@app.route("/api/import/models")
@require_auth
def import_models_api():
    """Registre des modèles disponibles pour l'extraction (pour le sélecteur UI)."""
    return jsonify(import_service.get_registry_public())


@app.route("/api/orders/import/parse", methods=["POST"])
@require_auth
def import_parse_api():
    """Extrait les ordres d'un fichier déposé et calcule des métriques de contrôle."""
    try:
        if "file" not in request.files:
            return jsonify({"error": "Aucun fichier reçu."}), 400

        uploaded = request.files["file"]
        content = uploaded.read()
        if not content:
            return jsonify({"error": "Fichier vide."}), 400

        model_key = request.form.get("model") or None

        try:
            extraction = import_service.parse_orders_from_file(
                filename=uploaded.filename or "document",
                content=content,
                mime_type=uploaded.mimetype or "",
                model_key=model_key,
            )
        except import_service.ImportError_ as fe:
            return jsonify({"error": str(fe)}), 400

        metrics = _compute_import_metrics(extraction["orders"])

        return jsonify({
            "success": True,
            "orders": extraction["orders"],
            "declared_total_eur": extraction["declared_total_eur"],
            "currency_warning": extraction["currency_warning"],
            "model": extraction["model"],
            "metrics": metrics,
        })
    except Exception as e:
        debug_log("Import parse error", {"error": str(e)})
        return jsonify({"error": f"Échec de l'extraction : {str(e)}"}), 500


@app.route("/api/orders/import/confirm", methods=["POST"])
@require_auth
def import_confirm_api():
    """Persiste en masse les ordres édités/validés par l'utilisateur."""
    try:
        user_id = get_current_user_id()
        payload = request.get_json(silent=True) or {}
        orders = payload.get("orders", [])
        if not isinstance(orders, list) or not orders:
            return jsonify({"error": "Aucun ordre à importer."}), 400

        created, skipped, errors = 0, [], []

        for idx, raw in enumerate(orders):
            isin = (raw.get("isin") or "").strip().upper()
            quantity = raw.get("quantity")
            order_date = (raw.get("date") or "").strip()

            # Validation minimale
            if not isin or not price_service.is_valid_isin(isin):
                skipped.append({"line": idx + 1, "reason": f"ISIN invalide ou manquant ({isin or '∅'})"})
                continue
            if not order_date:
                skipped.append({"line": idx + 1, "reason": "Date manquante"})
                continue
            try:
                if quantity is None or float(quantity) <= 0:
                    skipped.append({"line": idx + 1, "reason": "Quantité invalide"})
                    continue
            except (TypeError, ValueError):
                skipped.append({"line": idx + 1, "reason": "Quantité invalide"})
                continue

            order_data = {
                "isin": isin,
                "quantity": float(quantity),
                "date": order_date,
            }
            # Prix unitaire fourni par l'extraction/édition (sinon récupéré par le helper)
            if raw.get("unit_price_eur") not in (None, ""):
                order_data["unitPrice"] = float(raw["unit_price_eur"])
            elif raw.get("unitPrice") not in (None, ""):
                order_data["unitPrice"] = float(raw["unitPrice"])

            try:
                order_data = _build_order_with_price(order_data)
                firebase_service.add_order(user_id, order_data)
                created += 1
            except ValueError as price_err:
                errors.append({"line": idx + 1, "isin": isin, "reason": str(price_err)})
            except Exception as add_err:  # noqa: BLE001
                errors.append({"line": idx + 1, "isin": isin, "reason": str(add_err)})

        return jsonify({"success": True, "created": created, "skipped": skipped, "errors": errors})
    except Exception as e:
        debug_log("Import confirm error", {"error": str(e)})
        return jsonify({"error": f"Échec de l'import : {str(e)}"}), 500


def _compute_import_metrics(orders: list) -> Dict[str, Any]:
    """Métriques de vérification à partir des ordres extraits.

    - total investi (Σ total_eur, sinon unit_price × quantité)
    - valeur actuelle estimée (prix courant × quantité agrégée par ISIN)
    - nombre de positions distinctes
    """
    total_invested = 0.0
    quantities_by_isin: Dict[str, float] = {}

    for o in orders:
        qty = o.get("quantity") or 0
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = 0.0

        total = o.get("total_eur")
        unit = o.get("unit_price_eur")
        if total not in (None, ""):
            try:
                total_invested += float(total)
            except (TypeError, ValueError):
                pass
        elif unit not in (None, "") and qty:
            try:
                total_invested += float(unit) * qty
            except (TypeError, ValueError):
                pass

        isin = (o.get("isin") or "").strip().upper()
        if isin and qty:
            quantities_by_isin[isin] = quantities_by_isin.get(isin, 0.0) + qty

    estimated_value = 0.0
    valued_positions = 0
    for isin, qty in quantities_by_isin.items():
        try:
            quote = price_service.get_current_price(isin)
            if quote.is_valid:
                estimated_value += quote.price * qty
                valued_positions += 1
        except Exception:  # noqa: BLE001
            continue

    return {
        "total_invested_eur": round(total_invested, 2),
        "estimated_value_eur": round(estimated_value, 2) if valued_positions else None,
        "positions_count": len(quantities_by_isin),
        "valued_positions": valued_positions,
        "orders_count": len(orders),
    }


@app.route("/api/price/<ticker_or_isin>")
def current_price_api(ticker_or_isin: str):
    """API endpoint for getting current price of a financial instrument."""
    try:
        price_quote = price_service.get_current_price(ticker_or_isin)
        
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

@app.route("/api/historical_prices/<ticker_or_isin>")
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
        
        price_quote = price_service.get_historical_price(ticker_or_isin, target_date)
        
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

@app.route("/api/history", methods=["GET", "POST"])
def price_history_api():
    """API endpoint for JustETF historical price series."""
    try:
                # Extract parameters from various request sources
        params = _extract_history_parameters()
        
        if not price_service.is_valid_isin(params["isin"]):
            return jsonify({"error": "Invalid ISIN parameter"}), 400
        
        if not params["date_from"] or not params["date_to"]:
            return jsonify({"error": "dateFrom and dateTo required (YYYY-MM-DD)"}), 400
        
        historical_data = price_service._fetch_justetf_historical_data(
            params["isin"], params["date_from"], params["date_to"]
        )
        
        if historical_data is None:
            return jsonify({"error": "Historical data unavailable"}), 502
        
        return jsonify(historical_data)
        
    except Exception as e:
        debug_log("History API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/position/<isin>", methods=["GET"])
@require_auth
def position_detail_api(isin):
    """API endpoint for position details with enriched data."""
    try:
        user_id = get_current_user_id()
        enriched_data = position_service.get_enriched_position_data(isin, user_id)
        return jsonify(enriched_data)
    except Exception as e:
        debug_log("Position detail API error", {"isin": isin, "error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/objectif", methods=["GET", "POST"])
@require_auth
def objectif_api():
    """API endpoint for financial objective: save, load, and compute progress."""
    try:
        user_id = get_current_user_id()

        # Fetch current portfolio data
        user_orders = firebase_service.get_user_orders(user_id)
        if user_orders:
            portfolio_summary = portfolio_service.get_portfolio_summary(user_orders)
        else:
            portfolio_summary = {}

        current_value = float(portfolio_summary.get("current_value") or 0)
        total_invested = float(portfolio_summary.get("total_invested") or 0)
        pl_abs = float(portfolio_summary.get("profit_loss_absolute") or 0)
        pl_pct_raw = portfolio_summary.get("profit_loss_percentage")
        pl_pct = float(pl_pct_raw) if pl_pct_raw is not None else None

        # Extract XIRR safely (performance can be dict or PerformanceMetrics object)
        performance = portfolio_summary.get("performance", {})
        if hasattr(performance, 'to_dict'):
            performance = performance.to_dict()
        xirr_raw = performance.get("annual_return") if isinstance(performance, dict) else None
        xirr = float(xirr_raw) if xirr_raw is not None else None

        # Calculate average monthly investment from order history
        avg_monthly_investment = None
        if user_orders:
            try:
                dates = [datetime.strptime(o["date"], "%Y-%m-%d") for o in user_orders if o.get("date")]
                if dates:
                    first_date = min(dates)
                    months_active = max(1, (datetime.now().year - first_date.year) * 12 + (datetime.now().month - first_date.month))
                    avg_monthly_investment = round(float(total_invested) / months_active, 2)
            except Exception:
                pass

        if request.method == "POST":
            data = request.get_json() or {}
            target_amount = float(data.get("target_amount", 0))
            target_year = int(data.get("target_year", datetime.now().year + 10))
            monthly_contribution = float(data.get("monthly_contribution", 0))

            objective = {
                "target_amount": target_amount,
                "target_year": target_year,
                "monthly_contribution": monthly_contribution,
            }
            firebase_service.save_user_objective(user_id, objective)
        else:
            objective = firebase_service.get_user_objective(user_id)

        progress = None
        if objective:
            target_amount = objective.get("target_amount", 0)
            target_year = objective.get("target_year", datetime.now().year + 10)
            monthly_contribution = objective.get("monthly_contribution", 0)
            current_year = datetime.now().year
            years_remaining = max(0, target_year - current_year)

            # Use XIRR if available, otherwise default to 7%
            rate = (xirr / 100) if xirr and xirr > 0 else 0.07
            monthly_rate = rate / 12
            n_months = years_remaining * 12

            # Future value of current capital
            fv_capital = current_value * ((1 + rate) ** years_remaining)

            # Future value of monthly DCA contributions
            if monthly_rate > 0 and n_months > 0:
                fv_contributions = monthly_contribution * (((1 + monthly_rate) ** n_months - 1) / monthly_rate)
            else:
                fv_contributions = monthly_contribution * n_months

            projected_value = fv_capital + fv_contributions

            # Required monthly contribution to reach the target
            remaining_needed = target_amount - fv_capital
            if remaining_needed <= 0:
                required_monthly = 0.0
            elif monthly_rate > 0 and n_months > 0:
                required_monthly = remaining_needed * monthly_rate / (((1 + monthly_rate) ** n_months) - 1)
            elif n_months > 0:
                required_monthly = remaining_needed / n_months
            else:
                required_monthly = remaining_needed

            progress_pct = min(100.0, (current_value / target_amount * 100)) if target_amount > 0 else 0.0
            on_track = projected_value >= target_amount

            # Monthly chart data (up to target date)
            chart_labels = []
            chart_invested = []   # capital réellement mis de poche
            chart_interests = []  # gains générés (projeté - investi)
            chart_target = []
            step_months = max(1, int(n_months) // 24)
            for m in range(0, int(n_months) + 1, step_months):
                yr = current_year + m / 12
                chart_labels.append(round(yr, 1))
                # Capital investi cumulé = valeur actuelle + apports DCA futurs
                invested_at_m = float(current_value) + float(monthly_contribution) * m
                # Valeur projetée à ce mois
                fvc = float(current_value) * ((1 + monthly_rate) ** m) if monthly_rate > 0 else float(current_value) * ((1 + rate) ** (m / 12))
                if monthly_rate > 0 and m > 0:
                    fvd = float(monthly_contribution) * (((1 + monthly_rate) ** m - 1) / monthly_rate)
                else:
                    fvd = float(monthly_contribution) * m
                projected_at_m = fvc + fvd
                interests_at_m = max(0.0, projected_at_m - invested_at_m)
                chart_invested.append(round(invested_at_m, 2))
                chart_interests.append(round(interests_at_m, 2))
                chart_target.append(float(target_amount))

            # Annual crossover chart: intérêts générés/an vs DCA/an
            annual_dca = float(monthly_contribution) * 12
            crossover_labels = []
            annual_interests_chart = []
            annual_dca_chart = []
            crossover_year = None
            for y in range(0, int(years_remaining) + 1):
                m = y * 12
                fvc = float(current_value) * ((1 + monthly_rate) ** m) if monthly_rate > 0 else float(current_value) * ((1 + rate) ** y)
                if monthly_rate > 0 and m > 0:
                    fvd = float(monthly_contribution) * (((1 + monthly_rate) ** m - 1) / monthly_rate)
                else:
                    fvd = float(monthly_contribution) * m
                portfolio_at_y = fvc + fvd
                interests_this_year = round(portfolio_at_y * rate, 2)
                crossover_labels.append(current_year + y)
                annual_interests_chart.append(interests_this_year)
                annual_dca_chart.append(round(annual_dca, 2))
                if crossover_year is None and interests_this_year >= annual_dca and annual_dca > 0:
                    crossover_year = current_year + y

            progress = {
                "target_amount": float(target_amount),
                "target_year": int(target_year),
                "monthly_contribution": float(monthly_contribution),
                "current_value": float(current_value),
                "xirr": float(xirr) if xirr is not None else None,
                "rate_used": round(float(rate * 100), 2),
                "years_remaining": int(years_remaining),
                "fv_capital": round(float(fv_capital), 2),
                "fv_contributions": round(float(fv_contributions), 2),
                "projected_value": round(float(projected_value), 2),
                "required_monthly": round(float(max(0, required_monthly)), 2),
                "progress_pct": round(float(progress_pct), 1),
                "on_track": bool(on_track),
                "surplus_or_deficit": round(float(projected_value - target_amount), 2),
                "chart": {
                    "labels": chart_labels,
                    "invested": chart_invested,
                    "interests": chart_interests,
                    "target": chart_target,
                },
                "crossover": {
                    "labels": crossover_labels,
                    "annual_interests": annual_interests_chart,
                    "annual_dca": annual_dca_chart,
                    "crossover_year": crossover_year,
                }
            }

        return jsonify({
            "success": True,
            "data": {
                "objective": objective,
                "portfolio": {
                    "current_value": current_value,
                    "xirr": xirr,
                    "avg_monthly_investment": avg_monthly_investment,
                },
                "progress": progress,
            }
        })

    except Exception as e:
        debug_log("Objectif API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500


@app.route("/api/revenu-passif", methods=["POST"])
@require_auth
def revenu_passif_api():
    """Calcule quand l'utilisateur pourra atteindre un revenu mensuel net cible."""
    try:
        user_id = get_current_user_id()
        data = request.get_json() or {}

        target_monthly_net = float(data.get("target_monthly_net", 0))
        monthly_contribution = float(data.get("monthly_contribution", 0))
        account_type = data.get("account_type", "pea")

        if target_monthly_net <= 0:
            return jsonify({"success": False, "error": "Revenu cible invalide"}), 400

        # Récupérer le portefeuille actuel
        user_orders = firebase_service.get_user_orders(user_id)
        portfolio_summary = portfolio_service.get_portfolio_summary(user_orders) if user_orders else {}

        current_value = float(portfolio_summary.get("current_value") or 0)

        performance = portfolio_summary.get("performance", {})
        if hasattr(performance, 'to_dict'):
            performance = performance.to_dict()
        xirr_raw = performance.get("annual_return") if isinstance(performance, dict) else None
        xirr = float(xirr_raw) if xirr_raw is not None else None

        # Taux fiscal selon le régime
        tax_rates = {"pea": 0.175, "cto": 0.30}
        tax_rate = tax_rates.get(account_type, 0.175)

        # Taux de rendement annuel
        rate = (xirr / 100) if xirr and xirr > 0 else 0.07
        monthly_rate = rate / 12

        # Capital requis pour générer le revenu net mensuel cible
        target_monthly_gross = target_monthly_net / (1 - tax_rate)
        target_annual_gross = target_monthly_gross * 12
        required_capital = target_annual_gross / rate

        # Simuler mois par mois pour trouver quand on atteint le capital requis
        months_to_reach = None
        for m in range(1, 1201):  # max 100 ans
            fv = current_value * ((1 + monthly_rate) ** m)
            if monthly_rate > 0:
                fv += monthly_contribution * (((1 + monthly_rate) ** m - 1) / monthly_rate)
            else:
                fv += monthly_contribution * m
            if fv >= required_capital:
                months_to_reach = m
                break

        # Calculs pour l'affichage
        target_year = None
        years_to_reach = None
        if months_to_reach is not None:
            years_to_reach = months_to_reach / 12
            target_year = datetime.now().year + int(months_to_reach // 12)
            remaining_months_in_year = months_to_reach % 12
            if remaining_months_in_year > 6:
                target_year += 1

        progress_pct = min(100.0, (current_value / required_capital * 100)) if required_capital > 0 else 0.0
        tax_per_month = round(target_monthly_gross - target_monthly_net, 2)

        # Données graphique : progression vers le capital requis
        horizon_months = months_to_reach if months_to_reach else min(360, 240)
        chart_step = max(1, int(horizon_months) // 60)
        current_year = datetime.now().year
        chart_labels = []
        chart_invested = []
        chart_interests = []
        chart_target = []

        for m in range(0, int(horizon_months) + 1, chart_step):
            yr = current_year + m / 12
            chart_labels.append(round(yr, 1))
            invested_at_m = current_value + monthly_contribution * m
            fvc = current_value * ((1 + monthly_rate) ** m) if monthly_rate > 0 else current_value
            fvd = monthly_contribution * (((1 + monthly_rate) ** m - 1) / monthly_rate) if monthly_rate > 0 and m > 0 else monthly_contribution * m
            projected_at_m = fvc + fvd
            interests_at_m = max(0.0, projected_at_m - invested_at_m)
            chart_invested.append(round(invested_at_m, 2))
            chart_interests.append(round(interests_at_m, 2))
            chart_target.append(round(required_capital, 2))

        return jsonify({
            "success": True,
            "data": {
                "target_monthly_net": round(target_monthly_net, 2),
                "target_monthly_gross": round(target_monthly_gross, 2),
                "tax_per_month": tax_per_month,
                "tax_rate_pct": round(tax_rate * 100, 1),
                "account_type": account_type,
                "required_capital": round(required_capital, 2),
                "current_value": round(current_value, 2),
                "rate_used": round(rate * 100, 2),
                "xirr": xirr,
                "months_to_reach": months_to_reach,
                "years_to_reach": round(years_to_reach, 1) if years_to_reach else None,
                "target_year": target_year,
                "progress_pct": round(progress_pct, 1),
                "monthly_contribution": monthly_contribution,
                "chart": {
                    "labels": chart_labels,
                    "invested": chart_invested,
                    "interests": chart_interests,
                    "target": chart_target,
                },
            }
        })

    except Exception as e:
        debug_log("Revenu passif API error", {"error": str(e)})
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/portfolio/monthly-values", methods=["GET"])
@require_auth
def monthly_portfolio_values_api():
    """API endpoint for monthly portfolio values (authentification requise).

    Les utilisateurs freemium ont accès aux 3 derniers mois uniquement.
    Les utilisateurs premium ont accès à l'historique complet.
    """
    try:
        user_id = get_current_user_id()

        # Vérifier si l'utilisateur est premium
        is_premium = firebase_service.is_user_premium(user_id)

        # Récupérer les ordres depuis Firebase pour cet utilisateur
        user_orders = firebase_service.get_user_orders(user_id)

        # Calculer les valeurs mensuelles du portefeuille
        monthly_values = portfolio_service.get_monthly_portfolio_values(user_orders)

        # Calculer les métriques avancées (sur toutes les données)
        advanced_metrics = portfolio_service.calculate_advanced_metrics(monthly_values)

        # Pour les utilisateurs freemium, limiter aux 3 derniers mois
        is_limited = False
        total_months_available = len(monthly_values)

        if not is_premium and len(monthly_values) > 3:
            monthly_values = monthly_values[-3:]  # Garder uniquement les 3 derniers mois
            is_limited = True

        result = {
            "success": True,
            "data": monthly_values,
            "advanced_metrics": advanced_metrics.to_dict(),
            "user_id": user_id,
            "total_months": len(monthly_values),
            "is_premium": is_premium,
            "is_limited": is_limited,
            "total_months_available": total_months_available if is_limited else len(monthly_values),
            "freemium_limit_months": 3 if is_limited else None
        }
        return jsonify(result)

    except Exception as e:
        debug_log("Monthly portfolio values API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/position/<isin>/monthly-values", methods=["GET"])
@require_auth
def position_monthly_values_api(isin):
    """API endpoint for monthly position values (authentification requise).

    Les utilisateurs freemium ont accès aux 3 derniers mois uniquement.
    Les utilisateurs premium ont accès à l'historique complet.
    """
    try:
        user_id = get_current_user_id()

        # Vérifier si l'utilisateur est premium
        is_premium = firebase_service.is_user_premium(user_id)

        # Récupérer les ordres depuis Firebase pour cet utilisateur
        user_orders = firebase_service.get_user_orders(user_id)

        # Filtrer les ordres pour cet ISIN spécifique
        position_orders = [order for order in (user_orders or []) if order.get('isin') == isin]

        if not position_orders:
            return jsonify({
                "success": True,
                "data": [],
                "isin": isin,
                "message": "Aucun ordre trouvé pour cette position"
            })

        # Calculer les valeurs mensuelles pour cette position
        monthly_values = portfolio_service.get_monthly_position_values(position_orders, isin)

        # Pour les utilisateurs freemium, limiter aux 3 derniers mois
        is_limited = False
        total_months_available = len(monthly_values)

        if not is_premium and len(monthly_values) > 3:
            monthly_values = monthly_values[-3:]  # Garder uniquement les 3 derniers mois
            is_limited = True

        result = {
            "success": True,
            "data": monthly_values,
            "isin": isin,
            "user_id": user_id,
            "total_months": len(monthly_values),
            "is_premium": is_premium,
            "is_limited": is_limited,
            "total_months_available": total_months_available if is_limited else len(monthly_values),
            "freemium_limit_months": 3 if is_limited else None
        }
        return jsonify(result)

    except Exception as e:
        debug_log("Position monthly values API error", {"error": str(e), "isin": isin})
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/<export_type>", methods=["GET"])
@require_auth
@require_premium
def export_data_api(export_type):
    """API endpoint pour exporter les données (premium uniquement)."""
    try:
        user_id = get_current_user_id()

        # Vérifier le type d'export demandé
        allowed_formats = ['json', 'csv', 'excel']
        if export_type not in allowed_formats:
            return jsonify({"error": "Type d'export non supporté"}), 400

        # Récupérer les données utilisateur
        user_orders = firebase_service.get_user_orders(user_id)
        portfolio_summary = portfolio_service.get_portfolio_summary(user_orders)

        # Préparer les données pour l'export
        export_data = {
            "user_id": user_id,
            "export_date": datetime.now().isoformat(),
            "portfolio": {
                "total_invested": portfolio_summary["total_invested"],
                "current_value": portfolio_summary["current_value"],
                "profit_loss_absolute": portfolio_summary["profit_loss_absolute"],
                "profit_loss_percentage": portfolio_summary["profit_loss_percentage"],
                "orders_count": portfolio_summary["orders_count"]
            },
            "positions": portfolio_summary["positions"],
            "orders": user_orders,
            "plan": "premium"
        }

        if export_type == 'json':
            return jsonify({
                "success": True,
                "data": export_data,
                "format": "json"
            })

        elif export_type == 'csv':
                    # TODO: Implémenter l'export CSV
            return jsonify({
                "success": True,
                "message": "Export CSV sera disponible prochainement",
                "data": export_data
            })

        elif export_type == 'excel':
                    # TODO: Implémenter l'export Excel
            return jsonify({
                "success": True,
                "message": "Export Excel sera disponible prochainement",
                "data": export_data
            })

    except Exception as e:
        debug_log("Export API error", {"export_type": export_type, "error": str(e)})
        return jsonify({"error": str(e)}), 500

        # ========== ROUTES ABONNEMENT ==========

@app.route("/api/subscription", methods=["GET"])
@require_auth
def subscription_info_api():
    """API endpoint pour récupérer les informations d'abonnement (authentification requise)."""
    try:
        user_id = get_current_user_id()
        plan_info = get_user_plan_info()

        return jsonify({
            "success": True,
            "data": plan_info,
            "user_id": user_id
        })

    except Exception as e:
        debug_log("Subscription info API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/subscription/checkout", methods=["POST"])
@require_auth
def create_checkout_session_api():
    """API endpoint pour créer une session de checkout Stripe (authentification requise)."""
    try:
        user_id = get_current_user_id()
        user_info = get_current_user()

        if not user_info or not user_info.get('email'):
            return jsonify({"error": "Email utilisateur requis"}), 400

                # URLs de retour (à adapter selon votre domaine)
        base_url = request.host_url.rstrip('/')
        success_url = f"{base_url}/subscription?success=true"
        cancel_url = f"{base_url}/subscription?canceled=true"

                # Créer la session checkout
        session_data = stripe_service.create_checkout_session(
            user_id=user_id,
            email=user_info['email'],
            success_url=success_url,
            cancel_url=cancel_url,
            trial_days=3  # 3 jours d'essai gratuit
        )

        if not session_data:
            return jsonify({"error": "Impossible de créer la session de paiement"}), 500

        return jsonify({
            "success": True,
            "data": session_data
        })

    except Exception as e:
        debug_log("Checkout session API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/subscription/sync", methods=["POST"])
@require_auth
def sync_subscription_api():
    """Synchronise le statut d'abonnement Stripe vers Firebase."""
    try:
        user_id = get_current_user_id()

                # Récupérer la subscription depuis Firebase
        subscription = firebase_service.get_user_subscription(user_id)

        if not subscription or not subscription.get('stripe_customer_id'):
            return jsonify({
                "success": False,
                "error": "Aucun client Stripe trouvé"
            }), 404

        customer_id = subscription['stripe_customer_id']

                # Récupérer les abonnements depuis Stripe (inclure les annulés)
        import stripe
        subscriptions = stripe.Subscription.list(customer=customer_id, limit=1)

        if subscriptions.data:
            stripe_sub = subscriptions.data[0]

                    # Déterminer le plan
            from datetime import datetime
            plan = 'freemium'

                    # Check if subscription is FULLY cancelled (status = 'canceled')
            if stripe_sub['status'] == 'canceled':
                        # Révoquer l'accès immédiatement
                plan = 'freemium'
                subscription_data = {
                    'plan': 'freemium',
                    'status': 'canceled',
                    'stripe_customer_id': customer_id,
                    'stripe_subscription_id': None,
                    'canceled_at': datetime.now()
                }

                if stripe_sub.get('current_period_end'):
                    subscription_data['current_period_end'] = datetime.fromtimestamp(stripe_sub['current_period_end'])

                firebase_service.update_user_subscription(user_id, subscription_data)

                return jsonify({
                    "success": True,
                    "data": {
                        "plan": "freemium",
                        "status": "canceled",
                        "message": "Abonnement annulé - accès premium désactivé"
                    }
                })

                    # Check if subscription is scheduled for cancellation (cancel_at_period_end)
                    # Don't revoke access - user keeps it until end of paid period
            if stripe_sub.get('cancel_at_period_end', False):
                plan = 'premium'
                if stripe_sub.get('trial_end') and stripe_sub['trial_end'] > datetime.now().timestamp():
                    plan = 'trial'

                subscription_data = {
                    'plan': plan,
                    'status': 'active',
                    'cancel_at_period_end': True,
                    'stripe_customer_id': customer_id,
                    'stripe_subscription_id': stripe_sub['id'],
                    'current_period_start': datetime.fromtimestamp(stripe_sub['current_period_start']),
                    'current_period_end': datetime.fromtimestamp(stripe_sub['current_period_end'])
                }

                if stripe_sub.get('trial_end'):
                    subscription_data['trial_end'] = datetime.fromtimestamp(stripe_sub['trial_end'])

                firebase_service.update_user_subscription(user_id, subscription_data)

                return jsonify({
                    "success": True,
                    "data": {
                        "plan": plan,
                        "status": "active",
                        "cancel_at_period_end": True,
                        "message": f"Abonnement actif jusqu'au {subscription_data['current_period_end']}"
                    }
                })

                    # Gérer les statuts 'active' et 'trialing' (seulement si pas annulé)
            if stripe_sub['status'] in ['active', 'trialing']:
                if stripe_sub.get('trial_end') and stripe_sub['trial_end'] > datetime.now().timestamp():
                    plan = 'trial'
                else:
                    plan = 'premium'

                    # Mettre à jour Firebase
            subscription_data = {
                'plan': plan,
                'status': stripe_sub['status'],
                'stripe_customer_id': customer_id,
                'stripe_subscription_id': stripe_sub['id']
            }

                    # Ajouter les champs optionnels s'ils existent
            if stripe_sub.get('current_period_start'):
                subscription_data['current_period_start'] = datetime.fromtimestamp(stripe_sub['current_period_start'])
            if stripe_sub.get('current_period_end'):
                subscription_data['current_period_end'] = datetime.fromtimestamp(stripe_sub['current_period_end'])
            if stripe_sub.get('trial_end'):
                subscription_data['trial_end'] = datetime.fromtimestamp(stripe_sub['trial_end'])

            firebase_service.update_user_subscription(user_id, subscription_data)

            return jsonify({
                "success": True,
                "data": {
                    "plan": plan,
                    "status": stripe_sub['status']
                }
            })
        else:
                    # Aucun abonnement trouvé - réinitialiser à freemium
            subscription_data = {
                'plan': 'freemium',
                'status': 'none',
                'stripe_customer_id': customer_id,
                'stripe_subscription_id': None
            }
            firebase_service.update_user_subscription(user_id, subscription_data)

            return jsonify({
                "success": True,
                "data": {
                    "plan": "freemium",
                    "status": "none"
                }
            })

    except Exception as e:
        debug_log("Subscription sync error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/subscription/portal", methods=["POST"])
@require_auth
def customer_portal_api():
    """API endpoint pour accéder au portail client Stripe (authentification requise)."""
    try:
        user_id = get_current_user_id()

                # URL de retour
        base_url = request.host_url.rstrip('/')
        return_url = f"{base_url}/subscription"

                # Créer la session portail
        portal_url = stripe_service.create_customer_portal_session(
            user_id=user_id,
            return_url=return_url
        )

        if not portal_url:
            return jsonify({"error": "Impossible d'accéder au portail client"}), 500

        return jsonify({
            "success": True,
            "data": {"url": portal_url}
        })

    except Exception as e:
        debug_log("Customer portal API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/subscription/trial", methods=["POST"])
@require_auth
def start_trial_api():
    """API endpoint pour démarrer un essai gratuit (authentification requise)."""
    try:
        user_id = get_current_user_id()

                # Vérifier si l'utilisateur peut démarrer un essai
        subscription = firebase_service.get_user_subscription(user_id)
        if subscription and subscription.get('plan') != 'freemium':
            return jsonify({
                "error": "Essai non disponible",
                "message": "Vous avez déjà utilisé votre essai gratuit ou avez un abonnement actif."
            }), 400

                # Démarrer l'essai
        success = firebase_service.start_user_trial(user_id)

        if success:
            return jsonify({
                "success": True,
                "message": "Essai gratuit de 3 jours activé !",
                "data": get_user_plan_info()
            })
        else:
            return jsonify({"error": "Impossible de démarrer l'essai"}), 500

    except Exception as e:
        debug_log("Start trial API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/subscription/cancel", methods=["POST"])
@require_auth
def cancel_subscription_api():
    """API endpoint pour annuler un abonnement (authentification requise)."""
    try:
        user_id = get_current_user_id()

                # Annuler l'abonnement (logique automatique : immédiat si essai, fin de période si payé)
        success = stripe_service.cancel_subscription(user_id)

        if success:
            return jsonify({
                "success": True,
                "message": "Abonnement annulé."
            })
        else:
            return jsonify({"error": "Impossible d'annuler l'abonnement"}), 500

    except Exception as e:
        debug_log("Cancel subscription API error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

@app.route("/api/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Webhook endpoint pour Stripe."""
    try:
        payload = request.get_data()
        sig_header = request.headers.get('Stripe-Signature')

        if not sig_header:
            return jsonify({"error": "Missing Stripe signature"}), 400

                # Traiter le webhook
        success = stripe_service.handle_webhook(payload, sig_header)

        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Webhook processing failed"}), 400

    except Exception as e:
        debug_log("Stripe webhook error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500

def _get_account_type_from_request() -> str:
    """Extract account type from request, defaulting to 'pea'."""
    if request.method == "POST":
        return request.form.get("account_type", "pea")
    return request.args.get("account_type", "pea")


def _handle_get_orders(user_id: str) -> Dict[str, Any]:
    """Handle GET request for orders list (par utilisateur)."""
    # Récupérer les ordres Firebase pour cet utilisateur
    firebase_orders = firebase_service.get_user_orders(user_id)

    # Si pas d'ordres Firebase, utiliser le système local comme fallback
    if not firebase_orders:
        orders = portfolio_service.load_orders()
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


def _build_order_with_price(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Enrichit un ordre avec le prix unitaire et le total EUR si absents.

    Utilise le prix fourni s'il existe ; sinon récupère le prix historique à la
    date de l'ordre, avec repli sur le prix courant. Lève ValueError si le prix
    reste introuvable. Partagé par la création unitaire et l'import en masse.
    """
    def _missing(key):
        return key not in order_data or order_data.get(key) in (None, "")

    if _missing('unitPrice') or _missing('totalPriceEUR'):
        unit = order_data.get('unitPrice')
        if unit in (None, ""):
            order_date = datetime.strptime(order_data['date'], '%Y-%m-%d').date()
            price_quote = price_service.get_historical_price(order_data['isin'], order_date)
            if not price_quote.is_valid:
                price_quote = price_service.get_current_price(order_data['isin'])
            if not price_quote.is_valid:
                raise ValueError(f"Prix introuvable pour l'ISIN {order_data['isin']}")
            unit = price_quote.price

        unit = float(unit)
        order_data['unitPrice'] = unit
        order_data['totalPriceEUR'] = unit * float(order_data['quantity'])

    return order_data


def _handle_create_order(user_id: str) -> Dict[str, Any]:
    """Handle POST request to create a new order (par utilisateur)."""
    order_data = request.get_json()

    # Validate required fields (unitPrice and totalPriceEUR are optional, will be calculated)
    required_fields = ['isin', 'quantity', 'date']
    for field in required_fields:
        if field not in order_data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    try:
        # Enrichissement prix + calcul du total (helper partagé)
        try:
            order_data = _build_order_with_price(order_data)
        except ValueError as price_err:
            return jsonify({"error": str(price_err)}), 400

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


def _handle_delete_order(user_id: str) -> Dict[str, Any]:
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


def _extract_history_parameters() -> Dict[str, str]:
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


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError:
        port = 8000
    
    logger.info(f"Starting application on {host}:{port}")
    app.run(host=host, port=port, debug=True)
