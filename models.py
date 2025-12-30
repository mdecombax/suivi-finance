"""
Models module - Data structures and models for the financial tracking application.
Consolidates all dataclasses used across the application.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, List, Dict, Any


# ============================================================================
# PORTFOLIO MODELS
# ============================================================================

@dataclass
class InvestmentOrder:
    """Represents a single investment order/transaction."""

    id: int
    isin: str
    quantity: float
    unit_price_eur: float
    total_price_eur: float
    order_date: date
    price_source: Optional[str] = None
    venue: Optional[str] = None
    requested_date: Optional[date] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InvestmentOrder':
        """Create InvestmentOrder from dictionary data."""
        return cls(
            id=data.get('id', 0),
            isin=data.get('isin', '').strip().upper(),
            quantity=float(data.get('quantity', 0)),
            unit_price_eur=float(data.get('unitPriceEUR', 0)),
            total_price_eur=float(data.get('totalPriceEUR', 0)),
            order_date=date.fromisoformat(data.get('date', '')),
            price_source=data.get('priceSource'),
            venue=data.get('venue'),
            requested_date=date.fromisoformat(data['requestedDate']) if data.get('requestedDate') else None
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert InvestmentOrder to dictionary."""
        result = {
            'id': self.id,
            'isin': self.isin,
            'quantity': self.quantity,
            'unitPriceEUR': self.unit_price_eur,
            'totalPriceEUR': self.total_price_eur,
            'date': self.order_date.isoformat(),
        }

        if self.price_source:
            result['priceSource'] = self.price_source
        if self.venue:
            result['venue'] = self.venue
        if self.requested_date:
            result['requestedDate'] = self.requested_date.isoformat()

        return result


@dataclass
class PositionSummary:
    """Summary of a position aggregated by ISIN."""

    isin: str
    quantity: float
    total_invested: float
    average_unit_price: float
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    profit_loss_absolute: Optional[float] = None
    profit_loss_percentage: Optional[float] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert PositionSummary to dictionary for API responses."""
        return {
            'isin': self.isin,
            'name': self.name or self.isin,
            'quantity': self.quantity,
            'invested': self.total_invested,
            'avgUnitPrice': self.average_unit_price,
            'currentPrice': self.current_price,
            'currentValue': self.current_value,
            'plAbs': self.profit_loss_absolute,
            'plPct': self.profit_loss_percentage,
        }


@dataclass
class PerformanceMetrics:
    """Portfolio performance calculation results."""

    annual_return_percentage: Optional[float]
    total_return_percentage: Optional[float]
    calculation_method: str
    description: str
    calculation_details: List[Dict[str, Any]]
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert PerformanceMetrics to dictionary for API responses."""
        return {
            'annual_return': self.annual_return_percentage,
            'total_return': self.total_return_percentage,
            'method': self.calculation_method,
            'description': self.description,
            'calculation_details': self.calculation_details,
            'error': self.error_message,
        }


@dataclass
class FiscalScenario:
    """Tax scenario calculation for different account types."""

    name: str
    description: str
    tax_rate: float
    net_value: Optional[float]
    tax_amount: Optional[float]
    icon: str
    color: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert FiscalScenario to dictionary for API responses."""
        return {
            'name': self.name,
            'description': self.description,
            'tax_rate': self.tax_rate,
            'net_value': self.net_value,
            'tax_amount': self.tax_amount,
            'icon': self.icon,
            'color': self.color,
        }


@dataclass
class PriceQuote:
    """Represents a price quote from an external source."""

    price: float
    source: str
    venue: Optional[str] = None
    quote_date: Optional[date] = None
    currency: str = "EUR"
    error_message: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if the price quote is valid."""
        return self.price is not None and self.error_message is None

    def to_dict(self) -> Dict[str, Any]:
        """Convert PriceQuote to dictionary."""
        result = {
            'price': self.price,
            'source': self.source,
            'currency': self.currency,
        }

        if self.venue:
            result['venue'] = self.venue
        if self.quote_date:
            result['date'] = self.quote_date.isoformat()
        if self.error_message:
            result['error'] = self.error_message

        return result


# ============================================================================
# PROJECTION MODELS
# ============================================================================

@dataclass
class ProjectionScenario:
    """Represents a financial projection scenario."""
    name: str
    annual_return: float
    volatility: float
    description: str


@dataclass
class ProjectionParams:
    """Parameters for portfolio projection."""
    current_value: float
    monthly_contribution: float
    time_horizon_years: int
    annual_fees_rate: float = 0.0075  # 0.75% annual fees


@dataclass
class ProjectionResult:
    """Result of a portfolio projection."""
    scenario_name: str
    final_value: float
    total_contributions: float
    total_gains: float
    total_fees: float
    annualized_return: float
    monthly_values: List[float]
    labels: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert ProjectionResult to dictionary for JSON serialization."""
        return {
            "scenario_name": self.scenario_name,
            "final_value": self.final_value,
            "total_contributions": self.total_contributions,
            "total_gains": self.total_gains,
            "total_fees": self.total_fees,
            "annualized_return": self.annualized_return,
            "monthly_values": self.monthly_values,
            "labels": self.labels
        }
