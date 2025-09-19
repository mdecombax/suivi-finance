from flask import Flask, render_template, request
from flask import jsonify
from flask import redirect, url_for, send_file
from flask_cors import CORS
import os
import re
import requests
import yfinance as yf
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional
import json
from pathlib import Path
import numpy as np
from scipy.optimize import fsolve

# Services Firebase supprimés - utilisation du stockage local simple


app = Flask(__name__)
CORS(app)  # Activer CORS pour les requêtes frontend


def debug_log(message: str, extra: Optional[Dict[str, Any]] = None):
    """Emit log messages only in debug mode, with optional structured context."""
    if app.debug:
        if extra:
            try:
                app.logger.info("%s | %s", message, extra)
            except Exception:
                app.logger.info(message)
        else:
            app.logger.info(message)


def get_ticker_currency(ticker: yf.Ticker) -> str | None:
    try:
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info and "currency" in fast_info and fast_info["currency"]:
            return str(fast_info["currency"]).upper()
    except Exception:
        pass
    try:
        info = ticker.info or {}
        cur = info.get("currency")
        if cur:
            return str(cur).upper()
    except Exception:
        pass
    return None


def get_fx_rate(from_ccy: str, to_ccy: str, date: Optional[date] = None):
    """Get FX rate to convert from_ccy to to_ccy using Yahoo FX pairs (e.g., GBPEUR=X).

    If date is provided, returns rate on or before that date; otherwise latest.
    """
    if not from_ccy or not to_ccy or from_ccy.upper() == to_ccy.upper():
        return 1.0, None
    pair = f"{from_ccy.upper()}{to_ccy.upper()}=X"
    try:
        fx = yf.Ticker(pair)
        if date is None:
            debug_log("yfinance FX latest", {"pair": pair})
            # Try fast path
            rate = None
            try:
                fast_info = getattr(fx, "fast_info", None)
                if fast_info:
                    for key in ("lastPrice", "regularMarketPrice", "last_price", "last_trade_price"):
                        if key in fast_info and fast_info[key] is not None:
                            rate = float(fast_info[key])
                            break
            except Exception:
                pass
            if rate is None:
                hist = fx.history(period="1d", interval="1m")
                if not hist.empty:
                    rate = float(hist["Close"].iloc[-1])
            if rate is None:
                # daily fallback
                hist = fx.history(period="5d", interval="1d")
                if not hist.empty:
                    rate = float(hist["Close"].iloc[-1])
            if rate is None:
                return None, "Taux FX indisponible"
            return rate, None
        # Historical
        start = date - timedelta(days=10)
        end = date + timedelta(days=1)
        debug_log("yfinance FX history", {"pair": pair, "start": start.isoformat(), "end": end.isoformat()})
        hist = fx.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1d")
        if not hist.empty:
            chosen_date = None
            chosen_rate = None
            hist = hist.sort_index()
            for idx, row in hist.iterrows():
                idx_date = idx.date()
                if idx_date <= date:
                    if not chosen_date or idx_date > chosen_date:
                        chosen_date = idx_date
                        chosen_rate = float(row.get("Close")) if row.get("Close") is not None else None
            if chosen_rate is not None:
                return chosen_rate, None
        return None, "Taux FX introuvable pour la date"
    except Exception as e:
        return None, f"Erreur FX: {str(e)}"


