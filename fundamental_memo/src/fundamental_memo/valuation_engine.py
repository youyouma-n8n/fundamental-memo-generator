"""Pure-Python deterministic valuation, Reverse DCF, Exit Multiple, and earnings quality engine."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Literal

from fundamental_memo.schemas import (
    DcfSensitivity,
    DcfSensitivityMatrix,
    FinancialSnapshot,
    NegativeFreeCashFlowError,
    PeerComparable,
    ValuationAnalysis,
    ValuationError,
)

DEFAULT_WACC = 0.095
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_PROJECTION_YEARS = 5
DEFAULT_MIN_FCF_GROWTH = 0.02
DEFAULT_MAX_FCF_GROWTH = 0.15
DEFAULT_EXIT_EV_EBITDA = 15.0
REVERSE_DCF_LOWER_BOUND = -0.20
REVERSE_DCF_UPPER_BOUND = 1.00


def clamp_growth_rate(
    historical_revenue_growth_3y: float,
    min_growth_rate: float = DEFAULT_MIN_FCF_GROWTH,
    max_growth_rate: float = DEFAULT_MAX_FCF_GROWTH,
) -> float:
    """Clamp historical 3-year revenue growth into conservative DCF projection bounds."""
    if min_growth_rate > max_growth_rate:
        raise ValuationError("min_growth_rate cannot exceed max_growth_rate.")
    return min(max(historical_revenue_growth_3y, min_growth_rate), max_growth_rate)


def _validate_dcf_inputs(
    snapshot: FinancialSnapshot,
    *,
    wacc: float,
    terminal_growth_rate: float,
    projection_years: int,
) -> None:
    """Validate common inputs for forward and reverse unlevered DCF models."""
    if not math.isfinite(wacc) or wacc <= 0.0:
        raise ValuationError(f"WACC must be a positive finite number (got {wacc}).")
    if not math.isfinite(terminal_growth_rate):
        raise ValuationError(
            f"Terminal growth rate must be finite (got {terminal_growth_rate})."
        )
    if wacc <= terminal_growth_rate:
        raise ValuationError(
            f"WACC ({wacc:.4f}) must strictly exceed terminal growth rate "
            f"({terminal_growth_rate:.4f})."
        )
    if projection_years < 1:
        raise ValuationError(f"projection_years must be >= 1 (got {projection_years}).")
    if snapshot.shares_outstanding <= 0.0:
        raise ValuationError("shares_outstanding must be positive for DCF valuation.")
    if snapshot.free_cash_flow_ttm <= 0.0:
        raise NegativeFreeCashFlowError(
            f"Cannot compute standard positive-FCF DCF for {snapshot.ticker}: "
            f"TTM free cash flow is {snapshot.free_cash_flow_ttm:,.2f}."
        )


def _evaluate_perpetuity_dcf_per_share(
    snapshot: FinancialSnapshot,
    *,
    fcf_cagr: float,
    wacc: float,
    terminal_growth_rate: float,
    projection_years: int,
) -> float:
    """Evaluate 5-year unlevered perpetuity DCF intrinsic value per share for a given FCF CAGR.

    Formulas:
        FCF_t = FCF_0 * (1 + fcf_cagr)^t  for t = 1..N
        TV = FCF_N * (1 + g_term) / (WACC - g_term)
        EV = sum_{t=1..N} FCF_t / (1 + WACC)^t + TV / (1 + WACC)^N
        Equity Value = EV + cash_and_equivalents - total_debt
        Intrinsic Value / Share = Equity Value / shares_outstanding
    """
    present_value_fcfs = 0.0
    projected_fcf = snapshot.free_cash_flow_ttm
    for year_index in range(1, projection_years + 1):
        projected_fcf = snapshot.free_cash_flow_ttm * ((1.0 + fcf_cagr) ** year_index)
        present_value_fcfs += projected_fcf / ((1.0 + wacc) ** year_index)

    terminal_value = projected_fcf * (1.0 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    present_value_terminal = terminal_value / ((1.0 + wacc) ** projection_years)

    enterprise_value = present_value_fcfs + present_value_terminal
    equity_value = enterprise_value + snapshot.cash_and_equivalents - snapshot.total_debt
    return equity_value / snapshot.shares_outstanding


def compute_dcf_intrinsic_value(
    snapshot: FinancialSnapshot,
    *,
    wacc: float = DEFAULT_WACC,
    terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
    min_growth_rate: float = DEFAULT_MIN_FCF_GROWTH,
    max_growth_rate: float = DEFAULT_MAX_FCF_GROWTH,
    fcf_cagr_override: float | None = None,
) -> tuple[float, float, dict[str, float]]:
    """Compute 5-year unlevered DCF intrinsic value per share and upside percentage."""
    _validate_dcf_inputs(
        snapshot,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )

    if fcf_cagr_override is not None:
        if not math.isfinite(fcf_cagr_override) or fcf_cagr_override <= -1.0:
            raise ValuationError(
                f"fcf_cagr_override must be finite and > -1.0 (got {fcf_cagr_override})."
            )
        fcf_cagr = fcf_cagr_override
    else:
        fcf_cagr = clamp_growth_rate(
            snapshot.historical_revenue_growth_3y,
            min_growth_rate=min_growth_rate,
            max_growth_rate=max_growth_rate,
        )

    intrinsic_value_per_share = _evaluate_perpetuity_dcf_per_share(
        snapshot,
        fcf_cagr=fcf_cagr,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )
    upside_pct = (intrinsic_value_per_share / snapshot.current_price) - 1.0

    assumptions: dict[str, float] = {
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth_rate,
        "projection_years": float(projection_years),
        "fcf_cagr": fcf_cagr,
    }
    return intrinsic_value_per_share, upside_pct, assumptions


def solve_reverse_dcf_implied_cagr(
    snapshot: FinancialSnapshot,
    *,
    wacc: float = DEFAULT_WACC,
    terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
    lower_bound: float = REVERSE_DCF_LOWER_BOUND,
    upper_bound: float = REVERSE_DCF_UPPER_BOUND,
    tolerance_dollars: float = 1e-6,
    max_iterations: int = 100,
) -> float | None:
    """Solve for market-implied 5-year FCF CAGR via bisection over [lower_bound, upper_bound].

    Finds g_implied such that DCF(g_implied, WACC, g_term) == snapshot.current_price.
    Returns None if current_price lies outside the valuation bracket [DCF(lower), DCF(upper)].
    """
    _validate_dcf_inputs(
        snapshot,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )

    target_price = snapshot.current_price
    low_price = _evaluate_perpetuity_dcf_per_share(
        snapshot,
        fcf_cagr=lower_bound,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )
    high_price = _evaluate_perpetuity_dcf_per_share(
        snapshot,
        fcf_cagr=upper_bound,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )

    if target_price < low_price or target_price > high_price:
        return None

    low_rate = lower_bound
    high_rate = upper_bound
    for _ in range(max_iterations):
        mid_rate = 0.5 * (low_rate + high_rate)
        mid_price = _evaluate_perpetuity_dcf_per_share(
            snapshot,
            fcf_cagr=mid_rate,
            wacc=wacc,
            terminal_growth_rate=terminal_growth_rate,
            projection_years=projection_years,
        )
        if abs(mid_price - target_price) <= tolerance_dollars:
            return mid_rate
        if mid_price < target_price:
            low_rate = mid_rate
        else:
            high_rate = mid_rate

    return 0.5 * (low_rate + high_rate)


def compute_exit_multiple_dcf_value(
    snapshot: FinancialSnapshot,
    *,
    fcf_cagr: float,
    wacc: float = DEFAULT_WACC,
    target_exit_ev_ebitda: float = DEFAULT_EXIT_EV_EBITDA,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
) -> float | None:
    """Compute Exit Multiple DCF intrinsic value per share using Terminal Year EBITDA * Multiple.

    Formulas:
        PV_FCFs = sum_{t=1..N} FCF_0 * (1 + fcf_cagr)^t / (1 + WACC)^t
        Terminal_EBITDA = EBITDA_0 * (1 + fcf_cagr)^N
        PV_Terminal = (Terminal_EBITDA * target_exit_ev_ebitda) / (1 + WACC)^N
        Equity Value = PV_FCFs + PV_Terminal + (cash_and_equivalents - total_debt)
        Exit Multiple DCF / Share = Equity Value / shares_outstanding
    """
    if (
        snapshot.ebitda_ttm <= 0.0
        or snapshot.free_cash_flow_ttm <= 0.0
        or not math.isfinite(target_exit_ev_ebitda)
        or target_exit_ev_ebitda <= 0.0
        or not math.isfinite(wacc)
        or wacc <= 0.0
    ):
        return None

    present_value_fcfs = 0.0
    for year_index in range(1, projection_years + 1):
        projected_fcf = snapshot.free_cash_flow_ttm * ((1.0 + fcf_cagr) ** year_index)
        present_value_fcfs += projected_fcf / ((1.0 + wacc) ** year_index)

    terminal_ebitda = snapshot.ebitda_ttm * ((1.0 + fcf_cagr) ** projection_years)
    terminal_enterprise_value = terminal_ebitda * target_exit_ev_ebitda
    present_value_terminal = terminal_enterprise_value / ((1.0 + wacc) ** projection_years)

    net_cash = snapshot.cash_and_equivalents - snapshot.total_debt
    equity_value = present_value_fcfs + present_value_terminal + net_cash
    return equity_value / snapshot.shares_outstanding


def compute_implied_exit_ev_ebitda(
    snapshot: FinancialSnapshot,
    *,
    fcf_cagr: float,
    wacc: float = DEFAULT_WACC,
    terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
) -> float | None:
    """Compute the terminal-year EV/EBITDA multiple implied by the Perpetuity Growth DCF.

    Formula:
        FCF_N = FCF_0 * (1 + fcf_cagr)^N
        Terminal_Value_N = FCF_N * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
        EBITDA_N = EBITDA_0 * (1 + fcf_cagr)^N
        Implied_Exit_EV_EBITDA = Terminal_Value_N / EBITDA_N
    """
    if (
        snapshot.ebitda_ttm <= 0.0
        or snapshot.free_cash_flow_ttm <= 0.0
        or not math.isfinite(wacc)
        or not math.isfinite(terminal_growth_rate)
        or wacc <= terminal_growth_rate
    ):
        return None
    final_fcf = snapshot.free_cash_flow_ttm * ((1.0 + fcf_cagr) ** projection_years)
    terminal_value = final_fcf * (1.0 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    terminal_ebitda = snapshot.ebitda_ttm * ((1.0 + fcf_cagr) ** projection_years)
    if terminal_ebitda <= 0.0:
        return None
    return terminal_value / terminal_ebitda


def compute_dcf_sensitivity_matrix(
    snapshot: FinancialSnapshot,
    *,
    base_wacc: float = DEFAULT_WACC,
    base_cagr: float = DEFAULT_MAX_FCF_GROWTH,
    terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
) -> DcfSensitivityMatrix:
    """Build a 5x5 DCF intrinsic share price matrix spanning WACC columns and 5Y FCF CAGR rows.

    Columns (WACC): base_wacc + [-1.0%, -0.5%, 0.0%, +0.5%, +1.0%]
    Rows (CAGR):    max(0.0, base_cagr + [-5.0%, -2.5%, 0.0%, +2.5%, +5.0%])
    """
    wacc_offsets = (-0.010, -0.005, 0.0, 0.005, 0.010)
    cagr_offsets = (-0.050, -0.025, 0.0, 0.025, 0.050)

    wacc_values = [
        base_wacc if offset == 0.0 else round(base_wacc + offset, 6) for offset in wacc_offsets
    ]
    cagr_values = [
        max(0.0, base_cagr) if offset == 0.0 else round(max(0.0, base_cagr + offset), 6)
        for offset in cagr_offsets
    ]

    grid: list[list[float | None]] = []
    for cagr_val in cagr_values:
        row: list[float | None] = []
        for wacc_val in wacc_values:
            if wacc_val <= 0.0 or wacc_val <= terminal_growth_rate:
                row.append(None)
            else:
                row.append(
                    _evaluate_perpetuity_dcf_per_share(
                        snapshot,
                        fcf_cagr=cagr_val,
                        wacc=wacc_val,
                        terminal_growth_rate=terminal_growth_rate,
                        projection_years=projection_years,
                    )
                )
        grid.append(row)

    return DcfSensitivityMatrix(
        wacc_values=wacc_values,
        cagr_values=cagr_values,
        grid=grid,
    )


def compute_dcf_sensitivity(
    snapshot: FinancialSnapshot,
    *,
    wacc: float = DEFAULT_WACC,
    terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
    wacc_step: float = 0.01,
    fcf_cagr_override: float | None = None,
) -> DcfSensitivity:
    """Compute DCF intrinsic value per share across base WACC +/- wacc_step (default 100 bps)."""
    low_wacc = max(terminal_growth_rate + 0.005, wacc - wacc_step)
    high_wacc = wacc + wacc_step

    low_val, _, _ = compute_dcf_intrinsic_value(
        snapshot,
        wacc=low_wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
        fcf_cagr_override=fcf_cagr_override,
    )
    base_val, _, _ = compute_dcf_intrinsic_value(
        snapshot,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
        fcf_cagr_override=fcf_cagr_override,
    )
    high_val, _, _ = compute_dcf_intrinsic_value(
        snapshot,
        wacc=high_wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
        fcf_cagr_override=fcf_cagr_override,
    )
    return DcfSensitivity(
        low_wacc=low_wacc,
        low_wacc_value_per_share=low_val,
        base_wacc=wacc,
        base_wacc_value_per_share=base_val,
        high_wacc=high_wacc,
        high_wacc_value_per_share=high_val,
    )


def compute_positive_median(values: Sequence[float | None]) -> float | None:
    """Return the median of positive finite values, ignoring None and <= 0 outliers."""
    valid_values = [
        value for value in values if value is not None and math.isfinite(value) and value > 0.0
    ]
    if not valid_values:
        return None
    return float(statistics.median(valid_values))


def _linear_percentile(sorted_values: Sequence[float], quantile: float) -> float:
    """Compute a linear-interpolated percentile (quantile in [0, 1]) on sorted non-empty floats."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = quantile * (len(sorted_values) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = position - lower_index
    return sorted_values[lower_index] * (1.0 - fraction) + sorted_values[upper_index] * fraction


