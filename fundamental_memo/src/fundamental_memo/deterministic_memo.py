"""Pure-Python deterministic rule-based memo engine and graceful hybrid LLM fallback."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

from fundamental_memo.memo_synthesizer import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    _extract_business_driver_clause,
    _format_billions,
    has_amortization_margin_gap,
    synthesize_memo_with_llm,
)
from fundamental_memo.renderer import render_investment_memo
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

DETERMINISTIC_MODE_LABEL = "Deterministic Rule Engine (Zero-LLM)"
LOCALHOST_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

PROVIDER_GROQ = "Groq (Cloud Free Tier)"
PROVIDER_OLLAMA = "Local Ollama"
PROVIDER_CUSTOM = "Custom OpenAI-Compatible"
LLM_PROVIDERS: tuple[str, ...] = (PROVIDER_GROQ, PROVIDER_OLLAMA, PROVIDER_CUSTOM)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_CUSTOM_MODEL_OPTION = "Custom model ID..."
GROQ_MODEL_PRESETS: tuple[str, ...] = (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3-32b",
    GROQ_CUSTOM_MODEL_OPTION,
)
OLLAMA_DEFAULT_MODEL = "qwen3.8:27b-mlx"
OLLAMA_MODEL_PRESETS: tuple[str, ...] = (
    "qwen3.8:27b-mlx",
    "inkling-2-mini:latest",
    "gemma4:31b-mlx",
    "gemma4:26b-mlx",
)

HYBRID_MODEL_PRESETS: tuple[str, ...] = (
    "qwen3.8:27b-mlx",
    "inkling-2-mini:latest",
    "gemma4:31b-mlx",
    "gemma4:26b-mlx",
    "llama-3.3-70b-versatile",
)


@dataclass(frozen=True)
class MemoGenerationOutcome:
    """Result of hybrid AI or Deterministic Rule Engine memo synthesis."""

    memo_output: InvestmentMemoSchema
    mode_label: str
    used_deterministic: bool
    fallback_notice: str | None = None
    fallback_severity: Literal["caption", "warning"] = "caption"


def resolve_provider_api_key(
    provider: str,
    user_input: str = "",
    secrets_lookup: Callable[[str], str | None] | None = None,
) -> tuple[str, bool]:
    """Resolve the active API key and whether it originated from secrets/environment.

    Priority for Groq:
      1. Explicit sidebar ``user_input``
      2. ``secrets_lookup("GROQ_API_KEY")`` (e.g. ``st.secrets``)
      3. ``os.getenv("GROQ_API_KEY")``
      4. ``secrets_lookup("LLM_API_KEY")``
      5. ``os.getenv("LLM_API_KEY")``
    """
    cleaned_input = user_input.strip()
    if cleaned_input:
        return cleaned_input, False

    if provider == PROVIDER_OLLAMA:
        return "", False

    def _read_secret(name: str) -> str:
        if secrets_lookup is None:
            return ""
        try:
            raw = secrets_lookup(name)
            return str(raw).strip() if raw else ""
        except Exception:  # noqa: BLE001
            return ""

    def _read_env(name: str) -> str:
        raw = os.getenv(name, "")
        return raw.strip() if raw else ""

    if provider == PROVIDER_GROQ:
        for candidate in (
            _read_secret("GROQ_API_KEY"),
            _read_env("GROQ_API_KEY"),
            _read_secret("LLM_API_KEY"),
            _read_env("LLM_API_KEY"),
        ):
            if candidate:
                return candidate, True
        return "", False

    for candidate in (_read_secret("LLM_API_KEY"), _read_env("LLM_API_KEY")):
        if candidate:
            return candidate, True
    return "", False


def is_localhost_url(base_url: str) -> bool:
    """Return True when the configured OpenAI-compatible base URL targets localhost."""
    parsed = urlparse(base_url.strip())
    host = (parsed.hostname or "").strip().lower()
    return host in LOCALHOST_HOSTS


def probe_local_llm_endpoint(
    base_url: str = DEFAULT_BASE_URL,
    *,
    timeout: float = 0.25,
) -> bool:
    """Fast (< 0.3s) TCP reachability probe for a local Ollama/MLX endpoint.

    Returns False immediately for non-localhost URLs or any socket timeout/refusal.
    """
    if not is_localhost_url(base_url):
        return False
    parsed = urlparse(base_url.strip())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def build_deterministic_memo_schema(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
) -> InvestmentMemoSchema:
    """Build a strictly grounded 6-section InvestmentMemoSchema purely from threshold rules.

    Populated exclusively from verified FinancialSnapshot, ValuationAnalysis, and PeerComparable
    metrics with zero external LLM calls. Adapts Bull/Bear/Risk bullets dynamically using
    institutional thresholds (ROIC > 15%, Forward P/E compression > 20%, Reverse DCF implied
    5Y FCF CAGR > 25%, amortization spread > 15pp, working-capital DSO/DIO, WACC sensitivity).
    """
    multiples = compute_target_multiples(snapshot)
    ev_ebitda = multiples["ev_to_ebitda"]
    pe_ratio = multiples["pe_ratio"]
    forward_pe = multiples["forward_pe"]
    pe_compression = multiples["pe_compression_pct"]

    upside_pct = valuation.dcf_upside_pct * 100.0
    direction = "upside" if upside_pct >= 0.0 else "downside"
    abs_upside_pct = abs(upside_pct)
    wacc_pct = valuation.dcf_assumptions["wacc"] * 100.0
    term_pct = valuation.dcf_assumptions["terminal_growth_rate"] * 100.0
    cagr_pct = valuation.dcf_assumptions["fcf_cagr"] * 100.0
    exit_mult = valuation.dcf_assumptions.get("target_exit_ev_ebitda", 15.0)
    hist_growth_pct = snapshot.historical_revenue_growth_3y * 100.0

    stance = (
        "Buy — compelling intrinsic upside"
        if upside_pct > 10.0
        else "Hold — balanced near fair value"
        if upside_pct >= -10.0
        else "Hold / Disciplined Entry — rich implied growth"
    )

    comps_part = (
        f", comps ${valuation.implied_value_by_comps:,.2f}"
        if valuation.implied_value_by_comps is not None
        else ""
    )
    exit_part = (
        f", exit DCF ${valuation.exit_multiple_dcf_value:,.2f}"
        if valuation.exit_multiple_dcf_value is not None
        else ""
    )
    implied_part = (
        f" Reverse DCF prices {valuation.implied_fcf_cagr_5y * 100.0:.1f}% 5Y FCF CAGR."
        if valuation.implied_fcf_cagr_5y is not None
        else ""
    )
    executive_thesis = (
        f"{snapshot.company_name} ({snapshot.ticker}): {stance}. At "
        f"${snapshot.current_price:,.2f}, shares compare against base DCF "
        f"${valuation.dcf_intrinsic_value_per_share:,.2f} ({abs_upside_pct:.1f}% {direction})"
        f"{exit_part}{comps_part}.{implied_part}"
    ).strip()

    ev_ebitda_text = f"{ev_ebitda:.1f}x" if ev_ebitda is not None else "N/A"
    peer_ev_text = (
        f"{valuation.peer_median_ev_ebitda:.1f}x"
        if valuation.peer_median_ev_ebitda is not None
        else "N/A"
    )
    pe_text = f"{pe_ratio:.1f}x" if pe_ratio is not None else "N/A"
    peer_pe_text = (
        f"{valuation.peer_median_pe:.1f}x" if valuation.peer_median_pe is not None else "N/A"
    )

    if forward_pe is not None and pe_compression is not None:
        forward_clause = (
            f"Forward earnings compress P/E from {pe_text} trailing to "
            f"{forward_pe:.1f}x forward ({pe_compression * 100.0:+.1f}% normalization)"
        )
    elif forward_pe is not None:
        forward_clause = f"Forward P/E sits at {forward_pe:.1f}x vs. {pe_text} trailing"
    else:
        forward_clause = f"Trailing multiples stand at {pe_text} P/E and {ev_ebitda_text} EV/EBITDA"

    consensus_clause = (
        f", alongside a ${snapshot.analyst_target_mean:,.2f} consensus target."
        if snapshot.analyst_target_mean is not None
        else "."
    )

    if (
        valuation.implied_fcf_cagr_5y is not None
        and valuation.cagr_spread_vs_base is not None
        and valuation.implied_y5_fcf is not None
        and valuation.implied_y5_fcf_multiple is not None
    ):
        implied_cagr_text = f"{valuation.implied_fcf_cagr_5y * 100.0:.1f}%"
        spread_pct = valuation.cagr_spread_vs_base * 100.0
        reverse_clause = (
            f"Reverse DCF embeds {implied_cagr_text} 5Y FCF CAGR "
            f"({spread_pct:+.1f}% vs. {cagr_pct:.1f}% base), requiring "
            f"{_format_billions(valuation.implied_y5_fcf)} Year-5 FCF "
            f"({valuation.implied_y5_fcf_multiple:.2f}x current FCF)."
        )
    else:
        reverse_clause = (
            f"Market pricing falls outside standard Reverse DCF brackets vs. our "
            f"{cagr_pct:.1f}% base growth assumption."
        )

    exit_clause = (
        f"Our {exit_mult:.1f}x Exit EV/EBITDA cross-check implies "
        f"${valuation.exit_multiple_dcf_value:,.2f}."
        if valuation.exit_multiple_dcf_value is not None
        else ""
    )
    comps_clause = (
        f"Peer medians ({peer_ev_text} EV/EBITDA, {peer_pe_text} P/E) indicate "
        f"${valuation.implied_value_by_comps:,.2f}."
        if valuation.implied_value_by_comps is not None
        else f"Shares trade at {ev_ebitda_text} EV/EBITDA."
    )
    debate_lead = (
        f"The market debate around {snapshot.ticker} hinges on whether secular demand justifies "
        f"a premium over perpetuity DCF (${valuation.dcf_intrinsic_value_per_share:,.2f} at "
        f"{wacc_pct:.2f}% WACC, {term_pct:.2f}% terminal growth) vs. multiple-compression risk."
        if upside_pct < 0.0
        else f"The variant perception on {snapshot.ticker} centers on whether durable FCF drives "
        f"re-rating toward perpetuity DCF (${valuation.dcf_intrinsic_value_per_share:,.2f} at "
        f"{wacc_pct:.2f}% WACC) despite cyclical skepticism."
    )
    valuation_and_debate = (
        f"{debate_lead} {forward_clause}{consensus_clause} {exit_clause} {reverse_clause} "
        f"{comps_clause}"
    ).replace("  ", " ").strip()

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
    fcf_margin_text = (
        f"{snapshot.fcf_margin_ttm * 100.0:.1f}%"
        if snapshot.fcf_margin_ttm is not None
        else "N/A"
    )
    business_driver = _extract_business_driver_clause(snapshot.business_summary, snapshot.sector)
    gap_driver = (
        snapshot.working_capital_metrics.ocf_net_income_gap_driver
        if snapshot.working_capital_metrics is not None
        else "Cash conversion reflects working-capital and non-cash accrual dynamics."
    )
    sbc_note = (
        f"Deducting {_format_billions(snapshot.sbc_ttm)} SBC leaves "
        f"{_format_billions(snapshot.sbc_adjusted_fcf_ttm)} owner FCF on "
        f"{_format_billions(snapshot.revenue_ttm)} TTM revenue."
        if (snapshot.sbc_ttm is not None and snapshot.sbc_adjusted_fcf_ttm is not None)
        else f"Owner FCF remains resilient on {_format_billions(snapshot.revenue_ttm)} TTM revenue."
    )
    if (
        has_amortization_margin_gap(snapshot)
        and snapshot.ebitda_margin_ttm is not None
        and snapshot.fcf_margin_ttm is not None
    ):
        amort_note = (
            f"Non-cash amortization depresses GAAP operating margin ({om_text}), whereas cash-flow "
            f"durability remains strong at {snapshot.ebitda_margin_ttm * 100.0:.1f}% EBITDA "
            f"margin and {fcf_margin_text} FCF margin."
        )
    else:
        amort_note = ""

    profitability_and_cash_quality = (
        f"{snapshot.company_name}'s {business_driver} mix anchors resilient unit economics and "
        f"{valuation.earnings_quality_flag} cash conversion across the capital base. "
        f"{amort_note} {sbc_note} {gap_driver}"
    ).replace("  ", " ").strip()

    # Threshold-driven Bull Case bullets (3 concise bullets, <= 90 words total)
    if snapshot.roic_ttm is not None and snapshot.roic_ttm > 0.15:
        bull_1 = (
            f"Elite capital efficiency ({roic_text} ROIC) anchored by {business_driver} compounds "
            f"intrinsic value well above cost of capital."
        )
    else:
        bull_1 = (
            f"Secular demand across {business_driver} reinforces pricing power and supports "
            f"{roic_text} ROIC durability."
        )

    if forward_pe is not None and pe_compression is not None and pe_compression < -0.20:
        bull_2 = (
            f"Rapid earnings scaling drives {abs(pe_compression) * 100.0:.1f}% forward P/E "
            f"compression to {forward_pe:.1f}x, backed by {hist_growth_pct:.1f}% 3Y revenue CAGR."
        )
    else:
        bull_2 = (
            f"Strong {hist_growth_pct:.1f}% 3Y revenue CAGR demonstrates end-market momentum "
            f"exceeding conservative baseline assumptions."
        )

    bull_3 = (
        f"Disciplined {valuation.ocf_to_net_income_ratio:.2f}x OCF/NI conversion, "
        f"{fcf_margin_text} FCF margin, and {_format_billions(snapshot.capex_ttm)} CapEx fund "
        f"shareholder returns."
    )
    bull_case = [bull_1, bull_2, bull_3]

    # Threshold-driven Bear Case bullets (3 concise bullets, <= 90 words total; no DCF/Comps/CAGR)
    bear_1 = (
        f"Customer digestion or spending pauses across {business_driver} would pressure "
        f"top-line momentum and operating leverage."
    )
    if valuation.implied_fcf_cagr_5y is not None and valuation.implied_fcf_cagr_5y > 0.25:
        bear_2 = (
            f"Demanding market-implied growth leaves little margin of safety, exposing "
            f"{pe_text} trailing P/E to sharp multiple compression if {hist_growth_pct:.1f}% "
            f"growth moderates."
        )
    else:
        bear_2 = (
            f"Peer dispersion across {snapshot.sector} comparables exposes {pe_text} P/E and "
            f"{ev_ebitda_text} EV/EBITDA to re-rating risk if growth decelerates."
        )

    net_cash_val = (
        snapshot.net_cash
        if snapshot.net_cash is not None
        else (snapshot.cash_and_equivalents - snapshot.total_debt)
    )
    if net_cash_val < 0.0:
        bear_3 = (
            f"Negative net cash ({_format_billions(net_cash_val)}) with "
            f"{_format_billions(snapshot.total_debt)} total debt heightens sensitivity to "
            f"refinancing spreads."
        )
    elif snapshot.sbc_ttm is not None and snapshot.sbc_ttm > 0.0:
        bear_3 = (
            f"Ongoing {_format_billions(snapshot.sbc_ttm)} SBC dilutes true owner cash flow "
            f"below headline FCF across cycles."
        )
    else:
        bear_3 = (
            f"Gross margin erosion from {gm_text} or working-capital absorption would weaken "
            f"cash generation."
        )
    bear_case = [bear_1, bear_2, bear_3]

    # Actionable Key Downside Risks (4 bullets, <= 90 words total; exact Audit Trail baselines)
    dso_text = (
        f"{snapshot.working_capital_metrics.dso_days:.1f} days"
        if (
            snapshot.working_capital_metrics is not None
            and snapshot.working_capital_metrics.dso_days is not None
        )
        else "current levels"
    )
    dio_text = (
        f"{snapshot.working_capital_metrics.dio_days:.1f} days"
        if (
            snapshot.working_capital_metrics is not None
            and snapshot.working_capital_metrics.dio_days is not None
        )
        else "historical norms"
    )
    key_downside_risks = [
        f"Margin trigger: operating margin slipping below {om_text} or gross margin below "
        f"{gm_text} signals pricing pressure.",
        f"Working-capital trigger: DSO extending beyond {dso_text} or DIO above {dio_text} warns "
        f"of channel inventory build.",
        f"Discount-rate trigger: a 100 bps WACC increase above {wacc_pct:.2f}% materially "
        f"compresses terminal value.",
        f"Cash-quality trigger: rising SBC weakening OCF/NI conversion below "
        f"{valuation.ocf_to_net_income_ratio:.2f}x.",
    ]

    return InvestmentMemoSchema(
        executive_thesis=executive_thesis,
        valuation_and_debate=valuation_and_debate,
        profitability_and_cash_quality=profitability_and_cash_quality,
        bull_case=bull_case,
        bear_case=bear_case,
        key_downside_risks=key_downside_risks,
    )


def build_deterministic_memo(audit_trail: Mapping[str, Any]) -> str:
    """Build a complete, grounding-audited Markdown memo purely from an Audit Trail dict."""
    snapshot = FinancialSnapshot.model_validate(audit_trail["financial_snapshot"])
    valuation = ValuationAnalysis.model_validate(audit_trail["valuation_analysis"])
    peers = [
        PeerComparable.model_validate(peer_item)
        for peer_item in audit_trail.get("peer_comparables", [])
    ]
    raw_sensitivity = audit_trail.get("dcf_sensitivity")
    sensitivity = (
        DcfSensitivity.model_validate(raw_sensitivity)
        if raw_sensitivity is not None
        else compute_dcf_sensitivity(
            snapshot,
            wacc=valuation.dcf_assumptions["wacc"],
            terminal_growth_rate=valuation.dcf_assumptions["terminal_growth_rate"],
            projection_years=int(valuation.dcf_assumptions["projection_years"]),
            fcf_cagr_override=valuation.dcf_assumptions["fcf_cagr"],
        )
    )
    memo_schema = build_deterministic_memo_schema(snapshot, valuation, peers)
    return render_investment_memo(
        snapshot,
        valuation,
        peers,
        memo_schema,
        sensitivity=sensitivity,
        enforce_grounding=True,
    )


def _classify_fallback_error(
    exc: Exception, *, is_local: bool
) -> tuple[str, Literal["caption", "warning"]] | None:
    """Classify recoverable LLM endpoint errors into a user-facing notice and severity."""
    if isinstance(exc, GroundingAuditError):
        return None
    msg = str(exc).lower()
    if "401 unauthorized" in msg or "authentication failed" in msg:
        return (
            "API authentication failed (401 Unauthorized) — check your API key. "
            "Switched to Deterministic Rule Engine.",
            "warning",
        )
    if "429 too many requests" in msg or "rate limit" in msg:
        return (
            "LLM rate limit reached (429 Too Many Requests) — wait briefly or switch to "
            "llama-3.1-8b-instant. Switched to Deterministic Rule Engine.",
            "warning",
        )
    connectivity_markers = (
        "unable to reach",
        "timed out",
        "connection",
        "api error",
        "unexpected error calling",
    )
    if any(marker in msg for marker in connectivity_markers):
        notice = (
            "Local LLM unreachable — switched to Deterministic Rule Engine"
            if is_local
            else "LLM endpoint unreachable — switched to Deterministic Rule Engine"
        )
        return notice, "caption"
    return None


def generate_memo(
    snapshot: FinancialSnapshot,
    valuation: ValuationAnalysis,
    peers: Sequence[PeerComparable],
    *,
    sensitivity: DcfSensitivity | None = None,
    use_ai_synthesis: bool = False,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    api_key: str = "",
    max_retries: int = 2,
    allow_fallback: bool = True,
    client: Any | None = None,
) -> MemoGenerationOutcome:
    """Unified hybrid memo generator supporting local Ollama, BYOK cloud API, or zero-LLM mode.

    - Bypasses the LLM immediately when ``use_ai_synthesis`` is False.
    - Bypasses the LLM immediately when ``base_url`` is non-localhost and ``api_key`` is empty.
    - Catches authentication (401), rate-limit (429), and connectivity/timeout errors when
      ``allow_fallback=True`` and switches cleanly to the Deterministic Rule Engine with an
      explicit notice.
    """
    if not use_ai_synthesis:
        memo_output = build_deterministic_memo_schema(snapshot, valuation, peers)
        return MemoGenerationOutcome(
            memo_output=memo_output,
            mode_label=DETERMINISTIC_MODE_LABEL,
            used_deterministic=True,
            fallback_notice=None,
            fallback_severity="caption",
        )

    cleaned_url = base_url.strip() or DEFAULT_BASE_URL
    cleaned_key = api_key.strip()
    is_local = is_localhost_url(cleaned_url)

    if not is_local and not cleaned_key and client is None:
        memo_output = build_deterministic_memo_schema(snapshot, valuation, peers)
        return MemoGenerationOutcome(
            memo_output=memo_output,
            mode_label=DETERMINISTIC_MODE_LABEL,
            used_deterministic=True,
            fallback_notice=(
                "Cloud API key not configured — switched to Deterministic Rule Engine"
            ),
            fallback_severity="warning",
        )

    effective_key = cleaned_key if cleaned_key else "ollama"
    try:
        memo_output = synthesize_memo_with_llm(
            snapshot,
            valuation,
            peers,
            sensitivity=sensitivity,
            model=model,
            base_url=cleaned_url,
            api_key=effective_key,
            max_retries=max_retries,
            client=client,
        )
        return MemoGenerationOutcome(
            memo_output=memo_output,
            mode_label=f"AI Synthesis ({model})",
            used_deterministic=False,
            fallback_notice=None,
            fallback_severity="caption",
        )
    except SynthesisError as exc:
        classified = _classify_fallback_error(exc, is_local=is_local)
        if not allow_fallback or classified is None:
            raise
        notice, severity = classified
        memo_output = build_deterministic_memo_schema(snapshot, valuation, peers)
        return MemoGenerationOutcome(
            memo_output=memo_output,
            mode_label=DETERMINISTIC_MODE_LABEL,
            used_deterministic=True,
            fallback_notice=notice,
            fallback_severity=severity,
        )