def get_current_price(ticker_symbol: str):
    if not ticker_symbol:
        return None, None, None, "Veuillez saisir un ticker."

    try:
        debug_log("get_current_price: start", {"ticker": ticker_symbol})
        ticker = yf.Ticker(ticker_symbol)

        # Prefer fast_info when available (yfinance >= 0.2.x)
        last_price = None
        source = None
        venue = None
        try:
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info:
                # Keys may vary depending on instrument; try common ones
                for key in ("lastPrice", "regularMarketPrice", "last_price", "last_trade_price"):
                    if key in fast_info and fast_info[key] is not None:
                        last_price = float(fast_info[key])
                        source = "Yahoo Finance"
                        break
        except Exception:
            pass

        # Fallback to info
        if last_price is None:
            try:
                info = ticker.info or {}
                for key in ("currentPrice", "regularMarketPrice", "regularMarketPreviousClose"):
                    if key in info and info[key] is not None:
                        last_price = float(info[key])
                        source = "Yahoo Finance"
                        break
            except Exception:
                pass

        # Final fallback via recent history
        if last_price is None:
            debug_log("yfinance.history request", {"ticker": ticker_symbol, "period": "1d", "interval": "1m"})
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                last_price = float(hist["Close"].iloc[-1])
                source = "Yahoo Finance"

        # If still not found, try JustETF when input looks like an ISIN
        if last_price is None and looks_like_isin(ticker_symbol):
            debug_log("JustETF fallback for ISIN", {"isin": ticker_symbol})
            je_price, je_venue, je_err = get_price_from_justetf(ticker_symbol, currency="EUR", locale="fr")
            if je_err is None and je_price is not None:
                last_price = je_price
                venue = je_venue
                source = "JustETF"

        if last_price is None:
            return None, None, None, "Prix introuvable pour ce ticker/ISIN."

        # Convert to EUR if Yahoo source and non-EUR currency
        if source == "Yahoo Finance":
            ccy = get_ticker_currency(ticker)
            debug_log("Ticker currency", {"ticker": ticker_symbol, "currency": ccy})
            if ccy and ccy.upper() != "EUR":
                rate, fx_err = get_fx_rate(ccy.upper(), "EUR")
                if rate is None:
                    return None, None, None, fx_err or "Conversion EUR indisponible"
                last_price = float(last_price) * float(rate)
                source = "Yahoo Finance (EUR)"

        debug_log("get_current_price: end", {"ticker": ticker_symbol, "price": last_price, "source": source, "venue": venue})
        return last_price, source, venue, None
    except Exception as e:
        debug_log("get_current_price: error", {"ticker": ticker_symbol, "error": str(e)})
        return None, None, None, f"Erreur lors de la récupération: {str(e)}"


ISIN_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def looks_like_isin(value: str) -> bool:
    if not value:
        return False
    candidate = value.strip().upper()
    return bool(ISIN_REGEX.match(candidate))


def get_price_from_justetf(isin: str, currency: str = "EUR", locale: str = "fr"):
    try:
        isin_clean = (isin or "").strip().upper()
        url = f"https://www.justetf.com/api/etfs/{isin_clean}/quote"
        params = {"currency": currency, "locale": locale}
        debug_log("HTTP GET JustETF quote", {"url": url, "params": params})
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.justetf.com",
            "Referer": f"https://www.justetf.com/fr/etf-profile.html?isin={isin_clean}",
            "Connection": "keep-alive",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        debug_log("HTTP JustETF response", {"status_code": getattr(resp, "status_code", None)})
        resp.raise_for_status()
        data = resp.json()
        latest = data.get("latestQuote", {})
        raw_val = latest.get("raw")
        if raw_val is None:
            return None, None, "Réponse JustETF invalide."
        venue = data.get("quoteTradingVenue")
        return float(raw_val), venue, None
    except Exception as e:
        debug_log("HTTP JustETF quote error", {"isin": isin, "error": str(e)})
        return None, None, f"JustETF indisponible: {str(e)}"


