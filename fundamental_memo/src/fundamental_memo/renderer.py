"""One-page institutional Markdown memo renderer with grounding audit and word ceiling."""

from __future__ import annotations

from collections.abc import Sequence

from fundamental_memo.memo_synthesizer import (
    _collect_audit_keys,
    build_audit_trail_payload,
    sanitize_memo_prose,
    verify_memo_grounding_and_repetition,
)
from fundamental_memo.schemas import (
    DcfSensitivity,
    FinancialSnapshot,
    GroundingAuditError,
    InvestmentMemoSchema,
    MemoWordLimitError,
    PeerComparable,
    ValuationAnalysis,
    count_words,
)
from fundamental_memo.valuation_engine import (
    compute_dcf_sensitivity,
    compute_positive_median,
    compute_target_multiples,
)

MAX_MEMO_WORDS = 750


def _fmt_multiple(value: float | None) -> str:
    """Format a valuation multiple such as EV/EBITDA or P/E."""
    return f"{value:.1f}x" if value is not None else "N/A"


def _fmt_pct(value: float | None, *, signed: bool = False, decimals: int = 2) -> str:
    """Format a decimal ratio as a percentage string."""
    if value is None:
        return "N/A"
    pct = value * 100.0
    sign_prefix = "+" if signed else ""
    return f"{pct:{sign_prefix}.{decimals}f}%"


def _fmt_currency(value: float | None) -> str:
    """Format a per-share dollar value."""
    return f"${value:,.2f}" if value is not None else "N/A"


def _fmt_compact_usd(value: float | None) -> str:
    """Format large dollar values in billions or millions."""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    sign = "-" if value < 0.0 else ""
    if abs_val >= 1_000_000_000.0:
        return f"{sign}${abs_val / 1_000_000_000.0:,.2f}B"
    if abs_val >= 1_000_000.0:
        return f"{sign}${abs_val / 1_000_000.0:,.1f}M"
    return f"{sign}${abs_val:,.0f}"


def _fmt_days(value: float | None) -> str:
    """Format working capital days."""
    return f"{value:.1f}d" if value is not None else "N/A"


