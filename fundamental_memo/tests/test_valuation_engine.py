"""Unit tests for pure-Python DCF, Reverse DCF, Exit Multiple, comps, and earnings quality."""

from __future__ import annotations

import pytest

from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.schemas import (
    FinancialSnapshot,
    NegativeFreeCashFlowError,
    PeerComparable,
    ValuationError,
)
from fundamental_memo.valuation_engine import (
    compute_dcf_intrinsic_value,
    compute_dcf_sensitivity,
    compute_dcf_sensitivity_matrix,
    compute_earnings_quality,
    compute_exit_multiple_dcf_value,
    compute_implied_exit_ev_ebitda,
    compute_peer_comps,
    compute_peer_comps_with_range,
    compute_positive_median,
    compute_target_multiples,
    run_valuation_analysis,
    solve_reverse_dcf_implied_cagr,
)


def _sample_snapshot(**overrides: object) -> FinancialSnapshot:
    base: dict[str, object] = {
        "ticker": "TEST",
        "company_name": "Test Corp",
        "sector": "Technology",
        "current_price": 100.0,
        "market_cap": 100_000_000_000.0,
        "enterprise_value": 110_000_000_000.0,
        "revenue_ttm": 20_000_000_000.0,
        "ebitda_ttm": 6_000_000_000.0,
        "net_income_ttm": 4_000_000_000.0,
        "operating_cash_flow_ttm": 5_000_000_000.0,
        "capex_ttm": 1_000_000_000.0,
        "free_cash_flow_ttm": 4_000_000_000.0,
        "total_debt": 15_000_000_000.0,
        "cash_and_equivalents": 5_000_000_000.0,
        "shares_outstanding": 1_000_000_000.0,
        "historical_revenue_growth_3y": 0.10,
        "total_assets": 80_000_000_000.0,
    }
    base.update(overrides)
    return FinancialSnapshot.model_validate(base)


def test_dcf_exact_math_and_ev_to_equity_bridge() -> None:
    """Verify exact 5-year DCF cash flows, terminal value, and EV-to-Equity bridge."""
    snapshot = _sample_snapshot(historical_revenue_growth_3y=0.10)
    wacc = 0.095
    terminal_growth = 0.025
    fcf_0 = 4_000_000_000.0
    growth = 0.10

    expected_pv_fcf = sum(
        (fcf_0 * ((1.0 + growth) ** year)) / ((1.0 + wacc) ** year) for year in range(1, 6)
    )
    fcf_5 = fcf_0 * ((1.0 + growth) ** 5)
    expected_tv = fcf_5 * (1.0 + terminal_growth) / (wacc - terminal_growth)
    expected_ev = expected_pv_fcf + expected_tv / ((1.0 + wacc) ** 5)
    expected_equity = expected_ev + 5_000_000_000.0 - 15_000_000_000.0
    expected_per_share = expected_equity / 1_000_000_000.0
    expected_upside = (expected_per_share / 100.0) - 1.0

    intrinsic_value, upside_pct, assumptions = compute_dcf_intrinsic_value(
        snapshot, wacc=wacc, terminal_growth_rate=terminal_growth
    )

    assert intrinsic_value == pytest.approx(expected_per_share, rel=1e-9)
    assert upside_pct == pytest.approx(expected_upside, rel=1e-9)
    assert assumptions == {
        "wacc": wacc,
        "terminal_growth_rate": terminal_growth,
        "projection_years": 5.0,
        "fcf_cagr": 0.10,
    }


def test_dcf_growth_rate_clamping_and_explicit_override() -> None:
    """Verify clamping at [2%, 15%] by default and explicit fcf_cagr_override support."""
    high_growth = _sample_snapshot(historical_revenue_growth_3y=0.42)
    _, _, high_assumptions = compute_dcf_intrinsic_value(high_growth)
    assert high_assumptions["fcf_cagr"] == pytest.approx(0.15)

    low_growth = _sample_snapshot(historical_revenue_growth_3y=-0.08)
    _, _, low_assumptions = compute_dcf_intrinsic_value(low_growth)
    assert low_assumptions["fcf_cagr"] == pytest.approx(0.02)

    _, _, override_assumptions = compute_dcf_intrinsic_value(high_growth, fcf_cagr_override=0.22)
    assert override_assumptions["fcf_cagr"] == pytest.approx(0.22)