def parse_date(date_str: str):
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def get_price_on_date(ticker_symbol: str, date_str: str):
    """Return closing price for the given date (or nearest previous market day).

    Supports both Yahoo tickers and ISIN (via JustETF) heuristically.
    """
    if not ticker_symbol:
        return None, None, None, None, "Veuillez saisir un ticker ou ISIN."

    d = parse_date(date_str or "")
    if not d:
        return None, None, None, None, "Date invalide. Utilisez AAAA-MM-JJ."

    # If it looks like an ISIN, use JustETF historical endpoint
    if looks_like_isin(ticker_symbol):
        # Query a small window up to the requested date to handle weekends/holidays
        date_from = (d - timedelta(days=10)).strftime("%Y-%m-%d")
        date_to = d.strftime("%Y-%m-%d")
        debug_log("get_price_on_date: ISIN path", {"isin": ticker_symbol, "date_from": date_from, "date_to": date_to})
        data, err = get_history_from_justetf(ticker_symbol, date_from, date_to)
        if err:
            # Fallback to latest quote if history endpoint fails
            debug_log("get_price_on_date: ISIN history failed, fallback to quote", {"isin": ticker_symbol, "error": err})
            price, venue, err2 = get_price_from_justetf(ticker_symbol)
            if err2 is None and price is not None:
                return price, d.isoformat(), "JustETF", venue, None
            return None, None, None, None, err

        # Find the last value on or before requested date
        series = data.get("series") or []
        chosen = None
        for item in series:
            try:
                item_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
            except Exception:
                continue
            if item_date <= d:
                if not chosen or item_date > chosen[0]:
                    chosen = (item_date, item["value"]) 
        if chosen:
            return float(chosen[1]), chosen[0].isoformat(), data.get("source") or "JustETF", None, None

        # As a last resort, use latestQuote if date matches
        latest_val = data.get("latestQuote")
        latest_date = data.get("latestQuoteDate")
        try:
            if latest_val is not None and latest_date:
                latest_d = datetime.strptime(latest_date[:10], "%Y-%m-%d").date()
                if latest_d <= d:
                    return float(latest_val), latest_d.isoformat(), data.get("source") or "JustETF", None, None
        except Exception:
            pass

        return None, None, None, None, "Prix introuvable pour cette date."

    # Otherwise, use yfinance for ticker symbols
    try:
        ticker = yf.Ticker(ticker_symbol)
        start = d - timedelta(days=10)
        end = d + timedelta(days=1)
        debug_log("yfinance.history request", {"ticker": ticker_symbol, "start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d"), "interval": "1d"})
        hist = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), interval="1d")
        if not hist.empty:
            # Choose the last available date on or before d
            hist = hist.sort_index()
            chosen_date = None
            chosen_price = None
            for idx, row in hist.iterrows():
                idx_date = idx.date()
                if idx_date <= d:
                    if not chosen_date or idx_date > chosen_date:
                        chosen_date = idx_date
                        chosen_price = float(row.get("Close")) if row.get("Close") is not None else None
            if chosen_price is not None:
                # Convert to EUR if needed using FX rate on chosen_date
                ccy = get_ticker_currency(ticker)
                if ccy and ccy.upper() != "EUR":
                    rate, fx_err = get_fx_rate(ccy.upper(), "EUR", chosen_date)
                    if rate is None:
                        return None, None, None, None, fx_err or "Conversion EUR indisponible"
                    chosen_price = float(chosen_price) * float(rate)
                    src = "Yahoo Finance (EUR)"
                else:
                    src = "Yahoo Finance"
                debug_log("yfinance.history result", {"ticker": ticker_symbol, "chosen_date": chosen_date.isoformat(), "price": chosen_price, "currency": "EUR" if ccy and ccy.upper() != "EUR" else ccy})
                return chosen_price, chosen_date.isoformat(), src, None, None
        return None, None, None, None, "Prix introuvable pour cette date."
    except Exception as e:
        debug_log("get_price_on_date: error", {"ticker": ticker_symbol, "date": date_str, "error": str(e)})
        return None, None, None, None, f"Erreur lors de la récupération: {str(e)}"


