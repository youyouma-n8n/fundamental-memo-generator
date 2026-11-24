"""End-to-end CLI dry-run and upgraded Streamlit UI verification tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

from fundamental_memo.cli import run_memo_pipeline
from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.memo_synthesizer import DEFAULT_BASE_URL, SUPPORTED_MODELS
from fundamental_memo.schemas import count_words
from fundamental_memo.streamlit_app import (
    MODE_DEEP_DIVE,
    MODE_WATCHLIST,
    build_quarterly_momentum_dataframe,
    build_styled_watchlist_table,
)


def test_cli_offline_mock_data_end_to_end(tmp_path: Path) -> None:
    """Running CLI with --mock-data produces upgraded memo_AVGO.md under 750 words cleanly."""
    output_file = tmp_path / "memo_AVGO.md"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "fundamental_memo.cli",
            "--ticker",
            "AVGO",
            "--peers",
            "NVDA,AMD,MRVL,QCOM",
            "--wacc",
            "0.095",
            "--terminal-growth",
            "0.025",
            "--fcf-cagr",
            "0.15",
            "--exit-multiple",
            "15.0",
            "--model",
            "inkling-2-mini:latest",
            "--base-url",
            DEFAULT_BASE_URL,
            "--mock-data",
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert output_file.exists()

    memo_text = output_file.read_text(encoding="utf-8")
    word_count = count_words(memo_text)
    assert 400 <= word_count <= 750
    assert "Broadcom Inc. (AVGO)" in memo_text
    assert "## Valuation & The Debate (Variant Perception)" in memo_text
    assert "## Profitability & Cash Quality" in memo_text
    assert "## Key Downside Risks" in memo_text


def test_cli_invalid_wacc_returns_nonzero_exit(tmp_path: Path) -> None:
    """Invalid WACC <= terminal growth must exit non-zero with a concise stderr message."""
    output_file = tmp_path / "memo_bad.md"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "fundamental_memo.cli",
            "--ticker",
            "AVGO",
            "--peers",
            "NVDA,AMD,MRVL,QCOM",
            "--wacc",
            "0.02",
            "--terminal-growth",
            "0.03",
            "--mock-data",
            "--output",
            str(output_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    assert "strictly exceed" in completed.stderr
    assert not output_file.exists()


def test_streamlit_app_controls_kpis_charts_and_offline_generation() -> None:
    """Verify sidebar controls, 5 KPI cards, Plotly charts, and memo generation in offline mode."""
    app_path = (
        Path(__file__).resolve().parents[1] / "src" / "fundamental_memo" / "streamlit_app.py"
    )
    app_test = AppTest.from_file(str(app_path))
    app_test.run(timeout=20)

    assert not app_test.exception

    # Verify model dropdown & Ollama base URL
    assert len(app_test.sidebar.selectbox) == 1
    model_selector = app_test.sidebar.selectbox[0]
    assert list(model_selector.options) == list(SUPPORTED_MODELS)
    assert model_selector.value == "inkling-2-mini:latest"
    assert app_test.sidebar.text_input[2].value == DEFAULT_BASE_URL

    # Verify Bear / Base / Bull scenario presets update all 4 DCF inputs in st.session_state
    preset_buttons = {btn.label: btn for btn in app_test.sidebar.button}
    preset_buttons["Bear"].click()
    app_test.run(timeout=20)
    assert not app_test.exception
    bear_inputs = {widget.label: widget.value for widget in app_test.sidebar.number_input}
    assert bear_inputs["WACC"] == 0.105
    assert bear_inputs["Terminal growth rate"] == 0.020
    assert bear_inputs["5Y FCF CAGR"] == 0.080
    assert bear_inputs["Terminal Exit EV/EBITDA Multiple"] == 12.0

    preset_buttons = {btn.label: btn for btn in app_test.sidebar.button}
    preset_buttons["Bull"].click()
    app_test.run(timeout=20)
    assert not app_test.exception
    bull_inputs = {widget.label: widget.value for widget in app_test.sidebar.number_input}
    assert bull_inputs["WACC"] == 0.085
    assert bull_inputs["Terminal growth rate"] == 0.030
    assert bull_inputs["5Y FCF CAGR"] == 0.250
    assert bull_inputs["Terminal Exit EV/EBITDA Multiple"] == 20.0

    preset_buttons = {btn.label: btn for btn in app_test.sidebar.button}
    preset_buttons["Base"].click()
    app_test.run(timeout=20)
    assert not app_test.exception
    num_inputs = {widget.label: widget.value for widget in app_test.sidebar.number_input}
    assert num_inputs["WACC"] == 0.095
    assert num_inputs["Terminal growth rate"] == 0.025
    assert num_inputs["5Y FCF CAGR"] == 0.15
    assert num_inputs["Terminal Exit EV/EBITDA Multiple"] == 15.0

    # Select gemma4:31b-mlx, toggle offline mock mode, and trigger generation.
    app_test.sidebar.selectbox[0].select("gemma4:31b-mlx")
    app_test.sidebar.checkbox[0].check()
    gen_buttons = {btn.label: btn for btn in app_test.sidebar.button}
    gen_buttons["Generate one-page memo"].click()
    app_test.run(timeout=20)

    assert not app_test.exception
    # Verify 5 non-truncating KPI metric cards
    assert len(app_test.metric) == 5
    metric_labels = [metric.label for metric in app_test.metric]
    assert metric_labels == [
        "Current Price",
        "DCF Intrinsic Value",
        "Market-Implied CAGR",
        "ROIC (TTM)",
        "Earnings Quality",
    ]
    # Verify Reverse DCF Reality Check callout, 5x5 sensitivity table, 4Q momentum tab & caption
    assert any("Reverse DCF" in info.title or "5Y FCF CAGR" in info.value for info in app_test.info)
    assert len(app_test.dataframe) >= 2
    assert any(
        "implies an exit EV/EBITDA" in caption.value for caption in app_test.caption
    )
    assert any("Annual FCF progression:" in caption.value for caption in app_test.caption)
    assert any("Last 4 completed fiscal quarters" in caption.value for caption in app_test.caption)
    # Verify rendered memo Markdown
    assert any("Investment Memo: Broadcom Inc. (AVGO)" in md.value for md in app_test.markdown)
    assert any(
        "Valuation & The Debate (Variant Perception)" in md.value for md in app_test.markdown
    )
    # Verify no deprecated use_container_width remains in streamlit_app.py
    assert "use_container_width" not in app_path.read_text(encoding="utf-8")


def test_build_quarterly_momentum_dataframe_formats_columns() -> None:
    """Quarterly momentum table builder formats all 5 columns cleanly for 4 mock quarters."""
    bundle = load_mock_market_data()
    df = build_quarterly_momentum_dataframe(bundle.snapshot.quarterly_trajectory)
    assert list(df.columns) == [
        "Quarter",
        "Revenue ($B)",
        "Gross Margin (%)",
        "Operating Margin (%)",
        "FCF ($B)",
    ]
    assert len(df) == 4
    assert list(df["Quarter"]) == ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"]
    assert df["Revenue ($B)"].iloc[-1].startswith("$")
    assert df["Gross Margin (%)"].iloc[-1].endswith("%")


def test_run_memo_pipeline_excludes_target_ticker_from_peers() -> None:
    """Including the target ticker in the peer list automatically excludes self-comparison."""
    result = run_memo_pipeline(
        ticker="NVDA",
        peers=["NVDA", "AMD", "MRVL", "QCOM"],
        mock_data=True,
    )
    assert "NVDA" not in [peer.ticker for peer in result.peers]
    assert set(peer.ticker for peer in result.peers) == {"AMD", "MRVL", "QCOM"}


def test_streamlit_watchlist_screener_and_one_click_deep_dive_handoff() -> None:
    """Switch to Watchlist Screener, scan 5 mock tickers, and hand off NVDA into Deep-Dive."""
    app_path = (
        Path(__file__).resolve().parents[1] / "src" / "fundamental_memo" / "streamlit_app.py"
    )
    app_test = AppTest.from_file(str(app_path))
    app_test.run(timeout=20)
    assert not app_test.exception

    # Enable offline mock mode in sidebar and switch to Watchlist Quick-Scan Screener
    app_test.sidebar.checkbox[0].check()
    app_test.session_state["active_mode"] = MODE_WATCHLIST
    app_test.run(timeout=20)
    assert not app_test.exception

    main_buttons = {btn.label: btn for btn in app_test.button}
    assert "Run Batch Valuation Scan" in main_buttons
    main_buttons["Run Batch Valuation Scan"].click()
    app_test.run(timeout=20)
    assert not app_test.exception

    # Screener table rendered with 5 tickers
    assert len(app_test.dataframe) >= 1
    assert any("pure Python, no LLM" in cap.value for cap in app_test.caption)

    # Select NVDA and click Load Selected Ticker into Deep-Dive
    watchlist_select = [sb for sb in app_test.selectbox if "One-Page Memo" in sb.label][0]
    watchlist_select.select("NVDA")
    load_btn = {btn.label: btn for btn in app_test.button}["Load Selected Ticker into Deep-Dive"]
    load_btn.click()
    app_test.run(timeout=20)
    assert not app_test.exception

    # Verify atomic switch back to Single-Stock Deep-Dive and rendered NVDA memo
    assert app_test.session_state["active_mode"] == MODE_DEEP_DIVE
    assert app_test.session_state["target_ticker"] == "NVDA"
    assert any("NVIDIA Corporation (NVDA)" in md.value for md in app_test.markdown)

    # Verify styled watchlist helper directly
    from fundamental_memo.screener import run_watchlist_scan

    scan = run_watchlist_scan(["NVDA", "AVGO"], offline_mock=True)
    styler = build_styled_watchlist_table(scan)
    assert list(styler.data["Ticker"]) == ["NVDA", "AVGO"]
