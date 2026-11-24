"""Deterministic market data ingestion via yfinance or local offline JSON fixtures."""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Mapping, Sequence
from importlib import resources
from pathlib import Path
from typing import Any

import yfinance as yf
from pydantic import ValidationError

from fundamental_memo.schemas import (
    DataFetchError,
    FinancialSnapshot,
    HistoricalYearPoint,
    MarketDataBundle,
    PeerComparable,
    QuarterlyPoint,
    WorkingCapitalMetrics,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_EFFECTIVE_TAX_RATE = 0.21
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def sanitize_business_summary(
    raw_summary: object, *, max_sentences: int = 4, max_chars: int = 700
) -> str | None:
    """Retain up to the first 4 complete sentences fitting within 700 characters."""
    if not isinstance(raw_summary, str):
        return None
    normalized = " ".join(raw_summary.split()).strip()
    if not normalized:
        return None

    sentences = [s.strip() for s in _SENTENCE_SPLIT_PATTERN.split(normalized) if s.strip()]
    if not sentences:
        return None

    kept: list[str] = []
    for sentence in sentences[:max_sentences]:
        candidate = " ".join([*kept, sentence])
        if len(candidate) <= max_chars:
            kept.append(sentence)
        else:
            break

    if kept:
        return " ".join(kept)

    first_sentence = sentences[0]
    truncated = first_sentence[: max_chars - 3].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{truncated}..." if truncated else f"{first_sentence[: max_chars - 3]}..."


def _to_finite_float(value: object) -> float | None:
    """Convert a raw scalar value into a finite float, returning None if invalid."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    try:
        numeric = float(str(value))
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    """Divide numerator by denominator, returning None if either is missing or denominator <= 0."""
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _format_compact_usd(value: float) -> str:
    """Format a USD dollar amount compactly for deterministic gap-driver labels."""
    abs_val = abs(value)
    if abs_val >= 1_000_000_000.0:
        return f"${value / 1_000_000_000.0:,.2f}B"
    if abs_val >= 1_000_000.0:
        return f"${value / 1_000_000.0:,.1f}M"
    return f"${value:,.0f}"


def _extract_latest_statement_value(
    statement_frame: Any, candidate_labels: Sequence[str]
) -> float | None:
    """Extract the most recent finite numeric value matching any row label in a DataFrame."""
    if statement_frame is None or getattr(statement_frame, "empty", True):
        return None
    index_values = list(statement_frame.index)
    for label in candidate_labels:
        if label in index_values:
            row = statement_frame.loc[label]
            for raw_value in row:
                parsed = _to_finite_float(raw_value)
                if parsed is not None:
                    return parsed
    return None


def _format_fiscal_period_label(raw_column: object) -> str:
    """Format a statement column header (timestamp or string) as FY<YYYY> when possible."""
    year_attr = getattr(raw_column, "year", None)
    if isinstance(year_attr, int) and 1900 <= year_attr <= 2200:
        return f"FY{year_attr}"
    text = str(raw_column).strip()
    match = re.search(r"(20\d{2}|19\d{2})", text)
    if match:
        return f"FY{match.group(1)}"
    return text or "FY"


def _extract_row_series_by_period(
    statement_frame: Any, candidate_labels: Sequence[str]
) -> dict[str, float]:
    """Extract a mapping of fiscal period label -> finite float for the first matching row."""
    if statement_frame is None or getattr(statement_frame, "empty", True):
        return {}
    index_values = list(statement_frame.index)
    for label in candidate_labels:
        if label in index_values:
            row = statement_frame.loc[label]
            result: dict[str, float] = {}
            for col_key, raw_value in row.items():
                parsed = _to_finite_float(raw_value)
                if parsed is not None:
                    result[_format_fiscal_period_label(col_key)] = parsed
            if result:
                return result
    return {}


def extract_historical_trajectory(
    income_statement: Any, cashflow_statement: Any, *, max_years: int = 3
) -> list[HistoricalYearPoint]:
    """Extract up to the last 3 completed fiscal years (oldest to newest) from annual statements."""
    revenue_by_period = _extract_row_series_by_period(
        income_statement, ("Total Revenue", "Operating Revenue", "Revenue")
    )
    if not revenue_by_period:
        return []

    op_income_by_period = _extract_row_series_by_period(
        income_statement, ("Operating Income", "EBIT")
    )
    fcf_by_period = _extract_row_series_by_period(cashflow_statement, ("Free Cash Flow",))
    ocf_by_period = _extract_row_series_by_period(
        cashflow_statement,
        ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    )
    capex_by_period = _extract_row_series_by_period(
        cashflow_statement, ("Capital Expenditure", "Capital Expenditures")
    )

    sorted_periods = sorted(
        (period for period, rev in revenue_by_period.items() if rev > 0.0)
    )
    recent_periods = sorted_periods[-max_years:]

    trajectory: list[HistoricalYearPoint] = []
    for period in recent_periods:
        revenue = revenue_by_period[period]
        op_income = op_income_by_period.get(period)
        operating_margin = (
            op_income / revenue if (op_income is not None and revenue > 0.0) else None
        )

        fcf = fcf_by_period.get(period)
        if fcf is None and period in ocf_by_period:
            capex = abs(capex_by_period.get(period, 0.0))
            fcf = ocf_by_period[period] - capex

        trajectory.append(
            HistoricalYearPoint(
                period=period,
                revenue=revenue,
                operating_margin=operating_margin,
                free_cash_flow=fcf,
            )
        )
    return trajectory


def _format_quarter_period_label(raw_column: object) -> str:
    """Format a quarterly statement column header as YYYY-Q<1..4> when possible."""
    year_attr = getattr(raw_column, "year", None)
    month_attr = getattr(raw_column, "month", None)
    if (
        isinstance(year_attr, int)
        and 1900 <= year_attr <= 2200
        and isinstance(month_attr, int)
        and 1 <= month_attr <= 12
    ):
        quarter = ((month_attr - 1) // 3) + 1
        return f"{year_attr}-Q{quarter}"

    text = str(raw_column).strip()
    quarter_match = re.search(r"(20\d{2}|19\d{2})[-_\s]?Q([1-4])", text, flags=re.IGNORECASE)
    if quarter_match:
        return f"{quarter_match.group(1)}-Q{quarter_match.group(2)}"
    iso_match = re.search(r"(20\d{2}|19\d{2})-(\d{2})", text)
    if iso_match:
        month = int(iso_match.group(2))
        if 1 <= month <= 12:
            quarter = ((month - 1) // 3) + 1
            return f"{iso_match.group(1)}-Q{quarter}"
    return text or "Q"


def _extract_row_series_by_quarter(
    statement_frame: Any, candidate_labels: Sequence[str]
) -> dict[str, float]:
    """Extract a mapping of YYYY-Q# quarter label -> finite float for the first matching row."""
    if statement_frame is None or getattr(statement_frame, "empty", True):
        return {}
    index_values = list(statement_frame.index)
    for label in candidate_labels:
        if label in index_values:
            row = statement_frame.loc[label]
            result: dict[str, float] = {}
            for col_key, raw_value in row.items():
                parsed = _to_finite_float(raw_value)
                if parsed is not None:
                    result[_format_quarter_period_label(col_key)] = parsed
            if result:
                return result
    return {}


def extract_quarterly_trajectory(
    quarterly_income_stmt: Any, quarterly_cashflow: Any, *, max_quarters: int = 4
) -> list[QuarterlyPoint]:
    """Extract up to the 4 most recent completed fiscal quarters (oldest to newest)."""
    revenue_by_quarter = _extract_row_series_by_quarter(
        quarterly_income_stmt, ("Total Revenue", "Operating Revenue", "Revenue")
    )
    if not revenue_by_quarter:
        return []

    gross_profit_by_quarter = _extract_row_series_by_quarter(
        quarterly_income_stmt, ("Gross Profit",)
    )
    op_income_by_quarter = _extract_row_series_by_quarter(
        quarterly_income_stmt, ("Operating Income", "EBIT")
    )
    ebitda_by_quarter = _extract_row_series_by_quarter(
        quarterly_income_stmt, ("EBITDA", "Normalized EBITDA")
    )
    net_income_by_quarter = _extract_row_series_by_quarter(
        quarterly_income_stmt, ("Net Income", "Net Income Common Stockholders")
    )
    fcf_by_quarter = _extract_row_series_by_quarter(quarterly_cashflow, ("Free Cash Flow",))
    ocf_by_quarter = _extract_row_series_by_quarter(
        quarterly_cashflow,
        ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
    )
    capex_by_quarter = _extract_row_series_by_quarter(
        quarterly_cashflow, ("Capital Expenditure", "Capital Expenditures")
    )
    sbc_by_quarter = _extract_row_series_by_quarter(
        quarterly_cashflow, ("Stock Based Compensation",)
    )

    sorted_quarters = sorted(
        (period for period, rev in revenue_by_quarter.items() if rev > 0.0)
    )
    recent_quarters = sorted_quarters[-max_quarters:]

    trajectory: list[QuarterlyPoint] = []
    for period in recent_quarters:
        revenue = revenue_by_quarter[period]
        gross_profit = gross_profit_by_quarter.get(period)
        gross_margin = (
            gross_profit / revenue if (gross_profit is not None and revenue > 0.0) else None
        )
        op_income = op_income_by_quarter.get(period)
        operating_margin = (
            op_income / revenue if (op_income is not None and revenue > 0.0) else None
        )
        ebitda = ebitda_by_quarter.get(period)
        net_income = net_income_by_quarter.get(period)
        ocf = ocf_by_quarter.get(period)
        raw_capex = capex_by_quarter.get(period)
        capex_abs = abs(raw_capex) if raw_capex is not None else None
        raw_sbc = sbc_by_quarter.get(period)
        sbc_abs = abs(raw_sbc) if raw_sbc is not None else None

        fcf = fcf_by_quarter.get(period)
        if fcf is None and ocf is not None:
            fcf = ocf - (capex_abs if capex_abs is not None else 0.0)

        trajectory.append(
            QuarterlyPoint(
                period=period,
                revenue=revenue,
                gross_margin=gross_margin,
                operating_margin=operating_margin,
                free_cash_flow=fcf,
                gross_profit=gross_profit,
                operating_income=op_income,
                ebitda=ebitda,
                net_income=net_income,
                operating_cash_flow=ocf,
                capex=capex_abs,
                sbc=sbc_abs,
            )
        )
    return trajectory


def _extract_annual_revenues(income_statement: Any) -> list[float]:
    """Extract chronological annual revenue observations (oldest to newest) from an income stmt."""
    if income_statement is None or getattr(income_statement, "empty", True):
        return []
    candidate_labels = ("Total Revenue", "Operating Revenue", "Revenue")
    index_values = list(income_statement.index)
    for label in candidate_labels:
        if label in index_values:
            row = income_statement.loc[label]
            try:
                sorted_pairs = sorted(row.items(), key=lambda pair: str(pair[0]))
            except TypeError:
                sorted_pairs = list(reversed(list(row.items())))
            revenues: list[float] = []
            for _, raw_value in sorted_pairs:
                parsed = _to_finite_float(raw_value)
                if parsed is not None and parsed > 0.0:
                    revenues.append(parsed)
            if revenues:
                return revenues
    return []


def compute_three_year_revenue_cagr(
    annual_revenues: Sequence[float], fallback_growth: float | None = None
) -> float:
    """Compute a 3-year (or multi-year available) revenue CAGR from chronological revenues.

    Formula:
        CAGR = (revenue_latest / revenue_start) ** (1 / num_periods) - 1
    """
    positive_series = [value for value in annual_revenues if value > 0.0]
    if len(positive_series) >= 2:
        window = positive_series[-4:]
        num_periods = len(window) - 1
        start_revenue = window[0]
        end_revenue = window[-1]
        if start_revenue > 0.0 and end_revenue > 0.0 and num_periods > 0:
            return float((end_revenue / start_revenue) ** (1.0 / num_periods) - 1.0)
    if fallback_growth is not None and math.isfinite(fallback_growth):
        return fallback_growth
    return 0.0


def classify_ocf_net_income_gap_driver(
    *,
    operating_cash_flow_ttm: float,
    net_income_ttm: float,
    capex_ttm: float,
    sbc_ttm: float | None,
    change_in_working_capital: float | None,
) -> str:
    """Deterministically explain why OCF/Net Income deviates from 1.0x.

    Compares the OCF-minus-Net-Income gap against stock-based compensation (SBC),
    working-capital cash movements, and capital expenditures.
    """
    gap = operating_cash_flow_ttm - net_income_ttm
    sbc_abs = abs(sbc_ttm) if sbc_ttm is not None else 0.0
    wc_val = change_in_working_capital if change_in_working_capital is not None else 0.0
    capex_abs = abs(capex_ttm)

    if abs(gap) <= max(abs(net_income_ttm) * 0.05, 1.0):
        return (
            f"OCF closely tracks Net Income near 1.0x with CapEx of "
            f"{_format_compact_usd(capex_abs)}."
        )

    if gap > 0.0:
        if sbc_ttm is not None and sbc_abs >= abs(wc_val) and sbc_abs >= gap * 0.25:
            return (
                f"Non-cash SBC ({_format_compact_usd(sbc_abs)}) and amortization lift OCF above "
                f"Net Income, with CapEx at {_format_compact_usd(capex_abs)}."
            )
        if change_in_working_capital is not None and wc_val > 0.0 and wc_val >= sbc_abs:
            return (
                f"Working-capital cash inflow ({_format_compact_usd(wc_val)}) drives OCF above "
                f"Net Income, alongside CapEx of {_format_compact_usd(capex_abs)}."
            )
        return (
            f"Non-cash D&A and deferred accruals lift OCF above Net Income, with CapEx at "
            f"{_format_compact_usd(capex_abs)}."
        )

    if change_in_working_capital is not None and wc_val < 0.0:
        return (
            f"Working-capital cash outflow ({_format_compact_usd(abs(wc_val))}) drags OCF below "
            f"Net Income alongside CapEx of {_format_compact_usd(capex_abs)}."
        )
    if sbc_ttm is not None and sbc_abs > 0.0:
        return (
            f"Accrual expansion and working-capital absorption offset SBC "
            f"({_format_compact_usd(sbc_abs)}) add-backs, pushing OCF below Net Income."
        )
    return (
        f"Working-capital absorption and non-cash earnings accruals depress OCF below Net Income "
        f"with CapEx at {_format_compact_usd(capex_abs)}."
    )


def compute_roic(
    *,
    operating_income_ttm: float | None,
    effective_tax_rate: float | None,
    total_debt: float,
    total_equity: float | None,
    cash_and_equivalents: float,
) -> float | None:
    """Compute Return on Invested Capital (ROIC) in pure Python.

    Formula:
        NOPAT = operating_income_ttm * (1 - effective_tax_rate)
        Invested Capital = total_debt + total_equity - cash_and_equivalents
        ROIC = NOPAT / Invested Capital
    """
    if operating_income_ttm is None or total_equity is None:
        return None
    tax_rate = DEFAULT_EFFECTIVE_TAX_RATE
    if effective_tax_rate is not None and 0.0 <= effective_tax_rate <= 0.50:
        tax_rate = effective_tax_rate
    nopat = operating_income_ttm * (1.0 - tax_rate)
    invested_capital = total_debt + total_equity - cash_and_equivalents
    if invested_capital <= 0.0:
        return None
    return nopat / invested_capital


def build_snapshot_from_raw(
    ticker: str,
    info: Mapping[str, object],
    annual_revenues: Sequence[float] | None = None,
    statement_fallbacks: Mapping[str, float | None] | None = None,
    historical_trajectory: Sequence[HistoricalYearPoint] | None = None,
    quarterly_trajectory: Sequence[QuarterlyPoint] | None = None,
) -> FinancialSnapshot:
    """Construct and validate an expanded FinancialSnapshot from raw info and statements."""
    fallbacks = statement_fallbacks or {}
    normalized_ticker = ticker.strip().upper()

    def _pick(info_keys: Sequence[str], fallback_key: str | None = None) -> float | None:
        for key in info_keys:
            parsed = _to_finite_float(info.get(key))
            if parsed is not None:
                return parsed
        if fallback_key is not None:
            return fallbacks.get(fallback_key)
        return None

    current_price = _pick(("currentPrice", "regularMarketPrice", "previousClose"))
    shares_outstanding = _pick(("sharesOutstanding",))
    market_cap = _pick(("marketCap",))
    if market_cap is None and current_price is not None and shares_outstanding is not None:
        market_cap = current_price * shares_outstanding

    total_debt = _pick(("totalDebt",), "total_debt") or 0.0
    cash_and_equivalents = _pick(("totalCash",), "cash_and_equivalents") or 0.0
    # Always compute self-consistent Enterprise Value rather than trusting raw API enterpriseValue.
    enterprise_value: float | None = (
        market_cap + max(total_debt, 0.0) - max(cash_and_equivalents, 0.0)
        if market_cap is not None
        else None
    )

    quarterly_list = list(quarterly_trajectory or ())

    revenue_ttm = _pick(("totalRevenue",), "revenue_ttm")
    ebitda_ttm = _pick(("ebitda",), "ebitda_ttm")
    net_income_ttm = _pick(("netIncomeToCommon",), "net_income_ttm")
    operating_cash_flow_ttm = _pick(("operatingCashflow",), "operating_cash_flow_ttm")
    raw_capex = _pick(("capitalExpenditures",), "capex_ttm")
    capex_ttm = abs(raw_capex) if raw_capex is not None else 0.0

    free_cash_flow_ttm = _pick(("freeCashflow",), "free_cash_flow_ttm")
    if free_cash_flow_ttm is None and operating_cash_flow_ttm is not None:
        free_cash_flow_ttm = operating_cash_flow_ttm - abs(capex_ttm)

    gross_profit_ttm = _pick(("grossProfits",), "gross_profit_ttm")
    operating_income_ttm = _pick(("operatingIncome",), "operating_income_ttm")
    raw_sbc = _pick(("stockBasedCompensation",), "sbc_ttm")
    sbc_ttm = abs(raw_sbc) if raw_sbc is not None else None

    # Four-Quarter Sum TTM Reconciliation: whenever 4 valid completed quarters are available,
    # deterministically derive TTM flow metrics as exact 4Q sums so Quarterly (4Q) and TTM align.
    if len(quarterly_list) == 4:
        q_revs = [q.revenue for q in quarterly_list]
        if all(rev > 0.0 for rev in q_revs):
            revenue_ttm = sum(q_revs)

        if all(q.gross_profit is not None for q in quarterly_list):
            gross_profit_ttm = sum(
                q.gross_profit for q in quarterly_list if q.gross_profit is not None
            )
        elif all(q.gross_margin is not None for q in quarterly_list):
            gross_profit_ttm = sum(
                q.revenue * q.gross_margin for q in quarterly_list if q.gross_margin is not None
            )

        if all(q.operating_income is not None for q in quarterly_list):
            operating_income_ttm = sum(
                q.operating_income for q in quarterly_list if q.operating_income is not None
            )
        elif all(q.operating_margin is not None for q in quarterly_list):
            operating_income_ttm = sum(
                q.revenue * q.operating_margin
                for q in quarterly_list
                if q.operating_margin is not None
            )

        if all(q.ebitda is not None for q in quarterly_list):
            ebitda_ttm = sum(q.ebitda for q in quarterly_list if q.ebitda is not None)

        if all(q.net_income is not None for q in quarterly_list):
            net_income_ttm = sum(q.net_income for q in quarterly_list if q.net_income is not None)

        has_all_ocf = all(q.operating_cash_flow is not None for q in quarterly_list)
        has_all_capex = all(q.capex is not None for q in quarterly_list)
        if has_all_ocf:
            operating_cash_flow_ttm = sum(
                q.operating_cash_flow
                for q in quarterly_list
                if q.operating_cash_flow is not None
            )
        if has_all_capex:
            capex_ttm = sum(abs(q.capex) for q in quarterly_list if q.capex is not None)
        if has_all_ocf and has_all_capex and operating_cash_flow_ttm is not None:
            free_cash_flow_ttm = operating_cash_flow_ttm - capex_ttm
        elif all(q.free_cash_flow is not None for q in quarterly_list):
            free_cash_flow_ttm = sum(
                q.free_cash_flow for q in quarterly_list if q.free_cash_flow is not None
            )

        if all(q.sbc is not None for q in quarterly_list):
            sbc_ttm = sum(abs(q.sbc) for q in quarterly_list if q.sbc is not None)

    total_assets = _pick(("totalAssets",), "total_assets")
    fallback_growth = _pick(("revenueGrowth",))
    historical_revenue_growth_3y = compute_three_year_revenue_cagr(
        annual_revenues or (), fallback_growth=fallback_growth
    )

    required_fields: dict[str, float | None] = {
        "current_price": current_price,
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "revenue_ttm": revenue_ttm,
        "ebitda_ttm": ebitda_ttm,
        "net_income_ttm": net_income_ttm,
        "operating_cash_flow_ttm": operating_cash_flow_ttm,
        "free_cash_flow_ttm": free_cash_flow_ttm,
        "shares_outstanding": shares_outstanding,
    }
    missing = [name for name, value in required_fields.items() if value is None]
    if missing:
        missing_str = ", ".join(missing)
        raise DataFetchError(
            f"Missing required financial fields for {normalized_ticker}: {missing_str}."
        )

    cost_of_revenue_ttm = (
        revenue_ttm - gross_profit_ttm
        if (
            len(quarterly_list) == 4
            and revenue_ttm is not None
            and gross_profit_ttm is not None
            and revenue_ttm > gross_profit_ttm
        )
        else _pick(("costOfRevenue",), "cost_of_revenue_ttm")
    )
    if (
        cost_of_revenue_ttm is None
        and revenue_ttm is not None
        and gross_profit_ttm is not None
        and revenue_ttm > gross_profit_ttm
    ):
        cost_of_revenue_ttm = revenue_ttm - gross_profit_ttm

    gross_margin_ttm = _safe_divide(gross_profit_ttm, revenue_ttm)
    if gross_margin_ttm is None:
        gross_margin_ttm = _pick(("grossMargins",))

    operating_margin_ttm = _safe_divide(operating_income_ttm, revenue_ttm)
    if operating_margin_ttm is None:
        operating_margin_ttm = _pick(("operatingMargins",))
    if (
        operating_income_ttm is None
        and operating_margin_ttm is not None
        and revenue_ttm is not None
    ):
        operating_income_ttm = operating_margin_ttm * revenue_ttm

    total_equity = _pick(("totalStockholderEquity",), "total_equity")
    tax_provision = _pick((), "tax_provision")
    pretax_income = _pick((), "pretax_income")
    effective_tax_rate = _safe_divide(tax_provision, pretax_income)
    roic_ttm = compute_roic(
        operating_income_ttm=operating_income_ttm,
        effective_tax_rate=effective_tax_rate,
        total_debt=max(total_debt, 0.0),
        total_equity=total_equity,
        cash_and_equivalents=max(cash_and_equivalents, 0.0),
    )

    sbc_adjusted_fcf_ttm = (
        float(free_cash_flow_ttm) - sbc_ttm  # type: ignore[arg-type]
        if sbc_ttm is not None
        else None
    )

    net_cash = max(cash_and_equivalents, 0.0) - max(total_debt, 0.0)
    net_cash_to_market_cap = _safe_divide(net_cash, market_cap)

    fifty_two_week_low = _pick(("fiftyTwoWeekLow", "52w_low"))
    fifty_two_week_high = _pick(("fiftyTwoWeekHigh", "52w_high"))
    business_summary = sanitize_business_summary(
        info.get("longBusinessSummary") or info.get("business_summary")
    )
    raw_forward_pe = _pick(("forwardPE", "forward_pe"))
    forward_pe = raw_forward_pe if (raw_forward_pe is not None and raw_forward_pe > 0.0) else None

    raw_forward_ev_ebitda = _pick(("forwardEnterpriseToEbitda", "forward_ev_ebitda"))
    forward_ev_ebitda = (
        raw_forward_ev_ebitda
        if (raw_forward_ev_ebitda is not None and raw_forward_ev_ebitda > 0.0)
        else None
    )

    raw_target_mean = _pick(("targetMeanPrice", "analyst_target_mean"))
    analyst_target_mean = (
        raw_target_mean if (raw_target_mean is not None and raw_target_mean > 0.0) else None
    )
    raw_analyst_count = _pick(("numberOfAnalystOpinions", "analyst_count"))
    analyst_count = (
        int(round(raw_analyst_count))
        if (raw_analyst_count is not None and raw_analyst_count >= 0.0)
        else None
    )

    accounts_receivable = _pick(("accountsReceivable",), "accounts_receivable")
    inventory = _pick(("inventory",), "inventory")
    change_in_working_capital = _pick(("changeInWorkingCapital",), "change_in_working_capital")

    dso_ratio = _safe_divide(accounts_receivable, revenue_ttm)
    dso_days = dso_ratio * 365.0 if dso_ratio is not None else None
    dio_ratio = _safe_divide(inventory, cost_of_revenue_ttm)
    dio_days = dio_ratio * 365.0 if dio_ratio is not None else None
    gap_driver = classify_ocf_net_income_gap_driver(
        operating_cash_flow_ttm=float(operating_cash_flow_ttm),  # type: ignore[arg-type]
        net_income_ttm=float(net_income_ttm),  # type: ignore[arg-type]
        capex_ttm=capex_ttm,
        sbc_ttm=sbc_ttm,
        change_in_working_capital=change_in_working_capital,
    )
    working_capital_metrics = WorkingCapitalMetrics(
        dso_days=dso_days,
        dio_days=dio_days,
        ocf_net_income_gap_driver=gap_driver,
    )

    company_name = str(info.get("longName") or info.get("shortName") or normalized_ticker).strip()
    sector = str(info.get("sector") or "Unknown").strip()

    try:
        return FinancialSnapshot(
            ticker=normalized_ticker,
            company_name=company_name,
            sector=sector,
            current_price=float(current_price),  # type: ignore[arg-type]
            market_cap=float(market_cap),  # type: ignore[arg-type]
            enterprise_value=float(enterprise_value),  # type: ignore[arg-type]
            revenue_ttm=float(revenue_ttm),  # type: ignore[arg-type]
            ebitda_ttm=float(ebitda_ttm),  # type: ignore[arg-type]
            net_income_ttm=float(net_income_ttm),  # type: ignore[arg-type]
            operating_cash_flow_ttm=float(operating_cash_flow_ttm),  # type: ignore[arg-type]
            capex_ttm=capex_ttm,
            free_cash_flow_ttm=float(free_cash_flow_ttm),  # type: ignore[arg-type]
            total_debt=max(total_debt, 0.0),
            cash_and_equivalents=max(cash_and_equivalents, 0.0),
            shares_outstanding=float(shares_outstanding),  # type: ignore[arg-type]
            historical_revenue_growth_3y=historical_revenue_growth_3y,
            total_assets=total_assets,
            gross_margin_ttm=gross_margin_ttm,
            operating_margin_ttm=operating_margin_ttm,
            roic_ttm=roic_ttm,
            sbc_ttm=sbc_ttm,
            sbc_adjusted_fcf_ttm=sbc_adjusted_fcf_ttm,
            net_cash=net_cash,
            net_cash_to_market_cap=net_cash_to_market_cap,
            fifty_two_week_low=fifty_two_week_low,
            fifty_two_week_high=fifty_two_week_high,
            business_summary=business_summary,
            forward_pe=forward_pe,
            forward_ev_ebitda=forward_ev_ebitda,
            analyst_target_mean=analyst_target_mean,
            analyst_count=analyst_count,
            historical_trajectory=list(historical_trajectory or ()),
            quarterly_trajectory=list(quarterly_trajectory or ()),
            working_capital_metrics=working_capital_metrics,
        )
    except ValidationError as exc:
        raise DataFetchError(
            f"Financial snapshot validation failed for {normalized_ticker}: {exc}"
        ) from exc


def fetch_financial_snapshot(ticker: str) -> FinancialSnapshot:
    """Fetch live market and TTM financial statement data for a target ticker via yfinance."""
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise DataFetchError("Target ticker cannot be empty.")

    try:
        ticker_client = yf.Ticker(normalized_ticker)
        info_raw = ticker_client.info
        if not isinstance(info_raw, Mapping) or not info_raw:
            raise DataFetchError(
                f"No market metadata returned by yfinance for ticker '{normalized_ticker}'."
            )
        income_statement = ticker_client.income_stmt
        cashflow_statement = ticker_client.cashflow
        balance_sheet = ticker_client.balance_sheet
        try:
            quarterly_income_stmt = ticker_client.quarterly_income_stmt
            quarterly_cashflow = ticker_client.quarterly_cashflow
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Quarterly statements unavailable for '%s': %s", normalized_ticker, exc)
            quarterly_income_stmt = None
            quarterly_cashflow = None
    except DataFetchError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise DataFetchError(
            f"Failed to fetch live financial data for '{normalized_ticker}': {exc}"
        ) from exc

    statement_fallbacks: dict[str, float | None] = {
        "revenue_ttm": _extract_latest_statement_value(
            income_statement, ("Total Revenue", "Operating Revenue")
        ),
        "gross_profit_ttm": _extract_latest_statement_value(income_statement, ("Gross Profit",)),
        "cost_of_revenue_ttm": _extract_latest_statement_value(
            income_statement, ("Cost Of Revenue", "Reconciled Cost Of Revenue")
        ),
        "operating_income_ttm": _extract_latest_statement_value(
            income_statement, ("Operating Income", "EBIT")
        ),
        "tax_provision": _extract_latest_statement_value(income_statement, ("Tax Provision",)),
        "pretax_income": _extract_latest_statement_value(income_statement, ("Pretax Income",)),
        "ebitda_ttm": _extract_latest_statement_value(
            income_statement, ("EBITDA", "Normalized EBITDA")
        ),
        "net_income_ttm": _extract_latest_statement_value(
            income_statement, ("Net Income", "Net Income Common Stockholders")
        ),
        "operating_cash_flow_ttm": _extract_latest_statement_value(
            cashflow_statement,
            ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
        ),
        "capex_ttm": _extract_latest_statement_value(
            cashflow_statement, ("Capital Expenditure", "Capital Expenditures")
        ),
        "free_cash_flow_ttm": _extract_latest_statement_value(
            cashflow_statement, ("Free Cash Flow",)
        ),
        "sbc_ttm": _extract_latest_statement_value(
            cashflow_statement, ("Stock Based Compensation",)
        ),
        "change_in_working_capital": _extract_latest_statement_value(
            cashflow_statement, ("Change In Working Capital",)
        ),
        "total_debt": _extract_latest_statement_value(balance_sheet, ("Total Debt",)),
        "total_equity": _extract_latest_statement_value(
            balance_sheet,
            ("Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"),
        ),
        "cash_and_equivalents": _extract_latest_statement_value(
            balance_sheet,
            ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
        ),
        "total_assets": _extract_latest_statement_value(balance_sheet, ("Total Assets",)),
        "accounts_receivable": _extract_latest_statement_value(
            balance_sheet, ("Accounts Receivable", "Receivables")
        ),
        "inventory": _extract_latest_statement_value(balance_sheet, ("Inventory",)),
    }
    annual_revenues = _extract_annual_revenues(income_statement)
    historical_trajectory = extract_historical_trajectory(income_statement, cashflow_statement)
    quarterly_trajectory = extract_quarterly_trajectory(quarterly_income_stmt, quarterly_cashflow)

    return build_snapshot_from_raw(
        ticker=normalized_ticker,
        info=info_raw,
        annual_revenues=annual_revenues,
        statement_fallbacks=statement_fallbacks,
        historical_trajectory=historical_trajectory,
        quarterly_trajectory=quarterly_trajectory,
    )


def fetch_peer_comparables(peer_tickers: Sequence[str]) -> list[PeerComparable]:
    """Fetch comparable valuation multiples and growth metrics for peer tickers via yfinance."""
    comparables: list[PeerComparable] = []
    for raw_peer in peer_tickers:
        peer_symbol = raw_peer.strip().upper()
        if not peer_symbol:
            continue
        try:
            peer_client = yf.Ticker(peer_symbol)
            info_raw = peer_client.info
            if not isinstance(info_raw, Mapping) or not info_raw:
                raise ValueError("empty yfinance info payload")

            ev_to_ebitda = _to_finite_float(info_raw.get("enterpriseToEbitda"))
            pe_ratio = _to_finite_float(info_raw.get("trailingPE"))
            forward_pe = _to_finite_float(info_raw.get("forwardPE"))
            fcf = _to_finite_float(info_raw.get("freeCashflow"))
            market_cap = _to_finite_float(info_raw.get("marketCap"))
            fcf_yield: float | None = None
            if fcf is not None and market_cap is not None and market_cap > 0.0:
                fcf_yield = fcf / market_cap

            annual_revenues = _extract_annual_revenues(peer_client.income_stmt)
            fallback_growth = _to_finite_float(info_raw.get("revenueGrowth"))
            revenue_growth_3y: float | None = None
            if len(annual_revenues) >= 2:
                revenue_growth_3y = compute_three_year_revenue_cagr(
                    annual_revenues, fallback_growth=fallback_growth
                )
            elif fallback_growth is not None:
                revenue_growth_3y = fallback_growth

            comparables.append(
                PeerComparable(
                    ticker=peer_symbol,
                    ev_to_ebitda=ev_to_ebitda,
                    pe_ratio=pe_ratio,
                    forward_pe=forward_pe,
                    fcf_yield=fcf_yield,
                    revenue_growth_3y=revenue_growth_3y,
                    market_cap=market_cap,
                )
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Failed to fetch peer comparable '%s': %s", peer_symbol, exc)
            comparables.append(
                PeerComparable(
                    ticker=peer_symbol,
                    ev_to_ebitda=None,
                    pe_ratio=None,
                    forward_pe=None,
                    fcf_yield=None,
                    revenue_growth_3y=None,
                    market_cap=None,
                )
            )
    return comparables


def load_market_data_from_fixture(fixture_path: Path) -> MarketDataBundle:
    """Load and validate a target snapshot and peer comparables from a local JSON file."""
    try:
        raw_text = fixture_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DataFetchError(f"Unable to read fixture file '{fixture_path}': {exc}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise DataFetchError(f"Malformed JSON in fixture file '{fixture_path}': {exc}") from exc

    try:
        return MarketDataBundle.model_validate(payload)
    except ValidationError as exc:
        raise DataFetchError(
            f"Fixture file '{fixture_path}' failed schema validation: {exc}"
        ) from exc


def load_mock_watchlist_profiles() -> dict[str, FinancialSnapshot]:
    """Load bundled multi-ticker offline snapshot profiles for deterministic screening."""
    profile_resource = resources.files("fundamental_memo.fixtures").joinpath(
        "mock_watchlist_profiles.json"
    )
    try:
        raw_profiles = json.loads(profile_resource.read_text(encoding="utf-8"))
        if not isinstance(raw_profiles, dict):
            return {}
        return {
            symbol.strip().upper(): FinancialSnapshot.model_validate(data)
            for symbol, data in raw_profiles.items()
        }
    except (OSError, json.JSONDecodeError, ValidationError):
        return {}


def load_mock_market_data(
    ticker: str | None = None, peer_tickers: Sequence[str] | None = None
) -> MarketDataBundle:
    """Load the bundled deterministic offline fixture for zero-network execution."""
    fixture_resource = resources.files("fundamental_memo.fixtures").joinpath(
        "mock_market_data.json"
    )
    try:
        payload = json.loads(fixture_resource.read_text(encoding="utf-8"))
        bundle = MarketDataBundle.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise DataFetchError(f"Failed to load bundled mock fixture: {exc}") from exc

    snapshot = bundle.snapshot
    if ticker is not None:
        requested_ticker = ticker.strip().upper()
        if requested_ticker and requested_ticker != snapshot.ticker:
            watchlist_profiles = load_mock_watchlist_profiles()
            if requested_ticker in watchlist_profiles:
                snapshot = watchlist_profiles[requested_ticker]
            else:
                snapshot = snapshot.model_copy(
                    update={
                        "ticker": requested_ticker,
                        "company_name": f"{requested_ticker} (Offline Mock Profile)",
                    }
                )

    peers = list(bundle.peers)
    if peer_tickers:
        requested_peers = [symbol.strip().upper() for symbol in peer_tickers if symbol.strip()]
        peer_lookup = {peer.ticker: peer for peer in bundle.peers}
        matched = [peer_lookup[symbol] for symbol in requested_peers if symbol in peer_lookup]
        if matched:
            peers = matched

    return MarketDataBundle(snapshot=snapshot, peers=peers)


def fetch_market_data(
    ticker: str,
    peer_tickers: Sequence[str],
    *,
    mock_data: bool = False,
    fixture_path: Path | None = None,
) -> MarketDataBundle:
    """Fetch target and peer market data from fixture, bundled mock data, or live yfinance."""
    if fixture_path is not None:
        return load_market_data_from_fixture(fixture_path)
    if mock_data:
        return load_mock_market_data(ticker=ticker, peer_tickers=peer_tickers)

    snapshot = fetch_financial_snapshot(ticker)
    peers = fetch_peer_comparables(peer_tickers)
    return MarketDataBundle(snapshot=snapshot, peers=peers)
