"""Unit tests for Pydantic v2 data contracts and InvestmentMemoSchema word-budget validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fundamental_memo.schemas import (
    FinancialSnapshot,
    InvestmentMemoOutput,
    InvestmentMemoSchema,
    QuarterlyPoint,
)


def _valid_memo_payload() -> dict[str, object]:
    return {
        "executive_thesis": (
            "Broadcom trades at $170.00 versus base DCF of $97.25 and comps-implied $160.18."
        ),
        "valuation_and_debate": (
            "Perpetuity DCF yields $97.25 while Reverse DCF embeds 28.4% FCF CAGR versus "
            "15.0% base assumptions; the debate centers on secular growth versus peak multiples."
        ),
        "profitability_and_cash_quality": (
            "Gross margin of 64.2%, operating margin of 36.3%, and 12.6% ROIC back High "
            "earnings quality with 1.51x OCF/NI and $15.45B SBC-adjusted FCF."
        ),
        "bull_case": [
            "Durable 64.2% gross margin sustains 12.6% ROIC.",
            "Historical 23.2% revenue CAGR outpaces conservative baseline assumptions.",
            "High 1.51x cash conversion accelerates balance-sheet deleveraging.",
        ],
        "bear_case": [
            "Growth deceleration below 23.2% triggers multiple compression.",
            "Wide peer dispersion exposes 55.9x P/E to re-rating risk.",
            "Gross debt of $67.50B increases refinancing spread sensitivity.",
        ],
        "key_downside_risks": [
            "Operating margin slipping below 36.3% signals pricing pressure.",
            "DSO rising beyond 31.3 days warns of working-capital strain.",
            "A 100 bps WACC increase above 9.50% compresses terminal value.",
        ],
    }


def test_valid_investment_memo_schema_passes() -> None:
    """Valid InvestmentMemoSchema (and alias InvestmentMemoOutput) satisfies all constraints."""
    memo = InvestmentMemoSchema.model_validate(_valid_memo_payload())
    assert InvestmentMemoOutput is InvestmentMemoSchema
    assert len(memo.bull_case) == 3
    assert len(memo.bear_case) == 3
    assert 3 <= len(memo.key_downside_risks) <= 4


def test_rejects_executive_thesis_over_60_words() -> None:
    """executive_thesis exceeding 60 words must be rejected."""
    payload = _valid_memo_payload()
    payload["executive_thesis"] = " ".join(["word"] * 61)
    with pytest.raises(ValidationError, match="60-word limit"):
        InvestmentMemoSchema.model_validate(payload)


def test_rejects_valuation_and_debate_over_150_words() -> None:
    """valuation_and_debate exceeding 150 words must be rejected."""
    payload = _valid_memo_payload()
    payload["valuation_and_debate"] = " ".join(["debate"] * 151)
    with pytest.raises(ValidationError, match="150-word limit"):
        InvestmentMemoSchema.model_validate(payload)


def test_rejects_profitability_and_cash_quality_over_120_words() -> None:
    """profitability_and_cash_quality exceeding 120 words must be rejected."""
    payload = _valid_memo_payload()
    payload["profitability_and_cash_quality"] = " ".join(["margin"] * 121)
    with pytest.raises(ValidationError, match="120-word limit"):
        InvestmentMemoSchema.model_validate(payload)


def test_rejects_bullet_list_word_budgets_and_counts() -> None:
    """bull_case/bear_case/key_downside_risks enforce bullet counts and 90-word totals."""
    payload_short_bull = _valid_memo_payload()
    payload_short_bull["bull_case"] = ["Only one.", "Only two."]
    with pytest.raises(ValidationError, match="exactly 3"):
        InvestmentMemoSchema.model_validate(payload_short_bull)

    payload_long_bear = _valid_memo_payload()
    payload_long_bear["bear_case"] = [
        " ".join(["bear"] * 35),
        " ".join(["bear"] * 35),
        " ".join(["bear"] * 35),
    ]
    with pytest.raises(ValidationError, match="90-word total limit"):
        InvestmentMemoSchema.model_validate(payload_long_bear)

    payload_too_few_risks = _valid_memo_payload()
    payload_too_few_risks["key_downside_risks"] = ["Risk 1.", "Risk 2."]
    with pytest.raises(ValidationError, match="3 to 4"):
        InvestmentMemoSchema.model_validate(payload_too_few_risks)

    payload_extra = _valid_memo_payload()
    payload_extra["hallucinated_field"] = "unexpected"
    with pytest.raises(ValidationError):
        InvestmentMemoSchema.model_validate(payload_extra)


def test_financial_snapshot_derived_fields_and_52w_aliases() -> None:
    """FinancialSnapshot auto-derives net_cash/sbc_adjusted_fcf and serializes 52w aliases."""
    snapshot = FinancialSnapshot(
        ticker=" avgo ",
        company_name="Broadcom Inc.",
        sector="Technology",
        current_price=170.0,
        market_cap=793_900_000_000.0,
        enterprise_value=852_100_000_000.0,
        revenue_ttm=51_574_000_000.0,
        ebitda_ttm=27_850_000_000.0,
        net_income_ttm=14_200_000_000.0,
        operating_cash_flow_ttm=21_450_000_000.0,
        capex_ttm=550_000_000.0,
        free_cash_flow_ttm=20_900_000_000.0,
        total_debt=67_500_000_000.0,
        cash_and_equivalents=9_300_000_000.0,
        shares_outstanding=4_670_000_000.0,
        historical_revenue_growth_3y=0.232,
        sbc_ttm=5_450_000_000.0,
        fifty_two_week_low=119.76,
        fifty_two_week_high=185.16,
    )
    assert snapshot.ticker == "AVGO"
    assert snapshot.enterprise_value == pytest.approx(
        snapshot.market_cap + snapshot.total_debt - snapshot.cash_and_equivalents
    )
    assert snapshot.net_cash == pytest.approx(-58_200_000_000.0)
    assert snapshot.net_cash_to_market_cap == pytest.approx(-58_200_000_000.0 / 793_900_000_000.0)
    assert snapshot.sbc_adjusted_fcf_ttm == pytest.approx(15_450_000_000.0)
    dumped = snapshot.model_dump(by_alias=True)
    assert dumped["52w_low"] == pytest.approx(119.76)
    assert dumped["52w_high"] == pytest.approx(185.16)
    assert snapshot.ebitda_margin_ttm == pytest.approx(27_850_000_000.0 / 51_574_000_000.0)
    assert snapshot.fcf_margin_ttm == pytest.approx(20_900_000_000.0 / 51_574_000_000.0)


def test_financial_snapshot_margins_fallback_on_non_positive_revenue() -> None:
    """ebitda_margin_ttm and fcf_margin_ttm fall back to None when revenue_ttm <= 0."""
    snapshot = FinancialSnapshot(
        ticker="PRE",
        company_name="Pre-Revenue Biotech",
        sector="Healthcare",
        current_price=12.0,
        market_cap=1_200_000_000.0,
        enterprise_value=1_000_000_000.0,
        revenue_ttm=0.0,
        ebitda_ttm=-50_000_000.0,
        net_income_ttm=-60_000_000.0,
        operating_cash_flow_ttm=-45_000_000.0,
        capex_ttm=5_000_000.0,
        free_cash_flow_ttm=-50_000_000.0,
        total_debt=0.0,
        cash_and_equivalents=200_000_000.0,
        shares_outstanding=100_000_000.0,
        historical_revenue_growth_3y=0.0,
    )
    assert snapshot.ebitda_margin_ttm is None
    assert snapshot.fcf_margin_ttm is None


def test_quarterly_point_validation_and_snapshot_attachment() -> None:
    """QuarterlyPoint validates period, optional flow fields, and backward compatibility."""
    q_point = QuarterlyPoint(
        period="2025-Q3",
        revenue=14_005_000_000.0,
        gross_margin=0.748,
        operating_margin=0.281,
        free_cash_flow=5_480_000_000.0,
    )
    assert q_point.period == "2025-Q3"
    assert q_point.gross_margin == pytest.approx(0.748)
    assert q_point.operating_income is None
    assert q_point.operating_cash_flow is None
    assert q_point.capex is None

    q_full = QuarterlyPoint(
        period="2025-Q4",
        revenue=75_750_000_000.0,
        gross_profit=56_812_500_000.0,
        operating_income=49_237_500_000.0,
        ebitda=50_000_000_000.0,
        net_income=42_000_000_000.0,
        operating_cash_flow=26_250_000_000.0,
        capex=1_250_000_000.0,
        sbc=1_100_000_000.0,
        free_cash_flow=25_000_000_000.0,
    )
    assert q_full.operating_income == pytest.approx(49_237_500_000.0)
    assert q_full.capex == pytest.approx(1_250_000_000.0)
    with pytest.raises(ValidationError):
        QuarterlyPoint(period="", revenue=1_000.0)
