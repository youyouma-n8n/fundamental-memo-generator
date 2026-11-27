"""Local OpenAI-compatible LLM synthesizer, grounding verifier, and offline mock synthesizer."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)
from pydantic import ValidationError

from fundamental_memo.schemas import (
    DcfSensitivity,
    FinancialSnapshot,
    GroundingAuditError,
    InvestmentMemoSchema,
    PeerComparable,
    SynthesisError,
    ValuationAnalysis,
)
from fundamental_memo.valuation_engine import compute_dcf_sensitivity, compute_target_multiples

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_MLX_BASE_URL = "http://localhost:8080/v1"
DEFAULT_MODEL = "inkling-2-mini:latest"
SUPPORTED_MODELS: tuple[str, ...] = (
    "inkling-2-mini:latest",
    "gemma4:31b-mlx",
    "qwen3.8:27b-mlx",
)

SYSTEM_PROMPT = (
    "Cite only the provided Audit Trail JSON metrics. Do not invent external financial numbers. "
    "Strict opening-sentence anti-echoing rule: every section already displays a top KPI ribbon "
    "or table, so the FIRST SENTENCE of valuation_and_debate and profitability_and_cash_quality "
    "MUST begin with an analytical mechanism, business driver, or valuation tension — NEVER with "
    "a metric name or number already printed in that section's header table or ribbon (e.g., "
    "FORBIDDEN: 'Gross margin is 75.5%...'; REQUIRED: 'Company's custom AI accelerator and "
    "software mix underpins elite unit economics...'). "
    "Single-Mention rule: each headline valuation figure (DCF intrinsic value, Comps implied "
    "value, market-implied FCF CAGR) may appear at most twice total (once in executive_thesis "
    "and once in valuation_and_debate) and MUST NEVER appear in bull_case, bear_case, "
    "profitability_and_cash_quality, or key_downside_risks. "
    "Ground bull_case and bear_case in concrete segment/product drivers from "
    "financial_snapshot.business_summary alongside financial durability and risks. "
    "Amortization-aware profitability rule: always evaluate ebitda_margin_ttm and fcf_margin_ttm "
    "alongside GAAP operating_margin_ttm; whenever ebitda_margin_ttm exceeds operating_margin_ttm "
    "by more than 15 percentage points (e.g., M&A intangible amortization), explicitly highlight "
    "cash-flow margin durability rather than framing GAAP operating margin alone as operational "
    "deterioration. "
    "NEVER output raw JSON snake_case variable names (such as pe_compression_pct, "
    "analyst_target_mean, ocf_to_net_income_ratio, or implied_fcf_cagr_5y) in the memo prose. "
    "Always translate them into natural institutional financial English (e.g., 'forward P/E "
    "compression', 'Wall Street consensus target price', 'OCF-to-Net-Income ratio', "
    "'market-implied 5-year FCF CAGR'). "
    "When citing Reverse DCF Year-5 FCF multiples, always distinguish implied_y5_fcf_multiple "
    "('X.Xx current FCF') from implied_y5_fcf_vs_current_revenue ('X.Xx current revenue') — "
    "never swap their nouns. "
    "Keep analysis sharp, institutional, and concise. "
    "Respond ONLY with a valid JSON object matching the exact schema requested."
)

_CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
# Match standalone numeric literals (optionally preceded by $, +/-, and followed by B/M/T/%/x)
# while ignoring identifiers like 52w or Q4 or ticker names.
_NUMERIC_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])([+-]?\$?\d[\d,]*(?:\.\d+)?)(?:\s*(?:[BMT%]|x|bps|pp))?(?![A-Za-z0-9_])"
)
# Detect forbidden metric-first / ribbon-echoing opening sentences on analytical sections.
_FORBIDDEN_OPENING_METRIC_PATTERN = re.compile(
    r"^(?:"
    r"[\$+-]?\d|"
    r"at\s+\d+(?:\.\d+)?%\s+wacc\b|"
    r"(?:gross\s+margin|operating\s+margin|ebitda\s+margin|fcf\s+margin|roic|ocf\s*/\s*ni|"
    r"ocf-to-net-income|accrual\s+ratio|sbc-adjusted\s+fcf|dso|dio|ev\s*/\s*ebitda|p\s*/\s*e|"
    r"forward\s+p\s*/\s*e|trailing\s+p\s*/\s*e|base\s+dcf|perpetuity\s+dcf|our\s+5-year\s+dcf)\b"
    r")",
    re.IGNORECASE,
)

_APPROVED_STRUCTURAL_CONSTANTS: frozenset[float] = frozenset(
    {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 21.0, 25.0, 50.0, 52.0, 75.0, 100.0, 250.0, 365.0}
)

_SNAKE_CASE_IDENTIFIER_PATTERN = re.compile(r"`?\b([a-z]+(?:_[a-z0-9]+)+)\b`?")

AUDIT_TRAIL_IDENTIFIER_ALIASES: dict[str, str] = {
    "pe_compression_pct": "forward P/E compression",
    "analyst_target_mean": "consensus target price",
    "analyst_count": "covering analyst count",
    "ocf_to_net_income_ratio": "OCF-to-Net-Income ratio",
    "ocf_net_income_gap_driver": "cash-conversion gap driver",
    "implied_fcf_cagr_5y": "market-implied 5-year FCF CAGR",
    "cagr_spread_vs_base": "implied-versus-base CAGR spread",
    "implied_y5_fcf": "implied Year-5 FCF",
    "implied_y5_fcf_multiple": "implied Year-5 FCF multiple",
    "implied_y5_fcf_vs_current_revenue": "implied Year-5 FCF-to-current-revenue ratio",
    "dcf_intrinsic_value_per_share": "base DCF intrinsic value",
    "dcf_upside_pct": "DCF implied upside",
    "exit_multiple_dcf_value": "Exit Multiple DCF value",
    "implied_exit_ev_ebitda": "implied exit EV/EBITDA",
    "target_exit_ev_ebitda": "terminal exit EV/EBITDA multiple",
    "implied_value_by_comps": "comps-implied value",
    "peer_comps_p25_value": "25th-percentile peer comps value",
    "peer_comps_p75_value": "75th-percentile peer comps value",
    "peer_median_ev_ebitda": "peer median EV/EBITDA",
    "peer_median_pe": "peer median trailing P/E",
    "peer_median_forward_pe": "peer median forward P/E",
    "ev_to_ebitda": "EV/EBITDA",
    "pe_ratio": "trailing P/E",
    "forward_pe": "forward P/E",
    "forward_ev_ebitda": "forward EV/EBITDA",
    "fcf_yield": "FCF yield",
    "revenue_ttm": "TTM revenue",
    "ebitda_ttm": "TTM EBITDA",
    "net_income_ttm": "TTM net income",
    "operating_cash_flow_ttm": "TTM operating cash flow",
    "capex_ttm": "TTM CapEx",
    "free_cash_flow_ttm": "TTM free cash flow",
    "gross_margin_ttm": "TTM gross margin",
    "operating_margin_ttm": "TTM operating margin",
    "ebitda_margin_ttm": "TTM EBITDA margin",
    "fcf_margin_ttm": "TTM FCF margin",
    "roic_ttm": "TTM ROIC",
    "sbc_ttm": "TTM stock-based compensation",
    "sbc_adjusted_fcf_ttm": "SBC-adjusted FCF",
    "net_cash": "net cash",
    "net_cash_to_market_cap": "net cash-to-market-cap ratio",
    "total_debt": "total debt",
    "cash_and_equivalents": "cash and equivalents",
    "current_price": "current share price",
    "market_cap": "market capitalization",
    "enterprise_value": "enterprise value",
    "shares_outstanding": "shares outstanding",
    "historical_revenue_growth_3y": "3-year revenue CAGR",
    "accrual_ratio": "accrual ratio",
    "earnings_quality_flag": "earnings quality rating",
    "dso_days": "DSO",
    "dio_days": "DIO",
    "business_summary": "business profile",
    "historical_trajectory": "3-year historical trajectory",
    "quarterly_trajectory": "4-quarter trajectory",
    "working_capital_metrics": "working-capital metrics",
    "dcf_sensitivity_matrix": "DCF sensitivity matrix",
    "terminal_growth_rate": "terminal growth rate",
    "fcf_cagr": "5-year FCF CAGR",
    "financial_snapshot": "financial snapshot",
    "valuation_analysis": "valuation analysis",
    "peer_comparables": "peer comparables",
    "target_multiples": "valuation multiples",
    "dcf_sensitivity": "DCF sensitivity",
}


def _collect_audit_keys(node: object, keys: set[str]) -> None:
    """Recursively collect every snake_case key name present in an Audit Trail JSON payload."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and "_" in key:
                keys.add(key)
            _collect_audit_keys(value, keys)
    elif isinstance(node, list):
        for item in node:
            _collect_audit_keys(item, keys)


