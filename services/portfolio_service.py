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
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get complete portfolio summary including positions, performance, and fiscal scenarios."""
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