def test_reverse_dcf_round_trip_accuracy_within_one_cent() -> None:
    """Plugging implied_fcf_cagr_5y back into forward DCF must reproduce current_price ±$0.01."""
    bundle = load_mock_market_data()
    snapshot = bundle.snapshot
    implied_cagr = solve_reverse_dcf_implied_cagr(
        snapshot, wacc=0.095, terminal_growth_rate=0.025
    )
    assert implied_cagr is not None
    assert -0.20 <= implied_cagr <= 1.00

    reproduced_price, _, _ = compute_dcf_intrinsic_value(
        snapshot,
        wacc=0.095,
        terminal_growth_rate=0.025,
        fcf_cagr_override=implied_cagr,
    )
    assert abs(reproduced_price - snapshot.current_price) <= 0.01


def test_reverse_dcf_out_of_bracket_returns_none() -> None:
    """Market prices outside [-20%, +100%] CAGR valuation range return None gracefully."""
    extreme_snapshot = _sample_snapshot(current_price=50_000.0)
    assert solve_reverse_dcf_implied_cagr(extreme_snapshot) is None


def test_exit_multiple_dcf_exact_math_and_non_positive_ebitda() -> None:
    """Verify Terminal Year EBITDA * exit multiple DCF formula and negative-EBITDA handling."""
    snapshot = _sample_snapshot()
    wacc = 0.095
    cagr = 0.12
    exit_mult = 15.0

    expected_pv_fcf = sum(
        (4_000_000_000.0 * ((1.0 + cagr) ** yr)) / ((1.0 + wacc) ** yr) for yr in range(1, 6)
    )
    terminal_ebitda = 6_000_000_000.0 * ((1.0 + cagr) ** 5)
    expected_pv_term = (terminal_ebitda * exit_mult) / ((1.0 + wacc) ** 5)
    expected_per_share = (
        expected_pv_fcf + expected_pv_term + 5_000_000_000.0 - 15_000_000_000.0
    ) / 1_000_000_000.0

    exit_value = compute_exit_multiple_dcf_value(
        snapshot, fcf_cagr=cagr, wacc=wacc, target_exit_ev_ebitda=exit_mult
    )
    assert exit_value == pytest.approx(expected_per_share, rel=1e-9)

    neg_ebitda = _sample_snapshot(ebitda_ttm=-1_000_000.0)
    assert compute_exit_multiple_dcf_value(neg_ebitda, fcf_cagr=cagr, wacc=wacc) is None


def test_dcf_rejects_invalid_parameters_and_negative_fcf() -> None:
    """Verify invalid WACC/terminal growth and non-positive FCF raise typed errors."""
    snapshot = _sample_snapshot()
    with pytest.raises(ValuationError, match="strictly exceed"):
        compute_dcf_intrinsic_value(snapshot, wacc=0.025, terminal_growth_rate=0.025)

    with pytest.raises(ValuationError, match="positive"):
        compute_dcf_intrinsic_value(snapshot, wacc=-0.05, terminal_growth_rate=-0.06)

    negative_fcf_snapshot = _sample_snapshot(free_cash_flow_ttm=-500_000_000.0)
    with pytest.raises(NegativeFreeCashFlowError):
        compute_dcf_intrinsic_value(negative_fcf_snapshot)


def test_dcf_sensitivity_monotonic_in_wacc() -> None:
    """Lower WACC must yield higher intrinsic value than base and high WACC."""
    snapshot = _sample_snapshot()
    sensitivity = compute_dcf_sensitivity(snapshot, wacc=0.095, terminal_growth_rate=0.025)
    assert sensitivity.low_wacc_value_per_share > sensitivity.base_wacc_value_per_share
    assert sensitivity.base_wacc_value_per_share > sensitivity.high_wacc_value_per_share