def sanitize_text_identifiers(text: str, audit_keys: set[str] | None = None) -> str:
    """Replace any leaked Audit Trail snake_case JSON keys with natural institutional English."""
    known_keys = set(AUDIT_TRAIL_IDENTIFIER_ALIASES.keys())
    if audit_keys:
        known_keys.update(audit_keys)

    def _replace(match: re.Match[str]) -> str:
        ident = match.group(1)
        if ident in AUDIT_TRAIL_IDENTIFIER_ALIASES:
            return AUDIT_TRAIL_IDENTIFIER_ALIASES[ident]
        if ident in known_keys:
            return ident.replace("_", " ")
        return match.group(0)

    return _SNAKE_CASE_IDENTIFIER_PATTERN.sub(_replace, text)


def sanitize_memo_prose(
    memo: InvestmentMemoSchema, audit_keys: set[str] | None = None
) -> InvestmentMemoSchema:
    """Deterministically scrub leaked snake_case Audit Trail JSON keys from all memo fields."""
    return memo.model_copy(
        update={
            "executive_thesis": sanitize_text_identifiers(memo.executive_thesis, audit_keys),
            "valuation_and_debate": sanitize_text_identifiers(
                memo.valuation_and_debate, audit_keys
            ),
            "profitability_and_cash_quality": sanitize_text_identifiers(
                memo.profitability_and_cash_quality, audit_keys
            ),
            "bull_case": [
                sanitize_text_identifiers(item, audit_keys) for item in memo.bull_case
            ],
            "bear_case": [
                sanitize_text_identifiers(item, audit_keys) for item in memo.bear_case
            ],
            "key_downside_risks": [
                sanitize_text_identifiers(item, audit_keys) for item in memo.key_downside_risks
            ],
        }
    )


def find_leaked_snake_case_identifiers(
    text: str, audit_keys: set[str] | None = None
) -> list[str]:
    """Return any raw snake_case Audit Trail JSON keys still present in a text block."""
    known_keys = set(AUDIT_TRAIL_IDENTIFIER_ALIASES.keys())
    if audit_keys:
        known_keys.update(audit_keys)
    found: list[str] = []
    for match in _SNAKE_CASE_IDENTIFIER_PATTERN.finditer(text):
        ident = match.group(1)
        if ident in known_keys and ident not in found:
            found.append(ident)
    return found


def _strip_markdown_fences(raw_content: str) -> str:
    """Remove surrounding Markdown code fences if a local LLM wraps its JSON output."""
    cleaned = raw_content.strip()
    match = _CODE_FENCE_PATTERN.match(cleaned)
    if match:
        return match.group(1).strip()
    return cleaned


def _format_billions(value: float) -> str:
    """Format a USD dollar figure into a compact institutional string."""
    abs_value = abs(value)
    sign = "-" if value < 0.0 else ""
    if abs_value >= 1_000_000_000.0:
        return f"{sign}${abs_value / 1_000_000_000.0:,.2f}B"
    if abs_value >= 1_000_000.0:
        return f"{sign}${abs_value / 1_000_000.0:,.1f}M"
    return f"{sign}${abs_value:,.0f}"


def build_audit_trail_payload(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
    sensitivity: DcfSensitivity | None = None,
) -> dict[str, Any]:
    """Build the canonical Audit Trail JSON dictionary shared by synthesis, audit, and UI."""
    resolved_sensitivity = sensitivity
    if resolved_sensitivity is None:
        resolved_sensitivity = compute_dcf_sensitivity(
            snapshot,
            wacc=valuation.dcf_assumptions["wacc"],
            terminal_growth_rate=valuation.dcf_assumptions["terminal_growth_rate"],
            projection_years=int(valuation.dcf_assumptions["projection_years"]),
            fcf_cagr_override=valuation.dcf_assumptions["fcf_cagr"],
        )
    return {
        "financial_snapshot": snapshot.model_dump(mode="json", by_alias=True),
        "valuation_analysis": valuation.model_dump(mode="json"),
        "peer_comparables": [peer.model_dump(mode="json") for peer in peers],
        "target_multiples": compute_target_multiples(snapshot),
        "dcf_sensitivity": resolved_sensitivity.model_dump(mode="json"),
    }