def render_investment_memo(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
    memo_output: InvestmentMemoSchema,
    *,
    sensitivity: DcfSensitivity | None = None,
    max_words: int = MAX_MEMO_WORDS,
    enforce_grounding: bool = True,
) -> str:
    """Render the upgraded institutional Markdown memo and enforce grounding + word bounds."""
    dcf_sensitivity = sensitivity
    if dcf_sensitivity is None:
        dcf_sensitivity = compute_dcf_sensitivity(
            snapshot,
            wacc=valuation.dcf_assumptions["wacc"],
            terminal_growth_rate=valuation.dcf_assumptions["terminal_growth_rate"],
            projection_years=int(valuation.dcf_assumptions["projection_years"]),
            fcf_cagr_override=valuation.dcf_assumptions["fcf_cagr"],
        )

    audit_payload = build_audit_trail_payload(
        snapshot, valuation, peers, sensitivity=dcf_sensitivity
    )
    audit_keys: set[str] = set()
    _collect_audit_keys(audit_payload, audit_keys)
    clean_memo = sanitize_memo_prose(memo_output, audit_keys=audit_keys)

    if enforce_grounding:
        violations = verify_memo_grounding_and_repetition(
            clean_memo, snapshot, valuation, peers, sensitivity=dcf_sensitivity
        )
        if violations:
            raise GroundingAuditError(" ".join(violations))

    target_multiples = compute_target_multiples(snapshot)
    peer_median_fcf_yield = compute_positive_median([peer.fcf_yield for peer in peers])
    peer_tickers_label = ", ".join(peer.ticker for peer in peers) if peers else "None"

    upside_label = _fmt_pct(valuation.dcf_upside_pct, signed=True, decimals=1)
    wacc_pct = valuation.dcf_assumptions["wacc"] * 100.0
    term_pct = valuation.dcf_assumptions["terminal_growth_rate"] * 100.0
    fcf_cagr_pct = valuation.dcf_assumptions["fcf_cagr"] * 100.0
    exit_mult = valuation.dcf_assumptions.get("target_exit_ev_ebitda", 15.0)
    implied_cagr_label = _fmt_pct(valuation.implied_fcf_cagr_5y, decimals=1)
    cagr_spread_label = _fmt_pct(valuation.cagr_spread_vs_base, signed=True, decimals=1)

    dso_label = (
        _fmt_days(snapshot.working_capital_metrics.dso_days)
        if snapshot.working_capital_metrics is not None
        else "N/A"
    )
    dio_label = (
        _fmt_days(snapshot.working_capital_metrics.dio_days)
        if snapshot.working_capital_metrics is not None
        else "N/A"
    )

    bull_lines = "\n".join(f"- {bullet}" for bullet in clean_memo.bull_case)
    bear_lines = "\n".join(f"- {bullet}" for bullet in clean_memo.bear_case)
    risk_lines = "\n".join(f"- {risk}" for risk in clean_memo.key_downside_risks)

    sections = [
        f"# Investment Memo: {snapshot.company_name} ({snapshot.ticker})",
        (
            f"*Sector:* {snapshot.sector} | "
            f"*Current Price:* {_fmt_currency(snapshot.current_price)} | "
            f"*DCF Value:* {_fmt_currency(valuation.dcf_intrinsic_value_per_share)} "
            f"({upside_label}) | "
            f"*Implied 5Y FCF CAGR:* {implied_cagr_label} ({cagr_spread_label} vs. Base) | "
            f"*ROIC:* {_fmt_pct(snapshot.roic_ttm, decimals=1)} | "
            f"*Quality:* {valuation.earnings_quality_flag}"
        ),
        "## Executive Thesis",
        clean_memo.executive_thesis,
        "## Valuation & The Debate (Variant Perception)",
        (
            f"| Metric | {snapshot.ticker} | Peer Median ({peer_tickers_label}) |\n"
            "| --- | ---: | ---: |\n"
            f"| EV / EBITDA | {_fmt_multiple(target_multiples['ev_to_ebitda'])} | "
            f"{_fmt_multiple(valuation.peer_median_ev_ebitda)} |\n"
            f"| P / E (TTM) | {_fmt_multiple(target_multiples['pe_ratio'])} | "
            f"{_fmt_multiple(valuation.peer_median_pe)} |\n"
            f"| Forward P / E | {_fmt_multiple(target_multiples['forward_pe'])} | "
            f"{_fmt_multiple(valuation.peer_median_forward_pe)} |\n"
            f"| FCF Yield | {_fmt_pct(target_multiples['fcf_yield'])} | "
            f"{_fmt_pct(peer_median_fcf_yield)} |\n"
            f"| Implied Share Value | "
            f"{_fmt_currency(valuation.dcf_intrinsic_value_per_share)} (DCF) / "
            f"{_fmt_currency(valuation.exit_multiple_dcf_value)} ({exit_mult:.1f}x Exit) | "
            f"{_fmt_currency(valuation.implied_value_by_comps)} (Comps) / "
            f"{_fmt_currency(snapshot.analyst_target_mean)} (Street) |"
        ),
        (
            f"*DCF Sensitivity (5Y CAGR {fcf_cagr_pct:.1f}%, Term g {term_pct:.2f}%):* "
            f"WACC {dcf_sensitivity.low_wacc * 100.0:.2f}% = "
            f"{_fmt_currency(dcf_sensitivity.low_wacc_value_per_share)} | "
            f"Base {wacc_pct:.2f}% = "
            f"{_fmt_currency(dcf_sensitivity.base_wacc_value_per_share)} | "
            f"WACC {dcf_sensitivity.high_wacc * 100.0:.2f}% = "
            f"{_fmt_currency(dcf_sensitivity.high_wacc_value_per_share)}."
        ),
        clean_memo.valuation_and_debate,
        "## Profitability & Cash Quality",
        (
            f"*Gross Margin:* {_fmt_pct(snapshot.gross_margin_ttm, decimals=1)} | "
            f"*Operating Margin:* {_fmt_pct(snapshot.operating_margin_ttm, decimals=1)} | "
            f"*EBITDA Margin:* {_fmt_pct(snapshot.ebitda_margin_ttm, decimals=1)} | "
            f"*FCF Margin:* {_fmt_pct(snapshot.fcf_margin_ttm, decimals=1)} | "
            f"*ROIC:* {_fmt_pct(snapshot.roic_ttm, decimals=1)} | "
            f"*SBC-Adj FCF:* {_fmt_compact_usd(snapshot.sbc_adjusted_fcf_ttm)} | "
            f"*OCF/NI:* {valuation.ocf_to_net_income_ratio:.2f}x | "
            f"*Accrual:* {_fmt_pct(valuation.accrual_ratio, signed=True)} | "
            f"*DSO / DIO:* {dso_label} / {dio_label}"
        ),
        clean_memo.profitability_and_cash_quality,
        "## Bull Case vs. Bear Case",
        f"### Bull Case\n{bull_lines}",
        f"### Bear Case\n{bear_lines}",
        "## Key Downside Risks",
        risk_lines,
    ]

    rendered = "\n\n".join(sections).strip() + "\n"
    total_words = count_words(rendered)
    if total_words > max_words:
        raise MemoWordLimitError(
            f"Rendered investment memo exceeds {max_words}-word one-page limit "
            f"({total_words} words)."
        )
    return rendered
