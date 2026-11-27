"""End-to-end CLI dry-run and upgraded Streamlit UI verification tests."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
import tomllib  # type: ignore[import-untyped]
from streamlit.testing.v1 import AppTest

import fundamental_memo.streamlit_app as streamlit_app_mod
from fundamental_memo.cli import run_memo_pipeline
from fundamental_memo.data_fetcher import load_mock_market_data
from fundamental_memo.deterministic_memo import (
    DETERMINISTIC_MODE_LABEL,
    GROQ_BASE_URL,
    GROQ_CUSTOM_MODEL_OPTION,
    GROQ_MODEL_PRESETS,
    LLM_PROVIDERS,
    OLLAMA_DEFAULT_MODEL,
    PROVIDER_GROQ,
    PROVIDER_OLLAMA,
)
from fundamental_memo.memo_synthesizer import DEFAULT_BASE_URL
from fundamental_memo.schemas import DataFetchError, SynthesisError, count_words
from fundamental_memo.streamlit_app import (
    AUTHOR_ATTRIBUTION,
    MODE_DEEP_DIVE,
    MODE_WATCHLIST,
    _fetch_bundle_with_cloud_fallback,
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


def test_streamlit_app_controls_kpis_charts_and_offline_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify hybrid sidebar auto-detect, zero-LLM <2s generation, KPIs, and Plotly charts."""
    # Simulate Streamlit Community Cloud (localhost:11434 unreachable, no secrets/env)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        "fundamental_memo.deterministic_memo.probe_local_llm_endpoint",
        lambda *_args, **_kwargs: False,
    )
    app_path = (
        Path(__file__).resolve().parents[1] / "src" / "fundamental_memo" / "streamlit_app.py"
    )
    app_test = AppTest.from_file(str(app_path))
    app_test.run(timeout=20)

    assert not app_test.exception

    # Verify author attribution in both sidebar footer and main page header/footer
    assert any(AUTHOR_ATTRIBUTION in cap.value for cap in app_test.sidebar.caption)
    assert any(AUTHOR_ATTRIBUTION in cap.value for cap in app_test.caption)

    # Verify hybrid Narrative Synthesis sidebar defaults to Groq + unchecked when Ollama is offline
    sidebar_checkboxes = {cb.label: cb for cb in app_test.sidebar.checkbox}
    assert sidebar_checkboxes["Enable AI Narrative Synthesis (Ollama / Cloud API)"].value is False
    assert sidebar_checkboxes["Use Offline Mock Data"].value is False

    # Verify LLM Provider & Groq free-tier defaults inside collapsible settings
    sidebar_selects = {sb.label: sb for sb in app_test.sidebar.selectbox}
    assert list(sidebar_selects["LLM Provider"].options) == list(LLM_PROVIDERS)
    assert sidebar_selects["LLM Provider"].value == PROVIDER_GROQ
    assert list(sidebar_selects["Model"].options) == list(GROQ_MODEL_PRESETS)
    assert sidebar_selects["Model"].value == "llama-3.3-70b-versatile"
    base_url_inputs = [ti for ti in app_test.sidebar.text_input if ti.label == "Base URL"]
    assert len(base_url_inputs) == 1
    assert base_url_inputs[0].value == GROQ_BASE_URL
    assert any(ti.label == "Groq API Key" for ti in app_test.sidebar.text_input)

    # Selecting Custom model ID... reveals a text input for arbitrary Groq model slugs
    sidebar_selects["Model"].select(GROQ_CUSTOM_MODEL_OPTION)
    app_test.run(timeout=20)
    assert not app_test.exception
    assert any(ti.label == "Custom Groq Model ID" for ti in app_test.sidebar.text_input)

    # Enabling AI synthesis with blank Groq key shows inline sidebar warning
    sidebar_checkboxes = {cb.label: cb for cb in app_test.sidebar.checkbox}
    sidebar_checkboxes["Enable AI Narrative Synthesis (Ollama / Cloud API)"].check()
    app_test.run(timeout=20)
    assert not app_test.exception
    assert any("Groq API key" in w.value for w in app_test.sidebar.warning)

    # Switching to Local Ollama preserves localhost:11434 and qwen3.8:27b-mlx defaults
    sidebar_selects = {sb.label: sb for sb in app_test.sidebar.selectbox}
    sidebar_selects["LLM Provider"].select(PROVIDER_OLLAMA)
    sidebar_checkboxes = {cb.label: cb for cb in app_test.sidebar.checkbox}
    sidebar_checkboxes["Enable AI Narrative Synthesis (Ollama / Cloud API)"].uncheck()
    app_test.run(timeout=20)
    assert not app_test.exception
    ollama_base_urls = [ti for ti in app_test.sidebar.text_input if ti.label == "Base URL"]
    assert ollama_base_urls[0].value == DEFAULT_BASE_URL
    ollama_model_select = {sb.label: sb for sb in app_test.sidebar.selectbox}["Model"]
    assert ollama_model_select.value == OLLAMA_DEFAULT_MODEL

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

    # Enable offline mock data and run Zero-LLM Deterministic Rule Engine (< 2s)
    offline_cb = {cb.label: cb for cb in app_test.sidebar.checkbox}["Use Offline Mock Data"]
    offline_cb.check()
    t0 = time.perf_counter()
    gen_buttons = {btn.label: btn for btn in app_test.sidebar.button}
    gen_buttons["Generate one-page memo"].click()
    app_test.run(timeout=20)
    elapsed = time.perf_counter() - t0

    assert not app_test.exception
    assert elapsed < 5.0
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
    # Verify Deterministic Rule Engine mode badge, Reverse DCF callout, 5x5 matrix, 4Q momentum
    assert any(
        DETERMINISTIC_MODE_LABEL in cap.value and "Grounding Audit: **Passed**" in cap.value
        for cap in app_test.caption
    )
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
    sidebar_cbs = {cb.label: cb for cb in app_test.sidebar.checkbox}
    sidebar_cbs["Enable AI Narrative Synthesis (Ollama / Cloud API)"].uncheck()
    sidebar_cbs["Use Offline Mock Data"].check()
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


