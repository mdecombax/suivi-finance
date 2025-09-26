"""
Service for financial projections with scenario analysis.
Calculates portfolio evolution under different market conditions.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import numpy as np
from dataclasses import dataclass

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

class ProjectionService:
    """Service for calculating financial projections with multiple scenarios."""

    # Predefined scenarios based on historical market data
    SCENARIOS = {
        "pessimist": ProjectionScenario(
            name="Pessimiste",
            annual_return=0.03,  # 3% annual return
            volatility=0.15,     # 15% volatility
            description="Scénario de crise prolongée, inflation élevée"
        ),
        "normal": ProjectionScenario(
            name="Normal",
            annual_return=0.07,  # 7% annual return
            volatility=0.12,     # 12% volatility
            description="Scénario basé sur les moyennes historiques"
        ),
        "optimist": ProjectionScenario(
            name="Optimiste",
            annual_return=0.11,  # 11% annual return
            volatility=0.18,     # 18% volatility
            description="Scénario de forte croissance économique"
        )
    }

    def __init__(self, debug_logger=None):
        self.logger = debug_logger

    def _log(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log debug information if logger is available."""
        if self.logger:
            self.logger(message, extra)

    def calculate_projections(self, params: ProjectionParams) -> Dict[str, ProjectionResult]:
        """Calculate projections for all scenarios."""
        results = {}

        for scenario_key, scenario in self.SCENARIOS.items():
            try:
                result = self._calculate_single_projection(params, scenario)
                results[scenario_key] = result

                self._log(f"Calculated projection for {scenario.name}", {
                    "final_value": result.final_value,
                    "total_gains": result.total_gains,
                    "annualized_return": result.annualized_return
                })

            except Exception as e:
                self._log(f"Error calculating {scenario.name} projection", {"error": str(e)})
                continue

        return results

    def _calculate_single_projection(self, params: ProjectionParams, scenario: ProjectionScenario) -> ProjectionResult:
        """Calculate projection for a single scenario."""
        months = params.time_horizon_years * 12
        monthly_return = scenario.annual_return / 12
        monthly_fees = params.annual_fees_rate / 12

        # Initialize arrays for tracking
        monthly_values = []
        labels = []
        current_value = params.current_value
        total_contributions = 0
        total_fees = 0

        # Calculate starting date for projections
        start_date = datetime.now()

        for month in range(months + 1):
            # Calculate actual date for this month
            current_date = start_date + timedelta(days=month * 30.44)  # Average days per month

            # Generate label (every 6 months for readability)
            if month % 6 == 0:
                # Format as "Jan 2025" or "Jul 2025"
                labels.append(current_date.strftime("%b %Y"))
            else:
                labels.append("")

            # Record current value
            monthly_values.append(round(current_value, 2))

            if month < months:  # Don't apply changes in the last iteration
                # Add monthly contribution
                current_value += params.monthly_contribution
                total_contributions += params.monthly_contribution

                # Apply market return
                market_gain = current_value * monthly_return
                current_value += market_gain

                # Apply fees
                fees = current_value * monthly_fees
                current_value -= fees
                total_fees += fees

        # Calculate metrics
        final_value = monthly_values[-1]
        total_gains = final_value - params.current_value - total_contributions

        # Calculate annualized return using XIRR-like formula
        if params.current_value > 0:
            total_invested = params.current_value + total_contributions
            annualized_return = ((final_value / total_invested) ** (1 / params.time_horizon_years)) - 1
        else:
            annualized_return = 0

        return ProjectionResult(
            scenario_name=scenario.name,
            final_value=final_value,
            total_contributions=total_contributions,
            total_gains=total_gains,
            total_fees=total_fees,
            annualized_return=annualized_return,
            monthly_values=monthly_values,
            labels=labels
        )

    def get_projection_summary(self, params: ProjectionParams) -> Dict[str, Any]:
        """Get a comprehensive projection summary."""
        projections = self.calculate_projections(params)

        # Calculate summary statistics
        final_values = [p.final_value for p in projections.values()]
        final_value_range = max(final_values) - min(final_values) if final_values else 0

        return {
            "projections": {key: self._projection_to_dict(proj) for key, proj in projections.items()},
            "parameters": {
                "current_value": params.current_value,
                "monthly_contribution": params.monthly_contribution,
                "time_horizon_years": params.time_horizon_years,
                "annual_fees_rate": params.annual_fees_rate
            },
            "summary": {
                "scenarios_count": len(projections),
                "final_value_range": final_value_range,
                "best_case": max(final_values) if final_values else 0,
                "worst_case": min(final_values) if final_values else 0,
                "calculation_date": datetime.now().isoformat()
            }
        }

    def _projection_to_dict(self, projection: ProjectionResult) -> Dict[str, Any]:
        """Convert ProjectionResult to dictionary for JSON serialization."""
        return {
            "scenario_name": projection.scenario_name,
            "final_value": projection.final_value,
            "total_contributions": projection.total_contributions,
            "total_gains": projection.total_gains,
            "total_fees": projection.total_fees,
            "annualized_return": projection.annualized_return,
            "monthly_values": projection.monthly_values,
            "labels": projection.labels
        }

    def validate_projection_params(self, params_dict: Dict[str, Any]) -> Optional[str]:
        """Validate projection parameters. Returns error message if invalid, None if valid."""
        try:
            current_value = float(params_dict.get("current_value", 0))
            monthly_contribution = float(params_dict.get("monthly_contribution", 0))
            time_horizon = int(params_dict.get("time_horizon_years", 1))

            if current_value < 0:
                return "La valeur actuelle du portefeuille ne peut pas être négative"

            if monthly_contribution < 0:
                return "La contribution mensuelle ne peut pas être négative"

            if time_horizon < 1 or time_horizon > 50:
                return "L'horizon temporel doit être entre 1 et 50 ans"

            return None

        except (ValueError, TypeError):
            return "Paramètres invalides - vérifiez les valeurs numériques"