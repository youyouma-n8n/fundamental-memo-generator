"""Unit tests for expanded financial data ingestion, ROIC, working capital, and fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from fundamental_memo.data_fetcher import (
    build_snapshot_from_raw,
    classify_ocf_net_income_gap_driver,
    compute_roic,
    compute_three_year_revenue_cagr,
    extract_historical_trajectory,
    extract_quarterly_trajectory,
    load_market_data_from_fixture,
    load_mock_market_data,
    sanitize_business_summary,
)
from fundamental_memo.schemas import DataFetchError


def test_load_mock_market_data_offline_has_all_expanded_fields() -> None:
    """Bundled mock data populates all expanded snapshot and peer attributes offline."""
    bundle = load_mock_market_data(ticker="AVGO", peer_tickers=["NVDA", "AMD", "MRVL", "QCOM"])
    snap = bundle.snapshot
    assert snap.ticker == "AVGO"
    assert snap.gross_margin_ttm is not None
    assert snap.operating_margin_ttm is not None
    assert snap.roic_ttm is not None
    assert snap.sbc_ttm is not None
    assert snap.sbc_adjusted_fcf_ttm == pytest.approx(snap.free_cash_flow_ttm - snap.sbc_ttm)
    assert snap.fifty_two_week_low == pytest.approx(119.76)
    assert snap.fifty_two_week_high == pytest.approx(185.16)
    assert snap.enterprise_value == pytest.approx(
        snap.market_cap + snap.total_debt - snap.cash_and_equivalents
    )
    assert snap.business_summary is not None
    assert len(snap.business_summary) <= 700
    assert snap.business_summary.count(".") >= 3
    assert snap.forward_pe == pytest.approx(28.2)
    assert snap.analyst_target_mean == pytest.approx(196.5)
    assert snap.analyst_count == 34
    assert len(snap.historical_trajectory) == 3
    assert [pt.period for pt in snap.historical_trajectory] == ["FY2022", "FY2023", "FY2024"]
    assert snap.ebitda_margin_ttm == pytest.approx(snap.ebitda_ttm / snap.revenue_ttm)
    assert snap.fcf_margin_ttm == pytest.approx(snap.free_cash_flow_ttm / snap.revenue_ttm)
    assert len(snap.quarterly_trajectory) == 4
    assert [pt.period for pt in snap.quarterly_trajectory] == [
        "2024-Q1",
        "2024-Q2",
        "2024-Q3",
        "2024-Q4",
    ]
    assert all(pt.free_cash_flow is not None for pt in snap.quarterly_trajectory)
    assert all(peer.forward_pe is not None for peer in bundle.peers)
    assert snap.working_capital_metrics is not None
    assert snap.working_capital_metrics.dso_days is not None
    assert snap.working_capital_metrics.dio_days is not None
    assert len(bundle.peers) == 4
    assert all(peer.revenue_growth_3y is not None for peer in bundle.peers)
    assert all(peer.market_cap is not None for peer in bundle.peers)


def test_expanded_snapshot_ratios_and_missing_fcf_fallback() -> None:
    """Verify FCF fallback, margins, ROIC with 0.21 tax fallback, SBC-adj FCF, and DSO/DIO."""
    raw_info: dict[str, object] = {
        "longName": "Example Semiconductor Corp",
        "sector": "Technology",
        "currentPrice": 50.0,
        "sharesOutstanding": 1_000_000_000.0,
        "marketCap": 50_000_000_000.0,
        # Intentionally stale/mismatched API enterpriseValue; must be overridden deterministically.
        "enterpriseValue": 999_999_999_999.0,
        "totalRevenue": 12_000_000_000.0,
        "grossProfits": 7_200_000_000.0,
        "operatingIncome": 3_600_000_000.0,
        "ebitda": 4_000_000_000.0,
        "netIncomeToCommon": 2_500_000_000.0,
        "operatingCashflow": 3_200_000_000.0,
        "capitalExpenditures": -700_000_000.0,
        "totalDebt": 8_000_000_000.0,
        "totalCash": 3_000_000_000.0,
        "revenueGrowth": 0.12,
        "fiftyTwoWeekLow": 38.0,
        "fiftyTwoWeekHigh": 58.0,
        "longBusinessSummary": (
            "Example Semiconductor builds custom AI chips and 800G optical switches. "
            "It serves global hyperscale data centers. "
            "Its Data Center segment drives cloud growth. "
            "Its Embedded segment supplies industrial silicon. "
            "This fifth sentence should be dropped cleanly."
        ),
    }
    fallbacks: dict[str, float | None] = {
        "total_equity": 15_000_000_000.0,
        "sbc_ttm": 500_000_000.0,
        "accounts_receivable": 1_200_000_000.0,
        "inventory": 600_000_000.0,
        "change_in_working_capital": -100_000_000.0,
    }
    snapshot = build_snapshot_from_raw("EXMP", raw_info, statement_fallbacks=fallbacks)

    assert snapshot.enterprise_value == pytest.approx(55_000_000_000.0)
    assert snapshot.business_summary is not None
    assert "fifth sentence" not in snapshot.business_summary
    assert "Data Center segment" in snapshot.business_summary
    assert "Embedded segment" in snapshot.business_summary
    assert "800G optical switches" in snapshot.business_summary
    assert snapshot.capex_ttm == pytest.approx(700_000_000.0)
    assert snapshot.free_cash_flow_ttm == pytest.approx(2_500_000_000.0)
    assert snapshot.sbc_adjusted_fcf_ttm == pytest.approx(2_000_000_000.0)
    assert snapshot.gross_margin_ttm == pytest.approx(0.60)
    assert snapshot.operating_margin_ttm == pytest.approx(0.30)

    # NOPAT with 21% fallback tax = 3.6B * 0.79 = 2.844B; Invested Capital = 8 + 15 - 3 = 20B
    assert snapshot.roic_ttm == pytest.approx((3_600_000_000.0 * 0.79) / 20_000_000_000.0)
    assert snapshot.net_cash == pytest.approx(-5_000_000_000.0)
    assert snapshot.net_cash_to_market_cap == pytest.approx(-0.10)
    assert snapshot.working_capital_metrics is not None
    assert snapshot.working_capital_metrics.dso_days == pytest.approx(36.5)
    # Cost of revenue derived as 12B - 7.2B = 4.8B -> DIO = (0.6 / 4.8) * 365 = 45.625
    assert snapshot.working_capital_metrics.dio_days == pytest.approx(45.625)
    assert "SBC" in snapshot.working_capital_metrics.ocf_net_income_gap_driver


def test_roic_returns_none_on_non_positive_invested_capital() -> None:
    """ROIC must return None instead of dividing by zero/negative invested capital."""
    result = compute_roic(
        operating_income_ttm=1_000_000_000.0,
        effective_tax_rate=None,
        total_debt=1_000_000_000.0,
        total_equity=2_000_000_000.0,
        cash_and_equivalents=5_000_000_000.0,
    )
    assert result is None


def test_ocf_net_income_gap_driver_classifies_working_capital_drag() -> None:
    """Working-capital cash outflow depressing OCF below Net Income is classified clearly."""
    explanation = classify_ocf_net_income_gap_driver(
        operating_cash_flow_ttm=1_500_000_000.0,
        net_income_ttm=2_200_000_000.0,
        capex_ttm=300_000_000.0,
        sbc_ttm=100_000_000.0,
        change_in_working_capital=-900_000_000.0,
    )
    assert "Working-capital cash outflow" in explanation


def test_compute_three_year_revenue_cagr() -> None:
    """Verify 3-year CAGR computation from chronological revenue series."""
    cagr = compute_three_year_revenue_cagr([100.0, 110.0, 121.0, 133.1])
    assert cagr == pytest.approx(0.10, rel=1e-6)
    assert compute_three_year_revenue_cagr([], fallback_growth=0.07) == pytest.approx(0.07)


def test_missing_critical_fields_raise_data_fetch_error() -> None:
    """Missing non-derivable fields must raise DataFetchError."""
    with pytest.raises(DataFetchError, match="Missing required financial fields"):
        build_snapshot_from_raw("BROKEN", {"longName": "Broken Inc."})


def test_custom_json_fixture_loader_validation(tmp_path: Path) -> None:
    """Verify valid custom fixtures load and malformed fixtures raise DataFetchError."""
    bundle = load_mock_market_data()
    valid_path = tmp_path / "valid_fixture.json"
    valid_path.write_text(bundle.model_dump_json(indent=2, by_alias=True), encoding="utf-8")

    loaded = load_market_data_from_fixture(valid_path)
    assert loaded.snapshot.ticker == "AVGO"
    assert loaded.snapshot.fifty_two_week_low == pytest.approx(119.76)

    bad_path = tmp_path / "bad_fixture.json"
    bad_path.write_text(json.dumps({"snapshot": {"ticker": "AVGO"}}), encoding="utf-8")
    with pytest.raises(DataFetchError, match="failed schema validation"):
        load_market_data_from_fixture(bad_path)


def test_sanitize_business_summary_caps_sentences_and_length() -> None:
    """sanitize_business_summary greedily keeps up to 4 sentences within 700 characters."""
    # Greedy 3-sentence retention when sentence 4 pushes total over 700 chars
    s1 = "Data Center silicon leads growth with " + ("A" * 160) + "."
    s2 = "Client processors scale across PCs with " + ("B" * 160) + "."
    s3 = "Embedded solutions serve industrial markets with " + ("C" * 150) + "."
    s4 = "Gaming GPUs expand consumer reach with " + ("D" * 160) + "."
    greedy = sanitize_business_summary(f"{s1} {s2} {s3} {s4}")
    assert greedy is not None
    assert len(greedy) <= 700
    assert "Data Center" in greedy
    assert "Client processors" in greedy
    assert "Embedded solutions" in greedy
    assert "Gaming GPUs" not in greedy

    # Single overly long first sentence truncates cleanly with ellipsis <= 700 chars
    long_text = " ".join(["Semiconductor"] * 120) + ". Second sentence here."
    sanitized = sanitize_business_summary(long_text)
    assert sanitized is not None
    assert len(sanitized) <= 700
    assert sanitized.endswith("...")
    assert sanitize_business_summary(None) is None
    assert sanitize_business_summary("   ") is None


def test_extract_historical_trajectory_from_annual_statements() -> None:
    """Extract 3 chronological fiscal years with revenue, operating margin, and FCF fallback."""
    income_stmt = pd.DataFrame(
        {
            pd.Timestamp("2024-10-31"): [51_574_000_000.0, 18_720_000_000.0],
            pd.Timestamp("2023-10-31"): [35_819_000_000.0, 16_190_000_000.0],
            pd.Timestamp("2022-10-31"): [33_203_000_000.0, 14_211_000_000.0],
            pd.Timestamp("2021-10-31"): [27_450_000_000.0, 10_980_000_000.0],
        },
        index=["Total Revenue", "Operating Income"],
    )
    cashflow_stmt = pd.DataFrame(
        {
            pd.Timestamp("2024-10-31"): [21_450_000_000.0, -550_000_000.0],
            pd.Timestamp("2023-10-31"): [18_085_000_000.0, -452_000_000.0],
            pd.Timestamp("2022-10-31"): [16_736_000_000.0, -424_000_000.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    trajectory = extract_historical_trajectory(income_stmt, cashflow_stmt)
    assert [pt.period for pt in trajectory] == ["FY2022", "FY2023", "FY2024"]
    assert trajectory[1].revenue == pytest.approx(35_819_000_000.0)
    assert trajectory[1].operating_margin == pytest.approx(16_190_000_000.0 / 35_819_000_000.0)
    assert trajectory[1].free_cash_flow == pytest.approx(17_633_000_000.0)


def test_extract_quarterly_trajectory_from_statements_and_fallbacks() -> None:
    """Extract 4 chronological quarters with margins, FCF fallback, and empty-frame safety."""
    q_income = pd.DataFrame(
        {
            pd.Timestamp("2025-10-31"): [14_050_000_000.0, 9_835_000_000.0, 4_215_000_000.0],
            pd.Timestamp("2025-07-31"): [13_100_000_000.0, 9_039_000_000.0, 3_800_000_000.0],
            pd.Timestamp("2025-04-30"): [12_500_000_000.0, 8_500_000_000.0, 3_500_000_000.0],
            pd.Timestamp("2025-01-31"): [12_000_000_000.0, 8_040_000_000.0, 3_240_000_000.0],
            pd.Timestamp("2024-10-31"): [11_200_000_000.0, 7_392_000_000.0, 3_024_000_000.0],
        },
        index=["Total Revenue", "Gross Profit", "Operating Income"],
    )
    q_cashflow = pd.DataFrame(
        {
            pd.Timestamp("2025-10-31"): [6_100_000_000.0, -140_000_000.0],
            pd.Timestamp("2025-07-31"): [5_500_000_000.0, -130_000_000.0],
            pd.Timestamp("2025-04-30"): [5_100_000_000.0, -120_000_000.0],
            pd.Timestamp("2025-01-31"): [4_800_000_000.0, -110_000_000.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    quarterly = extract_quarterly_trajectory(q_income, q_cashflow)
    assert [pt.period for pt in quarterly] == ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"]
    assert quarterly[0].gross_margin == pytest.approx(8_040_000_000.0 / 12_000_000_000.0)
    assert quarterly[0].operating_margin == pytest.approx(3_240_000_000.0 / 12_000_000_000.0)
    assert quarterly[0].free_cash_flow == pytest.approx(4_690_000_000.0)
    assert quarterly[-1].free_cash_flow == pytest.approx(5_960_000_000.0)
    assert extract_quarterly_trajectory(None, None) == []
    assert extract_quarterly_trajectory(pd.DataFrame(), pd.DataFrame()) == []


def test_four_quarter_ttm_reconciliation_overrides_mismatched_info() -> None:
    """Four complete quarters deterministically reconcile TTM revenue, margins, OCF, and FCF."""
    q_income = pd.DataFrame(
        {
            pd.Timestamp("2026-01-31"): [
                82_000_000_000.0,
                61_500_000_000.0,
                53_300_000_000.0,
                54_500_000_000.0,
                45_000_000_000.0,
            ],
            pd.Timestamp("2025-10-31"): [
                78_000_000_000.0,
                58_500_000_000.0,
                50_700_000_000.0,
                51_900_000_000.0,
                42_500_000_000.0,
            ],
            pd.Timestamp("2025-07-31"): [
                73_000_000_000.0,
                54_750_000_000.0,
                47_450_000_000.0,
                48_600_000_000.0,
                40_000_000_000.0,
            ],
            pd.Timestamp("2025-04-30"): [
                70_000_000_000.0,
                52_500_000_000.0,
                45_500_000_000.0,
                46_500_000_000.0,
                38_500_000_000.0,
            ],
        },
        index=["Total Revenue", "Gross Profit", "Operating Income", "EBITDA", "Net Income"],
    )
    q_cashflow = pd.DataFrame(
        {
            pd.Timestamp("2026-01-31"): [29_000_000_000.0, -1_400_000_000.0, 1_300_000_000.0],
            pd.Timestamp("2025-10-31"): [27_000_000_000.0, -1_300_000_000.0, 1_250_000_000.0],
            pd.Timestamp("2025-07-31"): [25_000_000_000.0, -1_200_000_000.0, 1_200_000_000.0],
            pd.Timestamp("2025-04-30"): [24_000_000_000.0, -1_100_000_000.0, 1_150_000_000.0],
        },
        index=["Operating Cash Flow", "Capital Expenditure", "Stock Based Compensation"],
    )
    quarters = extract_quarterly_trajectory(q_income, q_cashflow)
    # Deliberately stale/mismatched .info summary values (NVDA-style divergence)
    mismatched_info: dict[str, object] = {
        "longName": "NVIDIA Corporation",
        "sector": "Technology",
        "currentPrice": 140.0,
        "sharesOutstanding": 24_500_000_000.0,
        "marketCap": 3_430_000_000_000.0,
        "totalRevenue": 361_800_000_000.0,
        "ebitda": 130_000_000_000.0,
        "netIncomeToCommon": 110_000_000_000.0,
        "operatingCashflow": 90_000_000_000.0,
        "capitalExpenditures": -3_000_000_000.0,
        "freeCashflow": 87_000_000_000.0,
        "operatingMargins": 0.36,
        "totalDebt": 10_000_000_000.0,
        "totalCash": 40_000_000_000.0,
    }
    snap = build_snapshot_from_raw(
        "NVDA",
        mismatched_info,
        statement_fallbacks={"total_equity": 75_000_000_000.0},
        quarterly_trajectory=quarters,
    )
    assert snap.revenue_ttm == pytest.approx(303_000_000_000.0)
    assert snap.operating_margin_ttm == pytest.approx(196_950_000_000.0 / 303_000_000_000.0)
    assert snap.ebitda_ttm == pytest.approx(201_500_000_000.0)
    assert snap.operating_cash_flow_ttm == pytest.approx(105_000_000_000.0)
    assert snap.capex_ttm == pytest.approx(5_000_000_000.0)
    assert snap.free_cash_flow_ttm == pytest.approx(100_000_000_000.0)
    assert snap.fcf_margin_ttm == pytest.approx(100_000_000_000.0 / 303_000_000_000.0)
    assert snap.ebitda_margin_ttm == pytest.approx(201_500_000_000.0 / 303_000_000_000.0)
    assert snap.sbc_ttm == pytest.approx(4_900_000_000.0)

    # Missing quarterly EBITDA falls back to .info EBITDA while keeping 4Q revenue/OCF/FCF
    quarters_no_ebitda = [q.model_copy(update={"ebitda": None}) for q in quarters]
    snap_fallback_ebitda = build_snapshot_from_raw(
        "NVDA", mismatched_info, quarterly_trajectory=quarters_no_ebitda
    )
    assert snap_fallback_ebitda.revenue_ttm == pytest.approx(303_000_000_000.0)
    assert snap_fallback_ebitda.ebitda_ttm == pytest.approx(130_000_000_000.0)
    assert snap_fallback_ebitda.ebitda_margin_ttm == pytest.approx(
        130_000_000_000.0 / 303_000_000_000.0
    )

    # Fewer than 4 quarters falls back cleanly to .info summary totals
    snap_short = build_snapshot_from_raw(
        "NVDA", mismatched_info, quarterly_trajectory=quarters[:3]
    )
    assert snap_short.revenue_ttm == pytest.approx(361_800_000_000.0)
    assert snap_short.operating_margin_ttm == pytest.approx(0.36)