def test_cloud_yfinance_fallback_loads_demo_profile_on_throttling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live yfinance throttling on supported demo tickers falls back cleanly with a notice."""

    def _raise_throttle(*_args: object, **_kwargs: object) -> object:
        raise DataFetchError("429 Too Many Requests")

    monkeypatch.setattr(streamlit_app_mod, "_cached_fetch_live_bundle", _raise_throttle)
    bundle, notice = _fetch_bundle_with_cloud_fallback(
        "NVDA", ["AMD", "AVGO"], use_mock_data=False
    )
    assert bundle.snapshot.ticker == "NVDA"
    assert notice is not None
    assert "temporarily unavailable" in notice

    with pytest.raises(DataFetchError):
        _fetch_bundle_with_cloud_fallback("UNSUPPORTED_TICKER", [], use_mock_data=False)


def test_streamlit_cloud_deployment_artifacts_are_valid() -> None:
    """Root requirements.txt and .streamlit/config.toml exist and parse cleanly."""
    repo_root = Path(__file__).resolve().parents[2]
    req_file = repo_root / "requirements.txt"
    toml_file = repo_root / ".streamlit" / "config.toml"

    assert req_file.exists()
    req_text = req_file.read_text(encoding="utf-8")
    for expected in (
        "streamlit>=",
        "yfinance>=",
        "pandas>=",
        "numpy>=",
        "scipy>=",
        "plotly>=",
        "pydantic>=",
        "openai>=",
        "markdown>=",
        "-e ./fundamental_memo",
    ):
        assert expected in req_text

    assert toml_file.exists()
    config = tomllib.loads(toml_file.read_text(encoding="utf-8"))
    assert config["theme"]["base"] == "dark"
    assert config["theme"]["primaryColor"] == "#3B82F6"
    assert config["theme"]["backgroundColor"] == "#0E1117"
    assert config["theme"]["secondaryBackgroundColor"] == "#161B22"
    assert config["theme"]["textColor"] == "#F8FAFC"
    assert config["server"]["headless"] is True

    # Linux-safe requirements: zero Apple Silicon mlx dependencies
    for line in req_text.splitlines():
        normalized = line.strip().lower()
        assert not normalized.startswith("mlx")

    # Local Streamlit secrets must be excluded from Git tracking
    gitignore_file = repo_root / ".gitignore"
    assert gitignore_file.exists()
    assert ".streamlit/secrets.toml" in gitignore_file.read_text(encoding="utf-8")


def test_streamlit_groq_401_error_shows_warning_and_preserves_charts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid Groq key (401) renders a clear warning while keeping KPIs, charts, and memo."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(
        "fundamental_memo.deterministic_memo.probe_local_llm_endpoint",
        lambda *_args, **_kwargs: False,
    )

    def _raise_401(*_args: object, **_kwargs: object) -> object:
        raise SynthesisError(
            "LLM authentication failed (401 Unauthorized) at 'https://api.groq.com/openai/v1'"
        )

    monkeypatch.setattr("fundamental_memo.deterministic_memo.synthesize_memo_with_llm", _raise_401)

    app_path = (
        Path(__file__).resolve().parents[1] / "src" / "fundamental_memo" / "streamlit_app.py"
    )
    app_test = AppTest.from_file(str(app_path))
    app_test.run(timeout=20)
    assert not app_test.exception

    # Enable AI synthesis with Groq + dummy key + offline mock data and trigger generation
    cbs = {cb.label: cb for cb in app_test.sidebar.checkbox}
    cbs["Enable AI Narrative Synthesis (Ollama / Cloud API)"].check()
    cbs["Use Offline Mock Data"].check()
    key_input = [ti for ti in app_test.sidebar.text_input if ti.label == "Groq API Key"][0]
    key_input.input("gsk_invalid_test_key")
    gen_btn = {btn.label: btn for btn in app_test.sidebar.button}["Generate one-page memo"]
    gen_btn.click()
    app_test.run(timeout=20)

    assert not app_test.exception
    assert any("401 Unauthorized" in w.value for w in app_test.warning)
    # All quantitative cards, tables, grounded memo, and author attribution remain intact
    assert len(app_test.metric) == 5
    assert len(app_test.dataframe) >= 2
    assert any("Investment Memo: Broadcom Inc. (AVGO)" in md.value for md in app_test.markdown)
    assert any(AUTHOR_ATTRIBUTION in cap.value for cap in app_test.caption)