def get_history_from_justetf(
    isin: str,
    date_from: str,
    date_to: str,
    currency: str = "EUR",
    locale: str = "fr",
):
    """Fetch historical series from JustETF performance-chart endpoint.

    date_from/date_to: YYYY-MM-DD
    Returns: dict with keys: latestQuote, latestQuoteDate, series: [{date, value}]
    """
    try:
        isin_clean = (isin or "").strip().upper()
        url = f"https://www.justetf.com/api/etfs/{isin_clean}/performance-chart"
        params = {
            "locale": locale,
            "currency": currency,
            "valuesType": "MARKET_VALUE",
            "reduceData": "false",
            "includeDividends": "false",
            "features": "DIVIDENDS",
            "dateFrom": date_from,
            "dateTo": date_to,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.justetf.com",
            "Referer": f"https://www.justetf.com/fr/etf-profile.html?isin={isin.strip().upper()}",
            "Connection": "keep-alive",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        debug_log("HTTP GET JustETF performance-chart", {"url": url, "params": params})
        debug_log("HTTP JustETF response", {"status_code": getattr(resp, "status_code", None)})
        resp.raise_for_status()
        data = resp.json()
        # Normalize series to simple list of {date, value}
        normalized_series = []
        for item in data.get("series", []) or []:
            d = item.get("date")
            val_obj = item.get("value", {}) or {}
            raw_val = val_obj.get("raw")
            if d is not None and raw_val is not None:
                try:
                    normalized_series.append({"date": d, "value": float(raw_val)})
                except Exception:
                    continue

        latest = data.get("latestQuote", {}) or {}
        latest_raw = latest.get("raw")
        latest_val = float(latest_raw) if latest_raw is not None else None
        result = {
            "latestQuote": latest_val,
            "latestQuoteDate": data.get("latestQuoteDate"),
            "series": normalized_series,
            "source": "JustETF",
        }
        debug_log("JustETF performance parsed", {"points": len(normalized_series), "latestQuote": latest_val})
        return result, None
    except Exception as e:
        debug_log("HTTP JustETF performance error", {"isin": isin, "error": str(e)})
        return None, f"JustETF history indisponible: {str(e)}"



# ----------------------------
# Orders simple JSON storage
# ----------------------------

ORDERS_FILE = Path(__file__).parent / "orders.json"


def _load_orders() -> list[dict[str, Any]]:
    try:
        if not ORDERS_FILE.exists():
            return []
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        debug_log("load_orders error", {"error": str(e)})
        return []


def _save_orders(orders: list[dict[str, Any]]):
    try:
        with open(ORDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
    except Exception as e:
        debug_log("save_orders error", {"error": str(e)})


def calculate_portfolio_performance(orders_list: list[dict[str, Any]], current_value: float) -> dict[str, Any]:
    """Calculate portfolio performance using XIRR (Money-Weighted Return)."""
    if not orders_list or current_value <= 0:
        return {
            "annual_return": None,
            "total_return": None,
            "method": "XIRR (Money-Weighted Return)",
            "description": "Taux de rendement interne tenant compte des flux de trésorerie",
            "calculation_details": [],
            "error": "Données insuffisantes"
        }
    
    try:
        # Prepare cash flows: negative for investments (outflows), positive for current value (inflow)
        cash_flows = []
        dates = []
        
        # Add investment outflows (negative values)
        for order in orders_list:
            cash_flows.append(-float(order.get("totalPriceEUR", 0)))
            dates.append(datetime.strptime(order.get("date", ""), "%Y-%m-%d").date())
        
        # Add current value as final inflow (positive value)
        cash_flows.append(current_value)
        dates.append(date.today())
        
        # Convert dates to years since first investment
        first_date = min(dates)
        years_since_start = [(d - first_date).days / 365.25 for d in dates]
        
        # XIRR calculation using Newton-Raphson method
        def xirr_equation(rate):
            return sum(cf / (1 + rate) ** years for cf, years in zip(cash_flows, years_since_start))
        
        # Try to find the rate that makes NPV = 0
        try:
            # Start with a reasonable guess
            initial_guess = 0.05  # 5% annual return
            annual_rate = fsolve(xirr_equation, initial_guess)[0]
            
            # Validate the result
            if abs(xirr_equation(annual_rate)) < 1e-6 and -0.99 < annual_rate < 10:  # Reasonable bounds
                annual_return_pct = annual_rate * 100
                total_return_pct = ((current_value / sum(-cf for cf in cash_flows[:-1])) - 1) * 100
                
                # Prepare calculation details
                calculation_details = []
                for i, (cf, d) in enumerate(zip(cash_flows[:-1], dates[:-1])):
                    calculation_details.append({
                        "date": d.isoformat(),
                        "amount": cf,
                        "description": f"Investissement {i+1}",
                        "years_from_start": years_since_start[i]
                    })
                
                calculation_details.append({
                    "date": dates[-1].isoformat(),
                    "amount": cash_flows[-1],
                    "description": "Valeur actuelle",
                    "years_from_start": years_since_start[-1]
                })
                
                return {
                    "annual_return": annual_return_pct,
                    "total_return": total_return_pct,
                    "method": "XIRR (Money-Weighted Return)",
                    "description": "Taux de rendement interne tenant compte des flux de trésorerie",
                    "calculation_details": calculation_details,
                    "error": None
                }
            else:
                raise ValueError("Invalid XIRR result")
                
        except Exception:
            # Fallback to simple annualized return
            total_days = (dates[-1] - dates[0]).days
            years = total_days / 365.25
            if years > 0:
                total_return_pct = ((current_value / sum(-cf for cf in cash_flows[:-1])) - 1) * 100
                annual_return_pct = ((current_value / sum(-cf for cf in cash_flows[:-1])) ** (1/years) - 1) * 100
                
                return {
                    "annual_return": annual_return_pct,
                    "total_return": total_return_pct,
                    "method": "Rendement annualisé simple",
                    "description": "Calcul simplifié basé sur la durée totale",
                    "calculation_details": [],
                    "error": "XIRR non calculable, méthode simplifiée utilisée"
                }
            else:
                raise ValueError("Invalid time period")
                
    except Exception as e:
        return {
            "annual_return": None,
            "total_return": None,
            "method": "XIRR (Money-Weighted Return)",
            "description": "Taux de rendement interne tenant compte des flux de trésorerie",
            "calculation_details": [],
            "error": f"Erreur de calcul: {str(e)}"
        }


def calculate_fiscal_scenarios(total_invested: float, current_value: float, pl_abs: float) -> dict[str, Any]:
    """Calculate fiscal scenarios for CTO (30% flat tax) and PEA (17.5% CSG/CRDS)."""
    scenarios = {
        "cto": {
            "name": "CTO (Flat Tax 30%)",
            "description": "Compte-titres ordinaire avec imposition à 30%",
            "tax_rate": 0.30,
            "net_value": None,
            "tax_amount": None,
            "icon": "🏦",
            "color": "cto"
        },
        "pea": {
            "name": "PEA (17.5% CSG/CRDS)",
            "description": "Plan d'épargne en actions après 5 ans",
            "tax_rate": 0.175,
            "net_value": None,
            "tax_amount": None,
            "icon": "📈",
            "color": "pea"
        }
    }
    
    if pl_abs is not None and total_invested > 0:
        for scenario in scenarios.values():
            if pl_abs >= 0:
                # Plus-value : imposition sur la plus-value
                scenario["tax_amount"] = pl_abs * scenario["tax_rate"]
                scenario["net_value"] = current_value - scenario["tax_amount"]
            else:
                # Moins-value : pas d'imposition, mais pas de récupération d'impôt non plus
                scenario["tax_amount"] = 0.0
                scenario["net_value"] = current_value
    
    return scenarios


@app.route("/")
def index():
    """Page d'accueil principale - Affichage direct du portefeuille"""
    return render_template("index.html")

@app.route("/api/portfolio", methods=["GET", "POST"])
def portfolio():
    """API pour récupérer les données du portefeuille"""
    try:
        account_type = request.form.get("account_type", "pea") if request.method == "POST" else "pea"
        
        # Récupérer les ordres depuis le fichier local
        orders_list = _load_orders()
        
        # Compute aggregates and portfolio metrics
        total_invested = sum((o.get("totalPriceEUR") or 0.0) for o in orders_list)
        
        # Group quantities and invested by ISIN
        isin_to_qty: dict[str, float] = {}
        isin_to_invested: dict[str, float] = {}
        for o in orders_list:
            isin = (o.get("isin") or "").strip().upper()
            qty = float(o.get("quantity") or 0.0)
            invested = float(o.get("totalPriceEUR") or 0.0)
            if not isin:
                continue
            isin_to_qty[isin] = isin_to_qty.get(isin, 0.0) + qty
            isin_to_invested[isin] = isin_to_invested.get(isin, 0.0) + invested

        # Fetch latest prices per ISIN in EUR
        current_value = 0.0
        latest_prices: dict[str, float] = {}
        for isin, qty in isin_to_qty.items():
            try:
                latest_price, venue, err = get_price_from_justetf(isin, currency="EUR", locale="fr")
                if err is None and latest_price is not None:
                    latest_prices[isin] = float(latest_price)
                    current_value += float(latest_price) * float(qty)
            except Exception:
                continue

        pl_abs = current_value - total_invested
        pl_pct = (pl_abs / total_invested * 100.0) if total_invested > 0 else None

        # Calculate portfolio performance
        performance_data = calculate_portfolio_performance(orders_list, current_value)
        
        # Calculate fiscal scenarios
        fiscal_scenarios = calculate_fiscal_scenarios(total_invested, current_value, pl_abs)
        
        # Get selected account type scenario
        selected_scenario = fiscal_scenarios.get(account_type, fiscal_scenarios["pea"])

        # Build per-ISIN aggregates
        aggregated_positions: list[dict[str, Any]] = []
        for isin, qty in sorted(isin_to_qty.items()):
            invested = float(isin_to_invested.get(isin, 0.0))
            avg_unit_price = (invested / qty) if qty > 0 else None
            cur_price = latest_prices.get(isin)
            cur_value = (cur_price * qty) if (cur_price is not None) else None
            pl_isin_abs = (cur_value - invested) if (cur_value is not None) else None
            pl_isin_pct = ((pl_isin_abs / invested) * 100.0) if (pl_isin_abs is not None and invested > 0) else None
            aggregated_positions.append({
                "isin": isin,
                "quantity": qty,
                "invested": invested,
                "avgUnitPrice": avg_unit_price,
                "currentPrice": cur_price,
                "currentValue": cur_value,
                "plAbs": pl_isin_abs,
                "plPct": pl_isin_pct,
            })

        return jsonify({
            "success": True,
            "data": {
                "total_invested": total_invested,
                "current_value": current_value,
                "pl_abs": pl_abs,
                "pl_pct": pl_pct,
                "aggregated_positions": aggregated_positions,
                "performance_data": performance_data,
                "fiscal_scenarios": fiscal_scenarios,
                "selected_scenario": selected_scenario,
                "account_type": account_type,
                "orders_count": len(orders_list)
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500





@app.route("/api/history", methods=["GET", "POST"])
def api_history():
    # Accept params via query (GET), JSON body, or form (POST)
    payload = {}
    if request.is_json:
        try:
            payload = request.get_json(silent=True) or {}
        except Exception:
            payload = {}
    isin = ((request.args.get("isin") if request.method == "GET" else None) 
            or payload.get("isin") 
            or request.form.get("isin") 
            or "").strip()
    date_from = ((request.args.get("dateFrom") if request.method == "GET" else None)
                 or payload.get("dateFrom") 
                 or request.form.get("dateFrom") 
                 or "").strip()
    date_to = ((request.args.get("dateTo") if request.method == "GET" else None)
               or payload.get("dateTo") 
               or request.form.get("dateTo") 
               or "").strip()

    if not looks_like_isin(isin):
        return jsonify({"error": "Paramètre isin invalide"}), 400
    if not date_from or not date_to:
        return jsonify({"error": "dateFrom et dateTo requis (YYYY-MM-DD)"}), 400

    data, err = get_history_from_justetf(isin, date_from, date_to)
    if err:
        return jsonify({"error": err}), 502
    return jsonify(data)


@app.route("/orders")
def orders():
    """Page de gestion des ordres"""
    return render_template("orders.html")

@app.route("/api/orders", methods=["GET", "POST", "DELETE"])
def api_orders():
    """API pour gérer les ordres"""
    try:
        if request.method == "GET":
            # Récupérer tous les ordres et les trier par date décroissante
            orders_list = _load_orders()
            orders_list.sort(key=lambda o: (o.get("date") or "", o.get("id") or 0), reverse=True)
            return jsonify({"success": True, "orders": orders_list})
        
        elif request.method == "POST":
            # Ajouter un nouvel ordre
            order_data = request.get_json()
            
            # Validation des données
            required_fields = ['isin', 'quantity', 'unitPrice', 'totalPriceEUR', 'date']
            for field in required_fields:
                if field not in order_data:
                    return jsonify({"error": f"Champ manquant: {field}"}), 400
            
            # Charger les ordres existants
            orders_list = _load_orders()
            
            # Ajouter un ID unique
            order_data['id'] = int(datetime.utcnow().timestamp() * 1000)
            
            # Ajouter l'ordre
            orders_list.append(order_data)
            
            # Trier par date décroissante (plus récent en premier)
            orders_list.sort(key=lambda o: (o.get("date") or "", o.get("id") or 0), reverse=True)
            
            # Sauvegarder
            _save_orders(orders_list)
            
            return jsonify({"success": True, "order_id": order_data['id']})
        
        elif request.method == "DELETE":
            # Supprimer un ordre
            order_id = request.args.get('order_id')
            if not order_id:
                return jsonify({"error": "ID d'ordre manquant"}), 400
            
            # Charger les ordres
            orders_list = _load_orders()
            
            # Supprimer l'ordre
            before_count = len(orders_list)
            orders_list = [o for o in orders_list if str(o.get('id', '')) != str(order_id)]
            
            if len(orders_list) < before_count:
                _save_orders(orders_list)
                return jsonify({"success": True})
            else:
                return jsonify({"error": "Ordre introuvable"}), 404
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/orders_old", methods=["GET", "POST"])
def orders_old():
    error = None
    success = None
    orders_list = _load_orders()
    account_type = request.form.get("account_type", "pea")  # Default to PEA

    if request.method == "POST":
        action = (request.form.get("action") or "").strip().lower()
        if action == "delete":
            try:
                oid = int(request.form.get("id") or "0")
            except Exception:
                oid = 0
            if oid:
                before = len(orders_list)
                orders_list = [o for o in orders_list if int(o.get("id") or 0) != oid]
                if len(orders_list) < before:
                    _save_orders(orders_list)
                    return redirect(url_for("orders", deleted="1"))
                else:
                    error = "Ordre introuvable."
            else:
                error = "Identifiant invalide."
        else:
            isin = (request.form.get("isin") or "").strip().upper()
            order_date = (request.form.get("date") or "").strip()
            qty_raw = (request.form.get("quantity") or "").strip()

            if not isin or not looks_like_isin(isin):
                error = "ISIN invalide."
            elif not order_date or not parse_date(order_date):
                error = "Date invalide (format AAAA-MM-JJ)."
            else:
                try:
                    quantity = float(qty_raw.replace(",", ".")) if qty_raw else 0.0
                except Exception:
                    quantity = None
                if quantity is None or quantity <= 0:
                    error = "Quantité invalide (nombre > 0)."

            if not error:
                price, price_date, source, venue, price_err = get_price_on_date(isin, order_date)
                if price_err:
                    error = price_err
                elif price is None:
                    error = "Prix introuvable pour cette date."
                else:
                    unit_price_eur = float(price)
                    total_price_eur = unit_price_eur * float(quantity)
                    new_order = {
                        "id": int(datetime.utcnow().timestamp() * 1000),
                        "date": price_date or order_date,
                        "requestedDate": order_date,
                        "isin": isin,
                        "quantity": float(quantity),
                        "unitPriceEUR": unit_price_eur,
                        "totalPriceEUR": total_price_eur,
                        "priceSource": source,
                        "venue": venue,
                    }
                    orders_list.append(new_order)
                    # Sort by date asc then id
                    try:
                        orders_list.sort(key=lambda o: (o.get("date") or "", o.get("id") or 0))
                    except Exception:
                        pass
                    _save_orders(orders_list)
                    return redirect(url_for("orders", added="1"))

    # Handle success messages via query params (after redirect)
    if request.method == "GET":
        if request.args.get("added") == "1":
            success = "Ordre ajouté."
        elif request.args.get("deleted") == "1":
            success = "Ordre supprimé."

    # Compute aggregates and portfolio metrics
    total_invested = sum((o.get("totalPriceEUR") or 0.0) for o in orders_list)
    # Group quantities and invested by ISIN
    isin_to_qty: dict[str, float] = {}
    isin_to_invested: dict[str, float] = {}
    for o in orders_list:
        isin = (o.get("isin") or "").strip().upper()
        qty = float(o.get("quantity") or 0.0)
        invested = float(o.get("totalPriceEUR") or 0.0)
        if not isin:
            continue
        isin_to_qty[isin] = isin_to_qty.get(isin, 0.0) + qty
        isin_to_invested[isin] = isin_to_invested.get(isin, 0.0) + invested

    # Fetch latest prices per ISIN in EUR
    current_value = 0.0
    latest_prices: dict[str, float] = {}
    for isin, qty in isin_to_qty.items():
        try:
            latest_price, venue, err = get_price_from_justetf(isin, currency="EUR", locale="fr")
            if err is None and latest_price is not None:
                latest_prices[isin] = float(latest_price)
                current_value += float(latest_price) * float(qty)
        except Exception:
            continue

    pl_abs = current_value - total_invested
    pl_pct = (pl_abs / total_invested * 100.0) if total_invested > 0 else None

    # Calculate fiscal scenarios
    fiscal_scenarios = calculate_fiscal_scenarios(total_invested, current_value, pl_abs)
    
    # Get selected account type scenario
    selected_scenario = fiscal_scenarios.get(account_type, fiscal_scenarios["pea"])
    
    # Calculate portfolio performance
    performance_data = calculate_portfolio_performance(orders_list, current_value)

    # Build per-ISIN aggregates
    aggregated_positions: list[dict[str, Any]] = []
    for isin, qty in sorted(isin_to_qty.items()):
        invested = float(isin_to_invested.get(isin, 0.0))
        avg_unit_price = (invested / qty) if qty > 0 else None
        cur_price = latest_prices.get(isin)
        cur_value = (cur_price * qty) if (cur_price is not None) else None
        pl_isin_abs = (cur_value - invested) if (cur_value is not None) else None
        pl_isin_pct = ((pl_isin_abs / invested) * 100.0) if (pl_isin_abs is not None and invested > 0) else None
        aggregated_positions.append({
            "isin": isin,
            "quantity": qty,
            "invested": invested,
            "avgUnitPrice": avg_unit_price,
            "currentPrice": cur_price,
            "currentValue": cur_value,
            "plAbs": pl_isin_abs,
            "plPct": pl_isin_pct,
        })

    return render_template(
        "orders.html",
        error=error,
        success=success,
        orders=orders_list,
        total_invested=total_invested,
        current_value=current_value,
        pl_abs=pl_abs,
        pl_pct=pl_pct,
        aggregated_positions=aggregated_positions,
        fiscal_scenarios=fiscal_scenarios,
        selected_scenario=selected_scenario,
        account_type=account_type,
        performance_data=performance_data,
    )


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("PORT", "5050"))
    except ValueError:
        port = 5050

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.run(host=host, port=port, debug=True)


