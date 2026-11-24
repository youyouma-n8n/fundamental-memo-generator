"""Pure-Python batch watchlist valuation screener (zero LLM latency)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fundamental_memo.data_fetcher import fetch_financial_snapshot, load_mock_market_data
from fundamental_memo.schemas import FinancialSnapshot, FundamentalMemoError
from fundamental_memo.valuation_engine import (
    DEFAULT_EXIT_EV_EBITDA,
    DEFAULT_MAX_FCF_GROWTH,
    DEFAULT_TERMINAL_GROWTH,
    DEFAULT_WACC,
    compute_target_multiples,
    run_valuation_analysis,
)


def _deduplicate_tickers(tickers: Sequence[str]) -> list[str]:
    """Normalize and deduplicate ticker symbols while preserving input order."""
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in tickers:
        symbol = raw.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized


def _evaluate_single_ticker(
    symbol: str,
    *,
    wacc: float,
    terminal_growth: float,
    base_cagr: float,
    exit_multiple: float,
    offline_mock: bool,
    snapshot_fetcher: Callable[[str], FinancialSnapshot] | None,
) -> dict[str, Any]:
    """Fetch and quantitatively value a single ticker, isolating any fetch/valuation error."""
    try:
        if snapshot_fetcher is not None:
            snapshot = snapshot_fetcher(symbol)
        elif offline_mock:
            snapshot = load_mock_market_data(ticker=symbol).snapshot
        else:
            snapshot = fetch_financial_snapshot(symbol)

        valuation = run_valuation_analysis(
            snapshot,
            [],
            wacc=wacc,
            terminal_growth_rate=terminal_growth,
            fcf_cagr_override=base_cagr,
            target_exit_ev_ebitda=exit_multiple,
        )
        multiples = compute_target_multiples(snapshot)
        return {
            "ticker": snapshot.ticker,
            "company_name": snapshot.company_name,
            "current_price": snapshot.current_price,
            "dcf_value": valuation.dcf_intrinsic_value_per_share,
            "dcf_upside_pct": valuation.dcf_upside_pct,
            "implied_fcf_cagr_5y": valuation.implied_fcf_cagr_5y,
            "forward_pe": multiples["forward_pe"],
            "ev_to_ebitda": multiples["ev_to_ebitda"],
            "roic_ttm": snapshot.roic_ttm,
            "fcf_margin_ttm": snapshot.fcf_margin_ttm,
            "earnings_quality_flag": valuation.earnings_quality_flag,
            "error": None,
        }
    except (FundamentalMemoError, ValueError) as exc:
        return {
            "ticker": symbol,
            "company_name": symbol,
            "current_price": None,
            "dcf_value": None,
            "dcf_upside_pct": None,
            "implied_fcf_cagr_5y": None,
            "forward_pe": None,
            "ev_to_ebitda": None,
            "roic_ttm": None,
            "fcf_margin_ttm": None,
            "earnings_quality_flag": "Error",
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ticker": symbol,
            "company_name": symbol,
            "current_price": None,
            "dcf_value": None,
            "dcf_upside_pct": None,
            "implied_fcf_cagr_5y": None,
            "forward_pe": None,
            "ev_to_ebitda": None,
            "roic_ttm": None,
            "fcf_margin_ttm": None,
            "earnings_quality_flag": "Error",
            "error": str(exc),
        }


def run_watchlist_scan(
    tickers: Sequence[str],
    wacc: float = DEFAULT_WACC,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    base_cagr: float = DEFAULT_MAX_FCF_GROWTH,
    exit_multiple: float = DEFAULT_EXIT_EV_EBITDA,
    offline_mock: bool = False,
    *,
    snapshot_fetcher: Callable[[str], FinancialSnapshot] | None = None,
) -> list[dict[str, Any]]:
    """Run the deterministic Python valuation engine across a basket of tickers (no LLM calls).

    Live scans execute concurrently via ThreadPoolExecutor to complete 5+ tickers in seconds
    while isolating per-ticker fetch or negative-FCF errors cleanly.
    """
    unique_tickers = _deduplicate_tickers(tickers)
    if not unique_tickers:
        return []

    if offline_mock or len(unique_tickers) == 1:
        return [
            _evaluate_single_ticker(
                symbol,
                wacc=wacc,
                terminal_growth=terminal_growth,
                base_cagr=base_cagr,
                exit_multiple=exit_multiple,
                offline_mock=offline_mock,
                snapshot_fetcher=snapshot_fetcher,
            )
            for symbol in unique_tickers
        ]

    max_workers = min(6, len(unique_tickers))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _evaluate_single_ticker,
                symbol,
                wacc=wacc,
                terminal_growth=terminal_growth,
                base_cagr=base_cagr,
                exit_multiple=exit_multiple,
                offline_mock=offline_mock,
                snapshot_fetcher=snapshot_fetcher,
            )
            for symbol in unique_tickers
        ]
        return [future.result() for future in futures]