def _collect_allowed_numbers(node: object, bucket: set[float]) -> None:
    """Recursively collect every numeric value from Audit Trail JSON across institutional scales."""
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, (int, float)):
        numeric = float(node)
        if not math.isfinite(numeric):
            return
        abs_val = abs(numeric)
        scaled_variants = (
            abs_val,
            abs_val * 100.0,
            abs_val * 10_000.0,
            abs_val / 1_000_000.0,
            abs_val / 1_000_000_000.0,
            abs_val / 1_000_000_000_000.0,
        )
        for variant in scaled_variants:
            bucket.add(variant)
            bucket.add(round(variant, 0))
            bucket.add(round(variant, 1))
            bucket.add(round(variant, 2))
        return
    if isinstance(node, dict):
        for value in node.values():
            _collect_allowed_numbers(value, bucket)
        return
    if isinstance(node, list):
        for item in node:
            _collect_allowed_numbers(item, bucket)


def _is_number_grounded(value: float, allowed_numbers: set[float]) -> bool:
    """Check whether a numeric token matches an Audit Trail figure within rounding tolerance."""
    abs_value = abs(value)
    if abs_value in _APPROVED_STRUCTURAL_CONSTANTS:
        return True
    tolerance = max(0.051, abs_value * 0.002)
    return any(abs(abs_value - candidate) <= tolerance for candidate in allowed_numbers)


def _count_formatted_value_mentions(text: str, value: float, *, is_percentage: bool = False) -> int:
    """Count occurrences of a specific headline figure (currency or percentage) in text.

    Uses strict numeric and unit boundaries so a percentage (e.g., 28.4%) never collides
    with a multiple (e.g., 28.2x Forward P/E) or a different decimal number sharing an integer part.
    """
    target = abs(value * 100.0) if is_percentage else abs(value)
    decimal_patterns: set[str] = {
        f"{target:,.2f}",
        f"{target:.2f}",
        f"{target:,.1f}",
        f"{target:.1f}",
    }
    if is_percentage:
        pct_patterns = set(decimal_patterns)
        if target >= 10.0:
            pct_patterns.add(f"{target:,.0f}")
        escaped = "|".join(re.escape(item) for item in sorted(pct_patterns, key=len, reverse=True))
        regex = re.compile(
            rf"(?<!\d)(?<!\d\.)(?:{escaped})(?!\d|\.\d)\s*(?:%|pp\b)", re.IGNORECASE
        )
    else:
        escaped_dec = "|".join(
            re.escape(item) for item in sorted(decimal_patterns, key=len, reverse=True)
        )
        unit_exclusion = r"(?!\d|\.\d)(?!\s*(?:%|x|×|bps\b|pp\b|days?\b))"
        if target >= 10.0:
            int_token = re.escape(f"{target:,.0f}")
            pattern_str = (
                rf"(?<!\d)(?<!\d\.)(?:\$?(?:{escaped_dec})|\${int_token}){unit_exclusion}"
            )
        else:
            pattern_str = rf"(?<!\d)(?<!\d\.)\$?(?:{escaped_dec}){unit_exclusion}"
        regex = re.compile(pattern_str, re.IGNORECASE)
    return len(regex.findall(text))


def verify_memo_grounding_and_repetition(
    memo: InvestmentMemoSchema,
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
    sensitivity: DcfSensitivity | None = None,
) -> list[str]:
    """Run deterministic numeric grounding and Single-Mention anti-repetition checks.

    Returns an empty list when all checks pass, or a list of concrete violation descriptions.
    """
    violations: list[str] = []
    audit_payload = build_audit_trail_payload(snapshot, valuation, peers, sensitivity=sensitivity)
    allowed_numbers: set[float] = set()
    _collect_allowed_numbers(audit_payload, allowed_numbers)

    # Whitelist any qualitative numeric tokens present in sanitized business_summary so
    # product specs (e.g., 5G, 800G, 3nm) never cause false-positive grounding failures.
    if snapshot.business_summary:
        for summary_match in _NUMERIC_TOKEN_PATTERN.finditer(snapshot.business_summary):
            raw_summary_num = summary_match.group(1).replace("$", "").replace(",", "")
            try:
                allowed_numbers.add(abs(float(raw_summary_num)))
            except ValueError:
                continue

    # Whitelist fiscal year numbers from annual and quarterly period labels (e.g., FY2024, 2025-Q3).
    for annual_point in snapshot.historical_trajectory:
        for year_match in re.finditer(r"(?:19|20)\d{2}", annual_point.period):
            allowed_numbers.add(float(year_match.group(0)))
    for quarterly_point in snapshot.quarterly_trajectory:
        for year_match in re.finditer(r"(?:19|20)\d{2}", quarterly_point.period):
            allowed_numbers.add(float(year_match.group(0)))

    # 1. Regex numeric grounding check across every LLM-generated narrative section
    section_texts: dict[str, str] = {
        "executive_thesis": memo.executive_thesis,
        "valuation_and_debate": memo.valuation_and_debate,
        "profitability_and_cash_quality": memo.profitability_and_cash_quality,
        "bull_case": " ".join(memo.bull_case),
        "bear_case": " ".join(memo.bear_case),
        "key_downside_risks": " ".join(memo.key_downside_risks),
    }

    unverified_tokens: list[str] = []
    for section_name, content in section_texts.items():
        for match in _NUMERIC_TOKEN_PATTERN.finditer(content):
            raw_number = match.group(1).replace("$", "").replace(",", "")
            try:
                parsed = float(raw_number)
            except ValueError:
                continue
            if not _is_number_grounded(parsed, allowed_numbers):
                unverified_tokens.append(f"{section_name}: '{match.group(0).strip()}'")

    if unverified_tokens:
        joined = "; ".join(unverified_tokens[:8])
        violations.append(
            f"Unverified numeric literals not found in Audit Trail JSON: {joined}."
        )

    # 2. Anti-repetition: forbidden exact DCF / Comps share prices inside bull_case or bear_case
    forbidden_price_figures: list[tuple[str, float]] = [
        ("dcf_intrinsic_value_per_share", valuation.dcf_intrinsic_value_per_share),
    ]
    if valuation.implied_value_by_comps is not None:
        forbidden_price_figures.append(
            ("implied_value_by_comps", valuation.implied_value_by_comps)
        )

    for case_section in ("bull_case", "bear_case"):
        case_text = section_texts[case_section]
        for metric_name, metric_val in forbidden_price_figures:
            if _count_formatted_value_mentions(case_text, metric_val, is_percentage=False) > 0:
                violations.append(
                    f"Anti-repetition violation: {case_section} must not repeat {metric_name} "
                    f"(${metric_val:,.2f})."
                )

    # 3. Single-Mention Rule: headline valuation figures may appear at most twice across memo
    headline_figures: list[tuple[str, float, bool]] = [
        ("dcf_intrinsic_value_per_share", valuation.dcf_intrinsic_value_per_share, False),
    ]
    if valuation.implied_value_by_comps is not None:
        headline_figures.append(("implied_value_by_comps", valuation.implied_value_by_comps, False))
    if valuation.implied_fcf_cagr_5y is not None:
        headline_figures.append(("implied_fcf_cagr_5y", valuation.implied_fcf_cagr_5y, True))

    for metric_name, metric_val, is_pct in headline_figures:
        section_counts = {
            sec: _count_formatted_value_mentions(txt, metric_val, is_percentage=is_pct)
            for sec, txt in section_texts.items()
        }
        mention_count = sum(section_counts.values())
        if mention_count > 2:
            formatted = f"{metric_val * 100.0:.1f}%" if is_pct else f"${metric_val:,.2f}"
            breakdown = ", ".join(
                f"{sec}: {cnt}" for sec, cnt in section_counts.items() if cnt > 0
            )
            violations.append(
                f"Single-Mention violation: {metric_name} ({formatted}) appeared "
                f"{mention_count} times [{breakdown}] (maximum allowed: 2 total — at most 1 in "
                f"executive_thesis and 1 in valuation_and_debate, and 0 elsewhere)."
            )

    # 4. Strict opening-sentence anti-echoing check on analytical prose sections
    for section_key in ("valuation_and_debate", "profitability_and_cash_quality"):
        opening_text = section_texts[section_key].strip()
        if _FORBIDDEN_OPENING_METRIC_PATTERN.match(opening_text):
            violations.append(
                f"Anti-echoing violation: {section_key} must open with an analytical mechanism, "
                f"business driver, or valuation tension rather than a header metric or number."
            )

    # 5. Reverse DCF Year-5 multiplier noun alignment check
    violations.extend(check_multiplier_noun_alignment(section_texts, valuation))

    return violations


