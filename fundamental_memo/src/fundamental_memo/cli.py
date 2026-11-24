"""Command-line interface and shared end-to-end orchestration pipeline."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fundamental_memo.data_fetcher import fetch_market_data
from fundamental_memo.memo_synthesizer import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    build_audit_trail_payload,
    synthesize_memo_with_llm,
    synthesize_mock_memo,
)
from fundamental_memo.renderer import render_investment_memo
from fundamental_memo.schemas import (
    DcfSensitivity,
    FinancialSnapshot,
    FundamentalMemoError,
    InvestmentMemoSchema,
    PeerComparable,
    ValuationAnalysis,
    count_words,
)
from fundamental_memo.valuation_engine import (
    DEFAULT_EXIT_EV_EBITDA,
    DEFAULT_TERMINAL_GROWTH,
    DEFAULT_WACC,
    compute_dcf_sensitivity,
    run_valuation_analysis,
)


@dataclass(frozen=True)
class PipelineResult:
    """Complete output of a single fundamental analysis and memo generation run."""

    snapshot: FinancialSnapshot
    peers: list[PeerComparable]
    valuation: ValuationAnalysis
    sensitivity: DcfSensitivity
    memo_output: InvestmentMemoSchema
    markdown: str
    word_count: int
    used_mock_llm: bool

    def audit_trail_json(self) -> dict[str, Any]:
        """Return the canonical Audit Trail JSON payload for export and UI display."""
        return build_audit_trail_payload(
            self.snapshot, self.valuation, self.peers, sensitivity=self.sensitivity
        )


def parse_peer_tickers(raw_peers: str) -> list[str]:
    """Parse a comma-separated peer ticker string into deduplicated uppercase tickers."""
    seen: set[str] = set()
    parsed: list[str] = []
    for token in raw_peers.split(","):
        symbol = token.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            parsed.append(symbol)
    return parsed


def run_memo_pipeline(
    *,
    ticker: str,
    peers: Sequence[str],
    wacc: float = DEFAULT_WACC,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    fcf_cagr: float | None = None,
    exit_ev_ebitda: float = DEFAULT_EXIT_EV_EBITDA,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    mock_data: bool = False,
    fixture_path: Path | None = None,
    live_llm: bool = False,
    max_retries: int = 2,
) -> PipelineResult:
    """Execute fetch -> quantitative valuation -> synthesis -> grounded Markdown rendering."""
    target_symbol = ticker.strip().upper()
    filtered_peers = [
        peer.strip().upper()
        for peer in peers
        if peer.strip() and peer.strip().upper() != target_symbol
    ]
    bundle = fetch_market_data(
        ticker=target_symbol,
        peer_tickers=filtered_peers,
        mock_data=mock_data,
        fixture_path=fixture_path,
    )
    valuation = run_valuation_analysis(
        bundle.snapshot,
        bundle.peers,
        wacc=wacc,
        terminal_growth_rate=terminal_growth,
        fcf_cagr_override=fcf_cagr,
        target_exit_ev_ebitda=exit_ev_ebitda,
    )
    sensitivity = compute_dcf_sensitivity(
        bundle.snapshot,
        wacc=wacc,
        terminal_growth_rate=terminal_growth,
        fcf_cagr_override=valuation.dcf_assumptions["fcf_cagr"],
    )

    use_mock_llm = mock_data and not live_llm
    if use_mock_llm:
        memo_output = synthesize_mock_memo(bundle.snapshot, valuation, bundle.peers)
    else:
        memo_output = synthesize_memo_with_llm(
            bundle.snapshot,
            valuation,
            bundle.peers,
            sensitivity=sensitivity,
            model=model,
            base_url=base_url,
            max_retries=max_retries,
        )

    markdown = render_investment_memo(
        bundle.snapshot,
        valuation,
        bundle.peers,
        memo_output,
        sensitivity=sensitivity,
    )
    return PipelineResult(
        snapshot=bundle.snapshot,
        peers=bundle.peers,
        valuation=valuation,
        sensitivity=sensitivity,
        memo_output=memo_output,
        markdown=markdown,
        word_count=count_words(markdown),
        used_mock_llm=use_mock_llm,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser for fundamental_memo."""
    parser = argparse.ArgumentParser(
        prog="python -m fundamental_memo.cli",
        description=(
            "Deterministic equity fundamental analysis and one-page investment memo generator."
        ),
    )
    parser.add_argument(
        "--ticker",
        required=True,
        help="Target equity ticker symbol (e.g., AVGO).",
    )
    parser.add_argument(
        "--peers",
        default="",
        help="Comma-separated list of 3-5 peer ticker symbols (e.g., NVDA,AMD,MRVL,QCOM).",
    )
    parser.add_argument(
        "--wacc",
        type=float,
        default=DEFAULT_WACC,
        help=f"Weighted Average Cost of Capital as a decimal (default: {DEFAULT_WACC}).",
    )
    parser.add_argument(
        "--terminal-growth",
        type=float,
        default=DEFAULT_TERMINAL_GROWTH,
        help=f"Gordon Growth terminal rate as a decimal (default: {DEFAULT_TERMINAL_GROWTH}).",
    )
    parser.add_argument(
        "--fcf-cagr",
        type=float,
        default=None,
        help="Optional explicit 5-year FCF CAGR override (defaults to clamped 3Y revenue growth).",
    )
    parser.add_argument(
        "--exit-multiple",
        type=float,
        default=DEFAULT_EXIT_EV_EBITDA,
        help=(
            "Terminal Exit EV/EBITDA multiple for cross-check "
            f"(default: {DEFAULT_EXIT_EV_EBITDA})."
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Local OpenAI-compatible model identifier (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"OpenAI-compatible base URL for Ollama/MLX (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output Markdown file path (default: memo_<TICKER>.md).",
    )
    parser.add_argument(
        "--mock-data",
        action="store_true",
        help=(
            "Run deterministically offline using bundled fixture data and deterministic mock "
            "synthesis (combine with --live-llm to call a local LLM on mock financials)."
        ),
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=None,
        help="Optional local JSON fixture file path supplying target snapshot and peer data.",
    )
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help=(
            "When combined with --mock-data, invoke the configured local LLM instead of "
            "deterministic mock prose."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning POSIX exit code."""
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    normalized_ticker = args.ticker.strip().upper()
    peer_list = parse_peer_tickers(args.peers)
    output_path: Path = args.output or Path(f"memo_{normalized_ticker}.md")

    try:
        result = run_memo_pipeline(
            ticker=normalized_ticker,
            peers=peer_list,
            wacc=args.wacc,
            terminal_growth=args.terminal_growth,
            fcf_cagr=args.fcf_cagr,
            exit_ev_ebitda=args.exit_multiple,
            model=args.model,
            base_url=args.base_url,
            mock_data=args.mock_data,
            fixture_path=args.fixture_path,
            live_llm=args.live_llm,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.markdown, encoding="utf-8")
    except (FundamentalMemoError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    synthesis_label = "offline-mock" if result.used_mock_llm else args.model
    implied_text = (
        f"{result.valuation.implied_fcf_cagr_5y * 100.0:.1f}%"
        if result.valuation.implied_fcf_cagr_5y is not None
        else "N/A"
    )
    print(
        f"Generated {output_path} for {result.snapshot.ticker} "
        f"(DCF: ${result.valuation.dcf_intrinsic_value_per_share:,.2f}, "
        f"Implied CAGR: {implied_text}, "
        f"Words: {result.word_count}, Synthesizer: {synthesis_label})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
