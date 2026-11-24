"""Pydantic v2 data contracts and domain exceptions for the fundamental memo pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class FundamentalMemoError(Exception):
    """Base exception for all fundamental memo pipeline errors."""


class DataFetchError(FundamentalMemoError):
    """Raised when market or financial statement data cannot be fetched or validated."""


class ValuationError(FundamentalMemoError):
    """Raised when quantitative valuation inputs or calculations are invalid."""


class NegativeFreeCashFlowError(ValuationError):
    """Raised when a standard DCF cannot be computed due to non-positive base Free Cash Flow."""


class SynthesisError(FundamentalMemoError):
    """Raised when LLM synthesis fails connectivity, parsing, or schema validation."""


class GroundingAuditError(SynthesisError):
    """Raised when generated prose violates numeric grounding or Single-Mention rules."""


class MemoWordLimitError(FundamentalMemoError):
    """Raised when a rendered Markdown memo exceeds the one-page word count limit."""


def count_words(text: str) -> int:
    """Count whitespace-delimited words in a text block."""
    return len(text.split())


class HistoricalYearPoint(BaseModel):
    """Single completed fiscal year observation for 3-year trajectory visualization."""

    period: str = Field(..., min_length=1, description="Fiscal year label (e.g., FY2023).")
    revenue: float = Field(..., description="Annual fiscal-year revenue in USD.")
    operating_margin: float | None = Field(
        default=None, description="Annual operating income divided by annual revenue."
    )
    free_cash_flow: float | None = Field(
        default=None, description="Annual free cash flow in USD."
    )


class QuarterlyPoint(BaseModel):
    """Single completed fiscal quarter observation for 4-quarter momentum and TTM reconciliation."""

    period: str = Field(..., min_length=1, description="Fiscal quarter label (e.g., 2025-Q3).")
    revenue: float = Field(..., description="Quarterly revenue in USD.")
    gross_margin: float | None = Field(
        default=None, description="Quarterly gross profit divided by quarterly revenue."
    )
    operating_margin: float | None = Field(
        default=None, description="Quarterly operating income divided by quarterly revenue."
    )
    free_cash_flow: float | None = Field(
        default=None, description="Quarterly free cash flow in USD."
    )
    gross_profit: float | None = Field(
        default=None, description="Quarterly gross profit in USD for 4Q TTM reconciliation."
    )
    operating_income: float | None = Field(
        default=None, description="Quarterly operating income in USD for 4Q TTM reconciliation."
    )
    ebitda: float | None = Field(
        default=None, description="Quarterly EBITDA in USD for 4Q TTM reconciliation."
    )
    net_income: float | None = Field(
        default=None, description="Quarterly net income in USD for 4Q TTM reconciliation."
    )
    operating_cash_flow: float | None = Field(
        default=None, description="Quarterly operating cash flow in USD for 4Q TTM reconciliation."
    )
    capex: float | None = Field(
        default=None,
        description="Quarterly CapEx magnitude (positive USD) for 4Q TTM reconciliation.",
    )
    sbc: float | None = Field(
        default=None,
        description="Quarterly stock-based compensation in USD for 4Q TTM reconciliation.",
    )


class WorkingCapitalMetrics(BaseModel):
    """Working capital efficiency ratios and deterministic OCF-vs-Net-Income gap explanation."""

    dso_days: float | None = Field(
        default=None,
        description="Days Sales Outstanding: (accounts_receivable / revenue_ttm) * 365.",
    )
    dio_days: float | None = Field(
        default=None,
        description="Days Inventory Outstanding: (inventory / cost_of_revenue_ttm) * 365.",
    )
    ocf_net_income_gap_driver: str = Field(
        ...,
        min_length=1,
        description=(
            "Deterministic classification comparing capex, SBC, and working capital to explain "
            "why OCF/Net Income deviates from 1.0x."
        ),
    )


class FinancialSnapshot(BaseModel):
    """Validated point-in-time market and TTM financial statement metrics for a target equity."""

    model_config = ConfigDict(populate_by_name=True)

    ticker: str = Field(..., min_length=1, description="Uppercase equity ticker symbol.")
    company_name: str = Field(..., min_length=1, description="Company legal or display name.")
    sector: str = Field(..., min_length=1, description="Primary GICS/market sector.")
    current_price: float = Field(..., gt=0.0, description="Latest market share price in USD.")
    market_cap: float = Field(..., gt=0.0, description="Market capitalization in USD.")
    enterprise_value: float = Field(..., gt=0.0, description="Enterprise value in USD.")
    revenue_ttm: float = Field(..., description="Trailing twelve-month revenue in USD.")
    ebitda_ttm: float = Field(..., description="Trailing twelve-month EBITDA in USD.")
    net_income_ttm: float = Field(..., description="Trailing twelve-month net income in USD.")
    operating_cash_flow_ttm: float = Field(
        ..., description="Trailing twelve-month operating cash flow in USD."
    )
    capex_ttm: float = Field(
        ..., description="Trailing twelve-month capital expenditures in USD."
    )
    free_cash_flow_ttm: float = Field(
        ..., description="Trailing twelve-month free cash flow in USD."
    )
    total_debt: float = Field(..., ge=0.0, description="Total balance-sheet debt in USD.")
    cash_and_equivalents: float = Field(
        ..., ge=0.0, description="Cash and short-term investments in USD."
    )
    shares_outstanding: float = Field(
        ..., gt=0.0, description="Diluted or basic shares outstanding."
    )
    historical_revenue_growth_3y: float = Field(
        ..., description="Three-year historical revenue CAGR as a decimal (e.g., 0.12 for 12%)."
    )
    total_assets: float | None = Field(
        default=None,
        description="Total assets in USD when available; used for the accrual ratio denominator.",
    )
    gross_margin_ttm: float | None = Field(
        default=None, description="Gross profit divided by TTM revenue."
    )
    operating_margin_ttm: float | None = Field(
        default=None, description="Operating income divided by TTM revenue."
    )
    ebitda_margin_ttm: float | None = Field(
        default=None, description="EBITDA divided by TTM revenue."
    )
    fcf_margin_ttm: float | None = Field(
        default=None, description="Free cash flow divided by TTM revenue."
    )
    roic_ttm: float | None = Field(
        default=None,
        description="Return on Invested Capital: NOPAT / (total_debt + total_equity - cash).",
    )
    sbc_ttm: float | None = Field(
        default=None, description="Trailing twelve-month stock-based compensation in USD."
    )
    sbc_adjusted_fcf_ttm: float | None = Field(
        default=None, description="Free cash flow minus stock-based compensation (TTM)."
    )
    net_cash: float | None = Field(
        default=None, description="Cash and equivalents minus total debt in USD."
    )
    net_cash_to_market_cap: float | None = Field(
        default=None, description="Net cash divided by market capitalization."
    )
    fifty_two_week_low: float | None = Field(
        default=None,
        validation_alias=AliasChoices("52w_low", "fifty_two_week_low"),
        serialization_alias="52w_low",
        description="52-week low share price in USD.",
    )
    fifty_two_week_high: float | None = Field(
        default=None,
        validation_alias=AliasChoices("52w_high", "fifty_two_week_high"),
        serialization_alias="52w_high",
        description="52-week high share price in USD.",
    )
    business_summary: str | None = Field(
        default=None,
        description=(
            "Sanitized qualitative business description (first 3-4 sentences, max 700 chars)."
        ),
    )
    forward_pe: float | None = Field(
        default=None, description="NTM / 1-year forward Price-to-Earnings ratio."
    )
    forward_ev_ebitda: float | None = Field(
        default=None, description="NTM / 1-year forward EV/EBITDA ratio when available."
    )
    analyst_target_mean: float | None = Field(
        default=None, description="Wall Street consensus mean target price in USD."
    )
    analyst_count: int | None = Field(
        default=None, ge=0, description="Number of covering sell-side analysts."
    )
    historical_trajectory: list[HistoricalYearPoint] = Field(
        default_factory=list,
        description="Last 3 completed fiscal years ordered oldest to newest.",
    )
    quarterly_trajectory: list[QuarterlyPoint] = Field(
        default_factory=list,
        description="Last 4 completed fiscal quarters ordered oldest to newest.",
    )
    working_capital_metrics: WorkingCapitalMetrics | None = Field(
        default=None, description="Working capital efficiency and OCF/NI gap diagnostics."
    )

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        """Strip whitespace and uppercase ticker symbols."""
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must be a non-empty string")
        return normalized

    @model_validator(mode="after")
    def populate_derived_liquidity_and_sbc_fields(self) -> FinancialSnapshot:
        """Enforce self-consistent EV and deterministically derive liquidity, SBC, and margins."""
        self.enterprise_value = self.market_cap + self.total_debt - self.cash_and_equivalents
        self.net_cash = self.cash_and_equivalents - self.total_debt
        if self.market_cap > 0.0:
            self.net_cash_to_market_cap = self.net_cash / self.market_cap
        if self.sbc_adjusted_fcf_ttm is None and self.sbc_ttm is not None:
            self.sbc_adjusted_fcf_ttm = self.free_cash_flow_ttm - self.sbc_ttm
        if self.revenue_ttm > 0.0:
            if self.ebitda_margin_ttm is None:
                self.ebitda_margin_ttm = self.ebitda_ttm / self.revenue_ttm
            if self.fcf_margin_ttm is None:
                self.fcf_margin_ttm = self.free_cash_flow_ttm / self.revenue_ttm
        else:
            self.ebitda_margin_ttm = None
            self.fcf_margin_ttm = None
        return self


class PeerComparable(BaseModel):
    """Validated comparable valuation multiples and growth metrics for a peer company."""

    ticker: str = Field(..., min_length=1, description="Peer ticker symbol.")
    ev_to_ebitda: float | None = Field(
        default=None, description="Enterprise Value to EBITDA multiple."
    )
    pe_ratio: float | None = Field(default=None, description="Trailing Price-to-Earnings ratio.")
    forward_pe: float | None = Field(default=None, description="Forward Price-to-Earnings ratio.")
    fcf_yield: float | None = Field(
        default=None, description="Free Cash Flow Yield (FCF / Market Cap) as a decimal."
    )
    revenue_growth_3y: float | None = Field(
        default=None, description="3-year revenue CAGR (or YoY growth fallback) as a decimal."
    )
    market_cap: float | None = Field(
        default=None, description="Peer market capitalization in USD for scatter bubble sizing."
    )

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        """Strip whitespace and uppercase peer ticker symbols."""
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("peer ticker must be a non-empty string")
        return normalized


class MarketDataBundle(BaseModel):
    """Container for target snapshot and peer comparables used by offline fixtures."""

    snapshot: FinancialSnapshot
    peers: list[PeerComparable] = Field(default_factory=list)


class DcfSensitivity(BaseModel):
    """DCF intrinsic value per share across a WACC sensitivity range."""

    low_wacc: float
    low_wacc_value_per_share: float
    base_wacc: float
    base_wacc_value_per_share: float
    high_wacc: float
    high_wacc_value_per_share: float


class DcfSensitivityMatrix(BaseModel):
    """5x5 DCF intrinsic share price matrix spanning WACC columns and 5Y FCF CAGR rows."""

    wacc_values: list[float]
    cagr_values: list[float]
    grid: list[list[float | None]]


class ValuationAnalysis(BaseModel):
    """Deterministic DCF, Reverse DCF, Exit Multiple, peer comps, and earnings quality outputs."""

    dcf_intrinsic_value_per_share: float
    dcf_upside_pct: float
    dcf_assumptions: dict[str, float]
    peer_median_ev_ebitda: float | None
    peer_median_pe: float | None
    peer_median_forward_pe: float | None = None
    implied_value_by_comps: float | None
    ocf_to_net_income_ratio: float
    accrual_ratio: float
    earnings_quality_flag: Literal["High", "Moderate", "Low"]
    implied_fcf_cagr_5y: float | None = None
    cagr_spread_vs_base: float | None = None
    implied_y5_fcf: float | None = None
    implied_y5_fcf_multiple: float | None = None
    implied_y5_fcf_vs_current_revenue: float | None = None
    exit_multiple_dcf_value: float | None = None
    exit_multiple_low_wacc_value: float | None = None
    exit_multiple_high_wacc_value: float | None = None
    implied_exit_ev_ebitda: float | None = None
    dcf_sensitivity_matrix: DcfSensitivityMatrix | None = None
    peer_comps_p25_value: float | None = None
    peer_comps_p75_value: float | None = None


class InvestmentMemoSchema(BaseModel):
    """Strictly bounded 6-section institutional memo narrative enforced from synthesis."""

    model_config = ConfigDict(extra="forbid")

    executive_thesis: str = Field(
        ...,
        min_length=1,
        description="Max 60 words: core stance, price vs. DCF/Comps spread, primary catalyst/risk.",
    )
    valuation_and_debate: str = Field(
        ...,
        min_length=1,
        description=(
            "Max 150 words: compare Base DCF, Reverse DCF, and Peer Comps, explaining why the "
            "market prices the stock at a discount or premium."
        ),
    )
    profitability_and_cash_quality: str = Field(
        ...,
        min_length=1,
        description=(
            "Max 120 words: analyze Gross/Operating Margins, ROIC, SBC-adjusted FCF, and explain "
            "the driver behind OCF/Net Income and Accrual Ratio."
        ),
    )
    bull_case: list[str] = Field(
        ...,
        description=(
            "Exactly 3 bullets, max 90 words total: operational upside drivers and margin/ROIC "
            "durability. Must not repeat exact DCF/Comps share price figures."
        ),
    )
    bear_case: list[str] = Field(
        ...,
        description=(
            "Exactly 3 bullets, max 90 words total: multiple compression, growth deceleration vs. "
            "Reverse DCF expectations, and peer dispersion risks. Must not repeat exact DCF/Comps "
            "share price figures."
        ),
    )
    key_downside_risks: list[str] = Field(
        ...,
        description=(
            "3 to 4 bullets, max 90 words total: actionable monitoring triggers such as margin "
            "thresholds, DSO/inventory build, or WACC sensitivity."
        ),
    )

    @field_validator("executive_thesis")
    @classmethod
    def validate_executive_thesis_words(cls, value: str) -> str:
        """Ensure executive_thesis is non-empty and at most 60 words."""
        cleaned = value.strip()
        word_count = count_words(cleaned)
        if word_count == 0:
            raise ValueError("executive_thesis cannot be empty")
        if word_count > 60:
            raise ValueError(f"executive_thesis exceeds 60-word limit ({word_count} words)")
        return cleaned

    @field_validator("valuation_and_debate")
    @classmethod
    def validate_valuation_and_debate_words(cls, value: str) -> str:
        """Ensure valuation_and_debate is non-empty and at most 150 words."""
        cleaned = value.strip()
        word_count = count_words(cleaned)
        if word_count == 0:
            raise ValueError("valuation_and_debate cannot be empty")
        if word_count > 150:
            raise ValueError(f"valuation_and_debate exceeds 150-word limit ({word_count} words)")
        return cleaned

    @field_validator("profitability_and_cash_quality")
    @classmethod
    def validate_profitability_and_cash_quality_words(cls, value: str) -> str:
        """Ensure profitability_and_cash_quality is non-empty and at most 120 words."""
        cleaned = value.strip()
        word_count = count_words(cleaned)
        if word_count == 0:
            raise ValueError("profitability_and_cash_quality cannot be empty")
        if word_count > 120:
            raise ValueError(
                f"profitability_and_cash_quality exceeds 120-word limit ({word_count} words)"
            )
        return cleaned

    @field_validator("bull_case", "bear_case")
    @classmethod
    def validate_three_case_bullets(cls, values: list[str]) -> list[str]:
        """Ensure bull and bear cases each have 3 non-empty bullets totaling at most 90 words."""
        if len(values) != 3:
            raise ValueError(f"must contain exactly 3 bullet points (got {len(values)})")
        cleaned_items: list[str] = []
        total_words = 0
        for index, item in enumerate(values, start=1):
            cleaned = item.strip()
            item_words = count_words(cleaned)
            if item_words == 0:
                raise ValueError(f"bullet {index} cannot be empty")
            total_words += item_words
            cleaned_items.append(cleaned)
        if total_words > 90:
            raise ValueError(f"bullets exceed 90-word total limit ({total_words} words)")
        return cleaned_items

    @field_validator("key_downside_risks")
    @classmethod
    def validate_key_downside_risks(cls, values: list[str]) -> list[str]:
        """Ensure key_downside_risks has 3 to 4 non-empty bullets totaling at most 90 words."""
        if not 3 <= len(values) <= 4:
            raise ValueError(f"key_downside_risks must contain 3 to 4 items (got {len(values)})")
        cleaned_items: list[str] = []
        total_words = 0
        for index, item in enumerate(values, start=1):
            cleaned = item.strip()
            item_words = count_words(cleaned)
            if item_words == 0:
                raise ValueError(f"risk {index} cannot be empty")
            total_words += item_words
            cleaned_items.append(cleaned)
        if total_words > 90:
            raise ValueError(
                f"key_downside_risks exceeds 90-word total limit ({total_words} words)"
            )
        return cleaned_items


InvestmentMemoOutput = InvestmentMemoSchema