def _build_multiplier_noun_pattern(value: float, noun_pattern: str) -> re.Pattern[str]:
    """Build a boundary-safe regex matching a multiplier value immediately followed by a noun."""
    abs_val = abs(value)
    candidates: set[str] = {f"{abs_val:.2f}", f"{abs_val:.1f}"}
    if abs(abs_val - round(abs_val)) < 1e-6:
        candidates.add(f"{abs_val:.0f}")
    escaped = "|".join(re.escape(item) for item in sorted(candidates, key=len, reverse=True))
    return re.compile(
        rf"(?<!\d)(?<!\d\.)(?:{escaped})(?!\d|\.\d)\s*[x×]\s*{noun_pattern}",
        re.IGNORECASE,
    )


def check_multiplier_noun_alignment(
    section_texts: Mapping[str, str], valuation: ValuationAnalysis
) -> list[str]:
    """Flag swapped Reverse DCF Year-5 FCF vs. current-revenue multiplier nouns in prose."""
    fcf_mult = valuation.implied_y5_fcf_multiple
    rev_ratio = valuation.implied_y5_fcf_vs_current_revenue
    if fcf_mult is None:
        return []
    if rev_ratio is not None and abs(fcf_mult - rev_ratio) <= 0.05:
        return []

    violations: list[str] = []
    fcf_as_revenue_re = _build_multiplier_noun_pattern(
        fcf_mult, r"(?:current\s+|ttm\s+|annual\s+)?revenue\b"
    )
    rev_as_fcf_re = (
        _build_multiplier_noun_pattern(
            rev_ratio, r"(?:current\s+|ttm\s+)?(?:fcf|free\s+cash\s+flow)\b"
        )
        if rev_ratio is not None
        else None
    )

    for section_name, content in section_texts.items():
        if fcf_as_revenue_re.search(content):
            violations.append(
                f"Multiplier noun mismatch in {section_name}: {fcf_mult:.2f}x is the Year-5 FCF "
                f"multiple of current FCF ('{fcf_mult:.2f}x current FCF'), NOT current revenue."
            )
        if rev_as_fcf_re is not None and rev_as_fcf_re.search(content):
            violations.append(
                f"Multiplier noun mismatch in {section_name}: {rev_ratio:.2f}x is the Year-5 FCF "
                f"ratio to current revenue ('{rev_ratio:.2f}x current revenue'), NOT current FCF."
            )
    return violations


def has_amortization_margin_gap(snapshot: FinancialSnapshot) -> bool:
    """Return True when EBITDA margin exceeds GAAP operating margin by more than 15pp."""
    if snapshot.ebitda_margin_ttm is None or snapshot.operating_margin_ttm is None:
        return False
    return (snapshot.ebitda_margin_ttm - snapshot.operating_margin_ttm) > 0.15