def test_peer_median_ignores_none_and_non_positive_outliers() -> None:
    """Verify peer median excludes None, zero, and negative multiples."""
    assert compute_positive_median([40.0, None, -15.0, 0.0, 20.0, 30.0]) == pytest.approx(30.0)
    assert compute_positive_median([None, -5.0, 0.0]) is None


def test_peer_comps_implied_value_and_percentile_range() -> None:
    """Verify EV/EBITDA + P/E median blending and 25th-75th percentile implied range."""
    snapshot = _sample_snapshot()
    peers = [
        PeerComparable(ticker="P1", ev_to_ebitda=20.0, pe_ratio=25.0, fcf_yield=0.03),
        PeerComparable(ticker="P2", ev_to_ebitda=None, pe_ratio=-10.0, fcf_yield=None),
        PeerComparable(ticker="P3", ev_to_ebitda=24.0, pe_ratio=35.0, fcf_yield=0.04),
    ]
    med_ev, med_pe, implied, p25, p75 = compute_peer_comps_with_range(snapshot, peers)

    assert med_ev == pytest.approx(22.0)
    assert med_pe == pytest.approx(30.0)
    assert implied == pytest.approx(121.0)
    assert p25 is not None and p75 is not None
    assert p25 < p75


def test_peer_comps_all_missing_returns_none() -> None:
    """When no valid peer multiples exist, medians, implied price, and range are None."""
    snapshot = _sample_snapshot()
    peers = [PeerComparable(ticker="BAD", ev_to_ebitda=None, pe_ratio=-5.0, fcf_yield=None)]
    med_ev, med_pe, implied = compute_peer_comps(snapshot, peers)
    assert med_ev is None
    assert med_pe is None
    assert implied is None


def test_earnings_quality_flags_and_ev_fallback() -> None:
    """Verify High, Moderate, Low earnings quality ratings and EV accrual fallback."""
    high_snapshot = _sample_snapshot(
        net_income_ttm=4_000_000_000.0,
        operating_cash_flow_ttm=5_000_000_000.0,
        total_assets=80_000_000_000.0,
    )
    ratio, accrual, flag = compute_earnings_quality(high_snapshot)
    assert ratio == pytest.approx(1.25)
    assert accrual == pytest.approx(-1_000_000_000.0 / 80_000_000_000.0)
    assert flag == "High"

    moderate_snapshot = _sample_snapshot(
        net_income_ttm=4_000_000_000.0,
        operating_cash_flow_ttm=3_600_000_000.0,
        total_assets=None,
        market_cap=90_000_000_000.0,
        total_debt=15_000_000_000.0,
        cash_and_equivalents=5_000_000_000.0,
    )
    mod_ratio, mod_accrual, mod_flag = compute_earnings_quality(moderate_snapshot)
    assert mod_ratio == pytest.approx(0.90)
    assert moderate_snapshot.enterprise_value == pytest.approx(100_000_000_000.0)
    assert mod_accrual == pytest.approx(400_000_000.0 / 100_000_000_000.0)
    assert mod_flag == "Moderate"

    low_snapshot = _sample_snapshot(
        net_income_ttm=4_000_000_000.0,
        operating_cash_flow_ttm=2_800_000_000.0,
    )
    low_ratio, _, low_flag = compute_earnings_quality(low_snapshot)
    assert low_ratio == pytest.approx(0.70)
    assert low_flag == "Low"

    loss_snapshot = _sample_snapshot(net_income_ttm=-500_000_000.0)
    loss_ratio, _, loss_flag = compute_earnings_quality(loss_snapshot)
    assert loss_ratio == pytest.approx(0.0)
    assert loss_flag == "Low"