def compute_peer_comps_with_range(
    snapshot: FinancialSnapshot, peers: Sequence[PeerComparable]
) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Compute peer medians, blended implied share price, and 25th–75th percentile implied range."""
    median_ev_ebitda = compute_positive_median([peer.ev_to_ebitda for peer in peers])
    median_pe = compute_positive_median([peer.pe_ratio for peer in peers])

    implied_prices: list[float] = []
    if median_ev_ebitda is not None and snapshot.ebitda_ttm > 0.0:
        implied_ev = median_ev_ebitda * snapshot.ebitda_ttm
        implied_equity_from_ev = implied_ev + snapshot.cash_and_equivalents - snapshot.total_debt
        implied_prices.append(implied_equity_from_ev / snapshot.shares_outstanding)

    if median_pe is not None and snapshot.net_income_ttm > 0.0:
        eps_ttm = snapshot.net_income_ttm / snapshot.shares_outstanding
        implied_prices.append(median_pe * eps_ttm)

    implied_value_by_comps: float | None = None
    if implied_prices:
        implied_value_by_comps = sum(implied_prices) / len(implied_prices)

    per_peer_implied_prices: list[float] = []
    for peer in peers:
        peer_estimates: list[float] = []
        if (
            peer.ev_to_ebitda is not None
            and math.isfinite(peer.ev_to_ebitda)
            and peer.ev_to_ebitda > 0.0
            and snapshot.ebitda_ttm > 0.0
        ):
            peer_ev = peer.ev_to_ebitda * snapshot.ebitda_ttm
            peer_equity = peer_ev + snapshot.cash_and_equivalents - snapshot.total_debt
            peer_estimates.append(peer_equity / snapshot.shares_outstanding)
        if (
            peer.pe_ratio is not None
            and math.isfinite(peer.pe_ratio)
            and peer.pe_ratio > 0.0
            and snapshot.net_income_ttm > 0.0
        ):
            eps_ttm_peer = snapshot.net_income_ttm / snapshot.shares_outstanding
            peer_estimates.append(peer.pe_ratio * eps_ttm_peer)
        if peer_estimates:
            per_peer_implied_prices.append(sum(peer_estimates) / len(peer_estimates))

    p25_value: float | None = None
    p75_value: float | None = None
    if per_peer_implied_prices:
        sorted_peer_prices = sorted(per_peer_implied_prices)
        p25_value = _linear_percentile(sorted_peer_prices, 0.25)
        p75_value = _linear_percentile(sorted_peer_prices, 0.75)

    return median_ev_ebitda, median_pe, implied_value_by_comps, p25_value, p75_value


def compute_peer_comps(
    snapshot: FinancialSnapshot, peers: Sequence[PeerComparable]
) -> tuple[float | None, float | None, float | None]:
    """Compute peer median EV/EBITDA, peer median P/E, and blended implied share price."""
    median_ev_ebitda, median_pe, implied_value_by_comps, _, _ = compute_peer_comps_with_range(
        snapshot, peers
    )
    return median_ev_ebitda, median_pe, implied_value_by_comps


def compute_target_multiples(snapshot: FinancialSnapshot) -> dict[str, float | None]:
    """Compute target company trailing and forward valuation multiples in pure Python."""
    ev_to_ebitda = (
        snapshot.enterprise_value / snapshot.ebitda_ttm if snapshot.ebitda_ttm > 0.0 else None
    )
    pe_ratio = (
        snapshot.market_cap / snapshot.net_income_ttm if snapshot.net_income_ttm > 0.0 else None
    )
    fcf_yield = (
        snapshot.free_cash_flow_ttm / snapshot.market_cap if snapshot.market_cap > 0.0 else None
    )
    forward_pe = (
        snapshot.forward_pe
        if (snapshot.forward_pe is not None and snapshot.forward_pe > 0.0)
        else None
    )
    forward_ev_ebitda = (
        snapshot.forward_ev_ebitda
        if (snapshot.forward_ev_ebitda is not None and snapshot.forward_ev_ebitda > 0.0)
        else None
    )
    pe_compression_pct = (
        (forward_pe - pe_ratio) / pe_ratio
        if (forward_pe is not None and pe_ratio is not None and pe_ratio > 0.0)
        else None
    )
    return {
        "ev_to_ebitda": ev_to_ebitda,
        "pe_ratio": pe_ratio,
        "forward_pe": forward_pe,
        "forward_ev_ebitda": forward_ev_ebitda,
        "pe_compression_pct": pe_compression_pct,
        "fcf_yield": fcf_yield,
    }


def compute_earnings_quality(
    snapshot: FinancialSnapshot,
) -> tuple[float, float, Literal["High", "Moderate", "Low"]]:
    """Compute OCF/Net Income cash conversion, Accrual Ratio, and categorical quality rating.

    Formulas:
        OCF / Net Income = operating_cash_flow_ttm / net_income_ttm  (0.0 if net_income_ttm <= 0)
        Accrual Ratio = (net_income_ttm - operating_cash_flow_ttm) / denominator
            where denominator = total_assets (if available and > 0) else enterprise_value
    """
    if snapshot.net_income_ttm > 0.0:
        ocf_to_net_income_ratio = snapshot.operating_cash_flow_ttm / snapshot.net_income_ttm
    else:
        ocf_to_net_income_ratio = 0.0

    denominator = (
        snapshot.total_assets
        if (snapshot.total_assets is not None and snapshot.total_assets > 0.0)
        else snapshot.enterprise_value
    )
    if denominator <= 0.0:
        raise ValuationError(
            "Positive total_assets or enterprise_value is required to compute accrual_ratio."
        )

    accrual_ratio = (snapshot.net_income_ttm - snapshot.operating_cash_flow_ttm) / denominator

    flag: Literal["High", "Moderate", "Low"]
    if snapshot.net_income_ttm <= 0.0 or ocf_to_net_income_ratio < 0.8 or accrual_ratio > 0.10:
        flag = "Low"
    elif ocf_to_net_income_ratio >= 1.0 and accrual_ratio <= 0.05:
        flag = "High"
    else:
        flag = "Moderate"

    return ocf_to_net_income_ratio, accrual_ratio, flag


def run_valuation_analysis(
    snapshot: FinancialSnapshot,
    peers: Sequence[PeerComparable],
    *,
    wacc: float = DEFAULT_WACC,
    terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
    fcf_cagr_override: float | None = None,
    target_exit_ev_ebitda: float = DEFAULT_EXIT_EV_EBITDA,
) -> ValuationAnalysis:
    """Execute full deterministic DCF, Reverse DCF, Exit Multiple, comps, and quality analysis."""
    dcf_value, dcf_upside, dcf_assumptions = compute_dcf_intrinsic_value(
        snapshot,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
        fcf_cagr_override=fcf_cagr_override,
    )
    base_fcf_cagr = dcf_assumptions["fcf_cagr"]
    dcf_assumptions["target_exit_ev_ebitda"] = target_exit_ev_ebitda

    implied_fcf_cagr_5y = solve_reverse_dcf_implied_cagr(
        snapshot,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )
    cagr_spread_vs_base = (
        implied_fcf_cagr_5y - base_fcf_cagr if implied_fcf_cagr_5y is not None else None
    )

    implied_y5_fcf: float | None = None
    implied_y5_fcf_multiple: float | None = None
    implied_y5_fcf_vs_current_revenue: float | None = None
    if implied_fcf_cagr_5y is not None and snapshot.free_cash_flow_ttm > 0.0:
        implied_y5_fcf = snapshot.free_cash_flow_ttm * (
            (1.0 + implied_fcf_cagr_5y) ** projection_years
        )
        implied_y5_fcf_multiple = implied_y5_fcf / snapshot.free_cash_flow_ttm
        if snapshot.revenue_ttm > 0.0:
            implied_y5_fcf_vs_current_revenue = implied_y5_fcf / snapshot.revenue_ttm

    low_wacc = max(terminal_growth_rate + 0.005, wacc - 0.01)
    high_wacc = wacc + 0.01
    exit_multiple_value = compute_exit_multiple_dcf_value(
        snapshot,
        fcf_cagr=base_fcf_cagr,
        wacc=wacc,
        target_exit_ev_ebitda=target_exit_ev_ebitda,
        projection_years=projection_years,
    )
    exit_multiple_low_wacc = compute_exit_multiple_dcf_value(
        snapshot,
        fcf_cagr=base_fcf_cagr,
        wacc=low_wacc,
        target_exit_ev_ebitda=target_exit_ev_ebitda,
        projection_years=projection_years,
    )
    exit_multiple_high_wacc = compute_exit_multiple_dcf_value(
        snapshot,
        fcf_cagr=base_fcf_cagr,
        wacc=high_wacc,
        target_exit_ev_ebitda=target_exit_ev_ebitda,
        projection_years=projection_years,
    )
    implied_exit_ev_ebitda = compute_implied_exit_ev_ebitda(
        snapshot,
        fcf_cagr=base_fcf_cagr,
        wacc=wacc,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )
    dcf_sensitivity_matrix = compute_dcf_sensitivity_matrix(
        snapshot,
        base_wacc=wacc,
        base_cagr=base_fcf_cagr,
        terminal_growth_rate=terminal_growth_rate,
        projection_years=projection_years,
    )

    (
        peer_median_ev_ebitda,
        peer_median_pe,
        implied_value_by_comps,
        peer_comps_p25_value,
        peer_comps_p75_value,
    ) = compute_peer_comps_with_range(snapshot, peers)
    peer_median_forward_pe = compute_positive_median([peer.forward_pe for peer in peers])

    ocf_to_net_income_ratio, accrual_ratio, earnings_quality_flag = compute_earnings_quality(
        snapshot
    )

    return ValuationAnalysis(
        dcf_intrinsic_value_per_share=dcf_value,
        dcf_upside_pct=dcf_upside,
        dcf_assumptions=dcf_assumptions,
        peer_median_ev_ebitda=peer_median_ev_ebitda,
        peer_median_pe=peer_median_pe,
        peer_median_forward_pe=peer_median_forward_pe,
        implied_value_by_comps=implied_value_by_comps,
        ocf_to_net_income_ratio=ocf_to_net_income_ratio,
        accrual_ratio=accrual_ratio,
        earnings_quality_flag=earnings_quality_flag,
        implied_fcf_cagr_5y=implied_fcf_cagr_5y,
        cagr_spread_vs_base=cagr_spread_vs_base,
        implied_y5_fcf=implied_y5_fcf,
        implied_y5_fcf_multiple=implied_y5_fcf_multiple,
        implied_y5_fcf_vs_current_revenue=implied_y5_fcf_vs_current_revenue,
        exit_multiple_dcf_value=exit_multiple_value,
        exit_multiple_low_wacc_value=exit_multiple_low_wacc,
        exit_multiple_high_wacc_value=exit_multiple_high_wacc,
        implied_exit_ev_ebitda=implied_exit_ev_ebitda,
        dcf_sensitivity_matrix=dcf_sensitivity_matrix,
        peer_comps_p25_value=peer_comps_p25_value,
        peer_comps_p75_value=peer_comps_p75_value,
    )