def build_synthesis_user_prompt(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
    sensitivity: DcfSensitivity | None = None,
) -> str:
    """Serialize verified Audit Trail JSON and schema/anti-repetition constraints into prompt."""
    payload = build_audit_trail_payload(snapshot, valuation, peers, sensitivity=sensitivity)
    amortization_guidance = (
        " CRITICAL AMORTIZATION NOTE: ebitda_margin_ttm exceeds operating_margin_ttm by more than "
        "15pp (indicative of non-cash M&A intangible amortization/D&A); you MUST explicitly cite "
        "cash-flow margin durability (ebitda_margin_ttm and fcf_margin_ttm) rather than framing "
        "GAAP operating_margin_ttm alone as operational deterioration."
        if has_amortization_margin_gap(snapshot)
        else ""
    )
    schema_instructions = {
        "executive_thesis": (
            "string, 2 crisp sentences, target 30-42 words (STRICT HARD MAX 60 words): core "
            "rating/stance, price vs. DCF/Comps spread, and single primary catalyst/risk."
        ),
        "valuation_and_debate": (
            "string, target 90-120 words (STRICT HARD MAX 150 words): FIRST SENTENCE MUST open "
            "with the core valuation debate or market tension (NEVER with a metric name or "
            "number). Compare trailing pe_ratio vs. forward_pe (pe_compression_pct) and "
            "analyst_target_mean alongside Base DCF, Reverse DCF (implied_fcf_cagr_5y / "
            "implied_y5_fcf), Exit Multiple DCF, and Peer Comps."
        ),
        "profitability_and_cash_quality": (
            "string, target 70-95 words (STRICT HARD MAX 120 words): FIRST SENTENCE MUST open "
            "with a business driver or operating mechanism (NEVER 'Gross margin is...' or any "
            "ribbon metric). Reference ebitda_margin_ttm and fcf_margin_ttm alongside GAAP "
            "operating_margin_ttm, interpret capital efficiency, SBC dilution impact, and explain "
            "OCF/Net Income using ocf_net_income_gap_driver." + amortization_guidance
        ),
        "bull_case": [
            "exact 3 short bullets (MAX 20 words per bullet, target 45-60 words total; STRICT "
            "HARD MAX 90 words total); MUST synthesize at least one concrete segment/product "
            "driver from financial_snapshot.business_summary alongside margin/ROIC durability. "
            "FORBIDDEN: repeating exact DCF/Comps share prices or implied_fcf_cagr_5y."
        ],
        "bear_case": [
            "exact 3 short bullets (MAX 20 words per bullet, target 45-60 words total; STRICT "
            "HARD MAX 90 words total); MUST cite at least one concrete segment/demand risk from "
            "financial_snapshot.business_summary alongside multiple compression, growth "
            "deceleration vs. market expectations, and peer dispersion. FORBIDDEN: repeating "
            "exact DCF/Comps share prices or implied_fcf_cagr_5y."
        ],
        "key_downside_risks": [
            "3 to 4 short bullets (MAX 18 words per bullet, target 45-60 words total; STRICT "
            "HARD MAX 90 words total); actionable monitoring triggers citing ONLY exact Audit "
            "Trail baseline metrics (current operating margin, DSO/DIO days, or +50/+100 bps "
            "WACC shift). For discount-rate risk, cite ONLY the WACC % / bps shift — NEVER "
            "write dollar DCF/Comps prices or implied CAGR in key_downside_risks, and NEVER "
            "invent round thresholds like 30%."
        ],
    }
    return (
        "Generate an institutional one-page investment memo JSON object using ONLY numeric values "
        "present in the verified Audit Trail JSON below. Every number is audited by regex. "
        "Target 550-700 words total.\n\n"
        f"AUDIT_TRAIL_JSON:\n{json.dumps(payload, indent=2)}\n\n"
        f"REQUIRED_OUTPUT_SCHEMA:\n{json.dumps(schema_instructions, indent=2)}\n\n"
        "Return raw JSON only with no additional keys or surrounding commentary."
    )


_LOSSLESS_SHORTHAND_SUBSTITUTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bstock-based compensation\b", re.IGNORECASE), "SBC"),
    (re.compile(r"\breturn on invested capital\b", re.IGNORECASE), "ROIC"),
    (re.compile(r"\btrailing twelve[- ]month(?:s)?\b", re.IGNORECASE), "TTM"),
    (re.compile(r"\boperating cash flow\b", re.IGNORECASE), "OCF"),
    (re.compile(r"\bfree cash flow\b", re.IGNORECASE), "FCF"),
    (re.compile(r"\bcapital expenditures?\b", re.IGNORECASE), "CapEx"),
    (re.compile(r"\bdays sales outstanding\b", re.IGNORECASE), "DSO"),
    (re.compile(r"\bdays inventory outstanding\b", re.IGNORECASE), "DIO"),
    (re.compile(r"\benterprise value\b", re.IGNORECASE), "EV"),
    (re.compile(r"\bpercentage points?\b", re.IGNORECASE), "pp"),
    (re.compile(r"\byear-over-year\b", re.IGNORECASE), "YoY"),
    (re.compile(r"\bquarter-over-quarter\b", re.IGNORECASE), "QoQ"),
    (re.compile(r"\bdue to the fact that\b", re.IGNORECASE), "as"),
    (re.compile(r"\bin order to\b", re.IGNORECASE), "to"),
    (re.compile(r"\bcompared to\b", re.IGNORECASE), "vs."),
    (re.compile(r"\bcompared with\b", re.IGNORECASE), "vs."),
    (re.compile(r"\bversus\b", re.IGNORECASE), "vs."),
)

_FIELD_WORD_LIMITS: dict[str, int] = {
    "executive_thesis": 60,
    "valuation_and_debate": 150,
    "profitability_and_cash_quality": 120,
    "bull_case": 90,
    "bear_case": 90,
    "key_downside_risks": 90,
}


def _apply_lossless_shorthand(text: str) -> str:
    """Condense verbose institutional phrases into standard finance shorthand losslessly."""
    result = text
    for pattern, replacement in _LOSSLESS_SHORTHAND_SUBSTITUTIONS:
        result = pattern.sub(replacement, result)
    return " ".join(result.split())


