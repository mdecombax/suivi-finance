"""
Service for portfolio management operations including performance calculations and data aggregation.
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from scipy.optimize import fsolve

from models.portfolio import (
    InvestmentOrder, PositionSummary, PerformanceMetrics, FiscalScenario
)
from services.price_service import PriceService


class PortfolioService:
    """Service for managing portfolio data and calculations."""
    
    def __init__(self, orders_file_path: str, price_service: PriceService, debug_logger=None):
        self.orders_file = Path(orders_file_path)
        self.price_service = price_service
        self.logger = debug_logger
    
    def _log(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log debug information if logger is available."""
        if self.logger:
            self.logger(message, extra)
    
    def load_orders(self) -> List[InvestmentOrder]:
        """Load all investment orders from the data file."""
        try:
            if not self.orders_file.exists():
                return []
            
            with open(self.orders_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                
            if not isinstance(raw_data, list):
                return []
            
            orders = []
            for item in raw_data:
                try:
                    order = InvestmentOrder.from_dict(item)
                    orders.append(order)
                except Exception as e:
                    self._log("Failed to parse order", {"item": item, "error": str(e)})
                    continue
            
            return orders
            
        except Exception as e:
            self._log("Failed to load orders", {"error": str(e)})
            return []
    
    def save_orders(self, orders: List[InvestmentOrder]) -> None:
        """Save investment orders to the data file."""
        try:
            orders_data = [order.to_dict() for order in orders]
            
            with open(self.orders_file, "w", encoding="utf-8") as f:
                json.dump(orders_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            self._log("Failed to save orders", {"error": str(e)})
    
    def add_order(self, order_data: Dict[str, Any]) -> InvestmentOrder:
        """Add a new investment order."""
        # Generate unique ID
        order_data['id'] = int(datetime.utcnow().timestamp() * 1000)
        
        # Create order object
        new_order = InvestmentOrder.from_dict(order_data)
        
        # Load existing orders, add new one, and save
        orders = self.load_orders()
        orders.append(new_order)
        
        # Sort by date descending (newest first)
        orders.sort(key=lambda o: (o.order_date, o.id), reverse=True)
        
        self.save_orders(orders)
        return new_order
    
    def delete_order(self, order_id: int) -> bool:
        """Delete an order by ID. Returns True if order was found and deleted."""
        orders = self.load_orders()
        initial_count = len(orders)
        
        orders = [order for order in orders if order.id != order_id]
        
        if len(orders) < initial_count:
            self.save_orders(orders)
            return True
        
        return False
    
    def get_portfolio_summary(self, orders_data: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get complete portfolio summary including positions, performance, and fiscal scenarios."""
        if orders_data is not None:
            # Convert Firebase orders data to InvestmentOrder objects
            orders = []
            for order_dict in orders_data:
                try:
                    # Convert Firebase format to InvestmentOrder format
                    converted_order = {
                        'id': order_dict.get('id'),
                        'isin': order_dict.get('isin'),
                        'quantity': order_dict.get('quantity'),
                        'date': order_dict.get('date'),
                        'unitPrice': order_dict.get('unitPrice'),
                        'totalPriceEUR': order_dict.get('totalPriceEUR'),
                        'type': order_dict.get('type', 'buy')  # Default to 'buy'
                    }
                    order = InvestmentOrder.from_dict(converted_order)
                    orders.append(order)
                except Exception as e:
                    self._log("Failed to convert Firebase order", {"order": order_dict, "error": str(e)})
                    continue
        else:
            orders = self.load_orders()

        if not orders:
            return {
                "total_invested": 0.0,
                "current_value": 0.0,
                "profit_loss_absolute": 0.0,
                "profit_loss_percentage": None,
                "positions": [],
                "performance": PerformanceMetrics(
                    annual_return_percentage=None,
                    total_return_percentage=None,
                    calculation_method="XIRR",
                    description="Insufficient data",
                    calculation_details=[],
                    error_message="No orders available"
                ),
                "fiscal_scenarios": {},
                "orders_count": 0
            }
        
        # Calculate aggregated positions
        positions = self._calculate_position_summaries(orders)
        
        # Calculate totals
        total_invested = sum(order.total_price_eur for order in orders)
        current_value = sum(pos.current_value or 0.0 for pos in positions)
        profit_loss_absolute = current_value - total_invested
        profit_loss_percentage = (
            (profit_loss_absolute / total_invested * 100.0) 
            if total_invested > 0 else None
        )
        
        # Calculate performance metrics
        performance = self.calculate_portfolio_performance(orders, current_value)
        
        # Calculate fiscal scenarios
        fiscal_scenarios = self.calculate_fiscal_scenarios(
            total_invested, current_value, profit_loss_absolute
        )
        
        return {
            "total_invested": total_invested,
            "current_value": current_value,
            "profit_loss_absolute": profit_loss_absolute,
            "profit_loss_percentage": profit_loss_percentage,
            "positions": [pos.to_dict() for pos in positions],
            "performance": performance.to_dict(),
            "fiscal_scenarios": {k: v.to_dict() for k, v in fiscal_scenarios.items()},
            "orders_count": len(orders)
        }
    
    def _calculate_position_summaries(self, orders: List[InvestmentOrder]) -> List[PositionSummary]:
        """Calculate aggregated position summaries by ISIN."""
        # Group orders by ISIN
        isin_groups: Dict[str, List[InvestmentOrder]] = {}
        for order in orders:
            if order.isin not in isin_groups:
                isin_groups[order.isin] = []
            isin_groups[order.isin].append(order)
        
        positions = []
        for isin, isin_orders in isin_groups.items():
            # Calculate aggregated values
            total_quantity = sum(order.quantity for order in isin_orders)
            total_invested = sum(order.total_price_eur for order in isin_orders)
            average_unit_price = total_invested / total_quantity if total_quantity > 0 else 0.0
            
            # Get current price
            current_price_quote = self.price_service.get_current_price(isin)
            current_price = current_price_quote.price if current_price_quote.is_valid else None
            
            # Calculate current value and P&L
            current_value = None
            profit_loss_absolute = None
            profit_loss_percentage = None
            
            if current_price is not None and current_price > 0:
                current_value = current_price * total_quantity
                profit_loss_absolute = current_value - total_invested
                profit_loss_percentage = (
                    (profit_loss_absolute / total_invested * 100.0)
                    if total_invested > 0 else None
                )
            
            position = PositionSummary(
                isin=isin,
                quantity=total_quantity,
                total_invested=total_invested,
                average_unit_price=average_unit_price,
                current_price=current_price,
                current_value=current_value,
                profit_loss_absolute=profit_loss_absolute,
                profit_loss_percentage=profit_loss_percentage
            )
            
            positions.append(position)
        
        # Sort by ISIN for consistent ordering
        positions.sort(key=lambda p: p.isin)
        return positions
    
    def calculate_portfolio_performance(
        self, 
        orders: List[InvestmentOrder], 
        current_value: float
    ) -> PerformanceMetrics:
        """Calculate portfolio performance using XIRR (Money-Weighted Return)."""
        if not orders or current_value <= 0:
            return PerformanceMetrics(
                annual_return_percentage=None,
                total_return_percentage=None,
                calculation_method="XIRR (Money-Weighted Return)",
                description="Internal rate of return accounting for cash flows",
                calculation_details=[],
                error_message="Insufficient data"
            )
        
        try:
            # Prepare cash flows: negative for investments (outflows), positive for current value (inflow)
            cash_flows = []
            dates = []
            
            # Add investment outflows (negative values)
            for order in orders:
                cash_flows.append(-order.total_price_eur)
                dates.append(order.order_date)
            
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
                            "description": f"Investment {i+1}",
                            "years_from_start": years_since_start[i]
                        })
                    
                    calculation_details.append({
                        "date": dates[-1].isoformat(),
                        "amount": cash_flows[-1],
                        "description": "Current value",
                        "years_from_start": years_since_start[-1]
                    })
                    
                    return PerformanceMetrics(
                        annual_return_percentage=annual_return_pct,
                        total_return_percentage=total_return_pct,
                        calculation_method="XIRR (Money-Weighted Return)",
                        description="Internal rate of return accounting for cash flows",
                        calculation_details=calculation_details,
                        error_message=None
                    )
                else:
                    raise ValueError("Invalid XIRR result")
                    
            except Exception:
                # Fallback to simple annualized return
                total_days = (dates[-1] - dates[0]).days
                years = total_days / 365.25
                if years > 0:
                    total_return_pct = ((current_value / sum(-cf for cf in cash_flows[:-1])) - 1) * 100
                    annual_return_pct = ((current_value / sum(-cf for cf in cash_flows[:-1])) ** (1/years) - 1) * 100
                    
                    return PerformanceMetrics(
                        annual_return_percentage=annual_return_pct,
                        total_return_percentage=total_return_pct,
                        calculation_method="Simple Annualized Return",
                        description="Simplified calculation based on total period",
                        calculation_details=[],
                        error_message="XIRR calculation failed, simplified method used"
                    )
                else:
                    raise ValueError("Invalid time period")
                    
        except Exception as e:
            return PerformanceMetrics(
                annual_return_percentage=None,
                total_return_percentage=None,
                calculation_method="XIRR (Money-Weighted Return)",
                description="Internal rate of return accounting for cash flows",
                calculation_details=[],
                error_message=f"Calculation error: {str(e)}"
            )
    
    def calculate_fiscal_scenarios(
        self, 
        total_invested: float, 
        current_value: float, 
        profit_loss_absolute: float
    ) -> Dict[str, FiscalScenario]:
        """Calculate fiscal scenarios for CTO (30% flat tax) and PEA (17.5% CSG/CRDS)."""
        scenarios = {
            "cto": FiscalScenario(
                name="CTO (Flat Tax 30%)",
                description="Ordinary securities account with 30% taxation",
                tax_rate=0.30,
                net_value=None,
                tax_amount=None,
                icon="🏦",
                color="cto"
            ),
            "pea": FiscalScenario(
                name="PEA (17.5% CSG/CRDS)",
                description="Equity savings plan after 5 years",
                tax_rate=0.175,
                net_value=None,
                tax_amount=None,
                icon="📈",
                color="pea"
            )
        }
        
        if profit_loss_absolute is not None and total_invested > 0:
            for scenario in scenarios.values():
                if profit_loss_absolute >= 0:
                    # Capital gain: tax on the gain
                    scenario.tax_amount = profit_loss_absolute * scenario.tax_rate
                    scenario.net_value = current_value - scenario.tax_amount
                else:
                    # Capital loss: no taxation, but no tax recovery either
                    scenario.tax_amount = 0.0
                    scenario.net_value = current_value
        
        return scenarios

    def get_monthly_portfolio_values(self, orders_data: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Calculate portfolio value at the beginning of each month since first order."""
        if orders_data is not None:
            # Convert Firebase orders data to InvestmentOrder objects
            orders = []
            for order_dict in orders_data:
                try:
                    converted_order = {
                        'id': order_dict.get('id'),
                        'isin': order_dict.get('isin'),
                        'quantity': order_dict.get('quantity'),
                        'date': order_dict.get('date'),
                        'unitPrice': order_dict.get('unitPrice'),
                        'totalPriceEUR': order_dict.get('totalPriceEUR'),
                        'type': order_dict.get('type', 'buy')
                    }
                    order = InvestmentOrder.from_dict(converted_order)
                    orders.append(order)
                except Exception as e:
                    self._log("Failed to convert Firebase order for monthly values", {"order": order_dict, "error": str(e)})
                    continue
        else:
            orders = self.load_orders()

        if not orders:
            return []

        # Sort orders by date (ascending - oldest first)
        orders.sort(key=lambda o: o.order_date)

        # Find the first order date to determine starting month
        first_order_date = orders[0].order_date
        first_month = date(first_order_date.year, first_order_date.month, 1)

        # Generate monthly data from first month to current month
        current_date = date.today()
        current_month = date(current_date.year, current_date.month, 1)

        monthly_values = []
        month_iter = first_month

        while month_iter <= current_month:
            month_first_day = month_iter

            # For the very first month (month of first order), value is 0
            if month_iter == first_month:
                monthly_values.append({
                    "month": month_first_day.strftime("%Y-%m"),
                    "month_display": month_first_day.strftime("%B %Y"),
                    "date": month_first_day.isoformat(),
                    "portfolio_value": 0.0,
                    "invested_capital": 0.0,
                    "plus_minus_values": 0.0,
                    "plus_minus_values_pct": 0.0,
                    "positions": [],
                    "is_first_month": True
                })
            else:
                # Calculate portfolio value at the beginning of this month
                portfolio_value, invested_capital, positions = self._calculate_portfolio_value_at_date(orders, month_first_day)

                # Calculate +/- values (profit/loss)
                plus_minus_values = portfolio_value - invested_capital
                plus_minus_values_pct = (plus_minus_values / invested_capital * 100) if invested_capital > 0 else 0

                monthly_values.append({
                    "month": month_first_day.strftime("%Y-%m"),
                    "month_display": month_first_day.strftime("%B %Y"),
                    "date": month_first_day.isoformat(),
                    "portfolio_value": portfolio_value,
                    "invested_capital": invested_capital,
                    "plus_minus_values": plus_minus_values,
                    "plus_minus_values_pct": plus_minus_values_pct,
                    "positions": positions,
                    "is_first_month": False
                })

            # Move to next month
            if month_iter.month == 12:
                month_iter = date(month_iter.year + 1, 1, 1)
            else:
                month_iter = date(month_iter.year, month_iter.month + 1, 1)

        # Add current value as a final row
        current_portfolio_value, current_invested_capital, current_positions = self._calculate_portfolio_value_at_date(orders, current_date)
        current_plus_minus_values = current_portfolio_value - current_invested_capital
        current_plus_minus_values_pct = (current_plus_minus_values / current_invested_capital * 100) if current_invested_capital > 0 else 0

        monthly_values.append({
            "month": "current",
            "month_display": "Actuellement",
            "date": current_date.isoformat(),
            "portfolio_value": current_portfolio_value,
            "invested_capital": current_invested_capital,
            "plus_minus_values": current_plus_minus_values,
            "plus_minus_values_pct": current_plus_minus_values_pct,
            "positions": current_positions,
            "is_current": True,
            "is_first_month": False
        })

        return monthly_values

    def _calculate_portfolio_value_at_date(
        self,
        orders: List[InvestmentOrder],
        target_date: date
    ) -> tuple[float, float, List[Dict[str, Any]]]:
        """Calculate portfolio value, total invested capital and positions at a specific date."""
        # Filter orders that occurred before the target date
        relevant_orders = [order for order in orders if order.order_date < target_date]

        if not relevant_orders:
            return 0.0, 0.0, []

        # Group orders by ISIN and calculate quantities held at target date
        isin_positions = {}
        for order in relevant_orders:
            isin = order.isin
            if isin not in isin_positions:
                isin_positions[isin] = {
                    'quantity': 0.0,
                    'total_invested': 0.0
                }

            # For now, treat all orders as buy orders (consistent with rest of codebase)
            # TODO: Add proper buy/sell support once order_type is added to InvestmentOrder model
            isin_positions[isin]['quantity'] += order.quantity
            isin_positions[isin]['total_invested'] += order.total_price_eur

        # Remove positions with zero or negative quantities
        isin_positions = {k: v for k, v in isin_positions.items() if v['quantity'] > 0}

        total_portfolio_value = 0.0
        total_invested_capital = 0.0
        positions_detail = []

        # For each position, get historical price and calculate value
        for isin, position_data in isin_positions.items():
            quantity = position_data['quantity']

            # Get historical price for this ISIN at target date
            price_quote = self.price_service.get_historical_price(isin, target_date)

            # Always add the invested capital for this position, regardless of price availability
            total_invested_capital += position_data['total_invested']

            if price_quote.is_valid and price_quote.price > 0:
                position_value = quantity * price_quote.price
                total_portfolio_value += position_value

                positions_detail.append({
                    "isin": isin,
                    "quantity": quantity,
                    "price": price_quote.price,
                    "value": position_value,
                    "total_invested": position_data['total_invested'],
                    "price_source": price_quote.source
                })
            else:
                # If we can't get historical price, log warning but continue
                self._log("Could not get historical price", {
                    "isin": isin,
                    "date": target_date.isoformat(),
                    "error": price_quote.error_message if price_quote else "No quote"
                })

                # Try current price as fallback for very recent dates
                current_price_quote = self.price_service.get_current_price(isin)
                if current_price_quote.is_valid and current_price_quote.price > 0:
                    position_value = quantity * current_price_quote.price
                    total_portfolio_value += position_value

                    positions_detail.append({
                        "isin": isin,
                        "quantity": quantity,
                        "price": current_price_quote.price,
                        "value": position_value,
                        "total_invested": position_data['total_invested'],
                        "price_source": f"{current_price_quote.source} (fallback)"
                    })

        return total_portfolio_value, total_invested_capital, positions_detail