def test_run_valuation_analysis_integrates_reverse_dcf_and_exit_multiple() -> None:
    """Verify full run_valuation_analysis populates Reverse DCF, Exit Multiple, and comps range."""
    bundle = load_mock_market_data()
    analysis = run_valuation_analysis(
        bundle.snapshot,
        bundle.peers,
        wacc=0.095,
        terminal_growth_rate=0.025,
        target_exit_ev_ebitda=15.0,
    )
    assert analysis.earnings_quality_flag == "High"
    assert analysis.implied_fcf_cagr_5y is not None
    assert analysis.cagr_spread_vs_base == pytest.approx(
        analysis.implied_fcf_cagr_5y - analysis.dcf_assumptions["fcf_cagr"]
    )
    assert analysis.exit_multiple_dcf_value is not None
    assert analysis.peer_comps_p25_value is not None
    assert analysis.peer_comps_p75_value is not None
    assert analysis.peer_comps_p25_value <= analysis.peer_comps_p75_value
    assert analysis.implied_exit_ev_ebitda is not None
    assert analysis.dcf_sensitivity_matrix is not None
    assert len(analysis.dcf_sensitivity_matrix.wacc_values) == 5
    assert len(analysis.dcf_sensitivity_matrix.cagr_values) == 5
    assert analysis.dcf_sensitivity_matrix.grid[2][2] == pytest.approx(
        analysis.dcf_intrinsic_value_per_share, rel=1e-9
    )
    assert analysis.peer_median_forward_pe == pytest.approx(28.25)
    assert analysis.implied_y5_fcf is not None
    expected_y5_fcf = bundle.snapshot.free_cash_flow_ttm * (
        (1.0 + analysis.implied_fcf_cagr_5y) ** 5
    )
    assert abs(analysis.implied_y5_fcf - expected_y5_fcf) <= 10_000_000.0
    assert analysis.implied_y5_fcf_multiple == pytest.approx(
        analysis.implied_y5_fcf / bundle.snapshot.free_cash_flow_ttm
    )
    assert analysis.implied_y5_fcf_vs_current_revenue == pytest.approx(
        analysis.implied_y5_fcf / bundle.snapshot.revenue_ttm
    )

    multiples = compute_target_multiples(bundle.snapshot)
    assert multiples["forward_pe"] == pytest.approx(28.2)
    assert multiples["pe_ratio"] is not None
    assert multiples["pe_compression_pct"] == pytest.approx(
        (28.2 - multiples["pe_ratio"]) / multiples["pe_ratio"]
    )


def test_implied_exit_ev_ebitda_and_sensitivity_matrix_edge_cases() -> None:
    """Verify implied exit multiple formula, zero-clamped CAGR rows, and consistent EV/EBITDA."""
    snapshot = _sample_snapshot(
        market_cap=100_000_000_000.0,
        total_debt=20_000_000_000.0,
        cash_and_equivalents=5_000_000_000.0,
        ebitda_ttm=5_000_000_000.0,
    )
    assert snapshot.enterprise_value == pytest.approx(115_000_000_000.0)
    multiples = compute_target_multiples(snapshot)
    assert multiples["ev_to_ebitda"] == pytest.approx(23.0)

    implied_exit = compute_implied_exit_ev_ebitda(
        snapshot, fcf_cagr=0.10, wacc=0.095, terminal_growth_rate=0.025
    )
    # Since both FCF and EBITDA grow at (1 + cagr)^5, Terminal_Value / Terminal_EBITDA
    # simplifies to (FCF_0 / EBITDA_0) * (1 + g_term) / (WACC - g_term).
    expected_implied = (4.0 / 5.0) * (1.025 / 0.07)
    assert implied_exit == pytest.approx(expected_implied, rel=1e-9)

    neg_ebitda = _sample_snapshot(ebitda_ttm=-100.0)
    assert compute_implied_exit_ev_ebitda(neg_ebitda, fcf_cagr=0.10) is None

    matrix = compute_dcf_sensitivity_matrix(
        snapshot, base_wacc=0.095, base_cagr=0.02, terminal_growth_rate=0.025
    )
    assert matrix.cagr_values[0] == 0.0
    assert matrix.cagr_values[1] == 0.0
    assert matrix.cagr_values[2] == pytest.approx(0.02)