def _condense_overflowing_json_fields(cleaned_json: str) -> dict[str, Any] | None:
    """Apply lossless institutional shorthand ONLY to fields exceeding their schema word limit."""
    try:
        parsed = json.loads(cleaned_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    modified = False
    for field_name, limit in _FIELD_WORD_LIMITS.items():
        val = parsed.get(field_name)
        if isinstance(val, str) and len(val.split()) > limit:
            condensed = _apply_lossless_shorthand(val)
            if condensed != val:
                parsed[field_name] = condensed
                modified = True
        elif (
            isinstance(val, list)
            and all(isinstance(item, str) for item in val)
            and sum(len(item.split()) for item in val) > limit
        ):
            condensed_list = [_apply_lossless_shorthand(item) for item in val]
            if condensed_list != val:
                parsed[field_name] = condensed_list
                modified = True
    return parsed if modified else None


def _describe_word_overflows(cleaned_json: str) -> str:
    """Build an exact per-field / per-bullet word count breakdown for surgical LLM retries."""
    try:
        parsed = json.loads(cleaned_json)
    except json.JSONDecodeError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    details: list[str] = []
    for field_name, limit in _FIELD_WORD_LIMITS.items():
        val = parsed.get(field_name)
        if isinstance(val, str):
            wc = len(val.split())
            if wc > limit:
                target = max(limit - 20, 25)
                details.append(
                    f"- {field_name}: currently {wc} words (hard cap {limit}) -> rewrite under "
                    f"{target} words."
                )
        elif isinstance(val, list) and all(isinstance(item, str) for item in val):
            counts = [len(item.split()) for item in val]
            total = sum(counts)
            if total > limit:
                bullet_str = ", ".join(f"bullet {i + 1}: {c}w" for i, c in enumerate(counts))
                per_bullet_target = max((limit - 25) // max(len(counts), 1), 12)
                details.append(
                    f"- {field_name}: currently {total} words [{bullet_str}] (hard cap {limit}) "
                    f"-> shorten EACH bullet to under {per_bullet_target} words so the total is "
                    f"under {limit - 25} words."
                )
    return "\n".join(details)


def _should_send_reasoning_effort(base_url: str, model: str, disable_thinking: bool) -> bool:
    """Return True only when ``reasoning_effort="none"`` should be sent to the endpoint.

    Non-reasoning Groq models (e.g. ``llama-3.3-70b-versatile``, ``llama-3.1-8b-instant``)
    reject ``reasoning_effort`` with HTTP 400; skipping it upfront avoids wasting a
    free-tier RPM call on every synthesis request.
    """
    if not disable_thinking:
        return False
    if "api.groq.com" in base_url.lower():
        model_lower = model.lower()
        return any(token in model_lower for token in ("qwen3", "gpt-oss", "deepseek-r1"))
    return True


def synthesize_memo_with_llm(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
    *,
    sensitivity: DcfSensitivity | None = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str = "ollama",
    max_retries: int = 2,
    timeout_seconds: float = 300.0,
    temperature: float = 0.2,
    disable_thinking: bool = True,
    client: Any | None = None,
) -> InvestmentMemoSchema:
    """Synthesize a schema-validated, grounding-audited InvestmentMemoSchema via a local LLM.

    Automatically retries up to ``max_retries`` times (default 2, i.e., 3 total attempts)
    when JSON parsing, Pydantic validation, numeric grounding, or Single-Mention checks fail.
    Passes ``reasoning_effort="none"`` by default so Ollama thinking models (e.g.,
    ``inkling-2-mini:latest``, ``gemma4:31b-mlx``, ``qwen3.8:27b-mlx``) skip long hidden
    reasoning traces and emit structured JSON rapidly without hitting timeouts.
    """
    if max_retries < 0:
        raise SynthesisError("max_retries must be non-negative.")

    openai_client: Any = (
        client
        if client is not None
        else OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
    )

    base_messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_synthesis_user_prompt(
                snapshot, valuation, peers, sensitivity=sensitivity
            ),
        },
    ]
    messages: list[dict[str, str]] = list(base_messages)

    last_error_message = "No response received from model."
    last_error_is_grounding = False
    total_attempts = max_retries + 1
    use_reasoning_override = _should_send_reasoning_effort(base_url, model, disable_thinking)

    for attempt in range(1, total_attempts + 1):
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if use_reasoning_override:
            create_kwargs["reasoning_effort"] = "none"

        try:
            try:
                response = openai_client.chat.completions.create(**create_kwargs)
            except BadRequestError:
                if not use_reasoning_override:
                    raise
                # Servers or non-thinking models that reject `reasoning_effort` fall back cleanly.
                use_reasoning_override = False
                create_kwargs.pop("reasoning_effort", None)
                response = openai_client.chat.completions.create(**create_kwargs)
            raw_content = response.choices[0].message.content or ""
        except AuthenticationError as exc:
            raise SynthesisError(
                f"LLM authentication failed (401 Unauthorized) at '{base_url}' "
                f"for model '{model}': invalid or missing API key. Details: {exc}"
            ) from exc
        except RateLimitError as exc:
            raise SynthesisError(
                f"LLM rate limit exceeded (429 Too Many Requests) at '{base_url}' "
                f"for model '{model}': free-tier quota or RPM limit reached. Details: {exc}"
            ) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise SynthesisError(
                f"Unable to reach LLM endpoint at '{base_url}' for model '{model}': {exc}"
            ) from exc
        except APIError as exc:
            raise SynthesisError(
                f"LLM API error from '{base_url}' for model '{model}': {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise SynthesisError(
                f"Unexpected error calling LLM '{model}' at '{base_url}': {exc}"
            ) from exc

        cleaned_json = _strip_markdown_fences(raw_content)
        memo: InvestmentMemoSchema | None = None
        try:
            memo = InvestmentMemoSchema.model_validate_json(cleaned_json)
        except ValidationError as exc:
            # If only a word-limit overshoot occurred, try lossless institutional shorthand first.
            if "word" in str(exc).lower():
                condensed_dict = _condense_overflowing_json_fields(cleaned_json)
                if condensed_dict is not None:
                    try:
                        memo = InvestmentMemoSchema.model_validate(condensed_dict)
                    except ValidationError as exc2:
                        last_error_message = str(exc2)
                        last_error_is_grounding = False
                else:
                    last_error_message = str(exc)
                    last_error_is_grounding = False
            else:
                last_error_message = str(exc)
                last_error_is_grounding = False

        if memo is not None:
            audit_payload = build_audit_trail_payload(
                snapshot, valuation, peers, sensitivity=sensitivity
            )
            audit_keys: set[str] = set()
            _collect_audit_keys(audit_payload, audit_keys)
            memo = sanitize_memo_prose(memo, audit_keys=audit_keys)
            audit_violations = verify_memo_grounding_and_repetition(
                memo, snapshot, valuation, peers, sensitivity=sensitivity
            )
            if not audit_violations:
                return memo
            last_error_message = " ".join(audit_violations)
            last_error_is_grounding = True

        if attempt < total_attempts:
            if not last_error_is_grounding and "word" in last_error_message.lower():
                overflow_breakdown = _describe_word_overflows(cleaned_json)
                breakdown_block = (
                    f"\nExact word counts:\n{overflow_breakdown}\n"
                    if overflow_breakdown
                    else ""
                )
                retry_instruction = (
                    "Your previous JSON failed ONLY a strict word-count ceiling:\n"
                    f"{last_error_message}\n{breakdown_block}\n"
                    "Keep all other valid fields UNCHANGED and rewrite ONLY the overflowing "
                    "field(s) to be at least 20 words shorter (for executive_thesis, write at "
                    "most 2 crisp sentences under 40 words; for any overflowing bullet list, keep "
                    "EACH bullet under 18 words so the list totals under 60 words) while citing "
                    "ONLY the same verified Audit Trail numbers. Return valid raw JSON only."
                )
            else:
                retry_instruction = (
                    "Your previous JSON failed strict schema, anti-repetition, or numeric "
                    f"grounding validation.\nErrors:\n{last_error_message}\n\n"
                    "Fix every violation surgically: (1) If any field exceeded its word limit, "
                    "cut at least 20 words from that field so it sits comfortably below the "
                    "hard cap; (2) Replace or remove every unverified number listed above — "
                    "cite ONLY exact numbers from AUDIT_TRAIL_JSON; (3) DELETE any repeated "
                    "headline valuation figure (DCF dollar value, Comps dollar value, "
                    "implied_fcf_cagr_5y) from key_downside_risks, bull_case, bear_case, and "
                    "profitability_and_cash_quality — keep at most ONCE in executive_thesis "
                    "and ONCE in valuation_and_debate (for WACC risk in key_downside_risks, "
                    "state only WACC % / +100 bps without dollar DCF prices); (4) Ensure "
                    "valuation_and_debate and profitability_and_cash_quality open with an "
                    "analytical driver rather than a header metric. Return valid raw JSON only."
                )
            # Keep context tight (base prompt + only the latest attempt) to avoid anchoring on
            # multiple prior failed JSON drafts.
            messages = [
                *base_messages,
                {"role": "assistant", "content": raw_content},
                {"role": "user", "content": retry_instruction},
            ]

    error_cls = GroundingAuditError if last_error_is_grounding else SynthesisError
    raise error_cls(
        f"LLM synthesis failed validation after {total_attempts} attempts for model '{model}': "
        f"{last_error_message}"
    )


