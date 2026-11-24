"""Unit tests for the pure-Python batch Watchlist Quick-Scan Screener."""

from __future__ import annotations

import time

import pytest

from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.schemas import DataFetchError, FinancialSnapshot
from fundamental_memo.screener import run_watchlist_scan


def test_run_watchlist_scan_offline_mock_evaluates_five_tickers_rapidly() -> None:
    """Offline mock watchlist scan returns 5 differentiated valuation records well under 5s."""
    t0 = time.perf_counter()
    results = run_watchlist_scan(
        tickers=["NVDA", "AMD", "MRVL", "QCOM", "AVGO", "nvda"],
        wacc=0.095,
        terminal_growth=0.025,
        base_cagr=0.15,
        exit_multiple=15.0,
        offline_mock=True,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < 5.0
    assert len(results) == 5
    assert [row["ticker"] for row in results] == ["NVDA", "AMD", "MRVL", "QCOM", "AVGO"]

    required_keys = {
        "ticker",
        "company_name",
        "current_price",
        "dcf_value",
        "dcf_upside_pct",
        "implied_fcf_cagr_5y",
        "forward_pe",
        "ev_to_ebitda",
        "roic_ttm",
        "fcf_margin_ttm",
        "earnings_quality_flag",
        "error",
    }
    for row in results:
        assert required_keys.issubset(row.keys())
        assert row["error"] is None
        assert row["current_price"] > 0.0
        assert row["dcf_value"] > 0.0
        assert row["ev_to_ebitda"] is not None
        assert row["fcf_margin_ttm"] is not None

    # Differentiated bundled mock profiles rather than identical clones
    prices = {row["current_price"] for row in results}
    assert len(prices) == 5


def test_run_watchlist_scan_isolates_per_ticker_failures() -> None:
    """A fetch error or negative-FCF ticker is isolated cleanly without aborting valid tickers."""
    valid_avgo = load_mock_market_data("AVGO").snapshot
    neg_fcf_snap = valid_avgo.model_copy(
        update={
            "ticker": "NEGF",
            "company_name": "Negative FCF Corp",
            "free_cash_flow_ttm": -500_000_000.0,
        }
    )

    def _fake_fetcher(symbol: str) -> FinancialSnapshot:
        if symbol == "BAD":
            raise DataFetchError("Ticker BAD not found")
        if symbol == "NEGF":
            return neg_fcf_snap
        return valid_avgo

    results = run_watchlist_scan(
        tickers=["AVGO", "BAD", "NEGF"],
        wacc=0.095,
        terminal_growth=0.025,
        base_cagr=0.15,
        exit_multiple=15.0,
        offline_mock=False,
        snapshot_fetcher=_fake_fetcher,
    )
    assert [row["ticker"] for row in results] == ["AVGO", "BAD", "NEGF"]
    assert results[0]["error"] is None
    assert results[0]["dcf_value"] == pytest.approx(97.25, abs=0.5)
    assert results[1]["error"] is not None and "BAD" in results[1]["error"]
    assert results[1]["earnings_quality_flag"] == "Error"
    assert results[2]["error"] is not None and "free cash flow" in results[2]["error"].lower()