def _extract_business_driver_clause(business_summary: str | None, sector: str) -> str:
    """Extract a concise segment/product driver phrase from sanitized business_summary."""
    if not business_summary:
        return f"core {sector} product franchises"
    lowered = business_summary.lower()
    if "custom ai accelerators" in lowered or "infrastructure software" in lowered:
        return "custom AI accelerators, Ethernet networking switches, and infrastructure software"
    first_sentence = business_summary.split(".", 1)[0].strip()
    if len(first_sentence) > 90:
        trimmed = first_sentence[:87].rsplit(" ", 1)[0].rstrip(" ,;:-")
        return trimmed
    return first_sentence


def synthesize_mock_memo(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
) -> InvestmentMemoSchema:
    """Deterministically construct an institutional InvestmentMemoSchema from Audit Trail data."""
    multiples = compute_target_multiples(snapshot)
    ev_ebitda = multiples["ev_to_ebitda"]
    pe_ratio = multiples["pe_ratio"]

    upside_pct = valuation.dcf_upside_pct * 100.0
    direction = "upside" if upside_pct >= 0.0 else "downside"
    abs_upside_pct = abs(upside_pct)
    wacc_pct = valuation.dcf_assumptions["wacc"] * 100.0
    term_pct = valuation.dcf_assumptions["terminal_growth_rate"] * 100.0
    cagr_pct = valuation.dcf_assumptions["fcf_cagr"] * 100.0
    exit_mult = valuation.dcf_assumptions.get("target_exit_ev_ebitda", 15.0)
    hist_growth_pct = snapshot.historical_revenue_growth_3y * 100.0

    stance = (
        "Buy — attractive risk-adjusted upside"
        if upside_pct > 10.0
        else "Hold — trading near intrinsic value"
        if upside_pct >= -10.0
        else "Hold / Disciplined Entry — priced for perfection"
    )

    comps_spread = (
        f"and comps-implied ${valuation.implied_value_by_comps:,.2f}"
        if valuation.implied_value_by_comps is not None
        else "with incomplete peer multiples"
    )
    primary_driver = (
        "Sustained secular growth and elite cash conversion anchor upside, though multiple "
        "compression remains the primary risk."
        if upside_pct >= 0.0
        else "High cash conversion and secular demand support quality, but demanding implied "
        "growth creates valuation compression risk."
    )
    executive_thesis = (
        f"{snapshot.company_name} ({snapshot.ticker}): {stance}. Shares trade at "
        f"${snapshot.current_price:,.2f} versus base DCF of "
        f"${valuation.dcf_intrinsic_value_per_share:,.2f} ({abs_upside_pct:.1f}% {direction}) "
        f"{comps_spread}. {primary_driver}"
    )

    ev_ebitda_text = f"{ev_ebitda:.1f}x" if ev_ebitda is not None else "N/A"
    peer_ev_text = (
        f"{valuation.peer_median_ev_ebitda:.1f}x"
        if valuation.peer_median_ev_ebitda is not None
        else "N/A"
    )
    pe_text = f"{pe_ratio:.1f}x" if pe_ratio is not None else "N/A"
    forward_pe = multiples["forward_pe"]
    pe_compression = multiples["pe_compression_pct"]
    peer_pe_text = (
        f"{valuation.peer_median_pe:.1f}x" if valuation.peer_median_pe is not None else "N/A"
    )

    if forward_pe is not None and pe_compression is not None:
        forward_clause = (
            f"Forward earnings growth compresses valuation from {pe_text} trailing to "
            f"{forward_pe:.1f}x forward P/E ({pe_compression * 100.0:+.1f}% normalization)"
        )
    elif forward_pe is not None:
        forward_clause = f"Forward P/E stands at {forward_pe:.1f}x versus {pe_text} trailing"
    else:
        forward_clause = f"Trailing valuation sits at {pe_text} P/E and {ev_ebitda_text} EV/EBITDA"

    consensus_clause = (
        f", while sell-side consensus targets ${snapshot.analyst_target_mean:,.2f}."
        if snapshot.analyst_target_mean is not None
        else "."
    )

    if (
        valuation.implied_fcf_cagr_5y is not None
        and valuation.cagr_spread_vs_base is not None
        and valuation.implied_y5_fcf is not None
    ):
        implied_cagr_text = f"{valuation.implied_fcf_cagr_5y * 100.0:.1f}%"
        spread_pct = valuation.cagr_spread_vs_base * 100.0
        reverse_clause = (
            f"Reverse DCF shows the market embeds {implied_cagr_text} 5-year FCF CAGR "
            f"({spread_pct:+.1f}% vs. {cagr_pct:.1f}% base), requiring "
            f"{_format_billions(valuation.implied_y5_fcf)} Year-5 FCF."
        )
    else:
        reverse_clause = (
            f"Market pricing sits outside standard Reverse DCF bounds relative to our "
            f"{cagr_pct:.1f}% base growth case."
        )

    exit_clause = (
        f"Our {exit_mult:.1f}x Exit EV/EBITDA cross-check yields "
        f"${valuation.exit_multiple_dcf_value:,.2f}."
        if valuation.exit_multiple_dcf_value is not None
        else ""
    )
    comps_clause = (
        f"Peer medians ({peer_ev_text} EV/EBITDA, {peer_pe_text} P/E) imply "
        f"${valuation.implied_value_by_comps:,.2f}."
        if valuation.implied_value_by_comps is not None
        else f"Shares trade at {ev_ebitda_text} EV/EBITDA."
    )
    debate_lead = (
        f"The market debate around {snapshot.ticker} centers on whether secular infrastructure "
        f"demand justifies paying above perpetuity DCF "
        f"(${valuation.dcf_intrinsic_value_per_share:,.2f} at {wacc_pct:.2f}% WACC and "
        f"{term_pct:.2f}% terminal growth) versus peak-multiple risk."
        if upside_pct < 0.0
        else f"The variant perception on {snapshot.ticker} hinges on whether durable cash "
        f"generation drives a re-rating toward perpetuity DCF "
        f"(${valuation.dcf_intrinsic_value_per_share:,.2f} at {wacc_pct:.2f}% WACC) despite "
        f"cyclical skepticism."
    )

    valuation_and_debate = (
        f"{debate_lead} {forward_clause}{consensus_clause} {exit_clause} {reverse_clause} "
        f"{comps_clause}"
    ).strip()

    gm_text = (
        f"{snapshot.gross_margin_ttm * 100.0:.1f}%"
        if snapshot.gross_margin_ttm is not None
        else "N/A"
    )
    om_text = (
        f"{snapshot.operating_margin_ttm * 100.0:.1f}%"
        if snapshot.operating_margin_ttm is not None
        else "N/A"
    )
    roic_text = f"{snapshot.roic_ttm * 100.0:.1f}%" if snapshot.roic_ttm is not None else "N/A"
    business_driver = _extract_business_driver_clause(snapshot.business_summary, snapshot.sector)
    gap_driver = (
        snapshot.working_capital_metrics.ocf_net_income_gap_driver
        if snapshot.working_capital_metrics is not None
        else "Cash conversion reflects working-capital and non-cash accrual dynamics."
    )
    sbc_note = (
        f"Deducting {_format_billions(snapshot.sbc_ttm)} in stock-based compensation trims "
        f"owner cash flow, yet capital returns remain covered on "
        f"{_format_billions(snapshot.revenue_ttm)} TTM revenue."
        if snapshot.sbc_ttm is not None
        else f"Owner cash flow remains resilient across {_format_billions(snapshot.revenue_ttm)} "
        f"in TTM revenue."
    )
    if (
        has_amortization_margin_gap(snapshot)
        and snapshot.ebitda_margin_ttm is not None
        and snapshot.fcf_margin_ttm is not None
    ):
        amort_note = (
            f"Despite non-cash amortization weighing on GAAP operating margin ({om_text}), "
            f"underlying cash-flow durability remains elite at "
            f"{snapshot.ebitda_margin_ttm * 100.0:.1f}% EBITDA margin and "
            f"{snapshot.fcf_margin_ttm * 100.0:.1f}% FCF margin."
        )
    else:
        amort_note = ""
    # Strict opening-sentence anti-echoing: lead with business mix and operating mechanism.
    profitability_and_cash_quality = (
        f"{snapshot.company_name}'s {business_driver} mix underpins resilient unit economics and "
        f"{valuation.earnings_quality_flag} cash conversion across the capital base. "
        f"{amort_note} {sbc_note} {gap_driver}"
    ).replace("  ", " ").strip()

    net_cash_val = snapshot.net_cash if snapshot.net_cash is not None else (
        snapshot.cash_and_equivalents - snapshot.total_debt
    )
    dso_text = (
        f"{snapshot.working_capital_metrics.dso_days:.1f} days"
        if (
            snapshot.working_capital_metrics is not None
            and snapshot.working_capital_metrics.dso_days is not None
        )
        else "elevated levels"
    )
    dio_text = (
        f"{snapshot.working_capital_metrics.dio_days:.1f} days"
        if (
            snapshot.working_capital_metrics is not None
            and snapshot.working_capital_metrics.dio_days is not None
        )
        else "historical norms"
    )

    bull_case = [
        (
            f"Secular demand across {business_driver} reinforces pricing power and sustains "
            f"{roic_text} ROIC."
        ),
        (
            f"Strong {hist_growth_pct:.1f}% 3-year revenue CAGR demonstrates hyperscale and "
            f"enterprise momentum exceeding conservative baseline assumptions."
        ),
        (
            f"Healthy {valuation.ocf_to_net_income_ratio:.2f}x cash conversion and low "
            f"{_format_billions(snapshot.capex_ttm)} CapEx fund rapid balance-sheet deleveraging."
        ),
    ]

    bear_case = [
        (
            f"Hyperscaler digestion or spending pauses across {business_driver} would trigger "
            f"multiple compression against demanding expectations."
        ),
        (
            f"Wide peer dispersion across {snapshot.sector} comparables exposes {pe_text} P/E to "
            f"re-rating risk if {hist_growth_pct:.1f}% top-line momentum slows."
        ),
        (
            f"Net cash position of {_format_billions(net_cash_val)} and "
            f"{_format_billions(snapshot.total_debt)} total debt heighten equity sensitivity to "
            f"refinancing spreads."
        ),
    ]

    key_downside_risks = [
        (
            f"Margin trigger: operating margin slipping below {om_text} or gross margin eroding "
            f"from {gm_text} signals pricing pressure."
        ),
        (
            f"Working-capital trigger: DSO extending beyond {dso_text} or DIO rising past "
            f"{dio_text} warns of channel inventory build."
        ),
        (
            f"Discount-rate trigger: a 100 bps WACC shift above {wacc_pct:.2f}% materially lowers "
            f"present value of terminal cash flows."
        ),
        (
            f"Dilution trigger: rising stock-based compensation compressing SBC-adjusted FCF "
            f"and weakening cash conversion below {valuation.ocf_to_net_income_ratio:.2f}x."
        ),
    ]

    return InvestmentMemoSchema(
        executive_thesis=executive_thesis,
        valuation_and_debate=valuation_and_debate,
        profitability_and_cash_quality=profitability_and_cash_quality,
        bull_case=bull_case,
        bear_case=bear_case,
        key_downside_risks=key_downside_risks,
    )
